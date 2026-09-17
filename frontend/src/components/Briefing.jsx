import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const GEN_LABEL = {
  llm: ['LLM-written, verified', 'brand'],
  llm_partial: ['LLM (some lines removed)', 'warn'],
  deterministic: ['Rules only, no LLM', ''],
  fallback_after_llm: ['LLM failed checks, used rules', 'warn'],
}
const STATUS_PILL = { Overdue: 'bad', 'Due soon': 'warn', Open: 'brand', Done: 'ok' }

function Cites({ ids, selected, onSelect }) {
  return (ids || []).map((id) => (
    <button key={id} className={`cite ${selected === id ? 'active' : ''}`} onClick={() => onSelect(id)}
      title="Show source">{id}</button>
  ))
}

function Bullets({ items, selected, onSelect }) {
  if (!items?.length) return <div className="muted small">Nothing to report.</div>
  return (
    <ul className="bullets">
      {items.map((b, i) => (
        <li key={i}>{b.text}<Cites ids={b.citations} selected={selected} onSelect={onSelect} /></li>
      ))}
    </ul>
  )
}

function SectionCard({ s, children, selected, onSelect }) {
  const [label, tone] = GEN_LABEL[s.generation] || [s.generation, '']
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3>{s.title}</h3>
          <div className="q">{s.question}</div>
        </div>
        <span className={`pill ${tone}`} title={`attempts: ${s.attempts}`}>{label}</span>
      </div>
      {children || <Bullets items={s.bullets} selected={selected} onSelect={onSelect} />}
      {s.rejected?.length > 0 && (
        <details className="small" style={{ marginTop: 8 }}>
          <summary className="muted">{s.rejected.length} line(s) removed by the checker</summary>
          <ul>{s.rejected.map((r, i) => <li key={i}><code>{r.text}</code>: {r.problems.join('; ')}</li>)}</ul>
        </details>
      )}
    </div>
  )
}

