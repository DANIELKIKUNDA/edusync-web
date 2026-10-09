# Manifeste de preuves — certification N0 / N1

Généré le 2026-10-09 19:23 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `bbe90e2da8580fddbbfed8d6c0c220be3785e907` (arbre de travail modifié au moment de l'exécution)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.22631)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : Redis server v=6.0.16 sha=00000000:0 malloc=jemalloc-5.2.1 b

## Résultats : 17/17 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 538 passed, 6 warnings in 56.25s | 64.1 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 1.2 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 10.2 s |
| Migrations sur base vierge (provisionnement) | `python.exe E:\edusyncweb\.local\closure\run.py backend/scripts/provision_database.py` | **PASS** | POINT-4A database provisioning: PASS | 5.4 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/prereq_probe.p` | **PASS** | == 42/42 PASS | 43.3 s |
| Sonde en conditions réelles : team_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/team_probe.py` | **PASS** | == 58/58 PASS | 27.1 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/school_lifecyc` | **PASS** | == 31/31 PASS | 32.4 s |
| Sonde en conditions réelles : health_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/health_probe.p` | **PASS** | == 12/12 PASS | 8.0 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/audit_probe.py` | **PASS** | == 25/25 PASS | 10.8 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/notifications_` | **PASS** | == 44/44 PASS | 26.1 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/realtime_probe` | **PASS** | == 8/8 PASS | 20.0 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/hardening_http` | **PASS** | == 17/17 PASS | 50.6 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/resilience_pro` | **PASS** | == 16/16 PASS | 260.5 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 46.5 s · rapport : .local/backups/last.json | 51.0 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 44 paquets · npm (exécution) : 73 · à examiner : 2 | 0.7 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 7.4 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 78 secrets checked across 1259 files: 0 leak(s) | 3.2 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `23c38ec5860465f4fc192d457f97b67b3bd472838973996f5e945ae6ab012937` |
| `certification/n0-n1-20261007/audit_probe.py` | `f6ab2ca727ff3e6fca5bb16f77cf8a1e632355b89869875fcfb8a13369b869ba` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `51f03510bfe146acde740fe1aaf9e3f0803f767f6f0a74dda663e3b4e23d33a8` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `aeec4229424ef2733935ea6ff5e518b59b525fc1f9322317891caf4eb92ea26a` |
| `certification/n0-n1-20261007/health-live.json` | `046d638bf682ffd73c7c34db9e677c322cc5872cd24f67274fe9d7920f1ae233` |
| `certification/n0-n1-20261007/health_probe.py` | `f9a8d9818b8f60d5aaafea320ea990fcced6daf602e341625c2394b523a5a638` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `a1422cb2c8a28380c25253ce66e513a230622940d131d6ffba758989c02d9463` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `4f8b3436cbe19748d6d8f666d20418b4098449fa653ee4618b3589f568deb297` |
| `certification/n0-n1-20261007/notifications-live.json` | `091972bc764f375a2fd685997b19190f7ff533d171bc911c90857790df8b0c40` |
| `certification/n0-n1-20261007/notifications_probe.py` | `dc011058994146f658987743514a46c942aa32d24066f98db1b993ade65e9359` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `fa7f0c85c7567328c7b1c6f88cd439a1747f6976f409b575131b926d4fdd00da` |
| `certification/n0-n1-20261007/prereq_probe.py` | `cc73229c5fcc76d0cbd260ae0c2e517d9d4bcf67723eec28301d52c802f0c50d` |
| `certification/n0-n1-20261007/realtime-live.json` | `da250fa757f7f67bfa7e149568fda86f7bb79b75cfc54fff7dee92f4152777a8` |
| `certification/n0-n1-20261007/realtime_probe.py` | `2d5e7ee4e62e95eafbaabb2929b619b1f96f40f1d0397baa015a76a4b137dbf8` |
| `certification/n0-n1-20261007/resilience-live.json` | `f1faef192dce7d2c6d779fe1b3b78c77d5a14c168e40bf87240749a8774ed022` |
| `certification/n0-n1-20261007/resilience_probe.py` | `ffd0262a484b08a8a4f4831714c3da9065fad080ff98e5609e0dfabbbeb8f7b6` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `2790e8051f9f0bef72cc743e610ceb3f6f3956f761b2c9d726e671d8f9e6af4c` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `b608c5c179dbbde33ec9031d90db297a9d3af850c29fbabc8722ebec941af68d` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `4d843a1c395a4b40c812eb8aeb719cdbdf02d6c553e86cf400281a2e2e94f58b` |
| `certification/n0-n1-20261007/supply-chain.json` | `afe6646c42a88d2a515b7299c8d9fa4262ddab765f75fbfabe475fd8af0ca8c2` |
| `certification/n0-n1-20261007/team-live.json` | `e5e6737311e331a882962248567c4527e57c4b2b873767512ded126756989c9a` |
| `certification/n0-n1-20261007/team_probe.py` | `cc452b5695ec0a78828c6245b489c4d0c168a9fe207bfe32c50f75aac1ff86fc` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.
