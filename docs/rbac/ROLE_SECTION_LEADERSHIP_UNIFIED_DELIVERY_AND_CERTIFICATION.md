# Préfet et directeurs — livraison globale et certification unique du rôle

**Statut : EN DÉVELOPPEMENT — NON CERTIFIÉ.** PR #27 (draft). Ne pas fusionner, ne pas déployer sans approbation du propriétaire.

## Doctrine de livraison

L'implémentation doit couvrir les **cinq volets** avant de demander à Claude ou Codex **une seule certification complète du rôle**, et non cinq certifications indépendantes. Les résultats intermédiaires de CI servent au développement et ne constituent pas une clôture de volet ni du rôle.

Rôles concernés : `PREFET_ETUDES` (SECONDAIRE), `DIRECTION_SECTION` (PRIMAIRE), `DIRECTION_SECTION` (MATERNELLE). Le rôle et les grants effectifs doivent être résolus par la même source d'autorisation que les API. Les sections multiples donnent l'union explicite de leurs grants, jamais un droit `SCHOOL` implicite.

## Les cinq volets à livrer ensemble

1. **Documents et liens signés** : provenance persistante école/section/classe/objet métier ; filtrage de `/documents/history?scope=mine`, `/documents/history/{id}/link`, `/documents/open` ; revalidation après révocation, mutation de section et changement d'affectation. Refuser tout document dont la provenance n'est pas démontrable.
2. **Finances par section** : rapports, agrégats, détails et exports réellement filtrés sur la section autorisée ; familles et élèves multi-sections ; aucune fuite de montants d'une autre section ; ne pas substituer une réponse globale ou une simple dissimulation frontend.
3. **Parité des API scolaires** : inventorier toutes les routes de consultation, création, modification, statistiques, historique et export ; appliquer les scopes à l'objet et aux lignes retournées ; garantir 403/404 selon contrat pour les objets hors périmètre et une fonctionnalité effective pour les accès autorisés.
4. **Sécurité et tests PostgreSQL réels** : écoles distinctes, trois sections, grants SECTION/CLASS/SCHOOL explicites, doubles grants, absence de grant, famille partagée, historique multi-section, révocation et réaffectation ; tests négatifs HTTP et SQL, y compris transactions et accès concurrents pertinents.
5. **Frontend complet** : menus, routes directes, écrans, filtres, états d'erreur et téléchargements pour chaque profil et pour la double affectation ; aucune fonctionnalité inaccessible à tort, aucune permission reposant seulement sur le masquage UI.

## Preuves et blocage d'infrastructure

Dernière CI entièrement verte constatée : `5a017f7`, run `40489786438`, avec PostgreSQL réel. Les commits postérieurs comprennent les tests `59f5284` (CLASS, union mixte, deny-all) et `b5653b9` (détails élèves), ainsi que la correction `5705117` des tableaux SQL vides dans l'historique des inscriptions. Les derniers runs échouent avec **zéro étape exécutée** dans tous les jobs ; vérifier annotations/permissions/facturation/quota GitHub Actions avant de conclure à un défaut applicatif. Ces commits ne sont pas encore certifiés.

## Mission finale à Claude ou Codex (une seule mission)

> Audite et certifie **globalement** le rôle Préfet des études / Directeur du primaire / Directeur de la maternelle d'EduSync Web, sur la PR #27, après livraison des cinq volets ci-dessus. Examine backend, frontend, schéma, migrations, SQL PostgreSQL réel, RBAC, multi-école, multi-section, documents, liens signés, finances, rapports, exports, mutations, menus et routes directes. Vérifie la révocation des droits et les réaffectations en session active. Exécute les tests fonctionnels positifs et négatifs, tests de non-régression, build et CI sur le commit final. Ne considère pas un refus global de fonctionnalité comme une implémentation réussie si le profil doit y accéder. Ne certifie pas sur un ancien commit vert. Produis un seul rapport par rôle et scénario avec PASS/FAIL/BLOCKED, preuves vérifiables, anomalies corrigées et risques résiduels. N'effectue aucune fusion ni déploiement sans autorisation explicite du propriétaire.

## Critères de fin

Tous les cinq volets sont implémentés et testés, les fonctions autorisées sont opérationnelles, aucun accès transversal interdit n'est possible, la CI finale est verte et le rapport d'audit unique est PASS sans blocage critique. Sinon conserver **NON CERTIFIÉ** et décrire précisément les blocages.

Références : `docs/rbac/SECTION_ISOLATION_CERTIFICATION_GATES_20261027.md` et `docs/rbac/CLAUDE_HANDOFF_SECTION_ISOLATION_20261027.md`.
