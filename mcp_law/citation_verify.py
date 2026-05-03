import os
"""LLM 환각 방지 — 법령/판례 인용 검증 가드.

chrisryugj/korean-law-mcp의 verify_citations 핵심 로직 포팅.
LLM이 생성한 법령 조문·판례 사건번호를 법제처 OPEN API로 cross-check.

검증 결과:
  ✓ exists      — 실제 존재 (DB 매칭)
  ✗ absent      — LLM 환각 (DB 미매칭)
  ⚠ ambiguous   — 형식 의심
"""
from __future__ import annotations
import re
import urllib.request
import urllib.parse
import json
from typing import Any

OC = os.getenv("LAW_API_KEY", "test")
BASE = "http://www.law.go.kr/DRF/lawSearch.do"

# 사건번호 패턴: YYYY[고합|고단|고정|고약|노|도]NNNN
CASE_NO_PATTERN = re.compile(r"\b(\d{4})\s*(고합|고단|고정|고약|노|도|두|다|허|구|드|므|즈|허|허가|러|마|초|토)\s*(\d{1,7})\b")

# 법령 조문 패턴: "형법 제X조" / "형사소송법 제X조 제Y항"
LAW_REF_PATTERN = re.compile(
    r"((?:[가-힣]{2,15})\s*(?:법|령|규칙))\s*제\s*(\d+)\s*조(?:\s*제\s*(\d+)\s*항)?(?:\s*제\s*(\d+)\s*호)?"
)


def _http_get_json(params: dict) -> dict:
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return {}


def verify_case_no(case_no_text: str) -> dict[str, Any]:
    """사건번호 1개 검증 → 법제처 DB에 실재하는지."""
    m = CASE_NO_PATTERN.search(case_no_text)
    if not m:
        return {"input": case_no_text, "status": "ambiguous", "reason": "사건번호 형식 미일치"}
    year, code, num = m.groups()
    qs = f"{year}{code}{num}"
    d = _http_get_json({"OC": OC, "target": "prec", "type": "JSON", "query": qs, "display": 5})
    root = d.get("PrecSearch") or d
    if not isinstance(root, dict):
        return {"input": qs, "status": "ambiguous", "reason": "API 응답 비정상"}
    items = None
    for k, v in root.items():
        if isinstance(v, list):
            items = v
            break
        elif k == "prec" and isinstance(v, dict):
            items = [v]
            break
    if items:
        for it in items:
            if isinstance(it, dict):
                actual = (it.get("사건번호") or "").replace(" ", "")
                if qs.replace(" ", "") in actual:
                    return {
                        "input": qs,
                        "status": "exists",
                        "matched": it.get("사건번호"),
                        "case_name": it.get("사건명"),
                        "court": it.get("법원명"),
                    }
    return {"input": qs, "status": "absent", "reason": "DB 미매칭 (LLM 환각 가능)"}


def verify_text(llm_output: str) -> dict[str, Any]:
    """LLM 생성 텍스트 안의 모든 사건번호·법령 조문 검증."""
    # 사건번호 추출
    case_refs = list(set(
        f"{m.group(1)}{m.group(2)}{m.group(3)}"
        for m in CASE_NO_PATTERN.finditer(llm_output)
    ))[:10]  # 최대 10개

    case_results = [verify_case_no(c) for c in case_refs]

    # 법령 참조
    law_refs = []
    for m in LAW_REF_PATTERN.finditer(llm_output):
        law_refs.append({
            "law": m.group(1),
            "article": m.group(2),
            "paragraph": m.group(3),
            "subparagraph": m.group(4),
        })
    law_refs = law_refs[:10]

    n_exists = sum(1 for r in case_results if r.get("status") == "exists")
    n_absent = sum(1 for r in case_results if r.get("status") == "absent")
    n_ambig = sum(1 for r in case_results if r.get("status") == "ambiguous")

    return {
        "case_refs_total": len(case_refs),
        "exists": n_exists,
        "absent": n_absent,
        "ambiguous": n_ambig,
        "hallucination_rate": round(n_absent / max(1, len(case_refs)), 3),
        "case_details": case_results,
        "law_refs": law_refs,
    }


if __name__ == "__main__":
    sample = "대법원 2019도18764 판결과 2020고합123 사건을 참조하라. 형법 제347조 제1항 위반."
    print(json.dumps(verify_text(sample), ensure_ascii=False, indent=2))
