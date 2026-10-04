# Recette Windows - Effectifs & depots

Resolution: 1366x768. Base: SQLite temporaire isolee.

| Parcours | Resultat | Preuve |
|---|---|---|
| Vue Effectifs avec menu lateral complet | PASS | `01_effectifs_toute_ecole.png` |
| Perimetre Primaire applique aux KPI et a la grille | PASS | `02_effectifs_primaire.png` |
| Filtre Transfert hors perimetre: etat vide explicite | PASS | `03_mouvements_filtres.png` |
| Perimetre Secondaire + Transfert: une ligne reelle | PASS | `04_mouvements_secondaire.png` |
| Registre depots filtre par Secondaire | PASS | `05_depots_materiels.png` |
| Export Excel filtre Primaire | PASS | `effectifs_primaire.xlsx` |
| Export PDF A4 paysage filtre Primaire | PASS | `effectifs_primaire.pdf` |

Controles techniques PASS:

- barre laterale visible;
- tableau par classe visible et non noir;
- lignes, KPI et mouvements lies au seul perimetre actif;
- pagination activee et boutons dependants de la page;
- registre de depots visible et filtre;
- PDF et Excel non vides et lisibles.

La base de production n'a pas ete ouverte ni modifiee. La recette cree et supprime sa base temporaire.
