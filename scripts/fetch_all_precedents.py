import os
"""형사 판례 전수 수집 — 법제처 OPEN API 페이징.

전략:
- 12개 핵심 죄종 × 페이지 (display=100) → 모든 판례 메타 + 본문 수집
- JSONL 형식으로 저장 (메모리 효율 + 재개 가능)
- 중복 제거 (판례일련번호 기준)
- 일일 한도 보수적: 시간당 1,000회 (총 1만/일 가정)

산출물: data/precedents_all.jsonl
스키마:
  {판례일련번호, 사건번호, 사건명, 법원명, 선고일자, 사건종류명, 판결유형, ...}
"""
import urllib.request, urllib.parse, json, time, os, sys
from pathlib import Path
from collections import OrderedDict

ROOT = Path(__file__).parent.parent
OC = os.getenv("LAW_API_KEY", "test")
BASE = "http://www.law.go.kr/DRF/lawSearch.do"
DETAIL_BASE = "http://www.law.go.kr/DRF/lawService.do"

OUT_DIR = ROOT / "data" / "precedents"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUT_DIR / "fetch_log.txt"
META_FILE = OUT_DIR / "precedents_meta.jsonl"

# 12개 핵심 형사 죄종 + 추가 (양형위 41개 범죄군 매칭)
CRIMES = [
    "사기", "절도", "횡령", "배임", "음주운전", "교통사고",
    "성폭력", "강제추행", "강간", "폭행", "상해", "협박",
    "공갈", "주거침입", "방화", "살인", "강도", "마약",
    "뇌물", "위증", "무고", "공무집행방해", "명예훼손", "스토킹",
    "보이스피싱", "사이버", "성매매", "도박",
]

DISPLAY = 100  # 최대값 (가이드 확인됨)
SLEEP_SEC = 0.5  # 초당 2회 (보수적)


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_search_page(query: str, page: int) -> dict:
    params = {
        "OC": OC, "target": "prec", "type": "JSON",
        "query": query, "display": DISPLAY, "page": page, "search": 2,
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        log(f"  ❌ search err {query} p{page}: {e}")
        return {}


def fetch_one(query: str, seen: set) -> int:
    """단일 죄종의 전 페이지 → seen 갱신, 메타 JSONL append. 신규 건수 반환."""
    new_count = 0
    page = 1
    while True:
        d = fetch_search_page(query, page)
        if not d:
            break
        root = d.get("PrecSearch") or d
        if not isinstance(root, dict):
            break
        items = None
        for k, v in root.items():
            if isinstance(v, list):
                items = v
                break
            elif k == "prec" and isinstance(v, dict):
                items = [v]
                break
        if not items:
            break
        total = int(root.get("totalCnt", 0)) if isinstance(root.get("totalCnt"), (int, str)) and str(root.get("totalCnt", "")).isdigit() else len(items)
        if page == 1:
            log(f"  '{query}': totalCnt={total:,} (페이지 ~{(total + DISPLAY - 1) // DISPLAY})")
        # append meta
        with META_FILE.open("a", encoding="utf-8") as f:
            for it in items:
                if not isinstance(it, dict):
                    continue
                pid = str(it.get("판례일련번호") or it.get("precSeq") or it.get("ID") or "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                it["_query_keyword"] = query
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                new_count += 1
        if len(items) < DISPLAY:
            break
        if page * DISPLAY >= total:
            break
        page += 1
        time.sleep(SLEEP_SEC)
    return new_count


def main():
    log("=" * 70)
    log(f"형사 판례 전수 수집 시작 ({len(CRIMES)}개 죄종)")
    log("=" * 70)

    # 기존 seen 로드 (재개 가능)
    seen = set()
    if META_FILE.exists():
        with META_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    pid = str(d.get("판례일련번호") or "")
                    if pid:
                        seen.add(pid)
                except:
                    continue
        log(f"기존 seen: {len(seen):,}건 (재개)")

    grand_new = 0
    for i, c in enumerate(CRIMES, 1):
        log(f"\n[{i}/{len(CRIMES)}] {c}")
        before = len(seen)
        new = fetch_one(c, seen)
        after = len(seen)
        grand_new += new
        log(f"  → +{new}건 (누적 {after:,})")
        time.sleep(SLEEP_SEC)

    log(f"\n{'='*70}")
    log(f"✅ 전수 수집 완료: 신규 +{grand_new:,}건, 누적 {len(seen):,}건")
    log(f"   메타 파일: {META_FILE} ({META_FILE.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
