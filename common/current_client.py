"""Client courant pour le job en cours (marketing OU code) -- meme principe que
common/workdir.py pour le dossier de projet cote code. Le modele ne fournit JAMAIS lui-meme le
client_id a un outil de publication/deploiement : ce serait risque (une erreur/hallucination du
modele pourrait melanger les identifiants de deux clients differents). Fixe une fois par
webapp/job_runner.py avant d'invoquer le supervisor, lu par tools/publishing/staging.py et
tools/deployment/staging.py.

ContextVar (pas une variable globale simple) -- meme raison que common/workdir.py : sans ca, un
thread d'outil en retard d'un job pour le client A pourrait lire le client B si le worker est
deja passe au job suivant. Ici c'est encore plus sensible que le repertoire de travail : ca
determine QUELS IDENTIFIANTS CHIFFRES sont dechiffres pour une action reelle (Meta/Vercel)."""
from __future__ import annotations

from contextvars import ContextVar

_current_client_var: ContextVar[str | None] = ContextVar("current_client", default=None)


def set_current_client(client_id: str | None) -> None:
    _current_client_var.set(client_id)


def get_current_client() -> str | None:
    return _current_client_var.get()
