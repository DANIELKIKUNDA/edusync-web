# Point 10H4 — Fermeture des formulaires complexes

Date: 2026-09-13

## Fermé dans cette passe
- Personnel: création agent migrée vers React Hook Form + Zod + FormField.
- Personnel: modification agent migrée vers React Hook Form + Zod + FormField.
- Personnel: affectation fonction/périmètre/titulariat migrée avec validations conditionnelles Zod.
- Scolarité: wizard d'inscription foyer + multi-enfants migré vers React Hook Form + Zod + useFieldArray.
- Les cinq champs terrain bloquants restent: Nom, Postnom, Prénom, Sexe, Classe.
- Date/lieu de naissance et autres données complémentaires restent facultatifs conformément au contrat Point 4C.
- Messages d'erreur de champs restent localisés sous les champs via FormField/role=alert.
- Boutons de mutation utilisent l'état isSubmitting et empêchent la double soumission UI.
- Aucun window.alert/window.prompt/window.confirm ni String(e)/String(err) détecté dans frontend/src.

## Préservation
Aucune règle métier Personnel/Scolarité, permission, API, export ou format documentaire n'a été redessinée. Le test de préservation Point 4C reste PASS.

## Validation locale
- pytest: 338/338 PASS
- python compileall backend/src: PASS
- audit statique formulaires: tous les fichiers TSX contenant <form> importent/utilisent le socle useForm.
- build React/TypeScript: non exécuté dans ce runtime en l'absence de node_modules.

## Gates externes inchangés
PostgreSQL/RLS réel, Redis réel, k6, navigateur Windows, fournisseur SMS réel et golden masters documentaires Finance nécessitent toujours leurs environnements/preuves réels. Ils ne sont pas déclarés certifiés par cette passe.
