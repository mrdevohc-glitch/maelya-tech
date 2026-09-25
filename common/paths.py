"""Chemins partages du projet d'agents (independants du projet cible en cours de traitement)."""
from __future__ import annotations

from pathlib import Path

AGENTS_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = AGENTS_ROOT / "output"
CONFIG_DIR = AGENTS_ROOT / "config"
CONTEXT_DIR = AGENTS_ROOT / "context"
SKILLS_DIR = AGENTS_ROOT / "skills"
