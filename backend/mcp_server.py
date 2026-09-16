"""MCP server exposing the SAME governed tools used by the briefing pipeline.

Run (stdio):   python mcp_server.py
Any MCP client (Claude Desktop, an IDE agent, another LangGraph agent) gets typed tools whose
entitlement checks are identical to the REST API's. Identity: in this demo the caller's user id
comes from the CBI_MCP_USER env var set by whoever launches the server (the MCP host), NOT from a
tool argument - a model must not be able to choose whose permissions it runs with.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from app.briefing import analysis as A
from app.briefing.graph import run_briefing
from app.ingest import pipeline
from app.retrieval.search import search_documents
from app.security.entitlements import AccessDenied, get_principal
from app.tools import structured as T

mcp = FastMCP("client-briefing-intel")
USER = os.getenv("CBI_MCP_USER", "ava.chen")


def _p():
    return get_principal(USER)


def _safe(fn):
    try:
        return fn()
    except AccessDenied as exc:
        return {"error": "access_denied", "detail": str(exc)}
    except T.ToolError as exc:
        return {"error": exc.code, "detail": str(exc)}


@mcp.tool()
def list_my_clients() -> list[dict] | dict:
    """List clients the current user covers, with the next scheduled meeting."""
    return _safe(lambda: T.list_clients(_p()))


@mcp.tool()
def get_client_profile(client_id: str) -> dict:
    """Client master record, aliases, coverage team, contacts, last and next interaction."""
    return _safe(lambda: T.get_client_profile(_p(), client_id))


@mcp.tool()
def get_open_commitments(client_id: str) -> list[dict] | dict:
    """Ledger of client asks and firm commitments with computed status (Open/Due soon/Overdue/Done)."""
    def run():
        p = _p()
        return A.build_ledger(p, client_id, T.get_extractions(p, client_id))
    return _safe(run)


@mcp.tool()
def get_material_metrics(client_id: str) -> list[dict] | dict:
    """Revenue, holdings, performance and service metrics with deterministic materiality flags."""
    def run():
        p = _p()
        prof = T.get_client_profile(p, client_id)
        return A.material_metrics(p, client_id, prof.get("aum_usd"), prof)
    return _safe(run)


@mcp.tool()
def search_client_documents(client_id: str, query: str, k: int = 5) -> list[dict] | dict:
    """Hybrid search over the entitled emails, notes, research and approved news for a client."""
    return _safe(lambda: search_documents(_p(), client_id, query, k=min(max(k, 1), 10)))


@mcp.tool()
def generate_briefing(client_id: str) -> dict:
    """Run the full verified briefing pipeline and return summary, sections and citations."""
    def run():
        b = run_briefing(_p(), client_id)
        return {k: b[k] for k in ("client_name", "executive_summary", "sections", "evidence", "conflicts",
                                  "suggested_actions", "withheld")}
    return _safe(run)


if __name__ == "__main__":
    pipeline.ensure_ready()
    mcp.run()
