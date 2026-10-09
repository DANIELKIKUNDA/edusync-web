# Manifeste de preuves — certification N0 / N1

Généré le 2026-10-09 19:12 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `09abc1e1ca3ecc9bb1cbfb0a2938fd54d3c703ce` (arbre de travail modifié au moment de l'exécution)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.22631)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : Redis server v=6.0.16 sha=00000000:0 malloc=jemalloc-5.2.1 b

## Résultats : 16/17 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 538 passed, 6 warnings in 255.02s (0:04:15) | 321.8 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 5.4 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 110.4 s |
| Migrations sur base vierge (provisionnement) | `python.exe E:\edusyncweb\.local\closure\run.py backend/scripts/provision_database.py` | **PASS** | POINT-4A database provisioning: PASS | 95.4 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/prereq_probe.p` | **PASS** | == 42/42 PASS | 113.0 s |
| Sonde en conditions réelles : team_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/team_probe.py` | **PASS** | == 58/58 PASS | 44.6 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/school_lifecyc` | **PASS** | == 31/31 PASS | 70.1 s |
| Sonde en conditions réelles : health_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/health_probe.p` | **FAIL** | == 11/12 PASS | 13.0 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/audit_probe.py` | **PASS** | == 25/25 PASS | 14.2 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/notifications_` | **PASS** | == 44/44 PASS | 26.6 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/realtime_probe` | **PASS** | == 8/8 PASS | 21.2 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/hardening_http` | **PASS** | == 17/17 PASS | 57.1 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe E:\edusyncweb\.local\closure\run.py certification/n0-n1-20261007/resilience_pro` | **PASS** | == 16/16 PASS | 557.1 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 141.1 s · rapport : .local/backups/last.json | 147.6 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 44 paquets · npm (exécution) : 73 · à examiner : 3 | 8.1 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 30.2 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 78 secrets checked across 1259 files: 0 leak(s) | 22.6 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `9cb723196b7db3eb850667d9dbaf9f9ea80970b56011e019f207b5e8155d25e2` |
| `certification/n0-n1-20261007/audit_probe.py` | `f6ab2ca727ff3e6fca5bb16f77cf8a1e632355b89869875fcfb8a13369b869ba` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `f3508c39204cc682ea0ce1e5e58d5e278e6c30781ab6706730063fb60bce2e99` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `aeec4229424ef2733935ea6ff5e518b59b525fc1f9322317891caf4eb92ea26a` |
| `certification/n0-n1-20261007/health-live.json` | `ba4a50f726d2ac27323a177c7da148b71c9d6a7adab059137cd2a2f3d68d552f` |
| `certification/n0-n1-20261007/health_probe.py` | `f9a8d9818b8f60d5aaafea320ea990fcced6daf602e341625c2394b523a5a638` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `a1422cb2c8a28380c25253ce66e513a230622940d131d6ffba758989c02d9463` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `4f8b3436cbe19748d6d8f666d20418b4098449fa653ee4618b3589f568deb297` |
| `certification/n0-n1-20261007/notifications-live.json` | `a34e35074c547a6316e2b74410c82842174957f9e7067c588c6c00b734f4b6d6` |
| `certification/n0-n1-20261007/notifications_probe.py` | `dc011058994146f658987743514a46c942aa32d24066f98db1b993ade65e9359` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `358d38208a014f9c5afffc4dafb2580dc44e21bb1c09ebc41cd8b1cc51b58c49` |
| `certification/n0-n1-20261007/prereq_probe.py` | `cc73229c5fcc76d0cbd260ae0c2e517d9d4bcf67723eec28301d52c802f0c50d` |
| `certification/n0-n1-20261007/realtime-live.json` | `3fd39e7ceb3549477442376e9c72be07dacd04a7a98ecf620d7c39e454d98307` |
| `certification/n0-n1-20261007/realtime_probe.py` | `2d5e7ee4e62e95eafbaabb2929b619b1f96f40f1d0397baa015a76a4b137dbf8` |
| `certification/n0-n1-20261007/resilience-live.json` | `6e5dccba9d49042bef991c6421ffba8c1493d1677e565394681de51453146e08` |
| `certification/n0-n1-20261007/resilience_probe.py` | `ffd0262a484b08a8a4f4831714c3da9065fad080ff98e5609e0dfabbbeb8f7b6` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `cf21e292ddec9c8bbe0f997151c480160534a8169b914db3d013357d0cabadec` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `b608c5c179dbbde33ec9031d90db297a9d3af850c29fbabc8722ebec941af68d` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `4d843a1c395a4b40c812eb8aeb719cdbdf02d6c553e86cf400281a2e2e94f58b` |
| `certification/n0-n1-20261007/supply-chain.json` | `9a75b8a520b73c33ebed6ab76dd44249e0ea2547ac17fd6eb7bfeb95048e566c` |
| `certification/n0-n1-20261007/team-live.json` | `f8798033e2e7eaf9674add3325b76a19fe9bd260963c83272f5e86f1f2ca943a` |
| `certification/n0-n1-20261007/team_probe.py` | `cc452b5695ec0a78828c6245b489c4d0c168a9fe207bfe32c50f75aac1ff86fc` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.
