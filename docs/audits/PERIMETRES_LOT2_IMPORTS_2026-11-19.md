# Périmètres — lot 2 : importation (19 novembre 2026)

## Défaut confirmé

Les rôles standards PREFET_ETUDES et DIRECTION_SECTION contenaient encore migration.finance_history.analyze et execute. Le garde des routes d’import contrôlait seulement la présence de la permission ; un grant SECTION pouvait donc autoriser une opération portant sur toute l’école.

## Correction

- Registre canonique et migration additive 0116 : retrait des deux droits des rôles standards concernés. Aucun changement des données scolaires, lots d’import, exceptions ou opérations offline.
- Tous les imports globaux, historiques, modèles et rapports de contrôle exigent SCHOOL pour la permission exacte. Une portée SCHOOL d’une autre permission ne suffit pas.
- La projection des permissions de connexion/rafraîchissement filtre les grants d’import SECTION/CLASS/CYCLE/absents, y compris les exceptions. Les menus utilisent cette projection.
- Les délégations personnalisées SCHOOL restent possibles ; les droits déjà décidés du caissier, secrétariat et gestionnaire restent inchangés. L’export du modèle élèves, déjà filtré par périmètre dans Documents, conserve son fonctionnement.
- La migration 0115 du travail parallèle sur les départs est conservée.

## Vérification

11 tests de politique et HTTP : refus avant accès aux données pour les grants partiels, refus sans permission, refus d’emprunter SCHOOL à une autre permission, et autorisation explicite SCHOOL. Contrôle PostgreSQL réel ajouté à finance_scope_postgres_integration.py : projection des permissions et contrats HTTP pour les deux portées. Le snapshot 0085 reste un contrôle historique du moteur d’union brut, séparé de la nouvelle politique.

La validation navigateur réelle avec un compte préfet ou direction limité n’est pas encore réalisée dans ce lot. Aucune certification globale des périmètres n’est prononcée. Les résultats CI et du déploiement sont indiqués dans la PR.

## Suite de l’audit

Vérifier séparément les sélecteurs et destinataires Communications, les assistants de saisie, les exports et accès par liens directs, les utilisateurs cumulant plusieurs rôles et les données conservées hors ligne. Chaque décision doit utiliser le périmètre de la permission concernée. Ne pas déduire un droit global du simple intitulé du rôle ou de l’absence de scopes.
