"""FastAPI : tableau de bord web pour piloter l'equipe d'agents a distance.

Lancement local : .venv\\Scripts\\python.exe -m uvicorn webapp.app:app --reload
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from common.crypto import encrypt_json
from common.paths import AGENTS_ROOT
from webapp import db
from webapp.auth import (
    AuthDependency,
    clear_failed_attempts,
    get_or_create_secret_key,
    is_locked_out,
    register_failed_attempt,
    verify_password,
)
from webapp.job_runner import start_background_worker

load_dotenv(AGENTS_ROOT / ".env")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(title="Agents -- tableau de bord", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_or_create_secret_key(),
    same_site="lax",
    https_only=os.environ.get("PLATFORM_HTTPS_ONLY", "false").lower() == "true",
    max_age=30 * 24 * 3600,
)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.exception_handler(StarletteHTTPException)
async def auth_redirect_handler(request: Request, exc: StarletteHTTPException):
    """Un 401 sur une page HTML renvoie vers /login plutot qu'une erreur JSON brute ; un 401
    sur /api/* reste une vraie reponse JSON (consommateurs programmatiques)."""
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.on_event("startup")
def _on_startup() -> None:
    db.init_db()
    n = db.mark_interrupted_jobs_as_failed()
    if n:
        print(f"[webapp] {n} job(s) marque(s) 'echec' (interrompus par un redemarrage precedent)")
    start_background_worker()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    ip = _client_ip(request)
    if is_locked_out(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Trop de tentatives -- reessaie dans quelques minutes."},
            status_code=429,
        )
    if verify_password(password):
        clear_failed_attempts(ip)
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    register_failed_attempt(ip)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Mot de passe incorrect."}, status_code=401
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse, dependencies=[AuthDependency])
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "projects": db.list_projects(),
            "threads": db.list_marketing_threads(),
            "recent_jobs": db.list_jobs(limit=20),
            "clients": db.list_clients(),
            "pending_count": len(db.list_pending_actions(status="pending")),
        },
    )


@app.post("/jobs", dependencies=[AuthDependency])
def create_job_form(
    kind: str = Form(...),
    task: str = Form(...),
    project_dir: str = Form(""),
    thread: str = Form(""),
    client_id: str = Form(""),
    allow_push: str = Form(""),
):
    job_id = db.create_job(
        kind=kind,
        task=task,
        project_dir=(project_dir.strip() or None) if kind == "code" else None,
        thread=(thread.strip() or None) if kind == "marketing" else None,
        client_id=(client_id.strip() or None) if kind == "marketing" else None,
        allow_push=bool(allow_push),
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# --- Clients ---

@app.get("/clients", response_class=HTMLResponse, dependencies=[AuthDependency])
def clients_page(request: Request):
    clients = [dict(c) for c in db.list_clients()]
    for client in clients:
        client["platforms"] = db.list_client_platforms(client["id"])
    return templates.TemplateResponse(request, "clients.html", {"clients": clients})


@app.post("/clients", dependencies=[AuthDependency])
def create_client_form(name: str = Form(...)):
    client_id = db.create_client(name.strip())
    return RedirectResponse(f"/clients/{client_id}", status_code=303)


@app.get("/clients/{client_id}", response_class=HTMLResponse, dependencies=[AuthDependency])
def client_detail_page(request: Request, client_id: str):
    client = db.get_client(client_id)
    if client is None:
        return HTMLResponse("Client introuvable", status_code=404)
    return templates.TemplateResponse(
        request,
        "client_detail.html",
        {"client": client, "platforms": db.list_client_platforms(client_id)},
    )


@app.post("/clients/{client_id}/profile", dependencies=[AuthDependency])
def update_client_profile_form(client_id: str, business_profile: str = Form("")):
    db.update_client_profile(client_id, business_profile)
    return RedirectResponse(f"/clients/{client_id}", status_code=303)


@app.post("/clients/{client_id}/credentials/meta", dependencies=[AuthDependency])
def save_meta_credentials_form(
    client_id: str,
    page_id: str = Form(...),
    access_token: str = Form(...),
    ig_user_id: str = Form(""),
):
    payload = {"page_id": page_id.strip(), "access_token": access_token.strip()}
    if ig_user_id.strip():
        payload["ig_user_id"] = ig_user_id.strip()
    db.save_client_credentials(client_id, "meta", encrypt_json(payload))
    return RedirectResponse(f"/clients/{client_id}", status_code=303)


# --- Actions en attente d'approbation ---

@app.get("/approvals", response_class=HTMLResponse, dependencies=[AuthDependency])
def approvals_page(request: Request):
    actions = [dict(a) for a in db.list_pending_actions()]
    for action in actions:
        client = db.get_client(action["client_id"])
        action["client_name"] = client["name"] if client else "(client supprime)"
    return templates.TemplateResponse(request, "approvals.html", {"actions": actions})


@app.get("/approvals/{action_id}", response_class=HTMLResponse, dependencies=[AuthDependency])
def approval_detail_page(request: Request, action_id: str):
    action = db.get_pending_action(action_id)
    if action is None:
        return HTMLResponse("Action introuvable", status_code=404)
    client = db.get_client(action["client_id"])
    return templates.TemplateResponse(
        request,
        "approval_detail.html",
        {"action": action, "client_name": client["name"] if client else "(client supprime)"},
    )


@app.post("/approvals/{action_id}/approve", dependencies=[AuthDependency])
def approve_action(action_id: str):
    action = db.get_pending_action(action_id)
    if action is None:
        return HTMLResponse("Action introuvable", status_code=404)
    db.decide_pending_action(action_id, approved=True)
    # L'execution reelle passe par la meme file/le meme worker que les autres jobs (kind
    # dedie) -- jamais execute directement depuis la requete web, et jamais par un modele.
    db.create_job(kind="execute_action", task=action_id)
    return RedirectResponse(f"/approvals/{action_id}", status_code=303)


@app.post("/approvals/{action_id}/reject", dependencies=[AuthDependency])
def reject_action(action_id: str):
    action = db.get_pending_action(action_id)
    if action is None:
        return HTMLResponse("Action introuvable", status_code=404)
    db.decide_pending_action(action_id, approved=False)
    return RedirectResponse(f"/approvals/{action_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse, dependencies=[AuthDependency])
def job_page(request: Request, job_id: str):
    job = db.get_job(job_id)
    if job is None:
        return HTMLResponse("Job introuvable", status_code=404)
    return templates.TemplateResponse(request, "job_detail.html", {"job": job})


@app.get("/jobs/{job_id}/fragment", response_class=HTMLResponse, dependencies=[AuthDependency])
def job_fragment(request: Request, job_id: str):
    job = db.get_job(job_id)
    if job is None:
        return HTMLResponse("Job introuvable", status_code=404)
    return templates.TemplateResponse(request, "_job_status.html", {"job": job})


# --- API JSON (usage programmatique) ---

@app.post("/api/jobs", dependencies=[AuthDependency])
async def api_create_job(request: Request):
    payload = await request.json()
    job_id = db.create_job(
        kind=payload["kind"],
        task=payload["task"],
        project_dir=payload.get("project_dir"),
        thread=payload.get("thread"),
        allow_push=bool(payload.get("allow_push", False)),
        max_iterations=payload.get("max_iterations"),
    )
    return JSONResponse({"job_id": job_id})


@app.get("/api/jobs", dependencies=[AuthDependency])
def api_list_jobs(kind: str | None = None, status: str | None = None):
    return JSONResponse([dict(r) for r in db.list_jobs(kind=kind, status=status)])


@app.get("/api/jobs/{job_id}", dependencies=[AuthDependency])
def api_get_job(job_id: str):
    job = db.get_job(job_id)
    if job is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(dict(job))


@app.get("/api/projects", dependencies=[AuthDependency])
def api_projects():
    return JSONResponse(db.list_projects())


@app.get("/api/marketing/threads", dependencies=[AuthDependency])
def api_marketing_threads():
    return JSONResponse(db.list_marketing_threads())
