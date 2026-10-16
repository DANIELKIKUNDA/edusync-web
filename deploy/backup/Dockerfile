# Pre-staging S9 — backup job: PostgreSQL 16 client tools (same major as the server) + rclone for documents/off-site.
FROM postgres:16-alpine
RUN apk add --no-cache rclone
COPY backup.sh /usr/local/bin/edusync-backup
ENTRYPOINT ["/bin/sh", "/usr/local/bin/edusync-backup"]
