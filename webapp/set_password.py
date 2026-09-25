#!/usr/bin/env python3
"""Definit (ou change) le mot de passe de la plateforme web. Ecrit le hash bcrypt dans .env
(PLATFORM_PASSWORD_HASH) -- le mot de passe en clair n'est jamais stocke ni affiche a nouveau.

Usage: .venv\\Scripts\\python.exe webapp\\set_password.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Permet de lancer ce script directement (`python webapp/set_password.py`) sans que
# l'import de `webapp.*` echoue -- Python n'ajoute sinon que le dossier du script lui-meme
# (webapp/) a sys.path, pas la racine du projet (agents/) qui contient le package `webapp`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.env_utils import ENV_PATH, update_env_var  # noqa: E402
from webapp.auth import hash_password  # noqa: E402


def main() -> None:
    print("Definir le mot de passe de la plateforme web (rien ne s'affiche pendant la frappe).")
    password = getpass.getpass("Nouveau mot de passe : ")
    confirm = getpass.getpass("Confirme : ")
    if password != confirm:
        print("Les deux mots de passe ne correspondent pas -- rien n'a ete change.")
        return
    if len(password) < 8:
        print("Choisis un mot de passe d'au moins 8 caracteres -- rien n'a ete change.")
        return

    hashed = hash_password(password)
    update_env_var("PLATFORM_PASSWORD_HASH", hashed)
    print(f"OK : PLATFORM_PASSWORD_HASH mis a jour dans {ENV_PATH}")
    print("Redemarre le serveur (webapp) pour que le nouveau mot de passe soit pris en compte.")


if __name__ == "__main__":
    main()
