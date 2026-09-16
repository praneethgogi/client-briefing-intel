"""Typed, entitlement-aware tools. The same functions back the LangGraph pipeline,
the REST API and the MCP server - one governed contract, many callers.

Every tool:
  * takes the Principal explicitly (identity propagation)
  * enforces row/field/document entitlements before returning anything
  * returns plain JSON-serialisable data with source + as_of for lineage
  * is traced (name, args, rows, ms) via the `traced` decorator
"""
from __future__ import annotations

import contextvars
import functools
import time

from .. import config, db
from ..security.entitlements import FIELD_CLASSIFICATION, Principal, filter_documents

_trace: contextvars.ContextVar[list | None] = contextvars.ContextVar("tool_trace", default=None)


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def start_trace() -> list:
    t: list = []
    _trace.set(t)
    return t


def traced(fn):
    @functools.wraps(fn)
    def wrapper(principal: Principal, *args, **kwargs):
        t0 = time.perf_counter()
        status, n = "ok", None
        try:
            out = fn(principal, *args, **kwargs)
            n = len(out) if isinstance(out, list) else None
            return out
        except Exception as exc:
            status = f"error:{type(exc).__name__}"
            raise
        finally:
            tr = getattr(principal, "trace", None)
            if tr is None:
                tr = _trace.get()
            if tr is not None:
                tr.append(dict(kind="tool", name=fn.__name__, args=[str(a) for a in args] +
                               [f"{k}={v}" for k, v in kwargs.items()], rows=n, status=status,
                               ms=round((time.perf_counter() - t0) * 1000, 2), user=principal.user_id))
    return wrapper


def _q(sql: str, params=()):
    with db.session() as conn:
        return db.rows(conn, sql, params)


@traced
def list_clients(principal: Principal) -> list[dict]:
    """Clients the caller is entitled to, with the next scheduled meeting."""
    out = []
    for c in _q("SELECT c.client_id, c.legal_name, c.segment, c.tier, m.date AS next_meeting, m.purpose "
                "FROM clients c LEFT JOIN meetings m ON m.client_id=c.client_id ORDER BY m.date"):
        if principal.can_see_client(c["client_id"]):
            out.append(c)
    return out


@traced
def get_client_profile(principal: Principal, client_id: str) -> dict:
    """Master record, aliases, coverage team, contacts, last interaction and next meeting."""
    principal.require_client(client_id)
    rows = _q("SELECT * FROM clients WHERE client_id=?", (client_id,))
    if not rows:
        raise ToolError("not_found", f"client {client_id} not found")
    c = rows[0]
    c["aliases"] = [r["alias"] for r in _q("SELECT alias FROM aliases WHERE client_id=?", (client_id,))]
    c["coverage"] = _q("SELECT user_id, role FROM coverage WHERE client_id=?", (client_id,))
    c["contacts"] = _q("SELECT name, title, email, updated_at, sources FROM contacts WHERE client_id=?", (client_id,))
    li = _q("SELECT * FROM interactions WHERE client_id=? AND date<=? ORDER BY date DESC LIMIT 1",
            (client_id, config.AS_OF_DATE.isoformat()))
    c["last_interaction"] = li[0] if li else None
    nm = _q("SELECT * FROM meetings WHERE client_id=? AND date>=? ORDER BY date LIMIT 1",
            (client_id, config.AS_OF_DATE.isoformat()))
    c["next_meeting"] = nm[0] if nm else None
    c["source"] = "CRM"
    return c


@traced
def get_revenue(principal: Principal, client_id: str) -> list[dict]:
    """Quarterly revenue by product line (confidential field)."""
    principal.require_client(client_id)
    cls = FIELD_CLASSIFICATION["revenue"]
    if not principal.can_read(cls):
        principal.note_withheld("dataset", "revenue", cls)
        return []
    return _q("SELECT period, product_line, revenue_usd FROM revenue WHERE client_id=? ORDER BY period", (client_id,))


