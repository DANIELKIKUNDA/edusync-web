#!/bin/bash
# Real Linux checks of the privileged mechanism: installation, permissions, sudoers, shebang, sshd forced command,
# refusals, attempts by `deploy` to bypass the chain, concurrency lock, unsafe installation. No Docker workload.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
FAKE_TOKEN="ghs_$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"

setup_host
install_controller
sum1="$(sudo sha256sum "$CTL" "$GATE" /etc/sudoers.d/edusync-deploy /etc/ssh/edusync-deploy/authorized_keys /etc/ssh/sshd_config.d/edusync-deploy.conf)"
install_controller >/dev/null
sum2="$(sudo sha256sum "$CTL" "$GATE" /etc/sudoers.d/edusync-deploy /etc/ssh/edusync-deploy/authorized_keys /etc/ssh/sshd_config.d/edusync-deploy.conf)"
check "installateur idempotent (2e exécution identique)" test "$sum1" == "$sum2"

section "Propriétaires et modes (root-owned, non modifiables par deploy)"
for p in / /usr /usr/local /usr/local/libexec /usr/local/libexec/edusync "$CTL" "$GATE" /etc /etc/edusync-deploy /etc/edusync-deploy/compose \
         /etc/edusync-deploy/compose/docker-compose.yml /etc/edusync-deploy/compose/compose.staging.yml /etc/edusync-deploy/staging.env \
         /var/lib/edusync-deploy /var/log/edusync-deploy /etc/sudoers.d/edusync-deploy /etc/ssh /etc/ssh/edusync-deploy \
         /etc/ssh/edusync-deploy/authorized_keys /etc/ssh/sshd_config.d /etc/ssh/sshd_config.d/edusync-deploy.conf /home /home/deploy /home/deploy/.ssh; do
  check "root-owned et protégé : $p" root_owned_protected "$p"
done
check "contrôleur 0755" test "$(stat -c %a "$CTL")" == 755
check "staging.env 0600" test "$(sudo stat -c %a /etc/edusync-deploy/staging.env)" == 600
check "sudoers 0440" test "$(sudo stat -c %a /etc/sudoers.d/edusync-deploy)" == 440
check "clé : restrict + commande forcée" sudo grep -qE '^restrict,command="/usr/local/libexec/edusync/deploy-gate" ssh-ed25519 ' /etc/ssh/edusync-deploy/authorized_keys
check "deploy toujours hors du groupe docker" bash -c '! id -nG deploy | tr " " "\n" | grep -qx docker'

section "sudoers minimal"
LIST="$(sudo -l -U deploy)"
echo "$LIST" | sed 's/^/      /'
check "une seule commande sudo : le contrôleur sans argument" bash -c "grep -cE '^\s+\(root\) NOPASSWD:' <<<\"\$0\" | grep -qx 1 && grep -q '/usr/local/libexec/edusync/deploy-controller \"\"' <<<\"\$0\"" "$LIST"
denied "sudo /bin/sh" "sudo -n /bin/sh -c id"
denied "sudo /usr/bin/docker" "sudo -n /usr/bin/docker ps"
denied "sudo contrôleur + argument" "sudo -n $CTL --project other"
denied "sudo -E contrôleur" "PYTHONPATH=/tmp sudo -n -E $CTL </dev/null"
denied "docker sans sudo" "docker ps"
denied "socket Docker" "test -w /var/run/docker.sock"

