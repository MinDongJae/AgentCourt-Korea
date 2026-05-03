"""
CLI 데모 — 사건 개요 입력 → 3-페르소나 양형기준 매칭 결과 출력

사용:
  python scripts/demo.py "사기 5천만원 초범 변제 합의 안 됨"
  python scripts/demo.py --case sample_cases/case_001_사기_5천만원.json
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

# 프로젝트 루트
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.multi_persona import analyze_case


def _color(text: str, code: int) -> str:
    return f"\033[{code}m{text}\033[0m"


def _h1(text: str) -> str:
    return _color(f"\n━━ {text} ━━", 96)


def _h2(text: str) -> str:
    return _color(text, 93)


def _print_persona(label: str, result: dict, color_code: int):
    print(_color(f"\n┌─ {label} 시점 ─────────────────────", color_code))
    if "_error" in result:
        print(f"│ ⚠ {result['_error']}")
        return
    if "_parse_failed" in result:
        print(f"│ (JSON 파싱 실패 — raw)\n│ {result.get('_raw', '')[:500]}")
        return
    print(f"│ {json.dumps(result, ensure_ascii=False, indent=2)[:1500]}")
    print(_color("└" + "─" * 40, color_code))


def _print_chunks(label: str, chunks: list[dict]):
    print(_color(f"\n  📑 {label} 매칭 양형기준 조문 ({len(chunks)}개):", 90))
    for c in chunks:
        score = c.get("score", 0)
        snip = c["text"][:140].replace("\n", " ")
        print(f"   • [p.{c['page']} · {c['crime_category']} · {c['section']}] (score={score:.3f})")
        print(f"     {snip}…")


def main():
    parser = argparse.ArgumentParser(description="양형기준 검색 어시스턴트 CLI 데모")
    parser.add_argument("query", nargs="*", help="사건 개요")
    parser.add_argument("--case", help="JSON 사건 파일 경로")
    parser.add_argument("--top-k", type=int, default=5, help="페르소나당 검색 청크 수")
    parser.add_argument("--json", action="store_true", help="JSON 원본 출력")
    args = parser.parse_args()

    if args.case:
        case_data = json.loads(Path(args.case).read_text(encoding="utf-8"))
        case_text = case_data.get("description") or case_data.get("case", "")
    elif args.query:
        case_text = " ".join(args.query)
    else:
        parser.print_help()
        return 1

    print(_h1("양형기준 검색 어시스턴트"))
    print(f"  사건: {_color(case_text, 97)}")
    print(f"  ⚖ 본 도구는 형량을 예측하지 않으며, 변호사 보조용입니다.")

    result = analyze_case(case_text, top_k=args.top_k)

    if "error" in result:
        print(f"\n❌ 오류: {result['error']}")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(_h2("\n■ 1단계 — 페르소나별 양형기준 청크 검색"))
    _print_chunks("검사 시점 (가중요소)", result["raw_chunks"]["prosecutor"])
    _print_chunks("변호인 시점 (감경요소)", result["raw_chunks"]["defender"])
    _print_chunks("판사 시점 (종합)", result["raw_chunks"]["judge"])

    print(_h2("\n■ 2단계 — LLM 페르소나 정리"))
    _print_persona("검사", result["prosecutor"], 91)
    _print_persona("변호인", result["defender"], 92)
    _print_persona("판사 (종합)", result["judge"], 96)

    print(_h2("\n■ 3단계 — 법제처 판례 매칭"))
    pres = result.get("precedents", {})
    if pres.get("_mock"):
        print(f"  ℹ 법제처 API mock 모드 (LAW_API_KEY 미설정)")
    print(f"  결과: {len(pres.get('results', []))}건")

    print(_color("\n" + result["_disclaimer"], 90))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
