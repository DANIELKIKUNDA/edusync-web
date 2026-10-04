# Point 3A — Catalogue exhaustif des capacités EduSync (draft audit)

**Capacités fonctionnelles recensées : 258**

Ce catalogue ne fixe encore aucun rôle. Toutes les affectations restent `UNDECIDED_BY_OWNER` : Daniel décide au Point 3B.

Chaque capacité possède un code stable, un domaine, un sous-groupe, une politique offline, un niveau de risque, un indicateur d’audit et des sorties éventuelles.

## Atelier Pro
### Écoles
- `platform.schools.read` — Voir les écoles de la plateforme · risque **MEDIUM** · offline `SERVER_ONLY`
- `platform.schools.create` — Créer une école · risque **HIGH** · offline `SERVER_ONLY` · audit
- `platform.schools.update` — Modifier l’identité technique d’une école · risque **HIGH** · offline `SERVER_ONLY` · audit
- `platform.schools.activate` — Activer une école · risque **HIGH** · offline `SERVER_ONLY` · audit
- `platform.schools.suspend` — Suspendre une école · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `platform.school_admin.bootstrap` — Créer/réinitialiser l’administrateur initial d’une école · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `platform.health.read` — Voir l’état technique des écoles · risque **MEDIUM** · offline `SERVER_ONLY`
- `platform.audit.read` — Consulter l’audit de plateforme · risque **HIGH** · offline `SERVER_ONLY`
- `platform.audit.export` — Exporter l’audit de plateforme · risque **HIGH** · offline `SERVER_ONLY`

## Audit
### Audit transversal
- `audit.school.read` — Consulter le journal d’audit école · risque **HIGH** · offline `SERVER_ONLY`
- `audit.school.filter` — Filtrer/rechercher les événements · risque **HIGH** · offline `SERVER_ONLY`
- `audit.school.export` — Exporter le journal d’audit · risque **HIGH** · offline `SERVER_ONLY` · sorties XLSX,PDF
- `audit.entity.history.read` — Voir l’historique d’une entité · risque **HIGH** · offline `SERVER_ONLY`

## Centre financier
### Analyses
- `finance.analysis.by_fee.read` — Analyser par type de frais · risque **MEDIUM** · offline `READ_CACHE`
- `finance.analysis.by_cashier.read` — Analyser par caissier · risque **HIGH** · offline `READ_CACHE`
- `finance.analysis.advance.read` — Analyser les fonds anticipés · risque **HIGH** · offline `READ_CACHE`

### Anciennes dettes
- `finance.old_debt.read` — Voir les anciennes dettes · risque **MEDIUM** · offline `READ_CACHE`
- `finance.old_debt.collect` — Encaisser une ancienne dette · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit

### Articles scolaires
- `finance.products.read` — Voir les articles scolaires · risque **LOW** · offline `READ_CACHE`
- `finance.products.manage` — Configurer les articles scolaires · risque **HIGH** · offline `READ_CACHE` · audit
- `finance.products.sale` — Vendre et encaisser un article · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.products.sales_report.read` — Voir le rapport des ventes · risque **MEDIUM** · offline `READ_CACHE`

### Caisse
- `finance.cash.read` — Voir la caisse du jour · risque **MEDIUM** · offline `READ_CACHE`
- `finance.cash.open` — Ouvrir sa caisse · risque **HIGH** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.cash.expense.create` — Enregistrer une dépense de caisse · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.cash.close` — Clôturer sa caisse · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.cash.reopen` — Réouvrir une caisse · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.cash.other.read` — Voir les autres caisses · risque **HIGH** · offline `READ_CACHE`
- `finance.cash.journal.print` — Imprimer le journal de caisse · risque **HIGH** · offline `READ_CACHE` · sorties PDF
- `finance.cash.journal.export_pdf` — Exporter le journal de caisse PDF · risque **HIGH** · offline `READ_CACHE` · sorties PDF

### Décisions financières
- `finance.decisions.read` — Voir les décisions financières · risque **HIGH** · offline `READ_CACHE`
- `finance.decisions.create` — Créer réduction/exonération/faveur · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.decisions.cancel` — Annuler une décision financière · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.responsibility.read` — Voir les responsabilités financières prévues · risque **HIGH** · offline `READ_CACHE`
- `finance.responsibility.set` — Définir famille/paie/tiers responsable · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.credits.read` — Voir crédits et trop-perçus · risque **HIGH** · offline `READ_CACHE`

