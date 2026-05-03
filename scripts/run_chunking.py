"""양형기준 PDF → 청크 (파일 출력 전용)."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "scripts" / "run_chunking_result.txt"

class _D:
    @staticmethod
    def load_dotenv(*a, **k): pass
sys.modules['dotenv'] = _D  # type: ignore

import os
os.environ.setdefault("INDEX_DIR", str(ROOT / "data"))
os.environ.setdefault("SENTENCING_PDF_PATH", str(ROOT / "data" / "sentencing_guideline_2025.pdf"))

lines: list[str] = []
def w(s=""):
    lines.append(str(s))

w("=" * 60)
w("PDF CHUNKING")
w("=" * 60)
w(f"PDF:  {os.environ['SENTENCING_PDF_PATH']}")
w(f"OUT:  {os.environ['INDEX_DIR']}/sentencing_chunks.json")

# 합성 청크 백업 (실 PDF 청킹 실패 시 폴백 가능)
import shutil
synthetic_path = Path(os.environ['INDEX_DIR']) / "sentencing_chunks_synthetic.json"
real_path = Path(os.environ['INDEX_DIR']) / "sentencing_chunks.json"
if real_path.exists() and not synthetic_path.exists():
    shutil.copy(real_path, synthetic_path)
    w(f"  ⚙ 합성 청크 백업: {synthetic_path.name}")

try:
    from core.chunker import build_chunks
    n = build_chunks(Path(os.environ["SENTENCING_PDF_PATH"]), real_path)
    w(f"\n✅ 청킹 완료: {n}개 청크")
except Exception as e:
    import traceback
    w(f"\n❌ 청킹 실패:")
    w(traceback.format_exc())
    LOG.write_text("\n".join(lines), encoding="utf-8")
    raise

# 청크 통계
import json
chunks = json.loads(real_path.read_text(encoding="utf-8"))
w(f"\n📊 청크 통계:")
w(f"  전체 청크 수: {len(chunks)}")
w(f"  최대 페이지: {max(c['page'] for c in chunks)}")
w(f"  최소 페이지: {min(c['page'] for c in chunks)}")
w(f"  평균 텍스트 길이: {sum(len(c['text']) for c in chunks) // len(chunks)}자")

from collections import Counter
cat_counter = Counter(c["crime_category"] for c in chunks)
sec_counter = Counter(c["section"] for c in chunks)
w(f"\n  죄종 Top 10:")
for cat, n in cat_counter.most_common(10):
    w(f"    {cat:20s} : {n}")
w(f"\n  섹션 분포:")
for sec, n in sec_counter.most_common():
    w(f"    {sec:15s} : {n}")

# 샘플 청크
w(f"\n📄 첫 청크 샘플:")
w(f"  chunk_id: {chunks[0]['chunk_id']}")
w(f"  page: {chunks[0]['page']}, category: {chunks[0]['crime_category']}, section: {chunks[0]['section']}")
w(f"  text[:300]: {chunks[0]['text'][:300]}")

LOG.write_text("\n".join(lines), encoding="utf-8")
print("OK")
