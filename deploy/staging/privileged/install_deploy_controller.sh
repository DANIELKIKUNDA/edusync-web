#!/bin/bash
# EduSync — one-shot ADMINISTRATIVE installation of the least-privilege staging deployment (CICD.md §3).
# Run by an administrator (edusyncadmin) from a REVIEWED checkout of the repository (tag or SHA approved for infra):
#   sudo bash deploy/staging/privileged/install_deploy_controller.sh
# Installs, root-owned: forced command (deploy-gate), controller, minimal sudoers rule, infrastructure compose and
# mounted configuration, protected directories. SSH: the key of the `deploy` account moves to a root-owned file outside
# the home directory (/etc/ssh/edusync-deploy/authorized_keys), selected by a drop-in that applies to `Match User deploy`
# ONLY (AuthorizedKeysFile + ForceCommand + no forwarding / tty / user rc). The effective configuration of every other
# account is compared before / after and must be identical, otherwise the drop-in is removed. The home directory
# becomes root-owned, so `deploy` can neither rename nor replace .ssh nor plant another key.
# Idempotent; refuses an unexpected state. Embeds no secret. Never adds `deploy` to the docker group and never grants
# it any other sudo right.
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
SSH_KEYS_DIR=/etc/ssh/edusync-deploy
SSH_KEYS=$SSH_KEYS_DIR/authorized_keys
SSH_DROPIN=/etc/ssh/sshd_config.d/edusync-deploy.conf
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

die() { echo "INSTALLATION REFUSÉE : $*" >&2; exit 1; }
say() { echo "• $*"; }

[[ $EUID -eq 0 ]] || die "à exécuter avec sudo par un administrateur"
[[ -f "$SRC/docker-compose.yml" && -f "$SRC/deploy/staging/privileged/deploy_controller.py" ]] || die "checkout du dépôt EduSync introuvable ($SRC)"
id "$DEPLOY_USER" >/dev/null 2>&1 || die "le compte $DEPLOY_USER n'existe pas"
if id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then die "$DEPLOY_USER appartient au groupe docker : retirez-le d'abord (gpasswd -d $DEPLOY_USER docker)"; fi
[[ -x /usr/bin/python3 ]] || die "/usr/bin/python3 absent"
/usr/bin/python3 -IS -c 'import sys; assert sys.flags.isolated == 1 and sys.flags.no_site == 1' || die "python3 -IS indisponible"
[[ -x /usr/bin/docker ]] || die "/usr/bin/docker absent"
COMPOSE_VERSION="$(/usr/bin/docker compose version --short 2>/dev/null || true)"
[[ -n "$COMPOSE_VERSION" ]] || die "plugin docker compose absent"
printf '%s\n%s\n' "2.24.4" "${COMPOSE_VERSION#v}" | sort -V -C || die "docker compose >= 2.24.4 requis (!reset / !override) : $COMPOSE_VERSION"
[[ -x /usr/bin/sudo ]] || die "/usr/bin/sudo absent"
SSHD="$(command -v sshd || echo /usr/sbin/sshd)"
[[ -x "$SSHD" ]] || die "sshd absent"
[[ -d /etc/ssh/sshd_config.d ]] || die "/etc/ssh/sshd_config.d absent"

