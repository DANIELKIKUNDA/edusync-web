#!/bin/bash
# EduSync — one-shot ADMINISTRATIVE installation of the least-privilege staging deployment (CICD.md §3).
# Run by an administrator (edusyncadmin) from a REVIEWED checkout of the repository (tag or SHA approved for infra):
#   sudo bash deploy/staging/privileged/install_deploy_controller.sh
# Installs, root-owned: forced command (deploy-gate), controller, minimal sudoers rule, infrastructure compose and
# mounted configuration, protected directories; locks the `deploy` account's authorized_keys to the forced command.
# Idempotent; refuses an unexpected state. Embeds no secret. Changes no global SSH configuration. Never adds `deploy`
# to the docker group and never grants it any other sudo right.
set -euo pipefail
umask 022
PATH=/usr/sbin:/usr/bin:/sbin:/bin

DEPLOY_USER=deploy
LIBEXEC=/usr/local/libexec/edusync
ETC=/etc/edusync-deploy
COMPOSE_DIR=$ETC/compose
STATE=/var/lib/edusync-deploy
LOGS=/var/log/edusync-deploy
SUDOERS=/etc/sudoers.d/edusync-deploy
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

die() { echo "INSTALLATION REFUSÉE : $*" >&2; exit 1; }
say() { echo "• $*"; }

[[ $EUID -eq 0 ]] || die "à exécuter avec sudo par un administrateur"
[[ -f "$SRC/docker-compose.yml" && -f "$SRC/deploy/staging/privileged/deploy_controller.py" ]] || die "checkout du dépôt EduSync introuvable ($SRC)"
id "$DEPLOY_USER" >/dev/null 2>&1 || die "le compte $DEPLOY_USER n'existe pas"
if id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then die "$DEPLOY_USER appartient au groupe docker : retirez-le d'abord (gpasswd -d $DEPLOY_USER docker)"; fi
command -v /usr/bin/python3 >/dev/null || die "/usr/bin/python3 absent"
command -v /usr/bin/docker >/dev/null || die "/usr/bin/docker absent"
/usr/bin/docker compose version >/dev/null 2>&1 || die "plugin docker compose absent"
[[ -x /usr/bin/sudo ]] || die "/usr/bin/sudo absent"

HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
AUTH="$HOME_DIR/.ssh/authorized_keys"
[[ -f "$AUTH" ]] || die "$AUTH absent : déposez d'abord la clé publique GitHub Actions"
KEYS="$(grep -cvE '^\s*(#|$)' "$AUTH" || true)"
[[ "$KEYS" == "1" ]] || die "$AUTH doit contenir exactement une clé (trouvé : $KEYS)"
KEYLINE="$(grep -vE '^\s*(#|$)' "$AUTH")"
KEYPART="$(grep -oE '(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]+( .*)?$' <<<"$KEYLINE" || true)"
[[ -n "$KEYPART" ]] || die "clé publique illisible dans $AUTH"

say "Contrôleur, commande forcée (root:root, non modifiables par $DEPLOY_USER)"
install -d -o root -g root -m 0755 "$LIBEXEC"
install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy_controller.py" "$LIBEXEC/deploy-controller"
install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy-gate.sh" "$LIBEXEC/deploy-gate"

say "Infrastructure installée hors du commit applicatif ($COMPOSE_DIR)"
install -d -o root -g root -m 0700 "$ETC"
install -d -o root -g root -m 0755 "$COMPOSE_DIR" "$COMPOSE_DIR/deploy" "$COMPOSE_DIR/deploy/seaweedfs" "$COMPOSE_DIR/deploy/caddy"
install -o root -g root -m 0644 "$SRC/docker-compose.yml" "$COMPOSE_DIR/docker-compose.yml"
install -o root -g root -m 0644 "$SRC/deploy/staging/privileged/compose.digests.yml" "$COMPOSE_DIR/compose.digests.yml"
install -o root -g root -m 0644 "$SRC/deploy/seaweedfs/entrypoint.sh" "$COMPOSE_DIR/deploy/seaweedfs/entrypoint.sh"
install -o root -g root -m 0644 "$SRC/deploy/caddy/Caddyfile" "$COMPOSE_DIR/deploy/caddy/Caddyfile"
git -C "$SRC" rev-parse HEAD 2>/dev/null > "$ETC/INSTALLED_FROM" || echo "inconnu" > "$ETC/INSTALLED_FROM"
chmod 0644 "$ETC/INSTALLED_FROM"

