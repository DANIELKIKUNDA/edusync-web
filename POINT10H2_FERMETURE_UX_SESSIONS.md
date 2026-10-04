# EduSync — Point 10H2 — fermeture UX & sessions persistantes

## Fermé dans cette passe
- Suppression des dialogues navigateur natifs `window.prompt/confirm/alert` des surfaces métier auditées.
- Nouveau dialogue EduSync accessible, homogène, responsive, validation obligatoire et fermeture clavier.
- Les motifs de sortie/réactivation/statut/fin d’affectation et les transferts élèves utilisent le dialogue EduSync.
- JWT d’accès retiré du stockage persistant navigateur : aucun access token n’est écrit dans localStorage.
- Au redémarrage, l’application restaure la session appareil via le cookie opaque HttpOnly et `/auth/refresh`.
- `/auth/refresh` restaure le contexte autoritaire utilisateur + école + permissions, puis émet un JWT court en mémoire.
- La session appareil reste glissante/persistante; changement de mot de passe, désactivation, modification membership ou révocation invalident l’accès.
- Écran de restauration de session explicite au lancement, sans bloquer le chargement de tous les modules.
- Version harmonisée 0.22.0-point10h2.

## Validation locale
- pytest: 334/334 PASS.
- Python compileall: PASS.
- audit statique: aucun `window.prompt`, `window.confirm`, `window.alert`, `String(e)` ou `String(err)` dans frontend/src.
- tests ajoutés pour absence de dialogue natif, absence de JWT persistant et restauration autoritaire de session.

## Gates non simulés
- Build React/Vite réel non certifié tant que les dépendances npm ne sont pas installées dans l’environnement de certification.
- PostgreSQL/RLS, Redis, Docker, k6, concurrence et tests offensifs live restent à exécuter sur l’infrastructure de certification.
- Fournisseur SMS réel nécessite des credentials et un environnement opérateur.
- Parité documentaire Finance Desktop reste soumise aux golden masters.

## Reliquat UX volontairement non déclaré fermé
Le socle React Hook Form + Zod est présent et la connexion l’utilise. Plusieurs formulaires historiques restent encore à migrer composant par composant avant de déclarer l’homogénéité formulaires à 100 %. Ce point ne doit pas être maquillé en PASS sans cette migration et un build TypeScript réel.
