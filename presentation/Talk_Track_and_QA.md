# Talk track and Q&A — Client Briefing Intelligence

Final round, 17 September 2026. Deck: `Client_Briefing_Intelligence.pptx` (16 slides, full talk track in the speaker notes).

**Delivery rules for me.** Direct answer in one or two sentences. Then three to five steps. Then one concrete example. Then stop. Under ninety seconds. If they want depth they will ask — let them.

---

## 1. Timing

| # | Slide | Min | The one line that must land |
|---|---|---|---|
| 1 | Title | 0.5 | Working prototype, synthetic data, nothing confidential. |
| 2 | The problem, reframed | 1.5 | The risk isn't a slow briefing, it's a confident wrong one. |
| 3 | Users & success criteria | 1 | I defined success as five testable things, which is why an eval plan is possible. |
| 4 | The reimagined workflow | 2 | The meeting is the unit of work, not the document. |
| 5 | Options considered | 0.75 | I picked the one I could prove. |
| 6 | Architecture | 2 | One governed store, one set of tools, three consumers. |
| 7 | Where the LLM is / isn't | 1.5 | **The LLM reads and writes. Code decides.** |
| 8 | Data unification | 1 | Four characters separate a merge from an incident. |
| 9 | Identity & controls | 1.5 | Filter before retrieval, never after generation. |
| 10 | **Live demo** | 5 | |
| 11 | Evaluation plan | 1.5 | Thirteen gates; I fixed prompts, never thresholds. |
| 12 | What the eval caught | 1.5 | An uninstrumented surface always looks perfect. |
| 13 | Results | 1 | All thirteen pass live; F1 is a range, not a point. |
| 14 | Trade-offs | 1 | The golden set is eighteen docs and I wrote it. |
| 15 | Where this goes next | 1.5 | Finish the reimagining; harden the platform. |
| 16 | Close | 0.5 | Trustworthy by construction. |

**~20 minutes.** If running long, cut slide 5 to one sentence and slide 8 to the Northwood example only. Never cut 7, 12 or 14.

---

## 2. Opening (memorise this one)

> "Before a client meeting, an analyst searches eight systems by hand for two or three hours. The obvious problem is that it's slow. The expensive problem is that it can be confidently wrong — a stale contact, a conflicting AUM figure, a commitment sitting in an inbox that nobody delivered, or something restricted that should never reach a sales conversation.
>
> So I built for trustworthiness first. Every statement in this briefing is cited, checked against its source, and filtered by what you're allowed to see. The design rule is one line: the LLM reads and writes, code decides."

---

## 3. Demo narration — beat by beat

Reset the demo data first. Two terminals and the browser open in advance, browser at ~110%.

| Beat | Say this | Watch for |
|---|---|---|
| Build | "Ava is preparing for tomorrow's Northwind meeting with their new CIO." | 11 sources, 3 conflicts, 0 withheld, ~4s |
| Talking points | "Three things that will actually come up. Each one cites its evidence." | The "LLM-written, verified" badge |
| Click `CM1` | "Every statement is one click from the document it came from." | Source panel opens |
| Ledger | "This ask arrived four days ago and **is not in the CRM**. It's due at this meeting. Today that gets missed." | "Not tracked in CRM" + "Due at this meeting" |
| Conflicts | "Four AUM figures across four systems. It picks the system of record, shows you all four, and says why." | Also the stale CIO and the Northwood near-miss |
| Create action | "Suggested action becomes a tracked task. Rebuild — the flag clears." | It drives the workflow, doesn't just describe it |
| Switch to Leo | "Same client, same moment, different analyst. Revenue is gone and he's told it's gone." | "Limited view" banner, `withheld: 1` |
| Switch to Ben | "Not on his coverage. The API returns 403 — the client isn't even listed." | |
| Run trace | "Every graph step, every access-checked tool call, tokens and latency." | |
| Post-meeting | Paste: *"Priya asked for a liquidity stress test by Oct 15. We'll send the FX hedging proposal by Sept 25."* | Two new tracked items — the loop closing |
| Evals | "Thirteen gates, green, on the live model." | |

**If the demo breaks:** "I'll show you the screenshots — and there's an offline mode that runs this whole flow with no network, which is also what CI uses." Do not debug live. Move on.

---

## 4. Q&A bank

### Design and architecture

**Why not let an agent decide which tools to call?**
Predictability, evaluability and security. A fixed graph means I can test every path and tell you the latency. More importantly, if the model chooses the tools, it's inside the security path — and then "where is the LLM *not* used" has no good answer. Agentic search does have a place here: the follow-up Q&A box and the MCP surface, where it's bounded and still entitlement-checked on every call.

