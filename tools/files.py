"""Outils fichiers partages (read/write/edit) pour tous les agents de l'equipe code."""
from __future__ import annotations

from langchain_core.tools import tool

from common.workdir import resolve


@tool
def read_file(path: str) -> str:
    """Lit le contenu d'un fichier texte. `path` est relatif au projet en cours de traitement."""
    target = resolve(path)
    if not target.exists():
        return f"ERREUR: fichier introuvable: {path}"
    return target.read_text(encoding="utf-8", errors="replace")


@tool
def write_file(path: str, content: str) -> str:
    """Cree ou remplace entierement un fichier texte. `path` est relatif au projet en cours."""
    target = resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: {path} ecrit ({len(content)} caracteres)."


@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Remplace une occurrence exacte de old_text par new_text dans un fichier existant.

    Echoue si old_text n'apparait pas exactement une fois (pour eviter une modification
    ambigue) : dans ce cas, relis le fichier et fournis un old_text plus specifique.
    """
    target = resolve(path)
    if not target.exists():
        return f"ERREUR: fichier introuvable: {path}"
    content = target.read_text(encoding="utf-8")
    occurrences = content.count(old_text)
    if occurrences == 0:
        return "ERREUR: old_text introuvable dans le fichier (aucune modification faite)."
    if occurrences > 1:
        return f"ERREUR: old_text apparait {occurrences} fois, sois plus specifique (aucune modification faite)."
    target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"OK: {path} modifie."
