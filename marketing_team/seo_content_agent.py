"""Agent SEO / contenu : audits SEO, strategie de contenu, articles, SEO programmatique.
Brouillons uniquement (write_draft), aucun outil d'edition directe du site."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.context import load_business_context
from common.current_client import get_current_client
from common.models import get_model
from common.prompts import MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION
from common.skills import load_skills
from tools.marketing_output import write_draft
from tools.web_search import research_web

_SKILLS_CONTEXT = load_skills(
    ("seo_content", "seo-audit", "SKILL.md"),
    ("seo_content", "programmatic-seo", "SKILL.md"),
    ("seo_content", "content-strategy", "SKILL.md"),
    ("seo_content", "content-creator", "SKILL.md"),
    ("_shared", "marketing-context", "SKILL.md"),
)


def _build_prompt() -> str:
    return f"""Tu es un expert SEO et strategie de contenu. Tu produis des audits SEO,
des strategies de contenu, et des articles complets, toujours en brouillon (write_draft).
Utilise research_web pour verifier des donnees SEO/concurrentielles a jour plutot que de
deviner. Tu ne modifies jamais un site en direct, tu n'as pas l'outil pour.

Profil business (client courant) :
{load_business_context(get_current_client())}

Reference d'expertise a appliquer :
{_SKILLS_CONTEXT}
{MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("seo_content_agent"),
        tools=[write_draft, research_web],
        prompt=_build_prompt(),
        name="seo_content_agent",
    )
