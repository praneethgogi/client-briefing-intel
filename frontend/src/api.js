let currentUser = 'ava.chen'
export const setUser = (u) => { currentUser = u }

async function call(method, path, body, asText = false) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User-Id': currentUser },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = j.detail || j.error || detail } catch { /* ignore */ }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return asText ? res.text() : res.json()
}

export const api = {
  health: () => call('GET', '/health'),
  personas: () => call('GET', '/personas'),
  clients: () => call('GET', '/clients'),
  readiness: () => call('GET', '/readiness'),
  assignments: (mine) => call('GET', `/assignments${mine ? '?mine=true' : ''}`),
  assignees: (cid) => call('GET', `/clients/${cid}/assignees`),
  assign: (body) => call('POST', '/assignments', body),
  resolveAssignment: (id, note) => call('POST', `/assignments/${id}/resolve`, { note }),
  generate: (cid) => call('POST', `/clients/${cid}/briefings`),
  approve: (bid) => call('POST', `/briefings/${bid}/approve`, {}),
  exportMd: (bid) => call('GET', `/briefings/${bid}/export`, null, true),
  createAction: (body) => call('POST', '/actions', body),
  actions: (cid) => call('GET', `/clients/${cid}/actions`),
  updateAction: (id, status) => call('PATCH', `/actions/${id}`, { status }),
  notes: (cid, text, meeting_date) => call('POST', `/clients/${cid}/notes`, { text, meeting_date }),
  ask: (cid, question) => call('POST', `/clients/${cid}/ask`, { question }),
  lineage: () => call('GET', '/platform/lineage'),
  dataQuality: () => call('GET', '/platform/data-quality'),
  audit: () => call('GET', '/platform/audit'),
  evals: () => call('GET', '/evals/latest'),
  reset: () => call('POST', '/admin/reset'),
}
