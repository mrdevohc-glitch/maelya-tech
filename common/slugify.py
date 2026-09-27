"""Slug de nom de projet, partage par cli.py, webapp/job_runner.py et webapp/app.py -- calcule
le meme dossier `output/projects/<slug>` par defaut quand aucun project_dir n'est fourni."""
from __future__ import annotations

import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "projet"
