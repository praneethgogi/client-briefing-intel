# Design notes

How the parts actually work: the two ingestion paths, retrieval, generation, the
verifier, and what each of the thirteen evaluation gates measures. File references are
to real code — if something here disagrees with the code, the code is right.

---

## 1. Two ingestion paths, one canonical store

Structured and unstructured data are handled completely differently, and deliberately so.
Structured data is already typed and trustworthy in shape; the hard part is deciding
*which client it belongs to*. Unstructured data has no shape at all; the hard part is
turning prose into rows without inventing anything.

Both land in one SQLite store (`backend/app/db.py`) standing in for a governed lakehouse.

### 1a. Structured: 12 sources → resolve → canonical rows → lineage

`backend/app/ingest/pipeline.py`

```
crm_accounts, aliases, contacts, coverage, revenue, holdings, performance,
pipeline, service_tickets, crm_actions, interactions, meetings
```

Each row arrives keyed by whatever the source system used — a `client_id`, an LEI, a
legal name, an alias, or a typo. **Entity resolution is the first thing that happens**,
because every downstream access decision depends on getting it right.

`backend/app/ingest/resolve.py` — a fixed ladder, no model involved:

| Rung | Match on | Score | Outcome |
|---|---|---|---|
| 1 | `client_id` | 100 | auto-merge |
| 2 | LEI | 100 | auto-merge — this is what recovers `MIG-77`, a migration record with no client_id |
| 3 | Exact normalised name or alias | 100 | auto-merge — `"NWCP"`, `"Evergreen TRS"` |
| 4 | Fuzzy ≥ `ER_AUTO_MATCH` (90) | e.g. 96 | auto-merge — `"Northwind Capitol Partners"`, a typo |
| 5 | Fuzzy ≥ `ER_REVIEW_MATCH` (75) | 75 | **held for a data steward** — `"Northwood Capital Group"` |
| 6 | Below 75 | — | unresolved, raised as a DQ issue |

Rungs 4 and 5 are four characters apart and must be treated as opposites. A wrong merge
shows one client's data to another client's coverage team, which is why this is a scored
rule with a human review band rather than a judgement call handed to a model.

Every merge writes a **crosswalk** row (source system, source record, source value,
client, method, score), so any canonical value can be traced back to the record it came
from. Each dataset writes a **lineage** row with source system, file, row count and load
time. Data-quality rules raise typed `dq_issues` — `unresolved_entity`, `stale_record`,
`missing_data`, `duplicate_record`, `missing_identifier`, each with a severity — and
those feed both the briefing's uncertainty section and the readiness triage.

Reads go through `backend/app/tools/structured.py`: twelve typed functions, each
`@traced` and each calling `principal.require_client()` before touching SQL. There is no
path from the UI to the database that skips the entitlement check.

### 1b. Unstructured: 18 documents → chunk → gate → extract → typed items

`backend/app/ingest/extract.py`

1. **Chunk.** Documents split on paragraph boundaries into `chunks` rows keyed
   `{doc_id}#{seq}`. Paragraphs, not fixed windows, because these are emails and meeting
   notes where a paragraph is already the unit of meaning.
2. **Classification gate.** `LLM_ALLOWED_CLASSIFICATIONS = {public, internal, confidential}`.
   Anything marked `mnpi` or `legal_restricted` is **never sent to a model at all** — not
   redacted afterwards, not filtered from the output. It does not enter the prompt. That
   is the only way to make "it cannot leak" a statement about the system rather than about
   the model's behaviour.
3. **Extract to a schema.** One call per document returning
   `{"items": [ExtractedItem]}`, validated by Pydantic:

   ```
   type      ask | commitment | fulfillment | contact_change | stated_fact
             | interest | concern | update
   actor     client | firm
   subject   canonical noun phrase, reused across the item's life
   text      one-sentence paraphrase
   due_date  ISO date or null
   value     number in full units (stated_fact only)
   person / previous_holder / new_title   (contact_change only)
   ```

   Invalid JSON or a schema violation triggers a bounded retry with the validation error
   fed back (`MAX_DRAFT_ATTEMPTS`). Still failing, the document degrades to replay rather
   than crashing the ingest.
