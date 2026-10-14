# Manifeste de preuves — certification N0 / N1

Généré le 2026-10-14 08:04 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `bc2344c96d01593a6a9ce360a26d87dc24c04fb1` (arbre propre au démarrage : le code testé est exactement ce commit)
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
| Arbre Git propre au démarrage | `git status --porcelain` | **PASS** | propre sur bc2344c96d01 | 0 s |
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 574 passed, 6 warnings in 23.22s | 26.9 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 2.0 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 5.5 s |
| Build frontend (vite) | `npm.cmd run build` | **PASS** | built in 805ms[39m | 3.0 s |
| Migrations sur base vierge (provisionnement) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py backend/scripts/provision_` | **PASS** | POINT-4A database provisioning: PASS | 4.3 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 42/42 PASS | 54.8 s |
| Sonde en conditions réelles : team_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 58/58 PASS | 90.0 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 31/31 PASS | 47.1 s |
| Sonde en conditions réelles : health_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 12/12 PASS | 12.6 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 25/25 PASS | 30.4 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 44/44 PASS | 34.9 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 8/8 PASS | 33.3 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 17/17 PASS | 67.8 s |
| Sonde en conditions réelles : mfa_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 83/83 PASS | 168.7 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 16/16 PASS | 242.1 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 27.4 s · rapport : .local/backups/last.json | 39.6 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 46 paquets · npm (exécution) : 73 · à examiner : 2 | 4.0 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 16.1 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 81 secrets checked across 1277 files: 0 leak(s) | 15.0 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `37a862436c773b4faf264fc3040287c86ecc570a072b7c9c3b3957c5559727c5` |
| `certification/n0-n1-20261007/audit_probe.py` | `13995d3cf99d67ce4ad5740123043a33576152e1e7411c354107b27eb5611219` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `f4d1d252d181bcfe4a67315721ca2933a31e3bf6bfaef85e52b4abeb1e5e97b6` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `38df344909ca11afa7d81b24c0091a515ad88776c544e1d388c5ba83c57d20b9` |
| `certification/n0-n1-20261007/health-live.json` | `5ec7c39ce6a5df9732ee712d240ce3ecbc0f56da563bf6181be366631a23c7ce` |
| `certification/n0-n1-20261007/health_probe.py` | `d1331c051e3d044b402a6fddd14e6e23c83d4fe55e4a1fdbdaade70a8d698bfa` |
| `certification/n0-n1-20261007/mfa-live.json` | `d0361f45e9c66c7235482406bfc89a17cc2173393cd346dd435d6d1ac2f73a47` |
| `certification/n0-n1-20261007/mfa_probe.py` | `cb6f81fdf152c506eb0189b49ae3a9d73530e73818756c74fa9d7db7702f8508` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `23f6ce21ee468608d1a15cbf04038f8d2e594e0f69ab803629f1eb39614554d9` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `cd8108a1b1c8015fcbf5da5774749f659030bd294b14ff534062228275237fa6` |
| `certification/n0-n1-20261007/notifications-live.json` | `8a6f984ffbc8376fde4c6de7bb2334a0a38b8760b0f69e0eec0f154ccf1d7b21` |
| `certification/n0-n1-20261007/notifications_probe.py` | `ac80fb1b0dca93991ebb0b976c655bba810496210db0e87185376a7cb4bb0150` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `133691eda55acdf40deba1780217b60d068aaa7d931bbbc2cd41af685a9decbd` |
| `certification/n0-n1-20261007/prereq_probe.py` | `cc73229c5fcc76d0cbd260ae0c2e517d9d4bcf67723eec28301d52c802f0c50d` |
| `certification/n0-n1-20261007/realtime-live.json` | `02db41c48ca388d85849286b164aebb38e835c17090e00eeead89fa2414c860a` |
| `certification/n0-n1-20261007/realtime_probe.py` | `67d310cbf82c9649af78afe150549f1be325c043279e842bbd4e8cad199c5afa` |
| `certification/n0-n1-20261007/resilience-live.json` | `cb27f279aaf2bc011521de4ab6ce4720402be049e5fdf265f6211bc317f85f19` |
| `certification/n0-n1-20261007/resilience_probe.py` | `a08f40205b8f6de2f1ff176cdcdd3ac4837edf2c1dc4bdb8be14d9425f4e4363` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `7d18e3d32d0843bd2de5388f57fed49ed58f851d1851d8c26dc3c3f88bdc265a` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `b608c5c179dbbde33ec9031d90db297a9d3af850c29fbabc8722ebec941af68d` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `cb31afb2dfeb410bf326923c38e1c0046d444d585beb767778e20fa48533dcf5` |
| `certification/n0-n1-20261007/supply-chain.json` | `fe1eee9b1556541f3342fb7aec5c715d04aef51b4caa9fc93728b9d5a1d4985c` |
| `certification/n0-n1-20261007/team-live.json` | `d1c81558dd9482bc3c570077ea3fe7054d029858275dc0c8d34507c5429996d7` |
| `certification/n0-n1-20261007/team_probe.py` | `655fdc2f03786eeace46a8a4a04d2f29fcbc0da04e228e2090c8a2eb35deb7c0` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.

## Addendum — parcours UI exécuté après le script, sur le même commit

Parcours `certification/n0-n1-20261007/n1_journey.mjs` (Edge sans interface, build de production) exécuté sur
`bc2344c96d01593a6a9ce360a26d87dc24c04fb1` juste après les 20 étapes ci-dessus : **58/58 PASS** — dont l'activation du second facteur à 390 et 320 px,
la fenêtre « Confirmez avec votre code » avant une action sensible (390 px) puis la reprise automatique de l'action,
la boîte de réinitialisation (390 px), l'avertissement « un seul Manager », l'onglet Sécurité et la fiche Équipe.
Les empreintes ci-dessous remplacent celles de ces fichiers dans le tableau précédent.

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/n1-journey-live.json` | `8cc58baf01c30d75205c35769faa9ebd18c017828ece7aa2691abfd32cfdcb20` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `cd8108a1b1c8015fcbf5da5774749f659030bd294b14ff534062228275237fa6` |
| `certification/n0-n1-20261007/captures/mfa-challenge-390.png` | `3df954b896ac7b2074729969e63eac8d32ad822c5a1bc3a61d8f7b5a330eab7c` |
| `certification/n0-n1-20261007/captures/mfa-challenge-wrong-390.png` | `3d7c9503a22aaddf7ef15843cc3f7762559a6a6c44499bafcd124702627318d4` |
| `certification/n0-n1-20261007/captures/mfa-enroll-codes-390.png` | `ca565ee5ead589a77d0d5ad57f2281698431502305776c45bed519eacf778b58` |
| `certification/n0-n1-20261007/captures/mfa-enroll-key-390.png` | `9dc71a76a45f5f1d9c0f126d1707ecfee96b7fd01c5e9aeb7d94d6058e61d12a` |
| `certification/n0-n1-20261007/captures/mfa-enroll-scan-390.png` | `cfcf2c7884f0d4fad74cb581a5cd6cac4572fd874ca6891c1e8dc24995ef3244` |
| `certification/n0-n1-20261007/captures/mfa-enroll-wrong-390.png` | `55970ac95535fb3feb4b27394c2516539e77635eac968f81ea699b61aee334d0` |
| `certification/n0-n1-20261007/captures/mfa-managers-warning-1280.png` | `d3d4b52fa601427e6be4afbf75031ce44eda43cfb6bef97e8cd35a10563d209f` |
| `certification/n0-n1-20261007/captures/mfa-recovery-390.png` | `de3d086e006f6b9f0341047eae7768aab042fe9fc493b0cc238fab1b7bfe29a3` |
| `certification/n0-n1-20261007/captures/mfa-reset-dialog-390.png` | `13f1046c5f0a403083cc4554528f2f0913bb562796c6824db02c6ce8b57852d0` |
| `certification/n0-n1-20261007/captures/mfa-security-tab-1280.png` | `45115688f8aedcfa19047e4ec728fcc2900a0af2d9993fde47159e924356cf09` |
| `certification/n0-n1-20261007/captures/mfa-stepup-390.png` | `fdcd572ffd49bb0676842acaa34c07ceba2d36b973106c77af4914a613342cd4` |
| `certification/n0-n1-20261007/captures/mfa-stepup-done-390.png` | `ae8ea789c0fc709328bce66a55c8b2b700f57d1ffdcb21c2448bdeb0ea1cadf4` |
| `certification/n0-n1-20261007/captures/mfa-team-sheet-1280.png` | `2ed615115483c7c888471d52353980da3fc43997f30411426354487aaac9c336` |

