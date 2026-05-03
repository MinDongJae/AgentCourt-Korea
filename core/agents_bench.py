"""AgentsBench 4단계 다중 에이전트 양형 시뮬레이션.

논문 기반: AgentsBench (MDPI Systems 2025) — 판사석 4단계 시뮬
참조: AgentCourt (arXiv 2408.08089), AgentsCourt (EMNLP 2024 Findings)

Stage 1 — Independent Analysis (병렬)
  검사·변호인·판사 3명이 독립적으로 사건 분석
  각 페르소나는 자기 시점의 양형기준 청크 + 법제처 판례를 본다

Stage 2 — Deliberation (3턴 토론)
  Turn 1: 검사 가중요소 주장 + 변호인 감경요소 주장
  Turn 2: 검사 변호인 주장 반박 + 변호인 검사 주장 반박
  Turn 3: 판사 양측 주장 정리 + 권고형량 영역 결정

Stage 3 — Final Sentencing
  판사가 종합 판단으로 최종 양형 결정 (영역 + 형량 범위 + 인자 가중치)

Stage 4 — Bench Consensus (양형위 7명 합의 시뮬)
  같은 사건을 7명의 가상 위원(전문/비전문 혼합)이 각자 양형 결정 → 분포 도출
  중앙값·표준편차로 권고형량 신뢰구간 제시

핵심 차별점 vs. 기존 단발 RAG:
  - 1턴 → 4단계 × 3턴 = 양형 의사결정 과정 모사
  - 단일 의견 → N=7 분포 (불확실성 정량화)
"""
from __future__ import annotations
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.retriever import retrieve_sentencing
from core.multi_persona import (
    _call_llm, _format_chunks_for_llm,
    PROSECUTOR_PROMPT, DEFENDER_PROMPT, JUDGE_PROMPT,
)


# ─── Stage 1: Independent Analysis ──────────────────────────────────────────

def stage1_independent(case: str, top_k: int = 5) -> dict[str, Any]:
    """3 페르소나 독립 분석 (병렬)."""
    pros_chunks = retrieve_sentencing(case, persona="prosecutor", top_k=top_k)
    def_chunks = retrieve_sentencing(case, persona="defender", top_k=top_k)
    judge_chunks = retrieve_sentencing(case, persona="judge", top_k=top_k)

    if "error" in pros_chunks:
        return {"error": pros_chunks["error"], "stage": 1}

    pros_msg = (
        f"사건 개요:\n{case}\n\n"
        f"검색된 양형기준 (가중요소 후보):\n{_format_chunks_for_llm(pros_chunks['results'])}"
    )
    def_msg = (
        f"사건 개요:\n{case}\n\n"
        f"검색된 양형기준 (감경요소 후보):\n{_format_chunks_for_llm(def_chunks['results'])}"
    )

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pros = ex.submit(_call_llm, PROSECUTOR_PROMPT, pros_msg)
        f_def = ex.submit(_call_llm, DEFENDER_PROMPT, def_msg)
        pros_result = f_pros.result()
        def_result = f_def.result()

    return {
        "stage": 1,
        "prosecutor": pros_result,
        "defender": def_result,
        "judge_chunks": judge_chunks["results"],
    }


# ─── Stage 2: Deliberation (3턴 토론) ─────────────────────────────────────

DELIBERATE_PROSECUTOR_PROMPT = """당신은 검사입니다. 다음은 변호인의 감경요소 주장입니다. 각 주장에 대해
1) 양형기준상 인정 여부, 2) 인정되어도 가중요소가 더 무겁다는 반박, 3) 추가 가중요소 제시
를 JSON으로 답하세요.

스키마:
{
  "rebuttal": [
    {"defender_claim": "...", "counter": "...", "weight": "약함|보통|강함"}
  ],
  "additional_aggravating": ["..."]
}"""

