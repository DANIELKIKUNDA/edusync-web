# WEB-0D — Gates Finance Offline

## Gate local exécuté

| Contrôle | Verdict |
|---|---|
| Pytest backend | PASS — 79/79 |
| Compilation Python | PASS |
| Migration 0004 — contrats statiques | PASS |
| CASH only | PASS |
| Lease exclusif single-writer | PASS statique/unitaire |
| Reçus préalloués / unicité | PASS statique/unitaire |
| Journal seq + SHA-256 | PASS unitaire |
| Vecteur Python ↔ JavaScript | PASS |
| TypeScript `financeJournal.ts` strict | PASS |
| Snapshot + anti-surallocation cumulée | PASS unitaire |
| Replay exact → zéro deuxième posting | PASS unitaire |
| Plafonds count/CDF/USD | PASS unitaire |
| RLS/FORCE RLS nouvelles tables | PASS statique |
| Transitions immutables DB | PASS statique |
| Audit automatique lease/protocole | PASS statique |
| Production flag sans certification | PASS — refus explicite |

## G2-A — PostgreSQL protocol live

Script : `backend/scripts/g2_offline_finance_protocol_probe.py` ou `RUN_G2_WINDOWS.ps1`.

Doit prouver sur PostgreSQL réel : création PREPARING, deuxième lease refusé, snapshot, activation, RLS école A/B, write guard, reçus uniques, replay exact, clôture refusée avec opération RECEIVED, passage DRAINING/CLOSED, VOID des reçus inutilisés et rollback propre du probe.

**État actuel : READY TO EXECUTE — pas déclaré PASS dans cet environnement.**

## G2-B — Finance ledger integration

À fermer lorsque le domaine Finance Web canonique est porté. Doit prouver, dans une transaction PostgreSQL unique :

1. `assert_finance_writer_allowed` ;
2. `FOR UPDATE` des charges concernées ;
3. recomputation du solde réel ;
4. exact allocations ;
5. création d'un seul `payment` ;
6. conservation du `receipt_no` préalloué ;
7. une seule entrée de caisse réelle ;
8. audit append-only ;
9. outbox transactionnelle ;
10. inbox `APPLIED` + reçu token `CONSUMED` ;
11. retry/replay sans deuxième effet ;
12. conflit/erreur = rollback total.

Scénarios obligatoires : double-submit, timeout après commit, 2 writers concurrents, paiement partiel répété, deux paiements cumulés sur même charge, CDF/USD, reçu réimprimé, coupure durant sync, appareil redémarré, local_stop_at dépassé, force-release incident.

**État actuel : WAITING FOR CANONICAL WEB FINANCE PORT.**

## Verdict global

`OFFLINE_FINANCE_PROTOCOL_LOCAL_PASS`  
`G2_A_LIVE_PENDING`  
`G2_B_LEDGER_PENDING`  
`PRODUCTION_FEATURE_FLAG_OFF`
