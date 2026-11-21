# Pre-staging S9 — backup job: PostgreSQL 16 client tools (same major as the server) + rclone for documents/off-site.
FROM postgres:16-alpine
# curl: external heartbeat of the backup (BACKUP_HEARTBEAT_URL, 2026-11-14).
RUN apk add --no-cache rclone curl
COPY backup.sh /usr/local/bin/edusync-backup
COPY backup-health.sh /usr/local/bin/edusync-backup-health
ENTRYPOINT ["/bin/sh", "/usr/local/bin/edusync-backup"]
