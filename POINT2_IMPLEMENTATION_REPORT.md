# Rapport d'implémentation — Point 2

## Objet

Industrialiser la Finance offline pour plusieurs caissiers sans sacrifier ni l'intégrité comptable ni la continuité de service en cas d'Internet instable.

## Changements principaux

### Domaine

Ajout de `finance_offline/domain/multi_cashier.py` :

- `PROTOCOL_V2` ;
- `JournalCheckpoint` ;
- `ReceivedCommandRecord` ;
- `OfflinePostingResult` ;
- partitionnement déterministe des snapshots ;
- validation des segments de journal incrémentaux ;
- invariant allocation + crédit résiduel = cash reçu.

### Application

Ajout de `MultiCashierOfflineFinanceCoordinator` :

- accepte replay exact ;
- reprend après timeout ;
- ancre le segment neuf sur le checkpoint serveur ;
- sérialise le lease au serveur ;
- revalide plafonds, token et autorité ;
- consomme la réservation de charge ;
- appelle le port Finance canonique ;
- consomme le reçu ;
- marque l'opération appliquée.

### PostgreSQL

Migration `0005_offline_finance_multi_cashier.sql` :

- suppression du writer unique par école ;
- writer actif unique par appareil/session ;
- `offline_charge_reservations` ;
- index partiel anti-double-réservation ;
- `offline_finance_incidents` ;
- RLS ;
- guard charge-scoped ;
- quarantaine après force release ;
- résolution d'incident explicite ;
- colonnes posting outcome / residual credit.

### Adapter PostgreSQL

Nouvelles primitives :

- `acquire_multi_writer_lease` ;
- `reserve_charge_snapshots` ;
- `activate_multi_writer_lease` ;
- `journal_checkpoint` ;
- `received_command` ;
- `assert_server_lease_limits` ;
- `consume_charge_reservations` ;
- `resolve_quarantine`.

### Frontend offline

`financeJournal.ts` passe à IndexedDB version 2 et exige :

- stockage persistant ;
- WebCrypto ;
- Web Locks ;
- lock exclusif par scope de caisse pendant l'append.

### Provisioning et certification

- migration 0005 ajoutée au provisioner ;
- GRANT/RLS des nouvelles tables/fonctions ;
- `g3_multi_cashier_probe.py` ;
- `RUN_POINT2_WINDOWS.ps1` ;
- `RUN_POINT2_LINUX.sh`.

## Préservation

Aucune règle métier Desktop n'a été supprimée. Le protocole V2 ne remplace pas le ledger scolaire existant : il prépare le transport offline sûr autour du futur portage canonique.

## Rôles

Aucun nouveau rôle définitif n'a été décidé. Une permission technique d'incident est créée sans attribution automatique. La matrice finale reste volontairement réservée au Point 3 avec Daniel.

## Verdict

**Point 2 implémenté localement.** La seule preuve non exécutable dans cet environnement est le gate PostgreSQL/navigateur réel, préparé dans le runbook.
