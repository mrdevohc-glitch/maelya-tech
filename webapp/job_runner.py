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


def _run_execute_action_job(row) -> str:
    """kind='execute_action' : le champ `task` contient l'id de l'action a executer (pas une
    instruction en langage naturel). Ne passe JAMAIS par un modele -- appelle directement
    l'executeur deterministe, uniquement pour une action deja approuvee par un humain."""
    from tools.publishing.executor import execute_action

    return execute_action(row["task"])


def _process_one(row) -> None:
    try:
        if row["kind"] == "code":
            result = _run_code_job(row)
        elif row["kind"] == "marketing":
            result = _run_marketing_job(row)
        elif row["kind"] == "execute_action":
            result = _run_execute_action_job(row)
        else:
            raise ValueError(f"Type de job inconnu: {row['kind']!r}")
        db.mark_succeeded(row["id"], result)
    except Exception:  # noqa: BLE001 -- un job en echec ne doit jamais arreter le worker
        db.mark_failed(row["id"], traceback.format_exc())


def _worker_loop() -> None:
    while True:
        row = db.claim_next_queued_job()
        if row is not None:
            _process_one(row)
        else:
            time.sleep(_POLL_INTERVAL_SECONDS)


def start_background_worker() -> threading.Thread:
    """A appeler une fois au demarrage du serveur (voir platform/app.py)."""
    thread = threading.Thread(target=_worker_loop, name="job-worker", daemon=True)
    thread.start()
    return thread
