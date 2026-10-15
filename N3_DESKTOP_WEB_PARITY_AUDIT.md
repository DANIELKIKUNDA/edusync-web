# N3 — Audit de parité Desktop → Web (lecture seule)

Date : 2026-10-15. Mandat du propriétaire : avant toute certification N3, inventorier tous les écarts entre le golden master
Desktop (`C:\Users\cs-ap\dev\edusync-desktop-golden`, EduSync École Offline 0.11.0-rc.1, lecture seule, rien exécuté)
et le Web (`main` = `e6e4de6`, code certifié N2 `ccfdbc6`). **Aucun code modifié pendant cet audit.**

Méthode : chaque opération métier publique du Desktop (`app/db/*.py`, `app/services/*.py`, pages de `app/ui/`) a été
recherchée dans le Web (routes `backend/src/edusync/modules/*/api/router.py`, dépôts `adapters/`, migrations, écrans).
Statuts : `PARITY_OK` (règle présente côté Web), `PARITY_GAP` (règle Desktop absente ou différente),
`WEB_EXTENSION` (absent du Desktop), `NOT_APPLICABLE_IN_SAAS`, `OWNER_DECISION_REQUIRED` (uniquement pour ce que le
Desktop ne tranche pas). Une règle présente au Desktop n'est jamais classée `OWNER_DECISION_REQUIRED`.

