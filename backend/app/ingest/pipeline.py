"""Ingestion: raw sources -> resolved, quality-checked canonical store with lineage.

Run:  python -m app.ingest.pipeline            (uses extraction cache / offline replay)
      python -m app.ingest.pipeline --reextract (force fresh LLM extraction)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date, datetime

from .. import config, db
from ..datagen import generate
from .extract import extract_documents
from .resolve import Resolver

SOURCE_SYSTEM = {
    "crm_accounts": "CRM", "aliases": "MDM", "contacts": "CRM+MarketingHub", "coverage": "CRM",
    "revenue": "FinanceDW", "holdings": "ProductDW", "performance": "PerformanceSys", "pipeline": "CRM",
    "service_tickets": "ServiceDesk", "crm_actions": "CRM", "interactions": "CRM", "meetings": "Calendar",
}
AS_OF_FIELD = {"crm_accounts": "updated_at", "contacts": "updated_at", "holdings": "as_of", "performance": "as_of",
               "pipeline": "updated_at", "service_tickets": "opened_at", "crm_actions": "updated_at",
               "interactions": "date", "meetings": "date", "revenue": "period"}


def _read(name: str) -> tuple[list[dict], str]:
    path = config.RAW_DIR / f"{name}.csv"
    text = path.read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines())), hashlib.sha256(text.encode()).hexdigest()[:12]


def _num(v):
    return float(v) if v not in (None, "") else None


def _parse_doc(path) -> dict:
    raw = path.read_text(encoding="utf-8")
    _, head, body = raw.split("---", 2)
    meta = {}
    for line in head.strip().splitlines():
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    meta["body"] = body.strip()
    return meta


def _days_old(iso: str) -> int:
    return (config.AS_OF_DATE - date.fromisoformat(iso)).days


def run(reextract: bool = False, regenerate: bool = True, verbose: bool = True) -> dict:
    if regenerate or not (config.RAW_DIR / "crm_accounts.csv").exists():
        generate()
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    now = datetime.now().isoformat(timespec="seconds")
    report: dict = {"datasets": {}, "dq_issues": 0}
    issues: list[dict] = []

    def issue(client_id, kind, severity, detail, source):
        issues.append(dict(issue_id=f"DQ-{len(issues) + 1:03d}", client_id=client_id, kind=kind,
                           severity=severity, detail=detail, source=source))

    with db.session() as conn:
        data, hashes = {}, {}
        for name in SOURCE_SYSTEM:
            data[name], hashes[name] = _read(name)

        # 1. Client master: rows with IDs are golden records; others go through resolution.
        masters = [r for r in data["crm_accounts"] if r["client_id"]]
        resolver = Resolver(masters, data["aliases"])
        for r in masters:
            conn.execute("INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?)",
                         (r["client_id"], r["legal_name"], r["lei"] or None, r["segment"], r["domicile"], r["tier"],
                          _num(r["aum_usd"]), r["aum_as_of"] or None, r["updated_at"]))
            conn.execute("INSERT INTO crosswalk VALUES (?,?,?,?,?,?,?)",
                         ("CRM", r["record_id"], r["legal_name"], r["client_id"], "client_id", 100, "matched"))
            if not r["lei"]:
                issue(r["client_id"], "missing_identifier", "low", "No LEI on client master record", "CRM")
            if _days_old(r["updated_at"]) > config.STALE_DAYS:
                issue(r["client_id"], "stale_record", "medium",
                      f"CRM account last updated {r['updated_at']} ({_days_old(r['updated_at'])} days ago)", "CRM")
        for a in data["aliases"]:
            conn.execute("INSERT INTO aliases VALUES (?,?)", (a["client_id"], a["alias"]))
        for r in data["crm_accounts"]:
            if r["client_id"]:
                continue
            m = resolver.resolve(r["legal_name"], r["lei"])
            conn.execute("INSERT INTO crosswalk VALUES (?,?,?,?,?,?,?)",
                         ("CRM", r["record_id"], r["legal_name"], m.client_id, m.method, m.score, m.status))
            issue(m.client_id, "duplicate_record", "medium",
                  f"Account record {r['record_id']} ('{r['legal_name']}') has no client ID; merged into "
                  f"{m.client_id} via {m.method}", "CRM")

        # 2. Contacts from two systems: resolve company, then de-duplicate by email (latest wins).
        merged: dict[str, dict] = {}
        for c in data["contacts"]:
            m = resolver.resolve(c["client_ref"])
            conn.execute("INSERT INTO crosswalk VALUES (?,?,?,?,?,?,?)",
                         (c["source"], c["contact_id"], c["client_ref"], m.client_id, m.method, m.score, m.status))
            if m.status != "matched":
                issue(m.candidate, "unresolved_entity", "high" if m.status == "review" else "low",
                      f"Contact {c['name']} references '{c['client_ref']}' - {m.status} "
                      f"(best candidate {m.candidate}, score {m.score}); held for data-steward review, not merged",
                      c["source"])
                continue
            key = c["email"].lower()
            prev = merged.get(key)
            if prev is None:
                merged[key] = dict(c, client_id=m.client_id, sources={c["source"]})
            else:
                prev["sources"].add(c["source"])
                if c["updated_at"] > prev["updated_at"]:
                    prev.update(title=c["title"], updated_at=c["updated_at"])
                issue(m.client_id, "duplicate_record", "low",
                      f"Contact {c['name']} present in {sorted(prev['sources'])}; merged on email", c["source"])
        for key, c in merged.items():
            conn.execute("INSERT INTO contacts VALUES (?,?,?,?,?,?,?)",
                         (key, c["client_id"], c["name"], c["title"], c["email"], c["updated_at"],
                          ",".join(sorted(c["sources"]))))

        # 3. Straight-through structured tables.
        simple = {
            "coverage": ("INSERT INTO coverage VALUES (?,?,?)", lambda r: (r["client_id"], r["user_id"], r["role"])),
            "revenue": ("INSERT INTO revenue VALUES (?,?,?,?)",
                        lambda r: (r["client_id"], r["period"], r["product_line"], _num(r["revenue_usd"]))),
            "holdings": ("INSERT INTO holdings VALUES (?,?,?,?,?,?)",
                         lambda r: (r["client_id"], r["product"], r["metric"], _num(r["value_usd"]),
                                    _num(r["prior_value_usd"]), r["as_of"])),
            "performance": ("INSERT INTO performance VALUES (?,?,?,?,?,?,?)",
                            lambda r: (r["client_id"], r["portfolio"], r["period"], _num(r["return_pct"]),
                                       _num(r["benchmark_pct"]), _num(r["client_total_aum_usd"]), r["as_of"])),
            "pipeline": ("INSERT INTO pipeline VALUES (?,?,?,?,?,?,?,?)",
                         lambda r: (r["opp_id"], r["client_id"], r["product"], r["stage"],
                                    _num(r["est_annual_revenue_usd"]), r["owner"], r["updated_at"], r["next_step"])),
            "service_tickets": ("INSERT INTO service_tickets VALUES (?,?,?,?,?,?,?)",
                                lambda r: (r["ticket_id"], r["client_id"], r["summary"], r["severity"], r["status"],
                                           r["opened_at"], r["closed_at"] or None)),
            "crm_actions": ("INSERT INTO crm_actions VALUES (?,?,?,?,?,?,?)",
                            lambda r: (r["action_id"], r["client_id"], r["title"], r["owner"], r["due_date"],
                                       r["status"], r["updated_at"])),
            "interactions": ("INSERT INTO interactions VALUES (?,?,?,?)",
                             lambda r: (r["client_id"], r["date"], r["type"], r["subject"])),
            "meetings": ("INSERT INTO meetings VALUES (?,?,?)", lambda r: (r["client_id"], r["date"], r["purpose"])),
        }
        for name, (sql, fn) in simple.items():
            conn.executemany(sql, [fn(r) for r in data[name]])
        for p in data["pipeline"]:
            if p["stage"] not in ("Won", "Lost") and _days_old(p["updated_at"]) > config.STALE_DAYS:
                issue(p["client_id"], "stale_record", "medium",
                      f"Opportunity {p['opp_id']} ({p['product']}) not updated since {p['updated_at']}", "CRM")
        perf_clients = {p["client_id"] for p in data["performance"]}
        for r in masters:
            if r["client_id"] not in perf_clients:
                issue(r["client_id"], "missing_data", "medium", "No performance data on file for this client",
                      "PerformanceSys")

        # 4. Documents: resolve client, chunk, extract.
        docs = []
        for path in sorted(config.DOCS_DIR.glob("*.md")):
            d = _parse_doc(path)
            m = resolver.resolve(d["client_ref"])
            d["client_id"] = m.client_id
            if d["client_ref"] and m.status != "matched":
                issue(m.candidate, "unresolved_entity", "medium",
                      f"Document {d['doc_id']} references '{d['client_ref']}' ({m.status})", d["source"])
            conn.execute("INSERT INTO crosswalk VALUES (?,?,?,?,?,?,?)",
                         (d["source"], d["doc_id"], d["client_ref"], m.client_id, m.method, m.score,
                          m.status if d["client_ref"] else "firm_wide"))
            h = hashlib.sha256(d["body"].encode()).hexdigest()[:12]
            conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (d["doc_id"], d["client_id"], d["client_ref"], d["doc_type"], d["date"], d["author"],
                          d["source"], d["classification"], d["title"], d["body"], h))
            for i, para in enumerate(p for p in d["body"].split("\n\n") if p.strip()):
                conn.execute("INSERT INTO chunks VALUES (?,?,?,?)", (f"{d['doc_id']}#{i}", d["doc_id"], i, para.strip()))
            docs.append(d)

        extracted, ext_stats = extract_documents(docs, force_llm=reextract)
        by_id = {d["doc_id"]: d for d in docs}
        for doc_id, items in extracted.items():
            for n, it in enumerate(items):
                extra = {k: it.get(k) for k in ("person", "new_title", "previous_holder") if it.get(k)}
                conn.execute("INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (f"{doc_id}:X{n + 1}", doc_id, by_id[doc_id]["client_id"], it["type"], it["actor"],
                              it["subject"], it["text"], it.get("due_date"), it.get("value"), json.dumps(extra),
                              "llm" if ext_stats["llm"] or ext_stats["cache"] else "replay"))

        conn.executemany("INSERT INTO dq_issues VALUES (?,?,?,?,?,?)",
                         [(i["issue_id"], i["client_id"], i["kind"], i["severity"], i["detail"], i["source"])
                          for i in issues])

        # 5. Lineage + freshness per dataset.
        for name, rows_ in data.items():
            f = AS_OF_FIELD.get(name)
            max_as_of = max((r[f] for r in rows_ if r.get(f)), default=None) if f else None
            conn.execute("INSERT INTO lineage VALUES (?,?,?,?,?,?,?)",
                         (name, SOURCE_SYSTEM[name], f"raw/{name}.csv", len(rows_), max_as_of, now, hashes[name]))
            report["datasets"][name] = len(rows_)
        conn.execute("INSERT INTO lineage VALUES (?,?,?,?,?,?,?)",
                     ("documents", "Email/Notes/News/Research", "raw/docs/*.md", len(docs),
                      max(d["date"] for d in docs), now, ""))
        report["datasets"]["documents"] = len(docs)
        report["dq_issues"] = len(issues)
        report["extraction"] = ext_stats
    if verbose:
        print(json.dumps(report, indent=2))
    return report


def ensure_ready() -> None:
    """Build the store on first start."""
    if not config.DB_PATH.exists():
        run(regenerate=True, verbose=False)
        return
    with db.session() as conn:
        n = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    if n == 0:
        run(regenerate=True, verbose=False)


if __name__ == "__main__":
    run(reextract="--reextract" in sys.argv)
