"""Outil de mise en attente d'un deploiement reel (Vercel) pour l'agent test_deploy_agent.
N'appelle JAMAIS une vraie API externe -- enregistre une action dans webapp.db.pending_actions
et rend la main a l'agent. L'execution reelle ne se fait qu'apres validation humaine dans le
tableau de bord (/approvals), par tools/publishing/executor.py -- jamais directement par un
agent/modele."""
from __future__ import annotations

import json
import re

from langchain_core.tools import tool

from common.current_client import get_current_client
from common.workdir import get_working_directory
from webapp import db


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "projet"


@tool
def stage_vercel_deploy() -> str:
    """Met en attente d'approbation un deploiement reel du projet en cours sur Vercel, pour le
    client courant. Ne deploie JAMAIS directement -- necessite une validation humaine avant de
    partir. Ne prend pas de chemin en argument : deploie toujours le dossier de travail actuel
    (jamais un chemin fourni par le modele)."""
    client_id = get_current_client()
    if not client_id:
        return (
            "ERREUR: aucun client selectionne pour cette conversation -- impossible de mettre "
            "en attente un deploiement reel sans savoir pour quel client. Demande a "
            "l'utilisateur de relancer ce job avec un client choisi dans le tableau de bord."
        )
    project_dir = get_working_directory()
    project_name = _slugify(project_dir.name)
    payload = {"project_dir": str(project_dir), "project_name": project_name}
    action_id = db.create_pending_action(client_id, "vercel", "deploy", json.dumps(payload))
    return (
        f"OK: deploiement mis en attente d'approbation (id={action_id}, projet='{project_name}'). "
        f"Rien n'est deploye -- l'utilisateur doit valider dans /approvals avant que ca parte "
        f"reellement. Dis-le clairement, ne dis jamais que c'est deploye."
    )