@traced
def get_holdings(principal: Principal, client_id: str) -> list[dict]:
    """Product holdings / usage with prior-period comparison."""
    principal.require_client(client_id)
    return _q("SELECT product, metric, value_usd, prior_value_usd, as_of FROM holdings WHERE client_id=?", (client_id,))


@traced
def get_performance(principal: Principal, client_id: str) -> list[dict]:
    """Mandate performance vs benchmark and client-reported total AUM."""
    principal.require_client(client_id)
    return _q("SELECT * FROM performance WHERE client_id=? ORDER BY as_of DESC", (client_id,))


@traced
def get_pipeline(principal: Principal, client_id: str) -> list[dict]:
    """Open opportunities with stage, owner, estimated revenue and staleness."""
    principal.require_client(client_id)
    rows = _q("SELECT * FROM pipeline WHERE client_id=? ORDER BY est_annual_revenue_usd DESC", (client_id,))
    for r in rows:
        from datetime import date
        r["days_since_update"] = (config.AS_OF_DATE - date.fromisoformat(r["updated_at"])).days
        r["stale"] = r["days_since_update"] > config.STALE_DAYS
        if not principal.can_read(FIELD_CLASSIFICATION["revenue"]):
            r["est_annual_revenue_usd"] = None
    return rows


@traced
def get_service_issues(principal: Principal, client_id: str) -> list[dict]:
    """Service tickets (open and recently closed)."""
    principal.require_client(client_id)
    return _q("SELECT * FROM service_tickets WHERE client_id=? ORDER BY opened_at DESC", (client_id,))


@traced
def get_actions(principal: Principal, client_id: str) -> list[dict]:
    """CRM tasks plus actions created in this app."""
    principal.require_client(client_id)
    crm = _q("SELECT action_id, title, owner, due_date, status, updated_at, 'CRM' AS origin FROM crm_actions "
             "WHERE client_id=?", (client_id,))
    app = _q("SELECT action_id, title, owner, due_date, status, created_at AS updated_at, origin FROM app_actions "
             "WHERE client_id=?", (client_id,))
    return crm + app


@traced
def get_documents(principal: Principal, client_id: str | None, since: str | None = None,
                  doc_types: list[str] | None = None, include_firm_wide: bool = False) -> list[dict]:
    """Document metadata + body, entitlement-filtered."""
    if client_id:
        principal.require_client(client_id)
    sql = "SELECT * FROM documents WHERE (client_id=?"
    params: list = [client_id]
    sql += " OR client_id IS NULL)" if include_firm_wide else ")"
    if since:
        sql += " AND date>?"
        params.append(since)
    if doc_types:
        sql += f" AND doc_type IN ({','.join('?' * len(doc_types))})"
        params += doc_types
    return filter_documents(principal, _q(sql + " ORDER BY date DESC", params))


@traced
def get_extractions(principal: Principal, client_id: str, types: list[str] | None = None) -> list[dict]:
    """LLM-extracted asks/commitments/changes. Inherit the source document's classification."""
    principal.require_client(client_id)
    sql = ("SELECT e.*, d.date AS doc_date, d.doc_type, d.title AS doc_title, d.classification, d.doc_id "
           "FROM extractions e JOIN documents d ON d.doc_id=e.doc_id WHERE e.client_id=?")
    params: list = [client_id]
    if types:
        sql += f" AND e.type IN ({','.join('?' * len(types))})"
        params += types
    rows = _q(sql + " ORDER BY d.date", params)
    out = []
    for r in rows:
        if principal.can_read(r["classification"]):
            out.append(r)
        else:
            principal.note_withheld("document", r["doc_id"], r["classification"])
    return out


@traced
def get_data_quality(principal: Principal, client_id: str) -> list[dict]:
    """Data-quality issues raised at ingestion for this client."""
    principal.require_client(client_id)
    return _q("SELECT * FROM dq_issues WHERE client_id=?", (client_id,))


@traced
def get_lineage(principal: Principal) -> list[dict]:
    """Dataset lineage and freshness."""
    return _q("SELECT * FROM lineage")
