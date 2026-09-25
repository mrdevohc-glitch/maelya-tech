"""Recherche web sans cle API, utilisee par research_agent et security_agent (recherche de CVE)."""
from __future__ import annotations

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from langchain_core.tools import tool


@tool
def research_web(query: str) -> str:
    """Recherche `query` sur le web et retourne les meilleurs resultats (titre, extrait, url)."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "Aucun resultat trouve."
    return "\n".join(
        f"- {r.get('title')}\n  {r.get('body')}\n  {r.get('href')}" for r in results
    )
