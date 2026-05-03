"""
양형기준 검색기 — 페르소나별 가중·감경 요소 필터링

페르소나:
- prosecutor: 가중요소 위주 (section in {"가중요소"})
- defender: 감경요소 위주 (section in {"감경요소"})
- judge: 종합 (모든 섹션)

본 모듈은 형량을 예측하지 않습니다. 양형기준 조문을 검색해서 반환합니다.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Literal
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None


PersonaT = Literal["prosecutor", "defender", "judge"]

PERSONA_FILTER: dict[str, set[str]] = {
    "prosecutor": {"가중요소", "권고형량"},
    "defender": {"감경요소", "권고형량"},
    "judge": {"가중요소", "감경요소", "권고형량", "일반양형요소", "본문"},
}
# 페르소나 필터로 매칭이 부족할 경우 폴백 — 본문 청크에도 도메인 키워드(가중/감경)가
# 포함된 경우가 많기 때문에 retrieve 단계에서 본문 청크를 secondary로 포함.
PERSONA_FALLBACK: dict[str, set[str]] = {
    "prosecutor": {"본문", "일반양형요소"},
    "defender": {"본문", "일반양형요소"},
    "judge": set(),  # judge는 이미 본문 포함
}


class SentencingRetriever:
    """싱글톤 — 인덱스 1회 로드 후 재사용."""
    _instance: "SentencingRetriever | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def _ensure_loaded(self):
        if self._loaded:
            return
        index_dir = Path(os.getenv("INDEX_DIR", "data"))
        chunks_path = index_dir / "sentencing_chunks.json"
        if not chunks_path.exists():
            raise FileNotFoundError(
                f"청크 파일 미존재: {chunks_path}. scripts/build_index.py 또는 scripts/seed_demo_data.py 실행."
            )
        self.chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

        # FAISS 인덱스가 있으면 벡터 검색, 없으면 lexical fallback
        index_path = index_dir / "faiss_index.bin"
        meta_path = index_dir / "index_meta.json"
        if faiss is not None and index_path.exists():
            self.index = faiss.read_index(str(index_path))
            self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            self._mode = "vector"
        else:
            self.index = None
            self.meta = {"_fallback": "lexical"}
            self._mode = "lexical"

        self._loaded = True

    def _embed_query(self, query: str) -> np.ndarray:
        provider = self.meta.get("embedding_provider", "openai")
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI()
            model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
            resp = client.embeddings.create(model=model, input=[query])
            v = np.array(resp.data[0].embedding, dtype=np.float32)
            v = v / max(np.linalg.norm(v), 1e-9)
            return v.reshape(1, -1)
        elif provider in ("bge-m3", "bge"):
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-m3")
            return model.encode([query], normalize_embeddings=True).astype(np.float32)
        raise ValueError(f"unknown provider: {provider}")

    def _lexical_score(self, query: str, text: str) -> float:
        """간단 키워드 빈도 점수 (벡터 인덱스 없을 때 폴백)."""
        # 한국어 토큰화 — 2자 이상 한글·영문·숫자 시퀀스
        import re
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", query)
        if not tokens:
            return 0.0
        score = 0.0
        for t in tokens:
            score += text.count(t)
        return score / len(tokens)

    def retrieve(self, query: str, persona: PersonaT = "judge", top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_loaded()
        allowed_sections = PERSONA_FILTER[persona]

        if self._mode == "vector":
            qvec = self._embed_query(query)
            D, I = self.index.search(qvec, top_k * 4)
            scored: list[tuple[float, int]] = [(float(s), int(i)) for s, i in zip(D[0], I[0]) if i >= 0]
        else:
            # Lexical fallback
            scored = [(self._lexical_score(query, ch["text"]), i) for i, ch in enumerate(self.chunks)]
            scored.sort(key=lambda x: x[0], reverse=True)
            scored = scored[:top_k * 4]

        fallback_sections = PERSONA_FALLBACK.get(persona, set())
        primary: list[dict[str, Any]] = []
        secondary: list[dict[str, Any]] = []
        for score, idx in scored:
            if score <= 0 and self._mode == "lexical":
                continue
            ch = self.chunks[idx]
            row = {
                "chunk_id": ch["chunk_id"],
                "page": ch["page"],
                "crime_category": ch["crime_category"],
                "section": ch["section"],
                "tags": ch.get("tags", []),
                "text": ch["text"],
                "score": float(score),
                "_mode": self._mode,
            }
            if ch["section"] in allowed_sections:
                primary.append(row)
            elif ch["section"] in fallback_sections:
                secondary.append(row)

        # 1순위 다음에 폴백 청크로 채움
        results = primary[:top_k]
        if len(results) < top_k:
            need = top_k - len(results)
            results.extend(secondary[:need])
        return results


_retriever: SentencingRetriever | None = None


def retrieve_sentencing(query: str, persona: str = "judge", top_k: int = 5) -> dict[str, Any]:
    """공개 API. MCP 서버에서 호출."""
    global _retriever
    if _retriever is None:
        _retriever = SentencingRetriever()
    if persona not in PERSONA_FILTER:
        return {"error": f"unknown persona: {persona}", "_valid": list(PERSONA_FILTER)}
    results = _retriever.retrieve(query, persona=persona, top_k=top_k)  # type: ignore[arg-type]
    return {
        "query": query,
        "persona": persona,
        "top_k": top_k,
        "results": results,
        "_disclaimer": "본 결과는 양형기준 조문 매칭이며 형량 예측이 아닙니다.",
    }
