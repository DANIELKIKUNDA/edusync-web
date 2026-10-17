# Manifeste de preuves — certification N0 / N1 / N2 / N3 + messagerie externe

Généré le 2026-10-17 14:16 UTC par `tools/certification/n0_n1_certify.py`.

* Commit : `2ad66ef309cf16a614d96ca20307254d2fc5a8b1` (arbre propre au démarrage : le code testé est exactement ce commit)
* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)
* OS : Windows 11 (10.0.26200)
* Python : 3.13.14
* Node : v24.19.0
* PostgreSQL : postgres (PostgreSQL) 16.11
* Redis (WSL) : Redis server v=6.0.16 sha=00000000:0 malloc=jemalloc-5.2.1 b

## Résultats : 47/47 étapes PASS

Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.

| Étape | Commande | Résultat | Détail | Durée |
|---|---|---|---|---|
| Arbre Git propre au démarrage | `git status --porcelain` | **PASS** | propre sur 2ad66ef309cf | 0 s |
| Tests backend (pytest) | `python.exe -m pytest -q -p no:cacheprovider --basetemp=../.local/pytest-tmp` | **PASS** | 647 passed, 6 warnings in 19.45s | 22.8 s |
| Compilation Python (compileall) | `python.exe -m compileall -q src` | **PASS** | OK | 2.0 s |
| Typecheck frontend (tsc) | `npx.cmd tsc --noEmit -p tsconfig.json` | **PASS** | 0 erreur | 5.2 s |
| Build frontend (vite) | `npm.cmd run build` | **PASS** | built in 888ms[39m | 3.6 s |
| Migrations sur base vierge (provisionnement) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py backend/scripts/provision_` | **PASS** | POINT-4A database provisioning: PASS | 4.6 s |
| Sonde en conditions réelles : prereq_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 42/42 PASS | 45.5 s |
| Sonde en conditions réelles : team_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 58/58 PASS | 65.1 s |
| Sonde en conditions réelles : school_lifecycle_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 33/33 PASS | 26.2 s |
| Sonde en conditions réelles : health_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 12/12 PASS | 8.3 s |
| Sonde en conditions réelles : audit_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 25/25 PASS | 20.7 s |
| Sonde en conditions réelles : notifications_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 44/44 PASS | 57.8 s |
| Sonde en conditions réelles : realtime_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 8/8 PASS | 15.2 s |
| Sonde en conditions réelles : hardening_http_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 17/17 PASS | 59.5 s |
| Sonde en conditions réelles : mfa_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 83/83 PASS | 143.3 s |
| Sonde en conditions réelles : resilience_probe.py | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n0-n1-202610` | **PASS** | == 16/16 PASS | 185.4 s |
| Sonde en conditions réelles : n2_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 50/50 PASS | 29.9 s |
| Parcours UI N2 (téléphone + 7 largeurs) | `node n2_journey.mjs` | **PASS** | PARCOURS N2 : PASS | 219.3 s |
| Sonde en conditions réelles : admission_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 16/16 PASS | 13.7 s |
| Sonde en conditions réelles : anticipation_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 32/32 PASS | 21.7 s |
| Sonde en conditions réelles : benefits_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 21/21 PASS | 13.0 s |
| Sonde en conditions réelles : class_status_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 21/21 PASS | 23.5 s |
| Sonde en conditions réelles : fee_schedules_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 18/18 PASS | 33.6 s |
| Sonde en conditions réelles : payment_policy_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 18/18 PASS | 30.4 s |
| Sonde en conditions réelles : receipt_settings_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 12/12 PASS | 35.3 s |
| Sonde en conditions réelles : tariff_rules_probe.py (N2) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n2-20261014/` | **PASS** | == 36/36 PASS | 24.2 s |
| Sonde en conditions réelles : rbac_probe.py (N3-A) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 14/14 PASS | 39.4 s |
| Sonde en conditions réelles : cash_integrity_probe.py (N3-B) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 37/37 PASS | 27.6 s |
| Contrôle UI N3-B (390 px + 1280 px) | `node cash_ui_check.mjs` | **PASS** | UI N3-B : PASS | 25.4 s |
| Sonde en conditions réelles : decisions_probe.py (N3-C) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 28/28 PASS | 14.8 s |
| Contrôle UI N3-C (390 px + 1280 px) | `node decisions_ui_check.mjs` | **PASS** | UI N3-C : PASS | 15.3 s |
| Sonde en conditions réelles : advance_funds_probe.py (N3-D) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 29/29 PASS | 17.8 s |
| Contrôle UI N3-D (390 px + 1280 px) | `node funds_ui_check.mjs` | **PASS** | UI N3-D : PASS | 27.7 s |
| Sonde en conditions réelles : checkout_rules_probe.py (N3-E) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 15/15 PASS | 11.6 s |
| Contrôle UI N3-E (390 px + 1280 px) | `node checkout_ui_check.mjs` | **PASS** | UI N3-E : PASS | 12.0 s |
| Sonde en conditions réelles : payroll_probe.py (N3-F) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 17/17 PASS | 23.3 s |
| Contrôle UI N3-F (390 px + 1280 px) | `node payroll_ui_check.mjs` | **PASS** | UI N3-F : PASS | 15.7 s |
| Sonde en conditions réelles : reports_probe.py (N3-G) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 25/25 PASS | 18.3 s |
| Contrôle UI N3-G (390 px + 1280 px) | `node reports_ui_check.mjs` | **PASS** | UI N3-G : PASS | 17.8 s |
| Sonde en conditions réelles : schooling_parity_probe.py (N3-H) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/n3-20261015/` | **PASS** | == 21/21 PASS | 20.7 s |
| Contrôle UI N3-H (390 px + 1280 px) | `node schooling_ui_check.mjs` | **PASS** | UI N3-H : PASS | 60.1 s |
| Sonde messagerie externe locale (fournisseurs simulés) | `python.exe C:\Users\cs-ap\dev\edusync-web\.local\closure\run.py certification/messaging-20` | **PASS** | == 53/53 PASS | 57.7 s |
| Contrôle UI messagerie (390 px + 1280 px) | `node messaging_ui_check.mjs` | **PASS** | UI MESSAGERIE : PASS | 62.3 s |
| Sauvegarde + restauration vérifiée | `python.exe tools/local/backup_restore.py --db edusync_claude_fresh` | **PASS** | == 8/8 PASS · 10.4 s · rapport : .local/backups/last.json | 14.1 s |
| Chaîne d'approvisionnement (licences, SBOM) | `python.exe tools/certification/supply_chain.py` | **PASS** | Python : 71 paquets · npm (exécution) : 82 · à examiner : 2 | 3.0 s |
| Vulnérabilités npm (npm audit) | `npm.cmd audit --omit=dev` | **PASS** | found 0 vulnerabilities | 4.1 s |
| Scan de secrets | `python.exe .local/closure/secret_scan.py` | **PASS** | 913 secrets checked across 1599 files: 0 leak(s) | 12.2 s |

## Fournisseurs réels (messagerie externe)

Hors du total ci-dessus : `EXTERNAL_REQUIRED` signifie que les secrets du fournisseur ne sont pas encore fournis —
ce n'est ni un PASS ni une certification. `REAL_ACCEPTED` = le fournisseur réel a accepté l'envoi ; la réception sur
l'appareil ou la boîte de test se confirme ensuite à la main (EXTERNAL_MESSAGING_CERTIFICATION.md).

| Fournisseur | Sonde | Statut | Durée |
|---|---|---|---|
| E-mail (SMTP) | `email_provider_probe.py` | **EXTERNAL_REQUIRED** | 1.9 s |
| SMS (Orange) | `sms_provider_probe.py` | **EXTERNAL_REQUIRED** | 2.5 s |
| Push (Firebase) | `push_provider_probe.py` | **EXTERNAL_REQUIRED** | 2.4 s |

## Fichiers de preuve (SHA-256)

| Fichier | SHA-256 |
|---|---|
| `certification/messaging-20261016/email_provider_probe-live.json` | `20c806c31ed67aeb2613c9076dfff56ede848436334f27e31ff33af965cfc08c` |
| `certification/messaging-20261016/email_provider_probe.py` | `3ed71c0b57cbe302a85bf4be567d3511e4b4193a8d3dcafaff68bc125ae8b294` |
| `certification/messaging-20261016/messaging-local-live.json` | `1e8b9ff6107cbcb2ecb9edd8d3ab3121620144cbc58249ee850d70fb6daa6c07` |
| `certification/messaging-20261016/messaging_local_probe.py` | `cb75c5498f7d1673855de5db3795c72d9029d29c9a0903d058aeee3d2fdf5fcd` |
| `certification/messaging-20261016/messaging_ui_check.mjs` | `097e06175e0a5abc35f9512dcd21709c8d9ef7d66346c948118a8618c75e4250` |
| `certification/messaging-20261016/provider_probe_common.py` | `ee3fda801ebfe0e841739ab0114be7b816eac51b357cc98c7e6b9a554dff36f5` |
| `certification/messaging-20261016/push_provider_probe-live.json` | `ab9d6f4064cfc4c9aca8efe459111ea4083b54ba650c3b922257c07712519d1d` |
| `certification/messaging-20261016/push_provider_probe.py` | `b6f52c6e3b50d65c463a8b174befd8a916cf9dc27167c66e83603331d2ae993d` |
| `certification/messaging-20261016/sms_provider_probe-live.json` | `bd12404c7f802525af362db40db06165349d8876a8428b3cb59e25e244bde89c` |
| `certification/messaging-20261016/sms_provider_probe.py` | `7901cd603fd2e6f40b00311509b3fdbe51f103f108189c1c428b959f4f782b71` |
| `certification/n0-n1-20261007/audit-live.json` | `7e8e82fde30de7ce548ff352942254dc29db8f3eaa4a48885787d9679283fb65` |
| `certification/n0-n1-20261007/audit_probe.py` | `13995d3cf99d67ce4ad5740123043a33576152e1e7411c354107b27eb5611219` |
| `certification/n0-n1-20261007/backup-restore-live.json` | `bd274aadb11880d0b826eb9f1ebdbe13717bd2a0407e3e5d0144417e6226c47e` |
| `certification/n0-n1-20261007/certify-run.json` | `4669a4416506198d017ef1494e203de01c06fb293b85702848f0b2080d40a7fd` |
| `certification/n0-n1-20261007/hardening-http-live.json` | `27b60fef9cbd81c8f99ea52471a540313ba45d491128ff0d807d7614ac2ab92f` |
| `certification/n0-n1-20261007/hardening_http_probe.py` | `38df344909ca11afa7d81b24c0091a515ad88776c544e1d388c5ba83c57d20b9` |
| `certification/n0-n1-20261007/health-live.json` | `ff8c63217d46962b01278ee31594eff5e00634e60b3e584fb0fcf0246f70338e` |
| `certification/n0-n1-20261007/health_probe.py` | `d1331c051e3d044b402a6fddd14e6e23c83d4fe55e4a1fdbdaade70a8d698bfa` |
| `certification/n0-n1-20261007/mfa-live.json` | `f51b6bc027096e0f613ac47126c229446345446075511551f0bd0cbb04b83018` |
| `certification/n0-n1-20261007/mfa_probe.py` | `cb6f81fdf152c506eb0189b49ae3a9d73530e73818756c74fa9d7db7702f8508` |
| `certification/n0-n1-20261007/n1-journey-live.json` | `8cc58baf01c30d75205c35769faa9ebd18c017828ece7aa2691abfd32cfdcb20` |
| `certification/n0-n1-20261007/n1_journey.mjs` | `cd8108a1b1c8015fcbf5da5774749f659030bd294b14ff534062228275237fa6` |
| `certification/n0-n1-20261007/notifications-live.json` | `76caf296279c6cd0ac3ac62d5975c57d69b56193dc2a7b5952ea4430f942fb1d` |
| `certification/n0-n1-20261007/notifications_probe.py` | `5c1841246f039d85afe8fc0b65c221d24ad91a68e038e57512fbfadc74c2ea49` |
| `certification/n0-n1-20261007/pip-audit.json` | `ee32aecb9a547dfae55791b176c6e063beb502bf5ab380899e463b67bc60931d` |
| `certification/n0-n1-20261007/prereq-live.json` | `c12dd19f0ceb52e715fef7de4deda331832a773e67b9bcfedbf315ccd2b311e9` |
| `certification/n0-n1-20261007/prereq_probe.py` | `b7821c2a3a78a11a0d55e0a810405ebf11c6b27a1c29572263d9e8af6c42606c` |
| `certification/n0-n1-20261007/realtime-live.json` | `f11ca86d57fd90ac67327c79f1ecaea36ddc7b7840cf6c660b588af599713723` |
| `certification/n0-n1-20261007/realtime_probe.py` | `67d310cbf82c9649af78afe150549f1be325c043279e842bbd4e8cad199c5afa` |
| `certification/n0-n1-20261007/resilience-live.json` | `7bd0947773671fdf017c0fad85b3490e41ded983244c69146d53e17ed45758ca` |
| `certification/n0-n1-20261007/resilience_probe.py` | `a08f40205b8f6de2f1ff176cdcdd3ac4837edf2c1dc4bdb8be14d9425f4e4363` |
| `certification/n0-n1-20261007/sbom.cdx.json` | `55e00f951609448203d62c544741a30518d529de114ae20b2f1ef587e2aa42db` |
| `certification/n0-n1-20261007/school-lifecycle-live.json` | `ee36f632ef90b596447140e4bf411ccc2d8fbb84834e3fe47c561bf7d694e746` |
| `certification/n0-n1-20261007/school_lifecycle_probe.py` | `fc6911f0bcbef595e1849442b606a41156a8df57784718b445297f060e88ac3b` |
| `certification/n0-n1-20261007/supply-chain.json` | `d54c8b83031b14d6ef953915a0a51d9519bf6473927e0ad68c0cb6c16c3d20d3` |
| `certification/n0-n1-20261007/team-live.json` | `d78bbdc08383b0e1c9b0f0d7840050342bacaa0ebfca0d8ddef416ecb116a739` |
| `certification/n0-n1-20261007/team_probe.py` | `a467df52af22ca06f648a6989ad1277a2c933968d78bc8b925376934c14a16db` |
| `certification/n2-20261014/access_check.mjs` | `ccd7914291756f793c40ff19aefe67342f8c01b87ebc68b651db4919894d7dbd` |
| `certification/n2-20261014/admission-live.json` | `6b1048d60ee91508858fed9b831e18de5632da9593974e0616c8b2c9212505c8` |
| `certification/n2-20261014/admission_probe.py` | `885ce007eb56e935848b78ca046b46bd594da9f7d686b39ffbdf372b1e544976` |
| `certification/n2-20261014/anticipation-live.json` | `7657684f34ec60d49c9d6008be149b548327d532408da3ffc66fdb59f7b76536` |
| `certification/n2-20261014/anticipation_probe.py` | `845d775a655d528097c3a5a62992b0356a7c0b8e635e361d9682084a3f0df4e8` |
| `certification/n2-20261014/anticipation_ui_check.mjs` | `585d6ab288f52b7b6541e58613d5e43a2719b12eff2e754569ac8ae13aed6bba` |
| `certification/n2-20261014/audit-metrics.json` | `59e8d58ce19227aa09be007ca44e75651503064ef12a5002ce91e89d794f1a3d` |
| `certification/n2-20261014/benefits-live.json` | `18f6820413c2704fd9e83dd009904d4420fcc7ed5c28706a855998fb4b285980` |
| `certification/n2-20261014/benefits_probe.py` | `68e049a0f6871545c7a2ced8808035dd17378bb830967bd0833217c8a963e938` |
| `certification/n2-20261014/benefits_ui_check.mjs` | `9d7b9404ce318e20c9ba596a108ef5f5bab07e356d41f98f867b0b9eecb9e477` |
| `certification/n2-20261014/cdp.mjs` | `19516e77d9cad1464a09305693212027a94edea7e84cc1f356d18b47337d6ae3` |
| `certification/n2-20261014/class-status-live.json` | `4abb0eebf181276498a9d0fe6ca75534eead2f169d3a22b6c418cb87299d5182` |
| `certification/n2-20261014/class_status_probe.py` | `ee1c47053643ac9c8f4b28c9112cf43b0351e977be6204555d1c068e6e749a16` |
| `certification/n2-20261014/class_ui_check.mjs` | `6b00f5b2f50104f7d1e2afcc4ae205ac466cae07fa97f6c9dc942d7d299e680e` |
| `certification/n2-20261014/enrollment_check.mjs` | `155a25a14419b09e5a985fcd733b96913e7b5fea3b16eee2b7d9eabcd1255e03` |
| `certification/n2-20261014/fee-schedules-live.json` | `3604481791341297f2ee12fae30ef68629ee52138c1eea20a78f7191f8045262` |
| `certification/n2-20261014/fee_schedules_probe.py` | `a6bfdd781be0305449d4c8196231b5844dd0df42bba2c45018adef2753e8dfb4` |
| `certification/n2-20261014/n2-journey.json` | `030e15ff20635630ee0bc917d5b20bd05bdcd85ffac813faedbbb958986231ff` |
| `certification/n2-20261014/n2-live.json` | `47867e67c1de5f9fb100c53fcd4982c46d4f93d05d19e6976f708d515c67d868` |
| `certification/n2-20261014/n2_audit.mjs` | `ca32e409e9300e6cec2e1a3b893a4b2b5c7c4475270689470b684debce9da89d` |
| `certification/n2-20261014/n2_journey.mjs` | `8a76105e2ac73d60408f013d2d21db7dc336296b4f4357c72b78c4291f3b4444` |
| `certification/n2-20261014/n2_probe.py` | `98f5492061b1145d81226672d83cda3b8a2dd68f6451879c5d5577fedca5beed` |
| `certification/n2-20261014/options_check.mjs` | `be071ca98b5ea870ba0bd575241602bbedc0756ab6f54bda5cb0202b79fe5a3f` |
| `certification/n2-20261014/payment-policy-live.json` | `e0c954fb8ba83570cd5d8885ebd55b28c8e52b2567b36f39a882f245b7255a06` |
| `certification/n2-20261014/payment_policy_probe.py` | `3b6774c97d23c0659ecaf17e333c49960ff9af43ddc8c853af2c61a0e2026248` |
| `certification/n2-20261014/rail_check.mjs` | `6848ee2e6265fcbc8b0104d7023913e81f93e8910e1ec30911164d452d25626a` |
| `certification/n2-20261014/readiness_check.mjs` | `bea7ef084f43de4a27cb7db77162f8e32c680ddaedc46f0f6f04e22205114474` |
| `certification/n2-20261014/receipt-settings-live.json` | `bb916a27215d93995ae0165f9814b0815376f4591dea420521aba87e9547cf62` |
| `certification/n2-20261014/receipt_settings_probe.py` | `3b1dbd19eb2419b2599101fc170cd270ba51a2b5baf670dffaf96356d332b620` |
| `certification/n2-20261014/settings_back.mjs` | `0f50a0f0ce35a36eb2d0f5820629ae9d6f27dd0f06b54ac6a8e52a3be1c7203b` |
| `certification/n2-20261014/settings_check.mjs` | `57ee2b613e25656c06fc9b562da20932158d28d2e68913f9b660ffd76b5573b8` |
| `certification/n2-20261014/sheet_debug.mjs` | `d345af2feaf17d8b968d93f34f2fcc1037f16e50efe7a214e0fd10ed6593d030` |
| `certification/n2-20261014/sidebar_check.mjs` | `42b71cfdd893b950a589b3a47e3329368b36bdbc551bbbdb9fe757a2e09be772` |
| `certification/n2-20261014/tablet_check.mjs` | `f41dc5a993056e5a1edb366f44ab1d4ee9c385f7b225f6d023a57d682ae78ec6` |
| `certification/n2-20261014/tariff-rules-live.json` | `a0df8092e7755c3767337453fe57929d5315ccb37893fb324d97b1349ba4a1ab` |
| `certification/n2-20261014/tariff_rules_probe.py` | `d4c2365d4fbcd26d546e2641d1fa7ad7ee51adc7b87cf75bbcb42470354edb57` |
| `certification/n2-20261014/tariffs_ui_check.mjs` | `e8896e49e1d1176c7f3cb019338cb3030b38606157825e85c23c6eed01468cf8` |
| `certification/n3-20261015/advance-funds-live.json` | `c171681a1047fd6fafa29892d2d7c5b88551237546d740032c5b71da981a2534` |
| `certification/n3-20261015/advance_funds_probe.py` | `131e57dcc0e8fd200111804382f273d13d5dab16ce67b0f6e861e7cb4b0db05b` |
| `certification/n3-20261015/cash-integrity-live.json` | `f56b9df2263351e92984eece0d5925561866004814269f3c4f0327452c96e2a8` |
| `certification/n3-20261015/cash_integrity_probe.py` | `b048e8be2751c6b66a3604bc71cfd906f22b2e5762283db5598e3db51fbe3261` |
| `certification/n3-20261015/cash_ui_check.mjs` | `ee582f2a6f6ed2db78b7b44b714a2aa03506ae42a7faebd72432ef67ac64d615` |
| `certification/n3-20261015/checkout-rules-live.json` | `f06e32772f7b3dfdc86f934606c3cf32c8b6ca218921d3b828404ae590364bbe` |
| `certification/n3-20261015/checkout_rules_probe.py` | `a5b3f112196bb6c8999aee13d41f8990abe2081169ab99951bade6227fbd58bf` |
| `certification/n3-20261015/checkout_ui_check.mjs` | `ac9d5eade525d745065d4cbf769937f2f7e12c093a29a1ad58dd64e6540c1ac8` |
| `certification/n3-20261015/decisions-live.json` | `2370b96162b720cea9b36743650801c8fdc2e80662751c9ec63bd4b3ee0063dc` |
| `certification/n3-20261015/decisions_probe.py` | `8b92df0989a1bfe9429cada783dd09a13817d3f32411f9c520b860de02dde7be` |
| `certification/n3-20261015/decisions_ui_check.mjs` | `69e7ab0e2809cb8e91ac42c10b02ba3aec15b5af80113ea25f7c8598a275761d` |
| `certification/n3-20261015/funds_ui_check.mjs` | `5d7ce2fa5c65fcfff2c77b86dd15f8f2b0d72ed0a93f92bf52bdeae579ba2e0f` |
| `certification/n3-20261015/payroll-live.json` | `24056a1bc38180c4b7a3d057cc05112c5c15ad0c6fbd62caaba2bf1e9e349eaf` |
| `certification/n3-20261015/payroll_probe.py` | `99d8cc4951c1fc76364862dd2c8673d4dfce8b8b8f5ba85a8550489cf07edd92` |
| `certification/n3-20261015/payroll_ui_check.mjs` | `1808d07799b09a268547ffa747fd77a96f562b23d5c225fbbec7834f5bb1e596` |
| `certification/n3-20261015/rbac-live.json` | `dcc6a8a0a3ac9212c2d360f0da27e47e76568ff355dc81edf6e9257926bd34f2` |
| `certification/n3-20261015/rbac_probe.py` | `0fb17804b69ef4bcf958c11aba0441ff4398682db5581e48b9c26b5b92531e59` |
| `certification/n3-20261015/reports-live.json` | `4607c25c1f102087a8b4a23f9fe88fc9c71b901227fff3afdfea10aa8adb3b60` |
| `certification/n3-20261015/reports_probe.py` | `5acdddb5805215b1b2adba746a07f178c9bc5fb40bd8859bd455e0697accce37` |
| `certification/n3-20261015/reports_ui_check.mjs` | `562856b940b06045b1b78643e1be33bd7e25c6586e5aa156da757c7da38b1a0e` |
| `certification/n3-20261015/schooling-parity-live.json` | `a08e74edca2a5d73a55becf585ac2c0c2f5225520fb7bef90d5ce1cb00313c4a` |
| `certification/n3-20261015/schooling_parity_probe.py` | `2e4c0b1facc63a0f08971cad7be16b718b7104fd2dd1d14fa2f2a3465e56b45d` |
| `certification/n3-20261015/schooling_ui_check.mjs` | `282972ce1712a7672e8e1bf693975cd0e82e99d7021fe041f1b11331bb2231e4` |
| `certification/prestaging-20261016/staging-stack-live.json` | `95efa2e3e7d6727e8a09032f30ab8d083b934761ae848af33904019abd935c97` |
| `certification/prestaging-20261016/staging_stack_probe.py` | `4435b930ed58f404701d7cf8746107ffa65cdff204d8b46fa408bf56d50dc6aa` |

Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.
