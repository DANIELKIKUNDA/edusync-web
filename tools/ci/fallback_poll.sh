#!/usr/bin/env bash
# Poller GitHub independant des minutes GitHub Actions (CI uniquement).
# IMPORTANT : n'executer que sur un hote CI dedie / approuve, jamais en production.
set -Eeuo pipefail
umask 077
[[ $# -eq 1 ]] || { echo "Usage: bash tools/ci/fallback_poll.sh <checkout-edusync-web-ci>" >&2; exit 64; }
ROOT="$(realpath "$1")"
[[ -d "$ROOT/.git" && -f "$ROOT/tools/ci/fallback_local.sh" ]] || {
  echo "REFUS : checkout Git officiel avec outils de CI de secours requis." >&2; exit 65;
}
[[ "$EUID" -ne 0 ]] || { echo "REFUS : root non autorise" >&2; exit 77; }
command -v flock >/dev/null || { echo "flock indisponible" >&2; exit 69; }

origin="$(git -C "$ROOT" remote get-url origin)"
case "$origin" in
  "git@github.com:DANIELKIKUNDA/edusync-web.git" | \
  "https://github.com/DANIELKIKUNDA/edusync-web.git" | \
  "https://github.com/DANIELKIKUNDA/edusync-web")
    ;;
  *) echo "REFUS : origin inattendu. Refuser toute autre provenance : $origin" >&2; exit 65;;
esac

STATE="$HOME/edusync-ci-control"
mkdir -p "$STATE"
chmod 700 "$STATE"
exec 9>"$STATE/lock"
if ! flock -n 9; then
  echo "Autre CI deja en cours : sans nouvelle execution."
  exit 0
fi

# Le poller ne teste que origin/main, jamais les PR issues d'une contribution externe.
git -C "$ROOT" fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'
SHA="$(git -C "$ROOT" rev-parse refs/remotes/origin/main)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || exit 65
if [[ -s "$STATE/last_sha" ]] && [[ "$(cat "$STATE/last_sha")" == "$SHA" ]]; then
  echo "SHA deja traite : $SHA ; etat : $(cat "$STATE/last_result" 2>/dev/null || echo INDETERMINE)"
  exit 0
fi
# Publication OPTIONNELLE d'un statut EXTERNE au SHA GitHub.
# Ne pas confondre ce statut avec le workflow officiel CI et ses gates CD.
publish_status() {
  if [[ -z "${EDUSYNC_GITHUB_STATUS_TOKEN_FILE:-}" ]]; then
    echo "NOTE : statut GitHub externe non configure ; rapports uniquement sur l'hote CI." >&2
    return 0
  fi
  python3 "$ROOT/tools/ci/fallback_github_status.py" "$SHA" "$1" "$2"
}

# Trace l'intention avant de lancer. Une interruption = absence de PASS et pas
# de relance infinie tant qu'un humain n'a pas revise les journaux.
printf '%s\n' "$SHA" > "$STATE/last_sha"
printf 'IN_PROGRESS %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/last_result"
echo "CI independante pour SHA=$SHA"
if ! publish_status pending "CI de secours en cours; resultat partiel, hors deployment"; then
  echo "WARN : statut pending non publie ; test local toujours execute." >&2
fi
if bash "$ROOT/tools/ci/fallback_local.sh" "$SHA"; then
  printf 'PASS_LOCAL %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/last_result"
  if ! publish_status success "Tests CI locaux PASS; CD/staging non certifies"; then
    printf 'PASS_LOCAL_STATUS_UNPUBLISHED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/last_result"
    echo "Les tests locaux passent, mais GitHub n'a pas recu leur statut." >&2
    exit 74
  fi
  echo "PASS local du SHA $SHA. Aucune preuve de workflow CI Actions, aucun deploiement."
else
  code=$?
  printf 'FAIL rc=%d %s\n' "$code" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/last_result"
  publish_status failure "Tests CI locaux FAIL; consulter les journaux du runner" || true
  echo "FAIL rc=$code pour $SHA : consulter ~/edusync-ci-reports." >&2
  exit "$code"
fi
