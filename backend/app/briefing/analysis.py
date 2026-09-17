"""Deterministic analysis - the parts of the briefing where an LLM is deliberately NOT used:
numbers, materiality, conflicts, commitment status, and change detection.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from rapidfuzz import fuzz

from .. import config
from ..security.entitlements import Principal
from ..tools import structured as T

_VERBS = {"send", "deliver", "provide", "prepare", "share", "create", "follow", "up", "bring", "the", "a", "an", "our"}


def fmt_usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}${a / 1e9:.2f}".rstrip("0").rstrip(".") + "B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:.2f}".rstrip("0").rstrip(".") + "M"
    if a >= 1e3:
        return f"{sign}${a / 1e3:.0f}K"
    return f"{sign}${a:.0f}"


def pct(new: float, old: float) -> float | None:
    if not old:
        return None
    return round((new - old) / abs(old) * 100, 1)


def _subject_key(s: str) -> str:
    return " ".join(t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _VERBS)


def same_subject(a: str, b: str) -> bool:
    ka, kb = _subject_key(a), _subject_key(b)
    return bool(ka and kb) and fuzz.token_set_ratio(ka, kb) >= 85


def today() -> date:
    return config.AS_OF_DATE


# ---------------------------------------------------------------- conflicts
def detect_conflicts(p: Principal, client_id: str, profile: dict, extractions: list[dict],
                     ledger: list[dict]) -> list[dict]:
    conflicts = []

    # 1. AUM across systems of record and documents
    claims = []
    if profile.get("aum_usd"):
        claims.append(dict(value=profile["aum_usd"], as_of=profile["aum_as_of"], source="CRM account master",
                           ref=f"CRM:{client_id}", rank=1))
    perf = T.get_performance(p, client_id)
    if perf and perf[0].get("client_total_aum_usd"):
        claims.append(dict(value=perf[0]["client_total_aum_usd"], as_of=perf[0]["as_of"],
                           source="Performance system (client-reported)", ref=f"PERF:{client_id}:{perf[0]['period']}",
                           rank=1))
    for e in extractions:
        if e["type"] == "stated_fact" and "aum" in e["subject"].lower() and e.get("value"):
            claims.append(dict(value=e["value"], as_of=e["doc_date"], source=f"{e['doc_type']} {e['doc_id']}",
                               ref=e["doc_id"], rank=2))
    if len(claims) > 1:
        vals = [c["value"] for c in claims]
        if max(vals) / min(vals) - 1 > config.AUM_CONFLICT_TOLERANCE:
            chosen = sorted(claims, key=lambda c: (c["rank"], c["as_of"]), reverse=False)
            structured = [c for c in claims if c["rank"] == 1]
            pick = max(structured or claims, key=lambda c: c["as_of"])
            conflicts.append(dict(
                kind="value_conflict", field="Total AUM",
                claims=[dict(c, display=fmt_usd(c["value"])) for c in sorted(claims, key=lambda c: c["as_of"])],
                resolution=f"Using {fmt_usd(pick['value'])} (most recent system of record, as of {pick['as_of']}). "
                           f"Confirm with the client.",
                chosen=pick["value"], refs=[c["ref"] for c in chosen]))

    # 2. Contact / role changes vs CRM
    contacts = profile.get("contacts", [])
    for e in extractions:
        if e["type"] != "contact_change":
            continue
        import json as _json
        extra = _json.loads(e.get("extra") or "{}")
        person, title, prev = extra.get("person"), extra.get("new_title"), extra.get("previous_holder")
        crm_person = next((c for c in contacts if person and c["name"].lower() == person.lower()), None)
        holder = next((c for c in contacts if title and fuzz.token_set_ratio(c["title"].lower(), title.lower()) > 90
                       and (not person or c["name"].lower() != person.lower())), None)
        stale = (crm_person and title and crm_person["title"].lower() != title.lower()) or holder
        # CRM is the system of record for who holds a role today, so it names the outgoing holder.
        # The document only announces the change, and a model reading it can mistake the person
        # greeted in the opening line for the one being replaced.
        outgoing = holder["name"] if holder else prev
        if stale:
            claims = []
            if holder:
                claims.append(dict(source="CRM contacts", as_of=holder["updated_at"],
                                   display=f"{holder['name']} - {holder['title']}", ref="CRM:contacts"))
            if crm_person:
                claims.append(dict(source="CRM contacts", as_of=crm_person["updated_at"],
                                   display=f"{crm_person['name']} - {crm_person['title']}", ref="CRM:contacts"))
            claims.append(dict(source=f"{e['doc_type']} {e['doc_id']}", as_of=e["doc_date"],
                               display=f"{person} - {title} (effective {e.get('due_date') or 'n/a'})",
                               ref=e["doc_id"]))
            conflicts.append(dict(
                kind="stale_contact", field=f"{title}",
                claims=claims,
                resolution=f"Newer correspondence ({e['doc_date']}) says {person} is {title}"
                           + (f", replacing {outgoing}" if outgoing else "") + ". CRM contact record needs updating.",
                refs=[e["doc_id"]], suggested_action=f"Update CRM: {person} as {title}"))

    # 3. Task status in CRM vs evidence trail
    for item in ledger:
        if item.get("crm_status") == "Open" and item["status"] == "Done":
            conflicts.append(dict(
                kind="status_conflict", field=f"Task '{item['subject']}'",
                claims=[dict(source=f"{item.get('origin', 'CRM')} task " + item["crm_action_id"], as_of=item.get("crm_updated_at"),
                             display="Open", ref="CRM:" + item["crm_action_id"]),
                        dict(source="document " + item["fulfilled_by"], as_of=item.get("fulfilled_on"),
                             display="Delivered", ref=item["fulfilled_by"])],
                resolution="Correspondence shows it was delivered; the tracked task was never closed.",
                refs=[item["fulfilled_by"]], suggested_action=f"Close task {item['crm_action_id']}"))
    return conflicts


# ---------------------------------------------------------------- commitments
def _next_meeting_date(p: Principal, client_id: str) -> str | None:
    """The client's next scheduled meeting, read from the calendar system of record."""
    meeting = T.get_client_profile(p, client_id).get("next_meeting")
    return meeting.get("date") if meeting else None


