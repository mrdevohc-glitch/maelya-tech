"""Execute une action reelle (publication) apres validation humaine explicite. JAMAIS appele
par un agent/modele -- uniquement par webapp/job_runner.py (job kind='execute_action'), lui-
meme declenche uniquement quand l'utilisateur clique "Approuver" dans /approvals."""
from __future__ import annotations

import json

from common.crypto import decrypt_json
from tools.publishing import meta_client
from webapp import db


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
        raise NotImplementedError(
            "Publication Instagram pas encore active : l'API Instagram exige une URL d'image "
            "publiquement accessible, pas un fichier local -- a completer une fois le tableau "
            "de bord deploye publiquement (voir la limite documentee dans "
            "tools/publishing/staging.py)."
        )

    raise ValueError(f"Combinaison plateforme/surface non supportee: {platform}/{surface}")
