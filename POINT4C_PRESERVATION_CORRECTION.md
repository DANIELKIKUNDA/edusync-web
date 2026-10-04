# Point 4C — Correction de préservation Desktop -> Web

Date : 2026-09-12
Statut : **CORRECTION APPLIQUÉE — l'ancien checkpoint Point 4C est supersédé**

## Motif

Le premier port Web avait préservé le métier mais avait simplifié les sorties PDF/Excel de l'annuaire Élèves/Familles. C'était contraire au contrat de préservation du projet : un module Desktop déjà certifié ne doit pas être réinventé dans sa présentation métier.

## Source canonique relue

La correction a été faite en repartant du code Desktop certifié, notamment :

- `app/services/schooling_exports.py` pour l'identité école, logo, couleurs, tableau, PDF et XLSX ;
- `app/ui/schooling_page.py::_student_export_rows` et `export_students` pour les colonnes, l'ordre et les filtres ;
- les vues familles de `schooling_page.py` pour le répertoire général et les vues Famille nombreuse / Bénéficiaires / Enfants du personnel.

## Annuaire élèves — contrat canonique restauré

Titre : `LISTE DES ÉLÈVES`.

Colonnes, dans cet ordre exact :

1. N°
2. Matricule
3. Élève
4. Sexe
5. Année
6. Section
7. Classe
8. Date naissance
9. Lieu naissance
10. Responsable / foyer
11. Téléphone
12. Statut

Filtres de sortie préservés : Année/Périmètre historique, Section, Classe, Statut, Sexe.

En-tête restauré : logo si disponible, nom de l'école, adresse/ville/province, téléphone, e-mail, titre, filtres, date d'édition et total. En-tête de tableau bleu `#175CD3`, texte blanc, alternance légère des lignes, PDF A4 paysage et XLSX avec ligne d'en-tête gelée/filtrable.

## Répertoire familles — contrat canonique restauré

Colonnes : `Code famille`, `Famille / foyer`, `Responsable principal`, `Téléphone`, `Adresse`, `Enfants inscrits`.

Les vues spécialisées Desktop restent des contrats distincts à conserver :

- Familles éligibles ;
- Bénéficiaires réels ;
- Enfants du personnel.

La famille/le foyer reste distinct du responsable. Le nom de foyer peut être généré automatiquement ; aucune fusion automatique n'est autorisée sur simple ressemblance de nom ou téléphone.

## Inscription — correction terrain

Le socle obligatoire par défaut devient exactement :

- Nom ;
- Postnom ;
- Prénom ;
- Sexe ;
- Classe.

La date de naissance, le lieu de naissance et les autres informations complémentaires restent non bloquants par défaut et peuvent être complétés ultérieurement. Une école peut rendre un champ additionnel obligatoire via sa politique d'inscription explicite.

## Renforcements non destructifs conservés

- `school_id` + RLS ;
- scopes Section/Classe ;
- idempotence ;
- concurrence optimiste ;
- audit ;
- outbox ;
- résolution assistée de foyer ;
- libellé automatique du foyer ;
- recherche transverse ;
- complétion ultérieure des fiches.

Aucun de ces renforcements ne modifie le format métier canonique des documents.
