#!/usr/bin/env bash
# Mise a jour du serveur en production. UNE seule commande, a lancer sur le VPS
# (ou via `ssh utilisateur@serveur bash /home/agents/agents/deploy/deploy.sh`).
set -euo pipefail

APP_DIR="/home/agents/agents"
cd "$APP_DIR"

echo "== git pull =="
sudo -u agents git pull

echo "== Dependances =="
sudo -u agents "$APP_DIR/.venv/bin/pip" install -r requirements.txt -q

echo "== Redemarrage du service =="
sudo systemctl restart agents-platform

echo "== Statut =="
sudo systemctl status agents-platform --no-pager -l | head -10
echo "Termine."
