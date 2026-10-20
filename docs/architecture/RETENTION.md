# Conservation et purge des données (lot 2026-10) — BUSINESS_DECISION_REQUIRED

Le mécanisme existe (`backend/scripts/retention_purge.py`) mais **ne supprime rien par défaut** : sans `--apply`, il
compte seulement. Les durées ci-dessous sont des **propositions techniques** ; elles doivent être validées par le
propriétaire (et, pour le journal d'audit, au regard des obligations légales applicables en RDC).

| Donnée | Proposition | Statut |
|---|---|---|
| Sessions d'appareil révoquées / expirées | 90 jours | proposé, purge manuelle (`--apply`) |
| Étapes de connexion (codes, MFA) expirées | 30 jours | proposé |
| Liens de compte utilisés / révoqués / expirés | 90 jours | proposé |
| Accusés de réception fournisseurs appliqués | 180 jours | proposé |
| Incidents de la plateforme résolus | 2 ans | proposé |
| Messagerie : envois, destinataires et messages techniques plateforme / compte (invitations, récupérations, alertes, tests) terminés | 180 jours | proposé |
| Appareils push révoqués (jeton chiffré) | 90 jours | proposé |
| Historique des communications d'une école | — | jamais purgé par la plateforme (donnée de l'école) |
| Signaux de supervision (Redis) | 26 h par minute, 8 jours par heure | **appliqué** (expiration automatique, aucune donnée personnelle) |
| Journal d'audit | 5 ans | **jamais purgé** tant que la durée légale n'est pas décidée (ajout seul, trigger) |
| Données des écoles (élèves, paiements, documents) | — | hors périmètre : décision par contrat avec chaque école, y compris à la résiliation |

Exécution (identifiants propriétaire de la base, jamais l'API) :
`python backend/scripts/retention_purge.py` (comptage) puis `--apply` (suppression, journalisée
`RETENTION_PURGE_APPLIED`). Vérifié en local le 19/10/2026 : une étape expirée insérée exprès a été purgée, le volume
journalisé, le journal d'audit intact.
