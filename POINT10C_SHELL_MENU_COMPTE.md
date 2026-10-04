# Point 10C — Shell, menu intelligent et compte utilisateur

- Sidebar dense 216 px, réductible à 64 px.
- En mode réduit, icônes conservées et titre affiché au survol.
- Navigation métier inchangée et Intendance toujours filtrée par permissions.
- Compte utilisateur déplacé en pied de sidebar : identité, paramètres, sécurité réservée, déconnexion.
- Topbar ramenée à 43 px : module courant, école, état de connexion uniquement.
- Aucun bouton Déconnexion encombrant dans la topbar.
- `prefers-reduced-motion` respecté.
- Responsive : shell desktop n'empiète pas sur le contenu; comportement mobile conservé comme gate UI à finaliser sur appareil.

Validation locale : 315/315 tests PASS ; compileall PASS.
Frontend build réel non exécuté faute de node_modules dans le checkpoint ; certification visuelle Windows/browser reste Point 11.
