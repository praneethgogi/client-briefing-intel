"""Meeting readiness - triage across the whole calendar, before anyone opens a briefing.

The team does not have one meeting, it has a week of them. The useful question is
not "write me a briefing" but "which of these can I walk into, and which need a
person first". This module answers that, and it answers it in code: no model is
called here, so the triage is repeatable and cheap enough to run on every page load.

Two axes are kept separate on purpose, because they call for different people:

  data     Can the briefing be trusted? Unresolved entities, conflicting values,
           stale or missing sources. These are validation failures, and they route
           to a data steward or analyst - the same routing an extraction platform
           applies on per-field confidence and validation results.

  prep     Is there relationship work outstanding? Overdue commitments, an ask due
           at this meeting, an ask never tracked in CRM. The briefing is sound;
           the relationship needs attention. That routes to the coverage team.

Collapsing the two into one score would tell an RM that a stale address and an
overdue commitment are the same problem. They are not.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..security.entitlements import AccessDenied, Principal
from ..tools import structured as T
from . import analysis as A

# Data-quality kinds that mean the briefing itself may be wrong, with the severity
# at which each one stops being a note and becomes a blocker.
BLOCKING_DQ = {"unresolved_entity"}
DATA_DQ = {"unresolved_entity", "stale_record", "missing_data", "duplicate_record",
           "missing_identifier"}

READY = "Ready"
NEEDS_REVIEW = "Needs review"
BLOCKED = "Blocked"


@dataclass
class Reason:
    axis: str        # "data" | "prep"
    severity: str    # "high" | "medium" | "low"
    text: str

    def as_dict(self) -> dict:
        return dict(axis=self.axis, severity=self.severity, text=self.text)


@dataclass
class MeetingReadiness:
    client_id: str
    client_name: str
    meeting_date: str | None
    purpose: str | None
    state: str
    reasons: list[Reason] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def data_reasons(self) -> list[Reason]:
        return [r for r in self.reasons if r.axis == "data"]

    @property
    def prep_reasons(self) -> list[Reason]:
        return [r for r in self.reasons if r.axis == "prep"]

    def as_dict(self) -> dict:
        return dict(client_id=self.client_id, client_name=self.client_name,
                    meeting_date=self.meeting_date, purpose=self.purpose,
                    state=self.state, counts=self.counts,
                    data=[r.as_dict() for r in self.data_reasons],
                    prep=[r.as_dict() for r in self.prep_reasons])


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


def for_client(p: Principal, client_id: str) -> MeetingReadiness:
    """Readiness for one client. Deterministic: every input is a code decision."""
    profile = T.get_client_profile(p, client_id)
    extractions = T.get_extractions(p, client_id)
    ledger = A.build_ledger(p, client_id, extractions)
    conflicts = A.detect_conflicts(p, client_id, profile, extractions, ledger)
    dq = [d for d in T.get_data_quality(p, client_id) if d.get("kind") in DATA_DQ]

    reasons: list[Reason] = []

    # --- data axis: can we trust what the briefing says? -----------------------
    blocking = [d for d in dq if d.get("kind") in BLOCKING_DQ and d.get("severity") == "high"]
    for d in blocking:
        reasons.append(Reason("data", "high", d.get("detail") or "Record held for review"))

    if conflicts:
        reasons.append(Reason("data", "medium",
                              f"{_plural(len(conflicts), 'conflicting value')} across systems"))

    stale = [d for d in dq if d.get("kind") == "stale_record"]
    if stale:
        reasons.append(Reason("data", "medium", _plural(len(stale), "stale source")))

    missing = [d for d in dq if d.get("kind") in ("missing_data", "missing_identifier")]
    if missing:
        reasons.append(Reason("data", "low", _plural(len(missing), "gap", "gaps") + " in the record"))

    other_unresolved = [d for d in dq if d.get("kind") == "unresolved_entity" and d not in blocking]
    if other_unresolved:
        reasons.append(Reason("data", "low",
                              _plural(len(other_unresolved), "record") + " not matched to a client"))

    # --- prep axis: is there relationship work outstanding? --------------------
    overdue = [l for l in ledger if l["status"] == "Overdue"]
    if overdue:
        reasons.append(Reason("prep", "high", _plural(len(overdue), "overdue commitment")))

    untracked = [l for l in ledger
                 if "Not tracked in CRM" in l.get("flags", []) and l["status"] != "Done"]
    at_meeting = [l for l in ledger if "Due at this meeting" in l.get("flags", [])]

    # An ask falling due at the meeting is the meeting's content, not a defect - as
    # long as somebody is working on it. It only signals a problem when nothing is
    # tracking it, which is how a client ask quietly goes unanswered.
    untracked_at_meeting = [l for l in at_meeting if l in untracked]
    if untracked_at_meeting:
        reasons.append(Reason("prep", "high", _plural(len(untracked_at_meeting), "ask")
                              + " due at this meeting with nothing tracking it"))

    untracked_other = [l for l in untracked if l not in untracked_at_meeting]
    if untracked_other:
        reasons.append(Reason("prep", "medium",
                              _plural(len(untracked_other), "ask") + " not tracked in CRM"))

    chased = [l for l in ledger if "Client has chased" in l.get("flags", [])]
    if chased:
        reasons.append(Reason("prep", "high",
                              _plural(len(chased), "item") + " the client has chased"))

    # A high-severity data issue blocks: the briefing may be wrong about who this
    # client even is. Everything else is a flag, not a stop.
    # Low-severity items are recorded and shown, but they do not move the state: a
    # note is not a task. Only high and medium take a meeting out of Ready, or the
    # queue fills with noise and the team stops reading it.
    if any(r.axis == "data" and r.severity == "high" for r in reasons):
        state = BLOCKED
    elif any(r.severity in ("high", "medium") for r in reasons):
        state = NEEDS_REVIEW
    else:
        state = READY

    meeting = profile.get("next_meeting") or {}
    return MeetingReadiness(
        client_id=client_id,
        client_name=profile.get("legal_name") or client_id,
        meeting_date=meeting.get("date"),
        purpose=meeting.get("purpose"),
        state=state,
        reasons=reasons,
        counts=dict(conflicts=len(conflicts), overdue=len(overdue), due_at_meeting=len(at_meeting),
                    untracked=len(untracked), data_issues=len(dq), open_items=len(
                        [l for l in ledger if l["status"] != "Done"])),
    )


def for_calendar(p: Principal) -> dict:
    """Readiness for every meeting this principal covers, soonest first."""
    rows: list[MeetingReadiness] = []
    for c in T.list_clients(p):
        try:
            rows.append(for_client(p, c["client_id"]))
        except AccessDenied:
            continue  # listed but not readable: leave it out rather than half-report it
    rows.sort(key=lambda r: (r.meeting_date or "9999", r.client_name))
    by_state = {s: sum(1 for r in rows if r.state == s) for s in (READY, NEEDS_REVIEW, BLOCKED)}
    return dict(
        meetings=[r.as_dict() for r in rows],
        total=len(rows),
        by_state=by_state,
        needs_attention=by_state[NEEDS_REVIEW] + by_state[BLOCKED],
    )
