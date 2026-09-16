"""Verifier: every generated bullet must be grounded.

Checks per bullet:
  1. has >= 1 citation
  2. every citation id exists in the evidence pack given to the model
  3. every number in the bullet appears (within tolerance) in the cited evidence
  4. no restricted / injected content markers
Failing bullets are dropped (and reported), never shown silently.
"""
from __future__ import annotations

import re

_UNITS = {"b": 1e9, "bn": 1e9, "billion": 1e9, "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
          "k": 1e3, "thousand": 1e3}
_MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b", r"\b\d{4}-q[1-4]\b", r"\bq[1-4]\s*\d{4}\b", r"\bq[1-4]\b",
    rf"\b{_MONTHS}\s+\d{{1,2}}(st|nd|rd|th)?(,\s*\d{{4}})?\b", rf"\b\d{{1,2}}\s+{_MONTHS}\b",
    r"\b(19|20)\d{2}\b", r"\b[A-Z]{1,4}-\d+\b", r"\b[ACDEFLOPT]{1,3}-?\d+(#\d+)?\b",
]
_NUM = re.compile(r"(?<![\w.])([-+]?\$?\d[\d,]*(?:\.\d+)?)\s*(bn|billion|million|thousand|mm|mn|b|m|k|%|bps)?(?![\w])",
                  re.IGNORECASE)
FORBIDDEN_MARKERS = ["inside information", "project lighthouse", "wall-crossed", "system override",
                     "ignore all previous instructions", "complaint regarding trade allocation"]


def _strip_ids_and_dates(text: str) -> str:
    out = text
    for pat in _DATE_PATTERNS:
        out = re.sub(pat, " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\[[A-Z]{2}\d+\]", " ", out)
    return out


def numbers(text: str) -> list[tuple[float, str]]:
    vals = []
    for m in _NUM.finditer(_strip_ids_and_dates(text)):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        try:
            v = float(raw.replace("$", "").replace(",", "").replace("+", ""))
        except ValueError:
            continue
        kind = "pct" if unit in ("%",) else "bps" if unit == "bps" else "num"
        v *= _UNITS.get(unit, 1)
        vals.append((v, kind))
    return vals


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    return abs(a - b) <= 0.015 * max(abs(a), abs(b))


def verify_bullet(bullet: dict, evidence: dict[str, dict]) -> list[str]:
    problems = []
    cites = bullet.get("citations") or []
    if not cites:
        problems.append("no citation")
    missing = [c for c in cites if c not in evidence]
    if missing:
        problems.append(f"unknown citation(s) {missing}")
    text = bullet.get("text", "")
    low = text.lower()
    for mk in FORBIDDEN_MARKERS:
        if mk in low:
            problems.append(f"forbidden content '{mk}'")
    cited_text = " ".join(evidence[c]["text"] for c in cites if c in evidence)
    ev_nums = numbers(cited_text)
    for v, kind in numbers(text):
        if kind == "num" and abs(v) < 10 and float(v).is_integer():
            continue  # small counts ("two tickets") are not treated as material figures
        if not any(_close(abs(v), abs(e)) for e, k in ev_nums if k == kind):
            problems.append(f"ungrounded number {v:g}")
    return problems


def verify_bullets(bullets: list[dict], evidence: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    ok, rejected = [], []
    for b in bullets:
        probs = verify_bullet(b, evidence)
        if probs:
            rejected.append(dict(b, problems=probs))
        else:
            ok.append(b)
    return ok, rejected
