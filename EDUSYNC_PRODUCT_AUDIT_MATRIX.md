# EduSync — matrice d'audit produit (Niveaux 0, 1 et 2)

Base : 52e226d → commits de cette passe (voir `CERTIFICATION_EVIDENCE_MANIFEST.md` pour le SHA exact).
Preuves : `certification/n0-n1-20261007/*.json` (sondes réelles), captures `certification/n0-n1-20261007/captures/`.
États : PASS · UX_FIX · FUNCTIONAL_FIX · SECURITY_FIX · RBAC_FIX · PERFORMANCE_FIX · OWNER_DECISION · BLOCKED_EXTERNAL.
« Corrigé » = défaut trouvé puis corrigé dans cette passe (état final indiqué après la flèche).

## Niveau 0 — socle

| Surface | Route / écran | Rôles | Permission | API | Desktop | Mobile | État | Preuve | Test |
|---|---|---|---|---|---|---|---|---|---|
| Écran de démarrage | `/` (index.html) | tous | — | `/auth/refresh` | oui | oui | UX_FIX → PASS | `n0-boot-1280.png`, `n1-journey-live.json` | `test_boot_screen_is_styled_inline…` |
| Connexion sans code établissement | `/` | tous | — | `POST /auth/login` scope AUTO | oui (7 largeurs) | oui | FUNCTIONAL_FIX → PASS | `prereq-live.json`, `n0-login-*.png` | `test_sign_in_has_no_school_code…` |
| Choix de l'espace (multi-écoles) | `/` | comptes multi-contextes | — | `POST /auth/login` | oui | oui | PASS | `prereq-live.json` (aucune session avant le choix) | idem |
| Photo de fond licenciée | `/` | — | — | — | oui | oui | PASS | `docs/BRAND_ASSETS.md` | `test_login_background_is_a_local_licensed_asset` |
| Accès Atelier Pro (seulement avant le 1er Manager) | `/` | Manager | — | scope PLATFORM | oui | oui | UX_FIX → PASS | `n1-journey-live.json` | `test_atelier_pro_link_only_before_a_manager_exists…` |
| Design moderne (Inter, cartes centrées) | toutes | tous | — | — | oui | oui | UX_FIX → PASS | `captures/n1-dashboard-*.png` | idem |
| Afficher / masquer le mot de passe | `/` | tous | — | — | oui | oui | PASS | `n1-journey-live.json` | — |
| Session persistante (1.1) | cookie appareil | tous | — | `/auth/refresh`, `/auth/logout-all` | — | — | FUNCTIONAL_FIX → PASS | `prereq-live.json` (20 contrôles) | `test_session_is_persistent…` |
| CSRF cookies | auth | — | — | origine vérifiée | — | — | SECURITY_FIX → PASS | `prereq-live.json` | — |
| Montants exacts (1.2) | toutes API Finance | — | — | JSON décimal | — | — | FUNCTIONAL_FIX → PASS | `prereq-live.json` (CDF/USD) | `test_money_leaves_the_api…` |
| Rôle worker dédié (1.3) | workers | — | — | — | — | — | SECURITY_FIX → PASS | `prereq-live.json` (10 contrôles) | `test_workers_refuse_owner…` |
| Sécurité du compte plateforme (1.4) | Atelier Pro › Sécurité et appareils | PLATFORM | — | `/auth/platform/*` | oui | oui | FUNCTIONAL_FIX → PASS | `prereq-live.json` | — |
| PWA (manifest, icônes, SW) | — | — | — | — | — | — | PASS (clôture précédente) ; installation réelle : HTTPS public BLOCKED_EXTERNAL | `N0_CERTIFICATION_REPORT.md` | `test_pwa_identity_assets_declared` |
| États réseau / hors ligne | toutes | — | — | — | — | — | PASS (inventaire) ; écriture locale différée : OWNER_DECISION | `N0_CERTIFICATION_REPORT.md` | tests point 11 |
| En-têtes HTTP (D) | interface + API | — | — | — | — | — | SECURITY_FIX → PASS ; HSTS : BLOCKED_EXTERNAL | `hardening-http-live.json` | `test_sensitive_operations_are_rate_limited…` |
| Lanceur local | raccourcis | — | — | — | — | — | FUNCTIONAL_FIX → PASS (tué par WSL, S3 lent après redémarrage, WSL bloqué) | `N0_CERTIFICATION_REPORT.md` | `test_local_launcher_survives…` |

