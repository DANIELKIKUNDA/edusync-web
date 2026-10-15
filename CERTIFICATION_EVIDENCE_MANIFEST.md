# Manifeste de preuves — certification N0 / N1 / N2

Généré le 2026-10-15 12:33 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `ccfdbc6371dc9e208be2eca96ffa9dd25d03d4ed` (arbre propre au démarrage : le code testé est exactement ce commit)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.26200)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : Redis server v=6.0.16 sha=00000000:0 malloc=jemalloc-5.2.1 b

## Résultats : 22/22 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Arbre Git propre au démarrage | `git status --porcelain` | **PASS** | propre sur ccfdbc6371dc | 0 s |
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 599 passed, 6 warnings in 22.55s | 27.8 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 2.3 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 6.6 s |
| Build frontend (vite) | `npm.cmd run build` | **PASS** | built in 744ms[39m | 5.7 s |
| Migrations sur base vierge (provisionnement) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py backend/scripts/provision_` | **PASS** | POINT-4A database provisioning: PASS | 7.3 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 42/42 PASS | 55.6 s |
| Sonde en conditions réelles : team_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 58/58 PASS | 90.3 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 33/33 PASS | 49.5 s |
| Sonde en conditions réelles : health_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 12/12 PASS | 9.7 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 25/25 PASS | 30.6 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 44/44 PASS | 35.7 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 8/8 PASS | 32.9 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 17/17 PASS | 66.0 s |
| Sonde en conditions réelles : mfa_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 83/83 PASS | 1760.5 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 16/16 PASS | 207.3 s |
| Sonde en conditions réelles : n2_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 50/50 PASS | 30.7 s |
| Parcours UI N2 (téléphone + 7 largeurs) | `node n2_journey.mjs` | **PASS** | PARCOURS N2 : PASS | 221.9 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 14.0 s · rapport : .local/backups/last.json | 18.0 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 46 paquets · npm (exécution) : 73 · à examiner : 2 | 3.2 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 5.1 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 190 secrets checked across 1465 files: 0 leak(s) | 5.7 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/n0-n1-20261007/audit-live.json` | `4b4627258f7966d23f0709871e8e7e5b8403848da2dc01cb5784b2d534f9a558` |
| `certification/n0-n1-20261007/audit_probe.py` | `13995d3cf99d67ce4ad5740123043a33576152e1e7411c354107b27eb5611219` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `3eb325c0d12f67f8ce1376b081bbd4dbe81dcc0034a5332f44cbbfc178af078d` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `38df344909ca11afa7d81b24c0091a515ad88776c544e1d388c5ba83c57d20b9` |
| `certification/n0-n1-20261007/health-live.json` | `3f7d24cd8f5b44350ad1bec5d7aa6d0ee0f160da8d705616b391cf560e81ff36` |
| `certification/n0-n1-20261007/health_probe.py` | `d1331c051e3d044b402a6fddd14e6e23c83d4fe55e4a1fdbdaade70a8d698bfa` |
| `certification/n0-n1-20261007/mfa-live.json` | `4b23de700d75675e9c2ada75d7c66324c875bfcb3ca572dd273a7112c11382cb` |
| `certification/n0-n1-20261007/mfa_probe.py` | `cb6f81fdf152c506eb0189b49ae3a9d73530e73818756c74fa9d7db7702f8508` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `8cc58baf01c30d75205c35769faa9ebd18c017828ece7aa2691abfd32cfdcb20` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `cd8108a1b1c8015fcbf5da5774749f659030bd294b14ff534062228275237fa6` |
| `certification/n0-n1-20261007/notifications-live.json` | `d1eb53f60042dc1195da88fe34878308fb3c7b0fadefd93e6a352bcdfdbf82b3` |
| `certification/n0-n1-20261007/notifications_probe.py` | `ac80fb1b0dca93991ebb0b976c655bba810496210db0e87185376a7cb4bb0150` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `8beb06e12e0bce752b04d5eb6da135c32b6f8c5076e416c1aa43da098db5c111` |
| `certification/n0-n1-20261007/prereq_probe.py` | `b7821c2a3a78a11a0d55e0a810405ebf11c6b27a1c29572263d9e8af6c42606c` |
| `certification/n0-n1-20261007/realtime-live.json` | `ae5a70ecf82957a2ed891182f1fce61279903dc696ede2fb32323752b270e2a2` |
| `certification/n0-n1-20261007/realtime_probe.py` | `67d310cbf82c9649af78afe150549f1be325c043279e842bbd4e8cad199c5afa` |
| `certification/n0-n1-20261007/resilience-live.json` | `2c2a4ef542b117e38d83304582d4066036a0832eb9d680f9c63fd23811143f7d` |
| `certification/n0-n1-20261007/resilience_probe.py` | `a08f40205b8f6de2f1ff176cdcdd3ac4837edf2c1dc4bdb8be14d9425f4e4363` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `d9321d7e52e5ae40ee14e9da7fae2556196f28d23941385f7a716184853cac6e` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `ce02587d838f19496d38ffdcf0d7134941d66b12e16515812a35ca3173c53164` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `df7f7862133b32e4ce7e42fdf6517568386c35c7e70959a42333d80dbe4bac4a` |
| `certification/n0-n1-20261007/supply-chain.json` | `fe1eee9b1556541f3342fb7aec5c715d04aef51b4caa9fc93728b9d5a1d4985c` |
| `certification/n0-n1-20261007/team-live.json` | `54b6af2f58d36a274a80aeff71568ba1f1e0468f195ca552b23a8cc11fe85b66` |
| `certification/n0-n1-20261007/team_probe.py` | `655fdc2f03786eeace46a8a4a04d2f29fcbc0da04e228e2090c8a2eb35deb7c0` |
| `certification/n2-20261014/access_check.mjs` | `ccd7914291756f793c40ff19aefe67342f8c01b87ebc68b651db4919894d7dbd` |
| `certification/n2-20261014/admission-live.json` | `6b1048d60ee91508858fed9b831e18de5632da9593974e0616c8b2c9212505c8` |
| `certification/n2-20261014/admission_probe.py` | `885ce007eb56e935848b78ca046b46bd594da9f7d686b39ffbdf372b1e544976` |
| `certification/n2-20261014/anticipation-live.json` | `17f9d97758b953ded7113b1b80efc30bda4045d4a3852e0f4457a80e3ba08e4a` |
| `certification/n2-20261014/anticipation_probe.py` | `6f84ac12d7a9bd47818c3a3fbccd83dbe5511fb4825a96e5e1bde926b456db06` |
| `certification/n2-20261014/anticipation_ui_check.mjs` | `585d6ab288f52b7b6541e58613d5e43a2719b12eff2e754569ac8ae13aed6bba` |
| `certification/n2-20261014/audit-metrics.json` | `59e8d58ce19227aa09be007ca44e75651503064ef12a5002ce91e89d794f1a3d` |
| `certification/n2-20261014/benefits-live.json` | `18f6820413c2704fd9e83dd009904d4420fcc7ed5c28706a855998fb4b285980` |
| `certification/n2-20261014/benefits_probe.py` | `68e049a0f6871545c7a2ced8808035dd17378bb830967bd0833217c8a963e938` |
| `certification/n2-20261014/benefits_ui_check.mjs` | `9d7b9404ce318e20c9ba596a108ef5f5bab07e356d41f98f867b0b9eecb9e477` |
| `certification/n2-20261014/cdp.mjs` | `19516e77d9cad1464a09305693212027a94edea7e84cc1f356d18b47337d6ae3` |
| `certification/n2-20261014/class-status-live.json` | `d192dd47a345e46b0682fa6f4fd7a4505ad983363c50e3636a6dc5408ad7789a` |
| `certification/n2-20261014/class_status_probe.py` | `ee1c47053643ac9c8f4b28c9112cf43b0351e977be6204555d1c068e6e749a16` |
| `certification/n2-20261014/class_ui_check.mjs` | `6b00f5b2f50104f7d1e2afcc4ae205ac466cae07fa97f6c9dc942d7d299e680e` |
| `certification/n2-20261014/enrollment_check.mjs` | `155a25a14419b09e5a985fcd733b96913e7b5fea3b16eee2b7d9eabcd1255e03` |
| `certification/n2-20261014/fee-schedules-live.json` | `3604481791341297f2ee12fae30ef68629ee52138c1eea20a78f7191f8045262` |
| `certification/n2-20261014/fee_schedules_probe.py` | `a6bfdd781be0305449d4c8196231b5844dd0df42bba2c45018adef2753e8dfb4` |
| `certification/n2-20261014/n2-journey.json` | `369cc1e68234174804b5450d680c3f9c0f4b1e0848e30b4b21efd0c368a74f21` |
| `certification/n2-20261014/n2-live.json` | `4f82d242f6ed7361ad22a1459f55389540a433acefae6048170a23412438a1bf` |
| `certification/n2-20261014/n2_audit.mjs` | `ca32e409e9300e6cec2e1a3b893a4b2b5c7c4475270689470b684debce9da89d` |
| `certification/n2-20261014/n2_journey.mjs` | `8a76105e2ac73d60408f013d2d21db7dc336296b4f4357c72b78c4291f3b4444` |
| `certification/n2-20261014/n2_probe.py` | `98f5492061b1145d81226672d83cda3b8a2dd68f6451879c5d5577fedca5beed` |
| `certification/n2-20261014/options_check.mjs` | `be071ca98b5ea870ba0bd575241602bbedc0756ab6f54bda5cb0202b79fe5a3f` |
| `certification/n2-20261014/payment-policy-live.json` | `2e767275b1813c4676a40afd69d3b73f561f5659b545103d67105e3c7f761432` |
| `certification/n2-20261014/payment_policy_probe.py` | `3b6774c97d23c0659ecaf17e333c49960ff9af43ddc8c853af2c61a0e2026248` |
| `certification/n2-20261014/rail_check.mjs` | `6848ee2e6265fcbc8b0104d7023913e81f93e8910e1ec30911164d452d25626a` |
| `certification/n2-20261014/readiness_check.mjs` | `bea7ef084f43de4a27cb7db77162f8e32c680ddaedc46f0f6f04e22205114474` |
| `certification/n2-20261014/receipt-settings-live.json` | `4484ebe09b3e339c58eb1d8d06b68e175b0c1e8849790138a7c2470247ebd899` |
| `certification/n2-20261014/receipt_settings_probe.py` | `3b1dbd19eb2419b2599101fc170cd270ba51a2b5baf670dffaf96356d332b620` |
| `certification/n2-20261014/settings_back.mjs` | `0f50a0f0ce35a36eb2d0f5820629ae9d6f27dd0f06b54ac6a8e52a3be1c7203b` |
| `certification/n2-20261014/settings_check.mjs` | `57ee2b613e25656c06fc9b562da20932158d28d2e68913f9b660ffd76b5573b8` |
| `certification/n2-20261014/sheet_debug.mjs` | `d345af2feaf17d8b968d93f34f2fcc1037f16e50efe7a214e0fd10ed6593d030` |
| `certification/n2-20261014/sidebar_check.mjs` | `42b71cfdd893b950a589b3a47e3329368b36bdbc551bbbdb9fe757a2e09be772` |
| `certification/n2-20261014/tablet_check.mjs` | `f41dc5a993056e5a1edb366f44ab1d4ee9c385f7b225f6d023a57d682ae78ec6` |
| `certification/n2-20261014/tariff-rules-live.json` | `a0df8092e7755c3767337453fe57929d5315ccb37893fb324d97b1349ba4a1ab` |
| `certification/n2-20261014/tariff_rules_probe.py` | `d4c2365d4fbcd26d546e2641d1fa7ad7ee51adc7b87cf75bbcb42470354edb57` |
| `certification/n2-20261014/tariffs_ui_check.mjs` | `e8896e49e1d1176c7f3cb019338cb3030b38606157825e85c23c6eed01468cf8` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.
