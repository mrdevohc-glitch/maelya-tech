"""Garde-fous partages pour les commandes shell executees par les agents "code".

Aucun agent ne peut lever ces blocages lui-meme : seul le flag CLI --allow-push
(voir cli.py) debloque `git push`, et rien ne debloque les suppressions destructrices.

ContextVar (pas une variable globale simple) pour la meme raison que common/workdir.py : sans
ca, un job B qui active allow_push pourrait etre vu par un thread d'outil en retard d'un job A
qui ne l'a jamais autorise.
"""
from __future__ import annotations

import re
from contextvars import ContextVar

_ALWAYS_BLOCKED = [
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "git reset --hard est destructif"),
    (re.compile(r"\bgit\s+clean\s+-f", re.IGNORECASE), "git clean -f est destructif"),
    (re.compile(r"\bgit\s+push\b.*(--force|-f\b)", re.IGNORECASE), "force-push est destructif pour le remote"),
]

_PUSH_PATTERN = re.compile(r"\bgit\s+push\b", re.IGNORECASE)
_RM_RF_PATTERN = re.compile(r"\brm\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+(\S+)", re.IGNORECASE)

_allow_push_var: ContextVar[bool] = ContextVar("allow_push", default=False)


def set_allow_push(value: bool) -> None:
    _allow_push_var.set(value)


def _is_safe_rm_target(target: str) -> bool:
    cleaned = target.strip().strip('"').strip("'").replace("\\", "/")
    if ".." in cleaned or cleaned in ("/", "."):
        return False
    return cleaned == "output" or cleaned.startswith("output/") or cleaned.startswith("./output/")


def check_command(command: str) -> tuple[bool, str]:
    """Retourne (autorise, raison_si_bloque)."""
    for pattern, reason in _ALWAYS_BLOCKED:
        if pattern.search(command):
            return False, f"Commande bloquee ({reason}): `{command}`"

    rm_match = _RM_RF_PATTERN.search(command)
    if rm_match and not _is_safe_rm_target(rm_match.group(2)):
        return False, (
            f"Commande bloquee (rm -rf en dehors de output/): `{command}`. "
            f"Supprime le fichier toi-meme si c'est voulu."
        )

    if _PUSH_PATTERN.search(command) and not _allow_push_var.get():
        return False, (
            f"Commande bloquee: `{command}`. Relance la CLI avec --allow-push pour "
            f"autoriser git push sur ce run."
        )

    return True, ""
