"""FastAPI : tableau de bord web pour piloter l'equipe d'agents a distance.

Lancement local : .venv\\Scripts\\python.exe -m uvicorn webapp.app:app --reload
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from common.crypto import encrypt_json
from common.paths import AGENTS_ROOT, OUTPUT_DIR
from tools.publishing.image_gen import IMAGES_DIR
from webapp import db
from webapp.rate_limit import RateLimiter
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

# /media sert les images publicitaires generees (output/marketing/images/) SANS authentification
# -- delibere : Meta doit pouvoir recuperer l'image pour publier sur Instagram, et n'a evidemment
# pas notre cookie de session. Les noms de fichiers sont des UUID (voir tools/publishing/
# image_gen.py), donc pas devinables/enumerables ; aucune autre donnee de l'app n'est exposee ici.
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(IMAGES_DIR)), name="media")


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


# --- Portail public /demande (cahier des charges/devis automatique pour un prospect) ---
# Route SANS AuthDependency par design : c'est le lien qu'on transmet a un client potentiel, pas
# a soi-meme. Voir le plan de securite : research_agent est invoque en isolation (job_runner.py),
# jamais le supervisor complet, pour qu'un brief malveillant ne puisse jamais atteindre un agent
# avec outil shell. Cloudflare Access doit avoir une regle "Bypass" dediee sur ce chemin, sinon
# le mur de connexion de studio.maelya.tech bloquerait aussi les vrais prospects.

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_intake_rate_limiter = RateLimiter(max_attempts=3, window_seconds=3600)
_MAX_BRIEF_CHARS = 4000
_MAX_INTAKE_PER_DAY = 20


def _verify_turnstile(token: str, remote_ip: str) -> bool:
    secret = os.environ.get("TURNSTILE_SECRET_KEY", "")
    if not secret:
        return False
    try:
        response = requests.post(
            _TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=10,
        )
        return bool(response.json().get("success"))
    except requests.RequestException:
        return False


def _intake_form_context(error: str | None) -> dict:
    return {"error": error, "turnstile_site_key": os.environ.get("TURNSTILE_SITE_KEY", "")}


def _create_intake(
    name: str, contact_email: str, company: str, brief: str, contact_phone: str | None = None
) -> str:
    """Transforme un brief (venu du formulaire web OU du webhook WhatsApp) en client + job
    'intake' + ligne intake_submissions -- source unique de verite pour ce chemin, pour que les
    deux canaux restent strictement equivalents en termes de securite (research_agent seul,
    jamais le supervisor complet -- voir job_runner.py::_run_intake_job)."""
    from tools.messaging.whatsapp_client import send_message

    client_id = db.create_client(company or name, whatsapp_number=contact_phone)
    source = "WhatsApp" if contact_phone else "le portail public"
    brief_prompt = (
        f"Nouvelle demande recue via {source}.\n"
        f"Contact : {name} <{contact_email}>" + (f" -- {company}" if company else "") + "\n\n"
        f"Besoin decrit par le prospect :\n{brief}"
    )
    project_dir = OUTPUT_DIR / "intake" / uuid.uuid4().hex[:12]
    job_id = db.create_job(kind="intake", task=brief_prompt, project_dir=str(project_dir), client_id=client_id)
    submission_id = db.create_intake_submission(
        client_id, name, contact_email, company, brief, job_id, contact_phone=contact_phone
    )

    owner_number = os.environ.get("OWNER_WHATSAPP_NUMBER", "")
    if owner_number:
        send_message(owner_number, f"Nouvelle demande recue ({source}) : {name}" + (f" -- {company}" if company else ""))
    if contact_phone:
        send_message(contact_phone, "Merci ! Ta demande a bien ete recue, on revient vers toi tres vite.")

    return submission_id


@app.get("/demande", response_class=HTMLResponse)
def intake_form(request: Request):
    return templates.TemplateResponse(request, "demande.html", _intake_form_context(None))


@app.get("/demande/merci", response_class=HTMLResponse)
def intake_thanks(request: Request):
    return templates.TemplateResponse(request, "demande_merci.html", {})


@app.post("/demande", response_class=HTMLResponse)
def intake_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: str = Form(""),
    brief: str = Form(...),
    turnstile_token: str = Form("", alias="cf-turnstile-response"),
):
    ip = _client_ip(request)

    if not _intake_rate_limiter.is_allowed(ip):
        return templates.TemplateResponse(
            request, "demande.html", _intake_form_context("Trop de demandes recentes depuis cette adresse -- reessaie plus tard."), status_code=429
        )
    if not _verify_turnstile(turnstile_token, ip):
        return templates.TemplateResponse(
            request, "demande.html", _intake_form_context("Verification anti-robot echouee -- reessaie."), status_code=400
        )
    if db.count_intake_submissions_today() >= _MAX_INTAKE_PER_DAY:
        return templates.TemplateResponse(
            request, "demande.html", _intake_form_context("Trop de demandes recues aujourd'hui -- reessaie demain ou contacte-nous directement."), status_code=429
        )

    name, email, company, brief = name.strip(), email.strip(), company.strip(), brief.strip()
    if not name or not email or not brief:
        return templates.TemplateResponse(
            request, "demande.html", _intake_form_context("Merci de remplir tous les champs obligatoires."), status_code=400
        )
    if len(brief) > _MAX_BRIEF_CHARS:
        return templates.TemplateResponse(
            request, "demande.html", _intake_form_context(f"Description trop longue (max {_MAX_BRIEF_CHARS} caracteres)."), status_code=400
        )

    _intake_rate_limiter.record(ip)
    _create_intake(name, email, company, brief)
    return RedirectResponse("/demande/merci", status_code=303)


# --- Webhook WhatsApp (pilotage proprietaire + prise de contact clients/prospects) ---
# Route SANS AuthDependency par design (Meta appelle ce webhook, pas un navigateur avec cookie
# de session) -- Cloudflare Access doit avoir une regle "Bypass" dediee sur ce chemin, comme
# pour /demande, /media et /static.

_whatsapp_sender_rate_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
_WHATSAPP_HELP_TEXT = (
    "Pour piloter les agents, commence ton message par 'code:' ou 'marketing:' suivi de "
    "l'instruction. Exemple : code: cree un site vitrine pour un artisan plombier"
)


@app.get("/webhooks/whatsapp")
def whatsapp_webhook_verify(request: Request):
    """Poignee de main initiale exigee par Meta lors de la configuration du webhook."""
    expected = os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
    if (
        expected
        and request.query_params.get("hub.mode") == "subscribe"
        and request.query_params.get("hub.verify_token") == expected
    ):
        return PlainTextResponse(request.query_params.get("hub.challenge", ""))
    return HTMLResponse("Verification refusee", status_code=403)


def _handle_owner_whatsapp_command(sender: str, text: str) -> None:
    from tools.messaging.whatsapp_client import send_message

    lowered = text.lower()
    if lowered.startswith("code:"):
        db.create_job(kind="code", task=text[len("code:"):].strip())
        send_message(sender, "OK, nouvelle tache 'code' lancee -- suis-la sur le tableau de bord.")
    elif lowered.startswith("marketing:"):
        db.create_job(kind="marketing", task=text[len("marketing:"):].strip(), thread="whatsapp")
        send_message(sender, "OK, nouvelle tache 'marketing' lancee -- suis-la sur le tableau de bord.")
    else:
        send_message(sender, _WHATSAPP_HELP_TEXT)


def _handle_unknown_whatsapp_message(sender: str, sender_name: str, text: str) -> None:
    """Expediteur inconnu = prospect/client -- traite EXACTEMENT comme /demande (voir
    _create_intake) : jamais le supervisor complet, un seul aller-retour."""
    from tools.messaging.whatsapp_client import send_message

    if not _whatsapp_sender_rate_limiter.is_allowed(sender):
        send_message(sender, "Trop de messages recents -- reessaie plus tard.")
        return
    if db.count_intake_submissions_today() >= _MAX_INTAKE_PER_DAY:
        send_message(sender, "Trop de demandes recues aujourd'hui -- reessaie demain.")
        return
    if len(text) > _MAX_BRIEF_CHARS:
        send_message(sender, f"Message trop long (max {_MAX_BRIEF_CHARS} caracteres).")
        return
    _whatsapp_sender_rate_limiter.record(sender)
    _create_intake(sender_name or sender, f"whatsapp:{sender}", "", text, contact_phone=sender)


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    from tools.messaging.whatsapp_client import verify_webhook_signature

    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    # CRITIQUE : sans cette verification, n'importe qui pourrait forger une requete pretendant
    # venir du numero du proprietaire et obtenir un acces "pilotage complet" des agents.
    if not verify_webhook_signature(body, signature):
        return JSONResponse({"error": "signature invalide"}, status_code=401)

    payload = await request.json()
    owner_number = os.environ.get("OWNER_WHATSAPP_NUMBER", "")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contact_names = {
                c.get("wa_id"): c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
            }
            for message in value.get("messages", []):
                sender = message.get("from", "")
                text = message.get("text", {}).get("body", "").strip()
                if not sender or not text:
                    continue
                if owner_number and sender == owner_number:
                    _handle_owner_whatsapp_command(sender, text)
                else:
                    _handle_unknown_whatsapp_message(sender, contact_names.get(sender, ""), text)

    return JSONResponse({"status": "ok"})


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
            "submissions_count": len(db.list_intake_submissions()),
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
        client_id=client_id.strip() or None,
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


@app.post("/clients/{client_id}/whatsapp", dependencies=[AuthDependency])
def update_client_whatsapp_form(client_id: str, whatsapp_number: str = Form("")):
    db.update_client_whatsapp_number(client_id, whatsapp_number.strip() or None)
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


@app.post("/clients/{client_id}/credentials/vercel", dependencies=[AuthDependency])
def save_vercel_credentials_form(
    client_id: str,
    api_token: str = Form(...),
    team_id: str = Form(""),
):
    payload = {"api_token": api_token.strip()}
    if team_id.strip():
        payload["team_id"] = team_id.strip()
    db.save_client_credentials(client_id, "vercel", encrypt_json(payload))
    return RedirectResponse(f"/clients/{client_id}", status_code=303)


# --- Demandes recues via /demande (lecture admin, authentifiee) ---

@app.get("/submissions", response_class=HTMLResponse, dependencies=[AuthDependency])
def submissions_page(request: Request):
    return templates.TemplateResponse(
        request, "submissions.html", {"submissions": db.list_intake_submissions()}
    )


@app.get("/submissions/{submission_id}", response_class=HTMLResponse, dependencies=[AuthDependency])
def submission_detail_page(request: Request, submission_id: str):
    submission = db.get_intake_submission(submission_id)
    if submission is None:
        return HTMLResponse("Demande introuvable", status_code=404)
    job = db.get_job(submission["job_id"]) if submission["job_id"] else None
    docs: dict[str, str] = {}
    if job is not None and job["project_dir"]:
        docs_dir = Path(job["project_dir"]) / "docs"
        if docs_dir.is_dir():
            for doc_file in sorted(docs_dir.glob("*.md")):
                docs[doc_file.name] = doc_file.read_text(encoding="utf-8", errors="replace")
    return templates.TemplateResponse(
        request,
        "submission_detail.html",
        {"submission": submission, "job": job, "docs": docs, "client_id": submission["client_id"]},
    )


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


# --- Tests d'intrusion (scans actifs sur cibles explicitement autorisees) ---

@app.get("/security", response_class=HTMLResponse, dependencies=[AuthDependency])
def security_page(request: Request):
    targets = [dict(t) for t in db.list_scan_targets()]
    for target in targets:
        results = db.list_scan_results(target["id"], limit=2)
        target["last_results"] = results
    return templates.TemplateResponse(
        request, "security.html", {"targets": targets, "clients": db.list_clients()}
    )


@app.post("/security/targets", dependencies=[AuthDependency])
def create_scan_target_form(
    target_type: str = Form(...),
    hostname: str = Form(...),
    url: str = Form(...),
    authorized_note: str = Form(...),
    client_id: str = Form(""),
):
    if not authorized_note.strip():
        return HTMLResponse(
            "La confirmation d'autorisation est obligatoire -- retour /security", status_code=400
        )
    db.create_scan_target(
        target_type=target_type,
        hostname=hostname.strip(),
        url=url.strip(),
        authorized_note=authorized_note.strip(),
        client_id=client_id.strip() or None,
    )
    return RedirectResponse("/security", status_code=303)


@app.get("/security/results/{result_id}", response_class=HTMLResponse, dependencies=[AuthDependency])
def scan_result_page(request: Request, result_id: str):
    result = db.get_scan_result(result_id)
    if result is None:
        return HTMLResponse("Resultat introuvable", status_code=404)
    target = db.get_scan_target(result["target_id"])
    return templates.TemplateResponse(
        request, "security_result.html", {"result": result, "target": target}
    )


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
