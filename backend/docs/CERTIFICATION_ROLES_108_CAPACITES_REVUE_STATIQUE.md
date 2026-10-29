# Audit de couverture backend — trois rôles (revue statique)

Branche : `chatgpt/intendant-etudes-discipline-certification`. Ce rapport **n'est pas une certification exécutée** : une occurrence de capacité dans un routeur ne prouve ni son accessibilité, ni sa sécurité, ni le succès des tests.

**Légende :** `Repérée` = capacité référencée textuellement dans un des routeurs examinés ; `À localiser` = non retrouvée dans ce sous-ensemble, pas nécessairement absente du backend. Les permissions de documents, tableaux de bord et réglages peuvent être implémentées dans d'autres modules.

## INTENDANT — 29 capacités

| Capacité | Indice dans les routeurs audités | État |
|---|---|---|
| `audit.entity.history.read` | audit | Repérée |
| `documents.history.read` | documents | Repérée |
| `documents.open` | documents | Repérée |
| `documents.print` | — | À localiser |
| `inventory.assets.create` | stewardship | Repérée |
| `inventory.assets.history.read` | stewardship | Repérée |
| `inventory.assets.read` | stewardship | Repérée |
| `inventory.assets.repair.record` | stewardship | Repérée |
| `inventory.assets.status.update` | stewardship | Repérée |
| `inventory.assets.update` | stewardship | Repérée |
| `inventory.counts.create` | stewardship | Repérée |
| `inventory.counts.export_xlsx` | stewardship | Repérée |
| `inventory.counts.print` | stewardship | Repérée |
| `inventory.counts.read` | stewardship | Repérée |
| `inventory.counts.record` | stewardship | Repérée |
| `inventory.counts.validate` | stewardship | Repérée |
| `inventory.stock.adjust` | stewardship | Repérée |
| `inventory.stock.export_xlsx` | stewardship | Repérée |
| `inventory.stock.issue` | stewardship | Repérée |
| `inventory.stock.item.manage` | stewardship | Repérée |
| `inventory.stock.low_alerts.read` | stewardship | Repérée |
| `inventory.stock.movements.read` | stewardship | Repérée |
| `inventory.stock.read` | stewardship | Repérée |
| `inventory.stock.receive` | stewardship | Repérée |
| `inventory.stock.sheet.print` | stewardship | Repérée |
| `notifications.internal.dismiss` | notifications | Repérée |
| `notifications.internal.read` | notifications | Repérée |
| `personnel.read` | personnel | Repérée |
| `settings.school_identity.read` | — | À localiser |

## DIRECTEUR_ETUDES — 41 capacités

| Capacité | Indice dans les routeurs audités | État |
|---|---|---|
| `audit.entity.history.read` | audit | Repérée |
| `communications.compose` | communications | Repérée |
| `communications.history.read` | communications | Repérée |
| `communications.read` | communications | Repérée |
| `communications.send.class` | communications | Repérée |
| `communications.send.individual` | communications | Repérée |
| `communications.send.section` | communications | Repérée |
| `communications.sms.send` | communications | Repérée |
| `dashboard.school.drilldown` | — | À localiser |
| `dashboard.school.export` | — | À localiser |
| `dashboard.school.print` | — | À localiser |
| `dashboard.school.read` | — | À localiser |
| `documents.history.read` | documents | Repérée |
| `documents.open` | documents | Repérée |
| `documents.print` | — | À localiser |
| `enrollments.export_pdf` | — | À localiser |
| `enrollments.export_xlsx` | — | À localiser |
| `enrollments.print` | — | À localiser |
| `enrollments.read` | — | À localiser |
| `families.children.read` | — | À localiser |
| `families.read` | schooling | Repérée |
| `families.responsibles.read` | — | À localiser |
| `headcounts.by_class.read` | effectifs | Repérée |
| `headcounts.by_option.read` | effectifs | Repérée |
| `headcounts.by_section.read` | effectifs | Repérée |
| `headcounts.export_pdf` | — | À localiser |
| `headcounts.export_xlsx` | — | À localiser |
| `headcounts.movements.read` | effectifs | Repérée |
| `headcounts.print` | — | À localiser |
| `headcounts.read` | effectifs | Repérée |
| `notifications.internal.dismiss` | notifications | Repérée |
| `notifications.internal.read` | notifications | Repérée |
| `personnel.assignments.read` | personnel | Repérée |
| `personnel.functions.read` | personnel | Repérée |
| `personnel.read` | personnel | Repérée |
| `personnel.summary.read` | personnel | Repérée |
| `settings.academic_year.read` | — | À localiser |
| `settings.school_identity.read` | — | À localiser |
| `settings.structure.read` | — | À localiser |
| `students.lifecycle.history.read` | — | À localiser |
| `students.read` | schooling | Repérée |

