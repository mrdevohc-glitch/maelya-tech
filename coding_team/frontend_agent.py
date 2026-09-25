"""Agent front-end / UI-UX : doit produire des interfaces vraiment soignees, pas du HTML
par defaut. Sa force vient de screenshot_page (tools/browser_preview.py) qui lui permet de
VOIR son propre rendu et de s'auto-corriger, au lieu de deviner a l'aveugle."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.models import get_model
from common.prompts import NO_FUTURE_PROMISES_INSTRUCTION
from tools.files import read_file, write_file, edit_file
from tools.shell import run_shell
from tools.browser_preview import screenshot_page

SYSTEM_PROMPT = f"""Tu es un designer produit / ingenieur front-end senior. Ton objectif n'est
pas juste "que ca marche" mais que ce soit visuellement soigne et professionnel : hierarchie
typographique claire, espacement genereux et coherent, palette de couleurs intentionnelle
(pas les couleurs par defaut du framework), etats interactifs (hover/focus/disabled) traites.

Boucle de travail obligatoire pour toute interface visuelle :
1. Ecris/modifie le composant ou la page (write_file/edit_file).
2. Build si necessaire (run_shell).
3. screenshot_page sur le resultat pour VOIR le rendu reel.
4. Critique honnetement ce que tu vois (alignement casse, contraste faible, densite
   incoherente, design generique) et itere avant de considerer le travail termine.

Ne dis jamais qu'un design est termine sans etre passe par screenshot_page au moins une fois.
{NO_FUTURE_PROMISES_INSTRUCTION}
"""


def build_agent():
    return create_react_agent(
        model=get_model("frontend_agent"),
        tools=[read_file, write_file, edit_file, run_shell, screenshot_page],
        prompt=SYSTEM_PROMPT,
        name="frontend_agent",
    )
