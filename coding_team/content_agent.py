"""Agent contenu (equipe code) : copywriting, README, landing copy, annonces de lancement.
S'appuie sur l'expertise copywriting/content-creator/brand-guidelines copiee sous skills/content/."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.models import get_model
from common.prompts import MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION
from common.skills import load_skills
from tools.files import read_file, write_file

_SKILLS_CONTEXT = load_skills(
    ("content", "copywriting", "SKILL.md"),
    ("content", "content-creator", "SKILL.md"),
    ("content", "brand-guidelines", "SKILL.md"),
)

SYSTEM_PROMPT = f"""Tu es un redacteur / content strategist senior charge du contenu d'un
projet logiciel : README, page d'accueil, description produit, posts d'annonce de lancement,
elements de langage pour la documentation.

Tu produis des brouillons uniquement (write_file dans docs/ ou content/) -- jamais de
publication ou d'envoi reel.

Reference d'expertise a appliquer :
{_SKILLS_CONTEXT}
{MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("content_agent"),
        tools=[read_file, write_file],
        prompt=SYSTEM_PROMPT,
        name="content_agent",
    )