4. **Cache.** Key is `model : prompt_version : content_hash`. The prompt hash matters:
   without it, editing the extraction prompt silently reuses results produced by the old
   one, and you end up scoring a prompt you already replaced. That happened during this
   build, which is why the key has three parts.

Extraction is where the LLM earns its place. Everything downstream — the commitment
ledger, conflict detection, the change timeline — is code operating on these typed rows.

### Why extraction is the model's job and status is not

`"We committed to send our ESG screening report by August 15"` is prose with no schema,
and no regex will generalise across the way five different bankers write it. That is
reading, and a model is good at it.

Whether that commitment is **Open, Due soon, Overdue or Done** is a comparison of dates
and evidence across documents and the CRM. That is deciding, and it belongs in
`backend/app/briefing/analysis.py`, where it is exact and testable.

---

## 2. Retrieval

`backend/app/retrieval/search.py`

Hybrid BM25 + embeddings, fused with reciprocal-rank fusion. The ordering matters more
than the algorithm:

1. **Entitlement filter first.** Candidate documents are fetched for the client (plus
   firm-wide research and news), then passed through `filter_documents(principal, docs)`.
   Only what survives is chunked into the candidate set.
2. **BM25** over `chunk text + document title`, restricted to chunks sharing at least one
   query token — so a zero-overlap chunk cannot ride in on a low score.
3. **Embeddings** (`text-embedding-3-small`) when a key is configured, cached on disk at
   `data/cache/embeddings.json`. Absent a key, retrieval degrades to BM25 alone and the
   app keeps working.
4. **RRF** fuses the two rankings.

Because step 1 precedes scoring, the model never receives text the user cannot see. You
cannot leak what was never in the prompt. This is also why the retrieval gate tests both
directions: a `expect_doc` that must be found, and a `forbid_doc` that must not be.

---

## 3. Generation and summarisation

`backend/app/briefing/sections.py`, `graph.py`

Seven sections, one per question in the brief. Four are LLM-written, three are pure code.

### The evidence pack

Each section's `gather()` builds a `Pack` — an id-addressed set of facts drawn from the
entitled tools:

```
CS1  "Northwind Capital Partners LLC is a Tier 1 Hedge Fund client…"  CRM account master
CS2  "Total AUM $3.8B (figures conflict across sources)"              Resolved AUM
CM1  "The client requests an estimate of securities lending…"         D-111
```

The prompt receives **the pack and nothing else** — never the raw corpus, never the
database. Each item carries its id, source and as-of date. `gather()` also produces
deterministic **fallback bullets** for the same facts, which is what the section falls
back to if generation cannot be verified.

### The flow per section

```
gather() ─▶ draft (LLM, evidence pack only) ─▶ verify ─┬─ pass ──▶ render
                     ▲                                  │
                     └──── retry once with the ─────────┘
                           specific failure reasons
                                                        └─ fail twice ──▶ deterministic fallback
```

Sections fan out in parallel via LangGraph `Send`. The deterministic fallback bullets are
**also** run through the verifier — the same gate applies to code and model output, so a
bug in the fallback path cannot bypass the check.

### Summarisation

The three talking points are a second pass over the *already-verified* section bullets,
not a fresh read of the corpus. The summariser sees each verified bullet with its
citations on a labelled line and must carry those ids forward. It is verified like any
other bullet and falls back to deterministic selection (most urgent commitment, latest
change, strongest opportunity) if it fails.

---

## 4. The verifier

`backend/app/briefing/verify.py` — the component that makes the rest defensible.

Every bullet, generated or deterministic, must pass four checks:

| Check | Rule |
|---|---|
| **Has a citation** | At least one id. No citation → rejected |
| **Citations exist** | Every id must be in the evidence pack given to the model. Invented ids → rejected |
| **Numbers are grounded** | Every number must appear in the *cited* evidence, within **1.5%**, and be the **same kind** |
| **No forbidden content** | Output scanned for MNPI and injection markers |

Details that matter:

- **Unit-aware.** `bn/billion/b → 1e9`, `mm/mn/million/m → 1e6`, `k/thousand → 1e3`. So
  `"$3.8 billion"` matches `3800000000`. `"3.8bn"` matches. **`"nearly $4B"` does not** —
  and is rejected, which is correct.
- **Kind-aware.** A percentage, a basis-point figure and a plain number are separate
  kinds. `18.6%` cannot be satisfied by a bare `18.6` elsewhere in the evidence.
