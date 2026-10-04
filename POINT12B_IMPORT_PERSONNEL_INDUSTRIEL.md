# Point 12B — Import personnel industriel

Version 0.43.0-point12b-import-personnel — 15/09/2026.

- XLSX/CSV, modèle EduSync téléchargeable.
- Staging PostgreSQL tenant-isolé avec FORCE RLS.
- Analyse sans écriture métier, aperçu 100 lignes, maximum 5 000 agents/lot.
- Contrôles : matricule/nom/catégorie obligatoires, sexe, catégorie, statut, dates, matricule déjà utilisé, doublon nominal possible.
- Exécution séparée, permission dédiée, Idempotency-Key obligatoire, verrou FOR UPDATE, confirmation des avertissements.
- Création via domaine Personnel, historique initial conservé, audit et outbox.
- UI Personnel > Import, adaptée aux écrans mobiles via les primitives mobiles déjà fermées.
- Permissions `migration.staff.analyze` et `migration.staff.execute` héritées uniquement des rôles disposant déjà de `personnel.create` lors de la migration.

Validation locale : 419/419 pytest PASS + compileall PASS.
Le build Vite et PostgreSQL réel restent des gates environnementaux.
