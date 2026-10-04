# Point 10H3 — fermeture UX formulaires

Cette passe poursuit Point 10H sans modifier la doctrine métier.

## Fermé dans cette passe
- Contrat commun `FormField` : label, erreur inline rouge, `role=alert`, focus de la première erreur.
- Atelier Pro / création école : React Hook Form + Zod.
- Paramètres / année scolaire : React Hook Form + Zod avec cohérence début/fin.
- Sécurité du compte : React Hook Form + Zod, confirmation de mot de passe dans le schéma.
- Personnel / création de fonction : React Hook Form + Zod.
- Élèves / modification de fiche : React Hook Form + Zod.
- Aucun dialogue navigateur natif ni affichage direct `String(e)`/`String(err)` dans `frontend/src`.
- Styles d'erreur et de focus homogènes.

## Audit honnête restant
Les formulaires métier complexes de Personnel (création/modification d'agent, affectation) et le wizard multi-enfants d'inscription conservent encore une partie de leur état historique. Ils utilisent déjà le pipeline d'erreur convivial et les contraintes serveur restent autoritaires, mais ils ne sont pas encore tous migrés intégralement vers RHF/Zod. Ne pas déclarer « 100 % formulaires migrés » avant cette dernière passe.

Le build React complet reste non certifié : `npm install` expire dans l'environnement courant. Les tests backend/statiques restent exécutables.
