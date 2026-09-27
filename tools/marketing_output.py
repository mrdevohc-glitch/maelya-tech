"""Outil d'ecriture pour les agents marketing : ecrit TOUJOURS sous output/marketing/,
independamment du repertoire de travail de l'equipe code (common/workdir.py). C'est le seul
outil d'ecriture donne aux agents marketing, et ils n'ont aucun outil reseau/shell -- la regle
"brouillons uniquement, jamais d'envoi reel" est donc garantie par la structure, pas juste
par une instruction dans le prompt."""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from common.paths import OUTPUT_DIR

_MARKETING_OUTPUT = OUTPUT_DIR / "marketing"


def resolve_marketing_path(relative_path: str) -> Path:
    """Resout un chemin relatif a output/marketing/, refuse toute evasion (ex: '../../secrets').
    Reutilise par write_draft ci-dessous et par tools/view_image.py pour les agents marketing."""
    target = (_MARKETING_OUTPUT / relative_path).resolve()
    if target != _MARKETING_OUTPUT and _MARKETING_OUTPUT not in target.parents:
        raise ValueError(f"Chemin en dehors de output/marketing/ refuse: '{relative_path}'")
    return target


@tool
def write_draft(filename: str, content: str) -> str:
    """Enregistre un brouillon (sequence email, post, audit SEO, creation pub...) en local sous
    output/marketing/. N'envoie et ne publie jamais rien -- ecrit uniquement un fichier."""
    try:
        target = resolve_marketing_path(filename)
    except ValueError as exc:
        return f"ERREUR: {exc}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: brouillon enregistre dans output/marketing/{filename}"
