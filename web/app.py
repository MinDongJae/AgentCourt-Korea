"""FastAPI 웹 서버 — 양형기준 검색 어시스턴트 fancy UI.

Gradio 대체. 리츠고/빅케이스/슈퍼로이어 수준의 단일 페이지 앱.

실행:
  python web/app.py
  → http://localhost:7860
"""
from __future__ import annotations
import sys
import os
import json
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# .env 로드
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
os.environ.setdefault("INDEX_DIR", str(ROOT / "data"))
os.environ.setdefault("LAW_API_MODE", "real")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.multi_persona import analyze_case
from core.retriever import SentencingRetriever

app = FastAPI(title="양형기준 검색 어시스턴트")

WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.on_event("startup")
async def warmup():
    """Retriever 사전 로드 → 첫 호출 지연 회피."""
    try:
        SentencingRetriever()
        print("✅ Retriever 로드 완료")
    except Exception as e:
        print(f"⚠ Retriever 로드 실패: {e}")


class CaseRequest(BaseModel):
    description: str
    top_k: int = 5
    prefer_lower_inst: bool = True  # 1·2심 우선 정렬 (양형 결정 사례에 가까움)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.post("/api/analyze")
async def api_analyze(req: CaseRequest):
    t0 = time.time()
    result = analyze_case(req.description, top_k=req.top_k, prefer_lower_inst=req.prefer_lower_inst)
    elapsed = time.time() - t0
    result["_elapsed_seconds"] = round(elapsed, 2)
    return JSONResponse(result)


class BenchRequest(BaseModel):
    description: str
    top_k: int = 5
    full_4_stages: bool = False  # Stage 4 (7명 위원 합의) 활성화 여부


@app.post("/api/bench")
async def api_bench(req: BenchRequest):
    """AgentsBench 4단계 다중 에이전트 양형 시뮬레이션 (동기, 30s timeout 가능)."""
    from core.agents_bench import simulate_bench
    return JSONResponse(simulate_bench(
        req.description,
        top_k=req.top_k,
        full_4_stages=req.full_4_stages,
    ))


# ─── Async Polling (API GW 30s 한계 우회) ───────────────────────────────
S3_BUCKET = "aptbaechi-sentencing-frontend"
S3_JOBS_PREFIX = "jobs/"


@app.post("/api/bench-submit")
async def api_bench_submit(req: BenchRequest):
    """job_id 즉시 반환 + Lambda async invoke로 background 토론 시작."""
    import uuid, boto3, json as _json, os as _os
    job_id = uuid.uuid4().hex[:16]

    # 1. S3에 PENDING 상태 기록
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=f"{S3_JOBS_PREFIX}{job_id}.json",
        Body=_json.dumps({"status": "PENDING", "stage": 0}, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )

    # 2. 자기 자신 Lambda async invoke (worker mode)
    fn_name = _os.getenv("AWS_LAMBDA_FUNCTION_NAME", "aptbaechi-sentencing-rag")
    lam = boto3.client("lambda")
    lam.invoke(
        FunctionName=fn_name,
        InvocationType="Event",  # async
        Payload=_json.dumps({
            "_internal_worker": True,
            "job_id": job_id,
            "description": req.description,
            "top_k": req.top_k,
            "full_4_stages": req.full_4_stages,
        }).encode("utf-8"),
    )

    return JSONResponse({"job_id": job_id, "status": "PENDING"})


@app.get("/api/bench-result/{job_id}")
async def api_bench_result(job_id: str):
    """polling endpoint — S3에서 job 결과 읽기."""
    import boto3, json as _json
    if not job_id.isalnum() or len(job_id) > 32:
        return JSONResponse({"error": "invalid job_id"}, status_code=400)
    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=f"{S3_JOBS_PREFIX}{job_id}.json")
        data = _json.loads(obj["Body"].read())
        return JSONResponse(data)
    except s3.exceptions.NoSuchKey:
        return JSONResponse({"status": "NOT_FOUND"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


class VerifyRequest(BaseModel):
    text: str


@app.post("/api/verify-citations")
async def api_verify_citations(req: VerifyRequest):
    """LLM 생성 텍스트의 법령·사건번호 인용 검증 (환각 탐지)."""
    from mcp_law.citation_verify import verify_text
    return JSONResponse(verify_text(req.text))


@app.get("/api/health")
async def api_health():
    """시스템 상태 — UI 상단 표시용."""
    r = SentencingRetriever()
    try:
        _ = r.retrieve("사기", persona="judge", top_k=1)
        retriever_ok = True
        n_chunks = len(r.chunks)
        mode = r._mode
    except Exception:
        retriever_ok = False
        n_chunks = 0
        mode = "error"

    llm_status = "anthropic" if os.getenv("ANTHROPIC_API_KEY") else (
        "gemini" if os.getenv("GEMINI_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "none"
    )
    law_mode = os.getenv("LAW_API_MODE", "mock")

    return {
        "retriever": {"ok": retriever_ok, "chunks": n_chunks, "mode": mode},
        "llm": llm_status,
        "law_api": law_mode,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S KST", time.gmtime(time.time() + 32400)),
    }


@app.get("/api/sample-cases")
async def api_sample_cases():
    """예시 사건 6개 — UI 좌측 사이드바용."""
    return [
        {"id": "case01", "title": "사기 5천만원 초범", "description": "사기죄 피해액 5천만원 초범 변제 합의 안 됨 부양가족 1인"},
        {"id": "case02", "title": "음주운전 0.18% 재범", "description": "음주운전 혈중알코올농도 0.18% 사고 없음 재범 자수"},
        {"id": "case03", "title": "마약 단순 투약", "description": "마약 투약 단순 소지 초범 가족 부양 치료 의지 강함"},
        {"id": "case04", "title": "보이스피싱 인출책", "description": "보이스피싱 인출책 가담 1회 자백 피해 회복 일부"},
        {"id": "case05", "title": "성범죄 합의·자수", "description": "강제추행 합의 자수 진지한 반성 초범 우발적"},
        {"id": "case06", "title": "절도 야간주거침입", "description": "절도 야간 주거침입 흉기 휴대 상습범 피해 변제 무"},
    ]


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("⚖ 양형기준 검색 어시스턴트")
    print("=" * 60)
    print("  URL:    http://localhost:7860")
    print("  PDF:    907p × 901 chunks (FAISS 3072d)")
    print("  LLM:    Claude Opus 4.7 → Gemini 2.5 Flash → GPT-4o")
    print("  법제처:  법령·판례·자치법규 (실 API)")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="info")
