# Certification d'isolation des sections — état NON CERTIFIÉ

Périmètres : DIRECTION_SECTION/PRIMAIRE, DIRECTION_SECTION/MATERNELLE, PREFET_ETUDES/SECONDAIRE. Une affectation double n'autorise que l'union explicite des sections. Aucun rôle ne reçoit SCHOOL par déduction.

## Contrôles déjà renforcés dans cette branche

- Rapports financiers et consultations historiques scolaires sans filtrage section : refus si aucun grant SCHOOL explicite.
- Documents archivés : la capacité scolaire globale n'est reconnue que si le grant SCHOOL est explicite.
- Liens signés : permissions recalculées lors de l'ouverture, y compris pour le créateur, dans la transaction tenant.
- Communications parents : destinataires liés à plusieurs sections contrôlés sur l'ensemble de leurs sections.

## Bloqueurs à lever avant la certification totale

1. **Documents générés par un responsable de section** : les requêtes `/documents/history?scope=mine`, `/documents/history/{id}/link` et `/documents/open` acceptent le propriétaire du document sans preuve que le document est lié à une section autorisée. La vérification `documents.open` ne remplace pas le filtrage du document. Introduire un scope de provenance persistant ou refuser les documents dont le scope ne peut pas être démontré.
2. **Rapports financiers de section** : les anciens rapports non filtrés sont volontairement refusés, pas encore servis avec un filtre SECTION. Implémenter des requêtes sectionnelles puis tester les exports.
3. **Consultations scolaires parity** : plusieurs endpoints sont volontairement refusés aux chefs de section jusqu'à ajout de filtres SQL SECTION.
4. **Audit transversal** : démontrer l'isolation de chaque route et export via des tests de base réelle (Primaire + Maternelle + Secondaire, élèves et responsables multi-sections, permissions révoquées, changements d'affectation).
5. **Frontend** : valider menus, navigation directe, écrans et exports pour chaque rôle ; le masquage UI ne remplace pas un 403 backend.

## Critère de clôture

Ne marquer CERTIFIÉ que si toutes les API, listes, détails, modifications, statistiques, documents, exports et liens signés sont couverts par des tests d'intégration négatifs inter-sections, si les parcours autorisés fonctionnent (pas seulement des refus), et si la CI du commit final est verte. Aucune fusion ni mise en production sans approbation.
