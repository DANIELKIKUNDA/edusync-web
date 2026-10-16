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
#   6. /backup-status/last.json {"finished_at","ok","restore_verified","offsite"} for the platform health screen.
# The production database is only read. No secret is written to the logs or to the status file.
set -u
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

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
counts() { for t in $TABLES; do printf '%s=%s\n' "$t" "$(psql -d "$1" -tAXc "SELECT count(*) FROM $t" 2>/dev/null || echo NA)"; done; }
status() { # ok restore_verified offsite detail
  tmp="$STATUS.tmp"
  printf '{"finished_at":"%s","ok":%s,"restore_verified":%s,"offsite":%s,"detail":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" > "$tmp" && mv "$tmp" "$STATUS"
}

run_once() {
  ts=$(date -u +%Y%m%dT%H%M%SZ); dir="$OUT/$ts"; mkdir -p "$dir/objects"
  counts "$PGDATABASE" > "$dir/counts.before"
  if ! pg_dump -Fc -f "$dir/db.dump" "$PGDATABASE"; then status false false false "pg_dump en échec"; log "FAIL pg_dump"; return 1; fi
  counts "$PGDATABASE" > "$dir/counts.after"
  if ! rclone copy --quiet "src:$BUCKET" "$dir/objects"; then status false false false "copie des documents en échec"; log "FAIL objets"; return 1; fi
  (cd "$dir" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)

  verified=false
  dropdb --if-exists "$CHECK_DB" && createdb "$CHECK_DB" \
    && pg_restore --exit-on-error --no-owner --no-acl -d "$CHECK_DB" "$dir/db.dump" >/dev/null 2>"$dir/restore.err" \
    && counts "$CHECK_DB" > "$dir/counts.restored" && verified=true
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
