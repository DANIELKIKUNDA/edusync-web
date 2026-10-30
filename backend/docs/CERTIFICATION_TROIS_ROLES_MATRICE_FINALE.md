# Matrice finale des attributions — Intendant, Directeur des études, Directeur de discipline

Générée par `tools/rbac/three_roles_matrix.py` sur le commit `df568db` (30/10/2026). PASS = contrôle **exécuté** (application réelle + PostgreSQL réel isolé, ou test unitaire) ; « PG » renvoie à `tools/ci/three_roles_postgres_integration.py` (sortie : `backend/docs/evidence/three_roles_postgres_run.txt`). Les routes sont trouvées par introspection de l'application.

## INTENDANT — 29 attributions au registre canonique

| Capacité | Cycle de vie | Route(s) qui la contrôlent | État | Preuve / justification |
|---|---|---|---|---|
| `audit.entity.history.read` | ACTIVE | GET /api/v1/audit/entities/{entity_type}/{entity_id} | **PASS** | PG « historique d'audit d'un élève du secondaire / primaire → 404 / paiement → 404 » ; tests/test_audit_entity_history_scope.py (10) |
| `documents.history.read` | ACTIVE | GET /api/v1/documents/history | **PASS** | PG « historique documentaire (200) » (3 rôles) |
| `documents.open` | ACTIVE | POST /api/v1/documents/history/{generation_id}/link<br>GET /api/v1/documents/open | **PASS** | PG « Liens documentaires signés » : droit retiré / appartenance retirée / compte désactivé / autre école / expiré / altéré → 403 |
| `inventory.assets.create` | ACTIVE | POST /api/v1/stewardship/assets | **PASS** | PG « immobilisation créée, idempotente (même clé → même bien, une ligne) » |
| `inventory.assets.history.read` | ACTIVE | GET /api/v1/stewardship/assets/{asset_id}/history | **PASS** | PG « historique complet du bien (CREATE, UPDATE, REPAIR ×2, STATUS) » |
| `inventory.assets.read` | ACTIVE | GET /api/v1/stewardship/assets<br>GET /api/v1/stewardship/locations | **PASS** | PG « liste des biens (200) », « locaux (200) » |
| `inventory.assets.repair.record` | ACTIVE | POST /api/v1/stewardship/assets/{asset_id}/repairs | **PASS** | PG « réparation ouverte puis clôturée », « clôture sans réparation → 409 », « bien sorti : réparation refusée » |
| `inventory.assets.status.update` | ACTIVE | POST /api/v1/stewardship/assets/{asset_id}/status | **PASS** | PG « sortie du patrimoine (DISPOSED) », « bien sorti : changement d'état refusé (409) » (erreur 500 corrigée) |
| `inventory.assets.update` | ACTIVE | PUT /api/v1/stewardship/assets/{asset_id} | **PASS** | PG « modification de la fiche → événement UPDATE », « version périmée → 409 », « bien sorti : modification refusée » |
| `inventory.counts.create` | ACTIVE | POST /api/v1/stewardship/counts | **PASS** | PG « comptage » (création idempotente par clé facultative) |
| `inventory.counts.export` | ACTIVE | GET /api/v1/stewardship/counts/{count_id}/export.xlsx<br>GET /api/v1/stewardship/counts/{count_id}/print.pdf | **PASS** | PG « export Excel du comptage », « impression du comptage en PDF », « exports sans le droit → 403 » |
| `inventory.counts.export_xlsx` | ALIAS | via inventory.counts.export | **PASS** | alias de `inventory.counts.export` : PG « export Excel du comptage », « impression du comptage en PDF », « exports sans le droit → 403 » |
| `inventory.counts.print` | ALIAS | via inventory.counts.export | **PASS** | alias de `inventory.counts.export` : PG « export Excel du comptage », « impression du comptage en PDF », « exports sans le droit → 403 » |
| `inventory.counts.read` | ACTIVE | GET /api/v1/stewardship/counts<br>GET /api/v1/stewardship/counts/{count_id} | **PASS** | PG « liste des comptages (200) », « école B : comptage de A → 404 » |
| `inventory.counts.record` | ACTIVE | POST /api/v1/stewardship/counts/{count_id}/lines | **PASS** | PG « écart sans justification → 422 », « comptage justifié », « article désactivé : comptage refusé » |
| `inventory.counts.validate` | ACTIVE | POST /api/v1/stewardship/counts/{count_id}/validate | **PASS** | PG « double validation simultanée → une seule (200 + 409) », « stock aligné sur le comptage » |
| `inventory.stock.adjust` | ACTIVE | — | **PASS** | PG « ajustement sans sens → 422 », « ajustement à la baisse de 2 » |
| `inventory.stock.export_xlsx` | ACTIVE | GET /api/v1/stewardship/stock/export.xlsx | **PASS** | PG « export Excel du stock : fichier valide, quantités numériques » |
| `inventory.stock.issue` | ACTIVE | — | **PASS** | PG « sortie de 3 », « sortie supérieure au stock refusée (409) », « concurrence : 2 sorties simultanées → une seule », « sans le droit → 403 » |
| `inventory.stock.item.manage` | ACTIVE | POST /api/v1/stewardship/items<br>PUT /api/v1/stewardship/items/{item_id} | **PASS** | PG « article créé », « idempotence », « code en double → 409 », « fiche article modifiée (If-Match) », « version périmée → 409 » |
| `inventory.stock.low_alerts.read` | ACTIVE | GET /api/v1/stewardship/stock/low-alerts | **PASS** | PG « alertes de stock faible », « alertes sans le droit → 403 » (route créée) |
| `inventory.stock.movements.read` | ACTIVE | GET /api/v1/stewardship/stock/movements | **PASS** | PG « mouvements consultables (3) » ; mesure : index 0101 |
| `inventory.stock.read` | ACTIVE | GET /api/v1/stewardship/stock<br>GET /api/v1/stewardship/sale-stock | **PASS** | PG « école B : article de A absent des listes », « stock des articles vendus (200) » |
| `inventory.stock.receive` | ACTIVE | POST /api/v1/settings/products/{product_id}/stock | **PASS** | PG « réception de 10 (201) » |
| `inventory.stock.sheet.print` | ACTIVE | GET /api/v1/stewardship/stock/print.pdf | **PASS** | PG « fiche de stock et impression du comptage en PDF » |
| `notifications.internal.dismiss` | ACTIVE | POST /api/v1/notifications/inbox/read-all<br>POST /api/v1/notifications/{notification_id}/dismiss | **PASS** | PG « un autre membre / une autre école ne peut pas l'acquitter (404) », « le destinataire l'acquitte », « sans le droit → 403 » |
| `notifications.internal.read` | ACTIVE | GET /api/v1/notifications/inbox<br>GET /api/v1/notifications/push/config<br>GET /api/v1/notifications/push-subscriptions | **PASS** | PG « le destinataire voit sa notification », « un autre membre ne la voit pas » |
| `personnel.read` | ACTIVE | GET /api/v1/personnel<br>GET /api/v1/personnel/{staff_id} | **PASS** | PG « INTENDANT : personnel (lecture) (200) » ; directeurs : « personnel du secondaire lisible », « agents du primaire et de toute l'école invisibles », « aucune création (403) » |
| `settings.school_identity.read` | ACTIVE | GET /api/v1/settings/overview<br>GET /api/v1/settings/numbering | **PASS** | PG « identité de l'école (lecture) (200) » ; « aucune modification des réglages → 403 » |

