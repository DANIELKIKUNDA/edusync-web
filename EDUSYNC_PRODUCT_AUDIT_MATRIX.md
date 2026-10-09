# EduSync — matrice d'audit produit (Niveau 0 et Niveau 1 uniquement)

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
| Accès Atelier Pro discret | `/` | Manager | — | scope PLATFORM | oui | oui | PASS | `n1-journey-live.json` | `test_sign_in_offers_first_run_setup…` |
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
| Limitation de débit (E) | — | — | — | middleware | — | — | SECURITY_FIX → PASS | `hardening-http-live.json` |
| Résilience (K) | — | — | — | 503 | — | — | FUNCTIONAL_FIX → PASS | `resilience-live.json` |
| Sauvegarde / restauration (G) | — | — | — | outil local | — | — | PASS | `backup-restore-live.json` |
| Chaîne d'approvisionnement (J) | — | — | — | — | — | — | SECURITY_FIX → PASS (PyJWT, source-map-js, verrou Python) | `pip-audit.json`, `sbom.cdx.json` |
| MFA (C) | — | PLATFORM | — | — | — | — | OWNER_DECISION | `MFA_PROPOSAL.md` |
| Rôles industriels | — | — | — | — | — | — | OWNER_DECISION (non activés) | `PLATFORM_ROLES_PROPOSAL.md` |
