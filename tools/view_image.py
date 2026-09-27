"""Permet a un agent de "voir" une image de reference jointe par l'utilisateur (maquette UI,
capture d'ecran, visuel produit...) depuis le tableau de bord web. Meme limite que
screenshot_page (tools/browser_preview.py) : seul un modele Anthropic recoit vraiment l'image
en base64 dans le resultat d'outil -- les autres fournisseurs recoivent seulement le chemin du
fichier et un avertissement honnete."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from common.models import supports_vision_tool_result


def make_view_reference_image_tool(agent_name: str, resolve_fn: Callable[[str], Path]):
    """Cree l'outil `view_reference_image` lie a `agent_name` (verifie le modele configure pour
    CET agent, pas un autre) -- a ajouter aux `tools=[...]` de l'agent concerne.

    `resolve_fn` resout le chemin relatif fourni par l'agent vers un vrai fichier, avec la meme
    protection anti-evasion que le reste du projet : `common.workdir.resolve` pour un agent de
    l'equipe code (relatif au projet en cours), `tools.marketing_output.resolve_marketing_path`
    pour un agent marketing (relatif a output/marketing/, ces agents n'ont pas de notion de
    "projet en cours")."""

    @tool
    def view_reference_image(path: str) -> list[dict]:
        """Affiche une image de reference jointe par l'utilisateur (chemin relatif indique dans
        le texte de la tache, ex: inputs/ab12cd.png)."""
        try:
            target = resolve_fn(path)
        except ValueError as exc:
            return [{"type": "text", "text": f"ERREUR: {exc}"}]
        if not target.exists():
            return [{"type": "text", "text": f"ERREUR: fichier introuvable: {path}"}]

        if not supports_vision_tool_result(agent_name):
            return [{
                "type": "text",
                "text": (
                    f"Image presente a {path} mais le modele actuel de {agent_name} "
                    f"(config/models.yaml) ne peut pas la voir directement dans un resultat "
                    f"d'outil -- si son contenu est important pour la tache, demande a "
                    f"l'utilisateur de le decrire plutot que de deviner."
                ),
            }]

        ext = target.suffix.lstrip(".").lower() or "png"
        b64_data = base64.b64encode(target.read_bytes()).decode("utf-8")
        return [
            {"type": "text", "text": f"Image de reference jointe par l'utilisateur ({path}) :"},
            {"type": "image", "source": {"type": "base64", "media_type": f"image/{ext}", "data": b64_data}},
        ]

    return view_reference_image
