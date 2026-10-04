# Point 4C — Audit de préservation Élèves / Familles / Inscriptions

Date : 2026-09-12

## Verdict

Le module Desktop est un actif mature à **préservation très forte**. Le port Web ne remplace pas le métier : il conserve l'identité permanente de l'élève, l'inscription annuelle, le foyer permanent, la réinscription sans duplication, les familles multi-enfants, la famille nombreuse avec bénéficiaire explicite, le lien enfant-agent explicite, l'historique de statut, les recherches, filtres et exports.

## Invariants Desktop conservés

- `student` = identité permanente ; `enrollment` = inscription annuelle.
- un élève existant garde son foyer permanent lors d'une réinscription ; aucune reliaison silencieuse ;
- batch familial tout-ou-rien dans une transaction ;
- matricule élève et code foyer générés automatiquement ;
- plusieurs enfants peuvent être inscrits/réinscrits dans une même session ;
- famille nombreuse calculée sur les enfants éligibles, mais bénéficiaire explicitement sélectionné ;
- enfant d'agent : lien explicite avec l'agent, jamais inféré depuis le nom/téléphone du responsable ;
- abandon, transfert, réintégration et changement de classe historisés ;
- données historiques et anciennes dettes ne sont jamais fusionnées dans une nouvelle inscription ;
- annuaires, profils, familles et exports restent filtrables.

## Améliorations Web décidées après audit

### 1. Inscription terrain-first

Par défaut, seules quatre informations saisies par l'opérateur bloquent une nouvelle inscription :

1. Nom ;
2. Postnom ;
3. Prénom ;
4. Classe.

Date de naissance, lieu de naissance, sexe, nationalité, adresse et école de provenance sont non bloquants. Ils sont visibles comme « à compléter » et peuvent être enrichis plus tard par un utilisateur autorisé.

Une école peut explicitement renforcer sa politique `ENROLLMENT` et rendre un champ supplémentaire obligatoire. Le défaut global reste minimal ; le logiciel ne rend pas arbitrairement obligatoire une donnée que le parent peut ignorer le jour de l'inscription.

### 2. Foyer et responsable sont deux concepts distincts

Le foyer possède son propre identifiant/code permanent. Le responsable est une personne de contact canonique distincte, reliée au foyer par `family_guardians`. Un foyer peut avoir plusieurs responsables ; un seul responsable principal actif est autorisé à la fois.

Le **nom affiché du foyer est généré automatiquement** :

- `Foyer de <responsable principal>` si un responsable est connu ;
- sinon `Foyer <nom complet du premier enfant>` ;
- les imports historiques sans contact restent visibles avec état `TO_COMPLETE` ; aucune identité n'est inventée.

### 3. Résolution de foyer assistée, jamais fusion silencieuse

La recherche accepte code foyer, responsable, téléphone, matricule ou identité élève. Un numéro partagé ou un nom identique reste ambigu ; le système propose des candidats et l'opérateur confirme. Aucune fusion automatique n'est déclenchée par une ressemblance de nom ou de téléphone.

### 4. Périmètres et confidentialité

Les listes, profils, mutations et exports respectent le périmètre RBAC effectif (école / section / classe). Un chef de section ne peut pas deviner un UUID pour accéder à un élève ou un foyer hors périmètre. Les enfants hors périmètre ne sont pas exposés dans la fiche foyer.

### 5. Documents et exports

Préservés/enrichis :

- annuaire élèves PDF ;
- annuaire élèves Excel ;
- répertoire familles PDF ;
- répertoire familles Excel ;
- fiche élève PDF.

Les sorties de démonstration ont été générées puis rendues en image pour contrôle visuel ; le premier rendu de l'annuaire a révélé un chevauchement de cellules, corrigé en imposant des cellules `Paragraph` avec largeurs bornées et retour à la ligne.

## Dette volontaire reportée

Les imports seront industrialisés au Point 5 : staging, prévisualisation, rapprochement assisté, idempotence et lots audités. Ils ne doivent pas créer artificiellement un responsable manquant.
