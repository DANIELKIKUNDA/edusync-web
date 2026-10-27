# Relais technique Claude — EduSync Web / PR #27

## Consigne du propriétaire
ChatGPT effectue les changements réalisables et laisse à Claude les blocages techniques résiduels. Ne pas déclarer la certification achevée, ne pas fusionner la PR, ne pas déployer sans autorisation explicite.

- Dépôt : `DANIELKIKUNDA/edusync-web`
- Branche : `chatgpt/prefet-directeur-certification`
- PR : https://github.com/DANIELKIKUNDA/edusync-web/pull/27 (draft)
- Rôles : `DIRECTION_SECTION/PRIMAIRE`, `DIRECTION_SECTION/MATERNELLE`, `PREFET_ETUDES/SECONDAIRE`.
- Principe : un droit SECTION ou CLASS n'accorde jamais SCHOOL implicitement. Une double affectation accorde l'union **explicite** des périmètres, sans exposition des autres sections.

## État vérifié au 27/10/2026

- CI **verte** : commit `5a017f7ffca62b286323e9e4cbe2bf968de1aeb4`, run `40489786438` (backend, frontend, sécurité, RBAC/migrations/PostgreSQL réel, CD privilégiée). Docker non exécuté pour la PR, conformément au workflow.
- Ce commit corrige une vraie erreur PostgreSQL `operator does not exist: text = integer` due à la combinaison `IN :lateral_classes` avec une liste vide dans `PostgresSchoolingRepository.list_students`.
- Le test PostgreSQL `tools/ci/section_isolation_postgres_integration.py` est exécuté par `.github/workflows/ci.yml` dans le job `rbac-contract` après migrations. Il couvre trois sections, une famille commune, les grants SECTION individuels et la double affectation.
- Commit ultérieur `59f5284ce764ec3f942af7c7c927bb56f8af94da` : ajoute les scénarios CLASS seul, CLASS + SECTION et aucun grant. **Non certifié** : run `40490364312`, tentatives 1 et 2, cinq jobs échouent en ~2 secondes, zéro étape exécutée. Il s'agit d'un blocage de lancement GitHub Actions, pas d'un résultat de tests. Vérifier les annotations du run, limites Actions, facturation et restrictions du compte/dépôt. Ne pas supposer que les nouveaux tests passent.
- La PR est restée draft, non fusionnée.

## Ce qui est déjà implémenté sur la branche

Les protections concernent notamment les listes d'élèves/familles, les inscriptions historiques, les familles partagées, les métriques par inscription dans sa propre section, les contacts/communications, les changements de familles partagées, les documents signés et le refus de certaines API globales sans grant SCHOOL. Voir les commits de la PR et `docs/rbac/SECTION_ISOLATION_CERTIFICATION_GATES_20261027.md`.

## Travail résiduel — ordre de traitement

1. **Documents** : auditer `/documents/history?scope=mine`, `/documents/history/{id}/link`, `/documents/open`. Le statut de créateur ne prouve pas le périmètre SECTION du document. Persister une provenance vérifiable (school, section/class, contexte métier), contrôler à la lecture et à l'ouverture du lien signé, et refuser les documents historiques sans provenance démontrable. Ajouter tests négatifs après révocation et mutation d'affectation.
2. **Finance** : les rapports historiques globaux sont actuellement refusés aux responsables SECTION ; implémenter, si le contrat produit l'exige, les agrégations SQL et exports filtrés sur les inscriptions/frais de la section réellement autorisée. Tester les familles multi-sections et les montants non divulgués.
3. **Parité des endpoints scolaires** : inventorier les routes encore refusées à SECTION, puis implémenter les filtres corrects ou documenter explicitement le refus fonctionnel. Couvrir liste, détail, écriture, statistiques et export, avec tests HTTP 403/404.
4. **PostgreSQL réel** : compléter `tools/ci/section_isolation_postgres_integration.py` pour cas négatifs, révocation de droits, changements d'affectation, classes mixtes, années historiques et second établissement ; exécuter avec migrations et transaction rollback. Les fixtures ne doivent jamais cibler une base distante ou de production.
5. **Frontend** : tester les trois profils et l'union double SECTION ; menus, accès direct URL, chargement des écrans, filtres, téléchargement et refus backend indépendamment du masquage UI.
6. **Certification** : après résolution du blocage GitHub Actions, obtenir une CI entièrement verte **sur le commit final** et conserver les preuves. Ne pas certifier sur le seul commit `5a017f7` si la branche a évolué.

## Recommandations d'exécution

- Partir de l'état réel de la branche et des migrations ; ne pas réécrire ni écraser les correctifs existants.
- Exécuter `python ../tools/ci/section_isolation_postgres_integration.py` depuis `backend` avec `PYTHONPATH=src`, `CI=true`, et `EDUSYNC_OWNER_DATABASE_URL` vers PostgreSQL **localhost** migré.
- Pour chaque API : établir la source du grant, la preuve d'appartenance des objets, le traitement de plusieurs sections et les refus en cas de grant vide/révoqué.
- Garder la PR draft et produire un rapport final PASS/FAIL/BLOCKED avec traces de CI et limites explicites.
