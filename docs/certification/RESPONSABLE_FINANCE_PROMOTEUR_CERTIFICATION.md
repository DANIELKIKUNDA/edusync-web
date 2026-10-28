# Certification — Responsable chargé des finances et Promoteur

Date : 28/10/2026 · Branche `claude/responsable-finance-promoteur-certification`, partie de `main` (`c34e16a`).
Statuts : **PASS** · **FAIL** · **BLOCKED**. Résultats réels sur la pile locale (école C). Aucune fusion, aucun déploiement,
aucune PR ouverte (une PR déclencherait GitHub Actions, bloqué par la facturation du compte).

## 1. Contrat appliqué

| Rôle | Doctrine (POINT3B, décisions 03 et 05) | Droits actifs |
|---|---|---:|
| Responsable chargé des finances | Contrôle et lecture financière globale ; pas d'encaissement ni de manipulation de caisse | 43 |
| Promoteur | Gouvernance : voir, suivre, imprimer, exporter ; aucune mutation, aucun SMS aux parents | 73 |

**Décision du propriétaire (28/10/2026)** : les deux rôles **analysent** la reprise de l'historique financier mais ne
l'**exécutent** pas (l'exécution écrit d'anciens paiements et dettes dans les comptes). Retrait par la migration
`0097_promoteur_finance_no_history_execute.sql`, le registre canonique et des tests. L'exécution reste au Gestionnaire et
au Caissier ; une école peut l'attribuer au rôle de son choix.

Aucun autre droit n'a été ajouté ni retiré.

## 2. Anomalies trouvées et corrigées

| # | Gravité | Anomalie | Correction |
|---|---|---|---|
| 1 | Haute | « Relevé PDF » d'un élève : erreur 500 **pour tous les rôles** (`archive_generated_tx` utilisé sans import dans `finance_reports/api/router.py`) | Import ajouté ; nouveau test `test_no_undefined_global_names.py` qui vérifie tout le serveur (prouvé en échec sur l'ancien code) |
| 2 | Moyenne | Écrans appelant des listes d'administration refusées (403) : années scolaires (Recouvrement), options (filtres des élèves), référentiel des classes (ordre des classes) | Sélecteurs ouverts à tout membre de l'école, comme `/classes/selector` : `listYearSelector` existant, nouveau `/settings/options/selector` (options actives, libellés) ; référentiel chargé seulement avec son droit |
| 3 | Moyenne | Carte « Encaissements du jour » affichée au Promoteur, au Responsable financier et au Gestionnaire avec « Ouvrez votre caisse », sans droit d'ouvrir une caisse | Carte réservée à qui ouvre une caisse (`finance.cash.open`, Caissier) ; les superviseurs gardent « Situation des caisses » |
| 4 | Faible | « CDF » affiché : titre archivé « Suivi mensuel du recouvrement (CDF) » (Documents, accueil) et état vide du recouvrement | Nouveaux titres en « FC » ; titres déjà archivés affichés en « FC » (`displayTitle`) ; état vide en « FC » (identique à la PR #27) |
| 5 | Faible | Code mort `academic_year_id if 'students.profile'!='students.profile' else None` (fiche élève) signalé par le nouveau test | Remplacé par `None` (comportement inchangé) |

## 3. Résultats

| Contrôle | Commande | Résultat |
|---|---|---|
| Tests backend | `python -m pytest -q` | **1060 passed**, 1 skipped, 0 échec |
| Tests frontend | `npx vitest run` | **80/80** |
| TypeScript / build | `npx tsc --noEmit` · `npx vite build` | **PASS** |
| Tests navigateur de composants | `EDUSYNC_TEST_BROWSER=msedge npm run test:browser` (seuls) | **28 passed**, 3 skipped, 0 échec |
| Registre RBAC | `tools/ci/rbac_registry.py check` | **0 dérive** |
| PostgreSQL réel — caissier | `tools/ci/cashier_postgres_integration.py` | **PASS** |
| Sonde API des deux rôles | `tools/local/finance_roles_probe.py` | **36/36 PASS** |
| Recette navigateur des deux rôles | `browser-tests/local_finance_roles_certification.mjs` | **20/20 PASS** |
| Robot d'exploration | `local_audit_robot.mjs` à 1440 px | Responsable financier : 14 constats au 1er passage → **0** après correction ; Promoteur : **0** |
| Non-régression Gestionnaire | `local_gestionnaire_certification.mjs` | **18/18 PASS** |
| Non-régression Caissier | `local_caissier_certification.mjs` | **0 échec** (script aligné sur celui de la PR #27) |

### Détail de la sonde API (vérifié contre la base)

- Lectures : profils et rapport périodique, élèves, sélecteurs (années, classes, options), relevé d'un élève, **Relevé
  PDF** (vrai PDF, plus d'erreur 500).
- Refus (403) : ouvrir une caisse, encaisser, inscrire, modifier l'identité de l'école, créer un agent, **exécuter une
  reprise financière**, ajouter un membre ; **aucune écriture** en base après ces refus (paiements, caisses,
  inscriptions, agents, membres).
- Élève d'une autre école : introuvable (404).

### Recette navigateur

Chaque module du menu est ouvert (Responsable financier : Paramètres, Élèves, Centre financier et tous ses onglets,
Documents, Accès & rôles ; Promoteur : en plus Personnel, Effectifs, Intendance, Communication). Aucun bouton
d'opération (encaisser, ouvrir une caisse, inscrire, nouvel agent, ajouter un membre, exécuter une reprise), aucun refus
serveur, aucun « CDF ». Responsive : Accueil, Centre financier et Élèves à 320, 390, 768, 1024 et 1440 px, avec une
navigation réelle (barre du bas sur téléphone) et aucun débordement horizontal.

## 4. BLOCKED / non certifié

| Point | Raison |
|---|---|
| CI GitHub | Bloquée par la facturation du compte ; aucune PR ouverte, aucun résultat CI revendiqué |
| Staging | Non déployé |
| Droits PLANNED des deux rôles (vues VF01 à VF04, historique des paiements, exports d'inventaire…) | Non construits, masqués ; hors de ce lot |

## 5. Conclusion

Les deux rôles sont **certifiés en local** : contrat respecté, décision du 28/10 appliquée, aucune écriture possible,
toutes les suites vertes, aucune régression sur le Gestionnaire et le Caissier. La branche est **techniquement prête
pour une décision de fusion** ; la seule condition manquante est une CI GitHub verte sur son dernier commit.

Note : la PR #27 contient une recette (`local_section_leaders_certification.mjs`) dont la vérification responsive peut
rester sur la même page à moins de 1024 px ; la méthode corrigée ici (barre du bas, échec si la page ne s'ouvre pas) est
à reporter dans la PR #27 quand elle sera reprise.
