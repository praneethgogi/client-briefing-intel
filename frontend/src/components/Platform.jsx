import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const SEV = { high: 'bad', medium: 'warn', low: '' }
const STATUS = { matched: 'ok', review: 'warn', unresolved: 'bad', firm_wide: '' }

export default function Platform({ user, onToast }) {
  const [lineage, setLineage] = useState([])
  const [dq, setDq] = useState({ issues: [], crosswalk: [] })
  const [err, setErr] = useState('')

  const load = () => {
    Promise.all([api.lineage(), api.dataQuality()])
      .then(([l, d]) => { setLineage(l); setDq(d) })
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [user])

  const reset = async () => {
    const r = await api.reset()
    onToast(`Demo data rebuilt: ${Object.values(r.datasets).reduce((a, b) => a + b, 0)} records, ${r.dq_issues} data-quality issues`)
    load()
  }

  return (
    <div className="stack">
      <div className="bhead">
        <div>
          <h1>Data platform</h1>
          <div className="sub">Where the data comes from, how fresh it is, data-quality checks, and how records were matched to clients.</div>
        </div>
        <button className="btn" onClick={reset}>Reset demo data</button>
      </div>
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h3>Lineage & freshness</h3>
        <table className="t" style={{ marginTop: 8 }}>
          <thead><tr><th>Dataset</th><th>Source system</th><th>File</th><th>Rows</th><th>Latest as-of</th><th>Content hash</th><th>Loaded</th></tr></thead>
          <tbody>{lineage.map((l) => (
            <tr key={l.dataset}><td><code>{l.dataset}</code></td><td>{l.source_system}</td><td className="small">{l.source_file}</td>
              <td>{l.rows}</td><td>{l.max_as_of || '-'}</td><td className="small muted">{l.content_hash || '-'}</td><td className="small">{l.loaded_at}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>Data-quality issues ({dq.issues.length})</h3>
        <div className="q">Raised at ingestion by rules, shown in briefings, and never hidden.</div>
        <table className="t" style={{ marginTop: 8 }}>
          <thead><tr><th>ID</th><th>Client</th><th>Kind</th><th>Severity</th><th>Detail</th><th>Source</th></tr></thead>
          <tbody>{dq.issues.map((i) => (
            <tr key={i.issue_id}><td><code>{i.issue_id}</code></td><td>{i.client_id || '-'}</td><td>{i.kind}</td>
              <td><span className={`pill ${SEV[i.severity]}`}>{i.severity}</span></td><td>{i.detail}</td><td className="small">{i.source}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>Matching records to clients</h3>
        <div className="q">Steps, in order: ID → LEI → exact name or alias → fuzzy match (≥90 automatic, 75–89 sent for review) → otherwise left unmatched. Guessing is never allowed.</div>
        <table className="t" style={{ marginTop: 8 }}>
          <thead><tr><th>Source</th><th>Record</th><th>Reference as written</th><th>Resolved to</th><th>Method</th><th>Score</th><th>Status</th></tr></thead>
          <tbody>{dq.crosswalk.map((x, i) => (
            <tr key={i}><td className="small">{x.source}</td><td><code>{x.source_record}</code></td><td>{x.source_value || <span className="muted">(none)</span>}</td>
              <td>{x.client_id || '-'}</td><td>{x.method}</td><td>{x.score}</td>
              <td><span className={`pill ${STATUS[x.status] ?? ''}`}>{x.status}</span></td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  )
}
