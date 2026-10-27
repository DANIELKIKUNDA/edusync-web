#!/usr/bin/env bash
# Construction locale d'images applicatives a partir d'un SHA ayant reussi la CI de secours.
# PAS de push sur GHCR, PAS de preuve de CI GitHub, PAS de deploiement.
set -Eeuo pipefail
umask 077
if [[ $# -ne 2 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: bash tools/ci/fallback_build_images.sh <SHA-40> <rapport-summary.txt-PASS>" >&2
  exit 64
fi
SHA="$1"
SUMMARY="$(realpath "$2")"
[[ -f "$SUMMARY" ]] || { echo "Rapport inexistant" >&2; exit 65; }
grep -Fxq "sha=$SHA" "$SUMMARY" || { echo "SHA et rapport incompatibles" >&2; exit 65; }
grep -Fxq "result=PASS" "$SUMMARY" || { echo "REFUS : resultat CI non PASS" >&2; exit 65; }
ROOT="$(git rev-parse --show-toplevel)"
[[ "$EUID" -ne 0 ]] || { echo "Ne pas executer avec sudo/root" >&2; exit 77; }
approved=0
for branch in main chatgpt/prefet-directeur-certification; do
  remote_sha="$(git -C "$ROOT" rev-parse -q --verify "refs/remotes/origin/$branch" || true)"
  if [[ -n "$remote_sha" ]] && git -C "$ROOT" merge-base --is-ancestor "$SHA" "$remote_sha"; then
    approved=1
    break
  fi
done
[[ "$approved" == 1 ]] || { echo "REFUS : SHA hors branches approuvees (git fetch origin)" >&2; exit 65; }
command -v docker >/dev/null || exit 69
docker info >/dev/null || exit 69
# Aucun build lourd sur un hote deja occupe par des applications.
bash "$ROOT/tools/ci/fallback_assert_ci_host.sh"
arch="$(docker info --format '{{.Architecture}}')"
case "$arch" in
  x86_64 | amd64) platform=linux/amd64 ;;
  aarch64 | arm64) platform=linux/arm64 ;;
  *) echo "Architecture Docker non prevue : $arch" >&2; exit 69 ;;
esac
mem_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
disk_kb="$(df -Pk /tmp | awk 'END {print $4}')"
if (( mem_kb < 3145728 || disk_kb < 16777216 )); then
  echo "REFUS : il faut au moins 3 Gio RAM libres et 16 Gio disque libres." >&2
  exit 75
fi

WORK="$(mktemp -d /tmp/edusync-images.XXXXXXXX)"
cleanup() {
  rc=$?
  set +e
  if [[ -d "$WORK" ]]; then
    # Dockerfiles executent COPY (aucune modification attendue du dossier source).
    rm -rf -- "$WORK"
  fi
  exit "$rc"
}
trap cleanup EXIT
git -C "$ROOT" archive "$SHA" | tar -x -C "$WORK"
OUT="$HOME/edusync-ci-reports/images-$SHA-$(date -u +%Y%m%dT%H%M%SZ).txt"
mkdir -p "$(dirname "$OUT")"
{
  echo "SHA=$SHA"
  echo "CI_REPORT=$SUMMARY"
  echo "PLATFORM=$platform"
  echo "PURPOSE=LOCAL_TEST_ONLY_NO_PUBLISH_NO_DEPLOY"
} > "$OUT"
while IFS=' ' read -r name dir; do
  image="edusync-local-${name}:$SHA"
  echo "Construction de $image ($platform)"
  args=(--pull --platform "$platform" --label "org.opencontainers.image.revision=$SHA")
  if [[ "$name" == frontend ]]; then
    args+=(--build-arg "EDUSYNC_BUILD_ID=$SHA")
  fi
  docker build "${args[@]}" -t "$image" "$WORK/$dir"
  id="$(docker image inspect "$image" --format '{{.Id}}')"
  docker_arch="$(docker image inspect "$image" --format '{{.Architecture}}')"
  echo "$name=$image | id=$id | arch=$docker_arch" >> "$OUT"
done <<EOF
backend backend
frontend frontend
backup deploy/backup
EOF
echo "Images locales construites pour $SHA. Rapport : $OUT"
echo "ATTENTION : une image locale ARM64 seule ne remplace pas les images GHCR multi-architecture."
