#!/bin/sh
# Docker healthcheck of the backup service (owner, 2026-11-21: Coolify showed « Running (no healthcheck) »).
# Healthy = the last backup is verified (ok:true in /backup-status/last.json) and less than 30 hours old.
# A backup runs as soon as the service starts; the compose start_period covers it. Reads one file, prints no secret.
STATUS=/backup-status/last.json
[ -s "$STATUS" ] || { echo "aucune sauvegarde terminée" >&2; exit 1; }
grep -q '"ok":true' "$STATUS" || { echo "dernière sauvegarde en échec" >&2; exit 1; }
recent=$(find "$STATUS" -mmin -1800)
[ -n "$recent" ] || { echo "dernière sauvegarde de plus de 30 h" >&2; exit 1; }
exit 0
