# Point 11I — Mobile workflows métier

Cette passe complète le shell mobile du Point 11H par une adaptation métier des écrans à forte fréquence.

- Finance : recherche tactile, frais sous forme de lignes-cartes, montant remis, choix avance, total et action d'encaissement sticky au-dessus de la navigation mobile.
- Élèves/Familles : KPIs horizontaux, répertoire élève en cartes sur téléphone, familles mono-colonne, fiche/drawer plein écran, pagination tactile.
- Personnel : filtres et formulaires mono-colonne, fiches plein écran, affectations tactiles.
- Effectifs : KPIs horizontaux, filtres mono-colonne et actions export tactiles; les registres conservent leurs colonnes métier.
- Intendance : synthèse mobile puis registres complets avec défilement horizontal contrôlé, sans suppression de colonnes.
- Documents : actions adaptées au tactile et aperçu conservé avant impression.

Doctrine : mobile-first pour l'interaction, parité métier avec Desktop/Web pour les données. Aucune colonne ou règle métier n'est supprimée pour « faire tenir » un écran.

La certification visuelle sur Android réel et le build Vite restent des gates machine : ils ne sont pas déclarés PASS sans exécution réelle.
