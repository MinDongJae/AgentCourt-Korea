"""29,124건 판례 메타 → chunks (양형기준 chunks와 합본).

각 판례 메타 (사건번호, 사건명, 법원명, 선고일자, 사건종류명, 판시사항, 판결요지)를
하나의 chunk로 합쳐서 검색 가능하게 만듦. 본문 전문은 너무 크니 메타 + 요지만.
"""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent
META_FILE = ROOT / "data" / "precedents" / "precedents_meta.jsonl"
EXISTING_CHUNKS = ROOT / "data" / "sentencing_chunks.json"
OUT_PATH = ROOT / "data" / "sentencing_chunks_v2.json"

print(f"[1] 양형기준 청크 로드")
sentencing_chunks = json.loads(EXISTING_CHUNKS.read_text(encoding="utf-8"))
print(f"  기존: {len(sentencing_chunks):,}개")

print(f"\n[2] 판례 메타 → chunk 변환")
prec_chunks = []
court_counter = Counter()
inst_counter = Counter()

with META_FILE.open("r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        try:
            p = json.loads(line)
        except:
            continue
        case_no = (p.get("사건번호") or "").replace(" ", "")
        court = p.get("법원명") or ""
        case_name = p.get("사건명") or ""
        case_type = p.get("사건종류명") or ""
        date = p.get("선고일자") or ""
        ruling = p.get("판결유형") or ""
        keyword = p.get("_query_keyword") or ""

        # 본문 — 판시사항/판결요지 (있으면)
        gist = p.get("판시사항") or ""
        summary = p.get("판결요지") or ""

        # 심급
        if any(x in case_no for x in ["고합", "고단", "고정", "고약"]) or "지방법원" in court:
            inst = "1심"
        elif "노" in case_no or "고등법원" in court:
            inst = "2심"
        elif case_no.endswith("도") is False and "도" in case_no.split("2", 1)[-1][:5]:
            inst = "3심"
        elif "대법원" in court:
            inst = "3심"
        else:
            inst = "기타"
        inst_counter[inst] += 1
        court_counter[court] += 1

        text_parts = [
            f"[판례] {case_no} {case_name}".strip(),
            f"법원: {court} | 선고: {date} | 종류: {case_type} | 유형: {ruling}",
        ]
        if gist:
            text_parts.append(f"판시사항: {gist[:600]}")
        if summary:
            text_parts.append(f"판결요지: {summary[:1200]}")

        text = "\n".join(text_parts)
        if len(text) < 50:
            continue

        prec_chunks.append({
            "chunk_id": f"prec_{i:06d}",
            "source": "법제처_판례",
            "case_no": case_no,
            "court": court,
            "instance": inst,
            "crime_keyword": keyword,
            "page": 0,
            "crime_category": keyword or "판례",
            "section": f"판례_{inst}",
            "tags": [inst.lower(), "precedent"],
            "text": text,
        })

print(f"  판례 chunk: {len(prec_chunks):,}개")
print(f"\n  심급 분포:")
total = sum(inst_counter.values())
for k, v in inst_counter.most_common():
    print(f"    {k:<5s}: {v:>6,} ({v/total*100:5.1f}%)")

print(f"\n  법원 top 10:")
for k, v in court_counter.most_common(10):
    print(f"    {k:<25s}: {v:>5,}")

# 합본
all_chunks = sentencing_chunks + prec_chunks
print(f"\n[3] 합본 청크 수: {len(all_chunks):,}개 ({len(sentencing_chunks):,} 양형기준 + {len(prec_chunks):,} 판례)")

OUT_PATH.write_text(json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8")
print(f"  저장: {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
