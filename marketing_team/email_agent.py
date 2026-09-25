"""Agent email : sequences, drip campaigns, cold email. Brouillons uniquement (write_draft),
aucun outil d'envoi -- voir tools/marketing_output.py."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.context import load_business_context
from common.current_client import get_current_client
from common.models import get_model
from common.prompts import MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION
from common.skills import load_skills
from tools.marketing_output import write_draft

_SKILLS_CONTEXT = load_skills(
    ("email", "email-sequence", "SKILL.md"),
    ("email", "cold-email", "SKILL.md"),
    ("_shared", "marketing-context", "SKILL.md"),
)


def _build_prompt() -> str:
    # Lu a la construction de l'agent (une fois par job, voir webapp/job_runner.py), pas a
    # l'import du module -- sinon le profil business resterait figure sur le premier client
    # rencontre au lieu de refleter le client courant de chaque job.
    return f"""Tu es un expert email marketing (sequences, drip campaigns, cold email).
Tu ne fais QUE produire des brouillons complets et prets a relire (write_draft) : sujet,
preview text, corps complet, CTA. Tu n'envoies jamais rien, tu n'as pas l'outil pour.

Profil business (client courant) :
{load_business_context(get_current_client())}

Reference d'expertise a appliquer :
{_SKILLS_CONTEXT}
{MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("email_agent"),
        tools=[write_draft],
        prompt=_build_prompt(),
        name="email_agent",
    )
