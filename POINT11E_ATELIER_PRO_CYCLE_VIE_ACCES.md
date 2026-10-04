# Point 11E — Atelier Pro / cycle de vie des accès

- Retrait explicite et audité des rôles standards école.
- Désactivation d’une appartenance : rôles actifs désactivés et sessions persistantes de cette école révoquées immédiatement.
- Réactivation : aucun ancien rôle restauré silencieusement.
- Fiche école : attributions RBAC structurées, attribution et retrait depuis la même surface.
- Permission critique : `platform.access.manage`.
- PostgreSQL reste source de vérité; mutations verrouillées `FOR UPDATE`.
