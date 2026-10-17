#!/usr/bin/env bash
# EduSync — déploiement staging exécuté SUR le serveur (CICD.md). Envoyé par le workflow « Deploy staging » via SSH
# (version du script = celle du commit déployé). Ne gère que le staging ; aucune action de production.
#
# Usage : remote_deploy.sh <sha-complet> <registry>      (jeton GHCR éphémère lu sur l'entrée standard)
#
# Disposition attendue sur le serveur (préparée une fois par l'opérateur, voir CICD.md) :
#   $EDUSYNC_APP_DIR/repo        clone du dépôt (fichiers compose / deploy du commit déployé)
#   $EDUSYNC_APP_DIR/env/staging.env   fichier d'environnement (secrets, jamais dans Git), EDUSYNC_ENV=staging
#   $EDUSYNC_APP_DIR/state/      current / previous : SHA déployés
#
# Étapes : vérifications → images du SHA (pull) → sauvegarde vérifiée avant mise à jour → migrations (service
# migrator, code 0 exigé) → démarrage → smoke tests → PASS : version conservée ; FAIL :
#   * aucune migration nouvelle appliquée  → rollback automatique vers le SHA précédent (images + fichiers compose),
#     puis smoke tests de la version restaurée ;
#   * migration nouvelle appliquée         → arrêt sûr (API, workers et frontend arrêtés, base et volumes intacts),
#     restauration de la sauvegarde d'avant mise à jour décidée par un humain (commande affichée).
set -Eeuo pipefail

SHA="${1:?SHA du commit à déployer obligatoire}"
REGISTRY="${2:?registre des images obligatoire (ghcr.io/<owner>)}"
APP_DIR="${EDUSYNC_APP_DIR:-/opt/edusync}"
ENV_FILE="${EDUSYNC_STAGING_ENV:-$APP_DIR/env/staging.env}"
PROJECT="${EDUSYNC_COMPOSE_PROJECT:-edusync-staging}"
REPO="$APP_DIR/repo"
STATE="$APP_DIR/state"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "ÉCHEC : $*"; exit 1; }

[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "SHA invalide (40 caractères hexadécimaux attendus)"
[[ -f "$ENV_FILE" ]] || die "fichier d'environnement absent : $ENV_FILE"
grep -qE '^EDUSYNC_ENV=(staging|production)$' "$ENV_FILE" || die "EDUSYNC_ENV doit valoir staging dans $ENV_FILE"
grep -qE '^EDUSYNC_ENV=production$' "$ENV_FILE" && die "ce script ne déploie jamais la production"
[[ -d "$REPO/.git" ]] || die "clone du dépôt absent : $REPO"
mkdir -p "$STATE"
PREVIOUS="$(cat "$STATE/current" 2>/dev/null || true)"

# Ephemeral registry token (GITHUB_TOKEN of the workflow run) read on stdin: never written to disk or to the logs.
read -r GHCR_TOKEN || true
if [[ -n "${GHCR_TOKEN:-}" ]]; then
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:-github-actions}" --password-stdin >/dev/null
fi
unset GHCR_TOKEN

# Public TLS by the Caddy service of the compose only when the env file asks for it (EDUSYNC_DEPLOY_TLS_PROFILE=true);
# when the host platform terminates TLS (Coolify / Traefik), the profile stays off.
PROFILE_ARGS=()
grep -qE '^EDUSYNC_DEPLOY_TLS_PROFILE=true$' "$ENV_FILE" && PROFILE_ARGS=(--profile tls)
compose() {
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" "${PROFILE_ARGS[@]}" -f "$REPO/docker-compose.yml" -f "$REPO/deploy/staging/docker-compose.images.yml" "$@"
}
checkout() { git -C "$REPO" fetch --quiet --tags origin && git -C "$REPO" checkout --quiet --detach "$1"; }
migrations_count() {
  compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM schema_migrations" 2>/dev/null || echo 0' | tr -d '[:space:]'
}
smoke() { EDUSYNC_ENV_FILE_PATH="$ENV_FILE" EDUSYNC_COMPOSE_PROJECT="$PROJECT" bash "$REPO/deploy/staging/smoke.sh"; }

log "Déploiement staging de $SHA (précédent : ${PREVIOUS:-aucun})"
checkout "$SHA"
export EDUSYNC_IMAGE_REGISTRY="$REGISTRY" EDUSYNC_IMAGE_TAG="$SHA" EDUSYNC_ENV_FILE="$ENV_FILE"

log "Images du commit (pull)"
compose pull --quiet migrator backend outbox-worker communications-worker frontend backup

BEFORE=0
if compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  BEFORE="$(migrations_count)"
  if compose ps --status running --services 2>/dev/null | grep -qx backup; then
    log "Sauvegarde vérifiée avant mise à jour"
    compose exec -T backup sh /usr/local/bin/edusync-backup once || die "sauvegarde d'avant mise à jour en échec : déploiement annulé (rien n'a changé)"
  fi
fi

log "Migrations puis démarrage (le service migrator doit sortir avec le code 0)"
set +e
compose up -d --no-build --remove-orphans
UP=$?
MIG_EXIT="$(docker inspect -f '{{.State.ExitCode}}' "$(compose ps -a -q migrator | head -n1)" 2>/dev/null || echo 1)"
set -e
AFTER="$(migrations_count || echo "$BEFORE")"

if [[ $UP -eq 0 && "$MIG_EXIT" == "0" ]] && smoke; then
  [[ -n "$PREVIOUS" && "$PREVIOUS" != "$SHA" ]] && echo "$PREVIOUS" > "$STATE/previous"
  echo "$SHA" > "$STATE/current"
  log "PASS : $SHA conservé (migrations : $BEFORE → $AFTER)"
  exit 0
fi

log "Le déploiement de $SHA a échoué (compose=$UP, migrateur=$MIG_EXIT, migrations : $BEFORE → $AFTER)"
if [[ -n "$PREVIOUS" && "$AFTER" == "$BEFORE" ]]; then
  log "Aucune migration nouvelle : rollback automatique vers $PREVIOUS"
  checkout "$PREVIOUS"
  export EDUSYNC_IMAGE_TAG="$PREVIOUS"
  compose up -d --no-build --remove-orphans
  if smoke; then
    log "ROLLBACK PASS : $PREVIOUS de nouveau en service ; $SHA refusé"
  else
    log "ROLLBACK FAIL : la version précédente ne répond pas non plus — intervention humaine requise"
  fi
  exit 2
fi

log "Migration nouvelle appliquée (ou premier déploiement) : arrêt sûr, aucune donnée modifiée par ce script"
compose stop frontend backend outbox-worker communications-worker || true
log "Base, volumes et sauvegarde d'avant mise à jour conservés. Restauration (décision humaine) : voir CICD.md §5"
exit 3
