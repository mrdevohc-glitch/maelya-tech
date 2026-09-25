"""Scans actifs (port + vulnerabilites web) contre une cible EXPLICITEMENT autorisee. JAMAIS
expose comme outil a un agent/LLM -- appele uniquement par webapp/job_runner.py
(kind='security_scan'), lui-meme uniquement declenche pour une cible presente dans
webapp.db.scan_targets (jamais une cible fournie ailleurs, jamais devinee).

Securite d'execution : subprocess sans shell (liste d'arguments, jamais une chaine interpretee
par un shell) + validation stricte du format hostname avant tout appel -- double protection
contre l'injection de commande meme si `_dispatch` avait un bug en amont."""
from __future__ import annotations

import re
import subprocess

_TIMEOUT_SECONDS = 300
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?(:\d{1,5})?(/[\w./?%&=-]*)?$"
)


class ScanTargetError(ValueError):
    pass


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd, shell=False, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except FileNotFoundError:
        return f"ERREUR: outil introuvable ({cmd[0]} pas installe sur ce serveur)."
    except subprocess.TimeoutExpired:
        return f"Scan interrompu apres {_TIMEOUT_SECONDS}s (timeout)."
    output = (result.stdout + result.stderr).strip()
    return output or f"OK (code retour {result.returncode}, aucune sortie)."


def run_port_scan(hostname: str) -> str:
    """Scan TCP connect (non privilegie, pas de SYN scan) sur les 100 ports les plus courants.
    Refuse tout hostname qui ne ressemble pas a un nom de domaine/IP simple."""
    if not _HOSTNAME_RE.match(hostname):
        raise ScanTargetError(f"Hostname refuse (format invalide): {hostname!r}")
    return _run(["nmap", "-sT", "-Pn", "--top-ports", "100", hostname])


def run_web_vuln_scan(url: str) -> str:
    """Scan de vulnerabilites web (nikto) contre une URL HTTP/HTTPS. Refuse tout ce qui n'est
    pas une URL http(s) simple."""
    if not _URL_RE.match(url):
        raise ScanTargetError(f"URL refusee (format invalide): {url!r}")
    return _run(["nikto", "-h", url, "-maxtime", str(_TIMEOUT_SECONDS)])
