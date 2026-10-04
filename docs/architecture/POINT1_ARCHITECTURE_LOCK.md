# Point 1 — Architecture et doctrine offline verrouillées

**Statut : LOCKED / BASELINE OFFICIELLE**  
Date : 2026-09-11

Ce document ferme le point 1 de la feuille de route EduSync Web multi-école. Toute évolution ultérieure doit être compatible avec cette baseline ou faire l'objet d'une décision d'architecture explicite et versionnée.

## 1. Cible produit

EduSync est un SaaS scolaire **multi-école** déployé sur un **VPS distant**. Il n'exige aucun serveur local dans l'école. Une PWA permet l'usage navigateur/ordinateur/tablette/téléphone; des emballages Tauri/Capacitor restent possibles sans dupliquer le métier.

La plateforme reste distincte de la grande plateforme organisationnelle de Daniel. EduSync possède seulement un niveau supérieur **Atelier Pro** pour créer/administrer les écoles et opérer la plateforme.

## 2. Topologie verrouillée

```text
PWA React/TypeScript
  ├─ cache statique Service Worker
  ├─ IndexedDB tenant+user+device
  ├─ outbox locale durable
  └─ sync engine
          │ HTTPS
          ▼
Reverse proxy TLS (VPS)
          ▼
FastAPI — modular monolith
  ├─ DDD bounded contexts
  ├─ application/use cases
  ├─ ports hexagonaux
  └─ adapters
     ├─ PostgreSQL 16 = source de vérité
     ├─ Redis = cache/coordination éphémère
     ├─ stockage documents
     └─ notification providers
```

Aucun partage de fichier SQLite sur réseau et aucune base locale d'un poste n'est la vérité centrale du SaaS.

## 3. Architecture applicative

Architecture obligatoire : **DDD + Clean Architecture + Hexagonale**, sous forme de **monolithe modulaire** au départ. Aucun microservice n'est créé sans besoin mesuré.

Bounded contexts de référence : Platform/Atelier Pro, IAM, Scolarité, Élèves & Familles, Effectifs, Finance, Caisse, Documents, Audit, Sync, Notifications, puis Intendance. Le métier Desktop existant est l'oracle de préservation lors du portage.

Le domaine ne dépend ni de FastAPI, ni de PostgreSQL, ni de React. Les adapters implémentent les ports. Les transactions métier sont pilotées par la couche application/UoW.

## 4. Multi-école

- chaque donnée tenant porte `school_id` ou est rattachée à un agrégat qui l'impose;
- le client n'est jamais la source d'autorité du tenant;
- le serveur résout le membership et fixe le contexte PostgreSQL;
- RLS + `FORCE ROW LEVEL SECURITY` constitue une barrière de défense supplémentaire;
- les caches, clés Redis, IndexedDB, audit, outbox/inbox et documents sont namespacés par école;
- les tests A/B inter-écoles sont obligatoires pour chaque module.

## 5. Doctrine offline générale : disponibilité maximale sous autorité bornée

EduSync ne bloque pas les opérations courantes uniquement parce qu'Internet est instable. Une opération est classée selon la preuve nécessaire à sa finalité :

1. `CACHED_READ` — consultation locale autorisée avec fraîcheur visible;
2. `LOCAL_SYNCABLE_WRITE` — écriture locale durable puis synchronisation, avec version/conflit explicite;
3. `AUTHORIZED_CRITICAL_WRITE` — écriture critique finale offline uniquement avec préautorisation serveur bornée et preuve locale durable;
4. `ONLINE_EXTERNAL_PROOF_REQUIRED` — l'intention peut être capturée offline, mais la finalité attend une preuve d'un système externe;
5. `ONLINE_SECURITY_ADMIN_REQUIRED` — changement de pouvoir/tenant uniquement avec autorité serveur actuelle.

Une opération inconnue n'obtient jamais une autorisation offline implicite.

## 6. Doctrine Finance offline