### Encaissements & reçus
- `finance.dashboard.read` — Voir le tableau de bord financier · risque **LOW** · offline `READ_CACHE`
- `finance.checkout.search` — Rechercher élève/famille à encaisser · risque **LOW** · offline `READ_CACHE`
- `finance.checkout.balance.read` — Voir charges, payé et reste · risque **MEDIUM** · offline `READ_CACHE`
- `finance.checkout.recommend` — Calculer le paiement recommandé · risque **MEDIUM** · offline `READ_CACHE`
- `finance.checkout.allocate.preview` — Prévisualiser les allocations · risque **MEDIUM** · offline `READ_CACHE`
- `finance.checkout.collect` — Encaisser un paiement · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.checkout.family.collect` — Encaisser un panier familial · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.checkout.offline_cash` — Encaisser CASH hors connexion sous autorisation · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.receipts.read` — Voir les reçus · risque **MEDIUM** · offline `READ_CACHE`
- `finance.receipts.print` — Imprimer un reçu · risque **HIGH** · offline `READ_CACHE` · sorties PDF
- `finance.receipts.reprint` — Réimprimer un reçu/duplicata · risque **HIGH** · offline `READ_CACHE` · audit · sorties PDF
- `finance.payments.history.read` — Voir l’historique des paiements · risque **MEDIUM** · offline `READ_CACHE`
- `finance.payments.reverse` — Annuler/corriger un paiement par workflow officiel · risque **CRITICAL** · offline `READ_CACHE` · audit

### Fonds anticipés
- `finance.advance_funds.read` — Voir les fonds anticipés · risque **MEDIUM** · offline `READ_CACHE`
- `finance.advance_funds.receive` — Recevoir un fonds anticipé · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit
- `finance.advance_funds.allocate` — Imputer un fonds anticipé · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.advance_funds.refund` — Rembourser un fonds anticipé non imputé · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `finance.advance_funds.receipt.print` — Imprimer reçu de fonds anticipé · risque **HIGH** · offline `READ_CACHE` · audit · sorties PDF

### Plans anticipés
- `finance.anticipation_plans.read` — Voir les plans anticipés · risque **MEDIUM** · offline `READ_CACHE`
- `finance.anticipation_plans.manage` — Créer/modifier/activer un plan anticipé · risque **HIGH** · offline `READ_CACHE` · audit
- `finance.anticipation_membership.set` — Enregistrer adhésion/refus parent · risque **HIGH** · offline `READ_CACHE` · audit
- `finance.anticipation.collect` — Encaisser selon un plan anticipé · risque **CRITICAL** · offline `PREAUTHORIZED_CRITICAL` · audit

### Rapports
- `finance.reports.daily.generate` — Générer rapport financier journalier · risque **HIGH** · offline `READ_CACHE` · audit
- `finance.reports.periodic.generate` — Générer rapport financier périodique · risque **HIGH** · offline `READ_CACHE` · audit
- `finance.reports.periodic.export_pdf` — Exporter rapport périodique PDF · risque **HIGH** · offline `READ_CACHE` · audit · sorties PDF
- `finance.reports.periodic.export_xlsx` — Exporter rapport périodique Excel · risque **HIGH** · offline `READ_CACHE` · audit · sorties XLSX
- `finance.reports.history.read` — Voir l’historique des rapports · risque **MEDIUM** · offline `READ_CACHE`

