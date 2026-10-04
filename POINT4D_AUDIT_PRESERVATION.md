# EduSync — Point 4D — Audit de préservation Effectifs & Dépôts

Date : 2026-09-12  
Doctrine : **Desktop certifié = oracle métier et documentaire. Copier avant d'enrichir.**

## Sources Desktop certifiées relues

Le checkpoint embarque les cinq preuves canoniques dans `preservation/effectifs_depots_desktop_certified/` : audit, rapport d'implémentation, validation PDF, validation Excel et recette Windows 1366×768.

Les contrats gelés sont les suivants :

- périmètre commun `Toute l'école / Maternelle / Primaire / Secondaire` ;
- trois KPI : élèves actifs, classes actives, moyenne par classe ;
- vues `Par classe / Par section / Par filière-option / Mouvements` ;
- quatre groupes annuels avec projection F/G/T : `Inscrits / Abandons / Transférés / Élèves actifs` ;
- même année scolaire dans chaque calcul : aucun mélange multi-années ;
- mouvements filtrables, recherchables et paginés ;
- registre des dépôts soumis au même périmètre ;
- dépôt matériel saisissable uniquement dans l'année `ACTIVE` ;
- PDF des effectifs : A4 paysage, identité école, logo si disponible, titre, périmètre, tableau groupé, total général ;
- Excel des effectifs : feuille `Par classe`, identité, titres groupés sur deux niveaux, **14 colonnes** pour la vue classe, total général ;
- l'impression utilise le PDF courant ;
- aucune nouvelle catégorie de mouvement n'est inventée.

## Décision de portage Web

Aucun tableau certifié n'a été remplacé par une nouvelle présentation métier. Les enrichissements ajoutés sont exclusivement techniques : `school_id`, RLS, scopes RBAC, idempotence des dépôts, audit/outbox, responsive Web et cache/transport PWA ultérieur.

## Dépôts matériels

Le Web introduit `material_contributions` comme registre append-only parce que la nouvelle base PostgreSQL ne possédait pas encore la table transactionnelle correspondante. Une saisie ajoute un événement de dépôt ; elle n'écrase pas l'historique. Aucun stock attendu, prix ou achat n'a été inventé dans ce lot.

## Point 4C corrigé conservé

La migration 0015 ne modifie la politique d'inscription que lorsqu'elle correspond exactement à l'ancien défaut : sexe ajouté aux champs obligatoires, date/lieu de naissance maintenus facultatifs. Une politique école déjà personnalisée n'est pas écrasée.
