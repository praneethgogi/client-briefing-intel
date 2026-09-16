"""Hybrid retrieval (BM25 + embeddings, fused with reciprocal-rank fusion).

Entitlement filtering happens FIRST: the candidate set is only chunks from documents the
principal may read for this purpose. Retrieval can therefore never surface restricted text.
Embeddings are used when an OpenAI key is configured (cached on disk); otherwise BM25 only.
"""
from __future__ import annotations

import json
import math
import re

from rank_bm25 import BM25Okapi

from .. import config, db, llm
from ..security.entitlements import Principal, filter_documents
from ..tools.structured import traced

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "we", "our", "us", "it", "be",
         "with", "by", "as", "at", "this", "that", "any", "all", "what", "which"}


def _tok(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _embed_cached(chunks: list[dict]) -> dict[str, list[float]] | None:
    if not llm.enabled():
        return None
    path = config.CACHE_DIR / "embeddings.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    missing = [c for c in chunks if c["chunk_id"] not in cache]
    if missing:
        try:
            vecs = llm.embed([c["text"] for c in missing])
        except Exception:
            return None
        for c, v in zip(missing, vecs):
            cache[c["chunk_id"]] = v
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    return {c["chunk_id"]: cache[c["chunk_id"]] for c in chunks}


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    return num / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


@traced
def search_documents(principal: Principal, client_id: str, query: str, doc_types: list[str] | None = None,
                     k: int = 5, include_firm_wide: bool = True) -> list[dict]:
    """Search entitled document chunks for a client (plus firm-wide research/news)."""
    principal.require_client(client_id)
    with db.session() as conn:
        sql = "SELECT * FROM documents WHERE (client_id=?" + (" OR client_id IS NULL)" if include_firm_wide else ")")
        params: list = [client_id]
        if doc_types:
            sql += f" AND doc_type IN ({','.join('?' * len(doc_types))})"
            params += doc_types
        docs = filter_documents(principal, db.rows(conn, sql, params))
        if not docs:
            return []
        meta = {d["doc_id"]: d for d in docs}
        chunks = db.rows(conn, f"SELECT * FROM chunks WHERE doc_id IN ({','.join('?' * len(meta))})", list(meta))
    corpus = [_tok(c["text"] + " " + meta[c["doc_id"]]["title"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    q = _tok(query)
    bm_scores = bm25.get_scores(q)
    lexical_hits = [i for i, toks in enumerate(corpus) if set(q) & set(toks)]
    rankings = [sorted(lexical_hits, key=lambda i: -bm_scores[i])]
    vecs = _embed_cached(chunks)
    if vecs is not None:
        try:
            qv = llm.embed([query])[0]
            sem = sorted(range(len(chunks)), key=lambda i: -_cos(qv, vecs[chunks[i]["chunk_id"]]))
            rankings.append(sem[: max(k * 2, 8)])
        except Exception:
            pass
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            fused[i] = fused.get(i, 0) + 1 / (60 + rank)
    out = []
    for i in sorted(fused, key=lambda i: -fused[i])[:k]:
        c, d = chunks[i], meta[chunks[i]["doc_id"]]
        out.append(dict(chunk_id=c["chunk_id"], doc_id=d["doc_id"], title=d["title"], doc_type=d["doc_type"],
                        date=d["date"], source=d["source"], classification=d["classification"],
                        client_scoped=d["client_id"] is not None, text=c["text"], score=round(fused[i], 4)))
    return out
