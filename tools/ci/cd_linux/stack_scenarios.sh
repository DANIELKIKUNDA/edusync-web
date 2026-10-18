#!/bin/bash
# Real end-to-end scenarios on a disposable Linux runner: sshd → forced command → sudo → installed controller → GitHub
# API → GHCR → Docker, with the real images of two CI-certified commits (same migrations) and real PostgreSQL, Redis,
# SeaweedFS, backup. Faults are injected from OUTSIDE the controller (occupied port, stopped backup service, tampered
# ledger, backend killed by a watcher); the controller itself has no test hook.
#   CUR_SHA, PREV_SHA : two commits whose CI succeeded on main (images on GHCR), identical backend/migrations
#   RUN_TOKEN         : GITHUB_TOKEN of the certification run (actions: read, packages: read)
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
: "${CUR_SHA:?}" "${PREV_SHA:?}" "${RUN_TOKEN:?}"
PROJECT_FILTER=(--filter label=com.docker.compose.project=edusync-staging)
HOST_HEADER="Host: staging.edusync.test"

state() { sudo python3 -c "import json,sys; d=json.load(open('/var/lib/edusync-deploy/$1.json')); print(eval(sys.argv[1], {}, {'d': d}))" "$2"; }
service_id() { docker ps -aq "${PROJECT_FILTER[@]}" --filter "label=com.docker.compose.service=$1" | head -1; }
health_ok() { curl -fsS -H "$HOST_HEADER" http://127.0.0.1:18080/health-api | grep -q ok; }
verdict_is() { test "$(state last_result "d['verdict']")" == "$1"; }
pg() { docker exec -i "$(service_id postgres)" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$0"' "$1"; }
start_watcher() { # $1 = all | <digest to spare>: kills every backend container of the project not running that digest
  ( while true; do
      for id in $(docker ps -q "${PROJECT_FILTER[@]}" --filter label=com.docker.compose.service=backend); do
        img="$(docker inspect -f '{{.Config.Image}}' "$id" 2>/dev/null || true)"
        if [[ "$1" == all || "$img" != *"$1" ]]; then docker kill "$id" >/dev/null 2>&1 || true; fi
      done
      sleep 1
    done ) & WATCHER=$!
}
stop_watcher() { kill "$WATCHER" 2>/dev/null || true; wait "$WATCHER" 2>/dev/null || true; }

write_staging_env() {
  section "staging.env de test (secrets aléatoires générés sur le runner, jamais affichés)"
  python3 - "$ROOT/.env.example" "$WORK/staging.env" <<'PY'
import base64, re, secrets, sys
text = open(sys.argv[1], encoding="utf-8").read()
r = lambda n=32: secrets.token_hex(n)
pw = {k: r(16) for k in ("owner", "tenant", "platform", "worker")}
values = {
    "EDUSYNC_ENV": "staging",
    "EDUSYNC_OWNER_DATABASE_URL": f"postgresql+psycopg://edusync_owner:{pw['owner']}@postgres:5432/edusync",
    "EDUSYNC_TENANT_DATABASE_URL": f"postgresql+psycopg://edusync_tenant:{pw['tenant']}@postgres:5432/edusync",
    "EDUSYNC_PLATFORM_DATABASE_URL": f"postgresql+psycopg://edusync_platform:{pw['platform']}@postgres:5432/edusync",
    "EDUSYNC_WORKER_DATABASE_URL": f"postgresql+psycopg://edusync_worker:{pw['worker']}@postgres:5432/edusync",
    "POSTGRES_OWNER_PASSWORD": pw["owner"],
    "EDUSYNC_JWT_SECRET": r(32),
    "EDUSYNC_MFA_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    "EDUSYNC_DOCUMENT_LINK_SECRET": r(32),
    "EDUSYNC_OBJECT_STORAGE_ACCESS_KEY": r(10),
    "EDUSYNC_OBJECT_STORAGE_SECRET_KEY": r(24),
    "EDUSYNC_SETUP_TOKEN": r(24),
    "EDUSYNC_PLATFORM_ADMIN_PASSWORD": "",
    "EDUSYNC_CORS_ORIGINS": "https://staging.edusync.test",
    "EDUSYNC_TRUSTED_HOSTS": "staging.edusync.test,localhost",
    "EDUSYNC_PUBLIC_APP_URL": "https://staging.edusync.test",
    "EDUSYNC_DEPLOY_TLS_PROFILE": "false",
}
for k, v in values.items():
    text, n = re.subn(rf"(?m)^{k}=.*$", lambda m: f"{k}={v}", text)
    if not n:
        text += f"\n{k}={v}\n"
open(sys.argv[2], "w", encoding="utf-8").write(text)
PY
  sudo install -o root -g root -m 0600 "$WORK/staging.env" /etc/edusync-deploy/staging.env
  rm -f "$WORK/staging.env"
}

section "Jeton du run (diagnostic sans la valeur)"
echo "      longueur ${#RUN_TOKEN}, caractères hors [A-Za-z0-9] : $(tr -d 'A-Za-z0-9' <<<"$RUN_TOKEN" | fold -w1 | sort -u | tr -d '\n')"
setup_host
install_controller
write_staging_env
INFRA_REFS="$(grep -oE 'docker\.io/[a-z0-9/._-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}' "$CTL" | sort -u)"

section "Autre projet présent sur l'hôte (témoin Coolify sur 127.0.0.1:8000) : ne doit jamais être touché"
docker run -d -q --name coolify-canary --label com.docker.compose.project=coolify -p 127.0.0.1:8000:80 docker.io/library/nginx:1.27-alpine >/dev/null
CANARY="$(docker inspect -f '{{.Id}}' coolify-canary)"

section "Hôte Docker vierge : aucune image EduSync ni d'infrastructure, aucun volume"
for ref in $INFRA_REFS; do docker image rm -f "$ref" >/dev/null 2>&1 || true; done
for ref in $INFRA_REFS; do check "absente : ${ref%@*}" bash -c "! docker image inspect '$ref' >/dev/null 2>&1"; done
check "aucune image ghcr.io/danielkikunda" bash -c "! docker image ls --format '{{.Repository}}' | grep -q '^ghcr.io/danielkikunda/'"
check "aucun volume edusync-staging" test -z "$(docker volume ls -q "${PROJECT_FILTER[@]}")"

section "S0 — port nécessaire déjà occupé par un service hors EduSync"
python3 -m http.server 18080 --bind 127.0.0.1 >/dev/null 2>&1 & BLOCKER=$!
sleep 2
expect_code "refus PORT_CONFLICT" 73 deploy_sha "$CUR_SHA" "$RUN_TOKEN"
check "verdict PORT_CONFLICT journalisé" sudo grep -q "VERDICT=PORT_CONFLICT" /var/log/edusync-deploy/deploy.log
kill "$BLOCKER"; wait "$BLOCKER" 2>/dev/null || true

section "S1 — premier déploiement sur hôte vierge (images préparées par le contrôleur, pile démarrée)"
expect_code "déploiement $CUR_SHA" 0 deploy_sha "$CUR_SHA" "$RUN_TOKEN"
check "verdict DEPLOY_SUCCESS" verdict_is DEPLOY_SUCCESS
check "hôte vierge reconnu explicitement" sudo grep -q "hôte vierge reconnu" /var/log/edusync-deploy/deploy.log
for ref in $INFRA_REFS; do check "préparée par digest : ${ref%@*}" docker image inspect "$ref" -f '{{.Id}}'; done
check "PWA, santé et API servies (127.0.0.1:18080)" health_ok
PUBLISHED="$(docker ps "${PROJECT_FILTER[@]}" --format '{{.Ports}}' | tr ',' '\n' | sed 's/^ *//' | { grep -F -- '->' || true; } | sort -u | tr '\n' ' ')"
echo "      ports publiés par edusync-staging : $PUBLISHED"
check "seul port publié : 127.0.0.1:18080 (rien pour API, PostgreSQL, Redis, SeaweedFS)" test "$PUBLISHED" == "127.0.0.1:18080->80/tcp "
check "aucune écoute générique 5432/6379/8333/8000 par EduSync" bash -c "! ss -ltnH | grep -E '(0\.0\.0\.0|\[::\]|\*):(5432|6379|8333|18080)\b'"
CUR_BACKEND="$(state current "d['digests']['edusync-backend']")"
sleep 20   # let the backup service finish its start-up run before the next verified backup
echo "      sauvegarde de démarrage : $(docker exec "$(service_id backup)" cat /backup-status/last.json 2>&1 || true)"
docker logs --tail 15 "$(service_id backup)" 2>&1 | sed 's/^/      backup> /'
set +e; docker exec "$(service_id backup)" sh /usr/local/bin/edusync-backup once 2>&1 | tail -15 | sed 's/^/      once> /'; set -e

section "MFA — enrôlement TOTP réel du premier Manager Système (HTTP via nginx, cookies réels)"
SETUP_TOKEN="$(sudo sed -n 's/^EDUSYNC_SETUP_TOKEN=//p' /etc/edusync-deploy/staging.env)"
set +e; python3 "$ROOT/tools/ci/cd_linux/mfa_probe.py" http://127.0.0.1:18080 staging.edusync.test https://staging.edusync.test "$SETUP_TOKEN" | tee "$WORK/mfa.out"; mfa_code=${PIPESTATUS[0]}; set -e
unset SETUP_TOKEN
check "sonde MFA" test "$mfa_code" == 0
docker logs "$(service_id backend)" 2>&1 | grep -E "mfa_(enroll_confirm|verify)_refused" | tail -12 | sed 's/^/      journal API> /' || true
check "journal API : raisons MFA présentes, aucun secret" bash -c "docker logs $(service_id backend) 2>&1 | grep -q 'reason=' && ! docker logs $(service_id backend) 2>&1 | grep -qiE 'secret=|otpauth'"

section "S2 — échec de la nouvelle version, registre identique → rollback par digests précédents"
start_watcher "$CUR_BACKEND"
expect_code "déploiement $PREV_SHA cassé (backend tué)" 2 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
stop_watcher
check "verdict ROLLBACK_SUCCESS" verdict_is ROLLBACK_SUCCESS
check "version courante inchangée ($CUR_SHA)" test "$(state current "d['sha']")" == "$CUR_SHA"
check "rollback_ok vrai" test "$(state failed "d['rollback_ok']")" == True
check "service rétabli après rollback" health_ok

section "S3 — sauvegarde obligatoire : service de sauvegarde arrêté"
BACKEND_BEFORE="$(service_id backend)"
docker stop "$(service_id backup)" >/dev/null
expect_code "refus BACKUP_REQUIRED_FAILED" 71 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
check "aucun conteneur applicatif recréé" test "$(service_id backend)" == "$BACKEND_BEFORE"
docker start "$(service_id backup)" >/dev/null
sleep 30

section "S4 — registre des migrations obligatoire et cohérent"
pg "INSERT INTO schema_migrations(version) VALUES ('9999_tampered')" >/dev/null
expect_code "registre divergent du dernier enregistré" 72 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
pg "DELETE FROM schema_migrations WHERE version='9999_tampered'" >/dev/null
pg "INSERT INTO schema_migrations(version) VALUES ('bad version!')" >/dev/null
expect_code "registre illisible (entrée invalide)" 72 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
pg "DELETE FROM schema_migrations WHERE version='bad version!'" >/dev/null
pg "ALTER TABLE schema_migrations RENAME TO schema_migrations_hidden" >/dev/null
expect_code "registre absent" 72 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
pg "ALTER TABLE schema_migrations_hidden RENAME TO schema_migrations" >/dev/null
check "aucun conteneur applicatif recréé" test "$(service_id backend)" == "$BACKEND_BEFORE"

section "S5 — rollback dont les smoke tests échouent → jamais ROLLBACK_SUCCESS"
start_watcher all
expect_code "déploiement cassé + rollback cassé" 4 deploy_sha "$PREV_SHA" "$RUN_TOKEN"
stop_watcher
check "verdict ROLLBACK_FAILED" verdict_is ROLLBACK_FAILED
check "rollback_ok faux" test "$(state failed "d['rollback_ok']")" == False
check "API, workers et frontend arrêtés ; PostgreSQL conservé" bash -c "test \"\$(docker inspect -f '{{.State.Running}}' $(service_id frontend))\" == false && test \"\$(docker inspect -f '{{.State.Running}}' $(service_id postgres))\" == true"

section "S6 — reprise : redéploiement de la version saine"
expect_code "déploiement $CUR_SHA" 0 deploy_sha "$CUR_SHA" "$RUN_TOKEN"
check "verdict DEPLOY_SUCCESS" verdict_is DEPLOY_SUCCESS
check "service rétabli" health_ok

section "Garanties finales"
check "témoin Coolify intact (même conteneur, toujours en marche)" test "$(docker inspect -f '{{.Id}} {{.State.Running}}' coolify-canary)" == "$CANARY true"
check "deploy toujours hors du groupe docker" bash -c '! id -nG deploy | tr " " "\n" | grep -qx docker'
check "aucun jeton dans le journal" bash -c "! sudo grep -q '$RUN_TOKEN' /var/log/edusync-deploy/deploy.log"
check "aucun DOCKER_CONFIG temporaire restant" test -z "$(sudo ls -A /run/edusync-deploy 2>/dev/null)"
sudo cat /var/log/edusync-deploy/deploy.log | grep -E "VERDICT=|REFUS|ÉCHEC|ROLLBACK|PASS" | sed 's/^/      /'

finish
