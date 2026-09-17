"""Record the demo as a video, by driving the real app.

    .venv\\Scripts\\python.exe scripts\\record_demo.py

Scripted rather than screen-captured, so it can be re-recorded after any change
instead of being a one-take artefact that silently goes stale. Writes a .webm to
docs/demo/. Needs the backend on :8000 and the frontend on :5173, and resets the
demo data first so every recording starts from the same world.

The video is sent rather than narrated, so it carries its own titles and captions:
without them a viewer sees clicking and has to infer the point.

Recording begins the moment the browser context is created, so the app is loaded
and settled before anything worth watching happens - otherwise the opening seconds
are a blank page and the first screen is effectively missing.
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

BEAT = 2600       # long enough to read a caption and see the screen under it
PAUSE = 1200
CARD = 3600

OVERLAY_CSS = """
#demo-cap {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 99998;
  background: linear-gradient(180deg, rgba(10,34,64,0) 0%, rgba(10,34,64,.93) 38%);
  color: #fff; padding: 46px 40px 24px;
  font-family: "Segoe UI", system-ui, sans-serif;
  opacity: 0; transition: opacity .45s ease;
  pointer-events: none;
}
#demo-cap.on { opacity: 1; }
#demo-cap .step {
  font-size: 11px; letter-spacing: 1.6px; text-transform: uppercase;
  color: #c8a24a; font-weight: 700; margin-bottom: 5px;
}
#demo-cap .line { font-size: 23px; font-weight: 600; font-family: Georgia, serif; }
#demo-cap .sub { font-size: 14px; color: #b9c6d6; margin-top: 5px; }