section "Shebang réel du contrôleur installé"
check "première ligne #!/usr/bin/python3 -IS" test "$(head -1 "$CTL")" == "#!/usr/bin/python3 -IS"
rm -f "$WORK/fifo"; mkfifo "$WORK/fifo"
sudo "$CTL" <"$WORK/fifo" >/dev/null 2>&1 & RUNNING=$!
exec 7>"$WORK/fifo"
CPID=""; for _ in $(seq 1 20); do CPID="$(pgrep -u root -xf '/usr/bin/python3 -IS /usr/local/libexec/edusync/deploy-controller' || true)"; [[ -n "$CPID" ]] && break; sleep 0.5; done
check "exécution directe par le noyau : argv = /usr/bin/python3, « -IS » (un seul argument), contrôleur" test -n "$CPID"
[[ -n "$CPID" ]] && echo "      /proc/$CPID/cmdline : $(sudo cat "/proc/$CPID/cmdline" | tr '\0' ' ')"
exec 7>&-
set +e; wait "$RUNNING"; code=$?; set -e
check "contrôleur lancé par son shebang → requête vide refusée (64)" test "$code" == 64
mkdir -p "$WORK/evil"; printf 'open("%s/evil_marker", "w").close()\n' "$WORK" > "$WORK/evil/json.py"; rm -f "$WORK/evil_marker"
sudo env PYTHONPATH="$WORK/evil" "$CTL" </dev/null >/dev/null 2>&1 || true
check "mode isolé (-I) : PYTHONPATH piégé ignoré" test ! -e "$WORK/evil_marker"
sudo env PYTHONPATH="$WORK/evil" /usr/bin/python3 -c 'import json' 2>/dev/null || true
check "témoin : sans -I le module piégé serait chargé" test -e "$WORK/evil_marker"
rm -f "$WORK/evil_marker"
SITE="$(/usr/bin/python3 -c 'import site; print(site.getsitepackages()[0])')"
sudo mkdir -p "$SITE"
printf 'import os; open("%s/pth_marker", "w").close()\n' "$WORK" | sudo tee "$SITE/zz_edusync_probe.pth" >/dev/null; rm -f "$WORK/pth_marker"
sudo "$CTL" </dev/null >/dev/null 2>&1 || true
check "sans site (-S) : fichiers .pth ignorés" test ! -e "$WORK/pth_marker"
/usr/bin/python3 -c pass
check "témoin : sans -S le .pth serait exécuté" test -e "$WORK/pth_marker"
sudo rm -f "$SITE/zz_edusync_probe.pth" "$WORK/pth_marker"
printf '#!/usr/bin/python3 -I -S\nprint("ok")\n' > "$WORK/old_shebang"; chmod +x "$WORK/old_shebang"
check "témoin : l'ancien shebang « -I -S » ne démarre pas sous Linux" bash -c "! '$WORK/old_shebang' >/dev/null 2>&1"
expect_code "contrôleur appelé avec un argument (root)" 64 sudo "$CTL" extra

section "sshd effectif pour deploy (drop-in Match User deploy uniquement)"
EFF="$(sudo sshd -T -C user=deploy,host=x,addr=203.0.113.9)"
for e in "authorizedkeysfile /etc/ssh/edusync-deploy/authorized_keys" "forcecommand /usr/local/libexec/edusync/deploy-gate" "permittty no" \
         "allowtcpforwarding no" "permittunnel no" "x11forwarding no" "allowagentforwarding no" "permituserrc no" "authenticationmethods publickey"; do
  check "sshd(deploy) : $e" grep -qix "$e" <<<"$EFF"
done
check "sshd(root) : aucune commande forcée" bash -c "! sudo sshd -T -C user=root,host=x,addr=203.0.113.9 | grep -qi '^forcecommand /'"

section "Commande forcée via le vrai sshd"
expect_code "connexion sans commande" 64 ssh_deploy </dev/null
expect_code "id" 64 ssh_deploy id </dev/null
expect_code "bash" 64 ssh_deploy bash -c id </dev/null
expect_code "SHA court" 64 deploy_sha "${SHA:0:7}" "$FAKE_TOKEN"
expect_code "SHA majuscules" 64 deploy_sha "${SHA^^}" "$FAKE_TOKEN"
expect_code "argument supplémentaire" 64 deploy_sha "$SHA --project other" "$FAKE_TOKEN"
expect_code "injection ;" 64 ssh_deploy "deploy $SHA;id" </dev/null
expect_code "injection \$( )" 64 ssh_deploy 'deploy $(id)' </dev/null
expect_code "injection |" 64 ssh_deploy "deploy $SHA | sh" </dev/null
expect_code "jeton absent" 64 ssh_deploy "deploy $SHA" </dev/null
echo probe > "$WORK/probe.txt"
set +e; scp -q $(ssh_opts deploy_key | sed 's/-T//') "$WORK/probe.txt" deploy@127.0.0.1:/tmp/edusync_scp_probe >/dev/null 2>&1; set -e
check "scp refusé (aucun fichier déposé)" test ! -e /tmp/edusync_scp_probe
set +e; echo "put $WORK/probe.txt /tmp/edusync_sftp_probe" | sftp -q -b - -i "$WORK/deploy_key" -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$WORK/known_hosts" -o BatchMode=yes deploy@127.0.0.1 >/dev/null 2>&1; set -e
check "sftp refusé (aucun fichier déposé)" test ! -e /tmp/edusync_sftp_probe
expect_code "redirection distante -R refusée" 255 timeout 20 ssh $(ssh_opts deploy_key) -N -o ExitOnForwardFailure=yes -R 127.0.0.1:2298:127.0.0.1:22 deploy@127.0.0.1
ssh $(ssh_opts deploy_key) -N -L 127.0.0.1:2299:127.0.0.1:22 deploy@127.0.0.1 >/dev/null 2>&1 & FWD=$!
sleep 3
banner="$(timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/2299 && head -c 4 <&3' 2>/dev/null || true)"
kill "$FWD" 2>/dev/null || true
check "redirection locale -L refusée (aucune bannière relayée)" test "$banner" != "SSH-"
expect_code "chemin positif : deploy <SHA> atteint le contrôleur root (jeton factice → vérification refusée)" 65 deploy_sha "$SHA" "$FAKE_TOKEN"
check "journal du contrôleur écrit par root" bash -c "sudo grep -q 'VERDICT=VERIFICATION_REFUSED' /var/log/edusync-deploy/deploy.log && test \"\$(sudo stat -c %U /var/log/edusync-deploy/deploy.log)\" == root"
check "aucun jeton dans le journal" bash -c "! sudo grep -q '$FAKE_TOKEN' /var/log/edusync-deploy/deploy.log"

