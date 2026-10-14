# N2 — Audit métier backend / frontend avant décisions (O1 à O6)

Date : 2026-10-14. Nature : **audit seul**. Aucun code, aucune migration, aucune permission et aucun écran n'a été
modifié pendant cette passe. La clôture du N2 est suspendue : pas de tag tant que le propriétaire n'a pas décidé.

Doctrine appliquée : COPIER → COMPARER → CERTIFIER LA PARITÉ → ENRICHIR. Quand une règle Desktop n'est pas retrouvée,
elle est notée `OWNER_DECISION_REQUIRED` ou `UNKNOWN_REQUIRES_GOLDEN_MASTER`, jamais inventée.

## 0. Sources consultées et limite principale

| Source | Contenu utile |
|--------|---------------|
| `docs/reference/WEB0_AUDIT_PRESERVATION_EDUSYNC.md` §3.1 | Le Desktop avait « un centre de configuration riche : identité, années, sections/options, classes, frais, tarifs, politiques d'inscription, avantages, encaissement, plans anticipés, contributions, articles, documents, sauvegardes, utilisateurs et personnel ». Préservation : **TRÈS FORTE**. |
| `POINT4A_PRESERVATION_MATRIX.md` | Encaissement (`PAYMENT`), inscription (`ENROLLMENT`), avantages (`BENEFITS`) : **PORTÉ BACKEND** ; options : **PORTÉ BACKEND** ; documents et sauvegardes : **CONTRAT PORTÉ**, exécution à raccorder. |
| `contracts/CAPABILITY_REGISTRY.json` + `docs/rbac/POINT3A_CAPABILITY_TREE.md` | 258 droits ; ceux des domaines audités sont marqués `EXISTING_DESKTOP` avec un libellé qui décrit la fonction Desktop. |
| `docs/rbac/POINT3B_*` | Décisions de rôles du propriétaire (attribution de ces droits). |
| Migrations 0006, 0008, 0010, 0013, 0015, 0017, 0038 ; code `backend/src` ; `frontend/src` | État actuel. |
| `.local/closure/wt-old` (ancien arbre de travail) | Ancien centre de configuration Web : **mêmes 8 rubriques qu'avant le N2**, aucun écran de politique ; `getPolicy`/`putPolicy` existaient dans `api.ts` sans être appelés. |
| Historique Git | 23 commits seulement (projet importé d'un bloc) : pas de trace d'écran de politique supprimé dans Git. |
| `CLOTURE_LOCALE_EDUSYNC.md`, `EDUSYNC_CERTIFICATION_CLAUDE.md` | Manque déjà consigné : génération des frais dus à partir des tarifs. |

**Limite** : le **code source et les écrans du Desktop ne sont pas dans ce dépôt**. Ce qu'on sait du Desktop vient des
documents de préservation et du registre des droits (libellés `EXISTING_DESKTOP`). Le **contenu exact** des réglages
Desktop (champs, valeurs, effets) n'est pas retrouvé : il faut le golden master (base, captures ou code Desktop).

## 1. Réponse à la question « écran perdu ou jamais fait ? »

Le projet historique annonçait bien les politiques d'encaissement, l'admission, les avantages, les paramètres
documentaires et les groupes tarifaires d'options. Constat :

- **Côté Desktop** : ces fonctions **existaient** (droits `EXISTING_DESKTOP`, audit de préservation).
- **Côté Web** : au point 4A, elles ont été portées **seulement en contrat serveur** (table `school_policy_documents`,
  routes génériques `GET/PUT /settings/policies/{kind}`, droits), **sans écran et sans brancher les modules métier sur
  ces données**. L'ancien Centre de configuration Web n'a jamais eu ces écrans.
- Conclusion : ce n'est **pas un écran perdu pendant le N2** ; c'est un **portage inachevé depuis le point 4A**
  (fonction Desktop → contrat Web vide). Plusieurs règles Desktop ont été **recodées en dur** dans les modules Web
  (encaissement, avantages) au lieu d'être lues dans la politique.
- Correction d'une formulation de mes rapports N2 : « aucun module ne les applique » est exact **pour les documents de
  politique stockés**, mais incomplet : les règles correspondantes existent, codées en dur, et le Desktop permettait
  (d'après les libellés de droits) de les configurer.

## 2. Inventaire par domaine

Légende de classement : `ACTIVE_AND_CONSUMED` · `CONFIGURABLE_BUT_NO_UI` · `BACKEND_INTERNAL_ONLY` · `DORMANT_FUTURE` ·
`LEGACY_OR_DEAD` · `UNKNOWN_REQUIRES_GOLDEN_MASTER`.

### 2.1 Table commune `school_policy_documents` (migration 0010)

- Colonnes : `school_id`, `kind` ∈ {PAYMENT, ENROLLMENT, BENEFITS, DOCUMENTS, BACKUP, COMMUNICATIONS}, `status`
  (DRAFT/ACTIVE/ARCHIVED), `payload jsonb`, `effective_from/until`, `version` ; une ligne par école et par type ; RLS forcée.
- Écriture : trigger de création d'école (0010, refait en 0038) qui insère PAYMENT, DOCUMENTS, BACKUP, COMMUNICATIONS
  avec des valeurs par défaut ; migration 0013 insère ENROLLMENT pour les écoles **existant à ce moment** (les écoles
  créées ensuite n'ont pas de ligne ENROLLMENT : le module Élèves applique alors ses valeurs par défaut) ; 0015 corrige
  ENROLLMENT (sexe obligatoire) ; route `PUT /settings/policies/{kind}` (versionnée, idempotente, auditée
  `{KIND}_POLICY_UPDATED`) ; écran Inscriptions (N2) pour ENROLLMENT.
- Lecture : `GET /settings/policies/{kind}` ; **un seul lecteur métier** : `postgres_schooling.enrollment_policy()`
  (ENROLLMENT).
- Valeurs par défaut doublées dans `settings/domain/models.py::POLICY_DEFAULTS` — **jamais lues** par le code.

### 2.2 PAYMENT (règles d'encaissement)

| Élément | Valeur |
|---------|--------|
| Desktop | droit `settings.payment_policy.manage` « Modifier **modes / acomptes / fonds / paiements futurs** » (`EXISTING_DESKTOP`) ; plans anticipés cités dans l'audit de préservation |
| Payload Web par défaut | `allow_partial_payments: true`, `currencies: [CDF, USD]`, `implicit_currency_conversion: false` |
| Qui écrit | trigger de création d'école ; route générique |
| Qui lit | **personne** |
| Règles réellement appliquées | codées en dur dans `finance_checkout/domain/models.py` : paiement partiel accepté (`split_payment`), CDF et USD jamais mélangés (`validate_selection`), ordre séquentiel des frais, surplus seulement avec un plan anticipé accepté |
| Plans anticipés | tables `finance_anticipation_plans` / `_memberships` (0017) lues à l'encaissement ; **aucune route ni écran pour créer un plan** (droit `finance.anticipation_plans.manage` non utilisé) |
| Modes de paiement, acomptes, fonds | non retrouvés comme réglages Web |
| Classement | payload : `LEGACY_OR_DEAD` en l'état (stocké, sans effet) ; règles : `ACTIVE_AND_CONSUMED` mais **non configurables** ; contenu Desktop : `UNKNOWN_REQUIRES_GOLDEN_MASTER` |
| Risque si on ajoute un écran maintenant | l'école croirait changer une règle qui n'a aucun effet |

### 2.3 ENROLLMENT (inscription et admission)

| Élément | Valeur |
|---------|--------|
| Desktop | droits `settings.enrollment_policy.read/manage/activate/review` (`EXISTING_DESKTOP`) ; `activate` et `review` non utilisés en Web |
| Payload | `required_student_fields`, `guardian_required_at_enrollment`, `guardian_phone_required` (+ `optional_student_fields`, `family_label_strategy`, `allow_profile_completion_later` semés en 0013, **jamais lus**) |
| Qui lit | `SchoolingUseCases.enroll` : champs exigés (5 champs terrain toujours forcés), responsable exigé, téléphone du responsable exigé |
| Écran | **N2** : Paramètres › Inscriptions (conserve les clés inconnues du payload) |
| Admission | `enrollments.collect_on_admission` (encaisser à l'inscription) ; POINT6A : « Admission n'est pas inventée » — frais ordinaire si l'école le configure |
| Classement | `ACTIVE_AND_CONSUMED` (3 clés) ; 3 clés semées `LEGACY_OR_DEAD` ou `UNKNOWN_REQUIRES_GOLDEN_MASTER` ; revue/activation de conditions : `UNKNOWN_REQUIRES_GOLDEN_MASTER` |

### 2.4 BENEFITS (avantages)

| Élément | Valeur |
|---------|--------|
| Desktop | `settings.benefits.manage` « Configurer **famille nombreuse / enfant du personnel** » (`EXISTING_DESKTOP`) ; parcours Windows validés « famille nombreuse, enfant d'agent » (audit de préservation §3.2) |
| Payload Web | **aucune ligne semée** ; route générique seulement |
| Règles réellement appliquées | codées en dur dans `SchoolingUseCases.enroll` : famille nombreuse = **au moins 5 enfants inscrits** dans le foyer pour l'année, **un seul bénéficiaire** par foyer et par année ; enfant du personnel = lien personnel + choix explicite ; enregistrés dans `student_benefits` |
| Effet financier | **aucun automatique** : `student_benefits` n'est lu par aucun module Finance ; les exonérations passent par les décisions de frais manuelles (POINT6H) |
| Écran | **aucun** pour régler les avantages ; **aucun** non plus dans l'assistant d'inscription pour désigner un bénéficiaire (le backend accepte `large_family_beneficiary` / `staff_beneficiary`, le frontend ne les envoie jamais) |
| Classement | payload : `CONFIGURABLE_BUT_NO_UI` et non lu ; règles : `ACTIVE_AND_CONSUMED` (codées en dur) ; seuil, nombre de bénéficiaires et effet financier Desktop : `UNKNOWN_REQUIRES_GOLDEN_MASTER` |
| Écart de parité | **perte probable** : un parcours Desktop validé (désigner famille nombreuse / enfant d'agent) n'est pas atteignable dans l'interface Web |

### 2.5 DOCUMENTS (paramètres documentaires)

| Élément | Valeur |
|---------|--------|
| Desktop | `settings.documents.manage` « Modifier **préfixes / reçus / logo / signature** » (`EXISTING_DESKTOP`) |
| Payload Web | `receipt_numbering: SERVER_SEQUENCE`, `document_history: true` — **jamais lus** (le mot `document_history` existe dans `documents/api/router.py` mais c'est le nom d'une route, pas une lecture de la politique) |
| Ce qui existe vraiment | logo (`PUT /documents/branding/logo`, écran Documents et Identité) ; réglages d'impression du reçu (`/finance/print-settings` : politique NONE/PROPOSE/AUTO_PREVIEW, format A5/80 mm ; écran Documents) ; numérotation serveur codée en dur ; historique des documents (route) |
| Absent | préfixes de numérotation, signature |
| Classement | payload : `LEGACY_OR_DEAD` ; réglages réels : `ACTIVE_AND_CONSUMED` **hors** de la table de politiques ; préfixes et signature : `UNKNOWN_REQUIRES_GOLDEN_MASTER` |

### 2.6 BACKUP (sauvegardes)

| Élément | Valeur |
|---------|--------|
| Desktop | `settings.backups.read/manage/create/test/restore` (`EXISTING_DESKTOP`) : l'école sauvegardait et restaurait elle-même |
| Payload Web | `enabled: true`, `offsite_required: true` — **jamais lus** |
| Ce qui existe vraiment | outil d'exploitation `tools/local/backup_restore.py` (sauvegarde + restauration vérifiée), hors interface ; `create/test/restore` non utilisés |
| Classement | payload : `LEGACY_OR_DEAD` ; fonction : `BACKEND_INTERNAL_ONLY` (exploitation) ; sauvegarde par l'école : `OWNER_DECISION_REQUIRED` (en SaaS, la sauvegarde est normalement une responsabilité de la plateforme) |

### 2.7 COMMUNICATIONS

| Élément | Valeur |
|---------|--------|
| Payload Web | `internal_notifications: true`, `external_sms_enabled: false` — **jamais lus** |
| Doublon | la liste de préparation lit **une autre table** : `settings_bootstrap_state.internal_notifications_enabled / external_sms_enabled` ; **aucune route n'écrit ces deux colonnes** (valeurs figées à la création) |
| Classement | payload : `LEGACY_OR_DEAD` ; colonnes de `settings_bootstrap_state` : `BACKEND_INTERNAL_ONLY` (lecture seule de fait) ; SMS réel : BLOCKED_EXTERNAL |

### 2.8 Groupes tarifaires des options (O5)

| Élément | Valeur |
|---------|--------|
| Desktop | `settings.option_tariff_group.manage` « Gérer groupes tarifaires options » et `settings.tariff_groups.manage` « Gérer barèmes de groupe » (`EXISTING_DESKTOP`) ; POINT3A cite des « groupes tarifaires de référence » |
| Backend | colonne `school_options.tariff_group_code` (0010) écrite par `PUT /settings/options/{code}` ; **jamais lue** ; les deux droits ne sont vérifiés par **aucune** route (l'option entière est gérée avec `settings.options.manage`) |
| Tarifs | un tarif peut viser classe, section **ou option** (`tariffs.option_id`) ; aucune notion de groupe |
| Frais dus | **aucun code Web ne génère les frais dus à partir des tarifs** (manque déjà consigné ; les sondes créent les frais en SQL). Les groupes tarifaires n'ont donc aujourd'hui aucun consommateur possible |
| Frontend | écran Options (N2) sans champ groupe tarifaire |
| Classement | `DORMANT_FUTURE` / `UNKNOWN_REQUIRES_GOLDEN_MASTER` |

### 2.9 Classes : activation, désactivation, réactivation (O2, O6)

| Élément | Valeur |
|---------|--------|
| Desktop | `settings.classes.activate` « **Activer/désactiver** une classe » ; `settings.classes.rename` « Renommer une classe » (`EXISTING_DESKTOP`) |
| Backend | `PUT /settings/classes/{id}` exige `settings.classes.activate` pour **désactiver** et `settings.classes.rename` pour toute écriture avec `enabled=true` (donc **réactiver**, et aussi renommer) ; pas de contrôle d'inscriptions actives ; audit `SCHOOL_CLASS_UPDATED` |
| Lecteurs de `enabled` | inscription nouvelle : **refusée** dans une classe désactivée ; **changement de classe** vers une classe désactivée : **refusé** (contrôle dans `postgres_schooling.change_class`, ligne 311 — *corrigé le 2026-10-14 : la première version de cet audit le disait à tort accepté*) ; effectifs (`postgres_effectifs.py:61`) : classe désactivée **masquée** ; liste documentaire, périmètres d'accès, import : classe masquée ; recouvrement financier et suivi des frais : classe **toujours affichée** ; tarifs : refusés sur classe désactivée |
| Frontend | N2 : bouton Désactiver/Réactiver avec confirmation, affiché selon le droit exigé par le serveur |
| Classement | `ACTIVE_AND_CONSUMED`, avec **effets incohérents** entre modules |

## 3. Les six points

### O1 — Mot de passe du premier administrateur d'école

- **HISTORIQUE TROUVÉ** : droit `platform.school_admin.bootstrap` « Créer/**réinitialiser** l'administrateur initial »
  (`NEW_APPROVED`, propre au Web) ; `SCHOOL_PROVISIONING_REPORT.md` : compte créé avec le mot de passe saisi par la
  plateforme, compte existant rattaché sans toucher au mot de passe ; rapport d'onboarding N1 : changement à la
  1re connexion « non imposé → OWNER_DECISION ». Desktop : `access.users.credentials.reset` et
  `access.users.pin.self_change` (« changer son propre code secret ») existaient ; règle Desktop de changement imposé
  **non retrouvée**.
- **BACKEND ACTUEL** : `POST /platform/schools/{id}/bootstrap-admin` crée le compte (`must_change_password` reste à
  `false`) ; la partie « réinitialiser » du libellé n'est pas implémentée.
- **FRONTEND ACTUEL** : Atelier Pro › action « administrateur initial » (nom, e-mail, mot de passe ≥ 10).
- **CONSOMMATEURS ACTUELS** : connexion (N2) : si `must_change_password`, étape de changement obligatoire.
- **TESTS** : sonde N1 school_lifecycle ; contrats N2 sur le changement obligatoire (comptes créés par l'école).
- **ÉCART** : un compte créé par l'école doit changer son mot de passe (décision D2), pas celui créé par la plateforme.
- **VRAIE QUESTION** : la plateforme connaît le mot de passe qu'elle a tapé pour le directeur. Doit-il être obligé de le
  changer à sa première connexion, comme les comptes créés par l'école ?
- **RECOMMANDATION TECHNIQUE** : si oui, un seul champ à positionner à la création (`must_change_password=true`,
  `password_set_by='PLATFORM'`) ; le mécanisme existe déjà et est testé.

### O2 — Désactiver une classe qui a des inscriptions actives

- **HISTORIQUE TROUVÉ** : droit Desktop « Activer/désactiver une classe » ; règle Desktop sur les élèves présents
  **non retrouvée** → `UNKNOWN_REQUIRES_GOLDEN_MASTER`.
- **BACKEND ACTUEL** : désactivation sans contrôle des inscriptions.
- **FRONTEND ACTUEL** : confirmation N2 qui dit « les élèves gardent leur inscription ».
- **CONSOMMATEURS ACTUELS** : voir §2.9 — la classe disparaît des effectifs et des listes, mais reste dans le
  recouvrement. (Le changement de classe vers une classe désactivée est en réalité déjà refusé — erratum.)
- **TESTS** : aucun test ne couvre « classe désactivée avec élèves ».
- **ÉCART** : effets incohérents ; le message de confirmation N2 est vrai pour l'inscription, mais **ne dit pas** que les
  élèves disparaissent des effectifs.
- **VRAIE QUESTION** : quand une classe ferme en cours d'année alors qu'elle a des élèves, que doit-il se passer ?
  (a) interdit tant qu'il reste des élèves — il faut d'abord les déplacer ; (b) autorisé, la classe reste visible
  partout pour l'historique mais n'accepte plus d'élèves ; (c) autre règle du Desktop.
- **RECOMMANDATION TECHNIQUE** : quelle que soit la décision, aligner tous les modules sur une même règle, et bloquer le
  changement de classe vers une classe désactivée (cohérence avec l'inscription). À faire après décision.

### O3 — PAYMENT / BENEFITS / DOCUMENTS / BACKUP / COMMUNICATIONS

- **HISTORIQUE TROUVÉ** : fonctions Desktop réelles (§2.2 à §2.7) ; portées en contrat vide au point 4A.
- **BACKEND ACTUEL** : stockées, versionnées, auditées ; **aucune lue**, sauf ENROLLMENT ; règles réelles codées en dur
  ailleurs (encaissement, avantages, impression, numérotation).
- **FRONTEND ACTUEL** : écran pour ENROLLMENT (N2) ; impression et logo dans Documents ; rien pour les autres.
- **CONSOMMATEURS ACTUELS** : aucun pour les payloads ; les modules lisent leurs propres constantes ou tables.
- **TESTS** : routes génériques testées ; aucun test ne prouve un effet métier d'une politique autre qu'ENROLLMENT.
- **ÉCART** : configuration Desktop non portée ; deux sources de vérité possibles (payload ignoré vs code) ; avantages
  non désignables dans l'interface.
- **VRAIES QUESTIONS** (une par domaine, à trancher avec le golden master Desktop) : voir §4.
- **RECOMMANDATION TECHNIQUE** : ne créer **aucun écran** tant qu'un module ne lit pas la donnée ; pour chaque domaine
  validé, faire lire la politique par le module concerné, tester l'effet, puis exposer l'écran. Supprimer ou marquer
  comme obsolètes les payloads jamais lus (après décision), pour éviter deux sources de vérité.

### O4 — Invitation par lien

- **HISTORIQUE TROUVÉ** : aucune trace (ni droit, ni document) ; le Desktop était local, sans e-mail.
- **BACKEND / FRONTEND / CONSOMMATEURS** : rien ; mot de passe provisoire en place (D1).
- **TESTS** : —
- **ÉCART** : aucun par rapport au Desktop ; c'est un enrichissement.
- **VRAIE QUESTION** : faut-il, plus tard, envoyer un lien d'activation par e-mail ou SMS au lieu de remettre un mot de
  passe provisoire ? (suppose un fournisseur réel).
- **RECOMMANDATION TECHNIQUE** : laisser en `BLOCKED_EXTERNAL` ; la décision D1 suffit pour la parité.

### O5 — Groupes tarifaires des options

- **HISTORIQUE TROUVÉ** : deux droits Desktop (§2.8) ; contenu exact non retrouvé.
- **BACKEND ACTUEL** : colonne écrite, jamais lue ; droits jamais vérifiés.
- **FRONTEND ACTUEL** : pas de champ.
- **CONSOMMATEURS ACTUELS** : aucun ; et la génération des frais à partir des tarifs n'existe pas encore en Web.
- **TESTS** : aucun.
- **ÉCART** : fonction Desktop non portée ; dépend d'un manque plus large (génération des frais).
- **VRAIE QUESTION** : dans votre école, des options différentes (ex. deux options du secondaire) partagent-elles le
  même barème de frais ? Le Desktop le gérait-il par « groupe » ?
- **RECOMMANDATION TECHNIQUE** : traiter avec la génération des frais dus (même chantier) ; ne rien exposer avant.

### O6 — Droit utilisé pour désactiver / réactiver une classe

- **HISTORIQUE TROUVÉ** : le registre Desktop est explicite : `settings.classes.activate` = « Activer/**désactiver** »
  ; `rename` = « Renommer ».
- **BACKEND ACTUEL** : réactivation (et toute écriture `enabled=true`) contrôlée par `rename`.
- **FRONTEND ACTUEL** : suit le serveur.
- **TESTS** : aucun ne fige ce choix.
- **ÉCART** : **écart technique avec le registre**, pas une question métier : quelqu'un qui peut seulement renommer
  peut réactiver ; quelqu'un qui peut activer/désactiver ne peut pas réactiver sans le droit de renommer.
- **VRAIE QUESTION** : aucune question métier nouvelle — le registre validé répond. Confirmation simple : « la personne
  qui peut fermer une classe est-elle aussi celle qui peut la rouvrir ? » (le registre dit oui).
- **RECOMMANDATION TECHNIQUE** : exiger `activate` pour tout changement de `enabled` (dans les deux sens) et `rename`
  pour un changement de libellé ; test de contrat. À faire seulement après votre accord.

## 4. Points ouverts nouveaux révélés par l'audit

1. **Génération des frais dus à partir des tarifs** : absente en Web (déjà consignée). Conditionne O5 et une partie de
  PAYMENT.
2. **Désignation des bénéficiaires** (famille nombreuse, enfant du personnel) : possible côté serveur, absente de
  l'interface d'inscription → perte de parité probable (N3).
3. **Plans anticipés** : lus à l'encaissement, mais aucun moyen de les créer.
4. **Notifications internes / SMS** : deux sources (politique COMMUNICATIONS et `settings_bootstrap_state`), aucune
  modifiable.
5. Écoles créées après la migration 0013 : pas de ligne ENROLLMENT (sans conséquence fonctionnelle, valeurs par défaut).

## 5. Ce que cet audit ne change pas

Aucun fichier applicatif modifié. La certification complète exécutée juste avant la suspension (22/22 étapes PASS sur
`7d54d68`) reste valable pour le code tel qu'il est ; ses fichiers de preuve ne sont pas commités et aucun tag n'est posé.

---

## 6. ADDENDUM — Golden master Desktop retrouvé (2026-10-14)

Source fournie par le propriétaire : `C:\Users\cs-ap\Documents\EduSync_AUDIT_WEB_OFFLINE_FIRST.zip` (531 fichiers,
EduSync École Offline 0.11.0-rc.1), extrait **en lecture seule** dans `C:\Users\cs-ap\dev\edusync-desktop-golden`
(hors du dépôt Web, rien n'y est exécuté). Les références ci-dessous sont relatives à ce dossier.

Cet addendum **remplace** les mentions `UNKNOWN_REQUIRES_GOLDEN_MASTER` des sections 2 et 3 quand la règle a été retrouvée.

### 6.1 Le Centre de configuration Desktop

`app/ui/settings_page.py` contient 13 rubriques : Mise en service, Identité, Année, Structure (sections, **options et
groupes tarifaires**), Types de frais, Tarifs (règles hiérarchiques datées + **mois de facturation** + « appliquer aux
classes »), **Conditions d'inscription**, **Avantages & cas particuliers**, **Règles d'encaissement + Plans de paiement
anticipé**, Contributions, Articles, **Documents & numérotation + Sauvegarde & restauration**, Assistance technique.
Certifié dans `artifacts/CERTIFICATION_PARAMETRES.md` (portée annuelle ou permanente de chaque rubrique).

**Conclusion révisée : ce sont des écrans Desktop réels et certifiés, non portés en Web** (le point 4A s'est arrêté au
contrat serveur). Doctrine : COPIER puis CERTIFIER LA PARITÉ.

### 6.2 Règles d'encaissement (PAYMENT) — `app/db/configuration.py::save_payment_policy`, `app/db/finance_checkout.py:495-520` et `:708`

| Réglage Desktop | Effet Desktop (appliqué par la caisse) | Web actuel |
|-----------------|----------------------------------------|-----------|
| Paiements partiels / acomptes autorisés (oui/non) | refus « Les paiements partiels ne sont pas autorisés par la politique de l'école » | toujours autorisés (codé en dur) |
| Acompte minimum | refus sous le minimum (hors plan anticipé) | **absent** |
| Présentation des acomptes dans les rapports (inclure / séparer) | lu par les rapports de recouvrement (`db/terrain.py:627`) | **absent** |
| Paiements anticipés autorisés | conditionne les plans | plans lus, **non créables** |
| Paiement des mois futurs autorisé | refus « Le paiement d'un mois futur est désactivé par la politique de l'école » | non contrôlé |
| Modes acceptés : Espèces, Mobile Money, Banque, Autre | refus d'un mode non accepté (caisse, opérations, inscription) | **la caisse Web n'enregistre aucun mode de paiement** |
| Plans de paiement anticipé (portée école / section / groupe d'Humanités / classe académique / classe ; mois ciblés ; répartition ; facultatif ou obligatoire ; date d'effet) | imputation « mois courant puis mois futurs ciblés » | tables présentes, imputation lue, **aucune création** |

Classement révisé : **ACTIVE_AND_CONSUMED au Desktop → PARITÉ NON ATTEINTE en Web** (Finance : les règles Desktop ont
priorité, aucune redéfinition).

### 6.3 Avantages (BENEFITS) — `app/db/configuration.py::save_benefit_policy`, `app/db/schooling.py:284-460`, `app/domain/benefits.py`

| Réglage Desktop (par **année**) | Défaut Desktop | Web actuel |
|---------------------------------|----------------|-----------|
| Famille nombreuse : activée | non | toujours possible côté serveur |
| … éligible à partir de N enfants | 5 | 5 **codé en dur** |
| … bénéficiaires gratuits | 1 | « un seul bénéficiaire » codé en dur |
| … réduction alternative (%) | 0 | **absent** |
| … frais concerné | SCOLARITE | **absent** |
| Enfants du personnel : activée | non | toujours possible |
| … nombre maximal de bénéficiaires par agent | 2 | **aucun plafond** |
| … réduction (%) | 50 | **absent** |
| … bénéficiaires gratuits | 0 | **absent** |
| Cumul famille nombreuse + enfant du personnel | interdit « sans politique explicite » | non contrôlé |
| Effet financier | réduction portée sur la charge (`charges.discount_percent`, `discount_amount`, `net_amount`) ; gratuit = 100 % | **aucun** |
| Choix du bénéficiaire | toujours manuel (« l'éligibilité est automatique, le bénéficiaire est choisi par l'école ») | **impossible dans l'interface Web** |

Classement révisé : **ACTIVE_AND_CONSUMED au Desktop → PARITÉ NON ATTEINTE** (réglages, plafonds, cumul, réduction,
désignation).

### 6.4 Conditions d'inscription — `app/db/configuration.py::upsert_enrollment_policy_item` (ligne 1032)

Au Desktop, une « condition d'inscription » est une **obligation d'admission annuelle** : libellé, **frais lié**,
obligatoire ou non, **moment du paiement** (à l'inscription / après / facultatif), **paiement différé possible**,
regroupement (bundle), **portée** (école, section, classe académique, classe), ordre ; activation ou désactivation ;
**validation de la rubrique** par l'école (« même si l'école n'exige aucun frais à l'inscription »).

| Point | Constat |
|-------|---------|
| Politique Web `ENROLLMENT` (champs exigés, responsable exigé, téléphone exigé) | **concept propre au Web** (point 4C, corrections terrain) : **aucun équivalent Desktop** (`required_student_fields`, `guardian_required` absents du Desktop) |
| Écran N2 « Inscriptions » | expose ce concept Web : c'est un **enrichissement**, pas la parité ; il ne remplace pas les conditions Desktop |
| Conditions d'admission Desktop | **non portées** en Web (ni table, ni écran) ; droits `settings.enrollment_policy.activate` et `.review` (validation de la rubrique) sans route |

**Correction de mes rapports N2** : SCHOOL_CONFIGURATION_REPORT et N2_OWNER_DECISIONS présentent l'écran Inscriptions
comme « la politique d'inscription ». Il faut lire « règles de saisie propres au Web » ; les conditions d'admission
Desktop restent à porter.

### 6.5 Groupes tarifaires des options (O5) — `app/db/configuration.py:64`, `:387-446`, `:787-826`

- Liste fermée : `GENERAL` « Humanités générales », `TECHNICAL` « Humanités techniques », `OTHER` « Autre groupe ».
- Chaque option des Humanités porte un groupe. Des **règles tarifaires de groupe** existent (`tariff_group_rules` :
  frais, montant, devise, statut ACTIVE / PENDING_OFFICIAL / INACTIVE, périodicité, date d'effet, référence officielle).
- **Résolution du tarif d'une classe** par priorité : classe ouverte (600) > classe académique (500) > **groupe
  d'Humanités (350)** > section (200) > école (100) ; la règle la plus précise gagne, à la date d'effet.
- Les plans anticipés peuvent viser un groupe d'Humanités.
- Web : la colonne existe, mais sans liste fermée, sans règles de groupe et sans résolution ; et la génération des frais
  dus n'existe pas. **Parité non atteinte** ; la règle Desktop est connue : il n'y a pas de question métier à inventer.

### 6.6 Classes (O2, O6) — `app/db/configuration.py:594-608`, `app/db/schooling.py:83-90`

- États : `ACTIVE`, `INACTIVE`, `ARCHIVED`.
- **Inactive avec des élèves : autorisé.** **Archivée : refusé** tant qu'il reste des inscriptions validées (« Une classe
  contenant des inscriptions actives ne peut pas être archivée »).
- Une classe inactive disparaît des listes de choix (inscription, changement de classe, documents à générer) mais reste
  dans l'historique.
- Un **seul** contrôle d'autorisation pour tout changement d'état (rôles ADMIN ou DIRECTION) ; le renommage est une
  opération distincte. → O6 : le registre Web (`settings.classes.activate` pour activer et désactiver) est fidèle au
  Desktop ; c'est le serveur Web qui s'en écarte.
- Web (avant correction) : deux états seulement (`enabled`), pas d'archivage ; changement de classe vers une classe inactive
  déjà refusé (erratum) ; liste des classes des effectifs qui masquait la classe inactive (au Desktop, la liste filtrée ne servait qu'aux choix).

### 6.7 Documents & sauvegardes — `app/db/configuration.py:1166-1201`

- Documents : **préfixe des reçus** (REC), **préfixe des rapports** (RAP), **nombre de copies** (1 à 5), format (80 mm,
  58 mm, A5), impression automatique, **signataire (nom, fonction)**, affichage du logo, imprimantes, dossier des
  documents ; consommés par la numérotation (`db/database.py:871`) et les PDF (`services/documents.py:1519` et `:1770`).
- Web : format A5 / 80 mm, politique d'impression du reçu et logo ; **préfixes, copies, signataire et 58 mm absents**.
- Sauvegarde : automatique quotidienne, rétention (1 à 365, 30 par défaut), vérification SHA-256, dossier local et
  externe, « Sauvegarder maintenant », « Tester », « Restaurer » (rôle ADMIN). Propre à un logiciel installé dans l'école.

### 6.8 Communications

Aucune trace de SMS ni de politique de communication dans le Desktop : la politique Web `COMMUNICATIONS` est **propre
au Web** (`DORMANT_FUTURE`).

### 6.9 Comptes et premier administrateur (O1) — `app/db/operations.py:47-60` et `:134-140`, `app/ui/users_page.py`

- Desktop : le secret est un **PIN de 4 à 12 chiffres**.
- **Premier administrateur** : au premier lancement, il **définit lui-même** son PIN (`set_initial_admin_pin`, refusé
  s'il est déjà défini) ; personne d'autre ne le connaît.
- Autres comptes : PIN initial saisi par l'administrateur ; **aucun changement imposé** ; chacun peut changer son PIN ;
  seul l'administrateur change celui d'un autre (réinitialisation).
- L'administrateur principal ne peut pas être désactivé.
- Web : la décision D2 (changement obligatoire pour les comptes créés par l'école) va **au-delà** du Desktop. C'est une
  décision du propriétaire du 2026-10-14, assumée comme enrichissement de sécurité (mot de passe en ligne et non PIN local).

## 7. Les six points après golden master

| Point | Règle Desktop retrouvée | Écart Web | Reste-t-il une question métier ? |
|-------|-------------------------|-----------|----------------------------------|
| O1 | Le premier administrateur choisit lui-même son secret ; personne d'autre ne le connaît | l'administrateur créé par la plateforme garde le mot de passe tapé par la plateforme | **Oui, une confirmation** : transposer au Web revient à lui imposer de choisir son mot de passe à la première connexion |
| O2 | Inactive autorisée avec élèves ; **archivage refusé** avec inscriptions actives ; une classe inactive est seulement retirée des listes de choix | pas d'archivage ; liste des classes des effectifs qui la masquait (le changement de classe était déjà refusé — erratum) | **Non** pour la règle (copier le Desktop) ; à confirmer seulement si vous voulez changer cette règle |
| O3 | Encaissement, avantages, conditions d'admission, documents, sauvegarde : écrans et effets réels (§6.2 à 6.7) ; communications : rien | parité non atteinte | **Oui pour deux sujets** : la sauvegarde par l'école (logiciel installé → service en ligne) ; l'ordre de portage (Finance prioritaire) |
| O4 | rien (local, sans e-mail) | — | Non : enrichissement futur, BLOCKED_EXTERNAL |
| O5 | Groupes GENERAL / TECHNICAL / OTHER, règles de groupe, priorité 350 | non porté ; dépend de la génération des frais | **Non** pour la règle ; c'est un chantier de portage |
| O6 | un seul droit pour tout changement d'état ; renommage séparé | le serveur Web demande « renommer » pour réactiver | **Non** : erreur technique à corriger |

## 8. Recommandation technique (sans décider le métier)

1. Ouvrir un lot **« parité Paramètres Desktop »** avant le N3 Finance : règles d'encaissement, modes de paiement et
   plans anticipés ; avantages (réglages par année, plafonds, cumul, réduction sur les frais, désignation à
   l'inscription) ; conditions d'admission ; groupes tarifaires, résolution hiérarchique des tarifs et **génération des
   frais dus** ; documents (préfixes, copies, signataire, 58 mm) ; états de classe avec archivage.
2. Corriger O6 et l'incohérence O2 (changement de classe, effectifs) en copiant le Desktop.
3. Requalifier l'écran N2 « Inscriptions » en « règles de saisie » et ne pas le présenter comme la parité.
4. Ne pas clôturer le N2 sur la configuration tant que ce lot n'est pas au moins planifié avec le propriétaire. La partie
   « utilisateurs et droits de l'école » du N2 reste indépendante et certifiée.


## 9. Suite donnée (décisions du propriétaire du 2026-10-14)

| Point | Décision | Réalisé |
|-------|----------|---------|
| O1 | Le premier `ADMIN_SYSTEME_ECOLE` choisit son mot de passe avant toute session | `BootstrapSchoolAdmin` marque le **nouveau** compte `must_change_password` (`password_set_by='PLATFORM'`) ; compte existant rattaché inchangé ; le mot de passe tapé par la plateforme n'ouvre que l'étape de choix (pas de session) ; sonde cycle de vie : 3 contrôles dédiés |
| O2 | Copier le Desktop (pause avec élèves, archivage si vide) | migration 0059 (`status` ACTIVE / INACTIVE / ARCHIVED, `enabled` = ACTIVE), route `POST /settings/classes/{id}/status`, effectifs qui gardent les classes en pause, archivage refusé avec inscriptions validées, classe archivée en lecture seule, année close en lecture seule ; sonde `class_status_probe.py` 21/21 |
| O6 | Corriger le RBAC | état : `settings.classes.activate` seul ; renommage : `settings.classes.rename` seul ; un `PUT` avec `enabled` ne change plus l'état (refus explicite) ; audit `SCHOOL_CLASS_STATUS_CHANGED` avant/après |
| Sauvegardes | Pas de restauration directe par l'école | aucun bouton de restauration ; reste `NOT_APPLICABLE_IN_SAAS` (à documenter dans la comparaison des 13 rubriques) |
| O3, O5 | Parité avant N3 Finance | lot « parité Paramètres » en cours |