def build_ledger(p: Principal, client_id: str, extractions: list[dict]) -> list[dict]:
    ledger: list[dict] = []

    def find(subject):
        return next((l for l in ledger if same_subject(l["subject"], subject)), None)

    for e in sorted(extractions, key=lambda x: x["doc_date"]):
        if e["type"] not in ("ask", "commitment", "fulfillment", "concern"):
            continue
        item = find(e["subject"])
        if item is None:
            if e["type"] == "concern":
                continue  # concerns only enrich existing items
            item = dict(subject=e["subject"], requested_by=None, committed_in=None, fulfilled_by=None,
                        fulfilled_on=None, chased_in=[], due_date=None, crm_action_id=None, crm_status=None,
                        crm_updated_at=None, evidence=[], first_seen=e["doc_date"])
            ledger.append(item)
        item["evidence"].append(e["doc_id"])
        if e["type"] == "ask":
            item["requested_by"] = item["requested_by"] or e["doc_id"]
            item["ask_text"] = item.get("ask_text") or e["text"]
        elif e["type"] == "commitment":
            item["committed_in"] = e["doc_id"]
            item["commit_text"] = e["text"]
        elif e["type"] == "fulfillment":
            item["fulfilled_by"], item["fulfilled_on"] = e["doc_id"], e["doc_date"]
        elif e["type"] == "concern":
            item["chased_in"].append(e["doc_id"])
        if e.get("due_date") and e["type"] in ("ask", "commitment"):
            item["due_date"] = min(filter(None, [item["due_date"], e["due_date"]]))

    for a in T.get_actions(p, client_id):
        item = find(a["title"])
        if item is None:
            item = dict(subject=a["title"], requested_by=None, committed_in=None, fulfilled_by=None, fulfilled_on=None,
                        chased_in=[], due_date=a["due_date"], evidence=[], first_seen=a["updated_at"][:10],
                        crm_action_id=None, crm_status=None, crm_updated_at=None)
            ledger.append(item)
        item["crm_action_id"] = a["action_id"]
        item["crm_status"] = a["status"]
        item["crm_updated_at"] = (a["updated_at"] or "")[:10]
        item["origin"] = a["origin"]
        if a["due_date"] and not item["due_date"]:
            item["due_date"] = a["due_date"]
        if a["status"] in ("Done", "Closed") and not item["fulfilled_by"]:
            item["fulfilled_by"], item["fulfilled_on"] = a["action_id"], item["crm_updated_at"]

    # An outstanding ask or commitment carrying no stated deadline is due at the next scheduled
    # meeting: that is when the client expects to discuss it. The date comes from the calendar
    # system of record rather than from the text, because relative references ("Thursday", "after
    # the summer") are exactly what a model resolves unreliably - and in this data set one of them
    # disagrees with the booked date. An explicit deadline always wins over this default.
    meeting = _next_meeting_date(p, client_id)
    if meeting:
        for item in ledger:
            originates_with_us = item["requested_by"] or item["committed_in"]
            if item["due_date"] or item["fulfilled_by"] or not originates_with_us:
                continue
            if item["first_seen"] <= meeting:
                item["due_date"] = meeting
                item["due_at_meeting"] = True

    t = today()
    for item in ledger:
        due = date.fromisoformat(item["due_date"]) if item["due_date"] else None
        if item["fulfilled_by"]:
            status = "Done"
        elif due and due < t:
            status = "Overdue"
        elif due and due <= t + timedelta(days=14):
            status = "Due soon"
        else:
            status = "Open"
        item["status"] = status
        flags = []
        if not item["crm_action_id"] and status != "Done":
            flags.append("Not tracked in CRM")
        if item["crm_status"] == "Open" and status == "Done":
            flags.append("Task still open in " + ("CRM" if item.get("origin", "CRM") == "CRM" else "app"))
        if item["chased_in"] and status != "Done":
            flags.append("Client has chased")
        if item.get("due_at_meeting") and status != "Done":
            flags.append("Due at this meeting")
        item["flags"] = flags
        item["owner_side"] = "firm"
    order = {"Overdue": 0, "Due soon": 1, "Open": 2, "Done": 3}
    ledger.sort(key=lambda i: (order[i["status"]], i["due_date"] or "9999"))
    for n, item in enumerate(ledger, 1):
        item["ledger_id"] = f"L{n}"
    return ledger


