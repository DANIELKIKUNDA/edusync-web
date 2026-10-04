#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Le fichier .env vient d'être créé. Remplace les secrets CHANGE_... puis relance." >&2
  exit 2
fi
if grep -Eq 'CHANGE_(OWNER|TENANT|PLATFORM)_PASSWORD|CHANGE_ME_NOW|CHANGE_WITH_AT_LEAST' .env; then
  echo "Secrets placeholders détectés dans .env." >&2
  exit 2
fi
docker compose up -d --build
docker compose ps
docker compose run --rm migrator python scripts/g1_live_certification.py
docker compose run --rm -e EDUSYNC_API_BASE_URL=http://backend:8000/api/v1 migrator python scripts/g1_api_probe.py
echo "G1 WEB-0C terminé."
