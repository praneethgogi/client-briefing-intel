import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Audit({ user }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api.audit().then(setRows).catch(() => setRows([])) }, [user])
  return (
    <div className="stack">
      <div className="bhead"><div><h1>Audit log</h1>
        <div className="sub">Every briefing build, access denial, approval, export, task and note capture is recorded. Compliance sees all users; everyone else sees only their own.</div></div></div>
      <div className="card">
        <table className="t">
          <thead><tr><th>Time</th><th>User</th><th>Event</th><th>Client</th><th>Detail</th></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}><td className="small">{r.ts}</td><td>{r.user_id}</td>
              <td><span className={`pill ${r.event === 'access.denied' ? 'bad' : 'brand'}`}>{r.event}</span></td>
              <td>{r.client_id || '-'}</td><td className="small" style={{ maxWidth: 520, wordBreak: 'break-word' }}>{r.detail}</td></tr>
          ))}</tbody>
        </table>
        {!rows.length && <div className="muted small">No events yet.</div>}
      </div>
    </div>
  )
}
