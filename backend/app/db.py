"""SQLite canonical store (a stand-in for the governed data platform)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, legal_name TEXT, lei TEXT, segment TEXT,
    domicile TEXT, tier TEXT, aum_usd REAL, aum_as_of TEXT, crm_updated_at TEXT);
CREATE TABLE IF NOT EXISTS aliases (client_id TEXT, alias TEXT);
CREATE TABLE IF NOT EXISTS crosswalk (source TEXT, source_record TEXT, source_value TEXT, client_id TEXT,
    method TEXT, score REAL, status TEXT);
CREATE TABLE IF NOT EXISTS contacts (contact_key TEXT PRIMARY KEY, client_id TEXT, name TEXT, title TEXT, email TEXT,
    updated_at TEXT, sources TEXT);
CREATE TABLE IF NOT EXISTS coverage (client_id TEXT, user_id TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS revenue (client_id TEXT, period TEXT, product_line TEXT, revenue_usd REAL);
CREATE TABLE IF NOT EXISTS holdings (client_id TEXT, product TEXT, metric TEXT, value_usd REAL, prior_value_usd REAL, as_of TEXT);
CREATE TABLE IF NOT EXISTS performance (client_id TEXT, portfolio TEXT, period TEXT, return_pct REAL,
    benchmark_pct REAL, client_total_aum_usd REAL, as_of TEXT);
CREATE TABLE IF NOT EXISTS pipeline (opp_id TEXT PRIMARY KEY, client_id TEXT, product TEXT, stage TEXT,
    est_annual_revenue_usd REAL, owner TEXT, updated_at TEXT, next_step TEXT);
CREATE TABLE IF NOT EXISTS service_tickets (ticket_id TEXT PRIMARY KEY, client_id TEXT, summary TEXT, severity TEXT,
    status TEXT, opened_at TEXT, closed_at TEXT);
CREATE TABLE IF NOT EXISTS crm_actions (action_id TEXT PRIMARY KEY, client_id TEXT, title TEXT, owner TEXT,
    due_date TEXT, status TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS interactions (client_id TEXT, date TEXT, type TEXT, subject TEXT);
CREATE TABLE IF NOT EXISTS meetings (client_id TEXT, date TEXT, purpose TEXT);
CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, client_id TEXT, client_ref TEXT, doc_type TEXT,
    date TEXT, author TEXT, source TEXT, classification TEXT, title TEXT, body TEXT, content_hash TEXT);
CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, doc_id TEXT, seq INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS extractions (item_id TEXT PRIMARY KEY, doc_id TEXT, client_id TEXT, type TEXT, actor TEXT,
    subject TEXT, text TEXT, due_date TEXT, value REAL, extra TEXT, extractor TEXT);
CREATE TABLE IF NOT EXISTS dq_issues (issue_id TEXT PRIMARY KEY, client_id TEXT, kind TEXT, severity TEXT,
    detail TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS lineage (dataset TEXT, source_system TEXT, source_file TEXT, rows INTEGER,
    max_as_of TEXT, loaded_at TEXT, content_hash TEXT);
CREATE TABLE IF NOT EXISTS briefings (briefing_id TEXT PRIMARY KEY, client_id TEXT, user_id TEXT, created_at TEXT,
    status TEXT, approved_by TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS app_actions (action_id TEXT PRIMARY KEY, client_id TEXT, title TEXT, owner TEXT,
    due_date TEXT, status TEXT, created_by TEXT, created_at TEXT, origin TEXT);
CREATE TABLE IF NOT EXISTS audit_log (ts TEXT, user_id TEXT, event TEXT, client_id TEXT, detail TEXT);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
