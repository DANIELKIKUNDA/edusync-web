#!/usr/bin/env bash
# Poller GitHub independant des minutes GitHub Actions (CI uniquement).
# IMPORTANT : n'executer que sur un hote CI dedie / approuve, jamais en production.
set -Eeuo pipefail
umask 077
[[ $# -ge 1 && $# -le 2 ]] || { echo "Usage: bash tools/ci/fallback_poll.sh <checkout-edusync-web-ci> [main|chatgpt/prefet-directeur-certification]" >&2; exit 64; }
BRANCH="${2:-main}"
case "$BRANCH" in
  main | chatgpt/prefet-directeur-certification) ;;
  *) echo "REFUS : branche non autorisee pour ce runner" >&2; exit 65 ;;
esac
BRANCH_KEY="${BRANCH//\//_}"
ROOT="$(realpath "$1")"
[[ -d "$ROOT/.git" && -f "$ROOT/tools/ci/fallback_local.sh" ]] || {
  echo "REFUS : checkout Git officiel avec outils de CI de secours requis." >&2; exit 65;
}
[[ "$EUID" -ne 0 ]] || { echo "REFUS : root non autorise" >&2; exit 77; }
command -v flock >/dev/null || { echo "flock indisponible" >&2; exit 69; }
# Fail-closed AVANT fetch et tout declenchement CI.
bash "$ROOT/tools/ci/fallback_assert_ci_host.sh"

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
# Un verrou global serialize les jobs manuels Prefet et le timer main.
exec 9>"$STATE/lock"
if ! flock -n 9; then
  echo "Autre CI deja en cours : sans nouvelle execution."
  exit 0
fi

# Une branche maintenue dans le depot du proprietaire, pas une PR de fork.
# Chaque branche conserve son propre etat pour ne pas masquer la CI de main.
git -C "$ROOT" fetch --no-tags origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
SHA="$(git -C "$ROOT" rev-parse "refs/remotes/origin/$BRANCH")"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || exit 65
LAST_SHA="$STATE/${BRANCH_KEY}.last_sha"
LAST_RESULT="$STATE/${BRANCH_KEY}.last_result"
if [[ -s "$LAST_SHA" ]] && [[ "$(cat "$LAST_SHA")" == "$SHA" ]]; then
  echo "SHA deja traite pour $BRANCH : $SHA ; etat : $(cat "$LAST_RESULT" 2>/dev/null || echo INDETERMINE)"
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
printf '%s\n' "$SHA" > "$LAST_SHA"
printf 'IN_PROGRESS %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LAST_RESULT"
echo "CI independante branche=$BRANCH SHA=$SHA"
if ! publish_status pending "CI de secours en cours; resultat partiel, hors deployment"; then
  echo "WARN : statut pending non publie ; test local toujours execute." >&2
fi
if bash "$ROOT/tools/ci/fallback_local.sh" "$SHA"; then
  if [[ -z "${EDUSYNC_GITHUB_STATUS_TOKEN_FILE:-}" ]]; then
    printf 'PASS_LOCAL_UNPUBLISHED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LAST_RESULT"
    echo "PASS local uniquement pour $BRANCH/$SHA. Aucun statut distant : jeton non configure."
  elif publish_status success "Tests CI locaux PASS; CD/staging non certifies"; then
    printf 'PASS_LOCAL_REPORTED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LAST_RESULT"
    echo "PASS local publie sous external/edusync-ci pour $BRANCH/$SHA."
  else
    printf 'PASS_LOCAL_STATUS_UNPUBLISHED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LAST_RESULT"
    echo "Les tests locaux passent, mais GitHub n'a pas recu leur statut." >&2
    exit 74
  fi
  echo "Aucune preuve de workflow GitHub Actions, aucune image GHCR publiee, aucun deploiement."
else
  code=$?
  printf 'FAIL rc=%d %s\n' "$code" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LAST_RESULT"
  publish_status failure "Tests CI locaux FAIL; consulter les journaux du runner" || true
  echo "FAIL rc=$code pour $SHA : consulter ~/edusync-ci-reports." >&2
  exit "$code"
fi
