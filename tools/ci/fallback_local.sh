#!/usr/bin/env bash
# CI de secours EduSync Web, hors GitHub Actions. AUCUN déploiement.
# À exécuter uniquement sur un hôte de test autorisé, non sur une machine de production.
set -Eeuo pipefail
umask 077

usage() {
  echo "Usage: bash tools/ci/fallback_local.sh <SHA-complet-de-40-caracteres>" >&2
  exit 64
}

[[ $# -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || usage
SHA="$1"
ROOT="$(git rev-parse --show-toplevel)"
# Autoriser HEAD (commit de branche) ou un commit contenu dans origin/main.
# La copie testée provient TOUJOURS du SHA fourni, pas du checkout de l'outillage.
if [[ "$(git -C "$ROOT" rev-parse HEAD)" != "$SHA" ]]; then
  MAIN_REF="$(git -C "$ROOT" rev-parse -q --verify refs/remotes/origin/main || true)"
  if [[ -z "$MAIN_REF" ]] || ! git -C "$ROOT" merge-base --is-ancestor "$SHA" "$MAIN_REF"; then
    echo "REFUS : le SHA doit etre HEAD ou un ancetre de origin/main (faire git fetch origin)." >&2
    exit 65
  fi
fi
git -C "$ROOT" cat-file -e "$SHA^{commit}"
for cmd in docker tar git awk df tee; do
  command -v "$cmd" >/dev/null || { echo "Commande manquante : $cmd" >&2; exit 69; }
done
[[ "$EUID" -ne 0 ]] || { echo "REFUS : ne pas lancer ce script avec sudo/root." >&2; exit 77; }
docker info >/dev/null 2>&1 || { echo "Docker indisponible ou droits Docker insuffisants." >&2; exit 69; }

# Ne pas mettre en concurrence les tests avec les services critiques du VPS.
mem_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
disk_kb="$(df -Pk /tmp | awk 'END {print $4}')"
if (( mem_kb < 4194304 || disk_kb < 12582912 )); then
  echo "REFUS : il faut au moins 4 Gio de RAM disponibles et 12 Gio libres dans /tmp." >&2
  echo "Utiliser un serveur de CI dedie ou liberer les ressources sans toucher aux services en production." >&2
  exit 75
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$HOME/edusync-ci-reports/${SHA:0:12}-$STAMP"
mkdir -p "$OUT"
chmod 700 "$OUT"
WORK="$(mktemp -d /tmp/edusync-ci.XXXXXXXX)"
NET="edusync-fallback-$(basename "$WORK" | cut -d. -f2)"
PG="${NET}-postgres"
CURRENT="preflight"
RESULT="FAIL"
cleanup() {
  rc=$?
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf -- "$WORK"
  {
    printf 'sha=%s\nstarted_utc=%s\nfinished_utc=%s\nresult=%s\nlast_stage=%s\n' \
      "$SHA" "$STAMP" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RESULT" "$CURRENT"
    printf 'scope=CI locale avec PostgreSQL et navigateur, PAS de preuve CI GitHub ni de deploiement\n'
  } > "$OUT/summary.txt"
  echo "Rapport : $OUT/summary.txt"
  exit "$rc"
}
trap cleanup EXIT

log_step() {
  CURRENT="$1"; shift
  echo "===== $CURRENT (SHA ${SHA:0:12}) ====="
  if "$@" 2>&1 | tee "$OUT/$CURRENT.log"; then
    echo "PASS $CURRENT" | tee -a "$OUT/resultats.txt"
  else
    echo "FAIL $CURRENT" | tee -a "$OUT/resultats.txt"
    return 1
  fi
}

git -C "$ROOT" archive "$SHA" | tar -x -C "$WORK"
docker network create --driver bridge "$NET" >/dev/null

# PostgreSQL jetable, sans publication de port et sans réutilisation des bases existantes.
log_step postgres_start docker run -d --rm \
  --name "$PG" --network "$NET" --cpus=1 --memory=1g --pids-limit=128 \
  -e POSTGRES_USER=edusync_owner -e POSTGRES_PASSWORD=ci-owner-only \
  -e POSTGRES_DB=edusync postgres:16

CURRENT="postgres_ready"
ok=0
for i in $(seq 1 60); do
  if docker exec "$PG" pg_isready -U edusync_owner -d edusync >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 2
done
[[ "$ok" == 1 ]] || { echo "PostgreSQL de test indisponible." >&2; exit 1; }

# Même socle de contrôles que ci.yml : Python 3.13, migrations, rôles, caisse et audits.
log_step backend_rbac_security docker run --rm --init \
  --network "$NET" --cpus=2 --memory=3g --pids-limit=384 \
  --security-opt no-new-privileges \
  -v "$WORK:/code" -w /code/backend \
  -e PYTHONPATH=src -e PYTHONUTF8=1 -e CI=true \
  -e "EDUSYNC_OWNER_DATABASE_URL=postgresql+psycopg://edusync_owner:ci-owner-only@$PG:5432/edusync" \
  -e "EDUSYNC_TENANT_DATABASE_URL=postgresql+psycopg://edusync_tenant:ci-tenant-only@$PG:5432/edusync" \
  -e "EDUSYNC_PLATFORM_DATABASE_URL=postgresql+psycopg://edusync_platform:ci-platform-only@$PG:5432/edusync" \
  python:3.13-bookworm bash -euo pipefail -c '
    python -m pip install -c requirements.lock .
    python -m pip install -c requirements.lock pytest pypdf
    python -m compileall -q src
    python -m pytest -q -p no:cacheprovider
    export EDUSYNC_MIGRATE_UNTIL=0084_platform_messaging_cockpit
    python scripts/provision_database.py
    python ../tools/ci/rbac_seed.py
    python ../tools/ci/rbac_snapshot.py snapshot /tmp/rbac_before.json --legacy
    export EDUSYNC_MIGRATE_UNTIL=0085_school_rbac_policies
    python scripts/provision_database.py
    python ../tools/ci/rbac_snapshot.py snapshot /tmp/rbac_after.json
    python ../tools/ci/rbac_snapshot.py compare /tmp/rbac_before.json /tmp/rbac_after.json
    unset EDUSYNC_MIGRATE_UNTIL
    python scripts/provision_database.py
    python ../tools/ci/rbac_registry.py check
    python ../tools/ci/cashier_postgres_integration.py
    (cd /code && python tools/ci/secret_patterns.py && python tools/certification/supply_chain.py)
    python -m pip install pip-audit==2.10.1
    pip-audit -r requirements.lock --progress-spinner off
  '

# Tests PWA et Chromium : une architecture ARM64 peut nécessiter un runner amd64 distinct.
# Un navigateur absent est un ECHEC, jamais un faux PASS.
log_step frontend_browser docker run --rm --init \
  --network "$NET" --cpus=2 --memory=4g --pids-limit=512 \
  --security-opt no-new-privileges \
  -v "$WORK:/code" -w /code/frontend \
  node:24-bookworm bash -euo pipefail -c '
    npm ci
    npx tsc --noEmit -p tsconfig.json
    npm test
    npx playwright install --with-deps chromium
    npm run test:browser
    npx vite build
    EDUSYNC_TEST_BUILD=1 npm run test:browser -- platform.spec.ts offline.spec.ts school_offline.spec.ts
    npm audit --omit=dev
  '

CURRENT="complete"
RESULT="PASS"
echo "PASS des contrôles locaux pour $SHA. Ce rapport ne remplace PAS la CI/CD GitHub ni les gates staging/production."
