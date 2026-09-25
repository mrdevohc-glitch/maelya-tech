"""Authentification mono-utilisateur : mot de passe hache (bcrypt) + session cookie signee.
Inclut un blocage anti-bruteforce simple (5 echecs / 5 min -> blocage 15 min par IP)."""
from __future__ import annotations

import os
import secrets
import time

import bcrypt
from fastapi import Depends, HTTPException, Request

from common.env_utils import update_env_var

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 5 * 60
_LOCKOUT_SECONDS = 15 * 60

# {ip: [timestamps des echecs recents]} -- en memoire, suffisant pour un seul process/serveur.
_failed_attempts: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _get_expected_hash() -> str:
    hashed = os.environ.get("PLATFORM_PASSWORD_HASH", "")
    if not hashed:
        raise RuntimeError(
            "PLATFORM_PASSWORD_HASH manquant dans .env -- lance webapp/set_password.py d'abord."
        )
    return hashed


def is_locked_out(ip: str) -> bool:
    until = _locked_until.get(ip)
    return until is not None and time.time() < until


def register_failed_attempt(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
    attempts.append(now)
    _failed_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        _locked_until[ip] = now + _LOCKOUT_SECONDS


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _locked_until.pop(ip, None)


def verify_password(plain: str) -> bool:
    expected = _get_expected_hash()
    return bcrypt.checkpw(plain.encode("utf-8"), expected.encode("utf-8"))


def get_or_create_secret_key() -> str:
    """Cle utilisee pour signer le cookie de session. Generee une seule fois et persistee dans
    .env -- sans ca, un redemarrage du serveur invaliderait toutes les sessions actives."""
    key = os.environ.get("PLATFORM_SECRET_KEY", "")
    if key:
        return key
    key = secrets.token_hex(32)
    update_env_var("PLATFORM_SECRET_KEY", key)
    os.environ["PLATFORM_SECRET_KEY"] = key
    return key


def require_auth(request: Request) -> None:
    """Dependance FastAPI : leve 401 si la session n'est pas authentifiee."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Non authentifie")


AuthDependency = Depends(require_auth)
