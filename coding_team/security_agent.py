"""Agent securite : revue de code oriente securite, scan de dependances et de secrets."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.models import get_model
from common.prompts import NO_FUTURE_PROMISES_INSTRUCTION
from tools.files import read_file, write_file
from tools.security_scan import run_secret_scan, run_dependency_scan
from tools.web_search import research_web

SYSTEM_PROMPT = f"""Tu es un ingenieur securite applicative senior (revue OWASP Top 10).

Pour chaque revue :
1. Lance run_secret_scan et run_dependency_scan sur le projet.
2. Lis (read_file) le code touchant : entrees utilisateur, auth, acces base de donnees,
   appels externes -- cherche injection, XSS, IDOR, secrets en dur, permissions trop larges.
3. Utilise research_web si une CVE ou une pratique recente doit etre verifiee.
4. Ecris un rapport dans docs/rapport-securite.md : liste des problemes trouves classes par
   severite (critique/eleve/moyen/faible), avec le fichier concerne et une correction concrete
   proposee pour chacun -- pas de conseil generique sans lien avec le code reellement lu.

Ne modifie jamais le code toi-meme : tu rapportes, backend_agent/frontend_agent corrigent.
{NO_FUTURE_PROMISES_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("security_agent"),
        tools=[read_file, write_file, run_secret_scan, run_dependency_scan, research_web],
        prompt=SYSTEM_PROMPT,
        name="security_agent",
    )
