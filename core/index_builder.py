"""
양형기준 청크 → FAISS 벡터 인덱스 빌더

지원 임베딩:
- OpenAI text-embedding-3-large (3072차원)
- BGE-M3 (sentence-transformers, 1024차원, 한국어 강함)
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None


def _embed_openai(texts: list[str], model: str) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI()
    # 배치 100개씩
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        resp = client.embeddings.create(model=model, input=batch)
        embeddings.extend([d.embedding for d in resp.data])
    return np.array(embeddings, dtype=np.float32)


def _embed_bge(texts: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-m3")
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=True).astype(np.float32)


def build_index(chunks_path: Path, index_dir: Path) -> dict[str, Any]:
    if faiss is None:
        raise ImportError("faiss-cpu 미설치. pip install faiss-cpu")

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    texts = [c["text"] for c in chunks]

    provider = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
    if provider == "openai":
        model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        print(f"⚙ OpenAI 임베딩 ({model}) — {len(texts)}개")
        vecs = _embed_openai(texts, model)
    elif provider in ("bge-m3", "bge"):
        print(f"⚙ BGE-M3 임베딩 — {len(texts)}개")
        vecs = _embed_bge(texts)
    else:
        raise ValueError(f"지원하지 않는 EMBEDDING_PROVIDER: {provider}")

    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)  # 코사인 유사도 (벡터는 정규화됨)
    # OpenAI 임베딩은 자동 정규화가 안 되므로 수동 정규화
    if provider == "openai":
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs = vecs / np.clip(norms, 1e-9, None)
    index.add(vecs)

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "faiss_index.bin"))
    np.save(index_dir / "embeddings.npy", vecs)

    meta = {
        "chunks_file": str(chunks_path.name),
        "embedding_provider": provider,
        "dim": int(dim),
        "count": int(len(texts)),
    }
    (index_dir / "index_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    index_dir = Path(os.getenv("INDEX_DIR", "data"))
    chunks_path = index_dir / "sentencing_chunks.json"

    if not chunks_path.exists():
        print(f"⚠ 청크 파일 미존재: {chunks_path}")
        print("   먼저 python core/chunker.py 실행")
        raise SystemExit(1)

    meta = build_index(chunks_path, index_dir)
    print(f"✅ 인덱스 빌드 완료: {meta}")
