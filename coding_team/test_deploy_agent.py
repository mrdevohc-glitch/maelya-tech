"""Agent tests & deploiement : suites de tests, scripts CI/CD, deploiement."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.models import get_model
from common.prompts import NO_FUTURE_PROMISES_INSTRUCTION
from tools.files import read_file, write_file, edit_file
from tools.shell import run_shell

SYSTEM_PROMPT = f"""Tu es un ingenieur QA/DevOps senior. Tu ecris des tests qui verifient un
vrai comportement (pas des tests qui passent toujours), et tu les executes reellement via
run_shell pour confirmer qu'ils passent avant de rendre la main.

Pour le deploiement : ecris des scripts/config CI clairs et documente les etapes manuelles
restantes (secrets a configurer, DNS, etc.) plutot que de pretendre tout automatiser si ce
n'est pas le cas.
Signale explicitement toute commande a fort impact (deploiement en prod, migration de
donnees) que tu ne peux pas executer toi-meme et qui doit rester manuelle.
{NO_FUTURE_PROMISES_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("test_deploy_agent"),
        tools=[read_file, write_file, edit_file, run_shell],
        prompt=SYSTEM_PROMPT,
        name="test_deploy_agent",
    )