### Vues & recouvrement
- `finance.views.vf01.read` — Voir registre financier détaillé VF-01 · risque **MEDIUM** · offline `READ_CACHE`
- `finance.views.vf01.export_xlsx` — Exporter VF-01 Excel · risque **MEDIUM** · offline `READ_CACHE` · sorties XLSX
- `finance.views.vf01.export_pdf` — Exporter VF-01 PDF officiel · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
- `finance.views.vf01.print` — Imprimer VF-01 · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
- `finance.views.vf02.read` — Voir synthèse classe VF-02 · risque **MEDIUM** · offline `READ_CACHE`
- `finance.views.vf03.read` — Voir synthèse section VF-03 · risque **MEDIUM** · offline `READ_CACHE`
- `finance.views.vf04.read` — Voir synthèse école VF-04 · risque **MEDIUM** · offline `READ_CACHE`
- `finance.views.summaries.export_xlsx` — Exporter les synthèses VF-02/VF-03/VF-04 · risque **MEDIUM** · offline `READ_CACHE` · sorties XLSX
- `finance.recovery.monthly.read` — Voir le suivi mensuel de recouvrement · risque **MEDIUM** · offline `READ_CACHE`
- `finance.recovery.historical.read` — Voir le recouvrement historique · risque **MEDIUM** · offline `READ_CACHE`

## Documents
### Historique & sorties
- `documents.history.read` — Voir historique des documents générés · risque **LOW** · offline `READ_CACHE`
- `documents.open` — Ouvrir un document généré · risque **LOW** · offline `READ_CACHE`
- `documents.print` — Imprimer un document · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit · sorties PDF
- `documents.regenerate` — Régénérer un document depuis les données · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit · sorties PDF,XLSX
- `documents.receipts.bundle.print` — Imprimer un lot familial de reçus · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit · sorties PDF
- `documents.student_import_template.export` — Exporter le modèle d’import élèves · risque **LOW** · offline `LOCAL_WRITE_SYNC` · sorties XLSX

## Effectifs & dépôts
### Dépôts matériels
- `contributions.read` — Voir les dépôts matériels · risque **LOW** · offline `READ_CACHE`
- `contributions.record` — Enregistrer un dépôt matériel élève · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `contributions.register.read` — Voir le registre des contributions · risque **LOW** · offline `READ_CACHE`
- `contributions.register.export_xlsx` — Exporter le registre des contributions · risque **LOW** · offline `READ_CACHE` · sorties XLSX

### Effectifs
- `headcounts.read` — Voir les effectifs · risque **LOW** · offline `READ_CACHE`
- `headcounts.by_class.read` — Voir les effectifs par classe · risque **LOW** · offline `READ_CACHE`
- `headcounts.by_section.read` — Voir les effectifs par section · risque **LOW** · offline `READ_CACHE`
- `headcounts.by_option.read` — Voir les effectifs par filière/option · risque **LOW** · offline `READ_CACHE`
- `headcounts.movements.read` — Voir les mouvements d’effectifs · risque **LOW** · offline `READ_CACHE`
- `headcounts.export_xlsx` — Exporter les effectifs Excel · risque **LOW** · offline `READ_CACHE` · sorties XLSX
- `headcounts.export_pdf` — Exporter les effectifs PDF · risque **LOW** · offline `READ_CACHE` · sorties PDF
- `headcounts.print` — Imprimer les effectifs · risque **LOW** · offline `READ_CACHE` · sorties PDF

## Intendance
### Biens durables
- `inventory.assets.read` — Voir biens durables · risque **LOW** · offline `READ_CACHE`
- `inventory.assets.create` — Enregistrer un bien durable · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.assets.update` — Modifier fiche/localisation du bien · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.assets.status.update` — Modifier état du bien · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.assets.repair.record` — Enregistrer une réparation · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.assets.history.read` — Voir historique du bien · risque **MEDIUM** · offline `READ_CACHE`

