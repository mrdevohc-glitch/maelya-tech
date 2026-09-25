"""Petit utilitaire partage pour lire/ecrire des variables dans .env (utilise par
set_password.py et auth.py pour persister le mot de passe hache et la cle de session)."""
from __future__ import annotations

import re

from common.paths import AGENTS_ROOT

ENV_PATH = AGENTS_ROOT / ".env"


def update_env_var(key: str, value: str) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pattern = re.compile(rf"^{re.escape(key)}=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