**CASH doit pouvoir rester opérationnel malgré une coupure Internet.** La sécurité ne doit pas être obtenue en bloquant systématiquement le caissier.

Invariants : UUID client, idempotency key, identité école/utilisateur/appareil/caisse, stockage durable, journal d'intégrité, reçus uniques, allocations exactes, CDF/USD séparés, réconciliation, audit append-only et posting serveur atomique.

Le protocole `EXCLUSIVE_SINGLE_WRITER_CASH_V1` de WEB-0D est désormais considéré **transitoire**. La cible verrouillée est `AUTHORIZED_MULTI_WRITER_CASH_V2`, à implémenter au point 2.

En cas de paiements cash concurrents créés pendant une isolation totale entre appareils, le serveur ne doit jamais inventer un merge silencieux. À la synchronisation, il recalcule le grand livre. Le montant qui ne peut plus être alloué à la dette originale suit la doctrine financière existante de **crédit résiduel traçable**, sous contrôle métier, au lieu de créer un faux second règlement de la même obligation.

Mobile Money/Banque : une preuve/intention peut être enregistrée offline, mais la dette n'est déclarée définitivement soldée qu'après vérification externe.

## 7. Idempotence et concurrence

- `operation_id` et `Idempotency-Key` sont obligatoires pour les mutations syncables;
- inbox serveur persistante pour dédupliquer les retries;
- outbox transactionnelle côté serveur;
- outbox durable côté client;
- contraintes uniques PostgreSQL comme dernière barrière;
- `version`/CAS pour les agrégats mutables;
- `SELECT ... FOR UPDATE` ou verrou métier ciblé pour les écritures financières/stock lorsque nécessaire;
- aucune stratégie globale `last-write-wins`;
- aucune fusion automatique de deux écritures financières contradictoires;
- timeout après commit = replay de la même opération, pas nouvelle opération.

## 8. Cache

- Service Worker : assets publics/versionnés et shell PWA uniquement; jamais une réponse API authentifiée;
- IndexedDB : read-models et outbox scoped `school_id + user_id + device_id`;
- stockage persistant requis pour les écritures critiques offline;
- Redis : cache, rate-limit, signaux/coordination et tâches; **jamais source de vérité**;
- invalidation/versionnement explicites; les valeurs financières finales viennent du grand livre PostgreSQL.

## 9. Audit

Audit append-only, corrélé à l'opération métier. Pour une mutation sensible : école, utilisateur, rôle/permissions effectives au moment de l'action, appareil, operation_id, correlation_id, source ONLINE/OFFLINE/SYNC/SYSTEM, date client, date serveur, motif, entité et avant/après si pertinent.

Une correction crée un nouvel événement; elle ne réécrit pas l'historique.

## 10. Sécurité et déploiement

VPS Linux, containers, TLS obligatoire, secrets hors code, comptes PostgreSQL séparés owner/platform/tenant, migrations exécutées par un rôle privilégié one-shot, API avec rôle applicatif limité, JWT court + mécanisme de renouvellement à prévoir, sauvegardes chiffrées/versionnées et restauration testée.

Le mode offline ne constitue jamais une manière de contourner une permission. L'appareil conserve seulement une autorité bornée émise alors que l'utilisateur était autorisé.

## 11. Gate de fermeture du Point 1

Le point 1 est fermé lorsque :

- la topologie VPS est explicite;
- DDD/Clean/Hexagonale et modular monolith sont fixés;
- PostgreSQL/Redis/PWA sont positionnés sans ambiguïté;
- isolation multi-école est fixée;
- classes d'opérations offline sont codées/testées;
- doctrine cash offline autorisée sous préautorisation est fixée;
- single-writer V1 est marqué transitoire et multi-writer V2 est la cible du point 2;
- idempotence/concurrence/cache/audit sont des invariants non négociables;
- rôles définitifs ne sont **pas** décidés ici : ils appartiennent au point 3 et Daniel conserve la décision finale.

**Verdict : POINT_1_ARCHITECTURE_OFFLINE_DOCTRINE_LOCKED.**
