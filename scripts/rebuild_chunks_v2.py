"""50개 양형위 PDF + 종합본 → multi-PDF 청크 빌드.

기존 chunker는 단일 PDF만 처리. 본 스크립트는 sentencing_pdfs/ 폴더의 모든 PDF를
순회하면서 파일명 기반 죄종 매핑 + 페이지별 청킹 + 통합 JSON 출력.

파일명 → 한글 죄종 매핑:
  F1.Crimes_of_Homicide → 살인
  F9.Crimes_of_Fraud → 사기
  ...
"""
import sys, os, json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.chunker import detect_section, split_text
from pypdf import PdfReader

PDF_DIR = ROOT / "data" / "sentencing_pdfs"
OUT_PATH = ROOT / "data" / "sentencing_chunks.json"

# PDF 파일명 → 한글 죄종 매핑 (양형위 영문 → 한글)
FILENAME_TO_CRIME = {
    "F1.Crimes_of_Homicide": "살인",
    "F2.Crimes_of_Bribery": "뇌물",
    "F3.Crimes_of_Sexual_Assault": "성범죄",
    "F4.Crimes_of_Robbery": "강도",
    "F5.Crimes_of_Embezzlement_and_Breach_of_Trust": "횡령배임",
    "F6.Crimes_of_Perjury_and_Destroy_of_evidence": "위증증거인멸",
    "F7.Crimes_of_False_Accusation": "무고",
    "F8.Crimes_of_Capture_and_HumanTrafficking": "약취유인인신매매",
    "F9.Crimes_of_Fraud": "사기",
    "F10.Crimes_of_Larceny": "절도",
    "F11.Crimes_of_Official_Documents": "공문서",
    "F12.Crimes_of_Private_Documents": "사문서",
    "F13.Crimes_of_Execution_Disturbance": "공무집행방해",
    "F14.Crimes_of_Food_and_Health": "식품보건",
    "F15.Crimes_of_Narcotics": "마약",
    "F16.Crimes_of_Stock": "증권금융",
    "F17.Crimes_of_Intellectual_Property": "지식재산권",
    "F18.Crimes_of_Violence": "폭력",
    "F19.Crimes_of_Traffic": "교통",
    "F20.Crimes_of_Election": "선거",
    "F21.Crimes_of_Tax": "조세",
    "F22.Crimes_of_Blackmail": "공갈",
    "F23.Crimes_of_Arson": "방화",
    "F24.Crimes_of_Malpractice": "산업안전보건",
    "F25.Crimes_of_Lawyer": "변호사법위반",
    "F26.Crimes_of_Prostitution": "성매매",
    "F27.Crimes_of_Arrest_and_Confinement": "체포감금유기학대",
    "F28.Crimes_of_Stolen_goods": "장물",
    "F29.Crimes_of_Right_and_Interference": "권리행사방해",
    "F30.Crimes_of_Business_Obstruction": "업무방해",
    "F31.Crimes_of_Destruction": "손괴",
    "F32.Crimes_of_Speculative_Game": "사행성게임물",
    "F33.Crimes_of_Labor_Standard": "근로기준법위반",
    "F34.Crimes_of_Petroleum_Business": "석유사업법위반",
    "F35.Crimes_of_Accidental_Homicide": "과실치사상",
    "F36.Crimes_of_Escape_Concealment": "도주범인은닉",
    "F37.Crimes_of_Illegal_Check_Control": "통화유가증권부정수표",
    "F38.Crimes_of_Loan_ClaimCollection": "대부업법채권추심",
    "F39.Crimes_of_Defamation": "명예훼손",
    "F40.Crimes_of_Similar_Reception": "유사수신행위법위반",
    "F41.Crimes_of_Electronic_Finance": "전자금융거래법위반",
    "F42.Crimes_of_Digital__Sexual": "디지털성범죄",
    "F50.Crimes_of_House__Breaking": "주거침입",
    "F51.Crimes_of__Environment": "환경",
    "F52.Crimes_of_Tariff": "관세",
    "F53.Crimes_of_Information_Network": "정보통신망개인정보",
    "F54.Crimes_of_Stalking": "스토킹",
    "F55.Crimes_of_Animal_Protection": "동물보호법위반",
    "sc_explan_doc": "양형기준해설",
    "2025_sentencing_guidelines": "종합양형기준",
}


def build_chunks_for_pdf(pdf_path: Path, crime: str, start_idx: int) -> list[dict]:
    chunks = []
    idx = start_idx
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        print(f"  ❌ PDF 읽기 실패 {pdf_path.name}: {e}")
        return []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        if not text.strip():
            continue
        section, tags = detect_section(text)
        for piece in split_text(text):
            chunks.append({
                "chunk_id": f"ch_{idx:06d}",
                "source_pdf": pdf_path.name,
                "page": page_num,
                "crime_category": crime,
                "section": section,
                "tags": tags,
                "text": piece,
            })
            idx += 1
    return chunks


def main():
    print(f"PDF 디렉토리: {PDF_DIR}")
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"발견된 PDF: {len(pdfs)}개\n")

    all_chunks: list[dict] = []
    idx = 0
    per_pdf_stats = []

    for pdf_path in pdfs:
        stem = pdf_path.stem
        crime = FILENAME_TO_CRIME.get(stem, stem)
        print(f"  처리: {pdf_path.name} → 죄종='{crime}'", end=" ")
        before = len(all_chunks)
        new_chunks = build_chunks_for_pdf(pdf_path, crime, idx)
        all_chunks.extend(new_chunks)
        idx = len(all_chunks)
        n = len(all_chunks) - before
        per_pdf_stats.append((pdf_path.name, crime, n))
        print(f"→ {n}개 청크")

    print(f"\n총 청크 수: {len(all_chunks):,}")

    OUT_PATH.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")

    # 통계
    from collections import Counter
    cat_counter = Counter(c["crime_category"] for c in all_chunks)
    print(f"\n죄종 분포 (top 15):")
    for cat, n in cat_counter.most_common(15):
        print(f"  {cat:<20s}: {n:>5,}")


if __name__ == "__main__":
    main()
