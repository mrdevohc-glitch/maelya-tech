"""Outil shell partage par les agents "code". Passe systematiquement par les garde-fous
(common/guardrails.py) avant toute execution."""
from __future__ import annotations

import subprocess

from langchain_core.tools import tool

from common.guardrails import check_command
from common.workdir import get_working_directory

_MAX_OUTPUT_CHARS = 8000
_TIMEOUT_SECONDS = 180


@tool
def run_shell(command: str) -> str:
    """Execute une commande shell dans le repertoire du projet en cours (installer des
    dependances, lancer des tests, builder, faire un commit local, etc.).

    Les commandes destructrices (rm -rf hors de output/, git push --force,
    git reset --hard, git clean -f) sont bloquees avant execution. `git push` simple est
    bloque par defaut sauf si l'utilisateur a relance la CLI avec --allow-push.
    """
    allowed, reason = check_command(command)
    if not allowed:
        return f"REFUSE: {reason}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=get_working_directory(),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"ERREUR: commande interrompue apres {_TIMEOUT_SECONDS}s (timeout)."

    output = (result.stdout + result.stderr).strip()
    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[-_MAX_OUTPUT_CHARS:]
    return output or f"OK (code retour {result.returncode}, aucune sortie)."
