# Implementation - Effectifs & depots

## UI/UX

- En-tete compact avec selecteur de cycle et actions Excel, PDF, Imprimer.
- Trois KPI: eleves actifs, classes actives, moyenne par classe.
- Onglets: Par classe, Par section, Par filiere / option, Mouvements.
- Grille native Qt sans effet d'opacite parent afin d'eviter le viewport noir Windows.

## Donnees

- `enrollment_counts(year_id, scope)` retourne les indicateurs F/G/T de chaque statut annuel.
- `enrollment_movements_summary(...)` filtre par annee, cycle, classe, type, recherche et pagine les lignes.
- Le cycle filtre aussi les classes disponibles et les lignes du registre de depots.

## Documents

- `app/services/effectifs_exports.py` produit les exports filtres par classe, section ou filiere.
- Excel contient titre, perimetre, F/G/T et total general.
- PDF est en A4 paysage et comporte les memes donnees.
- Imprimer genere le PDF courant puis le transmet a Windows/Foxit par le service documentaire existant.

## Fichiers principaux

- `app/db/terrain.py`
- `app/ui/terrain_pages.py`
- `app/services/effectifs_exports.py`
- `scripts/certify_effectifs_depots_windows.py`
- `tests/test_effectifs_depots_final.py`
