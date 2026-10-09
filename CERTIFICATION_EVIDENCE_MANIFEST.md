# Manifeste de preuves — certification N0 / N1

Généré le 2026-10-09 04:48 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `b5d91cc3111b1db453deb3c8f816662244145e74` (arbre de travail modifié au moment de l'exécution)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.22631)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : TIMEOUT

## Résultats : 14/16 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 536 passed, 6 warnings in 410.78s (0:06:50) | 447.4 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 11.3 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 66.8 s |
| Migrations sur base vierge (provisionnement) | `python.exe E:\edusyncweb\.local\closure\run.py backend/scripts/provision_database.py` | **PASS** | POINT-4A database provisioning: PASS | 48.1 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/prereq_probe.p` | **PASS** | == 42/42 PASS | 91.1 s |
| Sonde en conditions réelles : team_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/team_probe.py` | **PASS** | == 58/58 PASS | 47.0 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/school_lifecyc` | **PASS** | == 31/31 PASS | 48.9 s |
| Sonde en conditions réelles : health_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/health_probe.p` | **PASS** | == 12/12 PASS | 22.2 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/audit_probe.py` | **PASS** | == 25/25 PASS | 21.5 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/notifications_` | **PASS** | == 44/44 PASS | 51.0 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/hardening_http` | **PASS** | == 17/17 PASS | 86.8 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/resilience_pro` | **FAIL** | == 15/16 PASS | 456.5 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **FAIL** | (Background on this error at: https://sqlalche.me/e/20/e3q8) | 25918.3 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 44 paquets · npm (exécution) : 72 · à examiner : 2 | 88.4 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 385.1 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 78 secrets checked across 1229 files: 0 leak(s) | 320.6 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `e557f0ce34047b4031c0943e759c838dfc4b5eeac4506657bcf2cceba8d2094e` |
| `certification/n0-n1-20261007/audit_probe.py` | `f6ab2ca727ff3e6fca5bb16f77cf8a1e632355b89869875fcfb8a13369b869ba` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `728396c8ce3ccd7994fddc55774b3d532fb89f70cb6b78a1a679ffaa24b4a9f3` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `aeec4229424ef2733935ea6ff5e518b59b525fc1f9322317891caf4eb92ea26a` |
| `certification/n0-n1-20261007/health-live.json` | `2c5424b55feabda9d5799e2ae2ffab27f26b8e36d05b7bb5d01fc044b6a13453` |
| `certification/n0-n1-20261007/health_probe.py` | `4711ce89d87d49359521798c1e4aeb4dbeb0fea97b96c87e13e5a0a88a405b60` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `07a42382c184e6ff999701376ead5954f6eda384830538e5a1ac7a96fbe03366` |
| `certification/n0-n1-20261007/notifications-live.json` | `d65db2fd391800a3fd5376d5d372b4fbe5c7373c591b4be183f0befc49edaa63` |
| `certification/n0-n1-20261007/notifications_probe.py` | `dc011058994146f658987743514a46c942aa32d24066f98db1b993ade65e9359` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `a0f0ca4311d7e4dc4d1f0da545a552f683a8ad5be6d2e94257fc2750ecf40270` |
| `certification/n0-n1-20261007/prereq_probe.py` | `cc73229c5fcc76d0cbd260ae0c2e517d9d4bcf67723eec28301d52c802f0c50d` |
| `certification/n0-n1-20261007/resilience-live.json` | `a003dbc20fcbf3f8cf309aa96351a2d18a0b76bce23adc87f037b1f37b25ff0c` |
| `certification/n0-n1-20261007/resilience_probe.py` | `ffd0262a484b08a8a4f4831714c3da9065fad080ff98e5609e0dfabbbeb8f7b6` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `09570792d08c9b105594f9d9669992efedb7a88e0b8ee1e9da5171a12334242a` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `b608c5c179dbbde33ec9031d90db297a9d3af850c29fbabc8722ebec941af68d` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `4d843a1c395a4b40c812eb8aeb719cdbdf02d6c553e86cf400281a2e2e94f58b` |
| `certification/n0-n1-20261007/supply-chain.json` | `dd870754ffacb85d436d1a2117ce98df872dec2160853f6461a69d9ad8876192` |
| `certification/n0-n1-20261007/team-live.json` | `7ce84ca73154f484db19f6e3e495d85ae3ec1495aa003916c8d05d4aa0b1b6be` |
| `certification/n0-n1-20261007/team_probe.py` | `cc452b5695ec0a78828c6245b489c4d0c168a9fe207bfe32c50f75aac1ff86fc` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.