# ---------------------------------------------------------------- metrics
def material_metrics(p: Principal, client_id: str, chosen_aum: float | None, profile: dict,
                     materiality=None) -> list[dict]:
    """Metric facts with a deterministic materiality flag and a ready-made sentence.

    The thresholds come from the briefing pack, so a pension board review and a hedge
    fund financing review can draw the line in different places without a code change.
    Falling back to the defaults keeps every existing caller working.
    """
    from .packs import Materiality
    m = materiality or Materiality()
    facts = []
    rev = T.get_revenue(p, client_id)
    if rev:
        periods = sorted({r["period"] for r in rev})
        by = {per: sum(r["revenue_usd"] for r in rev if r["period"] == per) for per in periods}
        last, prev = periods[-1], periods[-2] if len(periods) > 1 else None
        trailing = sum(by[x] for x in periods[-4:])
        facts.append(dict(key="revenue_ttm", source="FinanceDW revenue", as_of=last, material=True,
                          text=f"Trailing four-quarter revenue is {fmt_usd(trailing)} (through {last})."))
        if prev:
            ch = pct(by[last], by[prev])
            lines = []
            for pl in sorted({r["product_line"] for r in rev}):
                a = sum(r["revenue_usd"] for r in rev if r["period"] == last and r["product_line"] == pl)
                b = sum(r["revenue_usd"] for r in rev if r["period"] == prev and r["product_line"] == pl)
                lines.append((pl, a - b, a, b))
            driver = max(lines, key=lambda x: abs(x[1]))
            facts.append(dict(
                key="revenue_qoq", source="FinanceDW revenue", as_of=last, material=abs(ch or 0) >= m.revenue_move_pct,
                text=f"{last} revenue was {fmt_usd(by[last])}, {'+' if ch >= 0 else ''}{ch}% vs {prev} "
                     f"({fmt_usd(by[prev])}); largest move in {driver[0]} ({fmt_usd(driver[3])} to {fmt_usd(driver[2])})."))
    for h in T.get_holdings(p, client_id):
        ch = pct(h["value_usd"], h["prior_value_usd"])
        if ch is None:
            continue
        facts.append(dict(key=f"holding:{h['product']}", source="ProductDW holdings", as_of=h["as_of"],
                          material=abs(ch) >= m.holdings_move_pct,
                          text=f"{h['product']} {h['metric'].lower()} is {fmt_usd(h['value_usd'])}, "
                               f"{'+' if ch >= 0 else ''}{ch}% vs prior period ({fmt_usd(h['prior_value_usd'])})."))
    perf = T.get_performance(p, client_id)
    if perf:
        r = perf[0]
        excess_bps = round((r["return_pct"] - r["benchmark_pct"]) * 100)
        facts.append(dict(key="performance", source="Performance system", as_of=r["as_of"],
                          material=abs(excess_bps) >= m.performance_bps,
                          text=f"{r['portfolio']} returned {r['return_pct']}% in {r['period']} vs benchmark "
                               f"{r['benchmark_pct']}% ({'+' if excess_bps >= 0 else ''}{excess_bps} bps)."))
    if chosen_aum:
        facts.append(dict(key="aum", source="Resolved AUM", as_of=None, material=True,
                          text=f"Total AUM: {fmt_usd(chosen_aum)} (see conflicts for alternative figures)."
                          if chosen_aum != profile.get("aum_usd") else f"Total AUM: {fmt_usd(chosen_aum)} "
                                                                       f"(CRM, as of {profile.get('aum_as_of')})."))
    for tk in T.get_service_issues(p, client_id):
        if tk["status"] == "Open":
            age = (today() - date.fromisoformat(tk["opened_at"])).days
            facts.append(dict(key=f"ticket:{tk['ticket_id']}", source="ServiceDesk", as_of=tk["opened_at"],
                              material=tk["severity"] in ("High", "Medium"),
                              text=f"Open {tk['severity'].lower()}-severity service issue {tk['ticket_id']}: "
                                   f"{tk['summary']} (open {age} days)."))
    return facts


