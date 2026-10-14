# Isolation entre écoles (multi-tenant) — certification N2

Date : 2026-10-14. Méthode : deux **écoles jumelles** A et B créées par l'API publique de la plateforme, avec une
configuration volontairement identique (même classe « 1A », même frais « MINERVAL », même tarif) et des utilisateurs
semblables. L'administrateur de A tente ensuite de lire et de modifier B, y compris avec des identifiants (UUID)
devinés. Preuve : `certification/n2-20261014/n2_probe.py` → `n2-live.json` (**50/50 PASS**, 2026-10-14).

## 1. Défenses en profondeur

| Couche | Mécanisme |
|--------|-----------|
| Jeton | le jeton d'accès porte l'école ; chaque requête de l'espace école est rattachée à cette école (`require_school_actor`) |
| Application | chaque requête SQL filtre `school_id = école de l'acteur` ; les cibles (`_target`, classes, rôles) sont recherchées **dans l'école** avant toute modification |
| Base de données | sécurité au niveau des lignes (RLS) **forcée** (`FORCE ROW LEVEL SECURITY` dans 31 migrations), transaction ouverte avec l'école de l'acteur (`tenant_transaction`) ; rôles applicatifs créés `NOBYPASSRLS`, aucun superutilisateur (scripts/provision_database.py) |
| Comptes partagés | un compte présent dans deux écoles reste unique ; chaque école ne gère que **son** adhésion ; ni renommage ni réinitialisation par une école |

## 2. Résultats (sonde réelle)

| Tentative depuis l'école A | Résultat |
|----------------------------|----------|
| Lister les classes, tarifs, types de frais | seulement ceux de A (3 contrôles PASS) |
| Modifier la classe de B avec son UUID | refusé (404/409/422) |
| Lister les membres | aucun membre de B (hors compte rattaché à A) |
| Désactiver, réinitialiser, renommer un membre de B, ou lui attribuer un rôle, avec son UUID | 404 dans les quatre cas |
| Attribuer dans A un rôle propre à B | 404 |
| Effet sur le journal des droits de B | aucune action de A |
| Vue d'ensemble | identité de A uniquement |
| Contrôle en base (propriétaire) | aucune attribution de rôle à cheval sur deux écoles |
| Compte rattaché aux deux écoles | garde son mot de passe, voit ses deux écoles ; A ne peut ni le renommer ni le réinitialiser |

Pour les membres et les rôles, les tentatives sur B reçoivent un **404** (et non un 403) : l'école A ne peut même pas
apprendre que l'objet existe. Pour la classe de B, la réponse observée est **409** « Classe modifiée par une autre session ou introuvable » :
la mise à jour filtre à la fois l'identifiant, l'école et la version, aucune ligne n'est touchée, et le message ne
révèle pas si la classe existe dans une autre école.

## 3. Hors périmètre de cette sonde

- Les modules N3 (élèves, finance, imports, personnel…) ont été couverts par les sondes antérieures de
  `certification/claude-20260930/` (dont `bola_sweep.py`, balayage d'accès croisé par identifiant) ; elles ne sont pas
  rejouées ici.
- Le logo est stocké sous une clé construite à partir de l'école de l'acteur (`object_store.logo_key(actor.school_id, …)`)
  et lu via `school_branding` filtré par école ; la sonde N2 ne tente pas de lire le logo de B. À ajouter au N3.

## 4. Verdict

**0 fuite** constatée entre les écoles jumelles sur l'administration de l'école (utilisateurs, rôles, configuration).
**PASS LOCAL N2** pour l'isolation multi-école.
