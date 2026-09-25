"""Vrais appels a l'API WhatsApp Business Platform (meme API Graph que Facebook/Instagram,
graph.facebook.com). Identifiants au niveau PLATEFORME (pas par client -- un seul numero
WhatsApp pour toute l'agence) : WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN,
WHATSAPP_APP_SECRET, WHATSAPP_WEBHOOK_VERIFY_TOKEN dans .env. Demarche manuelle cote Meta
(ajouter le produit "WhatsApp Business Platform" a l'app Meta for Developers existante) --
voir README.

send_message() est utilise pour des notifications a contenu FIXE/gabarit uniquement -- jamais
pour envoyer du texte libre genere par un agent sans relecture humaine (voir webapp/job_runner.py
et tools/publishing|deployment/staging.py pour les points d'appel)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

import requests

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
_TIMEOUT_SECONDS = 15

logger = logging.getLogger(__name__)


def send_message(to: str, text: str) -> None:
    """Envoie un message WhatsApp texte. N'echoue JAMAIS bruyamment si WhatsApp n'est pas
    configure (WHATSAPP_ACCESS_TOKEN absent) -- une notification manquee ne doit jamais faire
    echouer un job ou une action reelle par ailleurs correctement executee."""
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    if not phone_number_id or not token:
        logger.info("WhatsApp non configure -- notification ignoree (to=%s)", to)
        return
    try:
        response = requests.post(
            f"{_GRAPH_API_BASE}/{phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT_SECONDS,
        )
        if not response.ok:
            logger.warning("Envoi WhatsApp echoue (%s): %s", response.status_code, response.text)
    except requests.RequestException:
        logger.warning("Envoi WhatsApp echoue (reseau)", exc_info=True)


def verify_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Verifie l'en-tete X-Hub-Signature-256 envoye par Meta (HMAC-SHA256 du corps brut avec
    WHATSAPP_APP_SECRET). CRITIQUE : sans cette verification, n'importe qui pourrait forger une
    requete pretendant venir du numero du proprietaire et obtenir un acces "pilotage complet"."""
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not secret or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
