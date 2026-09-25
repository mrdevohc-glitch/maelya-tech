"""Outil d'ecriture pour les agents marketing : ecrit TOUJOURS sous output/marketing/,
independamment du repertoire de travail de l'equipe code (common/workdir.py). C'est le seul
outil d'ecriture donne aux agents marketing, et ils n'ont aucun outil reseau/shell -- la regle
"brouillons uniquement, jamais d'envoi reel" est donc garantie par la structure, pas juste
par une instruction dans le prompt."""
from __future__ import annotations

from langchain_core.tools import tool

from common.paths import OUTPUT_DIR

_MARKETING_OUTPUT = OUTPUT_DIR / "marketing"


@tool
def write_draft(filename: str, content: str) -> str:
    """Enregistre un brouillon (sequence email, post, audit SEO, creation pub...) en local sous
    output/marketing/. N'envoie et ne publie jamais rien -- ecrit uniquement un fichier."""
    target = (_MARKETING_OUTPUT / filename).resolve()
    if target != _MARKETING_OUTPUT and _MARKETING_OUTPUT not in target.parents:
        return "ERREUR: chemin en dehors de output/marketing/ refuse."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: brouillon enregistre dans output/marketing/{filename}"
