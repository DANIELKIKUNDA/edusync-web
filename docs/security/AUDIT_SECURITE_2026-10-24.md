# Audit sécurité CI — 24/10/2026

Branche `security/audit-ci-test-deps` (PR, non fusionnée, non déployée).

## 1. Causes exactes des échecs initiaux

| Exécution | Contrôle en échec | Cause | Nature |
|---|---|---|---|
| Audit dépendances, run 40087715304 (planifié, sur `e5a1125`) | `pip-audit + npm audit` | `npm audit --omit=dev` : **zod < 4.6.6**, GHSA-mrhx-c7xc-m3w5 (gravité haute : épuisement mémoire lors de la validation de collections contraintes surdimensionnées). Le workflow a ouvert le ticket #8 et échoué volontairement | Vulnérabilité réelle, publiée après le dernier push |
| CI, run 40088327019 (`003347f`) | « Sécurité — dépendances, licences, secrets », étape « Vulnérabilités npm (exécution) » | Même avis zod. Les autres jobs (backend, frontend, RBAC, CD privilégiée) étaient verts | Vulnérabilité réelle |

Aucun échec d’outillage, de configuration ou de réseau dans ces deux exécutions.

## 2. Vulnérabilités confirmées

| Paquet | Où | Avis | Statut |
|---|---|---|---|
| zod 4.1.x | dépendance d’exécution du frontend | GHSA-mrhx-c7xc-m3w5 (haute) | **Corrigé** dans `main` par `0eadc0d` (zod 4.6.6, seule copie dans le verrou) ; CI `0eadc0d` verte |
| pypdf 6.19.0 | **installé par la CI** du backend par-dessus la version verrouillée 6.21.2 | 11 CVE (CVE-2026-113786, -113789 à -113795, -115572, -115580, -115585) | **Corrigé dans cette branche**. Défaut de configuration trouvé pendant l’audit : invisible pour pip-audit, qui lit `requirements.lock` et non ce que la CI installe. Dépendance de test uniquement (lecture des PDF générés), jamais livrée dans les images |

## 3. Corrections

1. `.github/workflows/ci.yml` : `pip install pytest==9.1.1 pypdf==6.19.0` → `pip install -c requirements.lock pytest pypdf` (versions du verrou : pytest 9.1.1, pypdf 6.21.2).
2. `backend/tests/test_cicd_contracts.py` : nouveau test `test_ci_never_installs_a_python_package_outside_the_lock`. Tout `pip install` des workflows doit être contraint par le verrou et ne jamais épingler une version différente. Seul l’outil d’audit (`pip-audit==2.10.1`) est exempté. Le test **échoue sur l’ancienne CI** et passe sur la nouvelle.
3. `frontend/browser-tests/school_offline.spec.ts` : instabilité trouvée pendant la non-régression (1 échec sur 30 en exécution parallèle, `ERR_INTERNET_DISCONNECTED` à la réouverture). Cause : la page était fermée avant que le service worker contrôle la page et ait mis l’application en cache. Le test attend désormais ces deux conditions, comme le test hors connexion de la Plateforme. Défaut du test, pas du produit : 48/48 sous charge après correction.

Aucun contrôle désactivé, aucune vulnérabilité masquée, aucune exception d’audit ajoutée.

## 4. Fichiers modifiés

`.github/workflows/ci.yml` · `backend/tests/test_cicd_contracts.py` · `frontend/browser-tests/school_offline.spec.ts` · ce rapport.
Fichiers préservés intacts (vérifiés par empreinte SHA-256 après le contrôle des licences) : `certification/n0-n1-20261007/sbom.cdx.json`, `supply-chain.json`.

## 5. Commandes exécutées (local)

```
gh run view 40087715304 --log-failed ; gh run view 40088327019 --log-failed ; gh issue view 8
gh api repos/DANIELKIKUNDA/edusync-web/dependabot/alerts
pip-audit==2.10.1 -r backend/requirements.lock --no-deps --disable-pip      → aucune vulnérabilité connue
pip-audit -r <pypdf==6.19.0>                                               → 11 vulnérabilités (preuve du défaut)
npm audit --omit=dev ; npm audit                                           → 0 vulnérabilité
python tools/certification/supply_chain.py                                  → 71 Python + 82 npm, 2 à examiner (psycopg LGPL)
python tools/ci/secret_patterns.py                                          → 1 132 fichiers, 0 secret
git log --all -G <clé privée PEM | clé Google | jeton GitHub | Brevo | Stripe> → 0 commit
pytest backend/tests ; npx tsc --noEmit ; npx vitest run tests ; npx vite build
node browser-tests/run.mjs (dev) ; EDUSYNC_TEST_BUILD=1 … platform/offline/school_offline --repeat-each=8 --workers=3
```

## 6. Résultats

| Contrôle | Résultat |
|---|---|
| Tests backend (dont RBAC, isolation, contrats CI/CD) | 914 réussis, 1 ignoré |
| TypeScript | OK |
| Tests frontend (Vitest) | 43/43 |
| Build de production | OK |
| Navigateur (dev) | 22 réussis, 3 ignorés (captures à la demande, tests réservés au build compilé) |
| Navigateur (build compilé, charge) | 48/48 |
| pip-audit / npm audit | 0 / 0 |
| Secrets (arbre + historique) | 0 |
| Licences | 2 points à examiner, non bloquants : psycopg / psycopg-binary 3.3.5 sous LGPL-3.0, liaison dynamique |

## 7. Risques résiduels

- L’alerte Dependabot #1 (zod) et le ticket #8 sont encore ouverts. Ils se fermeront au prochain passage de GitHub sur `main` (déjà corrigé), ou au prochain audit quotidien.
- `pip-audit==2.10.1` est installé hors verrou, sans empreintes : c’est l’outil d’audit, avec ses propres dépendances non figées (risque de chaîne d’approvisionnement de l’outillage CI, faible).
- Le verrou Python n’est pas « hashé » (avertissement de pip-audit `--no-deps`) : une installation avec `--require-hashes` renforcerait l’intégrité.
- psycopg (LGPL) : acceptable en liaison dynamique ; à confirmer juridiquement si une distribution binaire modifiée était envisagée.
- 6 PR Dependabot ouvertes (montées de versions majeures d’actions GitHub, @hookform/resolvers 6) : non traitées ici, à revoir une par une.

## 8. Vérifications nécessitant un environnement externe

- CI GitHub de la PR, dont le job RBAC sur PostgreSQL et le build compilé : à lire sur la PR.
- Fermeture automatique de l’alerte Dependabot #1 et du ticket #8 (GitHub).
- Aucun déploiement : la fusion dans `main`, qui déclencherait le déploiement staging, attend votre autorisation.