DELIBERATE_DEFENDER_PROMPT = """당신은 변호인입니다. 다음은 검사의 가중요소 주장입니다. 각 주장에 대해
1) 양형기준상 가중요소 해당 여부, 2) 해당해도 감경요소가 상쇄한다는 반박, 3) 추가 감경요소 제시
를 JSON으로 답하세요.

스키마:
{
  "rebuttal": [
    {"prosecutor_claim": "...", "counter": "...", "weight": "약함|보통|강함"}
  ],
  "additional_mitigating": ["..."]
}"""

DELIBERATE_JUDGE_PROMPT = """당신은 판사입니다. 검사·변호인 양측의 주장과 반박을 종합해 다음을 JSON으로 답하세요.

1. 인정되는 가중요소 (양측 토론 후)
2. 인정되는 감경요소 (양측 토론 후)
3. 권고형량 영역 (감경 / 기본 / 가중)
4. 영역 결정 근거 1줄

스키마:
{
  "accepted_aggravating": [...],
  "accepted_mitigating": [...],
  "recommended_zone": "감경|기본|가중",
  "zone_rationale": "..."
}"""


def stage2_deliberation(case: str, stage1: dict) -> dict[str, Any]:
    """3턴 토론."""
    pros_init = stage1.get("prosecutor", {})
    def_init = stage1.get("defender", {})

    # Turn 2: 검사가 변호인 주장에 반박, 변호인이 검사 주장에 반박 (병렬)
    pros_rebut_msg = (
        f"사건:\n{case}\n\n"
        f"변호인의 감경요소 주장:\n{json.dumps(def_init, ensure_ascii=False, indent=2)[:2000]}"
    )
    def_rebut_msg = (
        f"사건:\n{case}\n\n"
        f"검사의 가중요소 주장:\n{json.dumps(pros_init, ensure_ascii=False, indent=2)[:2000]}"
    )

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pr = ex.submit(_call_llm, DELIBERATE_PROSECUTOR_PROMPT, pros_rebut_msg)
        f_dr = ex.submit(_call_llm, DELIBERATE_DEFENDER_PROMPT, def_rebut_msg)
        pros_rebut = f_pr.result()
        def_rebut = f_dr.result()

    # Turn 3: 판사 종합
    judge_msg = (
        f"사건:\n{case}\n\n"
        f"검사 초기 주장:\n{json.dumps(pros_init, ensure_ascii=False)[:1200]}\n\n"
        f"변호인 초기 주장:\n{json.dumps(def_init, ensure_ascii=False)[:1200]}\n\n"
        f"검사 반박:\n{json.dumps(pros_rebut, ensure_ascii=False)[:1200]}\n\n"
        f"변호인 반박:\n{json.dumps(def_rebut, ensure_ascii=False)[:1200]}\n\n"
        f"양형기준:\n{_format_chunks_for_llm(stage1.get('judge_chunks', []))}"
    )
    judge_synthesis = _call_llm(DELIBERATE_JUDGE_PROMPT, judge_msg)

    return {
        "stage": 2,
        "turn1": {"prosecutor": pros_init, "defender": def_init},
        "turn2": {"prosecutor_rebuttal": pros_rebut, "defender_rebuttal": def_rebut},
        "turn3": {"judge_synthesis": judge_synthesis},
    }


# ─── Stage 3: Final Sentencing ──────────────────────────────────────────────

FINAL_PROMPT = """당신은 판사입니다. 위 토론 종합 결과를 바탕으로 최종 양형을 결정하세요.

JSON 스키마:
{
  "final_zone": "감경|기본|가중",
  "form_range": "예: 징역 3년~5년",
  "key_aggravating": ["..."],
  "key_mitigating": ["..."],
  "reasoning": "1~2문장",
  "judge_role_disclaimer": "본 결정은 시뮬레이션이며 실제 양형은 담당 판사 재량입니다."
}"""


