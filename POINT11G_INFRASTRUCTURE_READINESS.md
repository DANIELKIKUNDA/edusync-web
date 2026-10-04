# EduSync — Point 11G — Préparation certification infrastructure réelle

Date: 2026-09-15
Version: 0.37.0-point11g

## Résultat

Le passage vers la certification réelle a commencé par l'audit du chemin de déploiement frais Docker/PostgreSQL. Un défaut bloquant a été trouvé et corrigé avant toute prétention de certification: `scripts/provision_database.py` s'arrêtait à la migration 0011 alors que le produit contient désormais les migrations jusqu'à 0032. Une base PostgreSQL neuve créée par le compose aurait donc été plus ancienne que le code applicatif.

Le provisioner applique maintenant explicitement et dans l'ordre toutes les migrations 0012 à 0032, y compris les doubles séries 0016, 0017 et 0021. Un gate de régression vérifie cette couverture et vérifie aussi que les secrets owner PostgreSQL restent hors du conteneur API runtime.

## Validation locale obtenue

- pytest backend: 393/393 PASS
- compileall backend: PASS
- couverture statique du provisioner: 32 fichiers SQL de migration référencés, aucun manquant
- scripts de certification live G1/G3 présents

## Gates non exécutables dans cet environnement

- Docker/Compose: moteur Docker indisponible ici
- PostgreSQL réel/RLS multi-tenant: non lancé
- Redis réel/recovery multi-worker: non lancé
- frontend: `npm install` n'a pas pu aboutir dans l'environnement; aucune dépendance `node_modules` n'est présente. Le `npm run build` échoue donc sur modules React/RHF/Zod absents, et n'est pas considéré comme un défaut TypeScript certifié.
- BOLA/IDOR dynamique, concurrence multi-caissier, k6 p95/p99: non exécutés faute d'infrastructure live.

## Statut

POINT 11G = READY FOR LIVE INFRASTRUCTURE CERTIFICATION, pas encore LIVE CERTIFIED.
Le prochain run doit se faire sur une machine avec Docker Desktop/Engine opérationnel et accès aux images/dépendances, puis exécuter provisioning frais, G1 PostgreSQL/RLS, API probe, Redis recovery, G3 concurrence, build frontend et k6.