## Niveau 1 — plateforme (Atelier Pro)

| Surface | Écran | Rôles | Permission | API | Desktop | Mobile | État | Preuve |
|---|---|---|---|---|---|---|---|---|
| Menu selon les permissions | barre latérale | PLATFORM | calculé serveur | `GET /platform/team/me` | oui | oui | RBAC_FIX → PASS | `team-live.json`, `n1-custom-role-1280.png` |
| Rôles PLATFORM_CUSTOM | Équipe › Rôles | Manager | `collaborators.manage` | `/platform/team/roles*` | oui | oui | FUNCTIONAL_FIX → PASS | `team-live.json` |
| Anti-escalade (A) | Équipe | Manager | réservée | idem | — | — | SECURITY_FIX → PASS | `team-live.json` (58) |
| Rôle brouillon/archivé sans droit | — | — | — | `require_platform_actor` | — | — | SECURITY_FIX → PASS | `team-live.json` « Rôle archivé : capacité retirée » |
| Comptes plateforme | Équipe › Comptes | Manager | `collaborators.manage` | `/platform/team/users*` | oui | oui | FUNCTIONAL_FIX → PASS | `team-live.json`, `n1-team-1280.png` |
| Suspension compte plateforme | fiche compte | Manager | idem | `…/suspend` | oui | oui | PASS | `team-live.json` |
| Tableau de bord réel | Tableau de bord | PLATFORM | `schools.read` | `/platform/dashboard` | oui | oui | PASS (aucune métrique inventée) | `n1-dashboard-*.png` |
| Création d'école complète | Écoles › Nouvelle école | Manager | `schools.create` | `POST /platform/schools` | oui | oui | FUNCTIONAL_FIX → PASS (dont 500 en concurrence corrigé) | `school-lifecycle-live.json` |
| Administrateur initial | Écoles › Créer admin | Manager | `school_admin.bootstrap` | `…/bootstrap-admin` | oui | oui | PASS ; réinitialisation de mot de passe : OWNER_DECISION | `SCHOOL_PROVISIONING_REPORT.md` |
| Suspension / réactivation : effets réels | Écoles | Manager | `schools.suspend/activate` | `…/suspend` `…/reactivate` | oui | oui | SECURITY_FIX → PASS | `school-lifecycle-live.json` |
| Santé mesurée | État du service | PLATFORM | `health.read` | `/platform/system/health` | oui | oui | FUNCTIONAL_FIX → PASS | `health-live.json`, `n1-health-1280.png` |
| Audit | Journal d'audit | PLATFORM | `audit.read` / `audit.export` | `/platform/audit-log*` | oui | oui | FUNCTIONAL_FIX → PASS | `audit-live.json` |
| Notifications ciblées | Notifications | PLATFORM | `notifications.system.send` | `/platform/notification-campaigns` | oui | oui | FUNCTIONAL_FIX → PASS | `notifications-live.json` |
| Centre de notifications | cloche (école + Atelier Pro) | tous | `notifications.internal.read` (école) | `/notifications/inbox`, `/platform/inbox` | oui | oui | FUNCTIONAL_FIX → PASS | idem, `n1-bell-1280.png` |
| Push | — | — | — | `…/push-subscriptions` | — | — | PASS (simulateur) ; réel : BLOCKED_EXTERNAL | idem |
| Temps réel (cloche) | cloche | tous | lecture boîte | `/notifications/stream`, `/platform/inbox/stream` (SSE) | oui | oui | FUNCTIONAL_FIX → PASS | `realtime-live.json` |
| Limitation de débit (E) | — | — | — | middleware | — | — | SECURITY_FIX → PASS | `hardening-http-live.json` |
| Résilience (K) | — | — | — | 503 | — | — | FUNCTIONAL_FIX → PASS | `resilience-live.json` |
| Sauvegarde / restauration (G) | — | — | — | outil local | — | — | PASS | `backup-restore-live.json` |
| Chaîne d'approvisionnement (J) | — | — | — | — | — | — | SECURITY_FIX → PASS (PyJWT, source-map-js, verrou Python) | `pip-audit.json`, `sbom.cdx.json` |
| MFA (C) | — | PLATFORM | — | — | — | — | FUNCTIONAL_FIX → PASS (option B + décisions du 2026-10-14) | `MFA_PLATFORM_OPTION_B_REPORT.md` |
| Rôles industriels | — | — | — | — | — | — | OWNER_DECISION (non activés) | `PLATFORM_ROLES_PROPOSAL.md` |

