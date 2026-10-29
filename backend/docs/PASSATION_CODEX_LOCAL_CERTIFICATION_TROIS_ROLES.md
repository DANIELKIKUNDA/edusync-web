# Dossier de passage Codex local — certification backend des trois rôles

## Périmètre et décisions

- Dépôt : `DANIELKIKUNDA/edusync-web`.
- Branche de travail exclusive : `chatgpt/intendant-etudes-discipline-certification`.
- Rôles : `INTENDANT` (29 attributions), `DIRECTEUR_ETUDES` (41), `DIRECTEUR_DISCIPLINE` (38), soit **108 attributions**, avec capacités partagées.
- Ne pas fusionner dans `main`, ne pas déployer et ne pas lancer de GitHub Actions.
- Le frontend reste hors périmètre jusqu'à clôture du backend.
- La matrice détaillée est dans `backend/docs/CERTIFICATION_ROLES_108_CAPACITES_REVUE_STATIQUE.md`. Une occurrence de permission dans le code n'est **pas** une preuve d'exécution.

## Préparation locale

Dans une copie propre du dépôt, enregistrer les modifications locales existantes avant toute bascule. Ne jamais écraser un travail non commité.

```powershell
git fetch origin
git switch chatgpt/intendant-etudes-discipline-certification
git pull --ff-only origin chatgpt/intendant-etudes-discipline-certification
git status --short
```

Inspecter les instructions du backend et les dépendances avant de lancer les commandes. Les exemples ci-dessous supposent que Python, pytest et les dépendances du backend sont installés dans l'environnement virtuel local.

```powershell
cd backend
python -m compileall -q src tests
python -m pytest -q tests/test_secondary_leadership_backend_regression.py tests/test_intendant_backend_exports_regression.py tests/test_intendant_dashboard_permissions_regression.py
python -m pytest -q tests/test_point9_stewardship.py tests/test_point10b_communications.py
```

Si les tests nécessitent PostgreSQL/Redis, les lancer seulement avec la configuration de test isolée prévue par le dépôt ; **ne pas pointer les migrations ni les tests d'écriture sur staging ou production**. Les suites peuvent nécessiter des fixtures supplémentaires. Documenter les erreurs d'environnement séparément des défauts applicatifs.

## Scénarios d'intégration indispensables

1. **Intendant** : créer un article et une immobilisation ; réception, sortie, ajustement et contrôle de stock ; inventaire avec deux opérateurs concurrents ; validation et refus des articles inactifs ; historique, exports XLSX/PDF ; refus des actions sans permission.
2. **Directeur des études** : lecture des élèves, familles, effectifs, inscriptions, personnel, documents et tableaux de bord ; filtrage `SECTION=SECONDAIRE` ; refus de `students.identity.update`, de mutations financières et de SMS groupés.
3. **Directeur de discipline** : lecture secondaire ; correction d'identité autorisée dans son périmètre ; refus des modifications de profil non autorisées et des changements mixtes ; communication de classe/section avec permission SMS groupée ; refus des autres sections.
4. **Multi-écoles** : créer deux écoles avec sections et années distinctes ; vérifier l'absence de données croisées dans les options d'affectation, documents, historiques de livraison et destinataires des communications.
5. **Familles multisections** : un même responsable parental avec enfants au primaire et au secondaire ; vérifier l'inclusion une seule fois dans l'audience autorisée, et l'exclusion de toute audience hors périmètre.
6. **Documents** : vérifier les capacités `documents.history.read`, `documents.open` et `documents.print`, notamment la révocation d'un accès après émission d'un lien signé.
7. **Audit** : vérifier qu'un utilisateur cantonné au secondaire ne peut pas lire `old_json`/`new_json` d'une entité primaire ou financière via `/entities/{entity_type}/{entity_id}`.
8. **Notifications** : lecture et acquittement uniquement par le destinataire et dans la bonne école.
9. **Idempotence** : répéter les requêtes de mutation avec la même clé, puis avec une charge différente ; vérifier l'absence de doublons et la cohérence des audits/outbox.
10. **Concurrence** : tests de transactions simultanées sur le stock, les comptages et la réservation de crédits SMS.

## Réserves de sécurité non clôturées

- **Audit par entité** : la route vérifie la capacité et le `school_id`, mais aucune validation explicite du périmètre SECTION de l'entité n'a été identifiée. Risque de lecture transversale des champs d'audit : **à reproduire et corriger**.
- **Documents signés** : la route d'ouverture vérifie le jeton, l'appartenance à l'école et le document ; la révocation des capacités pendant la durée de validité du lien n'est pas explicitement revalidée : **à tester et corriger si confirmé**.
- **Matrice de couverture** : les capacités non retrouvées dans les routeurs examinés ne sont pas nécessairement absentes ; étendre la recherche à l'ensemble du backend et associer chaque capacité à une route, un service ou une justification `N/A`.
- **Tests de régression** : plusieurs tests inspectent le code source par chaînes de caractères ; ils ne remplacent pas des tests API et PostgreSQL.

## Format de retour demandé à Codex

Fournir un rapport unique comportant :

- Branche, commit HEAD et `git status --short`.
- Version Python, commandes exactes exécutées, nombre de tests PASS/FAIL/SKIP et durée.
- Chaque échec avec chemin, fonction, trace essentielle, cause racine et correctif recommandé.
- Résultats de la matrice 108 capacités, regroupés par rôle, avec preuve `PASS`, `FAIL`, `N/A` ou `NON TESTÉ`.
- Résultats spécifiques aux huit scénarios de sécurité et de concurrence ci-dessus.
- Liste des migrations utilisées et confirmation de la base de test isolée.
- Aucun verdict de certification globale si une réserve critique reste ouverte.

## Conditions de clôture backend

- Couverture vérifiée de chaque capacité attribuée, sans élargissement implicite des permissions.
- Aucun défaut de cloisonnement multi-écoles ou inter-sections.
- Tests unitaires, intégration et régression requis au vert dans un environnement reproductible.
- Résultats Codex rapprochés des commits de la branche, puis revue finale avant décision de fusion.
