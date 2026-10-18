#!/bin/bash
# EduSync — OpenSSH forced command of the `deploy` account (CICD.md §2). Installed root-owned as
# /usr/local/libexec/edusync/deploy-gate and referenced from authorized_keys:
#   restrict,command="/usr/local/libexec/edusync/deploy-gate" ssh-ed25519 AAAA... github-actions-edusync-staging
# The requested command ($SSH_ORIGINAL_COMMAND) is only PARSED, never executed. The only accepted form is
#   deploy <40-hex-lowercase-SHA>
# The ephemeral registry / API token (GITHUB_TOKEN: opaque, possibly long, base64url / JWT characters) arrives as one
# bounded line on stdin; it is never interpreted by the shell. Both are handed to the root controller
# through stdin; sudo is called with an absolute path and no argument (sudoers allows exactly that, nothing else).
set -euo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly SUDO=/usr/bin/sudo
readonly CONTROLLER=/usr/local/libexec/edusync/deploy-controller

request="${SSH_ORIGINAL_COMMAND-}"
if [[ ! "$request" =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
  echo "Refusé : seule la commande « deploy <SHA de 40 caractères> » est autorisée." >&2
  exit 64
fi
sha="${BASH_REMATCH[1]}"

token=""
IFS= read -r -t 15 -n 4200 token || true
# Length checked apart: POSIX regex repetition bounds stop at RE_DUP_MAX (255).
if (( ${#token} < 20 || ${#token} > 4096 )) || [[ ! "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]]; then
  echo "Refusé : jeton éphémère absent ou invalide sur l'entrée standard." >&2
  exit 64
fi

exec "$SUDO" -n "$CONTROLLER" < <(printf '%s\n%s\n' "$sha" "$token")
