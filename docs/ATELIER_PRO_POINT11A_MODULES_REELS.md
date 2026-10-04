# Atelier Pro — Point 11A — modules réels

Atelier Pro n'est plus une simple page Écoles avec entrées de menu inactives.

## Modules activés
- **Cockpit plateforme** : nombre d'écoles, écoles actives/suspendues, appartenances actives, couverture admin initial, backlog outbox et activité récente.
- **Écoles** : annuaire paginé/recherchable/filtrable, statut, nombre d'accès actifs, présence de l'administrateur initial, création d'école conservée.
- **Accès** : identités, comptes plateforme/école, appartenances et statut actif.
- **Audit plateforme** : journal append-only avec pagination keyset `occurred_at,id` et chargement progressif.
- **Diagnostics** : PostgreSQL, backlog outbox, conflits Sync et confirmation de l'absence de verrou global.

## Doctrine
Les modules lisent les vraies tables PostgreSQL. Aucun KPI métier n'est simulé. Les mutations existantes de cycle de vie des écoles restent idempotentes et auditées. Les nouveaux écrans de lecture sont bornés (50 par défaut, 100 maximum).

## Reste Atelier Pro
La prochaine passe doit industrialiser les actions sensibles de cycle de vie dans l'UI (suspension/réactivation/bootstrap admin avec dialogues professionnels), puis les **notifications système** et une gestion RBAC plateforme plus complète. La certification live PostgreSQL/Redis/Windows reste Point 11 machine.
