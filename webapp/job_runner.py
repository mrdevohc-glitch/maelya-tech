"""Worker unique en arriere-plan qui execute les jobs un par un.

Reproduit volontairement le glue de cli.py (set_working_directory -> SqliteSaver ->
build_supervisor(checkpointer).invoke(...)) au lieu de l'importer depuis cli.py, pour que
cli.py reste 100% autonome et continue de fonctionner seul en ligne de commande sans dependre
de ce module.

Un seul thread traite les jobs sequentiellement (jamais deux en parallele) : common/workdir.py
et common/guardrails.py utilisent des variables globales de process, pas isolees par thread --
executer un seul job a la fois evite toute fuite d'etat entre deux jobs sans avoir a toucher
a ce code existant.
"""
from __future__ import annotations

import re
import threading
import time
import traceback
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from common.current_client import set_current_client
from common.guardrails import set_allow_push
from common.models import get_max_iterations
from common.paths import OUTPUT_DIR
from common.usage_tracking import usage_callbacks
from common.workdir import set_working_directory
from webapp import db

_POLL_INTERVAL_SECONDS = 2
_SECURITY_SCHEDULER_INTERVAL_SECONDS = 3600  # verifie une fois par heure quelles cibles sont dues
_SECURITY_SCAN_MAX_AGE_DAYS = 7
_MARKETING_PLAN_SCHEDULER_INTERVAL_SECONDS = 3600  # verifie une fois par heure quels plans sont dus


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "projet"


def _final_message_text(result: dict) -> str:
    messages = result.get("messages", [])
    if not messages:
        return "(aucune reponse)"
    content = getattr(messages[-1], "content", messages[-1])
    return content if isinstance(content, str) else str(content)


def _run_code_job(row) -> str:
    from coding_team.supervisor import build_supervisor

    set_allow_push(bool(row["allow_push"]))
    set_current_client(row["client_id"])  # lu par tools/deployment/staging.py
    project_dir = (
        Path(row["project_dir"]) if row["project_dir"] else OUTPUT_DIR / "projects" / _slugify(row["task"])
    )
    resolved = set_working_directory(project_dir)

    checkpoint_db = resolved / ".state" / "conversation.sqlite"
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

    max_iterations = row["max_iterations"] or get_max_iterations("coding_supervisor") * 6

    with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
        supervisor = build_supervisor(checkpointer=checkpointer)
        result = supervisor.invoke(
            {"messages": [{"role": "user", "content": row["task"]}]},
            config={
                "recursion_limit": max_iterations,
                "callbacks": usage_callbacks("coding_supervisor"),
                "configurable": {"thread_id": "main"},
            },
        )
    return f"[repertoire: {resolved}]\n\n{_final_message_text(result)}"


def _run_marketing_job(row) -> str:
    from marketing_team.supervisor import build_supervisor

    set_current_client(row["client_id"])  # lu par tools/publishing/staging.py

    thread = row["thread"] or "default"
    marketing_dir = OUTPUT_DIR / "marketing"
    checkpoint_db = marketing_dir / ".state" / f"conversation-{thread}.sqlite"
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

    max_iterations = row["max_iterations"] or get_max_iterations("marketing_supervisor") * 6

    with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
        supervisor = build_supervisor(checkpointer=checkpointer)
        result = supervisor.invoke(
            {"messages": [{"role": "user", "content": row["task"]}]},
            config={
                "recursion_limit": max_iterations,
                "callbacks": usage_callbacks("marketing_supervisor"),
                "configurable": {"thread_id": thread},
            },
        )
    return _final_message_text(result)


def _run_intake_job(row) -> str:
    """kind='intake' : brief soumis via le formulaire public /demande. Appelle
    coding_team.research_agent.build_agent() DIRECTEMENT -- jamais build_supervisor() -- pour
    qu'un brief ecrit par un inconnu sur internet ne puisse JAMAIS router vers un agent avec
    outil shell (backend/frontend/test_deploy). Un seul aller-retour, pas de conversation
    continue avec un anonyme."""
    from coding_team.research_agent import build_agent

    resolved = set_working_directory(Path(row["project_dir"]))
    agent = build_agent()
    # research_agent est normalement invoque plusieurs fois de suite (une fois par tour de
    # conversation avec un humain qui repond aux questions), chaque appel disposant de son
    # propre budget de config/models.yaml. Ici, pas d'humain pour repondre entre deux appels --
    # il doit produire les 4 documents en UN SEUL passage, donc budget double.
    result = agent.invoke(
        {"messages": [{"role": "user", "content": row["task"]}]},
        config={
            "recursion_limit": get_max_iterations("research_agent") * 2,
            "callbacks": usage_callbacks("research_agent"),
        },
    )
    return f"[repertoire: {resolved}]\n\n{_final_message_text(result)}"


def _run_execute_action_job(row) -> str:
    """kind='execute_action' : le champ `task` contient l'id de l'action a executer (pas une
    instruction en langage naturel). Ne passe JAMAIS par un modele -- appelle directement
    l'executeur deterministe, uniquement pour une action deja approuvee par un humain."""
    from tools.publishing.executor import execute_action

    return execute_action(row["task"])


def _run_security_scan_job(row) -> str:
    """kind='security_scan' : le champ `task` contient l'id d'une ligne scan_targets (jamais
    un hostname/URL en clair -- toujours relu depuis la table des cibles explicitement
    autorisees). Aucun LLM implique -- deterministe, comme execute_action."""
    from tools.security_active_scan import run_port_scan, run_web_vuln_scan

    target = db.get_scan_target(row["task"])
    if target is None:
        raise ValueError(f"Cible de scan introuvable: {row['task']}")

    port_result = run_port_scan(target["hostname"])
    db.create_scan_result(target["id"], "port", port_result)

    web_result = run_web_vuln_scan(target["url"])
    db.create_scan_result(target["id"], "web_vuln", web_result)

    db.mark_scan_target_scanned(target["id"])
    return f"Scan termine pour {target['hostname']}.\n\n[port]\n{port_result}\n\n[web]\n{web_result}"


