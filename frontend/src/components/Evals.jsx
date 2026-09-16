import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const LABELS = {
  leakage_violations: 'Restricted content leaked',
  access_control_pass_rate: 'Unauthorized access blocked',
  citation_validity: 'Statements with valid citations',
  numeric_faithfulness: 'Numbers that match their sources',
  question_coverage: 'Briefing questions answered',
  must_contain_recall: 'Expected facts present',
  conflict_recall: 'Planted conflicts detected',
  ledger_status_accuracy: 'Commitment status correct',
  withheld_accuracy: 'Access outcome correct per role',
  entity_resolution_accuracy: 'Records matched to the right client',
  retrieval_hit_rate_at_5: 'Right document in top 5 results',
  extraction_f1: 'Extraction F1 vs human labels',
  injection_extraction_items: 'Items extracted from injected text',
}

export default function Evals() {
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.evals().then(setR).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="stack"><h1>Evaluation</h1><div className="error">{err}</div></div>
  if (!r) return <div className="muted">Loading…</div>
  return (
    <div className="stack">
      <div className="bhead">
        <div>
          <h1>Evaluation scorecard</h1>
          <div className="sub">Run {r.run_at} · LLM mode <strong>{r.llm_mode}</strong>{r.model ? ` (${r.model})` : ''} · run with <code>python -m evals.run_evals</code>; CI fails the build if any check fails</div>
        </div>
        <span className={`pill ${r.passed ? 'ok' : 'bad'}`} style={{ fontSize: 14, padding: '6px 14px' }}>{r.passed ? 'ALL CHECKS PASS' : 'CHECK FAILED'}</span>
      </div>
      <div className="card">
        <table className="t">
          <thead><tr><th>Check</th><th>Metric</th><th>Value</th><th>Threshold</th><th>Result</th></tr></thead>
          <tbody>{Object.entries(r.gates).map(([k, g]) => (
            <tr key={k}><td>{LABELS[k] || k}</td><td><code>{k}</code></td><td><strong>{String(g.value)}</strong></td>
              <td>{g.rule.min !== undefined ? `≥ ${g.rule.min}` : `≤ ${g.rule.max}`}</td>
              <td className={g.passed ? 'gate-pass' : 'gate-fail'}>{g.passed ? 'PASS' : 'FAIL'}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="grid-2">
        <div className="card">
          <h3>Operational</h3>
          <table className="t" style={{ marginTop: 8 }}><tbody>
            {Object.entries(r.operational).map(([k, v]) => <tr key={k}><td>{k}</td><td><strong>{v}</strong></td></tr>)}
          </tbody></table>
          <div className="small muted" style={{ marginTop: 8 }}>Extraction: {r.extraction.mode}</div>
        </div>
        <div className="card">
          <h3>Test cases</h3>
          <table className="t" style={{ marginTop: 8 }}><tbody>
            {r.cases.map((c) => (
              <tr key={c.case}><td><code>{c.case}</code></td><td>{c.latency_ms} ms</td>
                <td>{c.problems.length ? <span className="gate-fail">{c.problems.join('; ')}</span> : <span className="gate-pass">no issues</span>}</td></tr>
            ))}
          </tbody></table>
          {r.extraction.notes?.length > 0 && (
            <details style={{ marginTop: 8 }}><summary className="small">Extraction differences ({r.extraction.notes.length})</summary>
              <ul className="small">{r.extraction.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></details>
          )}
        </div>
      </div>
    </div>
  )
}
