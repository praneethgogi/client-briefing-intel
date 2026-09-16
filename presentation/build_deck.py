"""Build the final-round presentation deck.

Run from the repo root:  .venv\\Scripts\\python.exe presentation\\build_deck.py

Every slide carries its talk track in the speaker notes. Screenshots come from
docs/, captured from the running app after the live evaluation passed.
"""
from __future__ import annotations

import pathlib

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "presentation" / "Client_Briefing_Intelligence.pptx"

NAVY = RGBColor(0x12, 0x3A, 0x66)
BLUE = RGBColor(0x1F, 0x5E, 0xA8)
INK = RGBColor(0x1C, 0x22, 0x28)
MUTED = RGBColor(0x5A, 0x6B, 0x7D)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RULE = RGBColor(0xD8, 0xDF, 0xE6)
GOOD = RGBColor(0x1B, 0x7F, 0x4B)
WARN = RGBColor(0xB1, 0x6A, 0x00)
WASH = RGBColor(0xF4, 0xF7, 0xFA)

FONT = "Segoe UI"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.85)
BODY_W = W - 2 * MARGIN

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


# ----------------------------------------------------------------- primitives
def slide(notes: str = ""):
    s = prs.slides.add_slide(BLANK)
    if notes:
        s.notes_slide.notes_text_frame.text = notes.strip()
    return s


