import React, { useEffect, useState } from 'react'
import { api, setUser } from './api.js'
import Briefing from './components/Briefing.jsx'
import Platform from './components/Platform.jsx'
import Evals from './components/Evals.jsx'
import Audit from './components/Audit.jsx'
import Readiness, { StateDot } from './components/Readiness.jsx'

export default function App() {
  const [personas, setPersonas] = useState([])
  const [user, setUserState] = useState('ava.chen')
  const [health, setHealth] = useState(null)
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(null)
  const [view, setView] = useState('week')
  const [readiness, setReadiness] = useState(null)
  const [loadingReadiness, setLoadingReadiness] = useState(false)
  const [inbox, setInbox] = useState([])
  const [busyAssignment, setBusyAssignment] = useState('')
  const [toast, setToast] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.health().then(setHealth).catch(() => setErr('Backend not reachable on :8000. Start it with: uvicorn app.api.main:app --reload'))
    api.personas().then(setPersonas).catch(() => {})
  }, [])

  const loadReadiness = () => {
    setLoadingReadiness(true)
    api.assignments(true).then(setInbox).catch(() => setInbox([]))
    return api.readiness().then(setReadiness).catch(() => setReadiness(null))
      .finally(() => setLoadingReadiness(false))
  }

  const resolveAssignment = async (a) => {
    setBusyAssignment(a.assignment_id)
    try {
      await api.resolveAssignment(a.assignment_id, null)
      showToast('Resolved. The meeting has been re-checked.')
      await loadReadiness()
    } catch (e) { showToast(e.message) } finally { setBusyAssignment('') }
  }

  useEffect(() => {
    setUser(user)
    setReadiness(null)
    setInbox([])
    api.clients().then((cs) => {
      setClients(cs)
      setClientId((cur) => (cs.some((c) => c.client_id === cur) ? cur : cs[0]?.client_id || null))
    }).catch(() => setClients([]))
    loadReadiness()
  }, [user])

  const stateFor = (cid) => readiness?.meetings.find((m) => m.client_id === cid)?.state

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
          <button className={`nav-item ${view === 'week' ? 'active' : ''}`} onClick={() => setView('week')}>
            Your week
            {inbox.length > 0
              ? <span className="count warn">{inbox.length} for you</span>
              : readiness && readiness.needs_attention > 0
                ? <span className="count">{readiness.needs_attention}</span>
                : null}
          </button>
          {clients.map((c) => (
            <button key={c.client_id} className={`client-item ${view === 'briefing' && c.client_id === clientId ? 'active' : ''}`}
              onClick={() => { setClientId(c.client_id); setView('briefing') }}>
              <span className="row-line"><StateDot state={stateFor(c.client_id)} />{c.legal_name}</span>
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
          {view === 'week' && (
            <Readiness data={readiness} loading={loadingReadiness} onRefresh={loadReadiness}
              onOpen={(cid) => { setClientId(cid); setView('briefing') }}
              inbox={inbox} onResolve={resolveAssignment} busyId={busyAssignment}
              onToast={showToast} />
          )}
          {view === 'briefing' && (
            <Briefing client={client} user={user} onToast={showToast} onChanged={loadReadiness} />
          )}
          {view === 'platform' && <Platform user={user} onToast={showToast} />}
          {view === 'evals' && <Evals />}
          {view === 'audit' && <Audit user={user} />}
        </main>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
