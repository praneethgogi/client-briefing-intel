import React, { useEffect, useState } from 'react'
import { api, setUser } from './api.js'
import Briefing from './components/Briefing.jsx'
import Platform from './components/Platform.jsx'
import Evals from './components/Evals.jsx'
import Audit from './components/Audit.jsx'

export default function App() {
  const [personas, setPersonas] = useState([])
  const [user, setUserState] = useState('ava.chen')
  const [health, setHealth] = useState(null)
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(null)
  const [view, setView] = useState('briefing')
  const [toast, setToast] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.health().then(setHealth).catch(() => setErr('Backend not reachable on :8000. Start it with: uvicorn app.api.main:app --reload'))
    api.personas().then(setPersonas).catch(() => {})
  }, [])

  useEffect(() => {
    setUser(user)
    api.clients().then((cs) => {
      setClients(cs)
      setClientId((cur) => (cs.some((c) => c.client_id === cur) ? cur : cs[0]?.client_id || null))
    }).catch(() => setClients([]))
  }, [user])

  const showToast = (m) => { setToast(m); setTimeout(() => setToast(''), 3500) }
  const persona = personas.find((p) => p.user_id === user)
  const client = clients.find((c) => c.client_id === clientId)

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo"><div className="logo-mark">CB</div>Client Briefing Intelligence</div>
        <span className="pill" style={{ background: 'rgba(255,255,255,.15)', color: '#fff' }}>synthetic data</span>
        <div className="spacer" />
        {health && <span className="meta">LLM: <strong>{health.llm_mode}</strong>{health.model ? ` · ${health.model}` : ''} · data as of {health.as_of}</span>}
        <div className="persona">
          <span className="role">Signed in as</span>
          <select value={user} onChange={(e) => setUserState(e.target.value)}>
            {personas.map((p) => <option key={p.user_id} value={p.user_id}>{p.display}</option>)}
          </select>
          {persona && <span className="role">{persona.role}</span>}
        </div>
      </header>
      <div className="body">
        <aside className="sidebar">
          <div className="side-title">Upcoming meetings</div>
          {clients.map((c) => (
            <button key={c.client_id} className={`client-item ${view === 'briefing' && c.client_id === clientId ? 'active' : ''}`}
              onClick={() => { setClientId(c.client_id); setView('briefing') }}>
              {c.legal_name}
              <span className="sub">{c.next_meeting} · {c.segment}</span>
            </button>
          ))}
          {!clients.length && <div className="small muted" style={{ padding: 8 }}>No clients covered.</div>}
          <div className="side-title">Platform</div>
          {[['platform', 'Data & lineage'], ['evals', 'Evaluation'], ['audit', 'Audit log']].map(([k, l]) => (
            <button key={k} className={`nav-item ${view === k ? 'active' : ''}`} onClick={() => setView(k)}>{l}</button>
          ))}
          {persona && (
            <>
              <div className="side-title">Your access</div>
              <div className="small" style={{ padding: '0 10px' }}>
                {persona.clearances.map((c) => <span key={c} className="pill" style={{ margin: 2 }}>{c}</span>)}
              </div>
            </>
          )}
        </aside>
        <main className="main">
          {err && <div className="error" style={{ marginBottom: 12 }}>{err}</div>}
          {view === 'briefing' && <Briefing client={client} user={user} onToast={showToast} />}
          {view === 'platform' && <Platform user={user} onToast={showToast} />}
          {view === 'evals' && <Evals />}
          {view === 'audit' && <Audit user={user} />}
        </main>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