#demo-card {
  position: fixed; inset: 0; z-index: 99999; background: #0a2240; color: #fff;
  display: flex; flex-direction: column; justify-content: center; padding: 0 92px;
  font-family: "Segoe UI", system-ui, sans-serif;
  opacity: 1; transition: opacity .6s ease;
}
#demo-card.off { opacity: 0; pointer-events: none; }
#demo-card .rule { width: 74px; height: 4px; background: #c8a24a; margin: 26px 0; }
#demo-card h1 { font-family: Georgia, serif; font-size: 52px; margin: 0; font-weight: 600; }
#demo-card h2 { font-family: Georgia, serif; font-size: 26px; margin: 0; font-weight: 400; color: #b9c6d6; }
#demo-card .foot { font-size: 15px; color: #8fa3bb; margin-top: 30px; line-height: 1.7; }
#demo-card .repo { color: #c8a24a; font-weight: 700; }
"""

OVERLAY_JS = """
() => {
  if (document.getElementById('demo-cap')) return;
  const cap = document.createElement('div');
  cap.id = 'demo-cap';
  cap.innerHTML = '<div class="step"></div><div class="line"></div><div class="sub"></div>';
  document.body.appendChild(cap);
  const card = document.createElement('div');
  card.id = 'demo-card';
  card.innerHTML = '<h1></h1><div class="rule"></div><h2></h2><div class="foot"></div>';
  document.body.appendChild(card);
}
"""


def reset_demo_data() -> None:
    req = urllib.request.Request(f"{API}/api/admin/reset", method="POST",
                                 headers={"X-User-Id": "ava.chen"})
    urllib.request.urlopen(req, timeout=300).read()
    print("  demo data reset")


class Demo:
    def __init__(self, page):
        self.page = page

    # -- overlay ----------------------------------------------------------
    def install(self) -> None:
        self.page.add_style_tag(content=OVERLAY_CSS)
        self.page.evaluate(OVERLAY_JS)

    def card(self, title: str, sub: str, foot: str = "", hold: int = CARD) -> None:
        self.page.evaluate(
            """([t, s, f]) => {
                const c = document.getElementById('demo-card');
                c.querySelector('h1').textContent = t;
                c.querySelector('h2').textContent = s;
                c.querySelector('.foot').innerHTML = f;
                c.classList.remove('off');
            }""", [title, sub, foot])
        self.page.wait_for_timeout(hold)

    def card_off(self) -> None:
        self.page.evaluate("() => document.getElementById('demo-card').classList.add('off')")
        self.page.wait_for_timeout(700)

    def say(self, step: str, line: str, sub: str = "") -> None:
        self.page.evaluate(
            """([n, l, s]) => {
                const c = document.getElementById('demo-cap');
                c.querySelector('.step').textContent = n;
                c.querySelector('.line').textContent = l;
                c.querySelector('.sub').textContent = s;
                c.classList.add('on');
            }""", [step, line, sub])

    def quiet(self) -> None:
        self.page.evaluate("() => document.getElementById('demo-cap').classList.remove('on')")

    # -- app helpers ------------------------------------------------------
    def top(self) -> None:
        self.page.evaluate("() => { const m = document.querySelector('.main'); if (m) m.scrollTop = 0; }")

    def build(self) -> None:
        for label in ("Build briefing", "Rebuild briefing"):
            btn = self.page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                break
        for _ in range(90):
            if self.page.get_by_text("Top talking points").count():
                break
            self.page.wait_for_timeout(1000)
        self.page.wait_for_timeout(PAUSE)

    def persona(self, name: str) -> None:
        self.page.select_option("header select", label=name)
        self.page.wait_for_timeout(PAUSE)


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
        d = Demo(page)

        # Load and settle BEFORE anything worth filming. The recording is already
        # running, so this is the blank stretch - keep it short and get a card up.
        page.goto(UI, wait_until="networkidle")
        page.wait_for_selector("text=Your week", timeout=60000)
        page.wait_for_timeout(1200)
        d.install()

        d.card("Client Briefing Intelligence",
               "A coverage team doesn’t have a meeting. It has a calendar.",
               "Working prototype · synthetic data throughout<br>"
               "<span class='repo'>github.com/praneethgogi/client-briefing-intel</span>")
        d.card_off()

        # 1 -- the landing view, held still so it actually registers
        d.top()
        d.say("01 · Triage", "It doesn’t open on a document.",
              "Three meetings this week. Which can Ava walk into?")
        page.wait_for_timeout(BEAT + 1400)

        d.say("01 · Triage", "Rules, not a model.",
              "Conflicts, unresolved records, stale sources, untracked asks — about 250ms")
        page.wait_for_timeout(BEAT)

        # 2 -- why Northwind is blocked
        d.say("02 · Blocked", "It refused to merge two firms.",
              "“Northwood Capital Group” scores 75 against Northwind — held for a human")
        page.get_by_text("Northwood Capital Group", exact=False).first.scroll_into_view_if_needed()
        page.wait_for_timeout(BEAT + 600)

        # 3 -- hand it to someone who covers the client
        d.say("03 · Hand off", "Assign it to the analyst.",
              "Only people already entitled to this client are offered")
        page.get_by_role("button", name="Assign").first.click()
        page.wait_for_timeout(PAUSE + 500)
        page.get_by_role("button", name="Leo Park").first.click()
        page.wait_for_timeout(BEAT)

        # 4 -- Leo clears it in his own week
        d.say("04 · The team", "Leo sees it in his week, and clears it.",
              "Assignment is a workflow action, never a grant of access")
        d.persona("Leo Park")
        page.wait_for_timeout(PAUSE)
        page.get_by_role("button", name="Mark resolved").first.click()
        page.wait_for_timeout(BEAT)

        # 5 -- now the briefing
        d.say("05 · Prepare", "Now the briefing.",
              "Seven questions, every statement cited and machine-checked")
        d.persona("Ava Chen")
        page.get_by_text("Northwind Capital Partners", exact=False).first.click()
        page.wait_for_timeout(PAUSE)
        d.build()
        d.top()
        page.wait_for_timeout(BEAT)

        # 6 -- evidence behind a statement
        d.say("06 · Evidence", "Every claim is one click from its source.",
              "Citations are checked to exist, and numbers to match what they cite")
        cite = page.locator(".cite").first
        if cite.count():
            cite.click()
        page.wait_for_timeout(BEAT)

        # 7 -- the ask nobody is tracking
        d.say("07 · The catch", "An ask due at this meeting, tracked nowhere.",
              "Found in an email, absent from the CRM — this is what gets missed today")
        page.get_by_text("Asks & commitments", exact=False).first.scroll_into_view_if_needed()
        page.wait_for_timeout(BEAT + 400)

        # 8 -- pack-driven order, collapsed by default
        d.say("08 · Configuration", "The briefing’s shape is YAML, not code.",
              "A hedge fund review and a fee review order the same seven questions differently")
        page.get_by_role("button", name="Full briefing").first.click()
        page.wait_for_timeout(BEAT)
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(BEAT)
        toggles = page.locator(".card.section.closed .section-toggle")
        if toggles.count():
            d.say("08 · Configuration", "Collapsed until you want it.",
                  "Seven questions as a contents page, not a wall of text")
            toggles.first.click()
            page.wait_for_timeout(BEAT)

        # 9 -- entitlements
        d.say("09 · Entitlements", "Same client, same moment, different analyst.",
              "Revenue is withheld — and Leo is told that it was")
        d.persona("Leo Park")
        page.get_by_text("Northwind Capital Partners", exact=False).first.click()
        page.wait_for_timeout(PAUSE)
        d.build()
        d.top()
        page.wait_for_timeout(BEAT)

        # 10 -- the gate
        d.say("10 · Proof", "Thirteen gates, run in CI on every push.",
              "Zero leakage, valid citations, numbers matching their source")
        d.persona("Ava Chen")
        page.get_by_text("Evaluation", exact=False).first.click()
        page.wait_for_timeout(BEAT + 1200)

        # 11 -- lineage underneath
        d.say("11 · Underneath", "Lineage, data quality and the entity crosswalk.",
              "Every canonical value traces back to the record it came from")
        page.get_by_text("Data & lineage", exact=False).first.click()
        page.wait_for_timeout(BEAT + 400)

        d.quiet()
        page.wait_for_timeout(600)
        d.card("The LLM reads and writes.", "Code decides.",
               "Triage, entity resolution, entitlements, every number and the uncertainty "
               "section are plain code.<br>The model reads prose and writes verified "
               "sentences — nothing else.<br><br>"
               "<span class='repo'>github.com/praneethgogi/client-briefing-intel</span>",
               hold=CARD + 900)

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
