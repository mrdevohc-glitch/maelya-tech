"""Chargement du profil business (context/business.md, ou celui d'un client) pour les agents
marketing/contenu."""
from __future__ import annotations

from common.paths import CONTEXT_DIR

_BUSINESS_PATH = CONTEXT_DIR / "business.md"


def load_business_context(client_id: str | None = None) -> str:
    """Sans client_id : comportement historique (context/business.md, usage CLI sans client).
    Avec client_id : lit le profil stocke pour ce client (webapp.db.clients.business_profile).
    """
    if client_id:
        from webapp import db  # import tardif : evite un cycle commun/webapp au chargement

        client = db.get_client(client_id)
        if client is None:
            return f"[Client '{client_id}' introuvable]"
        profile = (client["business_profile"] or "").strip()
        return profile or f"[Profil business vide pour le client '{client['name']}']"

    if not _BUSINESS_PATH.exists():
        return "[Aucun profil business renseigne -- voir context/business.md]"
    text = _BUSINESS_PATH.read_text(encoding="utf-8").strip()
    return text or "[context/business.md existe mais est vide -- remplis-le pour de meilleurs brouillons]"
