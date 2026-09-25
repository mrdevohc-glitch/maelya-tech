"""Outils de scan securite pour security_agent. Detection best-effort par motifs et outils
standards (npm audit / pip list --outdated) -- ne remplace pas un audit securite professionnel."""
from __future__ import annotations

import re
import subprocess

from langchain_core.tools import tool

from common.workdir import get_working_directory

_SECRET_PATTERNS = {
    "cle AWS": re.compile(r"AKIA[0-9A-Z]{16}"),
    "cle privee": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "token/API key en dur": re.compile(
        r"(?:api[_-]?key|secret|token|password)['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]",
        re.IGNORECASE,
    ),
}

_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "output", ".previews"}


@tool
def run_secret_scan() -> str:
    """Scanne les fichiers texte du projet pour des secrets codes en dur (cles AWS, cles
    privees, tokens/API keys/mots de passe en clair). Detection par motifs, pas exhaustive."""
    root = get_working_directory()
    findings = []
    for file in root.rglob("*"):
        if not file.is_file() or any(part in _SKIP_DIRS for part in file.parts):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{file.relative_to(root)}: possible {label}")

    if not findings:
        return "Aucun secret evident detecte (scan par motifs, pas exhaustif -- ne remplace pas gitleaks/trufflehog)."
    return "Secrets potentiels trouves:\n" + "\n".join(findings)


@tool
def run_dependency_scan() -> str:
    """Audit de dependances : `npm audit` si package.json existe, sinon `pip list --outdated`."""
    root = get_working_directory()
    if (root / "package.json").exists():
        cmd = ["npm", "audit"]
    elif (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        cmd = ["pip", "list", "--outdated"]
    else:
        return "Aucun package.json / requirements.txt / pyproject.toml trouve dans le projet."

    try:
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return f"Outil introuvable pour lancer: {' '.join(cmd)}"
    except subprocess.TimeoutExpired:
        return "Audit interrompu apres 120s (timeout)."

    output = (result.stdout + result.stderr).strip()
    if len(output) > 6000:
        output = output[-6000:]
    return output or "Aucun probleme signale."
