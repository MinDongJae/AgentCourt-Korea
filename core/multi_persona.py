"""
3-페르소나 RAG 코어

검사 · 변호인 · 판사 시점에서 양형기준 + 법제처 판례를 다각도로 검색,
LLM이 각 시점별로 양형 요소 체크리스트를 정리.

핵심 원칙:
- 형량 숫자 예측 X
- 판사 대체 X
- 양형기준 조문 + 판례 매칭 결과 + 체크리스트만 출력
"""
from __future__ import annotations
import json
import os
from typing import Any
from pathlib import Path

from core.retriever import retrieve_sentencing
from core.chunker import CRIME_CATEGORIES
from mcp_law.api_client import LawAPIClient


# LBOX OPEN 데이터셋 (arXiv 2206.05224, 한국 법률 AI 벤치마크) 의 최빈 죄종 +
# 양형기준 PDF 표지 화이트리스트 통합
# 길이 긴 키워드 우선 매칭 (예: "디지털 성범죄" → "성범죄"보다 우선)
LBOX_FREQUENT_CRIMES = [
    "디지털성범죄", "특수폭행", "특수절도", "특수강도", "보이스피싱",
    "강제추행", "준강간", "준강제추행", "성매매알선", "음주운전", "위험운전",
    "교통사고치상", "교통사고치사", "음주측정거부", "도주치사", "도주치상",
    "특정범죄가중처벌", "특정경제범죄가중처벌", "조세범처벌법위반",
    "정보통신망법위반", "도로교통법위반", "근로기준법위반",
    "마약류관리법위반", "성폭력범죄의처벌등에관한특례법위반",
    "강간", "강도", "절도", "사기", "횡령", "배임", "뇌물", "위증", "무고",
    "방화", "살인", "상해", "폭행", "협박", "공갈", "스토킹", "아동학대",
    "주거침입", "재물손괴", "명예훼손", "모욕", "공무집행방해",
]
# 모든 키워드 합산 + 길이 내림차순 정렬 (긴 것부터 매칭)
ALL_CRIME_KEYWORDS = sorted(
    set(CRIME_CATEGORIES + LBOX_FREQUENT_CRIMES),
    key=len,
    reverse=True,
)


def _extract_search_keyword(case_description: str) -> tuple[str, str | None]:
    """사건 개요에서 법제처 검색용 키워드 + 참조법령 추출.

    전략 (3-tier):
    1. 양형기준+LBOX 화이트리스트 매칭 (가장 빠름, 검증된 죄종)
    2. (조건부) LLM 키워드 추출 — 화이트리스트 미매칭 시 OpenAI/Claude 호출
    3. 첫 단어 폴백 (최후)

    Returns:
        (검색어, 참조법령) — 참조법령은 형사면 "형법", 민사면 "민법", 미상이면 None
    """
    # Tier 1: 화이트리스트 매칭
    for kw in ALL_CRIME_KEYWORDS:
        if kw in case_description:
            # 참조법령 자동 매핑
            ref_law = _infer_ref_law(kw)
            return kw, ref_law

    # Tier 2: LLM 폴백 (API 키 있을 때만)
    if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        kw = _llm_extract_keyword(case_description)
        if kw:
            return kw, _infer_ref_law(kw)

    # Tier 3: 첫 단어 폴백
    first = case_description.split()[0] if case_description.strip() else "사건"
    return first, None


def _infer_ref_law(keyword: str) -> str | None:
    """키워드에 따라 참조법령 자동 매핑."""
    # 형사 죄종 (대부분)
    criminal_kws = {
        "사기", "절도", "강도", "강간", "폭행", "상해", "협박", "공갈",
        "살인", "방화", "횡령", "배임", "뇌물", "위증", "무고", "장물",
        "도주", "범인은닉", "공무집행방해", "주거침입", "재물손괴",
        "성범죄", "성폭력", "강제추행", "준강간", "준강제추행", "성매매",
        "마약", "스토킹", "아동학대", "디지털성범죄", "보이스피싱",
        "음주운전", "위험운전", "교통사고", "음주측정거부",
        "특수폭행", "특수절도", "특수강도",
        "명예훼손", "모욕", "위조", "변조",
    }
    for ck in criminal_kws:
        if ck in keyword or keyword in ck:
            return "형법"

    # 특별형법 (참조법령 미지정 — 법제처가 자동 검색)
    if "법위반" in keyword or "처벌" in keyword:
        return None

    return None


