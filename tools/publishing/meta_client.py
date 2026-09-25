"""Vrais appels a l'API Graph de Meta (Facebook Page + Instagram). N'est JAMAIS importe par
un agent -- uniquement par tools/publishing/executor.py, apres validation humaine.

Identifiants attendus dans le payload chiffre du client (voir common/crypto.py), cle 'meta' :
{"page_id": "...", "access_token": "...", "ig_user_id": "..." (optionnel, requis pour Instagram)}

Jeton requis : un "Page Access Token" longue duree, obtenu via l'app Meta for Developers de
l'utilisateur (Facebook Login for Business + permission pages_manage_posts, et
instagram_content_publish si Instagram est utilise). Demarche manuelle cote Meta, hors de ce
code -- voir README pour le guide.
"""
from __future__ import annotations

import requests

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
_TIMEOUT_SECONDS = 30


class MetaAPIError(RuntimeError):
    pass


def _raise_for_graph_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except ValueError:
        detail = response.text
    raise MetaAPIError(f"Erreur API Meta ({response.status_code}): {detail}")


def post_to_facebook_page(page_id: str, access_token: str, message: str) -> str:
    """Publie un post texte sur une Page Facebook. Retourne l'id du post cree."""
    response = requests.post(
        f"{_GRAPH_API_BASE}/{page_id}/feed",
        data={"message": message, "access_token": access_token},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_graph_error(response)
    return response.json()["id"]


def post_to_instagram(ig_user_id: str, access_token: str, image_url: str, caption: str) -> str:
    """Publie une image + legende sur Instagram. `image_url` DOIT etre une URL publiquement
    accessible (contrainte de l'API Instagram -- pas de fichier local). Retourne l'id du post."""
    create = requests.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": access_token},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_graph_error(create)
    creation_id = create.json()["id"]

    publish = requests.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_graph_error(publish)
    return publish.json()["id"]
