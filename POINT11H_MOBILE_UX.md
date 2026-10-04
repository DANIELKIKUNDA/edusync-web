# Point 11H — EduSync Mobile UX

## Objectif
Faire d’EduSync une vraie expérience téléphone, et non un simple desktop rétréci.

## Fermé dans ce lot
- navigation école mobile fixe à 4 entrées : Accueil, Élèves, Finance, Plus ;
- feuille mobile « Plus » donnant accès à tous les modules autorisés par RBAC ;
- navigation mobile dédiée Atelier Pro ;
- barre supérieure mobile compacte, année scolaire conservée et accès compte tactile ;
- safe areas et espace réservé à la navigation basse ;
- cibles tactiles renforcées et champs à 16 px ;
- paramètres transformés en navigation horizontale tactile ;
- tableaux métier conservés sans perte de colonnes, avec défilement horizontal tactile ;
- dialogues sensibles en bottom-sheet plein largeur sur téléphone ;
- héros/actions et onglets adaptés aux petits écrans ;
- aucun changement de règle métier, permission ou calcul.

## Doctrine
Sur desktop, les tableaux denses restent la surface canonique. Sur mobile, aucune colonne métier n’est supprimée silencieusement : le tableau devient scrollable. Les actions fréquentes sont accessibles au pouce ; les modules secondaires passent par « Plus ».

## Gate matériel restant
Le rendu doit encore être certifié sur un vrai navigateur/appareil Android après build Vite réel. Ce lot ferme le contrat UI/UX mobile dans le code, pas la certification matérielle.
