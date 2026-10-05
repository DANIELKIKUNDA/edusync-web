# Certification EduSync Web — rapport Claude

**Période** : 30 septembre → 5 octobre 2026
**Certificateur / ingénieur de correction** : Claude (Opus 5.5), mandat de Daniel KIKUNDA
**Dépôt** : https://github.com/DANIELKIKUNDA/edusync-web (privé)
**Principe appliqué** : Git, tests, base réelle et comportement observable font foi. Les rapports antérieurs (Codex) ont servi de contexte, jamais de preuve. Aucun PASS n'est déclaré sans exécution réelle.

> Statut global : **certifiable en pré-production locale**, avec **3 écarts fonctionnels à décider par le propriétaire** et des **gates externes** (VPS, téléphone physique, impression, SMS, golden masters Desktop) listés en §29.

---

## 1. Commit de départ

Le dossier `E:\edusyncweb` **n'était pas un dépôt Git** (`fatal: not a git repository`). À défaut de SHA, l'état initial a été figé par une empreinte SHA-256 de 603 fichiers (hors `.venv`, `.local`, `node_modules`, `dist`, caches), manifeste conservé hors dépôt (`baseline.sha256`, empreinte du manifeste `560aae03…4652bf`).

Le dépôt Git a été créé pendant la mission (`git init`, branche `main`) puis poussé :

| Commit | Contenu |
|---|---|
| `54e8346` | Base Codex importée + corrections D1–D20 + gouvernance des accès (API + écran) |
| `fd517c1` | Gouvernance des accès vérifiée en réel, finitions UI |
| `dbe7fbc` | Parcours utilisateurs réels, Intendance rendue opérationnelle |
| `b0265d2` | D21–D22, U10, relecture finale sur base neuve, rapport de certification |

## 2. État initial du working tree

- Pas de Git ; aucun historique exploitable.
- Travail Codex **non documenté** présent : migrations `0039_platform_supervision_read`, `0040_finance_view_invoker` (postérieures à son rapport), `communications/worker.py` modifié après sa dernière suite de tests (test statique devenu obsolète).
- Environnement de recette Codex dans `.local/` (instance PostgreSQL isolée, secrets) — **exclu de Git**, jamais publié.
- Rapport Codex « Point 17 » : certification globale **non acquise**, 3 défauts Atelier Pro ouverts.

## 3. Environnement utilisé

| Élément | Valeur |
|---|---|
| OS | Windows 11 Pro 10.0.22631 |
| PostgreSQL | 16.11, **instance de recette isolée** (port 55432, 127.0.0.1) — le service du port 5432 n'a **jamais** été modifié |
| Redis | 6.0.16 (WSL Ubuntu 22.04), authentifié, port 16380 |
| Navigateur | Microsoft Edge headless, profil isolé, piloté par CDP |
| Bases | `edusync_claude_fresh` (installation neuve), `edusync_claude_perf` (volumétrie) |

## 4. Versions importantes

Python 3.13.14 · FastAPI 0.141.1 · Starlette 1.6.0 · SQLAlchemy 2.0.54 · psycopg 3.3.5 · Pydantic 2.13.5 · PyJWT 2.14.0 · redis-py 8.1.0 · pytest 9.1.1 · Node 24.19.0 · npm 10.8.2 · React 19.3.0 · Vite 8.3.0 · TypeScript 7.0.2.

## 5. Commandes exécutées (principales)

```text
# backend
PYTHONPATH=src python -m pytest -q --basetemp=<scratch>         # suite complète
PYTHONPATH=src python -m compileall -q src tests
# base neuve
python backend/scripts/provision_database.py                    # 44 migrations
python backend/scripts/bootstrap_platform_admin.py
# frontend
npm ci --offline --no-audit && npm run build                    # tsc -b + vite build
# preuves live (API + PostgreSQL réels)
python certification/claude-20260930/<probe>.py                 # 15 probes
node   certification/claude-20260930/browser_probe.mjs          # 112 écrans
node   certification/claude-20260930/journey_<role>.mjs         # 5 parcours UI
# historiques Codex rejoués
python backend/scripts/g1_live_certification.py | g1_api_probe.py | g2_offline_finance_protocol_probe.py | g3_multi_cashier_probe.py
```

