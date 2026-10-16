#!/bin/sh
# Pre-staging S3 — self-hosted S3-compatible document storage (SeaweedFS, Apache-2.0), private bucket.
# The S3 identity is generated from the environment at start-up (never committed); the API is its only client.
set -eu
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY required}"
umask 077
cat > /tmp/s3.json <<EOF
{"identities":[{"name":"edusync-app","credentials":[{"accessKey":"$S3_ACCESS_KEY","secretKey":"$S3_SECRET_KEY"}],
  "actions":["Read","Write","List","Tagging","Admin"]}]}
EOF
exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json