function Ledger({ s, evidenceFor, onSelect, selected }) {
  const ledger = s.data.ledger
  if (!ledger.length) return <Bullets items={s.bullets} onSelect={onSelect} selected={selected} />
  return (
    <table className="t">
      <thead><tr><th>Item</th><th>Status</th><th>Due</th><th>Where it came from</th></tr></thead>
      <tbody>
        {ledger.map((l, i) => (
          <tr key={l.ledger_id}>
            <td>
              <div style={{ fontWeight: 600 }}>{l.subject}</div>
              <div className="small muted">{l.ask_text || l.commit_text || ''}</div>
              <div className="row" style={{ marginTop: 3 }}>
                {l.flags.map((f) => <span key={f} className="pill warn">{f}</span>)}
              </div>
            </td>
            <td><span className={`pill ${STATUS_PILL[l.status]}`}>{l.status}</span></td>
            <td className="small">{l.due_date || '-'}</td>
            <td className="small">
              {l.requested_by && <div>Asked: {l.requested_by}</div>}
              {l.committed_in && <div>Committed: {l.committed_in}</div>}
              {l.fulfilled_by && <div>Delivered: {l.fulfilled_by}</div>}
              {l.crm_action_id && <div>Task: {l.crm_action_id} ({l.crm_status})</div>}
              <Cites ids={s.bullets[i]?.citations} selected={selected} onSelect={onSelect} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Metrics({ s, onSelect, selected }) {
  return (
    <div>
      {s.data.metrics.map((m) => (
        <div key={m.key} className={`metric ${m.material ? '' : 'dim'}`}>
          <span>{m.text}<Cites ids={[m.evidence_id]} selected={selected} onSelect={onSelect} /></span>
          {m.material ? <span className="pill warn">material</span> : <span className="pill">below threshold</span>}
        </div>
      ))}
      <div className="small muted" style={{ marginTop: 6 }}>
        Materiality is set by rules (revenue or holdings moves of 10% or more, performance 25 bps or more vs benchmark, open high/medium service issues).
      </div>
    </div>
  )
}

function Conflicts({ conflicts, s, onSelect, selected }) {
  return (
    <div>
      {conflicts.map((c, i) => (
        <div className="conflict" key={i}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong>{c.field}</strong><span className="pill warn">{c.kind.replace('_', ' ')}</span>
          </div>
          <div className="claims">
            {c.claims.map((cl, j) => (
              <div className="claim" key={j}>
                <span>{cl.display}</span>
                <span className="muted">{cl.source} · {cl.as_of || 'n/a'}</span>
              </div>
            ))}
          </div>
          <div className="small">{c.resolution}</div>
        </div>
      ))}
      <div style={{ marginTop: conflicts.length ? 10 : 0 }}>
        <Bullets items={s.bullets.filter((b) => !b.text.startsWith('Conflict'))} onSelect={onSelect} selected={selected} />
      </div>
    </div>
  )
}

function Trace({ b }) {
  const nodes = b.trace.filter((t) => t.kind === 'node')
  const tools = b.trace.filter((t) => t.kind === 'tool')
  const max = Math.max(1, ...nodes.map((n) => n.ms))
  const m = b.run_metrics
  return (
    <div className="stack">
      <div className="card">
        <h3>How this briefing was built</h3>
        <div className="q">LangGraph steps: authorize → prepare → plan → sections in parallel → summarize → assemble</div>
        <div style={{ marginTop: 10 }}>
          {nodes.map((n, i) => (
            <div className="trace-row" key={i}>
              <code>{n.name}</code>
              <span className="muted">{n.ms} ms</span>
              <div>
                <div className="bar" style={{ width: `${(n.ms / max) * 100}%` }} />
                <div className="small muted">{n.detail}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="row small" style={{ marginTop: 10 }}>
          <span className="pill">total {m.latency_ms} ms</span>
          <span className="pill">{m.tool_calls} tool calls</span>
          <span className="pill brand">{m.llm.calls} LLM calls</span>
          <span className="pill">{m.llm.prompt_tokens + m.llm.completion_tokens} tokens</span>
          {m.llm.errors?.length > 0 && <span className="pill bad">{m.llm.errors.length} LLM errors</span>}
        </div>
      </div>
      <div className="card">
        <h3>Tool calls (every one checked against the user's access)</h3>
        <table className="t" style={{ marginTop: 8 }}>
          <thead><tr><th>Tool</th><th>Args</th><th>Rows</th><th>Status</th><th>ms</th></tr></thead>
          <tbody>
            {tools.map((t, i) => (
              <tr key={i}><td><code>{t.name}</code></td><td className="small">{t.args.join(', ')}</td>
                <td>{t.rows ?? '-'}</td><td><span className={`pill ${t.status === 'ok' ? 'ok' : 'bad'}`}>{t.status}</span></td>
                <td>{t.ms}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Sources({ b }) {
  return (
    <div className="card">
      <h3>Sources you can see ({b.sources.length})</h3>
      <div className="q">Documents your access allows for this purpose. Restricted items are withheld before search or any LLM call.
        {b.withheld.count > 0 && ` ${b.withheld.count} item(s) were withheld.`}</div>
      <table className="t" style={{ marginTop: 8 }}>
        <thead><tr><th>Doc</th><th>Title</th><th>Type</th><th>Date</th><th>Source</th><th>Class</th></tr></thead>
        <tbody>
          {b.sources.map((d) => (
            <tr key={d.doc_id}><td><code>{d.doc_id}</code></td><td>{d.title}</td><td>{d.doc_type}</td><td>{d.date}</td>
              <td className="small">{d.source}{!d.client_scoped && <span className="pill" style={{ marginLeft: 4 }}>firm-wide</span>}</td>
              <td><span className={`pill ${d.classification === 'public' ? 'ok' : 'brand'}`}>{d.classification}</span></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SidePanel({ b, selected, clientId, onToast, onRegenerate, onChanged }) {
  const ev = selected ? b.evidence[selected] : null
  const [created, setCreated] = useState({})
  const [notes, setNotes] = useState('')
  const [captured, setCaptured] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState('')

  useEffect(() => { setCreated({}); setCaptured(null); setAnswer(null) }, [b.briefing_id])

  const createAction = async (a, i) => {
    setBusy(`a${i}`)
    try {
      await api.createAction({ client_id: clientId, title: a.title, due_date: a.due_date, origin: 'Briefing suggestion' })
      setCreated((c) => ({ ...c, [i]: true }))
      onToast(`Task created: ${a.title}`)
      onChanged?.()  // the meeting may now be ready; refresh the week
    } catch (e) { onToast(`Failed: ${e.message}`) } finally { setBusy('') }
  }
  const capture = async () => {
    setBusy('notes')
    try { setCaptured(await api.notes(clientId, notes)); setNotes(''); onChanged?.() } catch (e) { onToast(e.message) } finally { setBusy('') }
  }
  const ask = async () => {
    setBusy('ask')
    try { setAnswer(await api.ask(clientId, question)) } catch (e) { onToast(e.message) } finally { setBusy('') }
  }

  return (
    <div className="stack sticky">
      <div className="card">
        <h3>Source</h3>
        {!ev && <div className="q">Click a citation such as <span className="cite">KM1</span> to see where a statement came from.</div>}
        {ev && (
          <div className="evidence" style={{ marginTop: 8 }}>
            <div className="src"><strong>{ev.id}</strong> · {ev.source} · {ev.as_of || 'n/a'} · ref {ev.ref}</div>
            <div>{ev.text}</div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Suggested actions</h3>
        <div className="q">Created as tasks; the briefing picks them up next time it runs.</div>
        <div className="stack" style={{ gap: 8, marginTop: 8 }}>
          {b.suggested_actions.length === 0 && <div className="small muted">None.</div>}
          {b.suggested_actions.map((a, i) => (
            <div key={i} className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600 }}>{a.title}</div>
                <div className="small muted">{a.reason}{a.due_date ? ` · due ${a.due_date}` : ''}</div>
              </div>
              <button className="btn sm" disabled={created[i] || busy === `a${i}`} onClick={() => createAction(a, i)}>
                {created[i] ? 'Created' : 'Create'}
              </button>
            </div>
          ))}
          {Object.keys(created).length > 0 && (
            <button className="btn sm primary" onClick={onRegenerate}>Refresh briefing</button>
          )}
        </div>
      </div>

      <div className="card">
        <h3>After the meeting</h3>
        <div className="q">Paste your notes. New asks and commitments are pulled out and tracked.</div>
        <textarea placeholder="e.g. Priya asked for a liquidity stress test by Oct 15. We will send the FX hedging proposal by Sept 25."
          value={notes} onChange={(e) => setNotes(e.target.value)} style={{ marginTop: 8 }} />
        <div className="row" style={{ marginTop: 6 }}>
          <button className="btn primary sm" disabled={notes.length < 10 || busy === 'notes'} onClick={capture}>
            {busy === 'notes' ? 'Extracting…' : 'Capture notes'}</button>
        </div>
        {captured && (
          <div style={{ marginTop: 8 }} className="small">
            <div className="muted">Pulled out {captured.items.length} item(s) using {captured.method}:</div>
            <ul className="bullets" style={{ marginTop: 4 }}>
              {captured.items.map((it, i) => <li key={i}><span className="pill">{it.type}</span> {it.subject}{it.due_date ? ` (due ${it.due_date})` : ''}</li>)}
            </ul>
            <button className="btn sm primary" style={{ marginTop: 6 }} onClick={onRegenerate}>Refresh briefing</button>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Ask a follow-up</h3>
        <div className="q">Searches only documents you're allowed to see, with sources.</div>
        <div className="row" style={{ marginTop: 8, flexWrap: 'nowrap' }}>
          <input className="text" value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="What did they say about settlement delays?" onKeyDown={(e) => e.key === 'Enter' && question.length > 2 && ask()} />
          <button className="btn sm" disabled={question.length < 3 || busy === 'ask'} onClick={ask}>Ask</button>
        </div>
        {answer && (
          <div style={{ marginTop: 8 }}>
            <div className="small muted">mode: {answer.mode}</div>
            {answer.answer.map((a, i) => (
              <div className="evidence" key={i}>
                <div>{a.text}</div>
                <div className="src">{a.citations.map((c) => `${c}: ${answer.evidence[c]?.source} (${answer.evidence[c]?.as_of})`).join(' · ')}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Briefing({ client, user, onToast, onChanged }) {
  const [b, setB] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('prepare')

  useEffect(() => { setB(null); setError(''); setSelected(null); setTab('prepare') }, [client?.client_id, user])

  const generate = async () => {
    setLoading(true); setError('')
    try { setB(await api.generate(client.client_id)); setSelected(null) } catch (e) { setError(e.message) } finally { setLoading(false) }
  }
  const approve = async () => {
    const r = await api.approve(b.briefing_id)
    setB({ ...b, status: r.status, approved_by: r.approved_by })
    onToast('Briefing approved and logged')
  }
  const exportMd = async () => {
    const md = await api.exportMd(b.briefing_id)
    const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }))
    const a = document.createElement('a')
    a.href = url; a.download = `${b.client_name.replace(/\W+/g, '_')}_briefing.md`; a.click()
    URL.revokeObjectURL(url)
  }

  const sec = useMemo(() => Object.fromEntries((b?.sections || []).map((s) => [s.key, s])), [b])

  // One renderer per section key. Which sections appear, and in what order, comes from
  // the briefing pack - so a new meeting type is a config change, not a UI change.
  const renderSection = (key) => {
    const s = sec[key]
    if (!s) return null
    const extra = {
      commitments: <Ledger s={s} onSelect={setSelected} selected={selected} />,
      metrics: <Metrics s={s} onSelect={setSelected} selected={selected} />,
      uncertainty: <Conflicts conflicts={b.conflicts} s={s} onSelect={setSelected} selected={selected} />,
    }[key]
    return (
      <SectionCard key={key} s={s} selected={selected} onSelect={setSelected}>{extra}</SectionCard>
    )
  }

  if (!client) return <div className="empty"><h2>Pick a client</h2>Choose an upcoming meeting on the left.</div>

  const header = (
    <div className="bhead">
      <div>
        <h1>{client.legal_name}</h1>
        <div className="sub">
          {client.segment} · Tier {client.tier} · Next meeting <strong>{client.next_meeting || 'none scheduled'}</strong>
          {client.purpose ? ` · ${client.purpose}` : ''}
        </div>
      </div>
      <div className="row">
        {b && <span className={`pill ${b.status === 'approved' ? 'ok' : ''}`}>{b.status}{b.approved_by ? ` by ${b.approved_by}` : ''}</span>}
        {b && <button className="btn" onClick={exportMd}>Export</button>}
        {b && b.status !== 'approved' && <button className="btn ok" onClick={approve}>Approve</button>}
        <button className="btn primary" onClick={generate} disabled={loading}>
          {loading ? <><span className="spinner" /> Building…</> : b ? 'Rebuild briefing' : 'Build briefing'}
        </button>
      </div>
    </div>
  )

  if (!b) return (
    <div>
      {header}
      {error && <div className="error">{error}</div>}
      {!error && (
        <div className="card empty">
          <h2>Get ready for the meeting</h2>
          <div>Pulls together CRM, finance, product, service, emails, notes, research and approved news that
            you're allowed to see. It resolves duplicates and aliases, flags conflicts, and cites a source for every statement.</div>
        </div>
      )}
    </div>
  )

  const m = b.run_metrics
  const lead = b.pack?.lead || ['commitments', 'changes', 'uncertainty']
  const restCount = (b.pack?.order || []).filter((k) => !lead.includes(k)).length
  return (
    <div>
      {header}
      <div className="stats">
        <div className="stat"><div className="v">{b.sources.length}</div><div className="l">sources you can see</div></div>
        <div className={`stat ${b.conflicts.length ? 'warn' : ''}`}><div className="v">{b.conflicts.length}</div><div className="l">conflicts found</div></div>
        <div className={`stat ${b.withheld.count ? 'warn' : ''}`}><div className="v">{b.withheld.count}</div><div className="l">withheld by access policy</div></div>
        <div className="stat"><div className="v">{(m.latency_ms / 1000).toFixed(1)}s</div><div className="l">build time</div></div>
      </div>
      {b.withheld.count > 0 && (
        <div className="banner warn">
          <strong>Limited view.</strong> {b.withheld.count} item(s) withheld for your role ({b.user.role}):
          {' '}{b.withheld.items.map((w) => w.label || w.kind).join(', ')}. The briefing was built without them.
        </div>
      )}
      <div className="tabs">
        {[['prepare', 'Prepare'], ['briefing', 'Full briefing'], ['trace', 'Run trace'], ['sources', 'Sources']].map(([k, l]) => (
          <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      <div className="split">
        <div className="stack">
          {tab === 'prepare' && <>
            <div className="card talking">
              <div className="card-head">
                <h3>Top talking points</h3>
                <span className={`pill ${b.executive_summary.generation === 'llm' ? 'brand' : ''}`}>
                  {b.executive_summary.generation === 'llm' ? 'LLM-written, verified' : 'Rules only, no LLM'}</span>
              </div>
              <ol>
                {b.executive_summary.bullets.map((x, i) => (
                  <li key={i}>{x.text}<Cites ids={x.citations} selected={selected} onSelect={setSelected} /></li>
                ))}
              </ol>
            </div>
            {lead.map(renderSection)}
            <div className="card more">
              <div>
                <strong>That's what matters walking in.</strong>
                <div className="q">
                  {restCount} further {restCount === 1 ? 'question is' : 'questions are'} answered in the full
                  briefing. This order is set by the <strong>{b.pack.label}</strong> pack.
                </div>
              </div>
              <button className="btn" onClick={() => setTab('briefing')}>Full briefing</button>
            </div>
          </>}
          {tab === 'briefing' && <>
            <div className="card talking">
              <div className="card-head">
                <h3>Top talking points</h3>
                <span className={`pill ${b.executive_summary.generation === 'llm' ? 'brand' : ''}`}>
                  {b.executive_summary.generation === 'llm' ? 'LLM-written, verified' : 'Rules only, no LLM'}</span>
              </div>
              <ol>
                {b.executive_summary.bullets.map((x, i) => (
                  <li key={i}>{x.text}<Cites ids={x.citations} selected={selected} onSelect={setSelected} /></li>
                ))}
              </ol>
            </div>
            <div className="card more">
              <div>
                <strong>{b.pack.label}</strong>
                <div className="q">{b.pack.focus}</div>
              </div>
            </div>
            {b.pack.order.map(renderSection)}
          </>}
          {tab === 'trace' && <Trace b={b} />}
          {tab === 'sources' && <Sources b={b} />}
        </div>
        <SidePanel b={b} selected={selected} clientId={client.client_id} onToast={onToast}
          onRegenerate={generate} onChanged={onChanged} />
      </div>
    </div>
  )
}
