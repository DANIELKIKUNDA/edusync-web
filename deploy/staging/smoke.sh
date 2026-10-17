#!/usr/bin/env bash
# EduSync — smoke tests staging (sur le serveur, après « docker compose up »). Sort en erreur au premier contrôle raté.
# Contrôles : services en marche (aucun en redémarrage), migrateur terminé avec 0, API saine (healthcheck Docker),
# contrôles de sécurité staging actifs, page et API servies par nginx, état d'installation lisible.
set -Eeuo pipefail
ENV_FILE="${EDUSYNC_ENV_FILE_PATH:?fichier des variables obligatoire}"
PROJECT="${EDUSYNC_COMPOSE_PROJECT:-edusync-staging}"
REPO="${EDUSYNC_APP_DIR:-/opt/edusync}/repo"
HOST_HEADER="$(grep -E '^EDUSYNC_TRUSTED_HOSTS=' "$ENV_FILE" | cut -d= -f2 | cut -d, -f1)"
PROFILE_ARGS=()
grep -qE '^EDUSYNC_DEPLOY_TLS_PROFILE=true$' "$ENV_FILE" && PROFILE_ARGS=(--profile tls)
compose() { docker compose --env-file "$ENV_FILE" -p "$PROJECT" "${PROFILE_ARGS[@]}" -f "$REPO/docker-compose.yml" -f "$REPO/deploy/staging/docker-compose.images.yml" "$@"; }
ok() { printf 'SMOKE PASS %s\n' "$*"; }
ko() { printf 'SMOKE FAIL %s\n' "$*"; exit 1; }

for _ in $(seq 1 60); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q backend)" 2>/dev/null)" == "healthy" ]] && break
  sleep 5
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q backend)" 2>/dev/null)" == "healthy" ]] || ko "API non saine après 5 minutes"
ok "API saine (healthcheck)"

[[ "$(docker inspect -f '{{.State.ExitCode}}' "$(compose ps -a -q migrator | head -n1)")" == "0" ]] || ko "migrateur en erreur"
ok "migrations appliquées (migrateur code 0)"

for svc in postgres redis object-storage backend outbox-worker communications-worker frontend backup; do
  state="$(docker inspect -f '{{.State.Status}} {{.RestartCount}}' "$(compose ps -q "$svc")" 2>/dev/null || echo 'absent 0')"
  [[ "$state" == running* ]] || ko "service $svc : $state"
done
sleep 20
for svc in backend outbox-worker communications-worker frontend; do
  [[ "$(docker inspect -f '{{.State.Status}}' "$(compose ps -q "$svc")")" == "running" ]] || ko "service $svc arrêté après démarrage"
done
ok "8 services en marche, aucun en boucle de redémarrage"

compose exec -T backend python -c "from edusync.bootstrap.settings import Settings;s=Settings();s.assert_runtime_safe();assert s.env in ('staging','production')" \
  || ko "contrôles de sécurité staging"
ok "contrôles de sécurité actifs (EDUSYNC_ENV=staging)"

code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${HOST_HEADER}" http://127.0.0.1:8080/)"
[[ "$code" == "200" ]] || ko "page d'accueil via nginx : HTTP $code"
code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${HOST_HEADER}" http://127.0.0.1:8080/health-api)"
[[ "$code" == "200" ]] || ko "santé API via nginx : HTTP $code"
curl -s -H "Host: ${HOST_HEADER}" http://127.0.0.1:8080/api/v1/setup/status | grep -q '"setup_required"' || ko "API /setup/status"
ok "nginx sert la PWA et l'API"
echo "SMOKE OK"
