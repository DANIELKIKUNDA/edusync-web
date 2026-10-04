# EduSync — Point 6A.1 — Encaissement maximal
Date: 2026-09-13

## Résultat
Encaissement rapide porté au modèle guichet unique : obligations + échéances séquentielles + anticipation facultative dans la même opération.

## Invariants verrouillés
- Toutes les obligations actives restent visibles.
- Séquençage générique par `sequence_group` / `sequence_order` : mensualités, tranches, périodicités ordonnées.
- Une échéance future ne peut pas être forcée par API si une précédente reste due.
- Les chaînes de frais différentes ne se bloquent pas entre elles.
- CDF et USD restent séparés.
- Le tarif nominal n'est jamais modifié par un plan anticipé.
- Un surplus n'est accepté que si un plan anticipé actif a été explicitement accepté pour l'inscription et la devise.
- Un paiement unique ventile la part normale sur les obligations sélectionnées et le surplus dans `finance_advance_allocations`.
- Le fonds anticipé n'est plus un deuxième guichet obligatoire : il devient un ledger de suivi/imputation/remboursement.
- Paiement et impression restent découplés.
- Idempotence et caisse ouverte restent obligatoires.

## UX
- recherche globale 180 ms ;
- ajout enfant/famille ;
- obligations payées/restantes ;
- futures échéances visibles mais verrouillées ;
- bouton `Échéance suivante` générique ;
- saisie du montant réellement remis ;
- surplus expliqué avant validation ;
- activation explicite de l'affectation anticipée ;
- message post-paiement avec ventilation de l'avance.

## Validation locale
- pytest : 243 PASS ;
- compileall : PASS ;
- migration 0017 : RLS forcée sur plans, adhésions et avances ; ledger d'avance non supprimable/modifiable par PUBLIC.

## Gate restant
PostgreSQL réel, concurrence multi-caissier réelle, navigateur Windows/PWA et golden master du reçu Finance restent à certifier sur l'environnement final.
