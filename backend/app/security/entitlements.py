"""Identity propagation + row / document entitlements.

The Principal is resolved once per request (in production: from the SSO/OIDC token) and
passed explicitly into every tool. Filtering happens in the tool layer, BEFORE any text
can reach retrieval or an LLM prompt. Access = identity x purpose:
  * row level   - you only see clients you cover
  * field level - revenue is 'confidential' (senior coverage only)
  * document    - classification must be in your clearances AND allowed for the purpose
  * information barrier - MNPI is never usable for a sales briefing, even for wall-crossed
    users, and is suppressed with zero footprint (not even counted).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import db

PERSONAS: dict[str, dict] = {
    "ava.chen": dict(display="Ava Chen", role="Senior Relationship Manager",
                     clearances={"public", "internal", "confidential"}, all_clients=False),
    "leo.park": dict(display="Leo Park", role="Coverage Analyst",
                     clearances={"public", "internal"}, all_clients=False),
    "ben.osei": dict(display="Ben Osei", role="Relationship Manager (Foundations)",
                     clearances={"public", "internal", "confidential"}, all_clients=False),
    "sam.rivera": dict(display="Sam Rivera", role="Compliance Officer (supervisory review)",
                       clearances={"public", "internal", "confidential", "legal_restricted"}, all_clients=True),
}

# What each purpose may ever use, regardless of the user's clearances.
PURPOSE_ALLOWED = {
    "client_briefing": {"public", "internal", "confidential", "legal_restricted"},
}
ZERO_FOOTPRINT = {"mnpi"}  # information-barrier material: never counted, never hinted at
FIELD_CLASSIFICATION = {"revenue": "confidential"}


class AccessDenied(PermissionError):
    pass


@dataclass
class Principal:
    user_id: str
    display: str
    role: str
    clearances: set[str]
    covered_clients: set[str]
    all_clients: bool = False
    purpose: str = "client_briefing"
    withheld: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)

    def can_see_client(self, client_id: str) -> bool:
        return self.all_clients or client_id in self.covered_clients

    def require_client(self, client_id: str) -> None:
        if not self.can_see_client(client_id):
            raise AccessDenied(f"{self.user_id} does not cover client {client_id}")

    def can_read(self, classification: str) -> bool:
        return classification in self.clearances and classification in PURPOSE_ALLOWED[self.purpose]

    def note_withheld(self, kind: str, ref: str, classification: str) -> None:
        if classification in ZERO_FOOTPRINT:
            return
        if not any(w["ref"] == ref for w in self.withheld):
            self.withheld.append(dict(kind=kind, ref=ref, reason=f"{classification} - not permitted for your role"))

    def public_view(self) -> dict:
        return dict(user_id=self.user_id, display=self.display, role=self.role,
                    clearances=sorted(self.clearances), covered_clients=sorted(self.covered_clients),
                    all_clients=self.all_clients, purpose=self.purpose)


def get_principal(user_id: str, purpose: str = "client_briefing") -> Principal:
    p = PERSONAS.get(user_id)
    if p is None:
        raise AccessDenied(f"unknown user {user_id}")
    with db.session() as conn:
        covered = {r["client_id"] for r in db.rows(conn, "SELECT client_id FROM coverage WHERE user_id=?", (user_id,))}
    return Principal(user_id=user_id, display=p["display"], role=p["role"], clearances=set(p["clearances"]),
                     covered_clients=covered, all_clients=p["all_clients"], purpose=purpose)


def filter_documents(principal: Principal, docs: list[dict]) -> list[dict]:
    allowed = []
    for d in docs:
        if principal.can_read(d["classification"]):
            allowed.append(d)
        else:
            principal.note_withheld("document", d["doc_id"], d["classification"])
    return allowed
