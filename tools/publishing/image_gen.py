"""Generation de vraies images (creas publicitaires) via l'API Images d'OpenAI. Ne necessite
PAS d'approbation humaine : ca ne fait qu'ecrire un fichier local, aucune action externe/
irreversible. L'approbation intervient plus tard, au moment de PUBLIER (voir staging.py)."""
from __future__ import annotations

import base64
import os
import uuid

from langchain_core.tools import tool
from openai import OpenAI

from common.paths import OUTPUT_DIR

_IMAGES_DIR = OUTPUT_DIR / "marketing" / "images"


@tool
def generate_ad_image(prompt: str, size: str = "1024x1024") -> str:
    """Genere une image publicitaire (crea) a partir d'une description textuelle et
    l'enregistre localement. `size` : '1024x1024', '1536x1024' (paysage) ou '1024x1536'
    (portrait). Retourne le chemin du fichier -- pas de publication, juste la generation."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "ERREUR: OPENAI_API_KEY manquant dans .env -- impossible de generer une image."

    client = OpenAI(api_key=api_key)
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="medium",
        n=1,
    )
    image_bytes = base64.b64decode(response.data[0].b64_json)

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:10]}.png"
    target = _IMAGES_DIR / filename
    target.write_bytes(image_bytes)

    return f"OK: image generee dans output/marketing/images/{filename}"
