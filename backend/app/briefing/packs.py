"""Briefing packs: which questions lead, in what order, and where the lines sit.

Named BriefingPack to keep it distinct from sections.Pack, which is the
evidence pack handed to a prompt - a different thing entirely.

The engine is one piece of code. A hedge fund quarterly review, a pension board
review and a fee complaint are the same seven questions asked with different
emphasis and different thresholds - which is configuration, not a code fork. A new
desk or meeting type should be a YAML entry and a review, not a release.

Every pack answers all seven questions. A pack sets emphasis and thresholds; it
never drops coverage, because coverage is the contract with the user.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .sections import SECTION_BY_KEY, SECTIONS

PACKS_FILE = Path(__file__).with_name("packs.yaml")
ALL_KEYS = [s.key for s in SECTIONS]


class PackError(ValueError):
    """The pack file is wrong. Raised at load time, not halfway through a briefing."""


@dataclass(frozen=True)
class Materiality:
    revenue_move_pct: float = 10.0
    holdings_move_pct: float = 10.0
    performance_bps: float = 25.0

    def as_dict(self) -> dict:
        return dict(revenue_move_pct=self.revenue_move_pct,
                    holdings_move_pct=self.holdings_move_pct,
                    performance_bps=self.performance_bps)


@dataclass(frozen=True)
class BriefingPack:
    id: str
    label: str
    focus: str
    lead: tuple[str, ...]
    order: tuple[str, ...]
    materiality: Materiality
    segments: tuple[str, ...] = ()
    purpose_matches: tuple[str, ...] = ()

    def matches(self, segment: str | None, purpose: str | None) -> bool:
        if self.segments and (segment or "") in self.segments:
            return True
        if self.purpose_matches and purpose:
            low = purpose.lower()
            return any(m.lower() in low for m in self.purpose_matches)
        return False

    def as_dict(self) -> dict:
        return dict(id=self.id, label=self.label, focus=self.focus, lead=list(self.lead),
                    order=list(self.order), materiality=self.materiality.as_dict())


def _coerce_keys(pack_id: str, field_name: str, values, *, complete: bool) -> tuple[str, ...]:
    keys = tuple(values or ())
    unknown = [k for k in keys if k not in SECTION_BY_KEY]
    if unknown:
        raise PackError(f"pack '{pack_id}' {field_name} references unknown section(s): "
                        f"{', '.join(unknown)}. Known: {', '.join(ALL_KEYS)}")
    if len(set(keys)) != len(keys):
        raise PackError(f"pack '{pack_id}' {field_name} repeats a section")
    if complete:
        missing = [k for k in ALL_KEYS if k not in keys]
        if missing:
            # Every pack answers all seven questions. Silently dropping one would mean
            # the briefing quietly stops answering part of the brief.
            raise PackError(f"pack '{pack_id}' order omits section(s): {', '.join(missing)}. "
                            "A pack sets emphasis, not coverage.")
    return keys


@functools.lru_cache(maxsize=1)
def _load() -> tuple[dict[str, BriefingPack], str]:
    raw = yaml.safe_load(PACKS_FILE.read_text(encoding="utf-8")) or {}
    packs: dict[str, BriefingPack] = {}
    for entry in raw.get("packs", []):
        pid = entry.get("id")
        if not pid:
            raise PackError("a pack is missing its id")
        when = entry.get("when") or {}
        packs[pid] = BriefingPack(
            id=pid,
            label=entry.get("label", pid),
            focus=(entry.get("focus") or "").strip(),
            lead=_coerce_keys(pid, "lead", entry.get("lead"), complete=False),
            order=_coerce_keys(pid, "order", entry.get("order"), complete=True),
            materiality=Materiality(**(entry.get("materiality") or {})),
            segments=tuple(when.get("segments") or ()),
            purpose_matches=tuple(when.get("purpose_matches") or ()),
        )
    if not packs:
        raise PackError("no packs defined")
    default_id = raw.get("default") or next(iter(packs))
    if default_id not in packs:
        raise PackError(f"default pack '{default_id}' is not defined")
    return packs, default_id


def all_packs() -> list[BriefingPack]:
    packs, _ = _load()
    return list(packs.values())


def default_pack() -> BriefingPack:
    packs, default_id = _load()
    return packs[default_id]


def select(segment: str | None, purpose: str | None) -> BriefingPack:
    """First pack whose `when` matches, else the default. Order in the file is priority."""
    packs, default_id = _load()
    for pack in packs.values():
        if pack.id == default_id:
            continue
        if pack.matches(segment, purpose):
            return pack
    return packs[default_id]


def for_profile(profile: dict) -> BriefingPack:
    meeting = profile.get("next_meeting") or {}
    return select(profile.get("segment"), meeting.get("purpose"))
