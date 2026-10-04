# Point 3B — Décision 02 : Administrateur système école

Statut : **PROPOSITION V1 — validation de Daniel requise**

## Doctrine proposée
L’Administrateur système école administre **le système de cette école** : configuration, comptes et rôles, sauvegardes, diagnostics, audit et synchronisation technique. Il ne reçoit pas automatiquement les pouvoirs métier d’un Caissier, Préfet, Gestionnaire, Intendant ou Responsable Finance.

Cette séparation évite le modèle dangereux `ADMIN = tout faire`. Si la même personne exerce aussi une fonction métier, elle reçoit un second rôle ou des capacités supplémentaires explicitement décidées.

## Couverture proposée
Total : **84 capacités** regroupées ci-dessous.

### Paramètres — 55 capacités
- `settings.school_identity.read` — Voir identité école
- `settings.school_identity.update` — Modifier identité école
- `settings.school_logo.update` — Modifier logo école
- `settings.academic_year.read` — Voir les années scolaires
- `settings.academic_year.create` — Créer/préparer une année
- `settings.academic_year.update` — Modifier une année préparée
- `settings.academic_year.activate` — Activer une année
- `settings.academic_year.close` — Clôturer une année
- `settings.academic_year.archive` — Archiver une année
- `settings.academic_year.reopen` — Réouvrir pour correction
- `settings.academic_year.copy_previous` — Reprendre la configuration précédente
- `settings.work_year.select` — Changer année de consultation
- `settings.structure.read` — Voir structure et classes
- `settings.sections.manage` — Activer/désactiver les sections
- `settings.options.manage` — Activer/désactiver les options
- `settings.option_tariff_group.manage` — Gérer groupes tarifaires options
- `settings.classes.create` — Ouvrir une classe
- `settings.classes.batch_create` — Créer plusieurs classes
- `settings.classes.rename` — Renommer une classe
- `settings.classes.activate` — Activer/désactiver une classe
- `settings.fee_types.read` — Voir types de frais
- `settings.fee_types.manage` — Créer/modifier un type de frais
- `settings.fee_types.activate` — Activer/désactiver un type de frais
- `settings.regulatory_fees.configure` — Configurer frais réglementaires
- `settings.tariffs.read` — Voir tarifs et barèmes
- `settings.tariffs.manage` — Créer/modifier un tarif
- `settings.tariff_groups.manage` — Gérer barèmes de groupe
- `settings.tariffs.apply` — Appliquer les barèmes aux classes
- `settings.tariffs.copy_year` — Copier les barèmes vers une autre année
- `settings.billing_months.manage` — Configurer les mois de facturation
- `settings.enrollment_policy.read` — Voir conditions d’inscription
- `settings.enrollment_policy.manage` — Créer/modifier les conditions
- `settings.enrollment_policy.activate` — Activer/désactiver une condition
- `settings.enrollment_policy.review` — Valider la revue des conditions
- `settings.benefits.read` — Voir politiques sociales
- `settings.benefits.manage` — Configurer famille nombreuse / enfant du personnel
- `settings.payment_policy.read` — Voir règles d’encaissement
- `settings.payment_policy.manage` — Modifier modes/acomptes/fonds/paiements futurs
- `settings.contributions.read` — Voir contributions configurées
- `settings.contributions.manage` — Créer/modifier une contribution
- `settings.contributions.activate` — Activer/désactiver une contribution
- `settings.products.read` — Voir catalogue des articles vendus
- `settings.products.manage` — Créer/modifier un article vendu
- `settings.products.activate` — Activer/désactiver un article
- `settings.documents.read` — Voir paramètres documents
- `settings.documents.manage` — Modifier préfixes/reçus/logo/signature
- `settings.backups.read` — Voir paramètres sauvegarde
- `settings.backups.manage` — Modifier politique sauvegarde
- `settings.backups.create` — Créer une sauvegarde maintenant
- `settings.backups.test` — Tester une sauvegarde
- `settings.backups.restore` — Restaurer une sauvegarde
- `settings.documents.history.read` — Voir historique des documents
- `settings.diagnostics.read` — Voir diagnostic système
- `settings.diagnostics.export` — Exporter diagnostic
- `settings.document_root.manage` — Choisir dossier documentaire

### Utilisateurs & accès — 11 capacités
- `access.users.read` — Voir les utilisateurs
- `access.users.create` — Créer un utilisateur
- `access.users.update` — Modifier un utilisateur
- `access.users.activate` — Activer/désactiver un utilisateur
- `access.users.pin.self_change` — Changer son propre code secret
- `access.users.credentials.reset` — Réinitialiser les identifiants d’un utilisateur
- `access.roles.read` — Voir rôles et permissions
- `access.roles.manage` — Créer/modifier un rôle
- `access.permissions.assign` — Attribuer/retirer des permissions à un rôle
- `access.scopes.assign` — Attribuer un périmètre à une affectation
- `access.grants.exception` — Créer une exception individuelle temporaire

### Audit — 4 capacités
- `audit.school.read` — Consulter le journal d’audit école
- `audit.school.filter` — Filtrer/rechercher les événements
- `audit.school.export` — Exporter le journal d’audit
- `audit.entity.history.read` — Voir l’historique d’une entité

### Notifications internes — 5 capacités
- `notifications.internal.read` — Voir ses notifications internes
- `notifications.internal.read_all` — Voir toutes les notifications autorisées
- `notifications.internal.create` — Créer une notification interne
- `notifications.internal.dismiss` — Marquer/archiver une notification
- `notifications.internal.configure` — Configurer les règles internes

### Synchronisation technique — 6 capacités
- `sync.status.read` — Voir état de synchronisation
- `sync.device.register` — Enregistrer un appareil
- `sync.device.revoke` — Révoquer un appareil
- `sync.conflicts.read` — Voir les conflits de synchronisation
- `sync.conflicts.resolve` — Résoudre un conflit autorisé
- `sync.finance.quarantine.read` — Voir opérations/charges en quarantaine

### Documents techniques — 3 capacités
- `documents.history.read` — Voir historique des documents générés
- `documents.open` — Ouvrir un document généré
- `documents.regenerate` — Régénérer un document depuis les données

## Exclusions par défaut
- Aucun encaissement, annulation de paiement, dépense de caisse ou décision financière.
- Aucune création/modification d’élève ou d’inscription.
- Aucune mutation du personnel.
- Aucune entrée/sortie/correction de stock ou inventaire.
- Aucun SMS/communiqué externe par défaut.
- Pas d’armement Finance offline, de réconciliation financière ni de résolution de quarantaine financière.

## Opérations critiques incluses mais protégées
Certaines opérations techniques restent nécessaires à un administrateur système — par exemple restauration de sauvegarde, réouverture d’année ou gestion des accès. La permission seule ne suffit jamais à contourner les invariants : ces use cases restent audités, nécessitent confirmation/motif et peuvent recevoir un contrôle de double validation lors de leur implémentation finale.

## Décision attendue
Daniel peut valider ce modèle, retirer des capacités ou en ajouter. Tant qu’il ne l’a pas validé, `ADMIN_SYSTEME_ECOLE` reste `DRAFT` et non affectable.