## DIRECTEUR_DISCIPLINE — 38 capacités

| Capacité | Indice dans les routeurs audités | État |
|---|---|---|
| `audit.entity.history.read` | audit | Repérée |
| `communications.compose` | communications | Repérée |
| `communications.history.read` | communications | Repérée |
| `communications.read` | communications | Repérée |
| `communications.send.class` | communications | Repérée |
| `communications.send.individual` | communications | Repérée |
| `communications.send.section` | communications | Repérée |
| `communications.sms.bulk_send` | communications | Repérée |
| `communications.sms.send` | communications | Repérée |
| `dashboard.school.drilldown` | — | À localiser |
| `dashboard.school.export` | — | À localiser |
| `dashboard.school.print` | — | À localiser |
| `dashboard.school.read` | — | À localiser |
| `documents.history.read` | documents | Repérée |
| `documents.open` | documents | Repérée |
| `documents.print` | — | À localiser |
| `enrollments.export_pdf` | — | À localiser |
| `enrollments.print` | — | À localiser |
| `enrollments.read` | — | À localiser |
| `families.children.read` | — | À localiser |
| `families.read` | schooling | Repérée |
| `families.responsibles.read` | — | À localiser |
| `headcounts.by_class.read` | effectifs | Repérée |
| `headcounts.by_section.read` | effectifs | Repérée |
| `headcounts.movements.read` | effectifs | Repérée |
| `headcounts.print` | — | À localiser |
| `headcounts.read` | effectifs | Repérée |
| `notifications.internal.dismiss` | notifications | Repérée |
| `notifications.internal.read` | notifications | Repérée |
| `personnel.assignments.read` | personnel | Repérée |
| `personnel.functions.read` | personnel | Repérée |
| `personnel.read` | personnel | Repérée |
| `settings.academic_year.read` | — | À localiser |
| `settings.school_identity.read` | — | À localiser |
| `settings.structure.read` | — | À localiser |
| `students.identity.update` | schooling | Repérée |
| `students.lifecycle.history.read` | — | À localiser |
| `students.read` | schooling | Repérée |

## Contrôles de certification à réaliser

1. Vérifier les chemins et permissions de chaque capacité dans tous les routeurs et dépendances, et non uniquement les dix fichiers parcourus.
2. Exécuter les tests de sécurité multi-école, périmètre `SECTION=SECONDAIRE`, privilèges croisés et pagination/export.
3. Exécuter migrations et tests PostgreSQL sur une base de test isolée ; vérifier les accès aux documents signés et aux historiques d'audit.
4. Compléter cette matrice avec `PASS`, `FAIL`, `N/A` et la preuve de chaque scénario exécuté par Codex local.

## Réserves issues de la revue

- L'endpoint `audit/entities/{entity_type}/{entity_id}` vérifie `audit.entity.history.read` et l'école, mais ne contrôle pas explicitement le périmètre SECTION de l'entité demandée ; vérifier le risque de divulgation de `old_json` / `new_json`.
- Les liens signés de documents revalident l'appartenance à l'école, mais pas explicitement les capacités de l'utilisateur au moment de l'ouverture ; vérifier le scénario de révocation de permission pendant la validité du lien.
- Les contrôles de périmètre sont parfois appliqués en Python après la requête SQL ; tester les cas d'un même responsable présent dans plusieurs sections.