### Inventaires
- `inventory.counts.read` — Voir inventaires · risque **LOW** · offline `READ_CACHE`
- `inventory.counts.create` — Créer un inventaire · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.counts.record` — Saisir comptage inventaire · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.counts.validate` — Valider un inventaire · risque **HIGH** · offline `SERVER_ONLY` · audit
- `inventory.counts.print` — Imprimer inventaire · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
- `inventory.counts.export_xlsx` — Exporter inventaire Excel · risque **MEDIUM** · offline `READ_CACHE` · sorties XLSX

### Stocks
- `inventory.stock.read` — Voir stocks consommables · risque **LOW** · offline `READ_CACHE`
- `inventory.stock.item.manage` — Créer/modifier un article de stock · risque **MEDIUM** · offline `READ_CACHE`
- `inventory.stock.receive` — Enregistrer une entrée de stock · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.stock.issue` — Enregistrer une sortie de stock avec motif/destination · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.stock.adjust` — Corriger un stock par mouvement justifié · risque **CRITICAL** · offline `LOCAL_WRITE_SYNC` · audit
- `inventory.stock.movements.read` — Voir mouvements de stock · risque **MEDIUM** · offline `READ_CACHE`
- `inventory.stock.low_alerts.read` — Voir alertes de stock faible · risque **LOW** · offline `READ_CACHE`
- `inventory.stock.sheet.print` — Imprimer fiche de stock · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
- `inventory.stock.export_xlsx` — Exporter stocks/mouvements Excel · risque **MEDIUM** · offline `READ_CACHE` · sorties XLSX

## Migration & import
### Imports
- `migration.template.download` — Télécharger modèle Excel d’import · risque **LOW** · offline `LOCAL_WRITE_SYNC` · sorties XLSX
- `migration.students.analyze` — Analyser un fichier élèves · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC`
- `migration.students.simulate` — Simuler un import · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC`
- `migration.students.execute` — Importer les élèves · risque **HIGH** · offline `SERVER_ONLY` · audit
- `migration.historical.stage` — Stager un import historique · risque **HIGH** · offline `SERVER_ONLY` · audit
- `migration.historical.reconcile` — Rapprocher une ligne historique · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `migration.historical.finalize` — Comptabiliser les lignes historiques prêtes · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `migration.errors.export` — Exporter les erreurs/rejets d’import · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · sorties XLSX

## Notifications & communications
### Communications
- `communications.read` — Voir les communications · risque **LOW** · offline `READ_CACHE`
- `communications.compose` — Rédiger un communiqué/message · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `communications.send.individual` — Envoyer à un parent/destinataire · risque **HIGH** · offline `QUEUE_UNTIL_ONLINE` · audit
- `communications.send.class` — Envoyer à une classe · risque **HIGH** · offline `QUEUE_UNTIL_ONLINE` · audit
- `communications.send.section` — Envoyer à une section · risque **HIGH** · offline `QUEUE_UNTIL_ONLINE` · audit
- `communications.send.all_parents` — Envoyer à tous les parents de l’école · risque **CRITICAL** · offline `QUEUE_UNTIL_ONLINE` · audit
- `communications.templates.manage` — Gérer les modèles de messages · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `communications.history.read` — Voir historique et statut de livraison · risque **MEDIUM** · offline `READ_CACHE`
- `communications.delivery.retry` — Relancer une livraison échouée · risque **HIGH** · offline `QUEUE_UNTIL_ONLINE` · audit

### Notifications internes
- `notifications.internal.read` — Voir ses notifications internes · risque **LOW** · offline `READ_CACHE`
- `notifications.internal.read_all` — Voir toutes les notifications autorisées · risque **MEDIUM** · offline `READ_CACHE`
- `notifications.internal.create` — Créer une notification interne · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `notifications.internal.dismiss` — Marquer/archiver une notification · risque **LOW** · offline `LOCAL_WRITE_SYNC`
- `notifications.internal.configure` — Configurer les règles internes · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### SMS
- `communications.sms.send` — Envoyer par SMS · risque **HIGH** · offline `QUEUE_UNTIL_ONLINE` · audit
- `communications.sms.bulk_send` — Envoyer des SMS en masse · risque **CRITICAL** · offline `QUEUE_UNTIL_ONLINE` · audit

