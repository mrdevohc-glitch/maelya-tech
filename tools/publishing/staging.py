"""Outils de mise en attente d'actions reelles (publication de post) pour les agents
marketing. Ces outils n'appellent JAMAIS une vraie API externe -- ils enregistrent une action
dans webapp.db.pending_actions et rendent la main a l'agent. L'execution reelle ne se fait
qu'apres validation humaine dans le tableau de bord (/approvals), par
tools/publishing/executor.py -- jamais directement par un agent/modele."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from common.current_client import get_current_client
from webapp import db


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

    LIMITE CONNUE : l'API Instagram exige une URL d'image publiquement accessible, pas un
    fichier local -- l'executeur devra heberger l'image (ex: via le tableau de bord une fois
    deploye publiquement) avant de pouvoir vraiment publier. Voir tools/publishing/meta_client.py.
    """
    return _stage("meta", "post", {"surface": "instagram", "caption": caption, "image_path": image_path})
