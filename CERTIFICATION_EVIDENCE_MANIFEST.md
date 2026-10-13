# Manifeste de preuves — certification N0 / N1

Généré le 2026-10-13 19:50 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `9c5d5fae1bde0000c11c842c0ed712446b73daa8` (arbre propre au démarrage : le code testé est exactement ce commit)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.26200)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : Redis server v=6.0.16 sha=00000000:0 malloc=jemalloc-5.2.1 b

## Résultats : 20/20 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Arbre Git propre au démarrage | `git status --porcelain` | **PASS** | propre sur 9c5d5fae1bde | 0 s |
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 570 passed, 6 warnings in 21.97s | 25.7 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 2.4 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 3.2 s |
| Build frontend (vite) | `npm.cmd run build` | **PASS** | built in 931ms[39m | 3.2 s |
| Migrations sur base vierge (provisionnement) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py backend/scripts/provision_` | **PASS** | POINT-4A database provisioning: PASS | 4.0 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 42/42 PASS | 40.5 s |
| Sonde en conditions réelles : team_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 58/58 PASS | 89.5 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 31/31 PASS | 46.4 s |
| Sonde en conditions réelles : health_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 12/12 PASS | 13.6 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 25/25 PASS | 30.5 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 44/44 PASS | 35.1 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 8/8 PASS | 32.6 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 17/17 PASS | 68.4 s |
| Sonde en conditions réelles : mfa_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 60/60 PASS | 121.7 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 16/16 PASS | 183.3 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 6.9 s · rapport : .local/backups/last.json | 11.5 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 46 paquets · npm (exécution) : 73 · à examiner : 2 | 1.1 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 4.1 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 81 secrets checked across 1266 files: 0 leak(s) | 4.5 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `89109661c3c2b6dcb9424a83424407ba898d59514780094127d6c061c1d9a42a` |
| `certification/n0-n1-20261007/audit_probe.py` | `13995d3cf99d67ce4ad5740123043a33576152e1e7411c354107b27eb5611219` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `ac635af91b476e0a0869dd94c9898542c853fe43a7a35f948097eb572320494d` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `38df344909ca11afa7d81b24c0091a515ad88776c544e1d388c5ba83c57d20b9` |
| `certification/n0-n1-20261007/health-live.json` | `1e0ef303ae9fbc9e795ff06ba3d12932bbcd5580055e7e23fa2b551aba94acba` |
| `certification/n0-n1-20261007/health_probe.py` | `d1331c051e3d044b402a6fddd14e6e23c83d4fe55e4a1fdbdaade70a8d698bfa` |
| `certification/n0-n1-20261007/mfa-live.json` | `d1fef40b1c70c76a4f0d0694220b12c49614c1f4ec101e696b9dc58ed523c210` |
| `certification/n0-n1-20261007/mfa_probe.py` | `81d0b39d62b84eb90f3c5e2cfb261f94b25222fcad060e8b97e24a74297a06b9` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `21fa9b9f64257d6f336283c41663cbf83094c98e1e89be0ff37015632d0d9502` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `2f52f4fa530ab4abac8b52b9993b3f4b4bab5bfba4ec24aacf5ebc1c39842a8b` |
| `certification/n0-n1-20261007/notifications-live.json` | `a80470a80a185b358352792c03f9f97d623645da911ac800f56bb4dcb6ca7408` |
| `certification/n0-n1-20261007/notifications_probe.py` | `ac80fb1b0dca93991ebb0b976c655bba810496210db0e87185376a7cb4bb0150` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `ebefbe2cb5ef9dacb52282f29654cc1b4e770518ea78b598ed2c7a290b77941b` |
| `certification/n0-n1-20261007/prereq_probe.py` | `cc73229c5fcc76d0cbd260ae0c2e517d9d4bcf67723eec28301d52c802f0c50d` |
| `certification/n0-n1-20261007/realtime-live.json` | `f2e272fdc52c17085a1aba7792ae2e3c9926e002ab74acec5be6be22554f46cf` |
| `certification/n0-n1-20261007/realtime_probe.py` | `67d310cbf82c9649af78afe150549f1be325c043279e842bbd4e8cad199c5afa` |
| `certification/n0-n1-20261007/resilience-live.json` | `285537574d129e82e5790be47a1fd837211c19821d9af89a661e5e07d927d21c` |
| `certification/n0-n1-20261007/resilience_probe.py` | `a08f40205b8f6de2f1ff176cdcdd3ac4837edf2c1dc4bdb8be14d9425f4e4363` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `c26622ee9dbee24fb116f41d5473a5d440648b8526cac289d49603932399b42c` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `b608c5c179dbbde33ec9031d90db297a9d3af850c29fbabc8722ebec941af68d` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `cb31afb2dfeb410bf326923c38e1c0046d444d585beb767778e20fa48533dcf5` |
| `certification/n0-n1-20261007/supply-chain.json` | `fe1eee9b1556541f3342fb7aec5c715d04aef51b4caa9fc93728b9d5a1d4985c` |
| `certification/n0-n1-20261007/team-live.json` | `ed3b4a7df3e4ab1bd65348a7b6f09b72cc894ad7f9ce318d3418a01cf3eeb76c` |
| `certification/n0-n1-20261007/team_probe.py` | `655fdc2f03786eeace46a8a4a04d2f29fcbc0da04e228e2090c8a2eb35deb7c0` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.

## Addendum — parcours UI exécuté après le script, sur le même commit

Parcours `certification/n0-n1-20261007/n1_journey.mjs` (Edge sans interface, build de production) exécuté sur
`9c5d5fae1bde0000c11c842c0ed712446b73daa8` juste après les 20 étapes ci-dessus : **51/51 PASS**, dont la
validation en deux étapes à 390 et 320 px (activation, codes de secours, code faux, code de secours) et sur bureau
(onglet Sécurité, fiche Équipe). Les empreintes ci-dessous remplacent celles de ces fichiers dans le tableau précédent.

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/n1-journey-live.json` | `e1976a0bd1a2dc41379cc1a437be73d35deb70b5735aec0d24c83d9992309e11` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `2f52f4fa530ab4abac8b52b9993b3f4b4bab5bfba4ec24aacf5ebc1c39842a8b` |
| `certification/n0-n1-20261007/captures/mfa-challenge-390.png` | `538c7c60d8c2325e73d33e13fda6e3a1fef000f809139b3ded73869d10f6ed8d` |
| `certification/n0-n1-20261007/captures/mfa-challenge-wrong-390.png` | `814cc83fe865d4d1b67607f67535b6ee930e022588de6a0010e37029c835cdfc` |
| `certification/n0-n1-20261007/captures/mfa-enroll-codes-390.png` | `edfbacc0c3482bdeb7058b8f1d7048eabd65cd8a99cc6c92fa002d42fa7290dd` |
| `certification/n0-n1-20261007/captures/mfa-enroll-key-390.png` | `48c157b107d96c44edd9c19cb1ef3d4202f50cd49fdd1bb66aef4a45721e542d` |
| `certification/n0-n1-20261007/captures/mfa-enroll-scan-390.png` | `e8d94e0399d1f91da9ddf358ee7a09a90e06557e8eb77096baae7224b76a55d3` |
| `certification/n0-n1-20261007/captures/mfa-enroll-wrong-390.png` | `37800b1934494775cd3d6d20c1a0a3535bf472bf5e9f9afffe821db1f44350c8` |
| `certification/n0-n1-20261007/captures/mfa-recovery-390.png` | `ffd65e13e7d824490cd48c6dc5e54df9a844ed178c5b5da6d28a0efc637adccd` |
| `certification/n0-n1-20261007/captures/mfa-security-tab-1280.png` | `947f21c4797170b8ff875c7118e3bb8c9ce397e2c50772fe655b1bb308e99aec` |
| `certification/n0-n1-20261007/captures/mfa-team-sheet-1280.png` | `a1f58a64fcd79e3386b3093972c850e7596e7c13e6d6f26e9423fca93980fab0` |