Limite : `PARITY_OK` signifie ici « la fonctionnalité existe avec la même intention » ; la comparaison fine des règles
(montants, ordres d'imputation, messages) se fera lot par lot pendant les corrections, avec une sonde réelle par lot,
comme pour L1–L7. Les points marqués *à comparer finement* sont présents des deux côtés mais n'ont pas été comparés ligne
à ligne.

Décisions du propriétaire du 2026-10-15 intégrées : `finance.anticipation_plans.manage` par défaut à
`ADMIN_SYSTEME_ECOLE` (le caissier consulte, enregistre l'adhésion et encaisse ; délégation possible par rôle
`SCHOOL_CUSTOM`) ; changement de classe refusé dès qu'il existe des frais, sans transfert ni recalcul.

## 1. Synthèse par module

| Module | Écarts `PARITY_GAP` | Extensions Web |
|--------|---------------------|----------------|
| Élèves / familles / inscriptions | G-SCO-1 à 6 | règles de saisie, synchronisation hors ligne |
| Finance / encaissement | G-FIN-1, 2, 3 | multi-caissiers |
| Fonds anticipés | G-ADV-1 (module entier) | — |
| Plans anticipés | G-PLAN-1 (attribution du droit décidée) | — |
| Caisse | G-CAI-1 à 4 | — |
| Contre-opérations et reçus | G-REV-1, 2 | — |
| Décisions financières | G-DEC-1 à 4 | — |
| Recouvrement / états financiers | G-REC-1 à 5 | — |
| Articles scolaires | G-ART-1 | stock d'intendance |
| Personnel | G-PER-1, 2 | comptes d'accès liés |
| Effectifs & dépôts | G-EFF-1 | — |
| Documents / PDF / Excel | G-DOC-1 à 4 | historique de documents ; 2 points `NOT_APPLICABLE_IN_SAAS` |
| Migration & import | G-IMP-1, 2 | — |
| Communications | — | module entier |
| Intendance | — | module entier |
| Workflows par rôle | G-ROLE-1 | droits fins |

## 2. Inventaire détaillé

### 2.1 Élèves / familles / inscriptions (Desktop `app/db/schooling.py`, `app/ui/schooling_page.py`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Matricule élève et code famille automatiques (`next_student_matricule`, `next_family_code`) | générés à l'inscription | `PARITY_OK` |
| Liste / fiche / profil complet de famille, responsables (ajout, retrait, principal) | `/schooling/families*`, `/guardians` | `PARITY_OK` |
| Recherche de foyers candidats (`find_family_candidates`, `resolve_household_candidates`) | `/families/resolve/candidates` | `PARITY_OK` *à comparer finement* |
| Inscription familiale par lot (`preview_family_enrollment`, `enroll_family_batch`) | `/enrollments/family` (charges, avantages, conditions d'admission) | `PARITY_OK` (L2–L4) |
| **Doublons probables avant création** (`find_probable_students` : nom, post-nom, prénom, date de naissance) | aucune recherche de doublon | **`PARITY_GAP` G-SCO-1** |
| **Arriérés historiques d'un élève à l'inscription** (`student_historical_arrears`, `historical_debt_years`) | dettes antérieures visibles à la caisse (`/old-debts`) ; non montrées à l'inscription | **`PARITY_GAP` G-SCO-2** *à comparer* |
| Correction d'identité (`update_student_identity`) | `PATCH /students/{id}` | `PARITY_OK` |
| Recherche avancée, statistiques, synthèses (`search_students_advanced`, `schooling_statistics`, `*_overview_summary`) | `/schooling/summary`, `/students` | `PARITY_OK` *à comparer finement* |
| **Indicateurs détaillés des familles** (`family_kpi_details`) | partiel (synthèse) | **`PARITY_GAP` G-SCO-3** |
| **Diagnostic des contacts famille** (sans responsable, plusieurs principaux) (`family_contact_diagnostics`) | absent | **`PARITY_GAP` G-SCO-4** |
| Statuts : abandon, transfert, réintégration avec neutralisation des frais futurs | routes dédiées + `_apply_lifecycle_to_future_charges` (L6) | `PARITY_OK` |
| **Suspension** (`SUSPENSION` → `SUSPENDU`) | gérée par le dépôt, **aucune route ni écran** | **`PARITY_GAP` G-SCO-5** |
| Historique des statuts (`student_status_history`) | `student_status_events`, profil | `PARITY_OK` |
| Changement de classe (refusé si frais, décision du 2026-10-15) | `/class-change` fail-closed | `PARITY_OK` |
| **Années d'inscription et classes par année** pour réinscription (`enrollment_years`, `classes_for_year`) | réinscription d'une année sur l'autre non outillée en écran | **`PARITY_GAP` G-SCO-6** *à comparer* |
| Exports élèves / familles PDF et Excel (`schooling_exports.py`) | `/exports/students|families.(pdf|xlsx)`, fiche PDF | `PARITY_OK` |
| Règles de saisie à l'inscription | — | `WEB_EXTENSION` (N2) |
| Synchronisation hors ligne des inscriptions (`sync`) | — | `WEB_EXTENSION` |

### 2.2 Finance / encaissement (Desktop `app/db/finance_checkout.py`, `app/db/database.py`, `app/ui/finance_page_v10.py`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Recherche élève à la caisse, enfants de la famille | `/checkout/search`, `/family/{id}/children` | `PARITY_OK` |
| Lignes de frais encaissables, éligibilité séquentielle | `/balance/{enrollment}`, `sequential_eligibility` | `PARITY_OK` ; **chaîne séquentielle limitée à SCOLARITE au Desktop** → **`PARITY_GAP` G-FIN-1** *à comparer* |
| Lot d'admission d'abord (`registration_bundle_due`, `record_registration_bundle`) | `_registration_bundle_first`, `/registration-bundle` | `PARITY_OK` (L4) |
| **Autres lots** : `fee_bundle_due` / `record_fee_bundle`, `journal_badge_bundle_due` / `record_journal_badge_bundle` (journal + badge) | absents | **`PARITY_GAP` G-FIN-2** |
| Règles d'encaissement et modes | L5 | `PARITY_OK` |
| **Suggestion d'imputation et action recommandée** (`suggest_checkout_allocations`, `recommended_checkout` : lot d'admission → plus ancienne mensualité due → autre frais) | « Échéance suivante » sélectionne la première éligible ; pas de suggestion par montant | **`PARITY_GAP` G-FIN-3** |
| Encaissement familial avec numéro de séance (`record_family_checkout`, `next_checkout_session_no`, détail et séances récentes) | `/family-collect`, `/family-baskets/{id}` | `PARITY_OK` *à comparer (numérotation de séance)* |
| Dettes d'années clôturées encaissables sans changer d'année | `/old-debts/{student}` | `PARITY_OK` |
| Numéro de reçu, une séquence | L7 | `PARITY_OK` |
| Paiement multi-caissiers concurrent | — | `WEB_EXTENSION` |

### 2.3 Fonds anticipés (Desktop `app/db/operations.py:290-516`, `schema.sql` advance_funds / advance_allocations / advance_receipts)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Réception d'un fonds (élève, montant, devise, mode, référence, reçu propre ; refus si `advance_payments_enabled` désactivé ou mode non accepté) | droits au registre seulement (`finance.advance_funds.*`), aucune table, aucune route | **`PARITY_GAP` G-ADV-1** |
| Liste des fonds, solde disponible | absent | inclus G-ADV-1 |
| Imputation sur les frais dus (plus anciens d'abord) | absent | inclus G-ADV-1 |
| Annulation / remboursement d'un fonds non imputé, motif obligatoire (ADMIN, DIRECTION) | absent | inclus G-ADV-1 |
| Analyse des fonds (`analysis_advance_funds`), reçu PDF (`export_advance_receipt_pdf`) | absent | inclus G-ADV-1 |

Doctrine L6 : mécanisme distinct des plans, jamais fusionné.

### 2.4 Plans anticipés (Desktop `app/db/anticipation.py`)

| Fonctionnalité | Web | Statut |
|----------------|-----|--------|
| Plans, adhésions, échéancier, imputation mois courant puis mois cibles | lot L6, sonde 30/30 | `PARITY_OK` |
| Droit de création : ADMIN, DIRECTION au Desktop ; décision 2026-10-15 : `ADMIN_SYSTEME_ECOLE` par défaut | aucun rôle standard ne l'a encore | **`PARITY_GAP` G-PLAN-1** (décision prise, à appliquer) |

### 2.5 Caisse (Desktop `app/db/operations.py:470-670`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Ouverture de caisse, synthèse du jour | `/cash/open`, `/day-summary`, `/current` | `PARITY_OK` (modèle par caissier, voir G-CAI-4) |
| **Dépenses de caisse** (`record_expense` : catégorie, montant, devise, motif ≥ 3, référence ; ADMIN, CAISSIER, DIRECTION) | table `finance_cash_expenses` lue par la synthèse, **aucune route d'enregistrement** | **`PARITY_GAP` G-CAI-1** |
| Clôture avec instantanés par devise (`close_cash_day` ; ADMIN, DIRECTION) | `/cash/close` (par le caissier, comptage) | `PARITY_OK` *à comparer (droit de clôture)* → voir G-CAI-3 |
| **Réouverture de la caisse clôturée** (`reopen_cash_day` : ADMIN seul, motif ≥ 5, tracé) | absente | **`PARITY_GAP` G-CAI-2** |
| Journal de caisse et historique | `/history`, `/{session}/journal` | `PARITY_OK` |
| Journal de caisse PDF (`export_cash_journal_pdf`) | aucun export | voir G-DOC-3 |
| Rôles de clôture : Desktop ADMIN / DIRECTION ; Web : le caissier clôture sa session | **`PARITY_GAP` G-CAI-3** |
| Modèle : Desktop une caisse **de l'école par jour** ; Web une **session par caissier** avec synthèse globale | **`PARITY_GAP` G-CAI-4** *à qualifier* (la synthèse globale Web couvre la vue école ; la clôture de la journée école n'existe pas) |

### 2.6 Contre-opérations et reçus (Desktop `app/db/operations.py:225-289`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| **Annulation ou remboursement d'un paiement** (`reverse_payment` : ANNULATION / REMBOURSEMENT, motif, ADMIN / DIRECTION, paiement VALIDE seulement, contre-écriture tracée) | **absent** : aucun paiement ne peut être annulé | **`PARITY_GAP` G-REV-1** |
| Réimpression = duplicata compté et tracé (`mark_receipt_duplicate`) | impression de reçu, mention de duplicata *à vérifier* | **`PARITY_GAP` G-REV-2** *à comparer* |
| Historique des paiements d'un élève (`student_payment_history`, `list_payments`) | suivi des frais (`/fee-tracking/student`) | `PARITY_OK` *à comparer finement* |
| Reçu PDF, lot de reçus | reçus et reçus du panier familial | `PARITY_OK` |

### 2.7 Décisions financières (Desktop `app/db/financial_decisions.py`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Création / annulation de décision | `/finance/controls/decisions` (+ cancel) | `PARITY_OK` pour l'existence |
| **Types de décision** : DISCOUNT, EXEMPTION, INDIVIDUAL_FREE, COLLECTIVE_EXEMPTION, DIRECTION_EXCEPTION, THIRD_PARTY_COVERAGE | Web : EXEMPTION, REDUCTION, SPONSORSHIP, OTHER | **`PARITY_GAP` G-DEC-1** |
| **Recalcul des décisions d'une inscription** (`recalculate_enrollment_financial_decisions`) | absent | **`PARITY_GAP` G-DEC-2** |
| **Explication d'un frais** (`charge_financial_explanation` : brut, avantage, décision, net, payé) | absent | **`PARITY_GAP` G-DEC-3** |
| **Vue opérateur et suivi** (`student_financial_operator_view`, `financial_operator_follow_up`) | absent | **`PARITY_GAP` G-DEC-4** |
| Responsabilité d'un frais (famille, paie, école, tiers) | `/responsibilities` | `PARITY_OK` |
| Neutralisation des frais futurs au changement de statut | L6 | `PARITY_OK` |

### 2.8 Recouvrement / états financiers (Desktop `app/db/financial_views.py`, `terrain.py`, `operations.py:672-760`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Registre financier (VF01), synthèses classe / section / école (VF02–VF04) | `/finance/recovery/class-register`, `/sections`, `/summary/{kind}` (+ PDF / Excel) | `PARITY_OK` *à comparer finement* |
| Recouvrement mensuel | `/finance/recovery/monthly` (+ PDF / Excel) | `PARITY_OK` |
| **Statut de recouvrement historique** (`historical_recovery_status`) | absent | **`PARITY_GAP` G-REC-1** |
| **Analyses par type de frais et par caissier** (`analysis_by_fee_type`, `analysis_by_cashier`) | absentes | **`PARITY_GAP` G-REC-2** |
| **Rapport financier journalier** (`daily_financial_report` + PDF) | synthèse de caisse du jour seulement | **`PARITY_GAP` G-REC-3** |
| Présentation des acomptes dans les rapports (`partial_reporting_mode`) | stockée (L5), non lue | **`PARITY_GAP` G-REC-4** |
| Registre financier détaillé (`detailed_financial_register` + Excel) | suivi des frais (`/fee-tracking`) | `PARITY_OK` *à comparer (export Excel)* |
| Profils de rapports, rapports générés numérotés (`report_profiles`, `register_generated_report`, préfixe RAP) | modèles de rapports (`/finance/reports/templates`, `/preview`), historique de documents | `PARITY_OK` partiel ; **préfixe et numérotation des rapports** → **`PARITY_GAP` G-REC-5** |

### 2.9 Articles scolaires (Desktop `schooling.py` products)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Catalogue, activation, vente à la caisse | Paramètres › Articles, `/products/sell` | `PARITY_OK` |
| **Rapport des ventes d'articles** (`product_sales_report`) | absent | **`PARITY_GAP` G-ART-1** |
| Stock d'intendance lié aux ventes | `/stewardship/sale-stock` | `WEB_EXTENSION` |

### 2.10 Personnel (Desktop `app/db/personnel.py`, `staff_finance.py`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Fonctions (catalogue, activation), agents, activation, affectations (ajout, fin), synthèse | `/personnel/*` | `PARITY_OK` |
| Enfants du personnel, mode de prise en charge | `/{staff}/children`, `/children/{link}/finance-mode` | `PARITY_OK` |
| **Frais ouverts d'un enfant du personnel** (`staff_child_open_charges`) | absent comme vue dédiée | **`PARITY_GAP` G-PER-1** |
| **Retenue sur salaire confirmée = règlement hors caisse** (`confirm_staff_payroll_deduction`, sans reçu ni opération de caisse ; annulation motivée `cancel_staff_noncash_settlement` ; ADMIN, DIRECTION) | absent | **`PARITY_GAP` G-PER-2** |
| Comptes d'accès liés à un agent | `/access-links` | `WEB_EXTENSION` |

### 2.11 Effectifs & dépôts (Desktop `terrain.py`, `effectifs_exports.py`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Effectifs, mouvements (`enrollment_counts`, `enrollment_movements_summary`) | `/effectifs/counts`, `/movements`, `/classes`, `/overview` | `PARITY_OK` |
| Exports effectifs PDF / Excel | `/exports/counts.*`, `/print/counts.pdf` | `PARITY_OK` |
| Contributions en nature : remise par élève (`record_student_contribution`) | `/effectifs/deposits` | `PARITY_OK` *à comparer finement* |
| Registre des contributions (Excel) | `/exports/deposits.xlsx` | `PARITY_OK` |
| **Contrôle « jamais un faux paiement »** : quantités remises / restantes, agent réceptionnaire | *à comparer* | **`PARITY_GAP` G-EFF-1** *à vérifier* |

### 2.12 Documents / PDF / Excel (Desktop `app/services/documents.py`, `document_management.py`)

| Document Desktop | Web | Statut |
|------------------|-----|--------|
| Reçu (A5, 80 mm, 58 mm, copies), lot de reçus | L7 | `PARITY_OK` |
| Montant en toutes lettres (`money_in_words`) | *à vérifier sur le reçu Web* | **`PARITY_GAP` G-DOC-1** *à vérifier* |
| **Relevé de compte élève PDF** (`export_student_account_pdf`) | absent | **`PARITY_GAP` G-DOC-2** |
| **Journal de caisse PDF**, **rapport financier journalier PDF** | absents | **`PARITY_GAP` G-DOC-3** |
| **Rapport financier périodique PDF / Excel** (`export_periodic_financial_report_*`) | aperçu de modèle, export *à vérifier* | **`PARITY_GAP` G-DOC-4** *à vérifier* |
| Registre financier officiel de classe PDF, registre détaillé Excel, synthèses Excel | `/class-register.pdf|xlsx`, `/summary/{kind}.{fmt}` | `PARITY_OK` |
| Effectifs PDF / Excel, registre des contributions | effectifs | `PARITY_OK` |
| Modèle d'import élèves, import élèves (analyse, simulation, exécution) | `/documents/student-import-template.xlsx`, `/migration-import/students/*` | `PARITY_OK` |
| Historique des documents générés | `/documents/history` | `PARITY_OK` |
| **Reçu de fonds anticipé** | absent | inclus G-ADV-1 |
| Exports personnel, fiche élève, fiche agent | — | `PARITY_OK` / `WEB_EXTENSION` |
| Dossier des documents sur disque, envoi à l'imprimante Windows (`set_document_root`, `send_pdf_to_default_printer`) | stockage objet, impression par le navigateur | `NOT_APPLICABLE_IN_SAAS` (×2) |
| **Préfixe et numéro des rapports (RAP)** | absent | inclus G-REC-5 |

### 2.13 Migration & import (Desktop `services/documents.py` import, `finance_checkout.finalize_historical_financial_import`)

| Fonctionnalité Desktop | Web | Statut |
|------------------------|-----|--------|
| Import élèves (classeur protégé, détection de feuilles, classes) | `/migration-import/students/*` | `PARITY_OK` *à comparer finement* |
| Import de l'historique financier (analyse, mise en attente) | `/finance-history/*` | `PARITY_OK` |
| **Finalisation de l'historique sans toucher la caisse du jour** (`finalize_historical_financial_import`) | exécution de lot *à comparer* | **`PARITY_GAP` G-IMP-1** *à vérifier* |
| **Réparation des dates d'inscription** (`preview_enrollment_date_repair`), suggestions historiques par ligne | absentes | **`PARITY_GAP` G-IMP-2** |

### 2.14 Communications

Aucune trace de communication ni de SMS dans le Desktop. Web : `/communications/*` (modèles, envoi, relance) → `WEB_EXTENSION`
(décision n° 7 : ne bloque pas).

### 2.15 Intendance

Aucun module d'intendance au Desktop. Web : `/stewardship/*` (stock, biens, inventaires, emplacements) → `WEB_EXTENSION`.

### 2.16 Workflows par rôle (Desktop `app/ui/main_window.py::ROLE_PAGES` + `require_roles`)

| Desktop | Web | Statut |
|---------|-----|--------|
| 4 rôles : ADMIN, DIRECTION, SECRETARIAT, CAISSIER ; pages et opérations par rôle (ex. annulation : ADMIN / DIRECTION ; réouverture : ADMIN ; dépense : ADMIN / CAISSIER / DIRECTION) | registre de droits fins et rôles approuvés (PROMOTEUR, GESTIONNAIRE, RESPONSABLE_FINANCE, PRÉFET, DIRECTION_SECTION, CAISSIER, …) | `WEB_EXTENSION` pour la granularité |
| **Table de correspondance opération Desktop → droit Web → rôles Web** non établie ; certaines opérations Desktop n'ont pas de droit Web branché (annulation, réouverture, dépense, retenue sur salaire) | — | **`PARITY_GAP` G-ROLE-1** |

## 3. Liste des `PARITY_GAP` (à présenter avant toute correction)

| Id | Écart | Domaine | Poids Finance |
|----|-------|---------|---------------|
| G-ADV-1 | Fonds anticipés (réception, imputation, annulation / remboursement, reçu, analyse) | Finance | **CORRIGÉ** (N3-D : réception avec reçu propre, imputation plus anciennes d'abord, annulation / remboursement par le gestionnaire, reçu PDF ; jamais mêlé aux plans ; sonde fonds 29/29) |
| G-REV-1 | Annulation / remboursement d'un paiement (contre-opération motivée) | Finance | **CORRIGÉ** (N3-B : contre-opération en ajout seul, propre paiement / autorité supérieure ; sonde caisse 37/37) |
| G-CAI-1 | Enregistrement des dépenses de caisse | Caisse | **CORRIGÉ** (N3-B : dépense motivée dans la caisse ouverte) |
| G-CAI-2 | Réouverture motivée d'une caisse clôturée | Caisse | **CORRIGÉ** (N3-B : réouverture motivée de la journée, gestionnaire) |
| G-CAI-3 | Droit de clôture (ADMIN / DIRECTION au Desktop) | Caisse | **CORRIGÉ** (N3-B : clôture individuelle caissier, clôture globale gestionnaire) |
| G-CAI-4 | Journée de caisse de l'école vs sessions par caissier (à qualifier) | Caisse | **CORRIGÉ** (N3-B : sessions individuelles conservées + journée de l'école clôturée globalement avec instantanés) |
| G-DEC-1 | Types de décision financière Desktop (6) ≠ Web (4) | Décisions | **CORRIGÉ** (N3-C : 6 natures Desktop, portées, % / fixe, priorité, cumul, période ; anciennes décisions Web conservées telles quelles ; sonde décisions 28/28) |
| G-DEC-2 | Recalcul des décisions d'une inscription | Décisions | **CORRIGÉ** (N3-C : recalcul à la création, à l'annulation, après génération des frais, et sur demande) |
| G-DEC-3 | Explication d'un frais (brut → net → payé) | Décisions | **CORRIGÉ** (N3-C : explication brut → avantage → décisions → net → réglé → reste) |
| G-DEC-4 | Vue opérateur et suivi financier | Décisions | **CORRIGÉ** (N3-C : situation financière de l'élève et suivi ; + responsabilité prévue par frais, écart trouvé à la comparaison fine) |
| G-FIN-1 | Chaîne séquentielle limitée à SCOLARITE (à comparer) | Encaissement | moyen |
| G-FIN-2 | Lots de frais et lot journal + badge | Encaissement | moyen |
| G-FIN-3 | Suggestion d'imputation / action recommandée | Encaissement | faible |
| G-PLAN-1 | Attribuer `finance.anticipation_plans.manage` à `ADMIN_SYSTEME_ECOLE` (décision prise) | Plans | **CORRIGÉ** (N3-A, migration 0067, sonde 32/32) |
| G-PER-1 | Frais ouverts d'un enfant du personnel | Personnel | faible |
| G-PER-2 | Retenue sur salaire = règlement hors caisse (+ annulation) | Personnel / Finance | **élevé** |
| G-REC-1 | Statut de recouvrement historique | Recouvrement | moyen |
| G-REC-2 | Analyses par type de frais et par caissier | Recouvrement | moyen |
| G-REC-3 | Rapport financier journalier | Recouvrement | moyen |
| G-REC-4 | Présentation des acomptes dans les rapports | Recouvrement | moyen |
| G-REC-5 | Préfixe et numérotation des rapports | Documents | faible |
| G-REV-2 | Duplicata de reçu compté et tracé (à vérifier) | Reçus | **PARITY_OK** (vérifié N3-B : ORIGINAL puis DUPLICATA comptés et tracés, déjà au Web) |
| G-ART-1 | Rapport des ventes d'articles | Articles | faible |
| G-SCO-1 | Doublons probables avant création d'un élève | Élèves | moyen |
| G-SCO-2 | Arriérés historiques montrés à l'inscription (à comparer) | Élèves | moyen |
| G-SCO-3 | Indicateurs détaillés des familles | Élèves | faible |
| G-SCO-4 | Diagnostic des contacts famille | Élèves | faible |
| G-SCO-5 | Suspension d'un élève (route et écran) | Élèves | moyen |
| G-SCO-6 | Réinscription d'une année sur l'autre (à comparer) | Élèves | moyen |
| G-EFF-1 | Contributions : quantités remises / restantes, réceptionnaire (à vérifier) | Effectifs | faible |
| G-DOC-1 | Montant en toutes lettres sur le reçu (à vérifier) | Documents | faible |
| G-DOC-2 | Relevé de compte élève PDF | Documents | moyen |
| G-DOC-3 | Journal de caisse PDF, rapport journalier PDF | Documents | **CORRIGÉ** (N3-B : journal de caisse PDF, rapport journalier PDF) |
| G-DOC-4 | Rapport financier périodique PDF / Excel (à vérifier) | Documents | moyen |
| G-IMP-1 | Finalisation de l'historique financier sans toucher la caisse (à vérifier) | Import | moyen |
| G-IMP-2 | Réparation des dates d'inscription, suggestions historiques | Import | faible |
| G-ROLE-1 | Correspondance opération Desktop → droit → rôle Web | Rôles | **CORRIGÉ** (N3-A : pas de 1:1 ; GESTIONNAIRE = autorité financière supérieure ; migration 0068 ; sonde rbac 14/14) |

37 écarts, dont 9 marqués *à vérifier* ou *à comparer* : ces derniers seront soit confirmés, soit reclassés `PARITY_OK`
au début de leur lot, sonde à l'appui.

### Écarts trouvés pendant la comparaison fine (lots N3)

| Id | Écart | Lot | Statut |
|----|-------|-----|--------|
| G-DEC-5 | Responsabilité de règlement **par frais** (famille, retenue, tiers ; montant prévu ≤ restant réel ; remplacement tracé) — le Web n'avait qu'une responsabilité par inscription, conservée comme extension | N3-C | **CORRIGÉ** |
| G-DEC-6 | Crédit né d'une décision quand le déjà-payé dépasse le nouveau net (Desktop : fonds anticipé d'origine DECISION_CREDIT) ; refus d'annuler une décision dont le crédit est déjà utilisé | N3-D | **CORRIGÉ** |
| G-CAI-5 | Garde-fou de capacité qui comptait les paiements annulés (un frais redevenu payable était refusé) | N3-B | **CORRIGÉ** |

## 4. `OWNER_DECISION_REQUIRED`

Aucune : chaque écart a une règle Desktop. Les deux décisions encore ouvertes au N2 ont été tranchées le 2026-10-15.
Seul G-CAI-4 (journée de caisse unique de l'école vs sessions par caissier) demandera de choisir comment **transposer**
la règle Desktop au modèle multi-caissiers du Web ; la règle elle-même (clôture et réouverture de la journée par la
direction, avec instantanés) reste celle du Desktop.

## 5. Proposition d'ordre de correction (à valider)

1. G-PLAN-1 et G-ROLE-1 (droits) ; 2. G-REV-1, G-CAI-1/2/3/4 (intégrité de la caisse) ; 3. G-DEC-1 à 4 ; 4. G-ADV-1 ;
5. G-PER-1/2 ; 6. G-FIN-1/2/3 ; 7. G-REC-1 à 5 et G-DOC-1 à 4 ; 8. élèves, effectifs, import, articles.
Chaque lot : copie du Desktop, sonde réelle, écran mobile, tests de contrat, commit ; puis certification N3.
