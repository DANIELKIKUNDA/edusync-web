# WEB-0D — Rapport d'implémentation Finance Offline Safe Mode

Date : 2026-09-11  
Cible : EduSync Web multi-école sur VPS distant  
Doctrine : DDD + Clean Architecture + Hexagonale + preservation-first

## 1. Problème traité

WEB-0B/WEB-0C conservaient volontairement les encaissements définitifs en mode fail-closed hors connexion. Le risque était physique et comptable : double clic/retry, deux caissiers sur une même dette, numéros de reçus concurrents, caisse divergente, paiement local perdu ou resynchronisé plusieurs fois.

WEB-0D remplace ce blocage global par un protocole borné et certifiable : `EXCLUSIVE_SINGLE_WRITER_CASH_V1`.

## 2. Lease exclusif

Une école ne peut avoir qu'un seul lease `PREPARING`, `ACTIVE` ou `DRAINING`. La contrainte est doublée : advisory lock applicatif + index unique partiel PostgreSQL.

Le lease est lié à : `school_id`, caissier, appareil, session de caisse, fenêtre locale, nombre maximal de paiements et plafonds CDF/USD.

L'expiration de la fenêtre locale **n'entraîne jamais une libération serveur automatique**. Elle interdit seulement de créer de nouveaux paiements sur l'appareil. Le serveur reste verrouillé jusqu'à réconciliation ou force-release explicite. Ce choix retire la course « appareil encore offline / serveur déjà rouvert ».

## 3. Reçus

PostgreSQL préalloue des `offline_receipt_tokens` avec un `receipt_no` unique par école. Un reçu passe `AVAILABLE → CONSUMED` ou `AVAILABLE → VOID`, jamais en arrière. Son identité école/lease/numéro est immutable.

À la clôture, tous les reçus disponibles non utilisés deviennent `VOID`. Un numéro consommé est lié à un seul `operation_id`.

## 4. Snapshot financier

Avant activation, le serveur fige les obligations autorisées dans `offline_charge_snapshots` : charge, inscription, élève, devise, solde restant et version.

Après activation du lease, ce snapshot devient immutable. Le client et le serveur refusent : charge inconnue, autre élève/inscription, devise différente ou cumul d'allocations supérieur au solde figé.

WEB-0D n'autorise pas offline : création/modification de tarif, remise, exonération, remboursement, annulation, fonds anticipé, conversion de devise ou mutation de charge. La v1 règle seulement des charges déjà existantes et nommées.

## 5. Journal local

`financeJournal.ts` utilise IndexedDB séparé du cache applicatif. L'armement échoue si le navigateur ne garantit pas le stockage persistant via `navigator.storage.persisted()/persist()`.

Chaque opération possède : `operationId`, `Idempotency-Key`, `journalSeq`, contexte school/user/device/lease/session, reçu préalloué, allocations, heure client, `previousEntryHash`, `entryHash`.

Le journal utilise des index uniques sur operation, idempotency key, reçu et séquence. L'ajout de l'opération, la consommation locale du reçu et l'avancement hash/séquence sont atomiques dans **une transaction IndexedDB**.

Le hash est SHA-256 sur un JSON canonique. Un vecteur partagé prouve que Python et JavaScript calculent la même empreinte.

## 6. Synchronisation exact-once

`offline_payment_inbox` impose l'unicité école + operation, idempotency key, receipt_no, entry_hash ainsi que lease + journal_seq. Un replay strictement identique devient un no-op. Une réutilisation incohérente est un conflit.

Le coordinator vérifie le journal complet : identité unique, séquence 1..N, chaîne SHA-256, plafonds et allocations cumulées avant de déléguer au `OfflinePaymentPostingPort`.

## 7. Concurrence Finance

La fonction DB `assert_finance_writer_allowed(...)` est le garde global. Sans lease actif, le Finance Web normal peut écrire. Avec lease `PREPARING`, toutes les écritures Finance sont bloquées. Avec lease `ACTIVE/DRAINING`, seul le même school/user/device/cash_session/lease peut continuer.

Le futur adapter Finance devra appeler cette fonction dans la même transaction que le ledger. Ainsi, un autre caissier, même connecté au VPS, ne pourra pas modifier les mêmes soldes pendant que la caisse offline possède l'autorité d'écriture.

## 8. Réconciliation

Une clôture réussit uniquement si : toutes les opérations connues sont `APPLIED`, le nombre de reçus `CONSUMED` est identique, les totaux CDF/USD correspondent et le hash final correspond au journal local.

Une opération seulement `RECEIVED` empêche la clôture. Les reçus inutilisés deviennent VOID. Le lease devient `CLOSED` et libère ensuite l'école.

La libération forcée est une procédure d'incident, avec motif >= 10 caractères et permission dédiée. Elle est interdite si des commandes `RECEIVED` restent non appliquées. Chaque transition est auditée.

## 9. Permissions

WEB-0D ajoute :

- `finance.offline.arm` ;
- `finance.offline.reconcile` ;
- `finance.offline.force_release`.

Le CAISSIER reçoit arm + reconcile. `force_release` reste hors bundle CAISSIER ; l'administrateur école l'obtient via le mapping administratif global.

## 10. Feature gate

Le protocole est implémenté, mais le runtime production refuse `offline_finance_enabled=true` si `offline_finance_certified=false`.

La raison est volontaire : la couche Web n'a pas encore porté les vraies tables Finance. Le port `OfflinePaymentPostingPort` attend l'adapter canonique qui devra garantir une transaction unique : charge/recalcul + paiement + allocations + reçu + caisse + audit + outbox + protocole offline.

## 11. Verdict

**WEB-0D OFFLINE FINANCE PROTOCOL: VALIDATED LOCALLY.**  
**G2 POSTGRES PROTOCOL: READY TO EXECUTE, NOT YET CLAIMED PASS.**  
**OFFLINE FINANCE PRODUCTION ENABLE: BLOCKED UNTIL CANONICAL FINANCE POSTING ADAPTER + G2 LIVE PASS.**

Cette formulation est importante : le problème n'est plus « on ne sait pas encaisser offline ». Le mécanisme existe maintenant. Ce qui reste est la preuve live PostgreSQL et le branchement sur le vrai ledger Finance Web lorsque ce domaine sera porté.
