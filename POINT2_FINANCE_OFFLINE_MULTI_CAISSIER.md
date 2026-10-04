# EduSync — Point 2 verrouillé
## Finance offline multi-caissier à autorité partitionnée

Date : 11 septembre 2026  
Statut : **implémenté et validé localement — certification PostgreSQL/navigateur réelle à exécuter sur la machine de Daniel**.

## 1. Objectif

Le Point 2 supprime la dépendance fonctionnelle au modèle WEB-0D « un seul writer Finance offline pour toute l'école ».

La cible est maintenant : **plusieurs caissiers peuvent continuer à encaisser du CASH lorsque le VPS est momentanément inaccessible**, sans donner simultanément à deux appareils le droit de solder la même obligation.

Le protocole canonique devient :

`AUTHORIZED_PARTITIONED_CASH_V2`

## 2. Contrainte fondamentale

Deux appareils totalement hors connexion ne peuvent pas tous les deux posséder une autorité illimitée sur la même dette et garantir mathématiquement l'absence de double encaissement : ils ne peuvent pas se consulter.

EduSync choisit donc une stratégie d'**escrow d'autorité par charge** :

- plusieurs leases Finance offline peuvent être actifs dans la même école ;
- chaque charge financière active est réservée à **un seul lease** ;
- les charges d'un même élève sont routées vers le même appareil par défaut ;
- lorsque le modèle Famille Web sera porté, le routeur peut utiliser `family_id` pour garder toute une famille sur le même poste ;
- les autres caissiers restent libres de travailler sur leurs propres charges et sur les charges non réservées.

Ainsi, la perte d'Internet ne bloque pas l'école entière.

## 3. Ce qui est maintenant autorisé

### CASH

Un caissier dont la caisse a été armée peut :

1. consulter les obligations présentes dans son snapshot ;
2. encaisser du CASH hors connexion ;
3. consommer un numéro de reçu officiel préalloué ;
4. enregistrer une allocation exacte ;
5. poursuivre jusqu'à sa limite locale de nombre d'opérations et de montant CDF/USD ;
6. synchroniser plus tard avec le même `operation_id`, la même `idempotency_key` et la même chaîne de hash.

### Plusieurs caissiers

Deux ou plusieurs caissiers peuvent posséder simultanément des leases `ACTIVE` dans la même école **si leurs autorités de charge sont disjointes**.

L'ancien index PostgreSQL `uq_offline_finance_one_writer_per_school` est supprimé par la migration `0005_offline_finance_multi_cashier.sql`.

## 4. Partitionnement de l'autorité

Le backend fournit `partition_charge_snapshots(...)`.

Le partitionnement est déterministe par rendezvous hashing :

- une charge apparaît dans une seule partition ;
- toutes les charges d'un même routing key restent ensemble ;
- par défaut, le routing key est `student_id` ;
- un mapping futur `student_id -> family_id` permet de router par famille sans réécrire le protocole.

La sécurité finale est assurée par PostgreSQL :

`offline_charge_reservations`

et l'index partiel unique :

`uq_offline_charge_one_live_authority`.

Même si deux requêtes concurrentes essaient d'armer la même charge, un `pg_advisory_xact_lock` par charge + l'index unique ne laissent qu'un gagnant.

## 5. Concurrence online/offline

Le verrou global d'école n'est plus la primitive de sécurité.

Toute future mutation d'une charge dans le Finance Web canonique devra appeler :

`assert_finance_charge_writer_allowed(school_id, charge_id, lease_id)`

Résultat :

- charge non réservée : writer online autorisé ;
- charge réservée : seul son lease offline peut la poster ;
- charge en quarantaine : aucun writer automatique ne peut la modifier ;
- une autre charge de la même école reste disponible.

Cela augmente fortement la disponibilité par rapport au modèle V1.

## 6. Idempotence et retry

Le serveur accepte maintenant des segments de journal incrémentaux ancrés sur un checkpoint :

- `last_seq` ;
- `last_hash`.

Cas certifiés localement :

- double clic ;
- replay exact ;
- timeout après commit puis retry ;
- synchronisation incrémentale du prochain paiement ;
- séquence sautée ;
- hash d'ancrage incorrect ;
- `operation_id`, `idempotency_key`, reçu et séquence dupliqués.

