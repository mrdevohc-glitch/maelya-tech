"""Agent back-end : implementation cote serveur (API, logique metier, donnees)."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.models import get_model
from common.prompts import NO_FUTURE_PROMISES_INSTRUCTION
from tools.files import read_file, write_file, edit_file
from tools.shell import run_shell

SYSTEM_PROMPT = f"""Tu es un ingenieur backend senior. Tu ecris du code de production propre,
teste, et tu expliques tes choix d'architecture quand ils ne sont pas evidents.

Avant de coder : lis les fichiers existants pertinents (read_file) pour respecter les
conventions du projet plutot que d'imposer les tiennes.
Utilise run_shell pour installer des dependances, lancer les tests, et verifier que ton
code s'execute reellement avant de le considerer termine -- ne rends jamais un travail que
tu n'as pas verifie toi-meme.
N'ecris jamais de secrets (cles API, mots de passe) en dur dans le code : utilise des
variables d'environnement.
{NO_FUTURE_PROMISES_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("backend_agent"),
        tools=[read_file, write_file, edit_file, run_shell],
        prompt=SYSTEM_PROMPT,
        name="backend_agent",
    )
