# Gate — Point 2 Finance offline multi-caissier

## Verdict local

**PASS LOCAL — 99% READY / 1% LIVE CERTIFICATION**

## Obligations fermées dans l'environnement ChatGPT

- protocole courant = `AUTHORIZED_PARTITIONED_CASH_V2` ;
- plusieurs leases simultanés par école ;
- aucune exclusivité globale d'école ;
- autorité exclusive au niveau de la charge ;
- partition déterministe par élève, extensible à la famille ;
- index PostgreSQL anti-double-autorité ;
- advisory lock PostgreSQL par charge ;
- guard de mutation Finance par charge ;
- reçu unique préalloué par lease ;
- idempotence exact-once ;
- checkpoint de journal + sync incrémentale ;
- retry après timeout ;
- plafonds serveur + client ;
- CDF/USD séparés ;
- Web Locks local ;
- stockage persistant requis ;
- force release => quarantaine, pas réattribution silencieuse ;
- résolution de quarantaine auditée ;
- posting résiduel explicite si anomalie de solde ;
- aucune décision de rôle définitive prise au Point 2.

## Preuves locales exécutées

- Pytest : **100 PASS / 0 FAIL** ;
- compilation Python : PASS ;
- TypeScript strict ciblé Finance offline : PASS ;
- contrat de décisions Point 2 : PASS ;
- vecteur SHA-256 Python ↔ JavaScript : PASS ;
- tests de partition, retry, idempotence, cumul, autorité étrangère, crédit résiduel : PASS.

## 1% réservé à la machine de Daniel

`RUN_POINT2_WINDOWS.ps1` doit prouver sur PostgreSQL/Docker réels :

- migrations 0001→0005 ;
- RLS multi-école ;
- deux caissiers même école / charges différentes : PASS ;
- deux connexions concurrentes / même charge : un seul gagnant ;
- writer étranger sur charge réservée : bloqué ;
- charge non réservée : reste disponible ;
- hash frontend ;
- navigateur réel avec stockage persistant et Web Locks.

Le Point 2 n'active pas encore `EDUSYNC_OFFLINE_FINANCE_ENABLED=true` en production tant que l'adapter Finance canonique du Point 6 n'est pas raccordé et certifié.
