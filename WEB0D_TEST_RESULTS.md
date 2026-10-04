# WEB-0D — Résultats de validation locale

Date : 2026-09-11

## Résultats exécutés

- Pytest backend : **79 PASS / 0 FAIL / 0 SKIP**.
- Compilation Python (`src`, `tests`, `scripts`) : **PASS**.
- JSON + `docker-compose.yml` parse YAML : **PASS**.
- Service Worker `node --check` : **PASS**.
- TypeScript ciblé `frontend/src/offline/financeJournal.ts` en mode strict : **PASS**.
- Vecteur de hash Python ↔ JavaScript : **OFFLINE_FINANCE_HASH_VECTOR_PASS**.

## Preuves fonctionnelles couvertes localement

- CASH uniquement pour le mode offline définitif v1 ;
- lease exclusif single-writer par école ;
- reçus préalloués uniques ;
- operation_id + idempotency_key + receipt_no + journal_seq uniques ;
- hash-chain SHA-256 du journal local ;
- refus d'une séquence sautée ou d'un journal altéré ;
- plafonds nombre/CDF/USD ;
- aucune conversion FC/USD ;
- allocations exactes ;
- cumul de plusieurs paiements impossible au-delà du solde gelé d'une charge ;
- replay exact sans second effet métier dans le coordinator ;
- contexte école/utilisateur/appareil/session/lease vérifié ;
- stockage navigateur persistant obligatoire avant armement ;
- reçus et snapshots liés au lease ;
- clôture impossible si une opération reçue n'est pas appliquée ;
- feature flag production OFF tant que G2 n'est pas certifié.

## Limites de cette validation

Docker/PostgreSQL live n'est pas disponible dans cet environnement. Le probe `g2_offline_finance_protocol_probe.py` et les scripts `RUN_G2_WINDOWS.ps1` / `RUN_G2_LINUX.sh` restent à exécuter sur Docker Desktop ou staging VPS.

Le build React complet n'a pas été exécuté ici car les dépendances npm du frontend ne sont pas installées. Le fichier critique de caisse offline a toutefois été compilé isolément avec TypeScript strict.

Le **posting adapter Finance canonique** — charges → paiement → allocations → reçu → caisse → audit → outbox dans une seule transaction PostgreSQL — n'est pas simulé avant le portage du domaine Finance Web. Le protocole est prêt à le recevoir via `OfflinePaymentPostingPort`. En production, `EDUSYNC_OFFLINE_FINANCE_ENABLED` reste `false` tant que ce dernier gate n'est pas fermé.
