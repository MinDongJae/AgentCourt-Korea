"""Playwright로 fancy UI 스크린샷 + 시연 영상 자동 녹화.

사전 조건: 서버가 http://localhost:7860 에서 실행 중

산출물:
  - submission_법제처/demo/screenshots/01_landing.png — 랜딩 페이지
  - submission_법제처/demo/screenshots/02_query.png — 사건 입력
  - submission_법제처/demo/screenshots/03_results.png — 분석 결과
  - submission_법제처/demo/video.webm — 시연 영상 (60초)
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEMO_DIR = ROOT / "demo"
SHOT_DIR = DEMO_DIR / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


async def capture():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(DEMO_DIR),
            record_video_size={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        print("[1/4] 랜딩 페이지 로드...")
        await page.goto("http://localhost:7860/", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(SHOT_DIR / "01_landing.png"), full_page=False)
        print(f"   ✅ {SHOT_DIR / '01_landing.png'}")

        print("[2/4] 예시 사건 클릭 (사기 5천만원)...")
        await page.click(".sample-btn:nth-of-type(1)")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(SHOT_DIR / "02_query.png"))
        print(f"   ✅ {SHOT_DIR / '02_query.png'}")

        print("[3/4] 분석 시작 (Claude Opus 4.7 호출)...")
        await page.click("#analyze-btn")
        # 결과 대기 — persona-grid가 나타날 때까지
        try:
            await page.wait_for_selector(".persona-grid", timeout=120000)
        except Exception as e:
            print(f"   ⚠ 결과 대기 타임아웃: {e}")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(SHOT_DIR / "03_results.png"), full_page=True)
        print(f"   ✅ {SHOT_DIR / '03_results.png'}")

        print("[4/4] 모바일 뷰포트 캡처...")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(SHOT_DIR / "04_mobile.png"), full_page=True)
        print(f"   ✅ {SHOT_DIR / '04_mobile.png'}")

        await context.close()
        await browser.close()

    # 영상 파일은 context.close 시 자동 저장됨
    videos = sorted(DEMO_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if videos:
        target = DEMO_DIR / "demo_video.webm"
        if target.exists():
            target.unlink()
        videos[0].rename(target)
        # 잔여 webm 정리
        for v in videos[1:]:
            try: v.unlink()
            except Exception: pass
        print(f"\n시연 영상: {target}")

    print("\n" + "=" * 60)
    print("✅ 전체 캡처 완료")
    for f in sorted(SHOT_DIR.glob("*.png")):
        print(f"   {f.relative_to(ROOT)} ({f.stat().st_size:,} bytes)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(capture())