# ---------------------------------------------------------------- the single GitHub Actions key
HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
[[ "$HOME_DIR" == /* && "$HOME_DIR" != "/" ]] || die "répertoire personnel de $DEPLOY_USER invalide"
DEPLOY_SHELL="$(getent passwd "$DEPLOY_USER" | cut -d: -f7)"
case "$DEPLOY_SHELL" in /bin/bash|/usr/bin/bash|/bin/sh|/usr/bin/sh) ;; *) die "shell de $DEPLOY_USER ($DEPLOY_SHELL) : sshd exécute la commande forcée par ce shell, /bin/bash attendu";; esac
HOME_AUTH="$HOME_DIR/.ssh/authorized_keys"
if [[ -s "$SSH_KEYS" ]]; then KEYSRC="$SSH_KEYS"; elif [[ -f "$HOME_AUTH" && ! -L "$HOME_AUTH" ]]; then KEYSRC="$HOME_AUTH"; else die "aucune clé : déposez d'abord la clé publique GitHub Actions dans $HOME_AUTH"; fi
KEYS="$(grep -cvE '^\s*(#|$)' "$KEYSRC" || true)"
[[ "$KEYS" == "1" ]] || die "$KEYSRC doit contenir exactement une clé (trouvé : $KEYS)"
KEYLINE="$(grep -vE '^\s*(#|$)' "$KEYSRC")"
KEYPART="$(grep -oE '(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]+( .*)?$' <<<"$KEYLINE" || true)"
[[ -n "$KEYPART" ]] || die "clé publique illisible dans $KEYSRC"
# Keep the administrator's existing options (e.g. from="IP"), drop a previous copy of ours, refuse a foreign command=.
OPTS="${KEYLINE%%"$KEYPART"*}"; OPTS="${OPTS%"${OPTS##*[![:space:]]}"}"
OPTS="${OPTS//command=\"$LIBEXEC\/deploy-gate\"/}"
if grep -q 'command=' <<<"$OPTS"; then die "la clé porte déjà une autre commande forcée : état inattendu"; fi
OPTS="$(sed -E 's/(^|,)restrict(,|$)/\1\2/g; s/,,+/,/g; s/^,//; s/,$//' <<<"$OPTS")"
NEWLINE="restrict,command=\"$LIBEXEC/deploy-gate\"${OPTS:+,$OPTS} $KEYPART"

say "Contrôleur, commande forcée (root:root, non modifiables par $DEPLOY_USER)"
install -d -o root -g root -m 0755 /usr/local/libexec "$LIBEXEC"
install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy_controller.py" "$LIBEXEC/deploy-controller"
install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy-gate.sh" "$LIBEXEC/deploy-gate"
head -1 "$LIBEXEC/deploy-controller" | grep -qx '#!/usr/bin/python3 -IS' || die "shebang du contrôleur inattendu"

say "Infrastructure installée hors du commit applicatif ($COMPOSE_DIR)"
install -d -o root -g root -m 0700 "$ETC"
install -d -o root -g root -m 0755 "$COMPOSE_DIR" "$COMPOSE_DIR/deploy" "$COMPOSE_DIR/deploy/seaweedfs" "$COMPOSE_DIR/deploy/caddy"
install -o root -g root -m 0644 "$SRC/docker-compose.yml" "$COMPOSE_DIR/docker-compose.yml"
install -o root -g root -m 0644 "$SRC/deploy/staging/privileged/compose.staging.yml" "$COMPOSE_DIR/compose.staging.yml"
rm -f "$COMPOSE_DIR/compose.digests.yml"
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

say "Clé de $DEPLOY_USER hors du répertoire personnel : $SSH_KEYS (root:root 0644, forced command obligatoire)"
for d in /etc /etc/ssh; do
  [[ "$(stat -c '%u' "$d")" == "0" && $(( 8#$(stat -c '%a' "$d") & 8#022 )) -eq 0 ]] || die "$d doit appartenir à root et ne pas être modifiable par d'autres"
done
install -d -o root -g root -m 0755 "$SSH_KEYS_DIR"
TMP_AUTH="$(mktemp)"
printf '%s\n' "$NEWLINE" > "$TMP_AUTH"
install -o root -g root -m 0644 "$TMP_AUTH" "$SSH_KEYS"
rm -f "$TMP_AUTH"

# Effective sshd configuration of other accounts, before the drop-in (must stay identical).
probe() { "$SSHD" -T -C "user=$1,host=edusync-probe,addr=203.0.113.9" 2>/dev/null | grep -v '^hostkey ' | sort; }
OTHERS=(root nobody)
ADMIN_USER="${SUDO_USER:-}"; [[ -n "$ADMIN_USER" && "$ADMIN_USER" != "$DEPLOY_USER" && "$ADMIN_USER" != root ]] && OTHERS+=("$ADMIN_USER")
declare -A BEFORE=()
if [[ -f "$SSH_DROPIN" ]]; then mv "$SSH_DROPIN" "$SSH_DROPIN.previous"; fi
for u in "${OTHERS[@]}"; do BEFORE[$u]="$(probe "$u")"; done
TMP_DROP="$(mktemp)"
cat > "$TMP_DROP" <<EOF
# EduSync staging — managed by install_deploy_controller.sh. Applies to the account $DEPLOY_USER ONLY.
Match User $DEPLOY_USER
	AuthorizedKeysFile $SSH_KEYS
	AuthorizedPrincipalsFile none
	ForceCommand $LIBEXEC/deploy-gate
	AuthenticationMethods publickey
	PasswordAuthentication no
	KbdInteractiveAuthentication no
	PermitTTY no
	PermitUserRC no
	DisableForwarding yes
	AllowTcpForwarding no
	AllowAgentForwarding no
	AllowStreamLocalForwarding no
	X11Forwarding no
	PermitTunnel no
	PermitListen none
	PermitOpen none
EOF
install -o root -g root -m 0644 "$TMP_DROP" "$SSH_DROPIN"
rm -f "$TMP_DROP"
rollback_dropin() { rm -f "$SSH_DROPIN"; [[ -f "$SSH_DROPIN.previous" ]] && mv "$SSH_DROPIN.previous" "$SSH_DROPIN"; die "$1"; }
"$SSHD" -t || rollback_dropin "configuration sshd invalide avec le drop-in"
EFFECTIVE="$("$SSHD" -T -C "user=$DEPLOY_USER,host=edusync-probe,addr=203.0.113.9")"
for expect in "authorizedkeysfile $SSH_KEYS" "forcecommand $LIBEXEC/deploy-gate" "permittty no" "allowtcpforwarding no" \
              "x11forwarding no" "permittunnel no" "allowagentforwarding no" "permituserrc no" "passwordauthentication no" "authenticationmethods publickey"; do
  grep -qix "$expect" <<<"$EFFECTIVE" || rollback_dropin "sshd n'applique pas « $expect » à $DEPLOY_USER (Include de sshd_config.d absent ?)"
done
for u in "${OTHERS[@]}"; do
  [[ "$(probe "$u")" == "${BEFORE[$u]}" ]] || rollback_dropin "le drop-in modifierait la configuration SSH de $u : annulé"
done
rm -f "$SSH_DROPIN.previous"

say "Répertoire personnel de $DEPLOY_USER root-owned (aucune substitution de .ssh possible)"
chown root:root "$HOME_DIR"; chmod 0755 "$HOME_DIR"
install -d -o root -g root -m 0755 "$HOME_DIR/.ssh"
for f in "$HOME_DIR"/.ssh/authorized_keys "$HOME_DIR"/.ssh/authorized_keys2; do
  [[ -e "$f" || -L "$f" ]] && rm -f "$f"
done
printf '# Clé déplacée vers %s (root-owned) par install_deploy_controller.sh : ce fichier est ignoré.\n' "$SSH_KEYS" > "$HOME_DIR/.ssh/authorized_keys"
chown root:root "$HOME_DIR/.ssh/authorized_keys"; chmod 0644 "$HOME_DIR/.ssh/authorized_keys"
for f in .bashrc .profile .bash_profile .bash_login .bash_logout .ssh/rc .ssh/environment; do
  [[ -e "$HOME_DIR/$f" ]] && chown root:root "$HOME_DIR/$f" && chmod go-w "$HOME_DIR/$f"
done
if command -v systemctl >/dev/null && systemctl list-unit-files ssh.service >/dev/null 2>&1; then
  systemctl try-reload-or-restart ssh.service 2>/dev/null || systemctl try-reload-or-restart sshd.service 2>/dev/null || true
elif [[ -f /run/sshd.pid ]]; then
  kill -HUP "$(cat /run/sshd.pid)" || true
fi

say "Vérifications"
SUDO_LIST="$(sudo -l -U "$DEPLOY_USER" 2>/dev/null || true)"
grep -q "$LIBEXEC/deploy-controller" <<<"$SUDO_LIST" || die "règle sudo non effective"
if grep -E '\(ALL|\(root' <<<"$SUDO_LIST" | grep -v "$LIBEXEC/deploy-controller" | grep -q .; then die "$DEPLOY_USER possède d'autres droits sudo : à retirer"; fi
for f in / /usr /usr/local /usr/local/libexec "$LIBEXEC" "$LIBEXEC/deploy-controller" "$LIBEXEC/deploy-gate" "$ETC" "$COMPOSE_DIR" \
         "$COMPOSE_DIR/docker-compose.yml" "$COMPOSE_DIR/compose.staging.yml" "$ETC/staging.env" "$STATE" "$LOGS" /etc/sudoers.d "$SUDOERS" \
         /etc /etc/ssh "$SSH_KEYS_DIR" "$SSH_KEYS" /etc/ssh/sshd_config.d "$SSH_DROPIN" "$HOME_DIR" "$HOME_DIR/.ssh"; do
  [[ "$(stat -c '%u' "$f")" == "0" && $(( 8#$(stat -c '%a' "$f") & 8#022 )) -eq 0 ]] || die "$f n'est pas root-owned et protégé"
  printf '  %s %s\n' "$(stat -c '%U:%G %a' "$f")" "$f"
done
if id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then die "$DEPLOY_USER dans le groupe docker"; fi
echo "INSTALLATION OK — infrastructure installée depuis $(cat "$ETC/INSTALLED_FROM")."
echo "Étapes suivantes : compléter $ETC/staging.env (secrets générés), puis créer les secrets GitHub STAGING_SSH_*."