# ---------------------------------------------------------------- change timeline
def change_timeline(p: Principal, client_id: str, since: str | None, extractions: list[dict]) -> list[dict]:
    since = since or "0000"
    events = []
    for e in extractions:
        if e["doc_date"] > since and e["type"] in ("ask", "fulfillment", "contact_change", "update", "concern",
                                                   "interest", "commitment"):
            events.append(dict(date=e["doc_date"], kind=e["type"], ref=e["doc_id"],
                               text=f"{e['text']} ({e['doc_type'].replace('_', ' ')} {e['doc_id']})"))
    for d in T.get_documents(p, client_id, since=since, doc_types=["news"]):
        events.append(dict(date=d["date"], kind="news", ref=d["doc_id"], text=f"News: {d['title']}."))
    for tk in T.get_service_issues(p, client_id):
        if tk["closed_at"] and tk["closed_at"] > since:
            events.append(dict(date=tk["closed_at"], kind="service", ref=tk["ticket_id"],
                               text=f"Service ticket {tk['ticket_id']} closed: {tk['summary']}."))
        elif tk["opened_at"] > since:
            events.append(dict(date=tk["opened_at"], kind="service", ref=tk["ticket_id"],
                               text=f"New service ticket {tk['ticket_id']}: {tk['summary']}."))
    for o in T.get_pipeline(p, client_id):
        if o["updated_at"] > since:
            events.append(dict(date=o["updated_at"], kind="pipeline", ref=o["opp_id"],
                               text=f"Opportunity {o['opp_id']} ({o['product']}) updated; stage {o['stage']}."))
    events.sort(key=lambda x: x["date"])
    return events
