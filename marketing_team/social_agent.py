"""Agent reseaux sociaux : contenu, calendrier de posts, strategie X/Twitter. Brouillons
uniquement (write_draft), aucun outil de publication."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.context import load_business_context
from common.current_client import get_current_client
from common.models import get_model
from common.prompts import MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION
from common.skills import load_skills
from tools.marketing_output import write_draft
from tools.publishing.staging import stage_facebook_post, stage_instagram_post

_SKILLS_CONTEXT = load_skills(
    ("social", "social-content", "SKILL.md"),
    ("social", "social-media-manager", "SKILL.md"),
    ("social", "x-twitter-growth", "SKILL.md"),
    ("_shared", "marketing-context", "SKILL.md"),
)


def _build_prompt() -> str:
    return f"""Tu es un expert reseaux sociaux (contenu, calendrier editorial, croissance
organique) ET community manager pour le compte du client courant.

Deux modes distincts, ne les confonds jamais :
- Brainstorm/calendrier editorial/idees de posts -> write_draft (brouillon local, comme avant).
- L'utilisateur demande explicitement de PUBLIER un post precis pour CE client -> utilise
  stage_facebook_post / stage_instagram_post. Ces outils ne publient PAS directement : ils
  mettent l'action en attente d'approbation humaine. Dis TOUJOURS clairement a l'utilisateur
  que l'action est en attente et doit etre validee dans le tableau de bord (/approvals) --
  ne dis JAMAIS "c'est publie" ou "c'est en ligne", ce serait faux.

Profil business (client courant) :
{load_business_context(get_current_client())}

Reference d'expertise a appliquer :
{_SKILLS_CONTEXT}
{MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("social_agent"),
        tools=[write_draft, stage_facebook_post, stage_instagram_post],
        prompt=_build_prompt(),
        name="social_agent",
    )
