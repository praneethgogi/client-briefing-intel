"""Record the demo as a video, by driving the real app.

    .venv\\Scripts\\python.exe scripts\\record_demo.py

Scripted rather than screen-captured, so it can be re-recorded after any change
instead of being a one-take artefact that silently goes stale. Writes a .webm to
docs/demo/. Needs the backend on :8000 and the frontend on :5173, and resets the
demo data first so the recording always starts from the same world.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo"
UI = "http://localhost:5173"
API = "http://127.0.0.1:8000"
W, H = 1600, 1000

# Long enough to read, short enough to keep moving.
BEAT = 2200
PAUSE = 1100


def reset_demo_data() -> None:
    req = urllib.request.Request(f"{API}/api/admin/reset", method="POST",
                                 headers={"X-User-Id": "ava.chen"})
    urllib.request.urlopen(req, timeout=300).read()
    print("  demo data reset")


def build(page) -> None:
    for label in ("Build briefing", "Rebuild briefing"):
        btn = page.get_by_role("button", name=label)
        if btn.count():
            btn.first.click()
            break
    for _ in range(90):
        if page.get_by_text("Top talking points").count():
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(PAUSE)


def persona(page, name: str) -> None:
    page.select_option("header select", label=name)
    page.wait_for_timeout(BEAT)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    reset_demo_data()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  record_video_dir=str(OUT),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()

        # 1. It opens on the week, not a document.
        page.goto(UI, wait_until="networkidle")
        page.wait_for_timeout(BEAT + 1200)

        # 2. Northwind is blocked, and the reason is the entity it refused to merge.
        page.get_by_text("Northwood Capital Group", exact=False).first.scroll_into_view_if_needed()
        page.wait_for_timeout(BEAT)

        # 3. Hand it to the analyst who covers this client.
        page.get_by_role("button", name="Assign").first.click()
        page.wait_for_timeout(PAUSE)
        page.get_by_role("button", name="Leo Park").first.click()
        page.wait_for_timeout(BEAT)

        # 4. Leo picks it up in his own week and clears it.
        persona(page, "Leo Park")
        page.get_by_role("button", name="Mark resolved").first.click()
        page.wait_for_timeout(BEAT)

        # 5. Back to Ava: open the briefing that is now unblocked.
        persona(page, "Ava Chen")
        page.get_by_text("Northwind Capital Partners", exact=False).first.click()
        page.wait_for_timeout(PAUSE)
        build(page)

        # 6. Talking points, then the evidence behind one of them.
        page.wait_for_timeout(BEAT)
        cite = page.locator(".cite").first
        if cite.count():
            cite.click()
            page.wait_for_timeout(BEAT)

        # 7. The ask nobody is tracking.
        page.get_by_text("Asks & commitments", exact=False).first.scroll_into_view_if_needed()
        page.wait_for_timeout(BEAT)

        # 8. The full briefing, ordered by this meeting's pack.
        page.get_by_role("button", name="Full briefing").first.click()
        page.wait_for_timeout(BEAT)
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(BEAT)

        # 9. Same client, different analyst: revenue withheld and declared.
        persona(page, "Leo Park")
        page.get_by_text("Northwind Capital Partners", exact=False).first.click()
        page.wait_for_timeout(PAUSE)
        build(page)
        page.wait_for_timeout(BEAT)

        # 10. The evaluation gate.
        persona(page, "Ava Chen")
        page.get_by_text("Evaluation", exact=False).first.click()
        page.wait_for_timeout(BEAT + 1200)

        # 11. Lineage and data quality underneath it.
        page.get_by_text("Data & lineage", exact=False).first.click()
        page.wait_for_timeout(BEAT)

        ctx.close()
        browser.close()

    videos = sorted(OUT.glob("*.webm"))
    if not videos:
        print("  no video produced")
        return 1
    final = OUT / "client_briefing_demo.webm"
    if videos[0] != final:
        videos[0].rename(final)
    print(f"  wrote {final.relative_to(ROOT)} ({final.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
