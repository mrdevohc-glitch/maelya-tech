"""Chiffrement au repos des identifiants clients (jetons d'acces API tiers -- Meta, LinkedIn,
Google Ads, X...). Cle symmetrique (Fernet) generee une fois et persistee dans .env, comme
PLATFORM_SECRET_KEY pour les sessions web. L'agent/le modele ne dechiffre jamais rien lui-meme
-- seul le code d'execution (tools/publishing/executor.py) appelle decrypt_json()."""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet

from common.env_utils import update_env_var


def get_or_create_credentials_key() -> bytes:
    key = os.environ.get("PLATFORM_CREDENTIALS_KEY", "")
    if not key:
        key = Fernet.generate_key().decode("utf-8")
        update_env_var("PLATFORM_CREDENTIALS_KEY", key)
        os.environ["PLATFORM_CREDENTIALS_KEY"] = key
    return key.encode("utf-8")


def encrypt_json(payload: dict) -> bytes:
    fernet = Fernet(get_or_create_credentials_key())
    return fernet.encrypt(json.dumps(payload).encode("utf-8"))


def decrypt_json(blob: bytes) -> dict:
    fernet = Fernet(get_or_create_credentials_key())
    return json.loads(fernet.decrypt(blob).decode("utf-8"))