Toutes les probes s'exécutent via un lanceur qui charge `.local/certification.env` sans afficher de secret, et **refusent de tourner hors de l'instance isolée** (assertion `@127.0.0.1:55432`).

## 6. Tests exécutés

| Famille | Nombre | Résultat |
|---|---|---|
| pytest backend (unitaires + contrats statiques) | 488 | **488 PASS** (départ : 449 PASS, 1 FAIL, 1 ERROR) |
| Probes live API + PostgreSQL (base neuve) | ~250 contrôles | voir §7 |
| Balayage BOLA de toute l'API | ~3 230 requêtes | 0 fuite |
| Balayage GET de toute l'API | 101 routes | 0 erreur 500 |
| Navigateur, build de production, 7 largeurs × 2 rôles | 112 écrans | 0 défaut (après correction U10) |
| Parcours utilisateurs réels (clics/saisie) | 5 rôles, 51 étapes | 51/51 |
| Historiques Codex | G1 DB 8/8, G1 API, G2, G3 | PASS |

> Important : **pytest ne touche aucune base réelle** (tests unitaires et contrats statiques). Les preuves PostgreSQL/HTTP sont les probes live.

## 7. Résultats exacts (preuves live, `certification/claude-20260930/*.json`)

Relecture finale du 5 octobre 2026 sur une **base neuve** (suppression → 45 migrations → amorçage → toutes les probes), code final. Seul incident : Redis (WSL) s'était arrêté avec la mise en veille de WSL ; sessions et workers ont été rejoués après redémarrage de Redis, les autres probes n'ont pas été relancées.