## Paramètres
### Année scolaire
- `settings.academic_year.read` — Voir les années scolaires · risque **LOW** · offline `READ_CACHE`
- `settings.academic_year.create` — Créer/préparer une année · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.academic_year.update` — Modifier une année préparée · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.academic_year.activate` — Activer une année · risque **HIGH** · offline `SERVER_ONLY` · audit
- `settings.academic_year.close` — Clôturer une année · risque **HIGH** · offline `SERVER_ONLY` · audit
- `settings.academic_year.archive` — Archiver une année · risque **HIGH** · offline `SERVER_ONLY` · audit
- `settings.academic_year.reopen` — Réouvrir pour correction · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `settings.academic_year.copy_previous` — Reprendre la configuration précédente · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.work_year.select` — Changer année de consultation · risque **LOW** · offline `READ_CACHE`

### Articles scolaires vendus
- `settings.products.read` — Voir catalogue des articles vendus · risque **LOW** · offline `READ_CACHE`
- `settings.products.manage` — Créer/modifier un article vendu · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.products.activate` — Activer/désactiver un article · risque **HIGH** · offline `SERVER_ONLY` · audit

### Avantages
- `settings.benefits.read` — Voir politiques sociales · risque **LOW** · offline `READ_CACHE`
- `settings.benefits.manage` — Configurer famille nombreuse / enfant du personnel · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Contributions en nature
- `settings.contributions.read` — Voir contributions configurées · risque **LOW** · offline `READ_CACHE`
- `settings.contributions.manage` — Créer/modifier une contribution · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.contributions.activate` — Activer/désactiver une contribution · risque **HIGH** · offline `SERVER_ONLY` · audit

### Documents & sauvegardes
- `settings.documents.read` — Voir paramètres documents · risque **LOW** · offline `READ_CACHE`
- `settings.documents.manage` — Modifier préfixes/reçus/logo/signature · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.backups.read` — Voir paramètres sauvegarde · risque **LOW** · offline `READ_CACHE`
- `settings.backups.manage` — Modifier politique sauvegarde · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.backups.create` — Créer une sauvegarde maintenant · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.backups.test` — Tester une sauvegarde · risque **MEDIUM** · offline `READ_CACHE`
- `settings.backups.restore` — Restaurer une sauvegarde · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `settings.documents.history.read` — Voir historique des documents · risque **LOW** · offline `READ_CACHE`

### Inscription & admission
- `settings.enrollment_policy.read` — Voir conditions d’inscription · risque **LOW** · offline `READ_CACHE`
- `settings.enrollment_policy.manage` — Créer/modifier les conditions · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.enrollment_policy.activate` — Activer/désactiver une condition · risque **HIGH** · offline `SERVER_ONLY` · audit
- `settings.enrollment_policy.review` — Valider la revue des conditions · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Options avancées
- `settings.diagnostics.read` — Voir diagnostic système · risque **LOW** · offline `READ_CACHE`
- `settings.diagnostics.export` — Exporter diagnostic · risque **MEDIUM** · offline `READ_CACHE` · sorties ZIP
- `settings.document_root.manage` — Choisir dossier documentaire · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Règles d’encaissement
- `settings.payment_policy.read` — Voir règles d’encaissement · risque **LOW** · offline `READ_CACHE`
- `settings.payment_policy.manage` — Modifier modes/acomptes/fonds/paiements futurs · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Structure & classes
- `settings.structure.read` — Voir structure et classes · risque **LOW** · offline `READ_CACHE`
- `settings.sections.manage` — Activer/désactiver les sections · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.options.manage` — Activer/désactiver les options · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.option_tariff_group.manage` — Gérer groupes tarifaires options · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.classes.create` — Ouvrir une classe · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.classes.batch_create` — Créer plusieurs classes · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.classes.rename` — Renommer une classe · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.classes.activate` — Activer/désactiver une classe · risque **HIGH** · offline `SERVER_ONLY` · audit

### Tarifs & barèmes
- `settings.tariffs.read` — Voir tarifs et barèmes · risque **LOW** · offline `READ_CACHE`
- `settings.tariffs.manage` — Créer/modifier un tarif · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.tariff_groups.manage` — Gérer barèmes de groupe · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.tariffs.apply` — Appliquer les barèmes aux classes · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.tariffs.copy_year` — Copier les barèmes vers une autre année · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.billing_months.manage` — Configurer les mois de facturation · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Types de frais
- `settings.fee_types.read` — Voir types de frais · risque **LOW** · offline `READ_CACHE`
- `settings.fee_types.manage` — Créer/modifier un type de frais · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.fee_types.activate` — Activer/désactiver un type de frais · risque **HIGH** · offline `SERVER_ONLY` · audit
- `settings.regulatory_fees.configure` — Configurer frais réglementaires · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### École & identité
- `settings.school_identity.read` — Voir identité école · risque **LOW** · offline `READ_CACHE`
- `settings.school_identity.update` — Modifier identité école · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `settings.school_logo.update` — Modifier logo école · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

