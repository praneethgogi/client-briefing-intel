"""Entity resolution: map any source reference (ID, LEI, legal name, alias, typo) to a canonical client.

Deterministic and explainable on purpose - no LLM. Order of evidence:
  1. exact client_id           -> auto (score 100)
  2. LEI match                 -> auto (score 100)
  3. exact normalised name/alias
  4. fuzzy name/alias match    -> auto if >= ER_AUTO_MATCH, steward review if >= ER_REVIEW_MATCH
  5. otherwise unresolved      -> quarantined, never guessed
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .. import config

_SUFFIXES = {"llc", "inc", "ltd", "lp", "plc", "the", "co", "corp"}
_ABBREV = {"ptnrs": "partners", "cap": "capital", "fdn": "foundation", "fo": "family office",
           "trs": "teachers retirement system"}


def normalise(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    out = []
    for t in tokens:
        if t in _SUFFIXES:
            continue
        out.append(_ABBREV.get(t, t))
    return " ".join(out)


@dataclass
class Match:
    client_id: str | None
    method: str
    score: float
    status: str  # matched | review | unresolved
    candidate: str | None = None


class Resolver:
    def __init__(self, clients: list[dict], aliases: list[dict]):
        self.ids = {c["client_id"] for c in clients}
        self.lei = {c["lei"]: c["client_id"] for c in clients if c.get("lei")}
        self.names: list[tuple[str, str]] = []  # (normalised name, client_id)
        for c in clients:
            self.names.append((normalise(c["legal_name"]), c["client_id"]))
        for a in aliases:
            self.names.append((normalise(a["alias"]), a["client_id"]))

    def resolve(self, ref: str | None, lei: str | None = None) -> Match:
        ref = (ref or "").strip()
        if ref in self.ids:
            return Match(ref, "client_id", 100, "matched")
        if lei and lei in self.lei:
            return Match(self.lei[lei], "lei", 100, "matched")
        if not ref:
            return Match(None, "none", 0, "unresolved")
        norm = normalise(ref)
        for n, cid in self.names:
            if n == norm:
                return Match(cid, "alias_exact", 100, "matched")
        best_score, best_cid = 0.0, None
        for n, cid in self.names:
            # token_sort guards against "Northwood Capital Group" ~ "Northwind Capital"
            s = min(fuzz.token_sort_ratio(norm, n), fuzz.WRatio(norm, n))
            if s > best_score:
                best_score, best_cid = s, cid
        if best_score >= config.ER_AUTO_MATCH:
            return Match(best_cid, "fuzzy", round(best_score, 1), "matched")
        if best_score >= config.ER_REVIEW_MATCH:
            return Match(None, "fuzzy", round(best_score, 1), "review", candidate=best_cid)
        return Match(None, "fuzzy", round(best_score, 1), "unresolved", candidate=best_cid)
