# Audit - Effectifs & depots

Date: 2026-08-26

## Constats initiaux

- Le tableau d'effectifs pouvait devenir noir et ne reveler ses donnees qu'apres survol sous Windows.
- Aucun perimetre commun ne reliait les effectifs, mouvements et depots.
- Les mouvements etaient limites a une liste sans recherche, filtre ni pagination reelle.
- Les exports utilisaient les effectifs globaux et perdaient le contexte de consultation.
- Le registre des depots ne respectait pas le cycle choisi.

## Decisions appliquees

- Retrait local de l'effet d'opacite Qt sur ce conteneur de donnees, cause du rendu noir Windows.
- Perimetre unique: Toute l'ecole, Maternelle, Primaire et Secondaire.
- Projections annuelles F/G/T pour inscrits, abandons, transferes et actifs.
- Mouvements filtres et pagines par le backend, sans fusion de plusieurs annees.
- Exports Excel/PDF filtres; PDF A4 paysage; action Imprimer via Windows.
- Depots filtres par le meme perimetre que l'ecran Effectifs.

## Limites volontairement conservees

- Les categories de mouvements reposent sur les evenements metier existants. Aucune nouvelle action de cycle de vie n'a ete inventee.
- Les depots restent saisissables uniquement dans l'annee ACTIVE, conformement a la regle existante.