**Why LangGraph rather than CrewAI or plain functions?**
Explicit state and control flow, `Send` for fan-out so the seven sections draft in parallel, and checkpointing for human-in-the-loop later. CrewAI suits role-play multi-agent setups; that's less controllable and harder to evaluate. Honestly, for this scope plain async functions would also work — LangGraph earns its place when I add durable checkpoints and approval interrupts before CRM writes.

**Why SQLite and BM25?**
Zero setup for a one-day build, and they're stand-ins. The point is every tool contract above them is unchanged when SQLite becomes a governed lakehouse and BM25 becomes a managed vector store with ACL-filtered search. The interface is the design; the storage is an implementation detail.

**How does MCP fit?**
The same governed tools exposed to any agent host, with typed contracts and error codes. The important detail: identity comes from the host environment, never from a tool argument. A model cannot choose whose permissions it runs with.

**Isn't seven parallel LLM calls expensive?**
Only four sections and the summary use the model — five calls, about 5k tokens, under a cent per briefing. Three sections are pure code. At scale I'd precompute overnight for scheduled meetings, cache evidence packs, and use a smaller model for extraction.

### Safety and correctness

**How do you stop hallucinations?**
Four layers. The prompt only ever sees an evidence pack, never the raw corpus. Every bullet must carry citation IDs. A verifier checks the citations exist and that every number matches its cited source. Fail, and it retries once with the failure reason; fail again and the section falls back to deterministic bullets. Then the eval gate measures citation validity and numeric faithfulness at 100%.

**How are entitlements enforced with RAG?**
The filter runs before retrieval, not after generation. The index carries ACL metadata, unentitled documents are removed before scoring, so the model physically never receives text the user can't see. You cannot leak what was never in the prompt. Row, field and document level, and purpose is part of the check.

**What about prompt injection?**
Defence in depth. Documents are framed as untrusted data. Restricted classifications never reach a prompt at all. The output is checked for forbidden markers. And there's a planted injection in the corpus — a newsletter containing "SYSTEM OVERRIDE" — with a standing eval gate that it must produce zero extracted items. It does.

**What if two sources conflict?**
Never silently pick. Precedence is system of record plus recency, every claim is shown with its source and date, and the resolution states which was used and why. Northwind's AUM appears as $4.2B in CRM, $3.8B in the performance system, $4.1bn in a meeting note. It uses $3.8B, shows all four, and suggests a data-steward fix.

**Could a wrong entity merge leak data?**
Yes, and that's exactly why it isn't a model decision. Resolution is a ladder — ID, LEI, exact alias, fuzzy — with a review band. Above 90 merges, below 75 is rejected, and 75–89 goes to a human. A typo, "Northwind Capitol Partners", scores 96 and merges. A different firm, "Northwood Capital Group", scores 75 and is held. Four characters apart, opposite outcomes.

### Evaluation

**How do you evaluate without real data?**
Synthetic data with deliberately planted defects — aliases, duplicates, a missing ID, conflicting numbers, a stale contact, restricted records, an injection — plus a human-labelled golden set. That proves the mechanism. In production: shadow mode alongside analysts, thumbs up/down per bullet, sampled human review, drift monitoring on the verifier rejection rate, and red-team sets.

**Isn't tuning prompts against your own golden set overfitting?**
Fair challenge, and partly yes. What I changed were four specification defects — my prompt never defined what "person" meant on a contact change, never distinguished an ask from a chase, never said a prior briefing isn't a system of record. Those are underspecification, not fitting to answers. But the set is eighteen documents with no held-out split, so I treat F1 as directional. With a real corpus I'd hold out a test split and grow the set from entitled corrections.

**Your offline F1 is 1.0. Is that real?**
No, and I'd rather say so than let it sit on a slide. Offline mode replays the human labels, so it agrees with them by construction. The only real number is live: 0.75 to 0.81 across runs. It's a range because it genuinely varies run to run, and on eighteen documents one item moves F1 about four points.

