"""Repertoire de travail courant partage par tous les outils fichiers/shell de l'equipe code.

Chaque projet traite par l'equipe code a son propre repertoire (voir cli.py --project-dir).
Les agents marketing n'utilisent pas ce module : ils ecrivent directement dans
common.paths.OUTPUT_DIR via leurs propres outils (pas de notion de "projet cible").
"""
from __future__ import annotations

from pathlib import Path

from common.paths import OUTPUT_DIR

_cwd: Path = OUTPUT_DIR / "projects" / "default"


def set_working_directory(path: str | Path) -> Path:
    """Definit le repertoire de travail courant et le cree si besoin. Retourne le chemin resolu."""
    global _cwd
    _cwd = Path(path).resolve()
    _cwd.mkdir(parents=True, exist_ok=True)
    return _cwd


def get_working_directory() -> Path:
    return _cwd


def resolve(relative_path: str) -> Path:
    """Resout un chemin relatif au repertoire de travail courant.

    Refuse toute tentative d'evasion du repertoire de travail (ex: '../../secrets').
    """
    target = (_cwd / relative_path).resolve()
    if target != _cwd and _cwd not in target.parents:
        raise ValueError(
            f"Chemin en dehors du repertoire de travail refuse: '{relative_path}' "
            f"(repertoire de travail: {_cwd})"
        )
    return target
