"""
1회 실행 — 양형기준 PDF → 청크 → FAISS 인덱스

전제:
  - data/sentencing_guideline_2025.pdf 배치
  - .env 에 EMBEDDING_PROVIDER, OPENAI_API_KEY 등 설정

실행:
  python scripts/build_index.py
"""
from __future__ import annotations
import sys
from pathlib import Path

# 프로젝트 루트 import 경로
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv

load_dotenv()

from core.chunker import build_chunks
from core.index_builder import build_index


def main():
    index_dir = Path(os.getenv("INDEX_DIR", "data"))
    pdf_path = Path(os.getenv("SENTENCING_PDF_PATH", "data/sentencing_guideline_2025.pdf"))
    chunks_path = index_dir / "sentencing_chunks.json"

    print(f"📂 PDF: {pdf_path}")
    print(f"📂 출력: {index_dir}")

    if not pdf_path.exists():
        print(f"\n⚠ PDF 미존재: {pdf_path}")
        print("   대법원 양형위원회 사이트에서 양형기준 2025판 PDF 다운로드")
        print("   다운로드 URL 안내: https://sc.scourt.go.kr/sc/krsc/criterion/")
        return 1

    print("\n[1/2] 양형기준 PDF 청킹...")
    n_chunks = build_chunks(pdf_path, chunks_path)
    print(f"      → {n_chunks}개 청크 생성")

    print("\n[2/2] FAISS 인덱스 빌드...")
    meta = build_index(chunks_path, index_dir)
    print(f"      → {meta}")

    print("\n✅ 완료. 다음:")
    print("   python scripts/demo.py \"사기 5천만원 초범\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
