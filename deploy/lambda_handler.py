"""Lambda handler — Mangum FastAPI + Worker 모드 분기.

worker 모드 (async invoke 시):
  payload['_internal_worker'] = True 인 경우 Mangum 우회 + bench 직접 실행 + S3 결과 저장
"""
from __future__ import annotations
import sys, os, json, traceback
from pathlib import Path

sys.path.insert(0, "/var/task")
os.environ.setdefault("INDEX_DIR", "/var/task/data")
os.environ.setdefault("LAW_API_MODE", "real")

# FastAPI 앱 import
import importlib.util
spec = importlib.util.spec_from_file_location("web_app", "/var/task/web/app.py")
web_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_app_module)
app = web_app_module.app

from mangum import Mangum
mangum_handler = Mangum(app, lifespan="off")


def _worker_run(event):
    """Async invoke worker — bench 시뮬 실행 + Stage별 S3 업데이트."""
    import boto3
    job_id = event.get("job_id")
    description = event.get("description", "")
    top_k = int(event.get("top_k", 5))
    full_4 = bool(event.get("full_4_stages", False))

    s3 = boto3.client("s3")
    bucket = "aptbaechi-sentencing-frontend"
    key = f"jobs/{job_id}.json"

    def update(state):
        s3.put_object(
            Bucket=bucket, Key=key,
            Body=json.dumps(state, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json", CacheControl="no-cache",
        )

    try:
        from core.agents_bench import (
            stage1_independent, stage2_deliberation, stage3_final, stage4_consensus,
        )
        import time
        t0 = time.time()

        update({"status": "RUNNING", "stage": 1, "message": "Stage 1: 검사·변호인·판사 독립 분석 중"})
        s1 = stage1_independent(description, top_k=top_k)
        if "error" in s1:
            update({"status": "ERROR", "error": s1["error"]})
            return
        update({"status": "RUNNING", "stage": 2, "message": "Stage 2: 토론 3턴 진행 중", "stage1": s1})

        s2 = stage2_deliberation(description, s1)
        update({"status": "RUNNING", "stage": 3, "message": "Stage 3: 최종 양형 결정 중", "stage1": s1, "stage2": s2})

        s3_result = stage3_final(description, s2)
        out = {
            "status": "DONE" if not full_4 else "RUNNING",
            "stage": 4 if full_4 else "DONE",
            "stage1": s1, "stage2": s2, "stage3": s3_result,
            "_elapsed_seconds": round(time.time() - t0, 2),
            "_methodology": "AgentsBench 4-stage simulation",
        }
        if full_4:
            out["message"] = "Stage 4: 양형위원회 7명 합의 진행 중"
            update(out)
            s4 = stage4_consensus(description, s3_result)
            out["stage4"] = s4
            out["status"] = "DONE"
            out["stage"] = "DONE"
            out["_elapsed_seconds"] = round(time.time() - t0, 2)
        update(out)
    except Exception as e:
        update({"status": "ERROR", "error": str(e), "trace": traceback.format_exc()[:2000]})


def handler(event, context):
    # Worker mode (async invoke from /api/bench-submit)
    if event.get("_internal_worker"):
        _worker_run(event)
        return {"ok": True}
    # 일반 HTTP 요청 (API GW / Lambda URL)
    return mangum_handler(event, context)