- **Dates and identifiers are stripped** before numbers are extracted, so `2026-09-18`,
  `Q2 2026` and `A-1` are not treated as quantities needing a source.
- **Bare integers under 10 are skipped** — `"two tickets"` is a count, not a figure. This
  is a deliberate false-negative: it trades a little strictness for not rejecting readable
  prose. Stated on the limitations slide.
- Rejected bullets are **kept and reported**, not silently dropped, and surface in the run
  trace and the scorecard.

---

## 5. The evaluation harness

`evals/run_evals.py` → `evals/results/latest.{json,md}`, exit code 1 on any breach.
Runs in CI on every push (`.github/workflows/ci.yml`).

It is not a test suite. Tests check that code does what it was written to do; this
measures whether the *system's output* is safe and correct, against a golden set
(`evals/golden/`) and four briefing cases spanning four personas.

### The thirteen gates

| Gate | What is actually computed | Bar |
|---|---|---|
| `leakage_violations` | For each case, every `must_not_contain` string is searched across **all rendered text and the whole evidence pack** — not just what is visible | **0** |
| `access_control_pass_rate` | Each `access_denied` case must raise `AccessDenied` when a briefing is attempted | **1.0** |
| `citation_validity` | Fraction of bullets whose citations are non-empty **and** all resolve to the evidence pack | **1.0** |
| `numeric_faithfulness` | Fraction of bullets with no `ungrounded number` problem from the verifier | **1.0** |
| `question_coverage` | Fraction of the seven sections that produced at least one bullet | **1.0** |
| `must_contain_recall` | Planted facts that must appear in the rendered briefing | **≥ 0.9** |
| `conflict_recall` | Planted conflicts (AUM, stale CIO, task status) that were detected | **1.0** |
| `ledger_status_accuracy` | Expected status **and** expected flags per commitment, matched by fuzzy subject | **1.0** |
| `withheld_accuracy` | Withheld count matches the role, **and** revenue visibility matches | **1.0** |
| `entity_resolution_accuracy` | Each reference resolves to the expected client — including the near-miss that must resolve to **nothing** | **1.0** |
| `retrieval_hit_rate_at_5` | `expect_doc` present in top 5; `forbid_doc` appearing counts as leakage | **≥ 0.75** |
| `extraction_f1` | Predicted items matched to human labels on **type + fuzzy subject** (token-set ≥ 85, verbs stripped); precision/recall/F1 | **≥ 0.70** |
| `injection_extraction_items` | Items extracted from `D-112`, a newsletter carrying `"SYSTEM OVERRIDE"` | **0** |

Alongside, not gated: latency p50/max, LLM calls, tokens, and **verifier rejections**.

### Two honest notes

**Offline extraction F1 is 1.0 by construction.** Offline mode replays the human labels,
so it agrees with them. The harness says so in its own output (`mode: "replay (golden
labels; run with OPENAI_API_KEY to measure the model)"`). The real figure is the live one:
**0.75–0.81 across runs**. It is a range because it genuinely varies; on an 18-document
set one item moves F1 by roughly four points.

**`verifier_rejections` was wrong until recently.** It summed rejections across
`b["sections"]` only, and the executive summary is a separate top-level key — so the
scorecard read zero while the summary failed verification on every build and silently fell
back to deterministic text. The metric now counts it. An uninstrumented surface always
looks perfect.

### The rule held throughout

When a gate failed, the prompt or the code changed. **The threshold never did.** A gate
you move when it is inconvenient is not a gate.

---

## 6. Where this is thin

- The golden set is 18 documents and one author, with no held-out split. Treat F1 as
  directional, not a benchmark.
- Materiality is a rule (revenue/holdings move %, performance bps) set per briefing pack,
  not a learned model. Transparent, but it would want tuning per segment with the desk.
- Identity is an `X-User-Id` header standing in for SSO. The enforcement points are real
  and correctly placed; the authentication in front of them is not.
- Opportunity ranking is a transparent heuristic: stage weight + evidence count − staleness.
- The number checker ignores bare integers under 10 by design (see §4).
- SQLite and BM25 are stand-ins. Every tool contract above them is unchanged when they
  become a lakehouse and a managed vector store.