## Personnel
### Enfants du personnel & paie
- `personnel.staff_children.read` — Voir les enfants du personnel · risque **LOW** · offline `READ_CACHE`
- `personnel.staff_children.finance_mode` — Définir le mode financier enfant du personnel · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.payroll_deduction.confirm` — Confirmer une retenue à la source · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.payroll_deduction.cancel` — Annuler une retenue non-cash · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit

### Fonctions & affectations
- `personnel.functions.read` — Voir les fonctions/postes · risque **LOW** · offline `READ_CACHE`
- `personnel.functions.manage` — Créer/modifier/activer une fonction · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.assignments.read` — Voir les affectations · risque **LOW** · offline `READ_CACHE`
- `personnel.assignments.add` — Ajouter une affectation · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.assignments.end` — Terminer une affectation · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit

### Personnel
- `personnel.read` — Consulter le personnel · risque **LOW** · offline `READ_CACHE`
- `personnel.create` — Ajouter un agent · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.update` — Modifier un agent · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.activate` — Activer/désactiver un agent · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `personnel.summary.read` — Voir la synthèse du personnel · risque **LOW** · offline `READ_CACHE`

## Synchronisation & offline
### Synchronisation
- `sync.status.read` — Voir état de synchronisation · risque **LOW** · offline `READ_CACHE`
- `sync.device.register` — Enregistrer un appareil · risque **HIGH** · offline `SERVER_ONLY` · audit
- `sync.device.revoke` — Révoquer un appareil · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `sync.conflicts.read` — Voir les conflits de synchronisation · risque **HIGH** · offline `READ_CACHE`
- `sync.conflicts.resolve` — Résoudre un conflit autorisé · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `sync.finance.arm` — Armer un poste pour encaissement CASH offline · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `sync.finance.reconcile` — Réconcilier la Finance offline · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `sync.finance.quarantine.read` — Voir opérations/charges en quarantaine · risque **HIGH** · offline `READ_CACHE`
- `sync.finance.quarantine.resolve` — Résoudre une quarantaine financière · risque **CRITICAL** · offline `SERVER_ONLY` · audit

## Tableau de bord
### École
- `dashboard.school.read` — Voir le tableau de bord école · risque **LOW** · offline `READ_CACHE`
- `dashboard.school.drilldown` — Ouvrir les cartes et vues détaillées · risque **LOW** · offline `READ_CACHE`
- `dashboard.school.export` — Exporter une vue de tableau de bord · risque **LOW** · offline `READ_CACHE` · sorties XLSX,PDF
- `dashboard.school.print` — Imprimer une vue de tableau de bord · risque **LOW** · offline `READ_CACHE` · sorties PDF

