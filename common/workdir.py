"""Repertoire de travail courant partage par tous les outils fichiers/shell de l'equipe code.

Chaque projet traite par l'equipe code a son propre repertoire (voir cli.py --project-dir).
Les agents marketing n'utilisent pas ce module : ils ecrivent directement dans
common.paths.OUTPUT_DIR via leurs propres outils (pas de notion de "projet cible").

IMPORTANT -- ContextVar, pas une variable globale simple : webapp/job_runner.py traite les jobs
un par un dans un seul thread, mais LangGraph execute les PLUSIEURS appels d'outils d'un meme
tour d'agent en parallele via un ThreadPoolExecutor interne (langgraph/prebuilt/tool_node.py).
Un thread d'outil un peu lent (ex: run_shell) peut donc encore etre en train de tourner au
moment ou le worker enchaine sur le job SUIVANT et change le repertoire courant -- avec une
simple variable globale, ce thread en retard verrait alors le mauvais projet (bug reel observe
en production le 2026-09-27 : ValueError "chemin en dehors du repertoire de travail" avec un
repertoire attendu different du repertoire courant). Un ContextVar est copie (pas partage) au
moment ou LangChain lance un thread via `copy_context().run(...)` (confirme dans
langchain_core/runnables/config.py) -- chaque thread d'outil garde donc la valeur figee au
moment de son lancement, meme si le thread principal change de projet ensuite.
"""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from common.paths import OUTPUT_DIR

_cwd_var: ContextVar[Path] = ContextVar("cwd", default=OUTPUT_DIR / "projects" / "default")


def set_working_directory(path: str | Path) -> Path:
    """Definit le repertoire de travail courant et le cree si besoin. Retourne le chemin resolu."""
    resolved = Path(path).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    _cwd_var.set(resolved)
    return resolved


def get_working_directory() -> Path:
    return _cwd_var.get()


def resolve(relative_path: str) -> Path:
    """Resout un chemin relatif au repertoire de travail courant.

    Refuse toute tentative d'evasion du repertoire de travail (ex: '../../secrets').
    """
    cwd = _cwd_var.get()
    target = (cwd / relative_path).resolve()
    if target != cwd and cwd not in target.parents:
        raise ValueError(
            f"Chemin en dehors du repertoire de travail refuse: '{relative_path}' "
            f"(repertoire de travail: {cwd})"
        )
    return target
