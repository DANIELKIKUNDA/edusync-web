#!/bin/bash
# EduSync — Linux certification harness of the privileged staging deployment (CICD.md §9). DISPOSABLE runners only:
# it creates the `deploy` account, installs the controller, starts sshd and Docker workloads, and changes /etc.
# Never run it on a real server.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WORK="${RUNNER_TEMP:-/tmp}/edusync-cd"
mkdir -p "$WORK"
FAILS=0
CTL=/usr/local/libexec/edusync/deploy-controller
GATE=/usr/local/libexec/edusync/deploy-gate

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILS=$((FAILS + 1)); }
section() { echo; echo "=== $*"; }
check() { local name="$1"; shift; if "$@"; then pass "$name"; else fail "$name"; fi; }

# expect_code NAME WANT CMD... : runs CMD, compares its exit code
expect_code() {
  local name="$1" want="$2"; shift 2
  set +e; "$@" >"$WORK/last.out" 2>&1; local got=$?; set -e
  if [[ "$got" == "$want" ]]; then pass "$name (code $got)"; else fail "$name : attendu $want, obtenu $got"; tail -25 "$WORK/last.out" | sed 's/^/      /'; fi
}

# denied NAME SHELL-CMD : the command run as `deploy` must fail
denied() {
  local name="$1"; shift
  if sudo -u deploy -- /bin/bash -c "$*" >"$WORK/denied.out" 2>&1; then fail "deploy a pu : $name"; else pass "refusé à deploy : $name"; fi
}

root_owned_protected() { # path
  local u m; u="$(sudo stat -c '%u' "$1")"; m="$(sudo stat -c '%a' "$1")"
  [[ "$u" == 0 && $(( 8#$m & 8#022 )) -eq 0 ]]
}

setup_host() {
  section "Hôte jetable : sshd, compte deploy (sans mot de passe, hors groupe docker), clé dédiée"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server >/dev/null
  # GitHub runner image: its own /etc/sudoers.d/runner is not 0440, which makes `visudo -c` fail (the installer
  # refuses an invalid sudo configuration, by design). Fix it on this disposable runner only.
  sudo chown root:root /etc/sudoers /etc/sudoers.d/* 2>/dev/null || true
  sudo chmod 0440 /etc/sudoers /etc/sudoers.d/* 2>/dev/null || true
  sudo visudo -c 2>&1 | sed 's/^/      visudo : /' || true
  sudo systemctl start ssh.socket 2>/dev/null || true
  sudo systemctl start ssh.service 2>/dev/null || true
  if ! id deploy >/dev/null 2>&1; then sudo useradd --create-home --shell /bin/bash deploy; fi
  sudo passwd -l deploy >/dev/null
  [[ -f "$WORK/deploy_key" ]] || ssh-keygen -q -t ed25519 -N '' -C github-actions-edusync-staging -f "$WORK/deploy_key"
  [[ -f "$WORK/rogue_key" ]] || ssh-keygen -q -t ed25519 -N '' -C rogue -f "$WORK/rogue_key"
  sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
  sudo install -o deploy -g deploy -m 600 "$WORK/deploy_key.pub" /home/deploy/.ssh/authorized_keys
  for _ in $(seq 1 20); do ssh-keyscan -t ed25519 127.0.0.1 >"$WORK/known_hosts" 2>/dev/null && [[ -s "$WORK/known_hosts" ]] && break; sleep 1; done
  [[ -s "$WORK/known_hosts" ]] || { echo "sshd injoignable"; exit 1; }
  check "deploy hors du groupe docker" bash -c '! id -nG deploy | tr " " "\n" | grep -qx docker'
}

install_controller() {
  section "Installation administrative réelle (install_deploy_controller.sh)"
  sudo bash "$ROOT/deploy/staging/privileged/install_deploy_controller.sh" | sed 's/^/      /'
}

ssh_opts() { echo -i "$WORK/$1" -T -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$WORK/known_hosts" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10; }
# ssh_deploy [key] -- remote args... (stdin forwarded)
ssh_deploy() { local key=deploy_key; if [[ "${1:-}" == --key ]]; then key="$2"; shift 2; fi; ssh $(ssh_opts "$key") -o ClearAllForwardings=yes deploy@127.0.0.1 "$@"; }
deploy_sha() { printf '%s\n' "$2" | ssh_deploy "deploy $1"; }    # deploy_sha SHA TOKEN

finish() {
  echo
  if [[ "$FAILS" -eq 0 ]]; then echo "RÉSULTAT : PASS"; else echo "RÉSULTAT : FAIL ($FAILS échec(s))"; exit 1; fi
}
