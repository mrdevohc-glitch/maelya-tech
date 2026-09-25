"""Client courant pour le job en cours (marketing OU code) -- meme principe que
common/workdir.py pour le dossier de projet cote code. Le modele ne fournit JAMAIS lui-meme le
client_id a un outil de publication/deploiement : ce serait risque (une erreur/hallucination du
modele pourrait melanger les identifiants de deux clients differents). Fixe une fois par
webapp/job_runner.py avant d'invoquer le supervisor, lu par tools/publishing/staging.py et
tools/deployment/staging.py."""
from __future__ import annotations

_current_client_id: str | None = None


def set_current_client(client_id: str | None) -> None:
    global _current_client_id
    _current_client_id = client_id


def get_current_client() -> str | None:
    return _current_client_id
