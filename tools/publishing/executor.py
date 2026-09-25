"""Execute une action reelle (publication OU deploiement) apres validation humaine explicite.
JAMAIS appele par un agent/modele -- uniquement par webapp/job_runner.py (job
kind='execute_action'), lui-meme declenche uniquement quand l'utilisateur clique "Approuver"
dans /approvals. Point d'extension unique pour toute nouvelle plateforme (publication ou
deploiement) : ajouter un cas dans _dispatch() ci-dessous."""
from __future__ import annotations

import json
import os
from pathlib import Path

from common.crypto import decrypt_json
from tools.deployment import vercel_client
from tools.publishing import meta_client
from webapp import db


def _notify_client_whatsapp(client_id: str, text: str) -> None:
    """Statut fixe uniquement (jamais du contenu genere par un agent sans relecture -- voir
    tools/messaging/whatsapp_client.py). Ignore silencieusement si le client n'a pas de numero
    WhatsApp enregistre ou si WhatsApp n'est pas configure."""
    from tools.messaging.whatsapp_client import send_message

    client = db.get_client(client_id)
    if client is not None and client["whatsapp_number"]:
        send_message(client["whatsapp_number"], text)


def execute_action(action_id: str) -> str:
    action = db.get_pending_action(action_id)
    if action is None:
        raise ValueError(f"Action introuvable: {action_id}")
    if action["status"] != "approved":
        raise ValueError(
            f"Action {action_id} n'est pas approuvee (statut actuel: {action['status']}) -- "
            f"refus d'executer."
        )

    try:
        result = _dispatch(action)
    except Exception as exc:  # noqa: BLE001 -- on consigne l'echec puis on relance
        db.mark_action_failed(action_id, str(exc))
        raise
    db.mark_action_executed(action_id, result)
    return result


def _dispatch(action) -> str:
    payload = json.loads(action["payload_json"])
    platform = action["platform"]
    surface = payload.get("surface")

    encrypted = db.get_client_credentials(action["client_id"], platform)
    if encrypted is None:
        raise ValueError(f"Aucun identifiant enregistre pour ce client sur '{platform}'.")
    credentials = decrypt_json(encrypted)

    if platform == "meta" and surface == "facebook":
        post_id = meta_client.post_to_facebook_page(
            credentials["page_id"], credentials["access_token"], payload["message"]
        )
        return f"Publie sur Facebook, post_id={post_id}"

    if platform == "meta" and surface == "instagram":
        ig_user_id = credentials.get("ig_user_id")
        if not ig_user_id:
            raise ValueError(
                "Aucun 'ig_user_id' enregistre pour ce client -- requis pour publier sur "
                "Instagram (voir /clients/<id>, section identifiants Meta)."
            )
        public_url = os.environ.get("PLATFORM_PUBLIC_URL", "").rstrip("/")
        if not public_url:
            raise ValueError(
                "PLATFORM_PUBLIC_URL manquant dans .env -- necessaire pour construire une URL "
                "d'image publiquement accessible (contrainte de l'API Instagram)."
            )
        # Seul le nom de fichier est retenu (jamais le chemin fourni tel quel) : l'image doit
        # forcement venir de output/marketing/images/, jamais d'un chemin arbitraire.
        image_filename = Path(payload["image_path"]).name
        image_url = f"{public_url}/media/{image_filename}"
        post_id = meta_client.post_to_instagram(
            ig_user_id, credentials["access_token"], image_url, payload.get("caption", "")
        )
        return f"Publie sur Instagram, post_id={post_id}"

    if platform == "vercel" and action["action_type"] == "deploy":
        deployment_url = vercel_client.deploy_directory(
            payload["project_dir"], credentials["api_token"], payload["project_name"],
            team_id=credentials.get("team_id"),
        )
        _notify_client_whatsapp(action["client_id"], f"Ton site est en ligne : {deployment_url}")
        return f"Deploye sur Vercel : {deployment_url}"

    raise ValueError(f"Combinaison plateforme/surface non supportee: {platform}/{surface}")
