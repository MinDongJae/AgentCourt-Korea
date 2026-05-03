"""
대법원 양형기준 PDF 청킹

전략:
- 양형기준 PDF는 「죄종 → 유형 → 권고 형량 범위 → 가중·감경 요소」 계층 구조
- 헤딩 단위로 1차 청킹 (페이지·섹션 메타 보존)
- 가중·감경 요소 블록은 별도 태그 (검사/변호인 페르소나가 직접 활용)

산출물: data/sentencing_chunks.json
스키마:
{
  "chunk_id": "ch_0042",
  "page": 137,
  "crime_category": "사기",      // 죄종
  "type_label": "일반사기",       // 유형
  "section": "권고 형량",         // 권고형량 / 가중요소 / 감경요소 / 일반양형요소
  "tags": ["가중"],
  "text": "..."
}
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # 빌드 시점에 체크

# 양형기준 섹션 마커 패턴 (한국 양형기준 PDF 관행 기반)
# 죄종은 PDF 표지에 명시된 화이트리스트로 한정 (false positive 회피)
CRIME_CATEGORIES = [
    "강도", "공갈", "공무집행방해", "공문서", "과실치사상", "산업안전보건",
    "관세", "교통", "권리행사방해", "근로기준법위반", "뇌물", "대부업법",
    "채권추심법위반", "도주", "범인은닉", "동물보호법위반", "디지털 성범죄",
    "마약", "명예훼손", "무고", "방화", "배임수증재", "변호사법위반",
    "사기", "사문서", "사행성", "게임물", "살인", "석유사업법위반",
    "선거", "성매매", "성범죄", "손괴", "스토킹", "식품", "보건",
    "약취", "유인", "인신매매", "업무방해", "위증", "증거인멸",
    "유사수신행위법위반", "장물", "전자금융거래법위반", "절도",
    "정보통신망", "개인정보", "조세", "주거침입", "증권", "금융",
    "지식재산", "체포", "감금", "추징", "폭력", "협박", "환경",
    "횡령", "배임",
]

HEADING_PATTERNS = {
    "type_label": re.compile(r"제\s*\d+\s*유형\s*[:\-]?\s*(.+)$", re.M),
    "section_recommendation": re.compile(r"권고\s*형량\s*범위", re.M),
    "section_aggravating": re.compile(r"(?:특별\s*)?가중\s*(?:요소|인자)", re.M),
    "section_mitigating": re.compile(r"(?:특별\s*)?감경\s*(?:요소|인자)", re.M),
    "section_general": re.compile(r"일반\s*양형\s*(?:요소|인자)", re.M),
}

CHUNK_TARGET_CHARS = 800  # 청크 목표 길이 (한국어 기준)
CHUNK_OVERLAP = 100


def extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    """PDF에서 페이지별 텍스트 추출."""
    if PdfReader is None:
        raise ImportError("pypdf 미설치. pip install pypdf")
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": i, "text": text})
    return pages


def detect_section(text_window: str) -> tuple[str, list[str]]:
    """텍스트 윈도우에서 섹션 + 태그 감지."""
    if HEADING_PATTERNS["section_aggravating"].search(text_window):
        return "가중요소", ["aggravating"]
    if HEADING_PATTERNS["section_mitigating"].search(text_window):
        return "감경요소", ["mitigating"]
    if HEADING_PATTERNS["section_recommendation"].search(text_window):
        return "권고형량", ["recommendation"]
    if HEADING_PATTERNS["section_general"].search(text_window):
        return "일반양형요소", ["general"]
    return "본문", []


def detect_crime_category(text: str, fallback: str) -> str:
    """죄종 화이트리스트 매칭 (가장 먼저 등장하는 카테고리).

    PDF의 페이지 헤더는 보통 "사기 양형기준" 또는 "교통범죄의 양형기준" 형태.
    화이트리스트 단어가 텍스트 첫 200자 안에 나타나면 그것을 죄종으로.
    """
    head = text[:200]
    # 길이 긴 카테고리 우선 매칭 (디지털 성범죄 → 성범죄로 잘못 매칭 방지)
    for cat in sorted(CRIME_CATEGORIES, key=len, reverse=True):
        if cat in head:
            return cat
    return fallback


def split_text(text: str, target: int = CHUNK_TARGET_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """문단·문장 경계 우선 분할."""
    if len(text) <= target:
        return [text] if text.strip() else []
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 2 > target and buf:
            chunks.append(buf)
            # overlap 처리: 마지막 문장 일부 가져오기
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = tail + "\n\n" + p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf.strip():
        chunks.append(buf)
    return chunks


def build_chunks(pdf_path: Path, output_path: Path) -> int:
    """전체 파이프라인. 반환값은 청크 개수."""
    pages = extract_pages(pdf_path)
    chunks: list[dict[str, Any]] = []

    current_crime = "미분류"
    chunk_idx = 0

    for page_obj in pages:
        page_num = page_obj["page"]
        text = page_obj["text"]
        if not text.strip():
            continue

        current_crime = detect_crime_category(text, current_crime)
        section, tags = detect_section(text)

        for piece in split_text(text):
            chunks.append({
                "chunk_id": f"ch_{chunk_idx:05d}",
                "page": page_num,
                "crime_category": current_crime,
                "section": section,
                "tags": tags,
                "text": piece,
            })
            chunk_idx += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(chunks)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    pdf = Path(os.getenv("SENTENCING_PDF_PATH", "data/sentencing_guideline_2025.pdf"))
    out = Path(os.getenv("INDEX_DIR", "data")) / "sentencing_chunks.json"

    if not pdf.exists():
        print(f"⚠ PDF 미존재: {pdf}")
        print("   대법원 양형위원회 사이트에서 양형기준 2025 PDF 다운로드 후 위 경로에 배치")
        raise SystemExit(1)

    n = build_chunks(pdf, out)
    print(f"✅ 청킹 완료: {n}개 청크 → {out}")