## Niveau 2 — administration de l'école (2026-10-14)

Preuves : `certification/n2-20261014/n2-live.json` (sonde réelle, 50/50), `n2-journey.json` (parcours téléphone 14/14
et 70 mesures de 320 à 1440 px), captures `certification/n2-20261014/captures/`. Rapport : `N2_CERTIFICATION_REPORT.md`.

| Surface | Écran | Rôles | Permission | API | Desktop | Mobile | État | Preuve |
|---|---|---|---|---|---|---|---|---|
| Création de membres par l'école | Accès & rôles › Ajouter un membre | ADMIN_SYSTEME_ECOLE | `access.users.create` | `POST /access/members` | oui | oui (feuille du bas) | FUNCTIONAL_FIX → PASS | `n2-live.json` |
| Mot de passe provisoire montré une fois, jamais rejoué | idem | idem | idem | idem | oui | oui | SECURITY_FIX → PASS | `n2-live.json` |
| Changement obligatoire à la 1re connexion | Connexion | tous | — | `POST /auth/password/first-change` | oui | oui | SECURITY_FIX → PASS | `n2-live.json` |
| Rattachement d'un compte d'une autre école | Accès & rôles | idem | `access.users.create` | `POST /access/members` | oui | oui | PASS ; ni renommage ni réinitialisation (compte partagé) | `n2-live.json` |
| Renommer, réinitialiser, désactiver, réactiver | fiche membre | idem | `access.users.update/activate/credentials.reset` | `/access/members/{id}*` | oui | oui | FUNCTIONAL_FIX → PASS ; révocation immédiate | `n2-live.json` |
| Anti-escalade (gouvernance) | rôles, attributions, membres | délégués | `access.*` | `/access/*` | — | — | SECURITY_FIX → PASS | `n2-live.json` |
| Isolation écoles jumelles A/B | toutes | — | — | — | — | — | PASS (0 fuite) | `n2-live.json` |
| Centre de configuration mobile-first | Paramètres | lecture `settings.*` | — | `/settings/*` | oui (navigation latérale) | oui (liste → section) | UX_FIX → PASS | `n2-journey.json` |
| Années : confirmations, année suivante proposée | Paramètres › Années | `settings.academic_year.*` | — | `/settings/academic-years*` | oui | oui | UX_FIX → PASS | `n2-journey.json` |
| Logo vérifié (au lieu d'une URL) | Paramètres › Identité | `settings.documents.manage` | — | `PUT /documents/branding/logo` | oui | oui | SECURITY_FIX → PASS | `n2-journey.json` |
| Options des sections | Paramètres › Structure | `settings.options.manage` | — | `/settings/options*` | oui | oui | FUNCTIONAL_FIX → PASS | `options_check.mjs` |
| Désactivation de classe confirmée | Paramètres › Structure | `settings.classes.activate` | — | `PUT /settings/classes/{id}` | oui | oui | UX_FIX → PASS ; classe avec élèves : OWNER_DECISION O2 | `n2-journey.json` |
| Règles d'inscription | Paramètres › Inscriptions | `settings.enrollment_policy.*` | — | `/settings/policies/ENROLLMENT` | oui | oui | FUNCTIONAL_FIX → PASS | `enrollment_check.mjs` |
| Autres politiques | — | — | — | `/settings/policies/{kind}` | — | — | OWNER_DECISION O3 (aucun module ne les applique) | `N2_OWNER_DECISIONS.md` |
| Montants exacts et dates françaises | Tarifs, Articles, Années | — | — | — | oui | oui | UX_FIX → PASS | test `formatMoney` sans flottant |
| Mise en service guidée | Paramètres › Mise en service | — | — | `/settings/overview` | oui | oui | UX_FIX → PASS | `readiness_check.mjs` (école C) |
| Barre latérale : icône, rail, aperçu, épingle | shell | tous | — | — | oui | — | UX_FIX → PASS | `rail_check.mjs` |
| Tiroir mobile fermé au passage bureau | shell | tous | — | — | — | oui | UX_FIX → PASS | `rail_check.mjs` |
| Mot de passe de l'administrateur initial | Atelier Pro | Manager | — | — | — | — | OWNER_DECISION O1 | `N2_OWNER_DECISIONS.md` |
| Invitation par lien | — | — | — | — | — | — | BLOCKED_EXTERNAL (fournisseur e-mail/SMS) | `N2_OWNER_DECISIONS.md` |