Bilan : PASS 29

## DIRECTEUR_ETUDES — 49 attributions au registre canonique

| Capacité | Cycle de vie | Route(s) qui la contrôlent | État | Preuve / justification |
|---|---|---|---|---|
| `audit.entity.history.read` | ACTIVE | GET /api/v1/audit/entities/{entity_type}/{entity_id} | **PASS** | PG « historique d'audit d'un élève du secondaire / primaire → 404 / paiement → 404 » ; tests/test_audit_entity_history_scope.py (10) |
| `communications.compose` | ACTIVE | POST /api/v1/communications/templates/preview | **PASS** | PG « SMS groupé autorisé / refusé » (route /communications/send : compose vérifié en premier) |
| `communications.history.read` | ACTIVE | GET /api/v1/communications/history<br>GET /api/v1/communications/history/{message_id}/deliveries | **PASS** | PG « historique : message du secondaire visible, du primaire masqué », « livraisons → 404 » ; tests/test_communications_history_scope.py |
| `communications.read` | ACTIVE | GET /api/v1/communications/readiness<br>GET /api/v1/communications/wallet<br>GET /api/v1/communications/wallet/ledger | **PASS** | PG « état des communications (200) » |
| `communications.send.class` | ACTIVE | — | **PASS** | PG « audience hors périmètre refusée : classe du primaire » ; tests/test_secondary_leadership_backend_regression.py |
| `communications.send.individual` | ACTIVE | — | **PASS** | PG « audience hors périmètre refusée : élève du primaire », « élève du secondaire d'une famille multi-sections » |
| `communications.send.section` | ACTIVE | — | **PASS** | PG « section secondaire : parent multi-sections, chacun une fois », « section primaire refusée » |
| `communications.sms.send` | ACTIVE | — | **PASS** | PG « crédit SMS réservé (2 sur 3) », « idempotence », « crédit insuffisant refusé » ; « SMS de bout en bout » (aperçu, confirmation, worker, crédit consommé) |
| `dashboard.school.drilldown` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.export` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.print` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `documents.history.read` | ACTIVE | GET /api/v1/documents/history | **PASS** | PG « historique documentaire (200) » (3 rôles) |
| `documents.open` | ACTIVE | POST /api/v1/documents/history/{generation_id}/link<br>GET /api/v1/documents/open | **PASS** | PG « Liens documentaires signés » : droit retiré / appartenance retirée / compte désactivé / autre école / expiré / altéré → 403 |
| `enrollments.export` | ACTIVE | GET /api/v1/schooling/exports/enrollments.pdf<br>GET /api/v1/schooling/exports/enrollments.xlsx | **PASS** | PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.export_pdf` | ALIAS | via enrollments.export | **PASS** | alias de `enrollments.export` : PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.export_xlsx` | ALIAS | via enrollments.export | **PASS** | alias de `enrollments.export` : PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.print` | ALIAS | via enrollments.export | **PASS** | alias de `enrollments.export` : PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `families.children.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `families.directory.export` | ACTIVE | GET /api/v1/schooling/exports/families.pdf<br>GET /api/v1/schooling/exports/families.xlsx | **PASS** | PG « export des familles autorisé (DIRECTEUR_ETUDES) / refusé (DIRECTEUR_DISCIPLINE) » |
| `families.directory.print_pdf` | ALIAS | via families.directory.export | **PASS** | alias de `families.directory.export` : PG « export des familles autorisé (DIRECTEUR_ETUDES) / refusé (DIRECTEUR_DISCIPLINE) » |
| `families.read` | ACTIVE | GET /api/v1/schooling/families/diagnostics<br>GET /api/v1/schooling/families/overview<br>GET /api/v1/schooling/families/kpi/{metric} | **PASS** | PG « familles = celles du secondaire », « fiche d'une famille du seul primaire → 404 », « indicateurs familles (200) » |
| `families.responsibles.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `headcounts.by_class.read` | ACTIVE | — | **PASS** | PG « effectifs par classe (200) » |
| `headcounts.by_option.read` | ACTIVE | — | **PASS** | PG « effectifs par option autorisés (DIRECTEUR_ETUDES) / refusés (DIRECTEUR_DISCIPLINE) » |
| `headcounts.by_section.read` | ACTIVE | — | **PASS** | PG « effectifs par section = SECONDAIRE seulement » |
| `headcounts.export` | ACTIVE | — | **PASS** | PG « export des effectifs par section sans le primaire » |
| `headcounts.export_pdf` | ALIAS | via headcounts.export | **PASS** | alias de `headcounts.export` : PG « export des effectifs par section sans le primaire » |
| `headcounts.export_xlsx` | ALIAS | via headcounts.export | **PASS** | alias de `headcounts.export` : PG « export des effectifs par section sans le primaire » |
| `headcounts.movements.read` | ACTIVE | GET /api/v1/effectifs/movements | **PASS** | PG « mouvements des effectifs (200) » |
| `headcounts.print` | ALIAS | via headcounts.export | **PASS** | alias de `headcounts.export` : PG « export des effectifs par section sans le primaire » |
| `headcounts.read` | ACTIVE | GET /api/v1/effectifs/overview<br>GET /api/v1/effectifs/classes | **PASS** | PG « vue d'ensemble des effectifs (200) » |
| `notifications.internal.dismiss` | ACTIVE | POST /api/v1/notifications/inbox/read-all<br>POST /api/v1/notifications/{notification_id}/dismiss | **PASS** | PG « un autre membre / une autre école ne peut pas l'acquitter (404) », « le destinataire l'acquitte », « sans le droit → 403 » |
| `notifications.internal.read` | ACTIVE | GET /api/v1/notifications/inbox<br>GET /api/v1/notifications/push/config<br>GET /api/v1/notifications/push-subscriptions | **PASS** | PG « le destinataire voit sa notification », « un autre membre ne la voit pas » |
| `personnel.assignments.read` | ACTIVE | GET /api/v1/personnel/{staff_id}/assignments | **PASS** | PG « affectations et fonctions lisibles » (agent du secondaire) |
| `personnel.functions.read` | ACTIVE | GET /api/v1/personnel/catalog/functions | **PASS** | PG « affectations et fonctions lisibles » (catalogue des fonctions) |
| `personnel.read` | ACTIVE | GET /api/v1/personnel<br>GET /api/v1/personnel/{staff_id} | **PASS** | PG « INTENDANT : personnel (lecture) (200) » ; directeurs : « personnel du secondaire lisible », « agents du primaire et de toute l'école invisibles », « aucune création (403) » |
| `personnel.summary.read` | ACTIVE | GET /api/v1/personnel/summary | **PASS** | PG « synthèse du personnel lisible (DIRECTEUR_ETUDES) / refusée (DIRECTEUR_DISCIPLINE) » |
| `settings.academic_year.read` | ACTIVE | GET /api/v1/settings/academic-years | **PASS** | PG « réglages scolaires en lecture (années, sections, identité) » |
| `settings.school_identity.read` | ACTIVE | GET /api/v1/settings/overview<br>GET /api/v1/settings/numbering | **PASS** | PG « identité de l'école (lecture) (200) » ; « aucune modification des réglages → 403 » |
| `settings.structure.read` | ACTIVE | GET /api/v1/settings/reference-catalog<br>GET /api/v1/settings/sections<br>GET /api/v1/settings/options | **PASS** | PG « réglages scolaires en lecture (années, sections, identité) » |
| `students.directory.export` | ACTIVE | GET /api/v1/schooling/exports/students.pdf<br>GET /api/v1/schooling/exports/students.xlsx | **PASS** | PG « export Excel des élèves = secondaire seulement » |
| `students.directory.export_xlsx` | ALIAS | via students.directory.export | **PASS** | alias de `students.directory.export` : PG « export Excel des élèves = secondaire seulement » |
| `students.directory.print_pdf` | ALIAS | via students.directory.export | **PASS** | alias de `students.directory.export` : PG « export Excel des élèves = secondaire seulement » |
| `students.lifecycle.history.read` | PLANNED | — | **N/A** | N/A — décision du propriétaire du 30/10 : historique du parcours reporté à la version des points (PLANNED) |
| `students.profile.complete` | ACTIVE | — | **PASS** | PG « complément de profil (adresse) d'un élève du secondaire (200) » |
| `students.profile.print_pdf` | ACTIVE | GET /api/v1/schooling/students/{student_id}/profile.pdf | **PASS** | PG « fiche PDF d'un élève du secondaire », « du primaire → 404 » |
| `students.read` | ACTIVE | GET /api/v1/schooling/summary<br>GET /api/v1/schooling/students<br>GET /api/v1/schooling/students/{student_id} | **PASS** | PG « liste des élèves = secondaire seulement », « fiche d'un élève du primaire / d'une autre école → 404 » |

Bilan : N/A 8 · PASS 41

## DIRECTEUR_DISCIPLINE — 43 attributions au registre canonique

| Capacité | Cycle de vie | Route(s) qui la contrôlent | État | Preuve / justification |
|---|---|---|---|---|
| `audit.entity.history.read` | ACTIVE | GET /api/v1/audit/entities/{entity_type}/{entity_id} | **PASS** | PG « historique d'audit d'un élève du secondaire / primaire → 404 / paiement → 404 » ; tests/test_audit_entity_history_scope.py (10) |
| `communications.compose` | ACTIVE | POST /api/v1/communications/templates/preview | **PASS** | PG « SMS groupé autorisé / refusé » (route /communications/send : compose vérifié en premier) |
| `communications.history.read` | ACTIVE | GET /api/v1/communications/history<br>GET /api/v1/communications/history/{message_id}/deliveries | **PASS** | PG « historique : message du secondaire visible, du primaire masqué », « livraisons → 404 » ; tests/test_communications_history_scope.py |
| `communications.read` | ACTIVE | GET /api/v1/communications/readiness<br>GET /api/v1/communications/wallet<br>GET /api/v1/communications/wallet/ledger | **PASS** | PG « état des communications (200) » |
| `communications.send.class` | ACTIVE | — | **PASS** | PG « audience hors périmètre refusée : classe du primaire » ; tests/test_secondary_leadership_backend_regression.py |
| `communications.send.individual` | ACTIVE | — | **PASS** | PG « audience hors périmètre refusée : élève du primaire », « élève du secondaire d'une famille multi-sections » |
| `communications.send.section` | ACTIVE | — | **PASS** | PG « section secondaire : parent multi-sections, chacun une fois », « section primaire refusée » |
| `communications.sms.bulk_send` | ACTIVE | — | **PASS** | PG « DIRECTEUR_DISCIPLINE : SMS groupé autorisé (pas 403) » / « DIRECTEUR_ETUDES : refusé (403) » |
| `communications.sms.send` | ACTIVE | — | **PASS** | PG « crédit SMS réservé (2 sur 3) », « idempotence », « crédit insuffisant refusé » ; « SMS de bout en bout » (aperçu, confirmation, worker, crédit consommé) |
| `dashboard.school.drilldown` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.export` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.print` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `dashboard.school.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `documents.history.read` | ACTIVE | GET /api/v1/documents/history | **PASS** | PG « historique documentaire (200) » (3 rôles) |
| `documents.open` | ACTIVE | POST /api/v1/documents/history/{generation_id}/link<br>GET /api/v1/documents/open | **PASS** | PG « Liens documentaires signés » : droit retiré / appartenance retirée / compte désactivé / autre école / expiré / altéré → 403 |
| `enrollments.export` | ACTIVE | GET /api/v1/schooling/exports/enrollments.pdf<br>GET /api/v1/schooling/exports/enrollments.xlsx | **PASS** | PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.export_pdf` | ALIAS | via enrollments.export | **PASS** | alias de `enrollments.export` : PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.print` | ALIAS | via enrollments.export | **PASS** | alias de `enrollments.export` : PG « registre des inscriptions Excel = secondaire seulement », « registre PDF », « Gestionnaire : toute l'école sans l'école B », « sans le droit → 403 » |
| `enrollments.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `families.children.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `families.read` | ACTIVE | GET /api/v1/schooling/families/diagnostics<br>GET /api/v1/schooling/families/overview<br>GET /api/v1/schooling/families/kpi/{metric} | **PASS** | PG « familles = celles du secondaire », « fiche d'une famille du seul primaire → 404 », « indicateurs familles (200) » |
| `families.responsibles.read` | DEPRECATED | — | **N/A** | N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10) |
| `headcounts.by_class.read` | ACTIVE | — | **PASS** | PG « effectifs par classe (200) » |
| `headcounts.by_section.read` | ACTIVE | — | **PASS** | PG « effectifs par section = SECONDAIRE seulement » |
| `headcounts.export` | ACTIVE | — | **PASS** | PG « export des effectifs par section sans le primaire » |
| `headcounts.movements.read` | ACTIVE | GET /api/v1/effectifs/movements | **PASS** | PG « mouvements des effectifs (200) » |
| `headcounts.print` | ALIAS | via headcounts.export | **PASS** | alias de `headcounts.export` : PG « export des effectifs par section sans le primaire » |
| `headcounts.read` | ACTIVE | GET /api/v1/effectifs/overview<br>GET /api/v1/effectifs/classes | **PASS** | PG « vue d'ensemble des effectifs (200) » |
| `notifications.internal.dismiss` | ACTIVE | POST /api/v1/notifications/inbox/read-all<br>POST /api/v1/notifications/{notification_id}/dismiss | **PASS** | PG « un autre membre / une autre école ne peut pas l'acquitter (404) », « le destinataire l'acquitte », « sans le droit → 403 » |
| `notifications.internal.read` | ACTIVE | GET /api/v1/notifications/inbox<br>GET /api/v1/notifications/push/config<br>GET /api/v1/notifications/push-subscriptions | **PASS** | PG « le destinataire voit sa notification », « un autre membre ne la voit pas » |
| `personnel.assignments.read` | ACTIVE | GET /api/v1/personnel/{staff_id}/assignments | **PASS** | PG « affectations et fonctions lisibles » (agent du secondaire) |
| `personnel.functions.read` | ACTIVE | GET /api/v1/personnel/catalog/functions | **PASS** | PG « affectations et fonctions lisibles » (catalogue des fonctions) |
| `personnel.read` | ACTIVE | GET /api/v1/personnel<br>GET /api/v1/personnel/{staff_id} | **PASS** | PG « INTENDANT : personnel (lecture) (200) » ; directeurs : « personnel du secondaire lisible », « agents du primaire et de toute l'école invisibles », « aucune création (403) » |
| `settings.academic_year.read` | ACTIVE | GET /api/v1/settings/academic-years | **PASS** | PG « réglages scolaires en lecture (années, sections, identité) » |
| `settings.school_identity.read` | ACTIVE | GET /api/v1/settings/overview<br>GET /api/v1/settings/numbering | **PASS** | PG « identité de l'école (lecture) (200) » ; « aucune modification des réglages → 403 » |
| `settings.structure.read` | ACTIVE | GET /api/v1/settings/reference-catalog<br>GET /api/v1/settings/sections<br>GET /api/v1/settings/options | **PASS** | PG « réglages scolaires en lecture (années, sections, identité) » |
| `students.directory.export` | ACTIVE | GET /api/v1/schooling/exports/students.pdf<br>GET /api/v1/schooling/exports/students.xlsx | **PASS** | PG « export Excel des élèves = secondaire seulement » |
| `students.directory.print_pdf` | ALIAS | via students.directory.export | **PASS** | alias de `students.directory.export` : PG « export Excel des élèves = secondaire seulement » |
| `students.identity.update` | ACTIVE | — | **PASS** | PG « correction d'identité (200) + audit », « version périmée → 409 », « identité + profil → 422 », « élève du primaire → refusé » ; DIRECTEUR_ETUDES → 403 |
| `students.lifecycle.history.read` | PLANNED | — | **N/A** | N/A — décision du propriétaire du 30/10 : historique du parcours reporté à la version des points (PLANNED) |
| `students.profile.complete` | ACTIVE | — | **PASS** | PG « complément de profil (adresse) d'un élève du secondaire (200) » |
| `students.profile.print_pdf` | ACTIVE | GET /api/v1/schooling/students/{student_id}/profile.pdf | **PASS** | PG « fiche PDF d'un élève du secondaire », « du primaire → 404 » |
| `students.read` | ACTIVE | GET /api/v1/schooling/summary<br>GET /api/v1/schooling/students<br>GET /api/v1/schooling/students/{student_id} | **PASS** | PG « liste des élèves = secondaire seulement », « fiche d'un élève du primaire / d'une autre école → 404 » |

Bilan : N/A 8 · PASS 35

## Rapprochement avec les « 108 attributions » de la mission

Le registre canonique (source de vérité, statut CANONICAL) compte **121 attributions** pour ces trois rôles : les 108 de l'origine (migrations 0008 / 0009) + les variantes de format ajoutées par la décision du 23/10 (alias `*.export_pdf`, `*.export_xlsx`, `*.print`), **moins** les capacités `personnel.*` et `finance.*` retirées aux deux directeurs par la migration 0024 (point 9). **Décisions du propriétaire du 30/10** : le personnel est rendu aux deux directeurs **en lecture** (migration 0102, agents de leur section seulement) ; `documents.print` est retiré de tous les rôles (0103) ; `enrollments.export` est construit et activé (0104) ; l'historique du parcours est reporté à la version des points.