def _sync_intake_status(job_id: str, status: str) -> None:
    """Un job kind='intake' est toujours lie a une ligne intake_submissions -- on la tient a
    jour en meme temps que le job pour que /submissions n'ait pas besoin de jointure."""
    submission = db.get_intake_submission_by_job(job_id)
    if submission is not None:
        db.update_intake_status(submission["id"], status)


def _notify_owner_job_done(row, status: str) -> None:
    """Notification WhatsApp au proprietaire (voir tools/messaging/whatsapp_client.py --
    silencieusement ignoree si WhatsApp n'est pas configure). Uniquement pour code/marketing --
    'intake' a deja sa propre notification a la creation (webapp/app.py::_create_intake)."""
    import os

    from tools.messaging.whatsapp_client import send_message

    owner_number = os.environ.get("OWNER_WHATSAPP_NUMBER", "")
    if not owner_number or row["kind"] not in ("code", "marketing"):
        return
    apercu = row["task"][:80] + ("..." if len(row["task"]) > 80 else "")
    send_message(owner_number, f"Job {row['kind']} {status} : {apercu}")


def _notify_client_intake_ready(job_id: str) -> None:
    """Statut fixe uniquement, jamais le contenu genere -- coherent avec la relecture humaine
    obligatoire avant tout envoi reel au client (voir webapp/app.py::_create_intake)."""
    from tools.messaging.whatsapp_client import send_message

    submission = db.get_intake_submission_by_job(job_id)
    if submission is None:
        return
    client = db.get_client(submission["client_id"])
    if client is not None and client["whatsapp_number"]:
        send_message(client["whatsapp_number"], "Ton cahier des charges est pret -- on revient vers toi tres vite.")


def _process_one(row) -> None:
    if row["kind"] == "intake":
        _sync_intake_status(row["id"], "running")
    try:
        if row["kind"] == "code":
            result = _run_code_job(row)
        elif row["kind"] == "marketing":
            result = _run_marketing_job(row)
        elif row["kind"] == "intake":
            result = _run_intake_job(row)
        elif row["kind"] == "execute_action":
            result = _run_execute_action_job(row)
        elif row["kind"] == "security_scan":
            result = _run_security_scan_job(row)
        else:
            raise ValueError(f"Type de job inconnu: {row['kind']!r}")
        db.mark_succeeded(row["id"], result)
        if row["kind"] == "intake":
            _sync_intake_status(row["id"], "succeeded")
            _notify_client_intake_ready(row["id"])
        _notify_owner_job_done(row, "termine")
    except Exception:  # noqa: BLE001 -- un job en echec ne doit jamais arreter le worker
        db.mark_failed(row["id"], traceback.format_exc())
        if row["kind"] == "intake":
            _sync_intake_status(row["id"], "failed")
        _notify_owner_job_done(row, "en echec")


def _worker_loop() -> None:
    while True:
        row = db.claim_next_queued_job()
        if row is not None:
            _process_one(row)
        else:
            time.sleep(_POLL_INTERVAL_SECONDS)


def _security_scheduler_loop() -> None:
    """Verifie periodiquement quelles cibles (webapp.db.scan_targets, toujours explicitement
    autorisees a l'ajout -- voir /security) n'ont pas ete scannees depuis 7 jours, et cree un
    job kind='security_scan' pour chacune. Ne lit et n'ecrit QUE cette table -- aucune cible
    ne peut venir d'ailleurs (agent, portail public, etc.)."""
    while True:
        try:
            for target in db.list_due_scan_targets(_SECURITY_SCAN_MAX_AGE_DAYS):
                if not db.has_pending_security_scan(target["id"]):
                    db.create_job(kind="security_scan", task=target["id"])
        except Exception:  # noqa: BLE001 -- le planificateur ne doit jamais s'arreter
            traceback.print_exc()
        time.sleep(_SECURITY_SCHEDULER_INTERVAL_SECONDS)


def _marketing_plan_scheduler_loop() -> None:
    """Verifie periodiquement quels plans marketing (webapp.db.marketing_plans, definis par
    client sur /clients/<id>) sont dus pour leur cadence propre, et cree un job kind='marketing'
    pour chacun. Le job passe par le meme pipeline stage->approve->execute que tout job manuel
    -- aucune nouvelle regle de securite, juste un declencheur automatique."""
    while True:
        try:
            for plan in db.list_due_marketing_plans():
                if not db.has_pending_marketing_plan_job(plan["id"]):
                    db.create_job(
                        kind="marketing", task=plan["brief_template"],
                        client_id=plan["client_id"], thread=f"plan-{plan['id']}", plan_id=plan["id"],
                    )
                    db.mark_marketing_plan_run(plan["id"])
        except Exception:  # noqa: BLE001 -- le planificateur ne doit jamais s'arreter
            traceback.print_exc()
        time.sleep(_MARKETING_PLAN_SCHEDULER_INTERVAL_SECONDS)


def start_background_worker() -> threading.Thread:
    """A appeler une fois au demarrage du serveur (voir webapp/app.py)."""
    thread = threading.Thread(target=_worker_loop, name="job-worker", daemon=True)
    thread.start()
    threading.Thread(target=_security_scheduler_loop, name="security-scheduler", daemon=True).start()
    threading.Thread(target=_marketing_plan_scheduler_loop, name="marketing-plan-scheduler", daemon=True).start()
    return thread
