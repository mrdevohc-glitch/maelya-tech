"""Capture d'ecran d'une page (fichier HTML local ou URL) pour la boucle de retroaction
visuelle du frontend_agent : generer -> screenshot -> auto-critique -> iterer.

Avec un modele Anthropic, l'image est renvoyee en base64 dans le resultat de l'outil (format
tool_result de Claude) pour que l'agent puisse vraiment "voir" le rendu. Les APIs OpenAI et la
plupart des autres fournisseurs n'acceptent pas d'image dans un resultat d'outil (uniquement
dans un message utilisateur) -- dans ce cas l'outil renvoie seulement le chemin du fichier et
le previent qu'il doit juger le design sur le HTML/CSS ecrit, pas sur un rendu vu directement.
"""
from __future__ import annotations

import base64

from langchain_core.tools import tool
from playwright.sync_api import sync_playwright

from common.models import get_agent_config
from common.workdir import get_working_directory, resolve

_VISION_TOOL_RESULT_PROVIDERS = {"anthropic"}


def _frontend_provider() -> str:
    model_ref = get_agent_config("frontend_agent").get("model", "")
    return model_ref.split(":", 1)[0] if ":" in model_ref else ""


@tool
def screenshot_page(path_or_url: str, output_name: str = "preview.png") -> list[dict]:
    """Ouvre une page (chemin de fichier HTML relatif au projet, ou URL http/https) dans un
    navigateur headless et en capture une image. Utilise cet outil pour verifier visuellement
    un design avant de le considerer termine.
    """
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        target_url = path_or_url
    else:
        file_path = resolve(path_or_url)
        if not file_path.exists():
            return [{"type": "text", "text": f"ERREUR: fichier introuvable: {path_or_url}"}]
        target_url = file_path.as_uri()

    preview_dir = get_working_directory() / ".previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_path = preview_dir / output_name

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(target_url, wait_until="networkidle")
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()

    if _frontend_provider() not in _VISION_TOOL_RESULT_PROVIDERS:
        return [{
            "type": "text",
            "text": (
                f"Capture enregistree dans .previews/{output_name}. Le modele actuel "
                f"(config/models.yaml -> frontend_agent) ne peut pas voir l'image directement "
                f"depuis cet outil -- relis le HTML/CSS que tu as ecrit pour juger la mise en "
                f"page, les espacements et les couleurs, plutot que de supposer que c'est bon."
            ),
        }]

    b64_data = base64.b64encode(output_path.read_bytes()).decode("utf-8")
    return [
        {
            "type": "text",
            "text": (
                f"Capture enregistree dans .previews/{output_name}. "
                f"Regarde l'image ci-dessous et juge honnetement le design avant de continuer."
            ),
        },
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64_data},
        },
    ]
