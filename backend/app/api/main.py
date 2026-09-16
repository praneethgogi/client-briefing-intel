"""REST API. Identity arrives in the X-User-Id header (demo stand-in for an SSO/OIDC token)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .. import config, db, llm, service
from ..ingest import pipeline
from ..security.entitlements import PERSONAS, AccessDenied, Principal, get_principal
from ..tools import structured as T


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.ensure_ready()
    yield


app = FastAPI(title="Client Briefing Intelligence", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(AccessDenied)
async def _denied(request: Request, exc: AccessDenied):
    service.audit(request.headers.get("x-user-id", "?"), "access.denied", None, str(exc))
    return JSONResponse(status_code=403, content={"error": "access_denied", "detail": str(exc)})


@app.exception_handler(T.ToolError)
async def _tool_error(request: Request, exc: T.ToolError):
    return JSONResponse(status_code=404 if exc.code == "not_found" else 400,
                        content={"error": exc.code, "detail": str(exc)})


def principal(x_user_id: str = Header(default="ava.chen")) -> Principal:
    try:
        return get_principal(x_user_id)
    except AccessDenied as exc:
        raise HTTPException(status_code=401, detail=str(exc))


class ActionIn(BaseModel):
    client_id: str
    title: str = Field(min_length=3, max_length=200)
    due_date: str | None = None
    origin: str = "Briefing"


class ActionPatch(BaseModel):
    status: str = Field(pattern="^(Open|Done|Cancelled)$")


class NotesIn(BaseModel):
    text: str = Field(min_length=10, max_length=8000)
    meeting_date: str | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ApproveIn(BaseModel):
    notes: str | None = None


@app.get("/api/health")
def health():
    return dict(status="ok", llm_mode=llm.mode(), model=config.OPENAI_MODEL if llm.enabled() else None,
                as_of=config.AS_OF_DATE.isoformat())


@app.get("/api/personas")
def personas():
    return [dict(user_id=k, display=v["display"], role=v["role"], clearances=sorted(v["clearances"]))
            for k, v in PERSONAS.items()]


@app.get("/api/me")
def me(p: Principal = Depends(principal)):
    return p.public_view()


@app.get("/api/clients")
def clients(p: Principal = Depends(principal)):
    return T.list_clients(p)


@app.get("/api/clients/{client_id}/profile")
def profile(client_id: str, p: Principal = Depends(principal)):
    return T.get_client_profile(p, client_id)


@app.post("/api/clients/{client_id}/briefings")
def create_briefing(client_id: str, p: Principal = Depends(principal)):
    return service.generate(p, client_id)


@app.get("/api/clients/{client_id}/briefings")
def briefings(client_id: str, p: Principal = Depends(principal)):
    return service.list_briefings(p, client_id)


@app.get("/api/briefings/{briefing_id}")
def get_briefing(briefing_id: str, p: Principal = Depends(principal)):
    try:
        return service.get_briefing(p, briefing_id)
    except KeyError:
        raise HTTPException(404, "briefing not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))


@app.post("/api/briefings/{briefing_id}/approve")
def approve(briefing_id: str, body: ApproveIn, p: Principal = Depends(principal)):
    try:
        return service.approve(p, briefing_id, body.notes)
    except KeyError:
        raise HTTPException(404, "briefing not found")


@app.get("/api/briefings/{briefing_id}/export", response_class=PlainTextResponse)
def export(briefing_id: str, p: Principal = Depends(principal)):
    return service.export_markdown(p, briefing_id)


@app.get("/api/clients/{client_id}/actions")
def actions(client_id: str, p: Principal = Depends(principal)):
    return service.list_actions(p, client_id)


@app.post("/api/actions")
def create_action(body: ActionIn, p: Principal = Depends(principal)):
    return service.create_action(p, body.client_id, body.title, body.due_date, body.origin)


@app.patch("/api/actions/{action_id}")
def update_action(action_id: str, body: ActionPatch, p: Principal = Depends(principal)):
    try:
        return service.update_action(p, action_id, body.status)
    except KeyError:
        raise HTTPException(404, "action not found")


@app.post("/api/clients/{client_id}/notes")
def notes(client_id: str, body: NotesIn, p: Principal = Depends(principal)):
    return service.capture_notes(p, client_id, body.text, body.meeting_date)


@app.post("/api/clients/{client_id}/ask")
def ask(client_id: str, body: AskIn, p: Principal = Depends(principal)):
    return service.ask(p, client_id, body.question)


@app.get("/api/platform/lineage")
def lineage(p: Principal = Depends(principal)):
    return T.get_lineage(p)


@app.get("/api/platform/data-quality")
def data_quality(p: Principal = Depends(principal)):
    with db.session() as conn:
        rows = db.rows(conn, "SELECT * FROM dq_issues ORDER BY severity, issue_id")
        xwalk = db.rows(conn, "SELECT * FROM crosswalk ORDER BY status DESC, source")
    visible = [r for r in rows if r["client_id"] is None or p.can_see_client(r["client_id"])]
    xw = [r for r in xwalk if r["client_id"] is None or p.can_see_client(r["client_id"])]
    return dict(issues=visible, crosswalk=xw)


@app.get("/api/platform/audit")
def audit_log(p: Principal = Depends(principal)):
    with db.session() as conn:
        rows = db.rows(conn, "SELECT * FROM audit_log ORDER BY ts DESC LIMIT 200")
    if p.all_clients:  # supervisory role sees everything
        return rows
    return [r for r in rows if r["user_id"] == p.user_id]


@app.get("/api/platform/resolve")
def resolve(ref: str, p: Principal = Depends(principal)):
    return service.resolve_preview(ref)


@app.get("/api/evals/latest")
def evals_latest():
    path = config.EVALS_DIR / "results" / "latest.json"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "no eval run yet - run `python -m evals.run_evals`"})
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/admin/reset")
def reset(p: Principal = Depends(principal)):
    """Rebuild the demo store from the raw synthetic pack (clears app actions, notes and briefings)."""
    report = pipeline.run(regenerate=True, verbose=False)
    service.audit(p.user_id, "admin.reset", None, dict(dq_issues=report["dq_issues"]))
    return report