def box(s, left, top, width, height):
    tb = s.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def para(tf, text, size, *, bold=False, color=INK, space_before=0, space_after=6,
         align=PP_ALIGN.LEFT, first=False, line=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    r = p.add_run()
    r.text = text
    f = r.font
    f.name, f.size, f.bold, f.color.rgb = FONT, Pt(size), bold, color
    return p


def rect(s, left, top, width, height, fill=None, line=None, line_w=1.0):
    from pptx.enum.shapes import MSO_SHAPE
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    return sh


TITLE_CHARS_PER_LINE = 54  # 32pt bold Segoe UI across the body width, measured from renders


def heading(s, title, kicker=None, sub=None):
    """Standard slide header. Returns the y where body content may start.

    The title height is derived from how many lines it will wrap to, so a long
    title pushes the subtitle down instead of printing on top of it.
    """
    y = Inches(0.52)
    if kicker:
        tf = box(s, MARGIN, y, BODY_W, Inches(0.3))
        para(tf, kicker.upper(), 12, bold=True, color=BLUE, first=True, space_after=0)
        y += Inches(0.34)
    lines = max(1, -(-len(title) // TITLE_CHARS_PER_LINE))
    title_h = Inches(0.56) * lines + Inches(0.1)
    tf = box(s, MARGIN, y, BODY_W, title_h)
    para(tf, title, 32, bold=True, color=NAVY, first=True, space_after=0, line=1.05)
    y += title_h
    if sub:
        tf = box(s, MARGIN, y, BODY_W, Inches(0.4))
        para(tf, sub, 15, color=MUTED, first=True, space_after=0)
        y += Inches(0.44)
    rect(s, MARGIN, y + Inches(0.06), BODY_W, Emu(9525), fill=RULE)
    return y + Inches(0.32)


def bullets(s, items, top, *, width=None, left=None, size=17, gap=11):
    left = left if left is not None else MARGIN
    width = width if width is not None else BODY_W
    tf = box(s, left, top, width, H - top - Inches(0.6))
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            text, note = item
        else:
            text, note = item, None
        para(tf, "•  " + text, size, bold=False, color=INK,
             space_before=0 if i == 0 else gap, space_after=0, first=(i == 0), line=1.15)
        if note:
            para(tf, "    " + note, size - 3, color=MUTED, space_before=3, space_after=0, line=1.1)
    return tf


def footer(s, text):
    tf = box(s, MARGIN, H - Inches(0.55), BODY_W, Inches(0.3))
    para(tf, text, 11, color=MUTED, first=True, space_after=0)


def picture(s, name, left, top, width):
    p = DOCS / name
    if not p.exists():
        rect(s, left, top, width, Inches(3.4), fill=WASH, line=RULE)
        tf = box(s, left + Inches(0.2), top + Inches(1.5), width - Inches(0.4), Inches(0.5))
        para(tf, f"[{name} missing]", 13, color=MUTED, align=PP_ALIGN.CENTER, first=True)
        return None
    pic = s.shapes.add_picture(str(p), left, top, width=width)
    pic.line.color.rgb = RULE
    pic.line.width = Pt(0.75)
    return pic


def stat_row(s, stats, top, *, height=Inches(1.02)):
    """stats: list of (value, label, color). Returns the y below the row."""
    n = len(stats)
    gap = Inches(0.18)
    w = int((BODY_W - gap * (n - 1)) / n)
    for i, (value, label, color) in enumerate(stats):
        x = MARGIN + i * (w + gap)
        rect(s, x, top, w, height, fill=WASH, line=RULE)
        tf = box(s, x + Inches(0.16), top + Inches(0.14), w - Inches(0.32), height - Inches(0.2))
        para(tf, value, 26, bold=True, color=color, first=True, space_after=2)
        para(tf, label, 11, color=MUTED, space_after=0, line=1.05)
    return top + height


CHARS_PER_INCH = 13.0  # rough advance width for Segoe UI at ~12.5pt


def _row_lines(row, widths, size):
    """How many wrapped lines the tallest cell in this row will need."""
    worst = 1
    for val, frac in zip(row, widths):
        text = val[0] if isinstance(val, tuple) else val
        usable = (BODY_W / Inches(1)) * frac - 0.2
        per_line = max(8.0, usable * CHARS_PER_INCH * (12.5 / size))
        worst = max(worst, -(-len(text) // int(per_line)))
    return worst


def table(s, headers, rows, top, *, widths=None, size=13, head_size=12, row_h=Inches(0.42)):
    """Draw a table. Returns the y below it, accounting for rows that wrap."""
    ncol = len(headers)
    widths = widths or [1.0 / ncol] * ncol
    nrow = len(rows) + 1
    line_h = Inches(0.235) * (size / 12.5)
    pad = Inches(0.17)
    heights = [row_h] + [max(row_h, _row_lines(r, widths, size) * line_h + pad) for r in rows]
    total = sum(heights, Inches(0))
    shape = s.shapes.add_table(nrow, ncol, MARGIN, top, BODY_W, total)
    tbl = shape.table
    for i, h in enumerate(heights):
        tbl.rows[i].height = int(h)
    tbl.first_row = True
    for i, frac in enumerate(widths):
        tbl.columns[i].width = Emu(int(BODY_W * frac))
    for c, h in enumerate(headers):
        cell = tbl.cell(0, c)
        cell.text = ""
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.1)
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = h
        r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(head_size), True, WHITE
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if ri % 2 else WASH
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            p = cell.text_frame.paragraphs[0]
            text, bold, color = (val if isinstance(val, tuple) else (val, False, INK))
            r = p.add_run()
            r.text = text
            r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(size), bold, color
    return top + total


def callout(s, text, top, *, color=BLUE, height=Inches(0.68)):
    # Two lines of callout text at this width run to roughly 150 characters.
    if len(text) > 150:
        height = Inches(0.92)
    top = min(top, H - Inches(0.26) - height)  # never let it run off the slide
    rect(s, MARGIN, top, BODY_W, height, fill=WASH, line=None)
    rect(s, MARGIN, top, Inches(0.05), height, fill=color)
    tf = box(s, MARGIN + Inches(0.24), top + Inches(0.13), BODY_W - Inches(0.48), height - Inches(0.18))
    para(tf, text, 14, bold=True, color=NAVY, first=True, space_after=0, line=1.15)


# --------------------------------------------------------------------- slides
# 1 ---------------------------------------------------------------- title
s = slide("""
Good morning, and thank you for the time. I'm Praneeth.

What I've built is a working prototype for client meeting briefings, running on
my laptop on entirely synthetic data. I'll spend about five minutes on how I
reimagined the workflow, five on the demo, and the rest on where the LLM is and
isn't used, and how I'd prove this is safe to run.

One thing up front: every company, person and number you'll see is fictional.
Nothing here touches real client data.
""")
rect(s, Emu(0), Emu(0), W, H, fill=NAVY)
tf = box(s, MARGIN, Inches(2.35), Inches(10.6), Inches(1.0))
para(tf, "Client Briefing Intelligence", 46, bold=True, color=WHITE, first=True, space_after=0)
tf = box(s, MARGIN, Inches(3.35), Inches(10.6), Inches(0.6))
para(tf, "Reimagining how a coverage team prepares for a client meeting",
     20, color=RGBColor(0xB9, 0xCF, 0xE8), first=True, space_after=0)
rect(s, MARGIN, Inches(4.25), Inches(1.5), Emu(28575), fill=BLUE)
tf = box(s, MARGIN, Inches(4.7), Inches(10.6), Inches(1.2))
para(tf, "Sai Praneeth Reddy Gogireddy", 17, bold=True, color=WHITE, first=True, space_after=4)
para(tf, "Final round  ·  17 September 2026", 14, color=RGBColor(0x9F, 0xB8, 0xD4), space_after=4)
para(tf, "Working prototype  ·  synthetic data throughout  ·  no client or firm data",
     13, color=RGBColor(0x9F, 0xB8, 0xD4), space_after=0)

# 2 ---------------------------------------------------------------- problem
s = slide("""
Here's the reframe that drove every design decision.

The obvious problem is that prep is slow: an analyst spends two or three hours
searching eight systems. That's real, but it isn't the expensive problem.

The expensive problem is that the briefing can be confidently wrong. The CRM says
one AUM figure, the performance system says another. The contact record is ten
months stale, so you greet the wrong CIO. A commitment sits in an email thread
and never reaches the CRM, so nobody delivers it. And some of what's in the
system is restricted and must never reach a sales conversation at all.

So I optimised for trustworthiness first and speed second. Speed is a
by-product; trust is the product.
""")
y = heading(s, "The real risk isn't a slow briefing", kicker="The problem, reframed",
            sub="It's a confident, wrong or leaky one")
stat_row(s, [
    ("8+", "systems searched by hand", NAVY),
    ("2-3 hrs", "analyst prep per meeting", NAVY),
    ("4", "conflicting AUM figures in this data set", WARN),
    ("10 mo", "since the CRM contact was updated", WARN),
], y)
bullets(s, [
    ("Conflicting numbers.", "CRM says $4.2B, the performance system says $3.8B, a meeting note says “about $4.1bn”. Which goes in the briefing?"),
    ("Stale relationships.", "CRM still names the outgoing CIO. You walk in and greet the wrong person."),
    ("Commitments that live in inboxes.", "A client ask sits in an email thread, never reaches the CRM, and is quietly missed."),
    ("Restricted material.", "Deal-team MNPI and legal-hold notes sit in the same stores and must never surface in a sales briefing."),
], y + Inches(1.45))
callout(s, "A wrong briefing costs the relationship. A leaked one costs far more. Speed is the easy half of this problem.",
        H - Inches(1.5))

# 3 ---------------------------------------------------------------- users
s = slide("""
Three users, and they want different things.

The relationship manager wants to walk in prepared and not be surprised. The
analyst wants their hours back. The control functions want to know that nothing
leaked and that every statement can be traced.

The important point is the last row. I didn't define success as "the memo reads
well". I defined it as seven questions answered, every statement cited, conflicts
shown rather than smoothed over, entitlements enforced, and actions tracked.
Those are all testable, which is what makes the evaluation plan possible later.
""")
y = heading(s, "Who it serves, and what “good” means", kicker="Users & success criteria",
            sub="Success had to be testable, or the evaluation plan later is just an opinion")
y2 = table(s, ["", "What they need", "What failure looks like"], [
    [("Relationship manager", True, NAVY), "Walk in prepared; know what's open and what changed",
     "Greets the wrong CIO; misses a commitment"],
    [("Coverage analyst", True, NAVY), "Hours of searching become minutes; evidence is one click away",
     "Rebuilds the same picture by hand every quarter"],
    [("Control functions", True, NAVY), "Nothing restricted surfaces; everything is traceable",
     "A leak with no audit trail"],
], y, widths=[0.22, 0.40, 0.38])
callout(s, "Success = 7 questions answered  ·  every statement cited  ·  conflicts visible  ·  entitlements enforced  ·  actions tracked",
        y2 + Inches(0.3), color=GOOD)
bullets(s, [
    "Each of those five is measurable, so each one became a gate in the evaluation suite.",
], y2 + Inches(1.25))

# 4 ---------------------------------------------------------------- workflow
s = slide("""
This is the heart of the submission, so I'll slow down here.

The brief said: reimagine the workflow, and don't assume the answer is a memo or
a chatbot. A memo is stale the moment it's written. A chatbot makes the human do
the work of knowing what to ask.

So I treated the meeting as the unit of work, not the document, and I built
around a loop with three phases.

Before: unify the data, resolve entities, then generate a briefing where every
statement is cited and checked.

During: the briefing leads with the three things that will actually come up, and
each one is one click from its source.

After: notes captured in thirty seconds become tracked commitments, and those
feed the next briefing. That's the closing of the loop, and it's the part that
compounds. Each meeting leaves the relationship better documented than it found
it.

The prototype does all three. What I'd change next is the surfacing, and I'll
come back to that at the end.
""")
y = heading(s, "The meeting is the unit of work, not the document", kicker="The reimagined workflow",
            sub="Not a memo, not a chatbot — a loop that gets better every time the team meets a client")
gap = Inches(0.28)
cw = int((BODY_W - 2 * gap) / 3)
phases = [
    ("BEFORE", "Prepare", [
        "Unify 12 structured sources + 18 documents",
        "Resolve entities, flag conflicts and gaps",
        "Generate: cited, checked, access-filtered",
    ], BLUE),
    ("DURING", "In the meeting", [
        "Three talking points, not seven sections",
        "Every claim one click from its source",
        "What's open, what's due, what changed",
    ], NAVY),
    ("AFTER", "Capture & close", [
        "Paste notes → new asks and commitments",
        "Suggested actions become tracked tasks",
        "Feeds the next briefing automatically",
    ], GOOD),
]
for i, (kick, title, items, col) in enumerate(phases):
    x = MARGIN + i * (cw + gap)
    rect(s, x, y, cw, Inches(3.15), fill=WASH, line=RULE)
    rect(s, x, y, cw, Inches(0.07), fill=col)
    tf = box(s, x + Inches(0.22), y + Inches(0.28), cw - Inches(0.44), Inches(2.6))
    para(tf, kick, 11, bold=True, color=col, first=True, space_after=3)
    para(tf, title, 21, bold=True, color=NAVY, space_after=10)
    for j, it in enumerate(items):
        para(tf, "•  " + it, 13.5, color=INK, space_before=0 if j == 0 else 8, space_after=0, line=1.15)
callout(s, "The loop is the point: every meeting leaves the relationship better documented than it found it.",
        y + Inches(3.45), color=GOOD)
footer(s, "The assignment asked us not to assume the answer is a memo or a chatbot. A memo is stale on arrival; a chatbot makes the human guess what to ask.")

# 5 ---------------------------------------------------------------- options
s = slide("""
Three ways to build this. I'll be quick, and I'm happy to go deeper in questions.

Option B is agent-first: give a model the tools and let it decide what to call.
It demos well and it's genuinely flexible. But it's hard to evaluate, latency is
unpredictable, and crucially it weakens the answer to "where is the LLM not
used", because the answer becomes "it's used everywhere, including the security
path".

Option C is knowledge-graph-first. Right long-term answer for entity resolution
at scale, too big for one day, and it doesn't de-risk generation.

I chose A: a deterministic backbone with the LLM at the edges. Code decides,
the model reads and writes. It can't fail badly in a live demo, and every claim
I make about it is measurable.
""")
y = heading(s, "Three options; I picked the one I could prove", kicker="Options considered")
y2 = table(s, ["", "Approach", "Why not / why yes"], [
    [("A", True, GOOD), ("Deterministic backbone, LLM at the edges, thin MCP surface", True, NAVY),
     ("CHOSEN — predictable, evaluable, and it can't fail badly live", True, GOOD)],
    [("B", True, MUTED), "Agent-first: model chooses the tools",
     "Flexible and demos well, but unpredictable latency, harder to evaluate, and it weakens the “where the LLM is not used” answer"],
    [("C", True, MUTED), "Knowledge-graph first",
     "The right long-term answer for entity resolution at scale; too large for one day and it doesn't de-risk generation"],
], y, widths=[0.06, 0.34, 0.60])
callout(s, "Agentic search still has a place — in follow-up Q&A and over MCP, where it is bounded and still entitlement-checked.",
        y2 + Inches(0.3))

# 6 ---------------------------------------------------------------- architecture
s = slide("""
Left to right: sources, ingestion, one governed store, then serving.

Ingestion does four things: resolves records to clients, applies data-quality
rules, uses the LLM to extract asks and commitments from free text, and records
lineage for every row.

Everything then lands in one canonical store. In the prototype that's SQLite; in
production it's a governed lakehouse, and nothing above it changes.

On the serving side the important detail is the order. Identity is resolved
first. Every tool call is entitlement-checked before it runs, so retrieval is
already filtered before scoring, and the model only ever sees text this user is
allowed to see.

Then LangGraph fans out: seven sections drafted in parallel, each one verified,
and anything that fails verification falls back to deterministic text.

The same governed tools back the REST API, the MCP server and the eval harness.
One contract, three consumers.
""")
y = heading(s, "One governed store, one set of tools, three consumers", kicker="Architecture")
lane_h = Inches(0.86)
lane_gap = Inches(0.11)
lanes = [
    ("SOURCES", "CRM  ·  Finance DW  ·  Product DW  ·  Performance  ·  Service desk  ·  Emails, notes, prior briefings, research, approved news", MUTED),
    ("INGESTION", "Entity resolution (ID → LEI → alias → fuzzy, with a review band)  ·  Data-quality rules  ·  LLM extraction  ·  Lineage & freshness", BLUE),
    ("CANONICAL STORE", "SQLite standing in for a governed lakehouse  —  crosswalk, DQ issues, lineage, audit log", NAVY),
    ("SERVING", "Principal (identity × purpose) → entitlement-checked tools → LangGraph: 7 sections in parallel → verifier → fallback", BLUE),
    ("CONSUMERS", "React UI  ·  MCP server  ·  Evaluation harness & CI gate", GOOD),
]
for i, (kick, text, col) in enumerate(lanes):
    top = y + i * (lane_h + lane_gap)
    rect(s, MARGIN, top, BODY_W, lane_h, fill=WASH, line=RULE)
    rect(s, MARGIN, top, Inches(0.06), lane_h, fill=col)
    tf = box(s, MARGIN + Inches(0.26), top + Inches(0.13), Inches(2.1), lane_h - Inches(0.2))
    para(tf, kick, 11.5, bold=True, color=col, first=True, space_after=0)
    tf = box(s, MARGIN + Inches(2.5), top + Inches(0.15), BODY_W - Inches(2.8), lane_h - Inches(0.2))
    para(tf, text, 13, color=INK, first=True, space_after=0, line=1.18)
footer(s, "Entitlements are enforced before retrieval and before prompting, never after generation.")

# 7 ---------------------------------------------------------------- llm or not
s = slide("""
This is the slide I'd most like you to take away.

The rule is one line: the LLM reads and writes; code decides.

Anything that must be exact, repeatable or defensible is code. Entity
resolution, because a wrong merge is a data-access incident. Entitlements,
because security decisions are never probabilistic. Every number, because
numbers must reconcile. Conflict detection and commitment status, because
they're just comparisons of sources and dates.

The model does the two things it's genuinely better at than code: reading messy
free text, and turning verified facts into readable prose.

And even there it's fenced. Extraction is schema-validated and cached. Narrative
gets an evidence pack and nothing else, must cite, and is checked before display.

One consequence worth stating: the uncertainty section is deliberately never
LLM-written. The one thing a language model will reliably do is smooth over a
contradiction, and that section exists precisely to not do that.
""")
y = heading(s, "The LLM reads and writes. Code decides.", kicker="Where the LLM is used — and where it isn't")
table(s, ["Step", "LLM?", "Why"], [
    ["Entity resolution, dedupe", ("NO", True, GOOD), "A wrong merge is a data-access incident. Must be explainable and repeatable."],
    ["Entitlements, information barrier", ("NO", True, GOOD), "Security decisions are never probabilistic."],
    ["Metrics, materiality, which AUM to use", ("NO", True, GOOD), "Numbers must be exact and auditable."],
    ["Conflict detection, commitment status", ("NO", True, GOOD), "Deterministic comparison of sources and dates."],
    ["Uncertainty section, withheld notices", ("NO", True, GOOD), "Must never be smoothed over — which is exactly what a model would do."],
    ["Reading asks & commitments from free text", ("YES", True, BLUE), "Schema-validated, cached, scored against human labels. Restricted docs never sent."],
    ["Writing 4 narrative sections + talking points", ("YES", True, BLUE), "Evidence pack only, must cite, verified, retry once, then deterministic fallback."],
], y, widths=[0.31, 0.09, 0.60], size=12.5, row_h=Inches(0.46))

# 8 ---------------------------------------------------------------- data
s = slide("""
Data unification, briefly, because this is where most of the real work sits.

Records resolve to a client in a fixed ladder: ID, then LEI, then exact alias,
then fuzzy match. And the ladder has a middle band, which is the part I'd argue
for. Above ninety it merges automatically. Below seventy-five it's rejected.
Between those, it goes to a human.

The example in the data is deliberate. "Northwind Capitol Partners" - a typo -
scores ninety-six and merges. "Northwood Capital Group" scores seventy-five and
does not merge; it's held for a data steward. Those two are four characters
apart and must be treated completely differently. An LLM asked to judge that
will be confidently wrong some fraction of the time, and you won't know which.

Everything that can't be resolved cleanly becomes a visible data-quality issue
in the briefing, rather than a silent omission.
""")
y = heading(s, "Resolution is a ladder with a human in the middle", kicker="Data unification",
            sub="A wrong merge shows one client's data to another client's coverage team")
y2 = table(s, ["Rung", "Match on", "Action"], [
    [("1", True, NAVY), "client_id", ("Merge", True, GOOD)],
    [("2", True, NAVY), "LEI  —  recovers the migration record MIG-77 that has no client_id", ("Merge", True, GOOD)],
    [("3", True, NAVY), "Exact alias  —  “NWCP”, “Evergreen TRS”", ("Merge", True, GOOD)],
    [("4", True, NAVY), "Fuzzy ≥ 90  —  “Northwind Capitol Partners” (typo) scores 96", ("Merge", True, GOOD)],
    [("5", True, NAVY), "Fuzzy 75-89  —  “Northwood Capital Group” scores 75", ("Hold for a data steward", True, WARN)],
    [("6", True, NAVY), "Below 75", ("Unresolved, surfaced as a DQ issue", True, MUTED)],
], y, widths=[0.08, 0.62, 0.30], size=12.5, row_h=Inches(0.42))
callout(s, "Four characters separate a merge from an incident. That decision belongs in code with a review band, not in a model.",
        y2 + Inches(0.3), color=WARN)

# 9 ---------------------------------------------------------------- controls
s = slide("""
Identity and controls. Four points, then the screenshot.

First, a principal is identity times purpose. The same person doing meeting prep
and doing supervisory review does not get the same answer. Purpose is part of
the check, not an afterthought.

Second, the filter runs before retrieval, not after generation. The index carries
ACL metadata, so unentitled documents are removed before scoring. The model
physically never receives text this user can't see. You cannot leak what was
never in the prompt.

Third, MNPI has a zero footprint. Restricted documents aren't just hidden -
they're not counted. Leo is told "one item withheld: revenue data", because he's
allowed to know that. Nobody is told that a deal exists.

Fourth, over MCP the identity comes from the host environment, never from a tool
argument. A model cannot choose whose permissions it runs with.

On screen: same client, same moment, different analyst. Revenue is gone, the
banner says so, and the third client isn't even in his list.
""")
y = heading(s, "Filter before retrieval, never after generation", kicker="Identity & controls")
left_w = Inches(5.25)
bullets(s, [
    ("Principal = identity × purpose.", "The same person gets different answers doing meeting prep vs supervisory review."),
    ("Three levels of check.", "Row (coverage), field (revenue is confidential), document (classification × purpose)."),
    ("MNPI has zero footprint.", "Not hidden — not counted. You can't infer a deal exists from a withheld count."),
    ("MCP identity comes from the host.", "Never a tool argument. A model cannot choose whose permissions it runs with."),
], y, left=MARGIN, width=left_w, size=15, gap=13)
picture(s, "screenshot_analyst.png", MARGIN + left_w + Inches(0.35), y,
        BODY_W - left_w - Inches(0.35))
footer(s, "Coverage Analyst view: revenue withheld and declared, one fewer client in the list, and the briefing rebuilt without the data — not redacted after the fact.")

# 10 --------------------------------------------------------------- demo
s = slide("""
Switching to the live app now.

[If the demo fails: this screenshot is the same view, and offline mode is
configured as a fallback - LLM_MODE=offline in .env - so I can still show the
full flow without the network.]

Run the script: build, talking points, click a citation, what changed, the
ledger with the untracked ask, the conflicts, create the action, switch to Leo,
switch to Ben for the denial, run trace, post-meeting capture, evaluation page.
""")
y = heading(s, "Live demo", kicker="Five minutes",
            sub="Ava Chen preparing for tomorrow's Northwind meeting with the new CIO")
table(s, ["", "Beat", "What to watch"], [
    [("1", True, BLUE), "Build the briefing", "11 sources, 3 conflicts, 0 withheld — built in about four seconds"],
    [("2", True, BLUE), "Talking points → click a citation", "Every statement traces to a source document, one click"],
    [("3", True, BLUE), "Asks & commitments", "“Not tracked in CRM” and “Due at this meeting” — the ask that would have been missed"],
    [("4", True, BLUE), "Uncertain / conflicting", "Four AUM figures, the one chosen and why; the stale CIO; the near-miss held for review"],
    [("5", True, BLUE), "Create the suggested action → rebuild", "The flag clears. The briefing drives the workflow, it doesn't just describe it"],
    [("6", True, BLUE), "Switch to Leo, then Ben", "Revenue withheld and declared; then a 403 — the client isn't even listed"],
    [("7", True, BLUE), "Run trace → post-meeting notes → evals", "Every step, tool call and token; notes become commitments; all 13 gates green"],
], y, widths=[0.05, 0.31, 0.64], size=12.5, row_h=Inches(0.45))
footer(s, "Backup: screenshots on the following slides, and offline mode (LLM_MODE=offline) runs the whole flow with no network.")

# 11 --------------------------------------------------------------- eval plan
s = slide("""
How I'd prove this is safe to run.

Thirteen gates in five families. The top family is absolute: zero leakage, access
control exactly right, injection produces nothing. Those aren't thresholds I
tune - they're pass or fail at one hundred percent, and the build fails if they
slip.

Groundedness: every statement carries a valid citation, and every number matches
the source it cites, within a tolerance and the same unit kind.

Then completeness, component quality, and operational cost.

The whole thing runs in CI on every push. And the rule I held to all day: when a
gate failed, I fixed the prompt or the code. I never moved the threshold. A gate
you move when it's inconvenient isn't a gate.

In production this extends: shadow mode alongside analysts, thumbs up and down
per bullet, drift monitoring on the rejection rate, periodic red-team sets, and
a golden set grown from real corrections.
""")
y = heading(s, "13 gates, five families, running in CI", kicker="Evaluation plan: how we show it's safe to run")
y2 = table(s, ["Family", "Gates", "Bar"], [
    [("Safety", True, NAVY), "Restricted-content leakage  ·  access-control outcomes per role  ·  prompt-injection resistance",
     ("100%, non-negotiable", True, GOOD)],
    [("Groundedness", True, NAVY), "Citation validity  ·  numeric faithfulness against the cited source",
     ("100%", True, GOOD)],
    [("Completeness", True, NAVY), "All 7 questions answered  ·  conflict recall  ·  ledger status  ·  withheld accuracy  ·  entity resolution",
     ("100%", True, GOOD)],
    [("Components", True, NAVY), "Retrieval hit@5  ·  extraction F1 vs human labels",
     ("≥ 0.75  /  ≥ 0.70", True, BLUE)],
    [("Operational", True, NAVY), "Latency  ·  LLM calls  ·  tokens  ·  verifier rejections",
     ("Tracked, reported", True, MUTED)],
], y, widths=[0.14, 0.60, 0.26], size=12.5, row_h=Inches(0.55))
callout(s, "When a gate failed I fixed the prompt, never the threshold. A gate you move when it's inconvenient isn't a gate.",
        y2 + Inches(0.3), color=WARN)

# 12 --------------------------------------------------------------- what it caught
s = slide("""
This is the slide I'd least like to skip, because it's the honest one.

My offline suite was thirteen out of thirteen green. Then I ran it against the
real model for the first time, and it found five defects. I want to walk through
two of them.

The first: the new CIO's name rendered as the word "None" - on the conflict
card, and in the suggested CRM action. The cause was that my extraction prompt
never actually defined which person the "person" field meant. Offline mode
replays human labels, which already had the name, so offline could never have
caught it. Only a live run could.

The second is the one I find genuinely instructive. My scorecard reported zero
verifier rejections. That was false. The executive summary was failing
verification on every single build and silently falling back to deterministic
text - and my metric summed rejections across sections only. The summary wasn't
in the denominator.

The lesson generalises well beyond this project: an uninstrumented surface
always looks perfect. Zero is only meaningful if you know what was counted.

I fixed the prompt, and I fixed the metric to count the summary. It now reports
zero honestly.
""")
y = heading(s, "The offline suite was green. The live run found five defects.",
            kicker="What the evaluation actually caught",
            sub="Including one in the evaluation itself")
y2 = table(s, ["#", "Defect", "Why offline couldn't catch it"], [
    [("1", True, WARN), "New CIO's name rendered as “None” on the conflict card and the CRM action",
     "The prompt never defined which person the “person” field meant. Offline replays human labels that already had the name."],
    [("2", True, WARN), ("Scorecard reported 0 verifier rejections — and it was wrong", True, NAVY),
     ("The summary failed verification on every build and fell back silently. The metric summed sections only; the summary wasn't in the denominator.", False, NAVY)],
    [("3", True, MUTED), "Extraction cache ignored the prompt", "Prompt edits were masked by stale cache — I was scoring the old prompt"],
    [("4", True, MUTED), "“Thursday” in an email vs a Friday meeting in the calendar",
     "The model can't resolve an ambiguous relative date; the deadline now resolves against the system of record"],
    [("5", True, MUTED), "Hard-coded temperature, and a reset path that failed on Windows",
     "Environment-specific — invisible in a Linux sandbox"],
], y, widths=[0.04, 0.38, 0.58], size=12, row_h=Inches(0.52))
callout(s, "An uninstrumented surface always looks perfect. “Zero” only means something once you know what was counted.",
        y2 + Inches(0.28), color=WARN)

# 13 --------------------------------------------------------------- results
s = slide("""
Where it landed, measured on the live model.

All thirteen gates pass. Zero leakage, zero verifier rejections - and that zero
now includes the summary. About four and a half seconds to build a briefing,
roughly five thousand tokens, which is well under a cent.

Two numbers I want to be honest about.

Extraction F1 offline reads 1.0. That is replay, not a measurement - offline mode
replays the human labels, so of course it agrees with them. The real number is
the live one: 0.75 to 0.81 across runs.

And that's a range, not a point, because it varies run to run. On an eighteen
document golden set, a single item moves F1 by about four points. So I'd call it
directional evidence that extraction works, not a benchmark. With a set this
small, anyone quoting two decimal places is overclaiming.
""")
y = heading(s, "All 13 gates pass on the live model", kicker="Results",
            sub="Measured against gpt-4o-mini, not simulated")
y2 = stat_row(s, [
    ("13 / 13", "gates passing, live", GOOD),
    ("0", "restricted-content leaks", GOOD),
    ("0", "verifier rejections", GOOD),
    ("4.4s", "to build a briefing", NAVY),
    ("~5k", "tokens per briefing", NAVY),
    ("< $0.01", "cost per briefing", NAVY),
], y)
y3 = table(s, ["Metric", "Offline", "Live", "Gate"], [
    ["Leakage / access control / injection", "0  ·  100%  ·  0", ("0  ·  100%  ·  0", True, GOOD), "absolute"],
    ["Citation validity, numeric faithfulness", "100%", ("100%", True, GOOD), "100%"],
    ["Coverage, conflicts, ledger, entity resolution", "100%", ("100%", True, GOOD), "100%"],
    ["Retrieval hit@5", "1.00", ("1.00", True, GOOD), "≥ 0.75"],
    [("Extraction F1", True, WARN), ("1.00  — replay, not a measurement", False, WARN),
     ("0.75 – 0.81 across runs", True, WARN), "≥ 0.70"],
], y2 + Inches(0.28), widths=[0.40, 0.24, 0.24, 0.12], size=12.5, row_h=Inches(0.45))
callout(s, "On an 18-document golden set one item moves F1 by ~4 points. That's directional evidence, not a benchmark — and I'd rather say so than quote two decimals.",
        y3 + Inches(0.26), color=WARN)

# 14 --------------------------------------------------------------- limits
s = slide("""
What I'd want you to know before anyone relied on this.

The golden set is eighteen documents and I wrote it myself, so it encodes my
judgement of what a good extraction looks like. That's the weakest part of the
evaluation and the first thing I'd grow.

Materiality is a rule - ten percent moves, twenty-five basis points. Transparent
and explainable, but a real deployment would tune those per segment with the
desk.

Identity is a demo header standing in for SSO. The enforcement points are real
and in the right places; the authentication in front of them is not.

Opportunity ranking is a transparent heuristic, not a model.

And storage is SQLite, which is a stand-in - but every tool contract above it is
unchanged when it becomes a lakehouse.

None of these are hidden in the code. They're all stated in the README.
""")
y = heading(s, "What I'd want you to know before relying on it", kicker="Trade-offs & limitations")
bullets(s, [
    ("The golden set is 18 documents, and I wrote it.", "It encodes my judgement of a good extraction. This is the weakest part of the evaluation and the first thing I'd grow — in production, from real entitled corrections."),
    ("Offline extraction F1 of 1.0 is replay, not accuracy.", "Offline mode replays the human labels, so agreement is guaranteed. The live number is the only real one."),
    ("Materiality is a rule, not a model.", "10% moves, 25bp vs benchmark. Transparent and explainable, but a real deployment would tune thresholds per segment with the desk."),
    ("Identity is a demo header standing in for SSO.", "The enforcement points are real and correctly placed; the authentication in front of them is not."),
    ("SQLite, BM25, heuristic opportunity ranking.", "Deliberate MVP choices. Each swaps out behind an unchanged tool contract."),
], y, size=15, gap=13)
footer(s, "All of these are stated in the README, not buried in the code.")

# 15 --------------------------------------------------------------- next
s = slide("""
Two horizons. Product first, then platform.

On product: the prototype proves the hard part - that you can generate a
briefing that is cited, checked and access-filtered. What it doesn't yet do is
present that as three phases. Today all three live on one page. The next
iteration splits them: a prepare view, a compact in-meeting view, and a capture
view. Same engine, better surfacing. And briefings should be waiting at six in
the morning for every meeting on the calendar, not built on a button press.

On platform: CDC connectors into a governed lakehouse, entity resolution
becoming a real MDM service with a steward queue. SSO to a policy engine to
row-level security, with document ACLs in the vector index. Durable LangGraph
checkpoints so a human can approve before anything writes to CRM. And model
governance - a registry, prompt versioning, evals per release.

I'd note the prompt versioning point isn't theoretical for me. I hit exactly
that bug today: I changed a prompt and the cache silently served me results from
the old one.
""")
y = heading(s, "Where this goes next", kicker="Product, then platform")
half = int((BODY_W - Inches(0.35)) / 2)
rect(s, MARGIN, y, half, Inches(3.5), fill=WASH, line=RULE)
rect(s, MARGIN, y, half, Inches(0.07), fill=BLUE)
tf = box(s, MARGIN + Inches(0.24), y + Inches(0.3), half - Inches(0.48), Inches(3.0))
para(tf, "PRODUCT — finish the reimagining", 11.5, bold=True, color=BLUE, first=True, space_after=9)
for i, t in enumerate([
    "Split the one page into three phases: prepare, in-meeting, capture",
    "Briefings pre-built at 06:00 for every meeting on the calendar — not on a button press",
    "In-meeting view: three talking points and a capture box, nothing else",
    "Steward queue for the entity-resolution review band",
]):
    para(tf, "•  " + t, 13.5, color=INK, space_before=0 if i == 0 else 9, space_after=0, line=1.15)
rect(s, MARGIN + half + Inches(0.35), y, half, Inches(3.5), fill=WASH, line=RULE)
rect(s, MARGIN + half + Inches(0.35), y, half, Inches(0.07), fill=NAVY)
tf = box(s, MARGIN + half + Inches(0.59), y + Inches(0.3), half - Inches(0.48), Inches(3.0))
para(tf, "PLATFORM — production scale", 11.5, bold=True, color=NAVY, first=True, space_after=9)
for i, t in enumerate([
    "CDC connectors → governed lakehouse; MDM service for entity resolution",
    "SSO/OIDC → policy engine (OPA) → row-level security + ACL-filtered vector search",
    "Durable LangGraph checkpoints; human approval before any CRM write",
    "Model registry, prompt versioning, evals per release, LLM-as-judge alongside rule checks",
]):
    para(tf, "•  " + t, 13.5, color=INK, space_before=0 if i == 0 else 9, space_after=0, line=1.15)
callout(s, "The prototype proves the hard part — governed, verified generation. What's left is surfacing it well and hardening the platform underneath.",
        y + Inches(3.75), color=GOOD)

# 16 --------------------------------------------------------------- close
s = slide("""
To close.

I reimagined this as a loop around the meeting rather than a document: prepare,
support the conversation, capture what happened, and let that feed the next one.

The design rule is one line - the LLM reads and writes, code decides - and it's
what makes everything else provable.

And I proved it: thirteen gates, live, including the ones I'd least like to
fail. The evaluation found real defects, including one in the evaluation itself,
and I've told you about them rather than hoping you wouldn't ask.

Repo's on the slide. Everything is synthetic. Happy to take questions.
""")
rect(s, Emu(0), Emu(0), W, H, fill=NAVY)
tf = box(s, MARGIN, Inches(1.75), Inches(11.0), Inches(1.0))
para(tf, "Trustworthy by construction", 42, bold=True, color=WHITE, first=True, space_after=6)
para(tf, "cited  ·  entitled  ·  evaluated", 24, color=RGBColor(0xB9, 0xCF, 0xE8), space_after=0)
rect(s, MARGIN, Inches(3.5), Inches(1.5), Emu(28575), fill=BLUE)
tf = box(s, MARGIN, Inches(3.95), Inches(11.4), Inches(2.0))
for i, t in enumerate([
    "A loop around the meeting, not a document that goes stale",
    "The LLM reads and writes; code decides — which is what makes it provable",
    "13 gates passing live, and an honest account of what they caught",
]):
    para(tf, "•  " + t, 16, color=WHITE, first=(i == 0), space_before=0 if i == 0 else 10,
         space_after=0, line=1.15)
tf = box(s, MARGIN, H - Inches(1.35), Inches(11.4), Inches(0.8))
para(tf, "github.com/praneethgogi/client-briefing-intel", 16, bold=True,
     color=RGBColor(0x8F, 0xC2, 0xF0), first=True, space_after=4)
para(tf, "All companies, people, numbers and events are fictional and synthetic.",
     12, color=RGBColor(0x8A, 0xA4, 0xC2), space_after=0)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(str(OUT))
print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")

