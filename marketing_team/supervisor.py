"""Supervisor marketing : route le brief vers le(s) bon(s) agent(s) specialise(s). Aucun agent
de cette equipe n'a d'outil reseau/shell -- impossible d'envoyer/publier/depenser reellement,
seulement de produire des brouillons sous output/marketing/."""
from __future__ import annotations

from langgraph_supervisor import create_supervisor

from common.models import get_model
from marketing_team.email_agent import build_agent as build_email_agent
from marketing_team.social_agent import build_agent as build_social_agent
from marketing_team.seo_content_agent import build_agent as build_seo_content_agent
from marketing_team.ads_cro_agent import build_agent as build_ads_cro_agent

SUPERVISOR_PROMPT = """Tu diriges une equipe marketing composee de :
- email_agent : sequences email, cold email
- social_agent : contenu et strategie reseaux sociaux
- seo_content_agent : SEO, strategie de contenu, articles
- ads_cro_agent : publicite payante, optimisation de conversion

Route le brief de l'utilisateur vers le ou les agents pertinents. Si le brief demande un plan
marketing complet ("auto"), appelle les 4 dans un ordre logique (positionnement/SEO d'abord
si rien n'existe, puis contenu social et email, puis pub/CRO). Ne fais jamais le travail
toi-meme : delegue systematiquement.
"""


def build_supervisor(checkpointer=None):
    """`checkpointer` (optionnel) permet de reprendre une conversation entre deux lancements
    de la CLI (voir cli.py) -- sans lui, chaque appel a `invoke` part de zero."""
    agents = [
        build_email_agent(),
        build_social_agent(),
        build_seo_content_agent(),
        build_ads_cro_agent(),
    ]
    workflow = create_supervisor(
        agents=agents,
        model=get_model("marketing_supervisor"),
        prompt=SUPERVISOR_PROMPT,
    )
    return workflow.compile(checkpointer=checkpointer)
