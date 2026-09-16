"""Evaluation harness - "prove it is safe to run".

    python -m evals.run_evals              # uses LLM if OPENAI_API_KEY is set, else offline
    python -m evals.run_evals --offline    # deterministic plumbing only (what CI runs)

Writes evals/results/latest.json and evals/results/latest.md and exits non-zero if any
threshold in evals/thresholds.json is breached (used as a CI gate).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CBI_DB_PATH", str(RESULTS / "eval.db"))
if "--offline" in sys.argv:
    os.environ["LLM_MODE"] = "offline"
sys.path.insert(0, str(ROOT / "backend"))

from app import config, llm  # noqa: E402
from app.briefing.analysis import same_subject  # noqa: E402
from app.briefing.graph import run_briefing  # noqa: E402
from app.briefing.verify import verify_bullet  # noqa: E402
from app.ingest import pipeline  # noqa: E402
from app.ingest.extract import LLM_ALLOWED_CLASSIFICATIONS, extract_with_llm  # noqa: E402
from app.retrieval.search import search_documents  # noqa: E402
from app import db  # noqa: E402
from app.security.entitlements import AccessDenied, get_principal  # noqa: E402
from app.service import resolve_preview  # noqa: E402

GOLD = json.loads((ROOT / "evals" / "golden" / "expectations.json").read_text(encoding="utf-8"))
GOLD_EX = json.loads((ROOT / "evals" / "golden" / "extractions.json").read_text(encoding="utf-8"))
THRESHOLDS = json.loads((ROOT / "evals" / "thresholds.json").read_text(encoding="utf-8"))


def _ratio(ok: int, total: int) -> float:
    return round(ok / total, 4) if total else 1.0


def eval_briefings(details: list) -> dict:
    m = dict(leak=0, cite_ok=0, cite_total=0, num_ok=0, num_total=0, cov_ok=0, cov_total=0, mc_ok=0, mc_total=0,
             conf_ok=0, conf_total=0, led_ok=0, led_total=0, wh_ok=0, wh_total=0, lat=[], tokens=0, llm_calls=0,
             rejected=0)
    for case in GOLD["cases"]:
        p = get_principal(case["user"])
        t0 = time.perf_counter()
        b = run_briefing(p, case["client"])
        m["lat"].append((time.perf_counter() - t0) * 1000)
        m["tokens"] += b["run_metrics"]["llm"]["prompt_tokens"] + b["run_metrics"]["llm"]["completion_tokens"]
        m["llm_calls"] += b["run_metrics"]["llm"]["calls"]
        full = json.dumps({k: v for k, v in b.items() if k != "trace"}).lower()
        bullets = b["executive_summary"]["bullets"] + [x for s in b["sections"] for x in s["bullets"]]
        visible = " ".join(x["text"] for x in bullets).lower() + " " + \
            " ".join(e["text"] for e in b["evidence"].values()).lower()
        problems = []
        for s in case["must_not_contain"]:
            if s.lower() in full:
                m["leak"] += 1
                problems.append(f"LEAK: '{s}' present")
        for s in case["must_contain"]:
            m["mc_total"] += 1
            if s.lower() in visible:
                m["mc_ok"] += 1
            else:
                problems.append(f"missing expected content '{s}'")
        for x in bullets:
            m["cite_total"] += 1
            if x["citations"] and all(c in b["evidence"] for c in x["citations"]):
                m["cite_ok"] += 1
            else:
                problems.append(f"bad citation: {x['text'][:60]}")
            m["num_total"] += 1
            if not [pr for pr in verify_bullet(x, b["evidence"]) if pr.startswith("ungrounded number")]:
                m["num_ok"] += 1
            else:
                problems.append(f"ungrounded number: {x['text'][:60]}")
        # Count the executive summary too. It is verified like any other bullet but is not in
        # b["sections"], so counting only sections reported zero rejections while the summary was
        # failing verification and silently falling back to deterministic text.
        m["rejected"] += sum(len(s["rejected"]) for s in b["sections"])
        m["rejected"] += len(b["executive_summary"]["rejected"])
        for s in b["sections"]:
            m["cov_total"] += 1
            m["cov_ok"] += int(bool(s["bullets"]))
        fields = " | ".join(c["field"] for c in b["conflicts"]).lower()
        for f in case["expected_conflicts"]:
            m["conf_total"] += 1
            if f.lower() in fields:
                m["conf_ok"] += 1
            else:
                problems.append(f"conflict not detected: {f}")
        for subj, status in case["expected_ledger"].items():
            m["led_total"] += 1
            item = next((l for l in b["ledger"] if same_subject(l["subject"], subj)), None)
            if item and item["status"] == status:
                m["led_ok"] += 1
            else:
                problems.append(f"ledger {subj}: expected {status}, got {item and item['status']}")
        for subj, flag in case.get("expected_flags", {}).items():
            m["led_total"] += 1
            item = next((l for l in b["ledger"] if same_subject(l["subject"], subj)), None)
            if item and flag in item["flags"]:
                m["led_ok"] += 1
            else:
                problems.append(f"ledger flag missing {subj}: {flag}")
        m["wh_total"] += 1
        m["wh_ok"] += int(b["withheld"]["count"] == case["expected_withheld"])
        rev_visible = any(mm["key"].startswith("revenue") for mm in
                          next(s for s in b["sections"] if s["key"] == "metrics")["data"]["metrics"])
        rev_ok = case["revenue_visible"] is None or rev_visible == case["revenue_visible"]
        if case["revenue_visible"] is not None:
            m["wh_total"] += 1
            m["wh_ok"] += int(rev_ok)
        if b["withheld"]["count"] != case["expected_withheld"] or not rev_ok:
            problems.append("entitlement outcome mismatch")
        details.append(dict(case=case["id"], problems=problems, generation={s["key"]: s["generation"]
                                                                            for s in b["sections"]},
                            latency_ms=round(m["lat"][-1], 1)))
    return m


def eval_access() -> tuple[float, list]:
    ok, notes = 0, []
    for c in GOLD["access_denied"]:
        try:
            run_briefing(get_principal(c["user"]), c["client"])
            notes.append(f"{c['user']} was able to brief {c['client']}")
        except AccessDenied:
            ok += 1
    return _ratio(ok, len(GOLD["access_denied"])), notes


def eval_er() -> tuple[float, list]:
    ok, notes = 0, []
    for ref, expected in GOLD["entity_resolution"].items():
        got = resolve_preview(ref)["client_id"]
        if got == expected:
            ok += 1
        else:
            notes.append(f"{ref}: expected {expected}, got {got}")
    return _ratio(ok, len(GOLD["entity_resolution"])), notes


def eval_retrieval() -> tuple[float, int, list]:
    hits = total = leaks = 0
    notes = []
    for r in GOLD["retrieval"]:
        res = search_documents(get_principal(r["user"]), r["client"], r["query"], k=5)
        ids = [x["doc_id"] for x in res]
        if "expect_doc" in r:
            total += 1
            if r["expect_doc"] in ids:
                hits += 1
            else:
                notes.append(f"'{r['query']}' missed {r['expect_doc']} (got {ids})")
        if "forbid_doc" in r and r["forbid_doc"] in ids:
            leaks += 1
            notes.append(f"LEAK: '{r['query']}' returned {r['forbid_doc']}")
    return _ratio(hits, total), leaks, notes


def eval_extraction() -> dict:
    with db.session() as conn:
        docs = db.rows(conn, "SELECT * FROM documents")
    if not llm.enabled():
        return dict(mode="replay (golden labels; run with OPENAI_API_KEY to measure the model)", f1=1.0,
                    precision=1.0, recall=1.0, injection_items=0, notes=[])
    tp = fp = fn = 0
    injection_items = 0
    notes = []
    meter = llm.Meter()
    for d in docs:
        if d["classification"] not in LLM_ALLOWED_CLASSIFICATIONS or d["doc_id"] not in GOLD_EX:
            continue
        pred = [i.model_dump() for i in extract_with_llm(d, meter)]
        gold = list(GOLD_EX[d["doc_id"]])
        if d["doc_id"] == "D-112":
            injection_items = len(pred)
        matched = set()
        for pi in pred:
            j = next((k for k, g in enumerate(gold) if k not in matched and g["type"] == pi["type"]
                      and same_subject(g["subject"], pi["subject"])), None)
            if j is None:
                fp += 1
                notes.append(f"{d['doc_id']} extra: {pi['type']} / {pi['subject']}")
            else:
                matched.add(j)
                tp += 1
        for k, g in enumerate(gold):
            if k not in matched:
                fn += 1
                notes.append(f"{d['doc_id']} missed: {g['type']} / {g['subject']}")
    prec, rec = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0
    return dict(mode=f"llm ({config.OPENAI_MODEL})", f1=f1, precision=prec, recall=rec,
                injection_items=injection_items, notes=notes[:30], llm=meter.as_dict())


def main() -> int:
    t_start = time.perf_counter()
    pipeline.run(regenerate=True, verbose=False)
    details: list = []
    b = eval_briefings(details)
    acc, acc_notes = eval_access()
    er, er_notes = eval_er()
    ret, ret_leaks, ret_notes = eval_retrieval()
    ex = eval_extraction()
    metrics = {
        "leakage_violations": b["leak"] + ret_leaks,
        "access_control_pass_rate": acc,
        "citation_validity": _ratio(b["cite_ok"], b["cite_total"]),
        "numeric_faithfulness": _ratio(b["num_ok"], b["num_total"]),
        "question_coverage": _ratio(b["cov_ok"], b["cov_total"]),
        "must_contain_recall": _ratio(b["mc_ok"], b["mc_total"]),
        "conflict_recall": _ratio(b["conf_ok"], b["conf_total"]),
        "ledger_status_accuracy": _ratio(b["led_ok"], b["led_total"]),
        "withheld_accuracy": _ratio(b["wh_ok"], b["wh_total"]),
        "entity_resolution_accuracy": er,
        "retrieval_hit_rate_at_5": ret,
        "extraction_f1": ex["f1"],
        "injection_extraction_items": ex["injection_items"],
    }
    gates = {}
    for k, rule in THRESHOLDS.items():
        v = metrics[k]
        passed = (v >= rule["min"]) if "min" in rule else (v <= rule["max"])
        gates[k] = dict(value=v, rule=rule, passed=passed)
    lat = b["lat"]
    result = dict(
        run_at=time.strftime("%Y-%m-%d %H:%M:%S"), llm_mode=llm.mode(),
        model=config.OPENAI_MODEL if llm.enabled() else None,
        passed=all(g["passed"] for g in gates.values()), gates=gates,
        operational=dict(briefings=len(lat), latency_p50_ms=round(statistics.median(lat), 1),
                         latency_max_ms=round(max(lat), 1), llm_calls=b["llm_calls"], llm_tokens=b["tokens"],
                         verifier_rejections=b["rejected"], total_runtime_s=round(time.perf_counter() - t_start, 1)),
        extraction=ex, cases=details,
        notes=dict(access=acc_notes, entity_resolution=er_notes, retrieval=ret_notes),
    )
    (RESULTS / "latest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    md = [f"# Eval run {result['run_at']} - {'PASS' if result['passed'] else 'FAIL'}",
          f"LLM mode: {result['llm_mode']} {result['model'] or ''}", "", "| Metric | Value | Gate | Result |",
          "|---|---|---|---|"]
    for k, g in gates.items():
        rule = f">= {g['rule']['min']}" if "min" in g["rule"] else f"<= {g['rule']['max']}"
        md.append(f"| {k} | {g['value']} | {rule} | {'PASS' if g['passed'] else 'FAIL'} |")
    md += ["", "## Operational", *[f"- {k}: {v}" for k, v in result["operational"].items()], "",
           "## Case findings"]
    for d in details:
        md.append(f"- **{d['case']}**: {'; '.join(d['problems']) or 'no issues'}")
    (RESULTS / "latest.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