def _llm_extract_keyword(case_description: str) -> str | None:
    """LLM에게 사건 핵심 죄종 키워드 1개 추출시키기.

    화이트리스트로 못 잡은 신종 사건 또는 모호 케이스용 폴백.
    """
    prompt = (
        "다음 사건 개요에서 한국 형법·특별법상 죄종 키워드 1개만 추출하세요. "
        "예: '사기', '음주운전', '횡령'. "
        "JSON으로 {\"keyword\": \"...\"}만 반환.\n\n"
        f"사건: {case_description}"
    )
    try:
        if os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",  # 키워드 추출은 mini로 충분 (~$0.0001)
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=50,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            kw = data.get("keyword", "").strip()
            return kw if kw else None
    except Exception:
        return None
    return None


PROSECUTOR_PROMPT = """당신은 형사사건 검사 시점의 양형기준 검색 도우미입니다.
주어진 사건에서 **가중요소**(불리한 양형 요소)에 해당할 수 있는 양형기준 조문을 정리하세요.

⚠ 중요 — 다음을 절대 하지 마세요:
- 형량 숫자 예측 ("징역 X년" 등)
- 유무죄 판단
- 피고에 대한 단정적 평가

다음만 하세요:
- 검색된 양형기준 조문 중 가중요소 후보 나열
- 각 항목이 왜 본 사건의 가중요소가 될 수 있는지 한 줄 근거
- 변호인 측이 반박할 가능성이 있는 부분 메모

출력 형식 (JSON):
{
  "perspective": "prosecutor",
  "aggravating_candidates": [
    {"item": "...", "ground": "...", "rebuttable": "..."}
  ],
  "checklist": ["...", "..."]
}
"""

DEFENDER_PROMPT = """당신은 형사사건 변호인 시점의 양형기준 검색 도우미입니다.
주어진 사건에서 **감경요소**(유리한 양형 요소)에 해당할 수 있는 양형기준 조문을 정리하세요.

⚠ 중요 — 다음을 절대 하지 마세요:
- 형량 숫자 예측
- 유무죄 판단

다음만 하세요:
- 검색된 양형기준 조문 중 감경요소 후보 나열
- 각 항목 입증을 위해 변호인이 추가로 확보해야 할 자료 메모
- 검사가 가중으로 주장할 수 있어 사전 대비가 필요한 항목

출력 형식 (JSON):
{
  "perspective": "defender",
  "mitigating_candidates": [
    {"item": "...", "evidence_to_collect": "...", "counter_risk": "..."}
  ],
  "checklist": ["...", "..."]
}
"""

JUDGE_PROMPT = """당신은 양형기준 종합 정리 도우미입니다.
검사·변호인 시점 정리 결과와 검색된 양형기준 조문을 바탕으로,
변호사가 사건 준비 시 **놓치지 말아야 할 양형 요소 체크리스트**를 정리하세요.

⚠ 중요 — 다음을 절대 하지 마세요:
- 형량 숫자 추천 ("적정 형량은 X년")
- 판결 자동화

다음만 하세요:
- 검사·변호인 양측 시점 통합 체크리스트
- 양형기준의 권고형량 범위 조문 인용 (조문 그대로, 해석 X)
- 추가로 확인해야 할 유사 판례 검색 키워드 제안

출력 형식 (JSON):
{
  "perspective": "judge",
  "unified_checklist": ["...", "..."],
  "recommended_range_text": "[조문 그대로 인용]",
  "precedent_search_queries": ["...", "..."]
}
"""


