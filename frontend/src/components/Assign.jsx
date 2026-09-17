import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

/**
 * Hand one readiness item to a teammate.
 *
 * The list of people comes from the server, not the client, and only ever contains
 * users already entitled to this client. Assigning is a workflow action, not a
 * grant: it can never widen somebody's access.
 */
export function AssignControl({ clientId, axis, text, onAssigned, onToast }) {
  const [open, setOpen] = useState(false)
  const [people, setPeople] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open && !people.length) api.assignees(clientId).then(setPeople).catch(() => setPeople([]))
  }, [open, clientId, people.length])

  const assign = async (userId) => {
    setBusy(true)
    try {
      await api.assign({ client_id: clientId, axis, text, assign_to: userId })
      onToast?.(`Assigned to ${people.find((p) => p.user_id === userId)?.display || userId}`)
      setOpen(false)
      onAssigned?.()
    } catch (e) {
      onToast?.(`Could not assign: ${e.message}`)
    } finally { setBusy(false) }
  }

  if (!open) {
    return <button className="link-btn" onClick={() => setOpen(true)}>Assign</button>
  }
  return (
    <span className="assign-pop">
      {people.length === 0 && <span className="small muted">No one else covers this client.</span>}
      {people.map((p) => (
        <button key={p.user_id} className="btn sm" disabled={busy} onClick={() => assign(p.user_id)}>
          {p.display}
        </button>
      ))}
      <button className="link-btn" onClick={() => setOpen(false)}>Cancel</button>
    </span>
  )
}

/** The work handed to this user across every client they cover. */
export function Inbox({ items, onResolve, busyId }) {
  if (!items.length) return null
  return (
    <div className="card inbox">
      <div className="card-head">
        <h3>Assigned to you</h3>
        <span className="pill warn">{items.length}</span>
      </div>
      <div className="q" style={{ marginBottom: 8 }}>
        Raised by a teammate preparing for a meeting. Clearing these is what moves a
        meeting to ready.
      </div>
      <ul className="reasons">
        {items.map((a) => (
          <li key={a.assignment_id}>
            <span className={`sev ${a.axis === 'data' ? 'medium' : 'low'}`}>{a.axis}</span>
            <span style={{ flex: 1 }}>
              {a.text}
              <span className="small muted"> — {a.client_id}, from {a.assigned_by}</span>
            </span>
            <button className="btn sm" disabled={busyId === a.assignment_id}
              onClick={() => onResolve(a)}>
              {busyId === a.assignment_id ? 'Saving…' : 'Mark resolved'}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
