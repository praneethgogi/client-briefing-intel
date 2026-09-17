import React from 'react'

export const STATE_CLASS = {
  Ready: 'ok',
  'Needs review': 'warn',
  Blocked: 'bad',
}

/** Small coloured dot used beside a meeting in the sidebar. */
export function StateDot({ state }) {
  return <span className={`dot ${STATE_CLASS[state] || ''}`} title={state} />
}

function ReasonList({ title, reasons, empty }) {
  if (!reasons.length) return <div className="q">{empty}</div>
  return (
    <>
      <div className="small muted" style={{ marginBottom: 4 }}>{title}</div>
      <ul className="reasons">
        {reasons.map((r, i) => (
          <li key={i}>
            <span className={`sev ${r.severity}`}>{r.severity}</span>
            {r.text}
          </li>
        ))}
      </ul>
    </>
  )
}

/**
 * Triage across the whole calendar. This is the landing view: the question is not
 * "write me a briefing" but "which of these can I walk into". Computed entirely in
 * code - no model is called - so it is cheap enough to run on every page load.
 */
export default function Readiness({ data, loading, onOpen, onRefresh }) {
  if (loading && !data) return <div className="card empty"><h2>Checking your meetings…</h2></div>
  if (!data) return null

  const { meetings, by_state: byState, total, needs_attention: needsAttention } = data
  const attention = meetings.filter((m) => m.state !== 'Ready')

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Your week</h1>
          <div className="sub">
            {total === 0 ? 'No meetings on your calendar.'
              : needsAttention === 0
                ? `All ${total} meetings are ready to walk into.`
                : `${needsAttention} of ${total} meetings need someone before they're ready.`}
          </div>
        </div>
        <button className="btn" onClick={onRefresh} disabled={loading}>
          {loading ? 'Checking…' : 'Re-check'}
        </button>
      </div>

      <div className="stats">
        <div className="stat"><div className="v">{total}</div><div className="l">meetings on the calendar</div></div>
        <div className={`stat ${byState.Ready ? 'ok' : ''}`}>
          <div className="v">{byState.Ready}</div><div className="l">ready to walk into</div></div>
        <div className={`stat ${byState['Needs review'] ? 'warn' : ''}`}>
          <div className="v">{byState['Needs review']}</div><div className="l">need review</div></div>
        <div className={`stat ${byState.Blocked ? 'bad' : ''}`}>
          <div className="v">{byState.Blocked}</div><div className="l">blocked on data</div></div>
      </div>

      <div className="banner">
        Triage runs on rules, not a model: conflicting values, unresolved records, stale
        sources, overdue commitments and asks nothing is tracking. Open a meeting and the
        briefing itself is written and checked.
      </div>

      {attention.length > 0 && (
        <>
          <h3 className="section-label">Needs a person first</h3>
          <div className="stack">
            {attention.map((m) => (
              <div key={m.client_id} className={`card triage ${STATE_CLASS[m.state]}`}>
                <div className="card-head">
                  <div>
                    <h3>{m.client_name}</h3>
                    <div className="q">{m.meeting_date} · {m.purpose}</div>
                  </div>
                  <div className="row">
                    <span className={`pill ${STATE_CLASS[m.state]}`}>{m.state}</span>
                    <button className="btn" onClick={() => onOpen(m.client_id)}>Open briefing</button>
                  </div>
                </div>
                <div className="grid-2" style={{ marginTop: 10 }}>
                  <div>
                    <ReasonList title="Data — can the briefing be trusted?" reasons={m.data}
                      empty="No data issues. The briefing can be trusted." />
                  </div>
                  <div>
                    <ReasonList title="Prep — is there work outstanding?" reasons={m.prep}
                      empty="Nothing outstanding on the relationship." />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {byState.Ready > 0 && (
        <>
          <h3 className="section-label">Ready</h3>
          <div className="stack">
            {meetings.filter((m) => m.state === 'Ready').map((m) => (
              <div key={m.client_id} className="card triage ok compact">
                <div className="card-head">
                  <div>
                    <h3>{m.client_name}</h3>
                    <div className="q">{m.meeting_date} · {m.purpose}</div>
                  </div>
                  <div className="row">
                    <span className="pill ok">Ready</span>
                    <button className="btn" onClick={() => onOpen(m.client_id)}>Open briefing</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
