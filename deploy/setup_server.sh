#!/usr/bin/env bash
# Installation initiale sur un VPS Debian/Ubuntu neuf. A executer UNE SEULE FOIS, avec
# l'utilisateur (nous le ferons ensemble, pas a pas -- ce script sert de reference).
#
# AVANT de lancer : remplace REPO_URL par l'URL de ton depot git prive (cree-le d'abord,
# ex: un repo prive sur GitHub, puis `git remote add origin <url>` + premier commit + push).
set -euo pipefail

REPO_URL="git@github.com:TON-COMPTE/agents.git"   # <-- a remplacer
APP_DIR="/home/agents/agents"

echo "== Paquets systeme =="
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git

echo "== Utilisateur dedie (pas root) =="
if ! id -u agents >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash agents
fi

echo "== Clone du depot =="
sudo -u agents git clone "$REPO_URL" "$APP_DIR"

echo "== Environnement Python =="
sudo -u agents python3 -m venv "$APP_DIR/.venv"
sudo -u agents "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "== Playwright (Chromium + dependances systeme, pour frontend_agent) =="
sudo -u agents "$APP_DIR/.venv/bin/playwright" install --with-deps chromium

echo "== Fichier .env =="
echo "-> Copie ton .env local (avec les vraies cles API) vers $APP_DIR/.env maintenant"
echo "   (scp depuis ta machine, PAS via git -- .env n'est jamais commite)."
read -p "Appuie sur Entree une fois .env copie sur le serveur..."

echo "== Mot de passe de la plateforme =="
sudo -u agents "$APP_DIR/.venv/bin/python" "$APP_DIR/webapp/set_password.py"

echo "== Service systemd =="
sudo cp "$APP_DIR/deploy/agents-platform.service" /etc/systemd/system/agents-platform.service
sudo systemctl daemon-reload
sudo systemctl enable --now agents-platform

echo "== Termine =="
echo "Verifie avec : sudo systemctl status agents-platform"
echo "Logs en direct : sudo journalctl -u agents-platform -f"
echo "Prochaine etape : installer cloudflared et creer un Tunnel vers http://localhost:8000"
echo "(fait ensemble, voir la documentation Cloudflare Tunnel)."