def _heuristic_summary(persona: str, chunks: list[dict[str, Any]], case: str) -> dict[str, Any]:
    """LLM 키 없을 때 규칙 기반 요약 — 검색된 청크의 메타에서 직접 체크리스트 추출.

    이 모드는 LLM 추론을 안 하지만, retriever 결과만으로도 변호사가 즉시 사용 가능한
    "관련 양형기준 페이지 목록"을 제공한다.
    """
    by_section: dict[str, list[dict[str, Any]]] = {}
    for c in chunks:
        by_section.setdefault(c["section"], []).append(c)

    items = []
    for sec, lst in by_section.items():
        for c in lst[:3]:
            items.append({
                "page": c["page"],
                "section": sec,
                "category": c["crime_category"],
                "snippet": c["text"][:150].replace("\n", " "),
            })

    label = {"prosecutor": "검사 시점 — 가중요소 후보",
             "defender": "변호인 시점 — 감경요소 후보",
             "judge": "판사 시점 — 종합 양형기준"}.get(persona, persona)

    return {
        "perspective": persona,
        "_mode": "heuristic_no_llm",
        "label": label,
        "matched_pages": sorted({c["page"] for c in chunks}),
        "items": items,
        "checklist": [
            f"본 사건과 관련된 양형기준 {len(chunks)}개 청크가 매칭됨 (페이지: {', '.join(str(p) for p in sorted({c['page'] for c in chunks}))})",
            f"{persona} 시점에서 우선 검토할 섹션: {', '.join(by_section.keys())}",
            "각 페이지의 가중·감경 요소를 변호사가 직접 검토 후 사건 적용 여부 판단",
        ],
        "_note": "LLM API 키 (ANTHROPIC_API_KEY/OPENAI_API_KEY) 미설정 — 규칙 기반 요약 모드. 키 설정 시 자동으로 LLM 분석 활성화.",
    }


def _call_gemini(system_prompt: str, user_msg: str, model: str = "gemini-2.5-flash") -> dict[str, Any]:
    """Gemini API 호출 — Anthropic 크레딧 부족 / OpenAI 비용 절감용 폴백.

    Pricing 비교 (Claude Opus 대비 4~5배 저렴):
    - gemini-2.5-flash: $0.30/1M input, $2.50/1M output ⭐ 본 도구 기본값
    - gemini-2.5-pro: $1.25/1M input, $5/1M output (단 thinking model이라 max_tokens 부족 시 빈 응답)
    """
    import httpx
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"_error": "GEMINI_API_KEY not set"}
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_msg}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,  # thinking 토큰 + 응답 토큰 모두 수용
            "temperature": 0.3,
        },
    }
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json=body, timeout=60,
        )
        if r.status_code != 200:
            return {"_error": f"Gemini API: {r.text[:300]}"}
        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {"_error": f"Gemini empty candidates: {json.dumps(data)[:200]}"}
        cand = candidates[0]
        # 응답 텍스트 추출 — finishReason이 MAX_TOKENS이거나 STOP이어야 정상
        finish = cand.get("finishReason", "?")
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            return {"_error": f"Gemini empty text (finishReason={finish}, usage={data.get('usageMetadata', {})})"}
        result = _parse_json_response(text)
        if not isinstance(result, dict):
            result = {"_text": text}
        result["_model_used"] = f"gemini/{model}"
        result["_finish_reason"] = finish
        return result
    except Exception as e:
        return {"_error": f"Gemini API: {e}"}


