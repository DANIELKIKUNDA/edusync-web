# Point 12A — Import élèves industriel

- XLSX et CSV, modèle canonique EduSync.
- Staging PostgreSQL par école + FORCE RLS.
- Analyse serveur avant toute mutation métier.
- Résolution stricte des classes dans l’année scolaire choisie.
- 5 champs bloquants : nom, postnom, prénom, sexe, classe.
- Détection de doublon possible en avertissement.
- Erreur => exécution bloquée ; avertissement => acceptation explicite.
- Aucun foyer fusionné silencieusement : l’exécution confirme la création de foyers séparés.
- Exécution atomique, auditée, outbox ; lot verrouillé FOR UPDATE.
- UI desktop/mobile avec aperçu et compteurs.
- Maximum 5 000 lignes/lot et limite HTTP globale existante.

Limite : l’import historique financier et l’import Personnel ne font pas partie de ce lot.