section "Tentatives de contournement par deploy"
denied "renommer ~/.ssh" "mv /home/deploy/.ssh /home/deploy/.ssh.old"
denied "remplacer ~/.ssh" "rm -rf /home/deploy/.ssh && mkdir /home/deploy/.ssh"
denied "remplacer authorized_keys" "echo x > /home/deploy/.ssh/authorized_keys"
denied "créer authorized_keys2" "touch /home/deploy/.ssh/authorized_keys2"
denied "lien symbolique vers une autre clé" "ln -sf /tmp/k /home/deploy/.ssh/authorized_keys2"
denied "lien symbolique du répertoire .ssh" "ln -sfn /tmp /home/deploy/.ssh2 && mv -T /home/deploy/.ssh2 /home/deploy/.ssh"
denied "écrire dans le répertoire personnel" "touch /home/deploy/.bashrc"
denied "modifier la clé autorisée root" "echo x >> /etc/ssh/edusync-deploy/authorized_keys"
denied "remplacer le répertoire de clés" "mv /etc/ssh/edusync-deploy /tmp/x"
denied "modifier le drop-in sshd" "echo x >> /etc/ssh/sshd_config.d/edusync-deploy.conf"
denied "modifier le contrôleur" "echo x >> $CTL"
denied "modifier la commande forcée" "echo x >> $GATE"
denied "modifier le compose installé" "echo x >> /etc/edusync-deploy/compose/docker-compose.yml"
denied "lire staging.env" "cat /etc/edusync-deploy/staging.env"
denied "écrire l'état" "touch /var/lib/edusync-deploy/current.json"
denied "modifier sudoers" "echo x >> /etc/sudoers.d/edusync-deploy"
# Even if a key were planted in the home directory (simulated by root), sshd ignores it: only the root-owned file counts.
sudo bash -c "cat '$WORK/rogue_key.pub' > /home/deploy/.ssh/authorized_keys; cp /home/deploy/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys2"
expect_code "clé plantée dans ~/.ssh ignorée par sshd" 255 ssh_deploy --key rogue_key id </dev/null
sudo bash -c "printf '# ignoré\n' > /home/deploy/.ssh/authorized_keys; rm -f /home/deploy/.ssh/authorized_keys2"
sudo cp /etc/ssh/edusync-deploy/authorized_keys "$WORK/ak.bak"
sudo bash -c "sed 's/^restrict,command=\"[^\"]*\" //' '$WORK/ak.bak' > /etc/ssh/edusync-deploy/authorized_keys"
expect_code "même sans options dans la clé, ForceCommand du drop-in s'applique" 64 ssh_deploy id </dev/null
sudo install -o root -g root -m 0644 "$WORK/ak.bak" /etc/ssh/edusync-deploy/authorized_keys

section "Verrou : deux déploiements jamais simultanés"
sudo flock -n -o /run/edusync-deploy.lock -c 'sleep 10' & HOLD=$!
sleep 2
expect_code "second déploiement pendant un déploiement" 75 deploy_sha "$SHA" "$FAKE_TOKEN"
wait "$HOLD" 2>/dev/null || true
expect_code "verrou libéré : la demande suivante est de nouveau traitée" 65 deploy_sha "$SHA" "$FAKE_TOKEN"

section "Installation altérée ou environnement non staging"
sudo chmod g+w /etc/edusync-deploy/compose/docker-compose.yml
expect_code "compose modifiable par le groupe" 78 deploy_sha "$SHA" "$FAKE_TOKEN"
sudo chmod 0644 /etc/edusync-deploy/compose/docker-compose.yml
sudo chown 1001 "$CTL" 2>/dev/null || sudo chown nobody "$CTL"
expect_code "contrôleur non possédé par root" 78 deploy_sha "$SHA" "$FAKE_TOKEN"
sudo chown root:root "$CTL"
sudo sed -i 's/^EDUSYNC_ENV=staging$/EDUSYNC_ENV=production/' /etc/edusync-deploy/staging.env
expect_code "EDUSYNC_ENV=production" 78 deploy_sha "$SHA" "$FAKE_TOKEN"
sudo sed -i 's/^EDUSYNC_ENV=production$/EDUSYNC_ENV=staging/' /etc/edusync-deploy/staging.env

finish
