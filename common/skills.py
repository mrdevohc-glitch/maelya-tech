"""Chargement des skills marketing/contenu copiees localement sous skills/ (voir skills/README.md
pour l'origine de chaque copie)."""
from __future__ import annotations

from common.paths import SKILLS_DIR


def load_skill(*relative_parts: str) -> str:
    """Lit un SKILL.md sous skills/ et retire son frontmatter YAML (entre les lignes '---')."""
    path = SKILLS_DIR.joinpath(*relative_parts)
    if not path.exists():
        return f"[skill manquante: {path}]"
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()


def load_skills(*paths: tuple[str, ...]) -> str:
    """Combine plusieurs skills (chacune un tuple de segments de chemin sous skills/) en un
    seul bloc de texte, separe par '---'."""
    return "\n\n---\n\n".join(load_skill(*p) for p in paths)
