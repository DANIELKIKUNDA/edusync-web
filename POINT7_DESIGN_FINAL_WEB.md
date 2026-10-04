# Point 7 — Design final Web

## Décision
Refonte visuelle transversale sans modification des contrats métier certifiés. Doctrine: tables-first, densité professionnelle, cartes compactes, actions visibles, données numériques alignées, responsive et reduced-motion.

## Changements
- shell ramené à 220 px pour libérer l'espace métier;
- largeur de travail portée à 1920 px;
- en-tête compact et suppression du badge de lot technique dans l'application école;
- panneaux, KPI et contrôles densifiés;
- tableaux HTML et grilles métier prioritaires, hover discret, en-têtes sticky lorsque possible;
- tokens visuels harmonisés (surfaces, lignes, rayon, ombres, texte secondaire);
- boutons et formulaires plus compacts;
- navigation moins décorative;
- règles responsive 1100/800/520 px;
- `prefers-reduced-motion` respecté;
- aucun changement de calcul, permission, export, dette, encaissement ou contrat documentaire.

## Gate
Le Point 7 est un candidat design local. La validation pixel/rendu navigateur Windows reste requise. Le build frontend complet dépend de l'installation des dépendances npm.

## Validation locale
- Backend: 291/291 tests PASS.
- Python compileall: PASS.
- Frontend build: non exécuté dans ce checkpoint car dépendances npm non installées.
