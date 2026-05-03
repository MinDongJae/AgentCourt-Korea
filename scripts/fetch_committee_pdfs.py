"""양형위원회 회의자료 PDF 일괄 수집.

게시판 URL 패턴: /sc/krsc/board/BoardViewAction.work?gubun=5&seqnum=N
N의 분포: 1~1744 사이 (회차 17~21)
회의자료는 첨부파일 다운로드 링크가 페이지 안에 있음.
"""
import urllib.request, urllib.parse, json, time, re
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "committee_pdfs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://sc.scourt.go.kr"

# 검증된 seqnum 목록 (회차 17~21 1·2차 회의)
KNOWN_SEQNUMS = [1744, 1735, 1648, 1637, 1550, 1536, 1435, 1425, 1328, 1320]

# 추가 — 각 회차 사이를 페이징으로 자동 발견
def fetch_board_page(page=1, gubun=5):
    """게시판 페이지 → seqnum 리스트."""
    url = f"{BASE}/sc/krsc/board/BoardListAction.work?gubun={gubun}&pageIndex={page}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        # seqnum 추출
        seqnums = list(set(re.findall(r"seqnum=(\d+)", html)))
        return seqnums, html
    except Exception as e:
        print(f"  ERR page {page}: {e}")
        return [], ""

def fetch_post(seqnum, gubun=5):
    """게시글 진입 → 첨부 PDF URL 추출."""
    url = f"{BASE}/sc/krsc/board/BoardViewAction.work?gubun={gubun}&seqnum={seqnum}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        # 첨부파일 URL 추출 — 보통 /sc/krsc/files/... 또는 download.work
        attach_urls = re.findall(r'href=["\']([^"\']*(?:download|\.pdf)[^"\']*)["\']', html, re.I)
        title_m = re.search(r"<title>([^<]+)</title>", html)
        return {
            "seqnum": seqnum,
            "title": title_m.group(1) if title_m else "?",
            "attachments": attach_urls,
        }
    except Exception as e:
        return {"seqnum": seqnum, "error": str(e)}

# 1. 게시판 페이지 1~10 스캔으로 seqnum 전수
print("[1] 게시판 seqnum 수집")
all_seqnums = set(KNOWN_SEQNUMS)
for page in range(1, 11):
    seqs, _ = fetch_board_page(page)
    print(f"  page {page}: {len(seqs)}개 seqnum")
    all_seqnums.update(seqs)
    time.sleep(0.3)
    if not seqs:
        break

print(f"\n총 seqnum: {len(all_seqnums)}개")

# 2. 각 게시글 진입 → 첨부 추출
print("\n[2] 각 게시글 첨부 추출")
results = []
for i, sn in enumerate(sorted({int(x) for x in all_seqnums}, reverse=True), 1):
    info = fetch_post(int(sn))
    n_att = len(info.get("attachments", []))
    print(f"  {i}/{len(all_seqnums)} seqnum={sn} [{info.get('title','?')[:40]}] att={n_att}")
    results.append(info)
    time.sleep(0.4)

# 3. 결과 저장
(OUT_DIR / "board_meta.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"\n메타: {OUT_DIR / 'board_meta.json'}")

# 4. PDF 일괄 다운로드
print("\n[3] PDF 다운로드")
ok = 0
for r in results:
    for att in r.get("attachments", []):
        if not att.lower().endswith(".pdf") and "download" not in att.lower():
            continue
        url = att if att.startswith("http") else f"{BASE}{att}"
        # 안전 파일명
        fn = f"committee_seq{r['seqnum']}_{att.split('/')[-1].split('?')[0]}"
        fn = re.sub(r"[^a-zA-Z0-9_\.\-]", "_", fn)[:100]
        if not fn.endswith(".pdf"):
            fn += ".pdf"
        out = OUT_DIR / fn
        if out.exists() and out.stat().st_size > 1000:
            ok += 1
            continue
        # 한글 URL 인코딩
        try:
            from urllib.parse import quote, urlsplit, urlunsplit
            sp = urlsplit(url)
            safe_path = quote(sp.path, safe="/:")
            safe_query = quote(sp.query, safe="=&")
            safe_url = urlunsplit((sp.scheme, sp.netloc, safe_path, safe_query, sp.fragment))
        except Exception:
            safe_url = url
        try:
            req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if data[:4] == b"%PDF":
                out.write_bytes(data)
                print(f"  ✅ {fn}: {len(data):,} bytes")
                ok += 1
            else:
                print(f"  ⚠ not pdf: {safe_url[:80]}")
        except Exception as e:
            print(f"  ❌ {safe_url[:80]}: {e}")
        time.sleep(0.3)

print(f"\n총 {ok}개 PDF 다운로드 → {OUT_DIR}")
