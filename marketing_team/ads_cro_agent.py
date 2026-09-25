"""Agent publicite / CRO : creas pub, structure de campagne, optimisation de conversion
(pages, formulaires, popups). Brouillons uniquement (write_draft), aucun outil de mise en
ligne ou de depense reelle."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.context import load_business_context
from common.current_client import get_current_client
from common.models import get_model
from common.prompts import MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION
from common.skills import load_skills
from tools.marketing_output import write_draft
from tools.publishing.image_gen import generate_ad_image

_SKILLS_CONTEXT = load_skills(
    ("ads_cro", "paid-ads", "SKILL.md"),
    ("ads_cro", "ad-creative", "SKILL.md"),
    ("ads_cro", "page-cro", "SKILL.md"),
    ("ads_cro", "form-cro", "SKILL.md"),
    ("ads_cro", "popup-cro", "SKILL.md"),
    ("ads_cro", "campaign-analytics", "SKILL.md"),
    ("_shared", "marketing-context", "SKILL.md"),
)


def _build_prompt() -> str:
    return f"""Tu es un expert publicite payante et optimisation de conversion (CRO).
Tu produis en brouillon (write_draft) : concepts de creas pub, structure de campagne
(ciblage, budget indicatif, enchere), et recommandations CRO concretes pour pages/formulaires/
popups. Utilise generate_ad_image pour produire de vraies images de creas quand c'est demande
(ca ne fait qu'ecrire un fichier local, pas besoin d'approbation pour ca). Tu ne lances jamais
une campagne ni ne depenses de budget reel, tu n'as pas l'outil pour -- cette capacite arrivera
dans une prochaine mise a jour (Google Ads/Meta Ads), toujours avec validation humaine obligatoire.

Profil business (client courant) :
{load_business_context(get_current_client())}

Reference d'expertise a appliquer :
{_SKILLS_CONTEXT}
{MULTIPLE_CHOICE_QUESTIONS_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("ads_cro_agent"),
        tools=[write_draft, generate_ad_image],
        prompt=_build_prompt(),
        name="ads_cro_agent",
    )
