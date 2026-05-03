"""환경 의존성 없이 retriever + 평가 동작 검증.

결과는 stdout + scripts/smoke_test_result.txt 양쪽에 기록.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

LOG_PATH = Path(__file__).parent / "smoke_test_result.txt"
_log_lines: list[str] = []

def out(msg: str = ""):
    out(msg)
    _log_lines.append(msg)

# dotenv shim
class _D:
    @staticmethod
    def load_dotenv(*a, **k): pass
sys.modules['dotenv'] = _D  # type: ignore

from core.retriever import SentencingRetriever

out("=" * 60)
out("smoke test — retriever (lexical fallback)")
out("=" * 60)

r = SentencingRetriever()
queries = [
    ("사기 5천만원 초범 변제 합의 안됨", "judge"),
    ("음주운전 0.18% 사고 없음 재범", "prosecutor"),
    ("성폭력 합의", "defender"),
    ("보이스피싱 인출책", "prosecutor"),
    ("마약 투약 단순 소지 초범", "defender"),
    ("스토킹 지속적 협박", "judge"),
]

for q, persona in queries:
    res = r.retrieve(q, persona=persona, top_k=3)
    out(f"\n[{persona:11s}] {q}")
    out(f"  mode={r._mode}, 결과 {len(res)}건:")
    for c in res:
        snippet = c["text"][:70].replace("\n", " ")
        out(f"   • [{c['section']:8s}|{c['crime_category']:6s}] score={c['score']:.2f}")
        out(f"     {snippet}...")

out("\n" + "=" * 60)
out("✅ smoke test 통과")

LOG_PATH.write_text("\n".join(_log_lines), encoding="utf-8")
print(f"\n💾 로그 저장: {LOG_PATH}")
