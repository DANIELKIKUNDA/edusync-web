# Certification locale Point 17 — état intermédiaire

## Mise à jour du 17 septembre 2026

**Certification globale NON acquise.** Les sections suivantes datées du 16 septembre sont le diagnostic initial ; les résultats ci-dessous les actualisent.

| Contrôle | Résultat obtenu |
|---|---|
| Frontend | PASS : sept versions `latest` résolues sur npm, versions fixées et lockfile généré ; `npm ci --offline --no-audit` puis build TypeScript/Vite réussis |
| Backend | PASS : suite complète rejouée après les dernières corrections, 450 tests en 57,07 s, deux avertissements de dépréciation ; voir `backend-tests-current.xml`. Compileall et pip check initialement réussis |
| SQL réel | PASS : 39 migrations initiales appliquées ; provisioner exécuté ensuite avec les correctifs 0037 et 0038 |
| G1 PostgreSQL | PASS observé au terminal : huit contrôles, privilèges restreints, isolation, refus d'écriture croisée, concurrence CAS et idempotence |
| G3 Finance | PASS observé au terminal : `G3_MULTI_CASHIER_POSTGRES_PASS` |
| G1 API | PASS observé au terminal : authentification, création concurrente, rejeu idempotent, conflit de payload, bootstrap, refus plateforme depuis école et suspension |
| Redis Windows → WSL | PASS : PING authentifié depuis Python Windows vers Redis de recette sur 16379 |
| HTTP écoles A/B | PASS : `live-http.json` ; consultations Paramètres/Scolarité/Personnel/Imports, refus de modification de l'année de l'autre école, refresh/logout/refresh refusé |
| Connexion responsive | PASS dans Edge aux largeurs 320/360/390/430/768/1440 ; captures et `browser-login.json` |
| Atelier Pro | FAIL : voir `platform-http.json` et les défauts ci-dessous |

Corrections reproduites : erreurs TypeScript bloquant le build ; migration 0036 oubliée ; `%I` SQL interprété comme paramètre psycopg ; fonction RLS inexistante dans les migrations d'import remplacée par le contexte scolaire existant ; portée RBAC racine NULL interdite par l'ancienne clé primaire (migration 0037) ; bootstrap INSERT-only incompatible avec ON CONFLICT (0038) ; paramètres SQL optionnels non typés ; assertion de stockage incompatible avec la recherche insensible à la casse Windows ; capacité attendue par la probe G1 devenue obsolète.

Le refus SQL sur les tables d'import a été reproduit par HTTP 500. Le provisioner attribue maintenant SELECT/INSERT/UPDATE aux six tables de staging et SELECT/INSERT au ledger historique, sans ajouter DELETE. Les consultations HTTP A/B passent après correction. Un rôle personnalisé de recette autorise ces tests ; les rôles métier standards n'ont pas été enrichis arbitrairement. RLS et FORCE RLS restent actifs.

Défauts encore ouverts : la liste Atelier Pro compte six adhésions pour un utilisateur possédant six rôles, au lieu d'une. Diagnostics et notifications système renvoient 500, avec droits SQL manquants sur `communication_deliveries` et `platform_system_notifications`. Le détail école renvoie 500, avec colonne `active` ambiguë. Dashboard, accès et audit répondent 200. Ces défauts ne sont pas déclarés corrigés.

Incident local : PostgreSQL de recette s'est arrêté anormalement à 12:20 le 17 septembre (cause externe exacte non établie). Reprise à 13:58 et récupération automatique terminée, sans reset ni suppression. Les probes HTTP ont ensuite été rejouées. Le service PostgreSQL préexistant sur 5432 et le Desktop sont restés intacts ; Docker n'a pas été lancé.

Restent à tester : workers/retries/leases/reprise ; imports complets XLSX ; BOLA métier complet avec suppressions et exports ; cycle Collaborateur plateforme ; révocation individuelle, changement de mot de passe et jetons invalides ; modules authentifiés aux six largeurs et PWA ; sécurité dynamique ; performance PostgreSQL représentative et parité Desktop. Les captures de connexion et l'isolation des années ne couvrent pas ces gates. Téléphone/impression physiques et VPS/SMS restent non certifiés.

