import json

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.api.main import app
from app.briefing import graph
from app.briefing.verify import verify_bullet
from app.ingest.resolve import Resolver
from app.security.entitlements import AccessDenied, get_principal


def test_entity_resolution_rules():
    r = Resolver([{"client_id": "C1", "legal_name": "Northwind Capital Partners LLC", "lei": "L1"}],
                 [{"client_id": "C1", "alias": "NWCP"}])
    assert r.resolve("NWCP").client_id == "C1"
    assert r.resolve("", lei="L1").client_id == "C1"
    assert r.resolve("Northwind Capitol Partners").status == "matched"
    assert r.resolve("Northwood Capital Group").client_id is None  # near miss is never auto-merged


def test_row_level_access_denied():
    with pytest.raises(AccessDenied):
        graph.run_briefing(get_principal("ben.osei"), "C001")


def test_mnpi_zero_footprint_and_no_leak():
    b = graph.run_briefing(get_principal("ava.chen"), "C001")
    blob = json.dumps(b).lower()
    assert "lighthouse" not in blob and "d-109" not in blob
    assert b["withheld"]["count"] == 0  # MNPI is not even counted


def test_field_level_revenue_withheld_for_analyst():
    b = graph.run_briefing(get_principal("leo.park"), "C001")
    assert b["withheld"]["count"] == 1
    assert "$6.44m" not in json.dumps(b).lower()


def test_verifier_rejects_ungrounded_numbers_and_bad_citations():
    ev = {"KM1": {"text": "Revenue was $1.89M, +18.6% vs prior."}}
    assert verify_bullet({"text": "Revenue up 18.6% to $1.89M", "citations": ["KM1"]}, ev) == []
    assert verify_bullet({"text": "Revenue up 25%", "citations": ["KM1"]}, ev)
    assert verify_bullet({"text": "Revenue up", "citations": ["ZZ9"]}, ev)
    assert verify_bullet({"text": "Revenue up", "citations": []}, ev)


def test_llm_path_uses_verified_output(monkeypatch):
    monkeypatch.setattr(llm, "enabled", lambda: True)

    def fake(system, user, meter=None, temperature=0.0):
        ids = [l.split("]")[0][1:] for l in user.splitlines() if l.startswith("[")]
        if meter:
            meter.calls += 1
        return {"bullets": [{"text": "Grounded point from the evidence.", "citations": ids[:1]}]}

    monkeypatch.setattr(llm, "complete_json", fake)
    b = graph.run_briefing(get_principal("ava.chen"), "C001")
    gens = {s["key"]: s["generation"] for s in b["sections"]}
    assert gens["snapshot"] == "llm" and gens["commitments"] == "deterministic"
    assert b["run_metrics"]["llm"]["calls"] >= 5


def test_llm_hallucination_falls_back_to_deterministic(monkeypatch):
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "complete_json",
                        lambda *a, **k: {"bullets": [{"text": "AUM is $9.9B", "citations": ["CS1"]}]})
    b = graph.run_briefing(get_principal("ava.chen"), "C001")
    snap = next(s for s in b["sections"] if s["key"] == "snapshot")
    assert snap["generation"] == "fallback_after_llm"
    assert all("9.9" not in x["text"] for x in snap["bullets"])
    assert snap["rejected"]


def test_api_flow_actions_and_notes():
    with TestClient(app) as c:
        h = {"X-User-Id": "ava.chen"}
        b = c.post("/api/clients/C001/briefings", headers=h).json()
        assert len(b["sections"]) == 7
        assert any("Securities lending" in a["title"] for a in b["suggested_actions"])
        c.post("/api/actions", headers=h, json={"client_id": "C001",
                                                "title": "Create task: Securities lending revenue estimate"})
        b2 = c.post("/api/clients/C001/briefings", headers=h).json()
        item = next(l for l in b2["ledger"] if l["subject"].startswith("Securities lending"))
        assert "Not tracked in CRM" not in item["flags"]
        n = c.post("/api/clients/C001/notes", headers=h,
                   json={"text": "Priya asked for a liquidity stress test by Oct 15."}).json()
        assert n["items"][0]["type"] == "ask" and n["items"][0]["due_date"] == "2026-10-15"
        assert c.get(f"/api/briefings/{b2['briefing_id']}", headers={"X-User-Id": "leo.park"}).status_code == 403
        assert c.post("/api/clients/C004/briefings", headers={"X-User-Id": "leo.park"}).status_code == 403


def test_every_pack_answers_all_seven_questions():
    """A pack sets emphasis, never coverage.

    The seven questions are the contract with the user. If a pack could quietly drop
    one, the briefing would stop answering part of the brief and the coverage gate
    would still pass, because it only scores the sections that were produced.
    """
    from app.briefing import packs
    from app.briefing.sections import SECTIONS

    all_keys = {s.key for s in SECTIONS}
    for pack in packs.all_packs():
        assert set(pack.order) == all_keys, f"pack '{pack.id}' does not cover all sections"
        assert set(pack.lead) <= all_keys, f"pack '{pack.id}' leads with an unknown section"

    with pytest.raises(packs.PackError):
        packs._coerce_keys("broken", "order", ["snapshot", "changes"], complete=True)
    with pytest.raises(packs.PackError):
        packs._coerce_keys("broken", "order", ["snapshot", "not_a_section"], complete=False)


def test_pack_selection_falls_back_and_sets_thresholds():
    from app.briefing import packs

    assert packs.select("Hedge Fund", "Quarterly review").id == "hedge_fund_review"
    # Meeting purpose is more specific than segment, so it wins for a pension fee review.
    assert packs.select("Public Pension", "Fee and custody review").id == "fee_and_custody"
    # Anything unrecognised still gets a briefing, on the default pack.
    fallback = packs.select("Sovereign Wealth", "Annual catch-up")
    assert fallback.id == packs.default_pack().id
    assert fallback.materiality.performance_bps == 25


def test_assignment_cannot_widen_access():
    """Handing work to a teammate is a workflow action, never a grant.

    If an assignment could name someone outside the coverage list, 'please look at
    this' becomes a way around the entitlement model.
    """
    with TestClient(app) as c:
        ava = {"X-User-Id": "ava.chen"}
        eligible = c.get("/api/clients/C001/assignees", headers=ava).json()
        names = {e["user_id"] for e in eligible}
        assert "leo.park" in names          # covers C001
        assert "ben.osei" not in names      # does not
        assert "ava.chen" not in names      # never yourself

        ok = c.post("/api/assignments", headers=ava, json={
            "client_id": "C001", "axis": "data", "text": "Northwood held for review",
            "assign_to": "leo.park"}).json()
        assert ok["status"] == "Open"

        denied = c.post("/api/assignments", headers=ava, json={
            "client_id": "C001", "axis": "data", "text": "should never land",
            "assign_to": "ben.osei"})
        assert denied.status_code == 403

        # The assignee sees it; someone who cannot see the client never does.
        mine = c.get("/api/assignments?mine=true", headers={"X-User-Id": "leo.park"}).json()
        assert any(a["assignment_id"] == ok["assignment_id"] for a in mine)
        assert c.get("/api/assignments", headers={"X-User-Id": "ben.osei"}).json() == []

        done = c.post(f"/api/assignments/{ok['assignment_id']}/resolve",
                      headers={"X-User-Id": "leo.park"}, json={"note": "Separate firm."}).json()
        assert done["status"] == "Resolved"