## Utilisateurs & accès
### Accès
- `access.users.read` — Voir les utilisateurs · risque **HIGH** · offline `READ_CACHE`
- `access.users.create` — Créer un utilisateur · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.users.update` — Modifier un utilisateur · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.users.activate` — Activer/désactiver un utilisateur · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.users.pin.self_change` — Changer son propre code secret · risque **MEDIUM** · offline `READ_CACHE` · audit
- `access.users.credentials.reset` — Réinitialiser les identifiants d’un utilisateur · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.roles.read` — Voir rôles et permissions · risque **HIGH** · offline `READ_CACHE`
- `access.roles.manage` — Créer/modifier un rôle · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.permissions.assign` — Attribuer/retirer des permissions à un rôle · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.scopes.assign` — Attribuer un périmètre à une affectation · risque **CRITICAL** · offline `SERVER_ONLY` · audit
- `access.grants.exception` — Créer une exception individuelle temporaire · risque **CRITICAL** · offline `SERVER_ONLY` · audit

## Élèves & inscriptions
### Familles & responsables
- `families.read` — Consulter les familles et ménages · risque **LOW** · offline `READ_CACHE`
- `families.create` — Créer une famille/ménage · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `families.update` — Modifier une famille · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `families.resolve` — Résoudre les candidats ménage/famille · risque **MEDIUM** · offline `READ_CACHE`
- `families.responsibles.read` — Voir les responsables · risque **LOW** · offline `READ_CACHE`
- `families.responsibles.add` — Ajouter un responsable · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `families.responsibles.remove` — Retirer un responsable · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `families.children.read` — Voir les enfants du ménage · risque **LOW** · offline `READ_CACHE`

### Inscriptions
- `enrollments.read` — Consulter les inscriptions · risque **LOW** · offline `READ_CACHE`
- `enrollments.preview` — Prévisualiser une inscription familiale · risque **LOW** · offline `READ_CACHE`
- `enrollments.create` — Inscrire un ou plusieurs enfants · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `enrollments.reenroll` — Réinscrire un élève connu · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `enrollments.validate` — Valider les inscriptions · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `enrollments.collect_on_admission` — Encaisser les obligations d’admission pendant l’inscription · risque **HIGH** · offline `PREAUTHORIZED_CRITICAL` · audit
- `enrollments.arrears.read` — Voir les arriérés historiques d’un élève · risque **LOW** · offline `READ_CACHE`
- `enrollments.print` — Imprimer la vue d’inscription · risque **LOW** · offline `READ_CACHE` · sorties PDF
- `enrollments.export_pdf` — Exporter la vue PDF · risque **LOW** · offline `READ_CACHE` · sorties PDF
- `enrollments.export_xlsx` — Exporter la vue Excel · risque **LOW** · offline `READ_CACHE` · sorties XLSX

### Élèves
- `students.read` — Consulter/rechercher les élèves · risque **LOW** · offline `READ_CACHE`
- `students.create` — Créer un nouvel élève · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `students.identity.update` — Modifier l’identité de l’élève · risque **MEDIUM** · offline `LOCAL_WRITE_SYNC` · audit
- `students.class.change` — Changer la classe · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `students.lifecycle.abandon` — Déclarer un abandon avec date et motif · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `students.lifecycle.transfer` — Déclarer un transfert · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `students.lifecycle.reintegrate` — Réintégrer un élève · risque **HIGH** · offline `LOCAL_WRITE_SYNC` · audit
- `students.lifecycle.history.read` — Voir l’historique du cycle de vie · risque **MEDIUM** · offline `READ_CACHE`
- `students.account.read` — Voir le compte/relevé élève · risque **MEDIUM** · offline `READ_CACHE`
- `students.account.print` — Imprimer le relevé élève · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
- `students.account.export_pdf` — Exporter le relevé élève PDF · risque **MEDIUM** · offline `READ_CACHE` · sorties PDF
