"""Outils de mise en attente d'actions reelles (publication de post) pour les agents
marketing. Ces outils n'appellent JAMAIS une vraie API externe -- ils enregistrent une action
dans webapp.db.pending_actions et rendent la main a l'agent. L'execution reelle ne se fait
qu'apres validation humaine dans le tableau de bord (/approvals), par
tools/publishing/executor.py -- jamais directement par un agent/modele."""
from __future__ import annotations

import json
import os

from langchain_core.tools import tool

from common.current_client import get_current_client
from webapp import db


def _notify_owner_pending_action(client_id: str, platform: str, action_type: str) -> None:
    from tools.messaging.whatsapp_client import send_message

    owner_number = os.environ.get("OWNER_WHATSAPP_NUMBER", "")
    if not owner_number:
        return
    client = db.get_client(client_id)
    client_name = client["name"] if client else client_id
    send_message(
        owner_number,
        f"Nouvelle action en attente d'approbation ({platform}/{action_type}) pour {client_name} -- voir /approvals.",
    )


def _stage(platform: str, action_type: str, payload: dict) -> str:
    client_id = get_current_client()
    if not client_id:
        return (
            "ERREUR: aucun client selectionne pour cette conversation -- impossible de mettre "
            "en attente une publication reelle sans savoir pour quel client. Utilise write_draft "
            "en attendant, ou demande a l'utilisateur de relancer ce job avec un client choisi "
            "dans le tableau de bord."
        )
    action_id = db.create_pending_action(client_id, platform, action_type, json.dumps(payload))
    _notify_owner_pending_action(client_id, platform, action_type)
    return (
        f"OK: mis en attente d'approbation (id={action_id}). Rien n'est publie -- l'utilisateur "
        f"doit valider dans /approvals avant que ca parte reellement. Dis-le clairement a "
        f"l'utilisateur, ne dis jamais que c'est publie."
    )


@tool
def stage_facebook_post(message: str) -> str:
    """Met en attente d'approbation un post texte pour la Page Facebook du client courant.
    Ne publie JAMAIS directement -- necessite une validation humaine avant de partir."""
    return _stage("meta", "post", {"surface": "facebook", "message": message})


@tool
def stage_instagram_post(caption: str, image_path: str) -> str:
    """Met en attente d'approbation un post Instagram (image + legende) pour le client
    courant. `image_path` doit etre le chemin d'une image deja generee (voir
    generate_ad_image). Ne publie JAMAIS directement -- necessite une validation humaine.

    L'image est servie publiquement (sans authentification) via /media/<nom-fichier> au moment
    de l'execution -- necessaire car l'API Instagram exige une URL publique, pas un fichier
    local (voir tools/publishing/executor.py et PLATFORM_PUBLIC_URL dans .env).
    """
    return _stage("meta", "post", {"surface": "instagram", "caption": caption, "image_path": image_path})
