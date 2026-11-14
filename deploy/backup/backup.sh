#!/bin/sh
# EduSync — scheduled backup with verified restore (pre-staging S9; same method as tools/local/backup_restore.py).
#
# Every BACKUP_INTERVAL_SECONDS (default 24 h):
#   1. pg_dump -Fc of the database and a copy of every object of the documents bucket (rclone, remote "src");
#   2. SHA256SUMS of the backup;
#   3. restore into an ISOLATED database (edusync_restore_check), then check the row counts of the key tables: each
#      restored count must lie between the count read just before and just after the dump (live writes continue);
#   4. optional off-site copy (rclone remote named in BACKUP_OFFSITE, for example offsite:edusync-backups/staging);
#   5. retention: local backups older than BACKUP_KEEP_DAYS are deleted;
#   6. /backup-status/last.json {"finished_at","ok","restore_verified","offsite","duration_seconds","restore_seconds"}
#      for the platform health screen (the restore is timed on every run: a recovery time measured, not assumed);
#   7. optional external heartbeat (BACKUP_HEARTBEAT_URL, https, e.g. Healthchecks.io): <url>/start, then <url> on a
#      verified backup or <url>/fail with the reason. No ping for a day = the external service alerts the owner, even
#      when the server itself is down. The URL is never written to the logs.
# The production database is only read. No secret is written to the logs or to the status file.
set -u
# Production Coolify (docker-compose.coolify.yml) : secrets lus depuis des fichiers montés (VAR_FILE), jamais depuis les
# variables de Coolify, injectées dans tous les conteneurs. Sans *_FILE (staging, local), rien ne change.
for v in PGPASSWORD RCLONE_CONFIG_SRC_ACCESS_KEY_ID RCLONE_CONFIG_SRC_SECRET_ACCESS_KEY; do
  eval "f=\${${v}_FILE:-}"
  if [ -n "$f" ]; then
    [ -s "$f" ] || { echo "secret manquant : $f" >&2; exit 1; }
    eval "$v=\$(cat \"\$f\")"; export "$v"
  fi
done
: "${PGHOST:=postgres}" "${PGDATABASE:=edusync}" "${PGUSER:?PGUSER required}" "${PGPASSWORD:?PGPASSWORD required}"
export PGHOST PGDATABASE PGUSER PGPASSWORD
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BUCKET="${BACKUP_SOURCE_BUCKET:-edusync-documents}"
OFFSITE="${BACKUP_OFFSITE:-}"
OUT=/backups
STATUS=/backup-status/last.json
CHECK_DB=edusync_restore_check
TABLES="schools users school_memberships rbac_roles rbac_assignments generated_documents audit_events finance_payments finance_charges enrollments students schema_migrations"

HEARTBEAT="${BACKUP_HEARTBEAT_URL:-}"
case "$HEARTBEAT" in https://*|"") ;; *) echo "BACKUP_HEARTBEAT_URL ignorée : https obligatoire" >&2; HEARTBEAT="" ;; esac
heartbeat() { # suffix [message] — never fails the backup, never prints the URL
  [ -n "$HEARTBEAT" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "${2:-}" "${HEARTBEAT%/}$1" 2>/dev/null || log "signal de vie externe non envoyé"
}
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
counts() { for t in $TABLES; do printf '%s=%s\n' "$t" "$(psql -d "$1" -tAXc "SELECT count(*) FROM $t" 2>/dev/null || echo NA)"; done; }
status() { # ok restore_verified offsite detail
  tmp="$STATUS.tmp"
  printf '{"finished_at":"%s","ok":%s,"restore_verified":%s,"offsite":%s,"detail":"%s","duration_seconds":%s,"restore_seconds":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$(( $(date +%s) - ${RUN_START:-$(date +%s)} ))" "${RESTORE_SECONDS:-null}" > "$tmp" && mv "$tmp" "$STATUS"
}

run_once() {
  heartbeat /start
  if run_backup; then heartbeat "" "sauvegarde vérifiée"; return 0; fi
  heartbeat /fail "$(sed -n 's/.*"detail":"\([^"]*\)".*/\1/p' "$STATUS" 2>/dev/null)"; return 1
}

run_backup() {
  RUN_START=$(date +%s); RESTORE_SECONDS=null
  ts=$(date -u +%Y%m%dT%H%M%SZ); dir="$OUT/$ts"; mkdir -p "$dir/objects"
  counts "$PGDATABASE" > "$dir/counts.before"
  if ! pg_dump -Fc -f "$dir/db.dump" "$PGDATABASE"; then status false false false "pg_dump en échec"; log "FAIL pg_dump"; return 1; fi
  counts "$PGDATABASE" > "$dir/counts.after"
  # A fresh installation has no document yet, hence no bucket: create the (private) bucket, idempotent, then copy.
  if ! rclone mkdir "src:$BUCKET" || ! rclone copy --quiet "src:$BUCKET" "$dir/objects"; then status false false false "copie des documents en échec"; log "FAIL objets"; return 1; fi
  (cd "$dir" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)

  verified=false
  restore_start=$(date +%s)
  dropdb --if-exists "$CHECK_DB" && createdb "$CHECK_DB" \
    && pg_restore --exit-on-error --no-owner --no-acl -d "$CHECK_DB" "$dir/db.dump" >/dev/null 2>"$dir/restore.err" \
    && counts "$CHECK_DB" > "$dir/counts.restored" && verified=true
  RESTORE_SECONDS=$(( $(date +%s) - restore_start ))
  if [ "$verified" = true ]; then
    for t in $TABLES; do
      b=$(grep "^$t=" "$dir/counts.before" | cut -d= -f2); a=$(grep "^$t=" "$dir/counts.after" | cut -d= -f2)
      r=$(grep "^$t=" "$dir/counts.restored" | cut -d= -f2)
      if [ "$r" = NA ] || [ "$b" = NA ] || [ "$r" -lt "$b" ] || [ "$r" -gt "$a" ]; then verified=false; log "Écart de comptage $t : avant=$b restauré=$r après=$a"; fi
    done
  fi
  dropdb --if-exists "$CHECK_DB"

  offsite=false
  if [ -n "$OFFSITE" ]; then
    if rclone copy --quiet "$dir" "$OFFSITE/$ts"; then offsite=true; else log "FAIL copie hors site"; fi
  fi
  find "$OUT" -mindepth 1 -maxdepth 1 -type d -mtime "+$KEEP_DAYS" -exec rm -rf {} +
  if [ "$verified" = true ]; then status true true "$offsite" "$ts"; log "PASS sauvegarde $ts (restauration vérifiée, hors site=$offsite)"
  else status false false "$offsite" "restauration non vérifiée ($ts)"; log "FAIL restauration $ts"; return 1; fi
}

if [ "${1:-}" = "once" ]; then run_once; exit $?; fi
while true; do run_once || true; sleep "$INTERVAL"; done