**What did the evaluation actually catch?** *(volunteer this if it doesn't come up)*
Five defects on the first live run, after the offline suite was fully green. The best one: my scorecard reported zero verifier rejections, and that was false. The executive summary was failing verification on every build and silently falling back to deterministic text — my metric summed rejections across sections, and the summary wasn't in the denominator. I fixed the prompt and the metric. The lesson generalises: an uninstrumented surface always looks perfect.

**What would make you say this is NOT safe to ship?**
Any safety gate below 100% — leakage, access control, injection. Those aren't thresholds to tune. Beyond that: a rising verifier rejection rate would tell me the model or the data drifted, and I'd want shadow mode against real analysts before anyone relied on it unsupervised.

### Scale and operations

**How would you scale to 10k RMs and 100k clients?**
Precompute. Briefings are built overnight for meetings on tomorrow's calendar, not on demand. Then: cached evidence packs, async workers, per-section parallelism, a smaller model for extraction, and token budgets per briefing. The expensive part is extraction, and it's cached by content hash — a document is only ever read once per prompt version.

**Cost and latency?**
About 4.4 seconds and roughly 5k tokens per briefing on gpt-4o-mini — under a cent. The whole thirteen-gate live suite is about 19k tokens. Precomputing overnight makes latency a non-issue for the user.

**Model lifecycle and governance?**
Approved-model registry, prompt versioning, evals per release with rollback, and monitoring on rejection rate and cost. Prompt versioning isn't theoretical for me — I hit exactly that bug: I changed an extraction prompt and the cache silently served results from the old one, so I was scoring a prompt I'd already replaced. The cache key now includes a prompt hash.

**Would this run on a different model?**
Yes, it's a config switch, and I validated both ways. There's a real portability trap: the code hard-coded `temperature=0`, which reasoning models reject outright — so it 400s on every call. Sampling parameters are model-dependent, not global. I run the demo on gpt-4o-mini deliberately: temperature 0 makes it reproducible, which is the whole point of a verified system.

### Product and judgement

**Why is this not just a memo?**
A memo is stale the moment it's written and it ends when you close it. This is a loop: prepare, support the conversation, capture what happened, and feed that into the next briefing. The post-meeting capture is the part that compounds — every meeting leaves the relationship better documented than it found it.

**Why not a chatbot?**
A chatbot makes the human do the work of knowing what to ask. An RM walking into a meeting shouldn't have to guess the right question to discover that a commitment is overdue. Push the seven answers; keep a question box for the long tail. I have one — it's the follow-up Q&A, over entitled documents only.

**What's genuinely weak about this?**
The golden set — eighteen documents, and I wrote it, so it encodes my judgement of a good extraction. That's the first thing I'd grow. After that: materiality is a rule rather than a tuned model, identity is a demo header standing in for SSO, and opportunity ranking is a transparent heuristic. All stated in the README, not buried.

**What would you do with one more week?**
Split the UI into the three phases properly — prepare, in-meeting, capture. Right now all three live on one page, which is the one place the build hasn't caught up with the design. Then a steward UI for the entity-resolution review band, LLM-as-judge for narrative quality alongside the rule checks, checkpointed human approval before any CRM write, and a much larger golden set.

**How does this relate to your day job?**
Same principles I run in production on AGDEX — a configuration-driven extraction platform on Azure OpenAI and Document Intelligence: schema-driven extraction, confidence and validation gates, human review on the uncertain band, and measured accuracy rather than asserted accuracy. **This build is clean-room, on my own laptop, on synthetic data.** No client data, no firm data, nothing from my employer.

**Why should we hire you for this role?**
Because the hard part of agentic infrastructure isn't getting a model to produce something impressive — it's being able to prove what it produced is safe. I built a working prototype in a day, and I can tell you exactly where the LLM is, where it isn't, what the evaluation caught, and what's still weak. That's the job.

---

## 5. Traps

| If they say | Don't | Do |
|---|---|---|
| "That F1 seems low" | Defend it | "It is, and it's honest. Eighteen documents, no held-out split. I'd rather show a real number than a replayed 1.0." |
| "This is just RAG with extra steps" | Get defensive | "The retrieval is the easy part. The entitlement filter before scoring and the verifier after generation are what make it usable at a bank." |
| "Why didn't you use agents?" | Apologise | "I did, where it's bounded — follow-up Q&A and MCP. I kept them out of the security path on purpose." |
| "Could the model have made that number up?" | Say "no" | "It can't reach the display. Numbers come from SQL, and the verifier rejects any generated number that doesn't match its cited source." |
| A question I don't know | Bluff | "I don't know. Here's how I'd find out." |
| Deep-diving one slide | Rush the rest | "Happy to go deeper — shall I finish the arc first and come back?" |

---

## 6. Pre-flight

- [ ] `.\scripts\run_backend.ps1` and `.\scripts\run_frontend.ps1`, browser at ~110%
- [ ] **Reset demo data** immediately before presenting
- [ ] Health check shows `llm_mode: openai`
- [ ] `.env` has the key; `LLM_MODE=offline` is the fallback if the network misbehaves
- [ ] Deck open in presenter view (notes are the talk track)
- [ ] Repo open: `github.com/praneethgogi/client-briefing-intel`, CI green
- [ ] Notifications silenced, second monitor arranged
