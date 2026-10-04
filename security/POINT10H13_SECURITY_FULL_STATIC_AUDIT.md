# Point 10H13 — Audit statique final de sécurité École

## Résultat
Audit transversal exécuté sur le checkpoint H12. Aucun endpoint métier non public sans dépendance acteur serveur n’a été trouvé. Les mutations Atelier Pro existantes restent permissionnées dans la couche application. Les JWT imposent algorithme, issuer/audience et claims temporels/type. Les permissions école sont rechargées depuis PostgreSQL à chaque requête et l’identité membership/user/school est revalidée. Aucun sink frontend `dangerouslySetInnerHTML`, `eval`, `new Function` ou stockage local/session de token sensible n’a été trouvé.

## Correction issue de l’audit
Les deux lectures keyset Sync (`/conflicts`, `/outbox/pending`) construisaient un fragment WHERE uniquement à partir de constantes internes. Ce n’était pas une SQL injection exploitable, mais cela violait la doctrine stricte « zéro SQL SELECT interpolé ». Elles utilisent désormais deux requêtes SQL statiques paramétrées (avec/sans curseur). `cursor_at` est désormais typé `datetime` par FastAPI afin qu’un curseur temporel invalide soit rejeté en validation plutôt que transmis au pilote PostgreSQL.

## Gates automatiques ajoutés
- couverture d’authentification de toutes les routes non publiques ;
- permissions des mutations plateforme dans les use-cases ;
- absence de SQL DML interpolé dans les routers ;
- absence de sinks frontend dangereux connus et de stockage navigateur de tokens ;
- JWT algorithm-pinned et claims obligatoires ;
- cookie persistant HttpOnly/SameSite=Lax/Secure en production ;
- revalidation tenant/membership/permissions.

## Validation locale
- `pytest -q`: 369/369 PASS
- `python -m compileall -q backend/src`: PASS

## Limite honnête
Ce checkpoint ferme l’audit statique local. Il ne certifie pas les attaques dynamiques ni l’infrastructure : BOLA réel entre tenants, RLS PostgreSQL FORCE avec rôles réels, JWT forgé/replay, SQLi/XSS dynamiques, brute-force distribué Redis, proxy/chunked, `pip-audit`, `npm audit`, SAST, Docker/VPS et tests réseau restent des gates machine/live.
