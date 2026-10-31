# Passe « mobile d'abord » — rapport (31/10/2026, pile locale)

Demande du propriétaire : « comme un logiciel d'une très grande entreprise américaine ou européenne, pensé mobile first ;
parcours chaque page, chaque rôle » ; la barre du bas « seule des onglets » à refaire ; les petites cartes « en bloc de 4 :
2 × 2 », jamais en une seule colonne. Branche : `claude/mobile-first-pass`. Aucune fusion, aucun déploiement, aucune PR.

## Références suivies

- Material 3, barre de navigation : 3 à 5 destinations, indicateur actif, libellés courts toujours visibles.
- Apple HIG, barres d'onglets : la barre sert à naviguer, pas à agir ; une entrée « Plus » pour le reste, à limiter.
- Tableaux sur téléphone : une carte par fiche quand on lit les éléments un par un ; jamais de défilement de toute la page.

## Mesure (robot `frontend/browser-tests/local_mobile_audit.mjs`, 12 rôles, 86 écrans, téléphone 390 × 844)

| Mesure | Avant | Après |
|---|---|---|
| Écrans où le titre est répété (2 à 4 fois) | presque tous | **0** |
| Débordement horizontal, tableaux coupés | 0 | **0** |
| Premier contenu sous la ligne de flottaison (> 700 px) | ~25 écrans (Élèves 883–933 px, Effectifs 857–958 px, Synchronisation 1 067 px) | **1** (Élèves du caissier, 740 px) |
| Barre du bas adaptée au rôle | non (mêmes 4 entrées pour tous ; Intendant et administrateur sans module de travail) | **oui, pour les 12 rôles** |

Barre du bas obtenue (Accueil + 3 modules + « Plus ») : Intendant → Intendance, Documents, Personnel ; directeurs → Effectifs,
Élèves, Personnel ; caissier → Finance, Élèves, Effectifs ; secrétariat → Élèves, Effectifs, Documents ; administrateur →
Accès, Réglages, Documents ; gestionnaire et promoteur → Finance, Intendance, Effectifs ; responsable financier → Finance,
Effectifs, Documents. Règle : les modules où le membre travaille le plus, lus dans ce que le serveur projette déjà pour lui
(cartes d'accueil et raccourcis) — jamais le nom du rôle.

## Ce qui a changé (téléphone uniquement, < 768 px ; l'ordinateur est inchangé)

| Élément | Avant | Après |
|---|---|---|
| Barre du bas | Accueil, Élèves, Finance, Documents, Menu pour tous | Destinations du rôle, ordre d'importance, indicateur « pilule » sur l'onglet actif, zone de geste respectée |
| « Menu » | Tiroir latéral, liste | « Plus » : feuille qui monte du bas, grille de tuiles avec icônes |
| Titre | Barre du haut + ligne « ‹ Module » + en-tête du module (2 à 4 fois) | Une seule fois (barre du haut) ; l'en-tête garde la description (2 lignes) et les actions |
| Petites cartes de chiffres | Une colonne verticale de grandes cartes | **Blocs 2 × 2** compacts (chiffre puis libellé) ; une carte impaire prend toute la ligne ; sur l'accueil, les petites cartes côte à côte, celles qui portent une liste ou un graphique en pleine largeur |
| Onglets | À moitié cachés | Défilement au doigt, onglet touché ramené au centre, barre d'onglets du module maintenue sous la barre du haut |
| Tableaux et grilles | Coupés à droite (recouvrement mensuel, alertes de stock, annuaire du personnel) | Une carte par fiche, libellé de chaque colonne à gauche, valeur à droite |
| Fenêtres (formulaires) | Boîtes centrées | Feuilles du bas, boutons d'action fixés en bas |
| Cibles tactiles, champs | Boutons < 44 px, zoom au toucher d'un champ (iOS) | 44 px minimum, champs en 16 px |
| Boutons « PDF / Excel » du recouvrement | Carrés vides (texte masqué, sans icône) | Libellés visibles |

Fichiers : `frontend/src/platform/mobile.css` (règles mobiles), `frontend/src/platform/mobile_enhance.ts` (tableaux en
cartes, onglet centré), `frontend/src/App.tsx` (choix de la barre), `frontend/src/platform/shell.tsx` (barre et « Plus »).

## Extension du 31/10 : plateforme et « Encaisser »

- **Plateforme EduSync** (Manager Système), même passe pour un système homogène : audit des 8 modules (robot étendu,
  connexion avec le second facteur de test local) — titre répété 0 (avant : 7 modules sur 8), cibles tactiles trop petites
  0 (avant : 25 sur Écoles) ; barre du bas Pilotage · Écoles · Accès · Équipe · Plus (avant : « Tableau », « Utilisateurs »
  tronqués, 3 destinations) ; même feuille « Plus ».
- **« Encaisser »** : pour qui encaisse (raccourci « Nouvel encaissement » accordé par le serveur), l'entrée finance de la
  barre s'appelle « Encaisser » et ouvre directement l'encaissement, même si le Centre financier est déjà ouvert sur un
  autre onglet. Caissier : Accueil · Encaisser · Élèves · Effectifs · Plus.
- **Indicateur actif** : une ancienne règle globale (`nav button>span`) écrasait la pastille de l'onglet actif dans les deux
  espaces ; corrigé. L'icône « Plus » devient « ••• » (elle ressemblait à celle du tableau de bord de la plateforme).

## Non-régression

| Recette | Résultat |
|---|---|
| Quatre rôles (Intendant, directeurs, secrétariat) — `local_three_roles_certification.mjs` | **46/46** |
| Rôles financiers — `local_finance_roles_certification.mjs` (navigation mobile alignée : module hors barre → « Plus ») | **25/25** |
| Hors ligne caissier / autres rôles | **10/10**, **6/6** |
| Tests frontend | **91/91** |

## Restes connus

- Les barres du graphique de recouvrement sont des cibles fines (données d'un graphique) ; trois champs de la
  Communication mesurent moins de 40 px.
- Élèves du caissier : premier contenu à 740 px (en-tête, chiffres et recherche avant la liste).
- Un essai sur un vrai téléphone reste recommandé.
