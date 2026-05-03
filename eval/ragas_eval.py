"""양형기준 검색 평가 — 죄종 메타 기반 (v0.2).

평가 방식:
  검색 결과 상위 K개 청크의 crime_category 중 expected_categories와 1개 이상 일치 → hit
  (단순 키워드 우연 일치가 아닌 의미 매칭 평가)

사용:
  python eval/ragas_eval.py
  python eval/ragas_eval.py --top-k 10 --persona judge
  python eval/ragas_eval.py --mode lexical    # 폴백 모드 비교
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env 로드 (벡터 모드 필요 시)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    import os
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from core.retriever import SentencingRetriever


# 죄종 별칭 매핑 — chunker 화이트리스트 기반 (양형기준 PDF 표지)
CATEGORY_ALIASES: dict[str, set[str]] = {
    "성범죄": {"성범죄", "성폭력", "디지털 성범죄", "디지털성범죄", "성매매"},
    "성폭력": {"성범죄", "성폭력", "디지털 성범죄", "디지털성범죄"},
    "사기": {"사기", "특정경제범죄가중처벌"},
    "교통": {"교통", "도로교통법위반"},
    "폭력": {"폭력", "협박", "공갈"},
    "협박": {"폭력", "협박", "공갈"},
    "강도": {"강도", "주거침입"},
    "주거침입": {"주거침입", "강도", "절도"},
    "근로기준법위반": {"근로기준법위반", "조세"},
}


def _expected_match(expected_cat: str, actual_cat: str) -> bool:
    """기대 죄종이 실제 매칭과 일치하거나 별칭 그룹에 포함되면 hit."""
    if expected_cat == actual_cat:
        return True
    aliases = CATEGORY_ALIASES.get(expected_cat, {expected_cat})
    return actual_cat in aliases


def evaluate(persona: str, top_k: int, questions_path: Path) -> dict:
    """죄종 메타 매칭 기반 평가 (별칭 그룹 허용)."""
    questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"]
    retriever = SentencingRetriever()
    _ = retriever.retrieve("점검", persona="judge", top_k=1)

    hits = 0
    rr_sum = 0.0
    per_question: list[dict] = []

    for q in questions:
        results = retriever.retrieve(q["query"], persona=persona, top_k=top_k)  # type: ignore[arg-type]
        expected_list = q["expected_categories"]

        rank = None
        matched_cats = []
        for i, r in enumerate(results, start=1):
            actual = r["crime_category"]
            if any(_expected_match(e, actual) for e in expected_list):
                if rank is None:
                    rank = i
                matched_cats.append(actual)

        hit = 1 if rank else 0
        rr = (1.0 / rank) if rank else 0.0
        hits += hit
        rr_sum += rr

        per_question.append({
            "id": q["id"],
            "query_excerpt": q["query"][:60],
            "expected_categories": expected_list,
            "first_hit_rank": rank,
            "matched_categories_in_top_k": list(set(matched_cats)),
            "top_k_categories": [r["crime_category"] for r in results],
        })

    n = len(questions)
    return {
        "version": "v0.2 (서술형 사건 → 죄종 메타 매칭)",
        "mode": getattr(retriever, "_mode", "?"),
        "persona": persona,
        "top_k": top_k,
        "n_questions": n,
        f"hit_at_{top_k}": round(hits / n, 3) if n else 0,
        "mrr": round(rr_sum / n, 3) if n else 0,
        "per_question": per_question,
    }


def main():
    parser = argparse.ArgumentParser(description="양형기준 검색 평가 (v0.2 서술형)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--persona", default="judge", choices=["prosecutor", "defender", "judge"])
    parser.add_argument("--out", default="eval/results/last_run.json")
    args = parser.parse_args()

    qpath = Path(__file__).parent / "eval_questions.json"
    if not qpath.exists():
        print(f"⚠ 질문 파일 미존재: {qpath}")
        return 1

    print(f"⚙ 평가: persona={args.persona}, top_k={args.top_k}")
    result = evaluate(args.persona, args.top_k, qpath)

    print(f"\n📊 결과 (v0.2 서술형 사건 평가)")
    print(f"   mode:     {result['mode']}")
    print(f"   질문 수:  {result['n_questions']}")
    print(f"   Hit@{args.top_k}:    {result[f'hit_at_{args.top_k}']:.3f}")
    print(f"   MRR:      {result['mrr']:.3f}")

    # 미스한 질문 표시
    misses = [q for q in result["per_question"] if q["first_hit_rank"] is None]
    if misses:
        print(f"\n   ❌ Miss ({len(misses)}건):")
        for m in misses[:5]:
            print(f"      • {m['id']}: {m['query_excerpt']}")
            print(f"        기대 {m['expected_categories']} / top-k {m['top_k_categories']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 상세: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
