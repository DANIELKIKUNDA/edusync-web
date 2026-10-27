#!/usr/bin/env bash
# EduSync Web — controles LECTURE SEULE d'un futur executeur CI.
# Aucune installation, aucun arret, aucune modification de conteneur/volume.
set -Eeuo pipefail
echo "=== EduSync CI fallback / preflight (lecture seule) ==="
printf 'Architecture machine : '; uname -m
printf 'Noyau : '; uname -sr
printf 'Utilisateur : '; id -un
printf 'Ressources disponibles :\n'
if [[ -r /proc/meminfo ]]; then
  awk '/^(MemTotal|MemAvailable):/ {printf "  %-15s %.2f Gio\n", $1, $2/1048576}' /proc/meminfo
fi
df -h /tmp "$HOME" 2>/dev/null | awk 'NR==1||!seen[$6]++'
if command -v docker >/dev/null 2>&1; then
  echo "Docker disponible : oui"
  if docker info --format '{{.ServerVersion}} | {{.OSType}}/{{.Architecture}}' 2>/dev/null; then
    echo "Docker accessible : oui"
  else
    echo "Docker accessible : non (permissions ou moteur indisponible)"
  fi
  if docker buildx version >/dev/null 2>&1; then
    echo "Docker Buildx : present"
  else
    echo "Docker Buildx : absent"
  fi
else
  echo "Docker disponible : non"
fi
for cmd in git tar awk flock bash; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'Programme %-9s : oui\n' "$cmd"
  else
    printf 'Programme %-9s : ABSENT\n' "$cmd"
  fi
done
echo
echo "IMPORTANT : diagnostic des ressources ne prouve PAS que cette machine est isolee."
echo "Ne pas executer les tests intensifs sur un VPS partage avec Coolify ou la production."
echo "La certification et le deploiement restent soumis aux controles de CICD.md / PRODUCTION.md."