| Preuve | Résultat |
|---|---|
| Finance (encaissement, rejeu, devises, IDOR, 2 caissiers concurrents, intégrité ledger) | 26/26 |
| D11 (pas d'encaissement de ce qui est réglé/exonéré, garde-fou base) | 8/8 |
| A/B adaptateur d'encaissement : ancien / corrigé | 0/3 → 3/3 |
| Imports (contrats, falsifications, limites, staging, rejeu, concurrence, double analyse, hors caisse, isolation) | 25/25 |
| Personnel & accès (sortie d'agent → accès révoqué, bornes RLS) | 10/10 |
| Décision rôles Personnel (02/10) | 7/7 |
| Sessions & JWT (forgé, alg=none, expiré, audience, révocation, mot de passe, brute force, timing) | 30/30 |
| Atelier Pro & Collaborateur plateforme | 29/29 |
| Workers & Redis (panne Redis, crash pendant bail, concurrence, dead-letter, SMS) | 14/14 |
| Sécurité HTTP (en-têtes, CORS, Host, limites, chunked, SQLi, XSS, formules Excel, mass assignment, fuites d'erreur) | 26/26 |
| Recouvrement (synthèses, registre de classe, exports PDF/XLSX, réconciliation au centime) | 19/19 |
| Gouvernance des accès par l'école | 24/24 |
| Intendance (stock, concurrence, rejeu, inventaire, immutabilité) | 13/13 |
| Balayage BOLA inter-écoles / balayage GET (aucune 500) | 2/2 · 1/1 |
| Historiques Codex G1 DB · G1 API · G2 offline V2 · G3 multi-caissier | 8/8 · PASS · PASS · PASS |
| Volumétrie : pagination du suivi des frais (base 72 000 élèves) | 8/8 |
| Volumétrie : charge 8 utilisateurs + 4 caissiers (§19) | 10/10 |
| Proxy : IP réelle derrière nginx (avant / après) | 1/2 → 2/2 |

## 8. Migrations testées

Installation fraîche **base vide → 45 migrations → démarrage** : PASS, rejouée à chaque cycle (≈ 12–50 s selon la charge machine).

Migrations ajoutées pendant la certification (toutes intégrées au provisioner, ordre vérifié par test) :

| Migration | Objet |
|---|---|
| `0041_finance_tenant_grants` | Droits minimaux du rôle tenant sur le ledger Finance ; paiements et allocations **append-only** ; `UPDATE` de `finance_charges` limité à `paid_amount, updated_at` |
| `0042_tenant_membership_deactivation` | Le rôle tenant peut **seulement désactiver** une adhésion de son école (politique RESTRICTIVE) |
| `0043_finance_charge_capacity_guard` | Trigger : argent reçu (caisse + hors caisse) ≤ obligation nette, quel que soit le code appelant |
| `0044_owner_decision_personnel_roles` | Décision propriétaire du 02/10 (Gestionnaire / Secrétariat) |
| `0045_finance_read_model_performance` | Vue canonique `finance_charge_effective` : exonérations et régularisations agrégées **une seule fois** (mêmes colonnes, même ordre, + `outside_cash_amount`), toujours `security_invoker` ; 4 index de recherche par frais / session de caisse |

## 9. Couverture RLS

Base neuve : **102 tables**, **88 avec `school_id`** → **88/88 avec RLS ET FORCE RLS**, toutes avec politiques ; **0 fonction SECURITY DEFINER** ; la vue `finance_charge_effective` est `security_invoker` (correctif Codex 0040 vérifié). Le rôle tenant ne lit que sa propre ligne dans `users` (confidentialité conservée).

## 10. Tests inter-tenant

- Deux puis trois écoles réelles créées par l'API plateforme.
- **Balayage BOLA automatique** : chaque route GET paramétrée (≈ 1 500 requêtes) et chaque route d'écriture (≈ 1 700 requêtes) rejouées par l'école B avec les identifiants réels de l'école A → **aucune donnée de A renvoyée, aucune modification de A**.
- Tentatives ciblées : solde, encaissement, recherche, famille, lots d'import, rapports de contrôle, sessions, rôles, attributions → refus ou résultat vide.
- JWT **validement signé** pointant vers l'école B → refusé (l'appartenance est revérifiée en base à chaque requête).

## 11. Finance

Doctrine vérifiée en réel : caisse personnelle, encaissement idempotent, CDF/USD séparés, séquençage des mensualités, reçu distinct du commit, aucune correction silencieuse.
Corrigé : D1, D2, D3, D4, D10, D11, D16 (voir §20). Le guichet calcule désormais le reste dû comme la vue canonique (net − exonérations − régularisations hors caisse − payé) et la base l'impose par trigger.

## 12. Multi-caissier

- 2 caissiers sur le même frais en parallèle : un seul encaissement complet, l'autre refusé proprement, **pas de sur-allocation**.
- Même `Idempotency-Key` envoyée 3 fois en parallèle : **1 paiement, 3 réponses identiques**.
- G3 Codex (multi-caissier PostgreSQL) : PASS.

## 13. Imports

Modèle officiel → analyse → staging → confirmation → import, vérifié pour élèves, personnel, historique financier : colonne renommée / supprimée / ajoutée, feuille de contrat retirée, mauvais contrat, non-XLSX, > 10 Mio, > 5 000 lignes, fichier corrompu → refus propres ; exécution concurrente → 1 seul import ; historique financier **sans aucun mouvement de caisse ni reçu**.
Corrigé : D9 (doublons via double analyse), D10 (sur-régularisation).

## 14. Sessions / JWT

Jeton court + session appareil opaque (cookie HttpOnly, SameSite=Lax, chemin limité). Vérifié : signature forgée, `alg=none`, expiré, mauvaise audience, mauvais type, déconnexion, révocation d'un appareil, changement de mot de passe, désactivation, retrait de rôle immédiat, verrouillage après 7 échecs.
Corrigé : D6 (jeton encore valide après déconnexion), D7, D8, D13.

## 15. Redis / outbox / workers

Outbox transactionnelle PostgreSQL ; Redis = transport. Vérifié en réel : panne Redis (événement conservé, backoff), crash pendant le bail puis reprise, acquittement tardif sans corruption, 4 workers concurrents sans double publication, dead-letter, SMS envoyé seulement avec preuve fournisseur, aucun verrou SQL pendant l'appel fournisseur.
Corrigé : D12 (file Redis non bornée), journalisation des erreurs des workers.
Non déployé : aucun service worker dans `docker-compose.yml` (voir §28).

## 16. Offline / sync

Finance hors-ligne **désactivée par défaut** et sans route HTTP montée (doctrine respectée). Protocole V2 multi-caissier vérifié sur PostgreSQL réel : **G2 PASS** (l'assertion Codex visait le message du protocole V1, alignée). Vecteur de hachage du journal offline : PASS.

## 17. Sécurité

En-têtes (nosniff, anti-clickjacking, Referrer-Policy, `no-store`), CORS strict, TrustedHost, limites de corps (y compris *chunked*) et de query string, Content-Length invalide, injection SQL (dont tentatives temporelles) sur 4 recherches, XSS stocké (React n'injecte jamais de HTML), affectation de masse, erreurs sans pile technique, en-tête `Server` masqué, journal d'audit *append-only*.
Corrigé : D5, D6, D8, D13, D14 (injection de formules Excel), D15 (IP réelle derrière le proxy).

## 18. Frontend

Build de production : `tsc -b` 0 erreur, `vite build` OK, modules chargés à la demande. Jeton d'accès **en mémoire seulement**.
Probe navigateur (build de production, 320 → 1440 px, 2 rôles) : **112 écrans, 0 débordement, 0 cible tactile < 40 px, 0 champ < 16 px sur mobile, 0 champ sans nom accessible, 0 exception JS, 0 erreur serveur**. (126 écrans au passage précédent : le compte caissier de test portait alors encore un rôle d'administrateur par erreur de fixture ; il ne voit plus, à juste titre, ni « Personnel » ni « Accès & rôles ».)
Suivi des frais : le détail nominatif s'affiche par pages de 200 lignes avec « Afficher plus » (D22).
Fixture du parcours caissier durcie : un frais partiellement payé lors d'un passage précédent portait le même libellé que le nouveau, ce qui rendait la lecture du reste dû ambiguë (vérifié en base : chaque paiement est allé sur le frais cliqué, aucune sur-allocation).
Parcours réels : caissier 18/18 (ordinateur + téléphone), inscription 8/8, gestionnaire 7/7, intendant 9/9, administrateur des accès 9/9, promoteur vérifié.

## 19. Performance

Base de volumétrie dédiée (`edusync_claude_perf`, jamais la base de production) : **72 006 élèves inscrits, 792 010 frais**, dont une école de **12 003 élèves / 132 000 frais** (classe la plus grande : 439 élèves). Générateur de charge : threads Python + httpx, **8 clients simultanés**, 80 requêtes par écran (k6 non installé). Machine : poste Windows de développement, PostgreSQL 16 avec réglages par défaut (`shared_buffers` 128 Mo) — les valeurs absolues seront **meilleures sur un serveur**, seuls les rapports avant/après comptent ici.

**Diagnostic (mesuré, pas supposé)** — `EXPLAIN ANALYZE` exécuté sur le code réel, sous le rôle tenant avec RLS (`explain-hotspots-before.json` / `-after.json`) : chaque écran de recouvrement recalculait les exonérations (deux fois) et les régularisations **pour chaque frais : 120 004 sous-requêtes par écran**. Correctif D21 (migration 0045) : agrégation unique. Correctif D22 : pagination serveur du détail nominatif.

**Exactitude** — les 4 écrans lourds ont été capturés avant et après sur la même base : **empreintes SHA-256 identiques** (résultats égaux au centime), `readmodel-before.json` / `readmodel-after.json`. Pagination : 12 003 lignes relues en 13 pages, **0 perte, 0 doublon, égales au centime** (`fee-paging-checks.json`, 8/8).

| Écran (8 utilisateurs simultanés) | Avant p50 | Après p50 | Après p95 | Erreurs |
|---|---|---|---|---|
| Suivi des frais par élève | 50,9 s | **4,4 s** (page de 200) | 6,1 s | 0 |
| Recouvrement mensuel | 44,9 s | **4,6 s** | 5,6 s | 0 |
| Synthèse école | 20,7 s | **3,3 s** | 4,7 s | 0 |
| Registre de la plus grande classe | 6,2 s **avec erreurs 500** | **4,4 s** | 5,7 s | **0** (avant : 3/64) |
| Recherche au guichet | 1,5 s | 0,65 s | 0,9 s | 0 |
| Solde d'un élève | 225 ms | 163 ms | 470 ms | 0 |
| Caisse courante | 632 ms | 422 ms | 619 ms | 0 |
| Identité + droits (`auth/me`) | 222 ms | 73 ms | 658 ms | 0 |
| **4 caissiers encaissant en parallèle** | 3,6 paiements/s | **7,3 paiements/s** (p50 316 ms) | 770 ms | 0 — ledger cohérent 100/100 |

Requête SQL seule, un utilisateur, statistiques à jour (médiane de 3) : mensuel 1,2 s · synthèse 0,8 s · registre 0,4 s · suivi complet 2,0 s (contre 10,3 / 4,1 / 0,5 / 11,6 s). `work_mem` porté à 32 Mo : **aucun gain mesurable**, configuration PostgreSQL laissée par défaut.

Verdict perf : `perf-checks.json` **10/10 PASS** (avant : 9/10). Constat d'exploitation : après un arrêt brutal, PostgreSQL perd ses statistiques de planification ; l'`autovacuum` les reconstruit, mais un `ANALYZE` manuel après restauration est recommandé (procédure d'exploitation, §28).
Limite honnête : les écrans d'analyse restent à quelques secondes pour 12 000 élèves sous 8 utilisateurs simultanés sur ce poste ; à remesurer avec k6 sur le serveur cible avant d'annoncer un objectif de temps de réponse.

## 20. Défauts trouvés

| # | Domaine | Défaut (reproduit en réel) | Gravité |
|---|---|---|---|
| D1 | Finance | Installation neuve : caisse et encaissement en HTTP 500 (droits SQL absents) | Bloquant |
| D2 | Finance | Un élève devant CDF **et** USD ne pouvait jamais payer | Majeur |
| D3 | Finance | Même clé d'idempotence en parallèle → 500 | Majeur |
| D4 | Finance | Clé réutilisée avec un autre montant → ancien reçu renvoyé en silence | Majeur |
| D5 | Sécurité | Sortie d'un agent impossible → **l'agent gardait son accès** | Critique |
| D6 | Sécurité | Jeton encore valide après déconnexion / révocation d'appareil | Majeur |
| D7 | API | Révocation de session avec identifiant invalide → 500 | Mineur |
| D8 | Sécurité | Connexion réussie remettait à zéro le compteur anti-brute-force par IP | Majeur |
| D9 | Imports | Même fichier analysé deux fois → élèves créés en double | Majeur |
| D10 | Finance | Deux reprises historiques → 100 000 régularisés sur un frais de 50 000 | Critique |
| D11 | Finance | **Double encaissement** d'un frais déjà réglé hors caisse ou exonéré | Critique |
| D12 | Exploitation | File Redis de l'outbox sans consommateur ni borne | Majeur |
| D13 | Sécurité | Énumération des comptes par temps de réponse | Moyen |
| D14 | Sécurité | Injection de formules dans les exports Excel (CWE-1236) | Majeur |
| D15 | Sécurité | Derrière nginx, tous les utilisateurs partageaient la même IP → blocage global | Majeur |
| D16 | Finance | Synthèses de recouvrement et registre de classe en 500 permanent | Majeur |
| D17 | Personnel | Historique global du personnel en 500 | Moyen |
| D18 | Intendance | Mouvement de stock rejoué → appliqué deux fois | Majeur |
| D19 | Intendance | Validation d'inventaire effaçait les mouvements intermédiaires (registre ≠ stock) | Critique |
| D20 | Intendance | Inventaire validé encore modifiable | Majeur |
| D21 | Performance | Écrans de recouvrement et suivi des frais : sommes recalculées **une fois par frais** (120 004 fois par écran) → 20 à 50 s sous charge, erreurs 500 sur le registre de classe | Majeur |
| D22 | Performance / UI | Suivi des frais : toute l'école renvoyée d'un coup (12 003 lignes, 4 Mo), paramètre `limit` ignoré | Majeur |
| U1 | UI | Menu latéral tronqué (« Acc », « Par »…) | Visible |
| U2 | UI | Sélecteur d'année vide pour les rôles non administrateurs | Majeur |
| U3 | UI | **Le caissier ne pouvait pas inscrire** (403 sur les classes, compteurs à 0) | Bloquant |
| U4 | UI | **Intendance en lecture seule** : aucune saisie possible | Bloquant |
| U5 | UI | Jargon technique et codes anglais à l'écran | Visible |
| U6 | UI | Champ de montant débordant sur téléphone ; reçu masqué | Moyen |
| U7 | UI | Panne réseau présentée comme « identifiants incorrects » | Moyen |
| U8 | Accessibilité | Champs et boutons sans nom accessible | Moyen |
| U9 | UI | Icônes émoji, boutons sans style, chevauchement d'étapes | Visible |
| U10 | Accessibilité | 3 champs (recherche au guichet, recherche et filtre de documents) annoncés seulement par leur texte indicatif | Moyen |

## 21. Corrections effectuées

Chaque défaut a été : reproduit → cause racine identifiée → corrigé au plus juste → test de régression ajouté → test ciblé → suite complète. Les défauts D2–D4 ont en plus une preuve A/B (ancien code 0/3, code corrigé 3/3 sur la même base). Aucun contournement de RLS, aucune règle Finance affaiblie : les corrections **ajoutent** des contraintes (append-only, trigger de capacité, politique RESTRICTIVE).

## 22. Fichiers modifiés (principaux)

- Backend : `adapters/postgres_finance_checkout.py`, `adapters/postgres_finance_recovery.py`, `adapters/postgres_fee_tracking.py`, `modules/finance_fee_tracking/api/router.py`, `adapters/postgres_personnel.py`, `bootstrap/app.py`, `bootstrap/dependencies.py`, `modules/iam/api/router.py`, `modules/migration_import/api/router.py`, `modules/stewardship/api/router.py`, `modules/settings/api/router.py`, `modules/finance_checkout/api/router.py`, `modules/sync/outbox_worker.py`, `modules/communications/worker.py`, `shared/infrastructure/login_guard.py`, `shared/infrastructure/xlsx_safety.py` (nouveau), `modules/access/` (nouveau), exports XLSX (5 modules).
- Migrations : 0041 → 0045 ; `scripts/provision_database.py`.
- Déploiement : `backend/Dockerfile`, `docker-compose.yml`, `.env.example`.
- Frontend : `App.tsx`, `api.ts`, `login.tsx`, `finance.tsx`, `documents.tsx`, `home.tsx`, `schooling.tsx`, `personnel.tsx`, `stewardship.tsx` (réécrit), `access.tsx` (nouveau), `platform/nav_icons.tsx` (nouveau), `styles.css`, `access.css`, `stewardship.css`.
- Liste exacte : `git show --stat` sur les commits du §1.

## 23. Tests de régression ajoutés

`backend/tests/test_claude_certification_20260930.py` : D1–D22, U10, gouvernance des accès, décision Personnel (unitaires avec connexion simulée + contrats SQL/sources). Trois tests historiques ajustés **sans affaiblir leur intention** (formulations UI réécrites, sélecteur d'année, constante du worker), chacun commenté.

## 24. Gates PASS

**19 gates PASS**, chacun prouvé par exécution réelle (§7) : installation fraîche · migrations (45) · RLS/FORCE RLS · isolation inter-tenant (BOLA) · Finance · multi-caissier · imports · Personnel (sortie, rôles) · Intendance · sessions/JWT · Redis/outbox/workers · protocole offline V2 · sécurité applicative locale · gouvernance des accès · build frontend · responsive 320→1440 · accessibilité de base · parcours réels de 5 rôles · performance à volumétrie (locale).

## 25. Gates FAIL

**0 gate FAIL.** Aucun FAIL local non corrigé. Les **écarts fonctionnels** ci-dessous ne sont pas des bugs mais des fonctionnalités absentes nécessitant une décision (§28).

## 26. Gates BLOCKED (environnement)

**6 gates BLOCKED** : Téléphone physique · impression réelle · Docker/VPS/HTTPS réel · SMS fournisseur réel · golden masters Desktop (`DESKTOP_GOLDEN_REQUIRED`) · k6 (non installé, charge mesurée par générateur Python).

## 27. Gates NOT APPLICABLE

**1 gate NOT APPLICABLE** : Finance hors-ligne en production (désactivée par doctrine tant que non certifiée sur appareils réels).

## 28. Risques résiduels et décisions attendues

1. **Génération des frais dus absente** : aucun code ne crée les obligations (`finance_charges`) à partir des tarifs. Les tests utilisent des frais de fixture. **Décision métier requise** (règles par classe/section, mensualités, exonérations).
2. **Aucune livraison SMS n'est créée** à partir d'un message : décider des destinataires (responsables, numéros, dédoublonnage, consentement, coût).
3. **Workers non déployés** dans `docker-compose.yml` et exécutés avec les identifiants propriétaire : prévoir un rôle PostgreSQL dédié aux workers avant production.
4. Pas de limitation de débit générale de l'API (seule la connexion l'est) : à configurer sur le reverse proxy.
5. Rotation du cookie de session non implémentée (session longue durée par appareil, révocable).
6. Montant des décisions financières typé `float` côté API (à passer en `Decimal`).
7. Connexion à froid lente sur cette machine (≈ 4–5 s) : à remesurer sur le serveur cible.
8. Exploitation : lancer `ANALYZE` après toute restauration de sauvegarde ou arrêt brutal de PostgreSQL (statistiques de planification perdues, mesuré pendant la certification).

## 29. Actions nécessitant un environnement externe

Déploiement Docker/VPS avec HTTPS et nginx · test sur téléphones réels (Android/iOS) · impression des reçus et documents · fournisseur SMS réel · comparaison documentaire avec le Desktop · test de charge k6 sur l'infrastructure cible · **pilote d'une à deux écoles** (recommandé avant lancement).

## 30. Commit final

Commit de clôture sur `main`, poussé sur https://github.com/DANIELKIKUNDA/edusync-web (privé) : **`b0265d2`** (D21, D22, U10, relecture finale, rapport). Avant chaque commit, un contrôle automatique vérifie qu'aucun des 47 secrets réels de l'environnement de recette n'apparaît dans les fichiers versionnés : **0 fuite**. Le dossier `.local/` (instance PostgreSQL, mots de passe, jetons) n'est pas versionné.

---

## Synthèse

```
PASS            : 19 gates
FAIL            : 0
BLOCKED         : 6 (environnement externe)
NOT APPLICABLE  : 1 (finance hors-ligne, désactivée par doctrine)
Tests           : pytest 488/488 · ≈ 300 contrôles live (base neuve + volumétrie), tous PASS · BOLA 0 fuite · 0 erreur 500
Build           : tsc 0 erreur · vite build OK · 112 écrans 320→1440 px sans défaut
Migrations      : base vide → 45 migrations → démarrage : PASS (18 s)
RLS             : 88/88 tables d'école avec RLS + FORCE RLS · 0 SECURITY DEFINER · vue Finance security_invoker
Finance         : 26/26 + D11 8/8 · idempotence, devises, sur-allocation impossible (trigger) · ledger append-only
Imports         : 25/25 · aucun mouvement de caisse depuis une reprise historique
Sessions        : 30/30 · jeton lié à une session appareil révocable
Redis           : 14/14 · outbox PostgreSQL = vérité, Redis = transport, file bornée
Sécurité        : 26/26 HTTP · 22 défauts techniques + 10 défauts UI corrigés, chacun avec test de régression
Performance     : 72 006 élèves / 792 010 frais · recouvrement 44,9 s → 4,6 s · suivi des frais 50,9 s → 4,4 s
                  · 4 caissiers 7,3 paiements/s, ledger cohérent · résultats identiques au centime
```

**Reste à faire avant la production** (aucun n'est un bug ouvert) :
1. Décisions du propriétaire : génération des frais dus à partir des tarifs ; création des livraisons SMS ; rôle PostgreSQL dédié aux workers et leur déploiement.
2. Environnement réel : VPS Docker + HTTPS + nginx, test k6 sur ce serveur, téléphones Android/iOS, impression des reçus, fournisseur SMS, comparaison avec le Desktop.
3. Pilote dans une ou deux écoles avant le lancement général.