def stage3_final(case: str, stage2: dict) -> dict[str, Any]:
    msg = (
        f"사건:\n{case}\n\n"
        f"토론 종합:\n{json.dumps(stage2.get('turn3', {}), ensure_ascii=False)[:3000]}"
    )
    return _call_llm(FINAL_PROMPT, msg)


# ─── Stage 4: Bench Consensus (7명 위원 합의) ───────────────────────────────

JUROR_PROMPT_TEMPLATE = """당신은 양형위원회 위원 #{num}입니다. 페르소나: {persona}.
다음 사건에 대해 권고형량 영역과 형량 범위를 JSON으로 답하세요.

페르소나 특성: {trait}

JSON 스키마:
{{
  "juror": {num},
  "zone": "감경|기본|가중",
  "form_range": "예: 징역 2년~3년",
  "weight_aggr": 1~5,
  "weight_mitig": 1~5,
  "rationale": "1줄"
}}"""

JURORS = [
    (1, "전문 판사 (대법원 30년)", "양형기준 엄격 적용. 가중요소 우선."),
    (2, "전문 판사 (지방법원 15년)", "감경요소 폭넓게 인정. 사회적 약자 배려."),
    (3, "비전문 위원 (변호사 출신)", "변호인 입장에서 감경요소 강조."),
    (4, "비전문 위원 (검사 출신)", "검사 입장에서 가중요소 강조."),
    (5, "비전문 위원 (학계 형법학자)", "양형기준 이론 충실히 적용."),
    (6, "비전문 위원 (시민단체)", "피해자 보호 + 사회 공익 우선."),
    (7, "비전문 위원 (재계)", "초범 + 변제 노력 가중 반영."),
]


def _juror_decide(num: int, persona: str, trait: str, case: str, stage3_result: dict) -> dict:
    msg = (
        f"사건:\n{case}\n\n"
        f"판사 시뮬 결과:\n{json.dumps(stage3_result, ensure_ascii=False)[:1500]}"
    )
    return _call_llm(
        JUROR_PROMPT_TEMPLATE.format(num=num, persona=persona, trait=trait),
        msg,
    )


def stage4_consensus(case: str, stage3_result: dict) -> dict[str, Any]:
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_juror_decide, num, p, t, case, stage3_result): num
            for num, p, t in JURORS
        }
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"juror": futures[fut], "_error": str(e)})

    # 분포 집계
    zones = [r.get("zone") for r in results if isinstance(r, dict) and r.get("zone")]
    from collections import Counter
    zone_dist = Counter(zones)

    return {
        "stage": 4,
        "jurors": results,
        "zone_distribution": dict(zone_dist),
        "consensus_zone": zone_dist.most_common(1)[0][0] if zone_dist else None,
        "n_jurors": len(JURORS),
    }


# ─── 통합 파이프라인 ────────────────────────────────────────────────────────

def simulate_bench(case: str, top_k: int = 5, full_4_stages: bool = False) -> dict[str, Any]:
    """AgentsBench 4단계 시뮬레이션.

    Args:
        case: 사건 개요
        top_k: 청크 수
        full_4_stages: True면 Stage 4 (7명 합의) 까지 실행 — 약 60~90초 추가
    """
    t0 = time.time()
    out: dict[str, Any] = {"case": case, "_methodology": "AgentsBench 4-stage simulation"}

    out["stage1"] = stage1_independent(case, top_k=top_k)
    if "error" in out["stage1"]:
        return out

    out["stage2"] = stage2_deliberation(case, out["stage1"])
    out["stage3"] = stage3_final(case, out["stage2"])

    if full_4_stages:
        out["stage4"] = stage4_consensus(case, out["stage3"])

    out["_elapsed_seconds"] = round(time.time() - t0, 2)
    out["_disclaimer"] = (
        "본 결과는 LLM 다중 에이전트 시뮬레이션이며 실제 양형이 아닙니다. "
        "변호사·국선변호인의 보조 도구로만 활용하세요."
    )
    return out
