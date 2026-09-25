"""Vrais appels a l'API Vercel (deploiement de projet). N'est JAMAIS importe par un agent --
uniquement par tools/publishing/executor.py, apres validation humaine.

Identifiants attendus dans le payload chiffre du client (voir common/crypto.py), cle 'vercel' :
{"api_token": "...", "team_id": "..." (optionnel)}

Jeton requis : un jeton d'acces personnel Vercel (vercel.com/account/tokens). Demarche manuelle
cote Vercel, hors de ce code -- voir README.
"""
from __future__ import annotations

import base64
from pathlib import Path

import requests

_API_BASE = "https://api.vercel.com"
_TIMEOUT_SECONDS = 60
_EXCLUDED_DIR_NAMES = {".git", ".venv", "node_modules", ".state", "__pycache__", "output", "dist", "build"}
_MAX_FILES = 500
_MAX_TOTAL_BYTES = 10 * 1024 * 1024


class VercelAPIError(RuntimeError):
    pass


def _raise_for_vercel_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except ValueError:
        detail = response.text
    raise VercelAPIError(f"Erreur API Vercel ({response.status_code}): {detail}")


def _collect_files(project_dir: Path) -> list[dict]:
    """Lit tous les fichiers du projet pour un deploiement inline (petits projets). Exclut les
    dossiers techniques (.git, .venv, node_modules...) -- jamais deployes chez le client."""
    files: list[dict] = []
    total_bytes = 0
    for path in sorted(project_dir.rglob("*")):
        if path.is_dir():
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.relative_to(project_dir).parts):
            continue
        raw = path.read_bytes()
        total_bytes += len(raw)
        if len(files) >= _MAX_FILES or total_bytes > _MAX_TOTAL_BYTES:
            raise VercelAPIError(
                f"Projet trop volumineux pour un deploiement inline "
                f"({_MAX_FILES} fichiers / {_MAX_TOTAL_BYTES // (1024 * 1024)} Mo max)."
            )
        rel_path = path.relative_to(project_dir).as_posix()
        try:
            files.append({"file": rel_path, "data": raw.decode("utf-8")})
        except UnicodeDecodeError:
            files.append({
                "file": rel_path,
                "data": base64.b64encode(raw).decode("ascii"),
                "encoding": "base64",
            })
    return files


def deploy_directory(project_dir: str, token: str, project_name: str, team_id: str | None = None) -> str:
    """Deploie le contenu de `project_dir` sur Vercel (deploiement de production). Retourne
    l'URL publique du deploiement cree."""
    files = _collect_files(Path(project_dir))
    if not files:
        raise VercelAPIError(f"Aucun fichier trouve dans {project_dir} -- rien a deployer.")

    response = requests.post(
        f"{_API_BASE}/v13/deployments",
        params={"teamId": team_id} if team_id else {},
        json={"name": project_name, "files": files, "target": "production"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_vercel_error(response)
    body = response.json()
    url = body.get("url")
    return f"https://{url}" if url else str(body.get("id", "deploiement cree (URL inconnue)"))
