"""Generation de vraies videos (petits montages promo) via l'API Video unifiee d'OpenRouter
(POST /api/v1/videos). Ne necessite PAS d'approbation humaine : ca ne fait qu'ecrire un
fichier local, aucune action externe/irreversible. L'approbation intervient plus tard, au
moment de PUBLIER (voir staging.py) -- meme principe que generate_ad_image.

Generation video est asynchrone cote OpenRouter (30s a quelques minutes) : ce module soumet
la requete puis attend (polling) le resultat dans le meme appel d'outil, pour rester coherent
avec NO_FUTURE_PROMISES_INSTRUCTION (l'agent ne doit jamais dire "je vous notifie quand c'est
pret" -- soit le fichier existe a la fin de l'appel, soit l'outil renvoie une erreur claire).
"""
from __future__ import annotations

import os
import time
import uuid

import requests
from langchain_core.tools import tool

from common.paths import OUTPUT_DIR

_API_BASE = "https://openrouter.ai/api/v1"
_TIMEOUT_SECONDS = 60
_POLL_INTERVAL_SECONDS = 15
_MAX_WAIT_SECONDS = 360  # 6 min -- au-dela, on arrete plutot que de bloquer l'agent indefiniment

# google/veo-3.1-lite : le moins cher des modeles video "grand nom" disponibles sur
# OpenRouter au 2026-09-26 (verifie en direct via GET /api/v1/videos/models, pas de memoire
# d'entrainement) -- $0.03/s en 720p sans audio, $0.05/s avec audio. Un clip de 6s revient
# donc a 0.18$ (sans son) ou 0.30$ (avec son) : largement adapte a des "petits montages".
_DEFAULT_MODEL = "google/veo-3.1-lite"

VIDEOS_DIR = OUTPUT_DIR / "marketing" / "videos"


class VideoGenerationError(RuntimeError):
    pass


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


@tool
def generate_ad_video(
    prompt: str,
    duration: int = 6,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    generate_audio: bool = False,
) -> str:
    """Genere un petit montage video publicitaire a partir d'une description textuelle et
    l'enregistre localement (modele google/veo-3.1-lite par defaut, le moins cher disponible).
    `duration` : secondes (4, 6 ou 8 pour ce modele). `resolution` : '720p' ou '1080p'.
    `aspect_ratio` : '16:9' (paysage) ou '9:16' (vertical, format story/reel). `generate_audio` :
    True pour generer du son synchronise (plus cher). Cet appel BLOQUE le temps de la generation
    reelle (30s a quelques minutes) -- c'est normal, la video existe reellement a la fin de
    l'appel, pas de suivi asynchrone a promettre. Retourne le chemin du fichier -- pas de
    publication, juste la generation."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "ERREUR: OPENROUTER_API_KEY manquant dans .env -- impossible de generer une video."

    try:
        submit = requests.post(
            f"{_API_BASE}/videos",
            headers=_headers(api_key),
            json={
                "model": _DEFAULT_MODEL,
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "generate_audio": generate_audio,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        if not submit.ok:
            detail = _error_detail(submit)
            return f"ERREUR API OpenRouter (video, {submit.status_code}): {detail}"

        job = submit.json()
        job_id = job.get("id")
        if not job_id:
            return f"ERREUR: reponse OpenRouter sans id de job: {job}"

        video_bytes = _poll_until_done(job_id, api_key)
    except requests.RequestException as exc:
        return f"ERREUR reseau lors de la generation video: {exc}"
    except VideoGenerationError as exc:
        return f"ERREUR generation video: {exc}"

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    # UUID complet (128 bits), meme discipline que generate_ad_image : ce nom de fichier sera
    # la seule protection d'acces si ce dossier est un jour expose publiquement comme /media.
    filename = f"{uuid.uuid4().hex}.mp4"
    target = VIDEOS_DIR / filename
    target.write_bytes(video_bytes)

    return f"OK: video generee dans output/marketing/videos/{filename}"


def _error_detail(response: requests.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", response.text)
    except ValueError:
        return response.text


def _poll_until_done(job_id: str, api_key: str) -> bytes:
    elapsed = 0
    while elapsed <= _MAX_WAIT_SECONDS:
        poll = requests.get(f"{_API_BASE}/videos/{job_id}", headers=_headers(api_key), timeout=_TIMEOUT_SECONDS)
        if not poll.ok:
            raise VideoGenerationError(f"echec du suivi du job ({poll.status_code}): {_error_detail(poll)}")

        status = poll.json().get("status")
        if status == "completed":
            content = requests.get(
                f"{_API_BASE}/videos/{job_id}/content",
                params={"index": 0},
                headers=_headers(api_key),
                timeout=_TIMEOUT_SECONDS,
            )
            if not content.ok:
                raise VideoGenerationError(f"echec du telechargement ({content.status_code}): {_error_detail(content)}")
            return content.content
        if status == "failed":
            raise VideoGenerationError(poll.json().get("error", "raison inconnue"))

        time.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    raise VideoGenerationError(
        f"delai depasse ({_MAX_WAIT_SECONDS}s) sans que le job {job_id} soit termine -- "
        f"reessayer avec une video plus courte ou une resolution plus basse."
    )