def _call_llm(system_prompt: str, user_msg: str) -> dict[str, Any]:
    """LLM 호출 — Anthropic → Gemini → OpenAI 단계별 폴백.

    우선순위 (2026-05-03 KST 기준):
    1. Anthropic Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 — 한국어 법조 최고
    2. Gemini 2.5 Pro — Anthropic 크레딧 부족 시. 비용 4~5배 저렴 + 2M context
    3. OpenAI GPT-4o — 최종 폴백

    JSON 응답 파싱 실패 시 raw 텍스트 반환.
    """
    anthropic_err = None
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic
            client = Anthropic()
            # 모델 단계별 시도 — credit/tier 문제 시 다음 모델로 폴백
            tried_models: list[tuple[str, str]] = []
            # 속도 우선 — Haiku 4.5가 충분 (페르소나별 양형요소 정리)
            for model_id in ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]:
                try:
                    resp = client.messages.create(
                        model=model_id,
                        max_tokens=1024,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_msg}],
                    )
                    text = resp.content[0].text
                    result = _parse_json_response(text)
                    result["_model_used"] = model_id
                    if tried_models:
                        result["_anthropic_fallback_chain"] = tried_models
                    return result
                except Exception as inner_e:
                    tried_models.append((model_id, str(inner_e)[:120]))
                    continue
            anthropic_err = f"All Anthropic models failed: {tried_models}"
        except Exception as e:
            anthropic_err = str(e)

    # Gemini 폴백 — Anthropic 실패 시 (한국어 우수 + 비용 1/4~1/5)
    if anthropic_err and os.getenv("GEMINI_API_KEY"):
        result = _call_gemini(system_prompt, user_msg)
        if "_error" not in result:
            result["_anthropic_fallback"] = f"Anthropic 실패 → Gemini 사용: {anthropic_err[:150]}"
            return result

    # OpenAI 최종 폴백 (Anthropic + Gemini 모두 실패 시)

    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
            )
            result = _parse_json_response(resp.choices[0].message.content or "")
            if anthropic_err:
                result["_anthropic_fallback"] = f"Anthropic 실패 → OpenAI 사용: {anthropic_err[:100]}"
            return result
        except Exception as e:
            return {"_error": f"OpenAI API: {e}", "_anthropic_err": anthropic_err}

    return {"_error": "ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요", "_anthropic_err": anthropic_err}


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except Exception:
        return {"_raw": text, "_parse_failed": True}


def _format_chunks_for_llm(chunks: list[dict[str, Any]]) -> str:
    lines = []
    for c in chunks:
        lines.append(
            f"[조문 {c['chunk_id']} · 페이지 {c['page']} · {c['crime_category']} · {c['section']}]\n{c['text']}"
        )
    return "\n\n".join(lines)


def _sort_precedents_lower_inst_first(items: list) -> list:
    """판례 리스트를 1심·2심 → 3심 순으로 재정렬.

    사건번호 패턴:
      - 1심: 고합·고단·고정·고약 → priority 0
      - 2심: 노 → priority 1
      - 3심: 도 → priority 2
    """
    def prio(it):
        if not isinstance(it, dict):
            return 9
        case_no = it.get("사건번호", "") or ""
        court = it.get("법원명", "") or ""
        if any(x in case_no for x in ["고단", "고합", "고정", "고약"]) or "지방법원" in court:
            return 0
        if "노" in case_no or "고등법원" in court:
            return 1
        if "대법원" in court or (case_no and case_no[-1] in "도"):
            return 2
        return 3
    return sorted(items, key=prio)