Un replay strictement identique est un no-op.

## 7. Concurrence locale du navigateur

IndexedDB seul ne suffit pas si deux onglets de la même caisse écrivent au même instant.

Point 2 impose donc :

- stockage persistant navigateur ;
- WebCrypto ;
- **Web Locks API** ;
- lock exclusif `edusync:finance:<school:user:device:lease>` autour de chaque append financier.

Si le navigateur ne fournit pas ces garanties, le CASH offline définitif n'est pas armé sur cet appareil.

## 8. Reçus

Les reçus restent préalloués par le VPS avant la coupure.

Invariants :

- numéro unique par école ;
- token lié au lease ;
- consommation unique ;
- retry ne consomme pas un second reçu ;
- reçus inutilisés annulés à la clôture ;
- reçu consommé jamais réattribué.

## 9. Limites de caisse

Chaque lease possède ses propres plafonds :

- `max_payments` ;
- `max_cdf` ;
- `max_usd` ;
- `local_stop_at`.

Les limites sont vérifiées localement puis **recalculées côté PostgreSQL** sur l'inbox reçue. Le client n'est donc jamais la seule autorité de contrôle.

CDF et USD restent strictement séparés.

## 10. Conflit inattendu au moment du posting canonique

La réservation doit normalement empêcher qu'une autre écriture modifie la charge.

Si malgré tout une situation anormale existe lors de la synchronisation — intervention administrative, restauration, incident, bug externe — le port canonique Finance doit expliquer **100 % du cash physiquement reçu** :

`montant reçu = montant réellement alloué + crédit résiduel explicite`.

Il est interdit de :

- perdre une partie du cash ;
- fabriquer un deuxième règlement de dette ;
- convertir silencieusement CDF/USD ;
- annuler rétroactivement le reçu physique sans procédure d'incident.

Le modèle `OfflinePostingResult` encode cet invariant.

## 11. Force release et appareil perdu

Une libération forcée ne rend plus immédiatement les charges à un autre caissier.

Si un lease `ACTIVE`/`DRAINING` est force-released :

- ses reçus disponibles sont annulés ;
- ses réservations passent à `QUARANTINED` ;
- les autres partitions de l'école continuent de fonctionner ;
- seules les charges concernées restent bloquées ;
- une résolution d'incident explicite est nécessaire pour les libérer.

La fonction :

`resolve_offline_finance_quarantine(...)`

exige un acteur, un motif et laisse une trace d'audit. **La permission correspondante n'est attribuée à aucun rôle dans Point 2** : Daniel décidera au Point 3.

## 12. Mobile Money et Banque

La doctrine Point 1 reste inchangée :

- l'intention peut être capturée offline ;
- la finalité financière dépend d'une preuve externe ;
- sans confirmation du prestataire, EduSync ne marque pas la dette comme définitivement réglée.

## 13. Transaction canonique attendue au portage Finance

Le futur adapter Finance Web doit effectuer dans **une seule transaction PostgreSQL** :

1. garde tenant/RLS ;
2. garde d'autorité de charge ;
3. verrouillage/recalcul de la charge ;
4. paiement ;
5. allocations exactes ;
6. éventuel crédit résiduel même devise ;
7. reçu officiel préalloué ;
8. mouvement de caisse ;
9. audit append-only ;
10. outbox ;
11. consommation de l'autorité et du token ;
12. commit.

La génération PDF reste post-commit : son échec ne doit jamais recréer le paiement.

## 14. Limite restante du Point 2

Le protocole multi-caissier est implémenté dans la fondation Web, mais les tables Web canoniques `charges/payments/payment_allocations/receipts/cash` seront portées depuis le Desktop au Point 6 de la feuille de route.

Le Point 2 fournit déjà le port hexagonal et les invariants que cet adapter devra respecter. Il n'invente pas un ledger parallèle.

## 15. Décision

**Point 2 fonctionnel : sécurité maximale + disponibilité maximale compatible avec un système réellement offline.**

L'ancien `single-writer école entière` devient historique/compatibilité V1. La cible et l'implémentation actuelle sont V2 partitionnées par charge.
