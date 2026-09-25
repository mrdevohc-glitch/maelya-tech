"""Limiteur de debit generique en memoire (par cle, ex. adresse IP). Meme principe que le
blocage anti-bruteforce de webapp/auth.py mais reutilisable pour n'importe quel endpoint public
(actuellement : le formulaire /demande). En memoire uniquement -- suffisant pour un seul process/
serveur, se reinitialise a chaque redemarrage (acceptable pour ce cas d'usage)."""
from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Verifie SANS enregistrer -- utile pour un controle en amont d'une action couteuse."""
        now = time.time()
        recent = [t for t in self._attempts.get(key, []) if now - t < self._window_seconds]
        return len(recent) < self._max_attempts

    def record(self, key: str) -> None:
        now = time.time()
        recent = [t for t in self._attempts.get(key, []) if now - t < self._window_seconds]
        recent.append(now)
        self._attempts[key] = recent