## Diagnostic initial conservé

Date : 16 septembre 2026. Ce rapport ne constitue pas une certification globale.

## Diagnostic initial

- Projet réel : `E:\edusyncweb`. Le chemin `E:\edusycweb` indiqué dans la reprise n'existe pas.
- Aucun dépôt `.git` présent ; `git status` échoue avec « not a git repository ».
- Version frontend/API : `0.52.0-point17-environment-closure`. Backend Python : `0.52.0`.
- Architecture : React/TypeScript/Vite/PWA ; FastAPI, monolithe modulaire avec domaines, ports et adaptateurs ; PostgreSQL durable et Redis éphémère.
- Scripts npm existants : `dev`, `build`, `preview`. Aucun script `test`.
- Sept dépendances frontend `latest`, aucun lockfile ni node_modules au départ.
- 39 fichiers SQL, dont plusieurs préfixes numériques partagés. Le provisioner omettait 0036.
- Node `24.19.0`, npm `10.8.2`, Python `3.13.14`, Git `2.51.0.windows.1`, PostgreSQL `16.11`.
- `npm.ps1` est bloqué par la politique PowerShell : utilisation de `npm.cmd`, sans modification de cette politique.
- Le lanceur `py` ne trouve aucun Python ; l'exécutable `python` fonctionne.
- Docker CLI `29.2.1`, Compose `5.1.0` ; Docker Desktop non démarré.
- Ubuntu-22.04 sous WSL2, Redis `6.0.16` déjà installé. Redis arrêté au début ; démarrage direct avec son compte redis, car le bus systemd est indisponible.
- Service PostgreSQL Windows existant actif sur 5432. Authentification administrative indisponible sans mot de passe ; aucune modification de ce service ni de ses bases.
- Instance de recette indépendante initialisée avec les binaires PostgreSQL installés, sous `.local/postgres-certification`, port 55432, écoute 127.0.0.1, shared_buffers 32 Mo, max_connections 20.
- Base isolée : `edusync_certification`. Secrets générés sous `.local`, exclus via `.gitignore` ; aucun secret affiché.
- Desktop local identifié : `E:\edusync`. Aucun fichier Desktop modifié. Parité documentaire non certifiée.

## Premières preuves

| Contrôle | Résultat réel |
|---|---|
| Baseline Point 17 présente | PASS |
| Couverture migrations avant correction | FAIL : `0036_platform_collaborator_role.sql` absente |
| Couverture migrations après correction | PASS : 39 fichiers référencés dans l'ordre |
| `python -m compileall -q backend/src` | PASS, code retour 0 |
| `node frontend/verify-offline-hash.mjs` | PASS : `OFFLINE_FINANCE_HASH_VECTOR_PASS` |
| Redis WSL `redis-cli ping` après démarrage | PASS : `PONG` |
| Résolution npm réelle | PASS pour les sept dépendances latest |
| Installation/build frontend | En cours, aucun PASS déclaré |
| Installation backend | Première tentative FAIL réseau ; nouvelle tentative en cours |
| Suite backend | Non exécutée à ce stade |
| Provisioning SQL réel | Non exécuté à ce stade |
| HTTP multi-tenant, sessions, workers, mobile, performance | Non exécutés à ce stade |

## Correction reproduite

`backend/scripts/provision_database.py` inclut maintenant la migration 0036 après 0035. Le test `test_fresh_database_provisioner_applies_every_current_migration` inventorie les fichiers SQL réels au lieu d'une liste figée arrêtée à 0032. Aucun contrôle RLS ni permission métier n'est désactivé.

## Configuration locale

La configuration privée est dans `.local/certification.env`. Le lanceur `run_local.py` charge cette configuration sans afficher les secrets et utilise `.venv`. Il est réservé à l'instance de recette isolée. Ne pas publier `.local`.

Les gates physiques (téléphone, impression), VPS/SMS et les documents `DESKTOP_GOLDEN_REQUIRED` restent ouverts tant que leurs preuves réelles ne sont pas obtenues.
