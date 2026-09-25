"""Chiffrement au repos des identifiants clients (jetons d'acces API tiers -- Meta, LinkedIn,
Google Ads, X...). Cle symmetrique (Fernet) generee une fois et persistee dans .env, comme
PLATFORM_SECRET_KEY pour les sessions web. L'agent/le modele ne dechiffre jamais rien lui-meme
-- seul le code d'execution (tools/publishing/executor.py) appelle decrypt_json()."""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from common.env_utils import ENV_PATH, update_env_var


def get_or_create_credentials_key() -> bytes:
    # Charge .env explicitement au lieu de compter sur l'appelant (webapp/app.py le fait au
    # demarrage, mais un script autonome qui importe seulement common.crypto/webapp.db --
    # comme un test isole -- ne le fait pas, et verrait a tort la cle comme absente, la
    # regenererait, et ECRASERAIT la vraie cle dans .env. load_dotenv() est sans effet si
    # deja charge (ne remplace pas un os.environ deja defini par defaut).
    load_dotenv(ENV_PATH)
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
