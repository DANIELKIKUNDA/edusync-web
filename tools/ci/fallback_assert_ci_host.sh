#!/usr/bin/env bash
# Fail-closed safety policy for resource-heavy CI fallback entrypoints.
# Requires an EXCLUSIVE CI Docker host. Refuses a staging host with running containers.
# This script never modifies Docker services, volumes, networks or system settings.
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "REFUS CI : ne pas executer les tests comme root ou via sudo." >&2
  exit 77
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "REFUS CI : Docker absent ; utiliser un hote CI dedie." >&2
  exit 69
fi

if ! docker info >/dev/null 2>&1; then
  echo "REFUS CI : pas d'acces Docker non-root sur cet hote." >&2
  echo "Ne pas ajouter edusyncadmin au groupe docker du serveur staging : acces equivalent root." >&2
  exit 69
fi

# Une machine servant deja staging/Coolify/une autre application n'est pas un
# executeur CI exclusif, meme si MemAvailable est encore important.
if ! running="$(docker ps --format '{{.Names}}')"; then
  echo "REFUS CI : impossible de verifier les conteneurs en cours." >&2
  exit 69
fi
if [[ -n "$running" ]]; then
  count="$(printf '%s\n' "$running" | wc -l)"
  echo "REFUS CI : $count conteneur(s) deja actif(s) sur cet hote." >&2
  echo "Les tests CPU/RAM/Docker sont reserves a une machine de CI sans charges applicatives." >&2
  echo "Ne pas arreter les conteneurs existants pour contourner cette protection." >&2
  exit 75
fi
echo "PASS controle hote CI exclusif : aucun conteneur existant actif."
