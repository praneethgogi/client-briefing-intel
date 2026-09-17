"""Briefing sections. Each section = one of the assignment's seven questions.

A section spec declares:
  gather(ctx)  -> evidence pack (ids + text + source + as_of) and structured data for the UI
  use_llm      -> whether an LLM may phrase the bullets (False = pure code)
  fallback     -> deterministic bullets used offline or when LLM output fails verification
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from .. import config
from ..retrieval.search import search_documents
from ..tools import structured as T
from .analysis import fmt_usd


@dataclass
class Ctx:
    principal: object
    client_id: str
    profile: dict
    extractions: list[dict]
    ledger: list[dict]
    conflicts: list[dict]
    metrics: list[dict]
    timeline: list[dict]
    chosen_aum: float | None
    since: str | None
    sources: list | None = None
    pack: object | None = None   # the BriefingPack in force; set in prepare()


class Pack:
    def __init__(self, prefix: str):
        self.prefix, self.items = prefix, {}

    def add(self, text: str, source: str, ref: str, as_of: str | None = None, kind: str = "fact") -> str:
        eid = f"{self.prefix}{len(self.items) + 1}"
        self.items[eid] = dict(id=eid, text=text, source=source, ref=ref, as_of=as_of, kind=kind)
        return eid


def _b(text: str, *cites: str) -> dict:
    return dict(text=text, citations=[c for c in cites if c])


# ------------------------------------------------------------------ 1. snapshot
def gather_snapshot(ctx: Ctx) -> dict:
    p, pr = Pack("CS"), ctx.profile
    cov = ", ".join(f"{c['user_id']} ({c['role']})" for c in pr["coverage"])
    e_prof = p.add(f"{pr['legal_name']} is a Tier {pr['tier'] or '?'} {pr['segment']} client domiciled in "
                   f"{pr['domicile']}. Coverage: {cov}.", "CRM account master", f"CRM:{ctx.client_id}",
                   pr["crm_updated_at"])
    e_aum = p.add(f"Total AUM {fmt_usd(ctx.chosen_aum)}" + (" (figures conflict across sources)"
                                                             if any(c['field'] == 'Total AUM' for c in ctx.conflicts)
                                                             else ""), "Resolved AUM", "AUM") if ctx.chosen_aum else None
    change = next((c for c in ctx.conflicts if c["kind"] == "stale_contact"), None)
    contact_ids = []
    for c in pr["contacts"]:
        contact_ids.append(p.add(f"CRM contact: {c['name']}, {c['title']} (record updated {c['updated_at']}).",
                                 "CRM contacts", "CRM:contacts", c["updated_at"]))
    e_change = None
    if change:
        latest = change["claims"][-1]
        e_change = p.add(f"Leadership change: {change['resolution']}", latest["source"], latest["ref"], latest["as_of"])
    interest_ids = [p.add(e["text"], f"{e['doc_type']} {e['doc_id']}", e["doc_id"], e["doc_date"])
                    for e in ctx.extractions if e["type"] in ("interest", "concern")][-5:]
    m_ids = [p.add(m["text"], m["source"], m["key"], m["as_of"]) for m in ctx.metrics
             if m["key"] in ("revenue_ttm",) or m["key"].startswith("holding:")][:3]

    fb = [_b(f"{pr['legal_name']}: Tier {pr['tier']} {pr['segment']}" +
             (f" with total AUM of {fmt_usd(ctx.chosen_aum)}." if ctx.chosen_aum else "."), e_prof, e_aum)]
    if e_change:
        fb.append(_b(ctx.conflicts[[c['kind'] for c in ctx.conflicts].index('stale_contact')]["resolution"]
                     .replace(" CRM contact record needs updating.", " (CRM not yet updated)."), e_change))
    elif contact_ids:
        fb.append(_b("Key contacts: " + "; ".join(f"{c['name']} ({c['title']})" for c in pr["contacts"][:3]) + ".",
                     *contact_ids[:3]))
    if interest_ids:
        fb.append(_b("What matters to them: " + " ".join(p.items[i]["text"] for i in interest_ids[-3:]),
                     *interest_ids[-3:]))
    return dict(pack=p, data=dict(profile={k: pr[k] for k in ("client_id", "legal_name", "segment", "tier",
                                                                "domicile", "lei", "aliases", "coverage", "contacts")}),
                fallback=fb, guidance="Summarise who the client is, who we deal with now (note any leadership "
                                      "change), relationship scale, and the 2-3 themes that matter most to them. "
                                      "Max 4 bullets.")


# ------------------------------------------------------------------ 2. what changed
_KIND_RANK = {"contact_change": 0, "ask": 1, "fulfillment": 2, "update": 3, "news": 4, "service": 5,
              "concern": 6, "pipeline": 7, "interest": 8, "commitment": 9}


def gather_changes(ctx: Ctx) -> dict:
    p = Pack("WC")
    li = ctx.profile.get("last_interaction")
    ids = []
    for ev in ctx.timeline:
        ids.append((ev, p.add(f"{ev['date']}: {ev['text']}", ev["kind"], ev["ref"], ev["date"])))
    ranked = sorted(ids, key=lambda x: (_KIND_RANK.get(x[0]["kind"], 9), x[0]["date"]))
    fb = []
    for ev, eid in ranked[:5]:
        fb.append(_b(p.items[eid]["text"], eid))
    if not ids:
        fb.append(_b(f"No recorded changes since the last interaction on {li['date'] if li else 'n/a'}.",
                     p.add(f"Last interaction: {li['date'] if li else 'none on file'}", "CRM interactions", "CRM")))
    return dict(pack=p, data=dict(since=ctx.since, last_interaction=li, timeline=ctx.timeline), fallback=fb,
                guidance=f"What changed since the last interaction ({ctx.since})? Prioritise leadership changes, new "
                         f"client asks, delivered items, service fixes and material news. Max 5 bullets, newest "
                         f"relevance first.")


# ------------------------------------------------------------------ 3. commitments (no LLM)
def gather_commitments(ctx: Ctx) -> dict:
    p, fb = Pack("CM"), []
    for item in ctx.ledger:
        who = "Client asked" if item.get("requested_by") else "We committed"
        due = f", due {item['due_date']}" if item["due_date"] else ""
        flags = f" [{'; '.join(item['flags'])}]" if item["flags"] else ""
        text = f"{item['subject']}: {item['status']}{due}{flags}."
        src_ref = item.get("fulfilled_by") or item.get("committed_in") or item.get("requested_by") or item.get("crm_action_id")
        eid = p.add(f"{who}: {item.get('ask_text') or item.get('commit_text') or item['subject']} "
                    f"Status {item['status']}{due}{flags}.", "Commitment ledger", src_ref or "ledger",
                    item.get("fulfilled_on") or item["first_seen"])
        fb.append(_b(text, eid))
    if not ctx.ledger:
        fb.append(_b("No open asks or commitments found in CRM or correspondence.",
                     p.add("Ledger empty", "Commitment ledger", "ledger")))
    return dict(pack=p, data=dict(ledger=ctx.ledger), fallback=fb, guidance="")


# ------------------------------------------------------------------ 4. metrics (no LLM)
def gather_metrics(ctx: Ctx) -> dict:
    p, fb = Pack("KM"), []
    for m in ctx.metrics:
        eid = p.add(m["text"], m["source"], m["key"], m["as_of"])
        m["evidence_id"] = eid
        if m["material"]:
            fb.append(_b(m["text"], eid))
    if not ctx.metrics:
        fb.append(_b("No metrics available for this client.", p.add("No metric data", "Data platform", "none")))
    return dict(pack=p, data=dict(metrics=ctx.metrics), fallback=fb, guidance="")


# ------------------------------------------------------------------ 5. opportunities
_STAGE_W = {"Proposal": 3, "Qualification": 2, "Discovery": 2, "Idea": 1}
_GENERIC = {"fund", "ii", "opportunities", "management", "overlay", "restructure", "the", "and"}
# keyword groups: a signal supports an opportunity only if it hits every group (max 2) of the product name
_SYNONYMS = {"fx": {"fx", "eur", "usd", "currency"}, "hedging": {"hedging", "hedge", "forward"},
             "transition": {"transition", "allocation"}, "alternative": {"alternative", "alternatives"}}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def _words(text: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z]+", text.lower())}


def _kw(product: str) -> list[set[str]]:
    groups = []
    for t in re.findall(r"[a-z]+", product.lower()):
        if t in _GENERIC or len(t) < 2:
            continue
        t = _stem(t)
        groups.append({_stem(x) for x in _SYNONYMS.get(t, {t})})
    return groups


def _supports(groups: list[set[str]], text: str) -> bool:
    words = _words(text)
    hits = sum(1 for g in groups if g & words)
    return hits >= min(2, len(groups)) and hits > 0


def gather_opportunities(ctx: Ctx) -> dict:
    p, pr, fb, opps = Pack("OP"), ctx.principal, [], []
    pipeline = T.get_pipeline(pr, ctx.client_id)
    signals = []
    for e in ctx.extractions:
        if e["type"] in ("ask", "interest", "concern", "stated_fact") and e["doc_date"] >= "2026-01-01":
            signals.append(dict(text=e["text"], source=f"{e['doc_type']} {e['doc_id']}", ref=e["doc_id"],
                                as_of=e["doc_date"], kind=e["type"]))
    for m in ctx.metrics:
        if m["key"].startswith("holding:") and m["material"]:
            signals.append(dict(text=m["text"], source=m["source"], ref=m["key"], as_of=m["as_of"], kind="holding"))
    for opp in pipeline:
        kws = _kw(opp["product"])
        docs = search_documents(pr, ctx.client_id, opp["product"], doc_types=["research_update", "news"], k=3)
        rev = fmt_usd(opp["est_annual_revenue_usd"]) if opp["est_annual_revenue_usd"] is not None else "withheld"
        stale = f"; not updated in {opp['days_since_update']} days" if opp["stale"] else ""
        e_opp = p.add(f"Pipeline {opp['opp_id']}: {opp['product']} - stage {opp['stage']}, est. annual revenue "
                      f"{rev}, next step: {opp['next_step']}{stale}.", "CRM pipeline", opp["opp_id"], opp["updated_at"])
        sup = []
        for s in signals:
            if _supports(kws, s["text"]):
                sup.append(p.add(s["text"], s["source"], s["ref"], s["as_of"], kind="signal"))
        for d in docs:
            if _supports(kws, d["title"] + " " + d["text"]):
                sup.append(p.add(f"{d['title']}: {d['text']}", f"{d['doc_type']} {d['doc_id']}", d["doc_id"],
                                 d["date"], kind="signal"))
        sup = list(dict.fromkeys(sup))
        score = _STAGE_W.get(opp["stage"], 1) + len(sup) - (2 if opp["stale"] else 0)
        opps.append(dict(opp, evidence_id=e_opp, support=sup, score=score))
    opps.sort(key=lambda o: -o["score"])
    for o in opps:
        why = " ".join(p.items[s]["text"].split(". ")[0].rstrip(".") + "." for s in o["support"][:3])
        stale = " Pipeline record is stale - refresh before presenting." if o["stale"] else ""
        rev = f", est. {fmt_usd(o['est_annual_revenue_usd'])}/yr" if o["est_annual_revenue_usd"] is not None else ""
        fb.append(_b(f"{o['product']} ({o['stage']}{rev}). Evidence: {why or 'no supporting signal found'}{stale}",
                     o["evidence_id"], *o["support"][:3]))
    if not opps:
        fb.append(_b("No pipeline opportunities on file.", p.add("Pipeline empty", "CRM pipeline", "pipeline")))
    return dict(pack=p, data=dict(opportunities=opps), fallback=fb,
                guidance="Recommend which opportunities to raise, in priority order, each with the specific evidence "
                         "that supports it (client asks, holdings trends, research, news). Flag stale pipeline "
                         "records. Max 4 bullets.")


# ------------------------------------------------------------------ 6. news
def gather_news(ctx: Ctx) -> dict:
    p, pr = Pack("NW"), ctx.principal
    cutoff = (config.AS_OF_DATE - timedelta(days=60)).isoformat()
    themes = " ".join(e["subject"] for e in ctx.extractions if e["type"] in ("interest", "ask"))
    query = f"{ctx.profile['legal_name']} {themes} rates FX allocation"
    hits = [h for h in search_documents(pr, ctx.client_id, query, doc_types=["news"], k=6) if h["date"] >= cutoff]
    items, fb = [], []
    for h in sorted(hits, key=lambda h: (not h["client_scoped"], h["date"]), reverse=False):
        eid = p.add(f"{h['title']} ({h['date']}): {h['text']}", f"Approved news feed {h['doc_id']}", h["doc_id"],
                    h["date"], kind="news")
        items.append(dict(h, evidence_id=eid))
        fb.append(_b(f"{h['title']} ({h['date']}). " + h["text"].split(". ")[0].rstrip(".") + ".", eid))
    ctx_ids = [p.add(m["text"], m["source"], m["key"], m["as_of"], kind="context")
               for m in ctx.metrics if m["material"] and m["key"].startswith("holding:")][:2]
    if not items:
        fb.append(_b(f"No approved news items for this client since {cutoff}.",
                     p.add(f"No approved news items since {cutoff}", "Approved news feed", "news")))
    return dict(pack=p, data=dict(news=items, window_start=cutoff, context_ids=ctx_ids), fallback=fb,
                guidance="For each approved news item, say in one bullet what happened and why it matters for "
                         "this conversation, linking it to the client's exposures or asks where the evidence "
                         "supports it. Max 3 bullets.")


# ------------------------------------------------------------------ 7. uncertainty (no LLM)
def gather_uncertainty(ctx: Ctx) -> dict:
    p, fb = Pack("UN"), []
    for c in ctx.conflicts:
        claims = "; ".join(f"{cl['source']} ({cl.get('as_of') or 'n/a'}): {cl['display']}" for cl in c["claims"])
        eid = p.add(f"Conflict on {c['field']}: {claims}. {c['resolution']}", "Conflict detector",
                    ",".join(c["refs"]), kind="conflict")
        fb.append(_b(f"Conflict - {c['field']}: {c['resolution']}", eid))
    dq = T.get_data_quality(ctx.principal, ctx.client_id)
    for i in dq:
        eid = p.add(f"Data quality ({i['kind']}, {i['severity']}): {i['detail']}", f"DQ check {i['source']}",
                    i["issue_id"], kind="dq")
        if i["severity"] in ("medium", "high"):
            fb.append(_b(f"Data quality - {i['detail']}.", eid))
    if not fb:
        fb.append(_b("No conflicting figures or material data-quality issues detected for this client.",
                     p.add("Conflict detector and DQ checks returned no material findings", "Conflict detector",
                           "checks", kind="check")))
    return dict(pack=p, data=dict(conflicts=ctx.conflicts, data_quality=dq), fallback=fb, guidance="")


@dataclass
class SectionSpec:
    key: str
    title: str
    question: str
    gather: Callable[[Ctx], dict]
    use_llm: bool


SECTIONS: list[SectionSpec] = [
    SectionSpec("snapshot", "Client snapshot", "Who is the client and what matters in the relationship?",
                gather_snapshot, True),
    SectionSpec("changes", "What changed", "What changed since the last interaction?", gather_changes, True),
    SectionSpec("commitments", "Asks & commitments",
                "What did the client ask, say or commit, and what remains open?", gather_commitments, False),
    SectionSpec("metrics", "Material metrics", "Which metrics or performance are material?", gather_metrics, False),
    SectionSpec("opportunities", "Opportunities to discuss",
                "Which opportunities should the team discuss, and what evidence supports them?",
                gather_opportunities, True),
    SectionSpec("news", "News & events", "Which recent news or events should shape the conversation?",
                gather_news, True),
    SectionSpec("uncertainty", "Uncertain, conflicting or unavailable",
                "What is uncertain, conflicting or unavailable?", gather_uncertainty, False),
]
SECTION_BY_KEY = {s.key: s for s in SECTIONS}