def analyze_case(case_description: str, top_k: int = 5, prefer_lower_inst: bool = True) -> dict[str, Any]:
    """단일 사건 → 3-페르소나 통합 분석.

    Args:
        case_description: 사건 개요 (사용자 입력)
        top_k: 페르소나당 검색 청크 수
        prefer_lower_inst: True면 법제처 판례를 1·2심 우선 정렬 (양형 결정 사례에 가까움)

    Returns:
        {prosecutor, defender, judge, precedents, _meta} 통합 결과
    """
    pros_chunks = retrieve_sentencing(case_description, persona="prosecutor", top_k=top_k)
    def_chunks = retrieve_sentencing(case_description, persona="defender", top_k=top_k)
    judge_chunks = retrieve_sentencing(case_description, persona="judge", top_k=top_k)

    # 인덱스 미빌드 시
    if "error" in pros_chunks:
        return {"error": pros_chunks["error"]}

    has_llm = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if has_llm:
        pros_msg = (
            f"사건 개요:\n{case_description}\n\n"
            f"검색된 양형기준 (가중요소 후보):\n{_format_chunks_for_llm(pros_chunks['results'])}"
        )
        def_msg = (
            f"사건 개요:\n{case_description}\n\n"
            f"검색된 양형기준 (감경요소 후보):\n{_format_chunks_for_llm(def_chunks['results'])}"
        )
        # pros + def 병렬 호출 (judge는 그 둘이 끝난 후 종합)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_pros = ex.submit(_call_llm, PROSECUTOR_PROMPT, pros_msg)
            f_def = ex.submit(_call_llm, DEFENDER_PROMPT, def_msg)
            pros_result = f_pros.result()
            def_result = f_def.result()

        judge_msg = (
            f"사건 개요:\n{case_description}\n\n"
            f"검사 시점 정리:\n{json.dumps(pros_result, ensure_ascii=False, indent=2)}\n\n"
            f"변호인 시점 정리:\n{json.dumps(def_result, ensure_ascii=False, indent=2)}\n\n"
            f"양형기준 종합 검색:\n{_format_chunks_for_llm(judge_chunks['results'])}"
        )
        judge_result = _call_llm(JUDGE_PROMPT, judge_msg)
    else:
        pros_result = _heuristic_summary("prosecutor", pros_chunks["results"], case_description)
        def_result = _heuristic_summary("defender", def_chunks["results"], case_description)
        judge_result = _heuristic_summary("judge", judge_chunks["results"], case_description)

    # 법제처 판례 검색 — 키워드 추출 전략 (검증된 출처 기반)
    #
    # 출처 1: 양형기준 PDF 표지 화이트리스트 (chunker.CRIME_CATEGORIES, 60+개)
    # 출처 2: LBOX OPEN 한국 법률 AI 벤치마크 (arXiv 2206.05224) — 100개 최빈 죄종
    # 검증: 법제처 OPEN API 공식 가이드 — query 부분일치, search=2(본문검색),
    #       display 최대 100. 참조법령 JO 필터는 특별형법(도로교통법·성폭력처벌특례법
    #       ·폭처법 등) 매칭 시 0건이 되므로 사용하지 않음.
    law_client = LawAPIClient()
    search_query, _ref_law_hint = _extract_search_keyword(case_description)

    # search=2 본문검색 (판례명+본문 모두), display 10
    # 참조법령 필터는 의도적으로 미적용 (특별형법 케이스 누락 방지)
    precedents = law_client.search_precedent(
        search_query,
        display=10,
        search=2,
    )
    if isinstance(precedents, dict):
        precedents["_search_query_used"] = search_query
        precedents["_ref_law_hint"] = _ref_law_hint
        # 1·2심 우선 정렬 (양형 결정 사례에 더 가까운 하급심 우선 노출)
        if prefer_lower_inst:
            ps = precedents.get("PrecSearch") or precedents
            if isinstance(ps, dict):
                items = ps.get("prec")
                if isinstance(items, list):
                    ps["prec"] = _sort_precedents_lower_inst_first(items)
                    precedents["_sort_strategy"] = "lower_inst_first"

    return {
        "case": case_description,
        "prosecutor": pros_result,
        "defender": def_result,
        "judge": judge_result,
        "precedents": precedents,
        "raw_chunks": {
            "prosecutor": pros_chunks["results"],
            "defender": def_chunks["results"],
            "judge": judge_chunks["results"],
        },
        "_disclaimer": (
            "본 결과는 변호사·국선변호인의 양형기준 검색 보조용입니다. "
            "형량 예측·판결 추천이 아니며, 최종 양형 판단은 판사의 권한입니다."
        ),
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    case = "사기죄 피해액 5천만원 초범 변제 합의 안 됨"
    result = analyze_case(case, top_k=5)
    print(json.dumps(result, ensure_ascii=False, indent=2))
