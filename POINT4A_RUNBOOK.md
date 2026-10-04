# Point 4A — Runbook certification machine

Objectif : vérifier uniquement ce qui dépend d'un vrai PostgreSQL/Docker/navigateur.

1. Copier `.env.example` vers `.env` et renseigner des secrets forts distincts owner/tenant/platform/JWT.
2. Lancer le provisioning PostgreSQL via le script du bundle.
3. Exécuter les probes G1/Point2 déjà inclus pour RLS, JWT, idempotence et concurrence.
4. Lancer `pytest -q` dans `backend`.
5. Dans `frontend`, exécuter `npm install` puis `npm run build`.
6. Démarrer la stack et créer une école dans Atelier Pro.
7. Vérifier qu'elle est immédiatement accessible sans classes ni tarifs inventés.
8. Préparer/activer une année, activer une section, ouvrir une classe, créer un type de frais et un tarif réel.
9. Vérifier qu'une seconde année ne peut pas être ACTIVE simultanément et qu'une année CLOSED doit être réouverte avant réactivation.
10. Tester avec deux écoles que les paramètres de A ne sont jamais visibles depuis B.

Ne pas déclarer le gate live PASS si l'un de ces contrôles échoue.
