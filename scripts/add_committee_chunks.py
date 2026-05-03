"""양형위 회의자료 44개 PDF → chunks 추가 (sentencing_chunks_v2.json에 append)."""
import json, re
from pathlib import Path
import fitz  # pymupdf — pypdf의 한글 인코딩 한계 회피

ROOT = Path(__file__).parent.parent
PDF_DIR = ROOT / "data" / "committee_pdfs"
EXISTING = ROOT / "data" / "sentencing_chunks.json"
OUT = ROOT / "data" / "sentencing_chunks_v3.json"

print(f"[1] 기존 chunks 로드")
all_chunks = json.loads(EXISTING.read_text(encoding="utf-8"))
print(f"  기존: {len(all_chunks):,}개")

print(f"\n[2] 회의자료 PDF 처리")
CHUNK_TARGET = 800
CHUNK_OVERLAP = 100

def split_text(text, target=CHUNK_TARGET, overlap=CHUNK_OVERLAP):
    if len(text) <= target:
        return [text] if text.strip() else []
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    buf = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 2 > target and buf:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = tail + "\n\n" + p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf.strip():
        chunks.append(buf)
    return chunks


pdfs = sorted(PDF_DIR.glob("*.pdf"))
print(f"  발견: {len(pdfs)}개 PDF")

idx = len(all_chunks)
new_chunks = []
for pdf_path in pdfs:
    seq_match = re.search(r"seq(\d+)", pdf_path.name)
    seq = seq_match.group(1) if seq_match else "?"
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"  ❌ {pdf_path.name}: {e}")
        continue
    pdf_chunks = 0
    for page_num, page in enumerate(doc, start=1):
        try:
            text = page.get_text() or ""
        except:
            continue
        if not text.strip():
            continue
        for piece in split_text(text):
            new_chunks.append({
                "chunk_id": f"committee_{idx:06d}",
                "source": "양형위_회의자료",
                "source_pdf": pdf_path.name,
                "seq": seq,
                "page": page_num,
                "crime_category": "양형위회의자료",
                "section": "회의자료",
                "tags": ["committee", "deliberation"],
                "text": piece,
            })
            idx += 1
            pdf_chunks += 1
    print(f"  {pdf_path.name}: {pdf_chunks}청크")

print(f"\n신규: {len(new_chunks):,}개")
all_chunks.extend(new_chunks)
print(f"총: {len(all_chunks):,}개")

OUT.write_text(json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8")
print(f"저장: {OUT} ({OUT.stat().st_size:,} bytes)")
