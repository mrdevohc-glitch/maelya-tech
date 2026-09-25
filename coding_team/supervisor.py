"""Supervisor de l'equipe code : route chaque tache vers l'agent specialise competent et gere
les hand-offs entre eux (via langgraph-supervisor)."""
from __future__ import annotations

from langgraph_supervisor import create_supervisor

from common.models import get_model
from common.prompts import NO_FUTURE_PROMISES_INSTRUCTION
from coding_team.research_agent import build_agent as build_research_agent
from coding_team.frontend_agent import build_agent as build_frontend_agent
from coding_team.backend_agent import build_agent as build_backend_agent
from coding_team.test_deploy_agent import build_agent as build_test_deploy_agent
from coding_team.security_agent import build_agent as build_security_agent
from coding_team.content_agent import build_agent as build_content_agent

SUPERVISOR_PROMPT = f"""Tu diriges une equipe de developpement logiciel composee de :
- research_agent : cadrage projet UNIQUEMENT (cahier des charges, choix techno, devis, contrat)
  -- n'a pas d'outil shell/build, ne PEUT PAS generer de PDF/CI reels, ne le sollicite jamais
  pour ca.
- frontend_agent : interface utilisateur / design (le vrai site/appli)
- backend_agent : code serveur / API / logique metier (le vrai site/appli)
- test_deploy_agent : tests et deploiement
- security_agent : revue de securite
- content_agent : copywriting / contenu du projet (README, landing, annonces)

Pour une nouvelle demande de projet : commence par research_agent UNE SEULE FOIS pour le
cadrage (docs/cahier-des-charges.md etc.), sauf si ce cadrage existe deja. DES QUE l'utilisateur
a valide le cadrage (ex: "ok", "valide", ou qu'il repond aux questions initiales), route
IMMEDIATEMENT vers backend_agent et/ou frontend_agent pour construire le vrai livrable -- ne
retourne PAS vers research_agent pour des sujets annexes (export PDF, CI/CD, mise en page de
documents) : ce n'est pas son role et il n'a pas les outils pour. Appelle test_deploy_agent des
qu'il y a du code a tester. Appelle security_agent avant de considerer un projet "termine" des
qu'il touche a des donnees utilisateur ou de l'authentification. Appelle content_agent pour tout
texte destine a des humains (README, landing, annonces).

Le but final est TOUJOURS le livrable demande par l'utilisateur (le site/l'appli), jamais la
paperasse de cadrage -- si tu remarques que l'equipe tourne en rond sur un sujet secondaire
depuis plusieurs echanges sans avancer vers ce livrable, arrete et route vers backend_agent ou
frontend_agent directement.

Ne fais jamais le travail toi-meme : delegue systematiquement a l'agent competent.
{NO_FUTURE_PROMISES_INSTRUCTION}
"""


def build_supervisor(checkpointer=None):
    """`checkpointer` (optionnel) permet de reprendre une conversation entre deux lancements
    de la CLI (voir cli.py) -- sans lui, chaque appel a `invoke` part de zero."""
    agents = [
        build_research_agent(),
        build_frontend_agent(),
        build_backend_agent(),
        build_test_deploy_agent(),
        build_security_agent(),
        build_content_agent(),
    ]
    workflow = create_supervisor(
        agents=agents,
        model=get_model("coding_supervisor"),
        prompt=SUPERVISOR_PROMPT,
    )
    return workflow.compile(checkpointer=checkpointer)