if [[ ! -f "$ETC/staging.env" ]]; then
  install -o root -g root -m 0600 "$SRC/.env.example" "$ETC/staging.env"
  sed -i 's/^EDUSYNC_ENV=.*/EDUSYNC_ENV=staging/' "$ETC/staging.env"
  sed -i "s#^EDUSYNC_ENV_FILE=.*##" "$ETC/staging.env"
  say "staging.env créé (gabarit sans secret) : à compléter par l'administrateur avant le premier déploiement"
else
  chown root:root "$ETC/staging.env"; chmod 0600 "$ETC/staging.env"
  say "staging.env existant conservé (root:root 0600)"
fi
grep -qE '^EDUSYNC_ENV=staging$' "$ETC/staging.env" || die "staging.env doit contenir EDUSYNC_ENV=staging"

say "État et journaux du contrôle (root uniquement)"
install -d -o root -g root -m 0700 "$STATE"
install -d -o root -g root -m 0750 "$LOGS"

say "sudoers minimal : $DEPLOY_USER → $LIBEXEC/deploy-controller, sans argument, rien d'autre"
TMP_SUDO="$(mktemp)"
cat > "$TMP_SUDO" <<EOF
# EduSync staging — managed by install_deploy_controller.sh. Exactly one command, no argument allowed ("").
Defaults!$LIBEXEC/deploy-controller env_reset, !setenv, secure_path="/usr/sbin:/usr/bin:/sbin:/bin", !requiretty
$DEPLOY_USER ALL=(root) NOPASSWD: $LIBEXEC/deploy-controller ""
EOF
visudo -cf "$TMP_SUDO" >/dev/null || { rm -f "$TMP_SUDO"; die "règle sudoers invalide"; }
install -o root -g root -m 0440 "$TMP_SUDO" "$SUDOERS"
rm -f "$TMP_SUDO"
visudo -c >/dev/null || die "configuration sudo globale invalide après installation"

say "authorized_keys de $DEPLOY_USER verrouillé sur la commande forcée (root:root, non modifiable par $DEPLOY_USER)"
# Keep the administrator's existing options (e.g. from="IP"), drop a previous copy of ours, refuse a foreign command=.
OPTS="${KEYLINE%%"$KEYPART"*}"; OPTS="${OPTS%"${OPTS##*[![:space:]]}"}"
OPTS="${OPTS//command=\"$LIBEXEC\/deploy-gate\"/}"
if grep -q 'command=' <<<"$OPTS"; then die "authorized_keys contient déjà une autre commande forcée : état inattendu"; fi
OPTS="$(sed -E 's/(^|,)restrict(,|$)/\1\2/g; s/,,+/,/g; s/^,//; s/,$//' <<<"$OPTS")"
NEWLINE="restrict,command=\"$LIBEXEC/deploy-gate\"${OPTS:+,$OPTS} $KEYPART"
TMP_AUTH="$(mktemp)"
printf '%s\n' "$NEWLINE" > "$TMP_AUTH"
chown root:root "$HOME_DIR/.ssh"; chmod 0755 "$HOME_DIR/.ssh"
install -o root -g root -m 0644 "$TMP_AUTH" "$AUTH"
rm -f "$TMP_AUTH"

say "Vérifications"
SUDO_LIST="$(sudo -l -U "$DEPLOY_USER" 2>/dev/null || true)"
grep -q "$LIBEXEC/deploy-controller" <<<"$SUDO_LIST" || die "règle sudo non effective"
if grep -E '\(ALL|\(root' <<<"$SUDO_LIST" | grep -v "$LIBEXEC/deploy-controller" | grep -q .; then die "$DEPLOY_USER possède d'autres droits sudo : à retirer"; fi
for f in "$LIBEXEC/deploy-controller" "$LIBEXEC/deploy-gate" "$COMPOSE_DIR/docker-compose.yml" "$COMPOSE_DIR/compose.digests.yml" "$ETC/staging.env" "$SUDOERS" "$AUTH"; do
  printf '  %s %s\n' "$(stat -c '%U:%G %a' "$f")" "$f"
done
if id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then die "$DEPLOY_USER dans le groupe docker"; fi
echo "INSTALLATION OK — infrastructure installée depuis $(cat "$ETC/INSTALLED_FROM")."
echo "Étapes suivantes : compléter $ETC/staging.env (secrets générés), puis créer les secrets GitHub STAGING_SSH_*."
