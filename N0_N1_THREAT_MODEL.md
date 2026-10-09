# EduSync Web — Modèle de menaces N0 / N1

Périmètre : démarrage, connexion, sessions, Atelier Pro (plateforme), écoles, équipe plateforme, rôles,
notifications, santé, audit. Base : commit de certification (voir `CERTIFICATION_EVIDENCE_MANIFEST.md`).
Chaque ligne renvoie à une preuve exécutée sur l'instance locale isolée (PostgreSQL 16 RLS, Redis, SeaweedFS).

Légende de statut : **MAÎTRISÉ** (contrôle en place et prouvé), **PARTIEL** (contrôle en place, limite
documentée), **BLOCKED_EXTERNAL** (dépend d'une infrastructure non disponible en local), **OWNER_DECISION**.

| # | Menace | Contrôles en place | Preuve | Statut |
|---|---|---|---|---|
| 1 | Force brute sur la connexion | Argon2 ; verrou du compte visé après 7 échecs / 15 min ; seuil par adresse à 50 (corrigé : il était aussi de 7 et bloquait une école entière derrière un NAT) ; empreintes dans Redis, jamais l'e-mail en clair | `hardening-http-live.json` « verrouillage du compte visé », « les autres comptes ne sont pas bloqués » | MAÎTRISÉ |
| 2 | Énumération de comptes | Réponse identique (401, même corps) pour compte inconnu et mauvais mot de passe ; mot de passe vérifié contre un hachage factice si le compte n'existe pas ; la liste des espaces n'est donnée qu'après authentification réussie | `prereq-live.json` « même réponse (pas d'énumération) », « ne révèle pas les contextes » | MAÎTRISÉ |
| 3 | Fixation de session | Aucun identifiant de session accepté du client : jeton opaque créé côté serveur à la connexion, haché en base, tourné à chaque renouvellement | `prereq-live.json` rotation | MAÎTRISÉ |
| 4 | Rejeu de jeton (vol de cookie) | Rotation + fenêtre de grâce 60 s ; ancien jeton rejoué après la grâce → session entière révoquée (`ROTATED_TOKEN_REUSED`) et jeton d'accès coupé | `prereq-live.json` 1.1 réutilisation | MAÎTRISÉ |
| 5 | CSRF | Cookie `HttpOnly; SameSite=Lax; Path=/api/v1/auth` ; contrôle d'origine sur login/refresh/logout/logout-all (Origin ou Sec-Fetch-Site) ; les API métier exigent un jeton Bearer (pas de cookie) | `prereq-live.json` CSRF ×4 | MAÎTRISÉ |
| 6 | XSS | CSP `script-src 'self'` (aucun script inline ni eval), React sans `dangerouslySetInnerHTML` (test statique), jetons jamais en localStorage, libellés d'audit rendus en texte | `hardening-http-live.json` ; `test_point10h13…frontend_has_no_known_raw_html…` | MAÎTRISÉ (styles inline autorisés : risque résiduel faible, pas d'exécution de script) |
| 7 | Redirection ouverte | Aucun paramètre de redirection ; liens de notification limités à un chemin relatif interne, vérifié par l'API **et** par une contrainte SQL | `notifications-live.json` « Lien refusé » ×4, « lien externe impossible même en SQL direct » | MAÎTRISÉ |
| 8 | BOLA / IDOR | Toutes les lectures filtrent par compte/école côté serveur ; RLS PostgreSQL FORCE sur les tables école ; révocation d'appareil limitée au propriétaire | `prereq-live.json` (session d'autrui), `notifications-live.json` (notification d'autrui ×2) | MAÎTRISÉ |
| 9 | Élévation de privilèges plateforme | Capacité d'équipe réservée et non délégable (API + déclencheur SQL) ; pas d'auto-attribution, auto-suspension, auto-réinitialisation ; impossible d'agir sur un compte plus puissant ; impossible de déléguer une capacité non détenue ; dernier Manager protégé (verrou consultatif) | `team-live.json` (58 contrôles) | MAÎTRISÉ |
| 10 | Falsification du `school_id` | Le contexte école vient du jeton signé puis est rechargé en base à chaque requête (appartenance active, versions) ; RLS par `app.current_school_id` | tests statiques `test_school_context_reloads_permissions…` ; probes de clôture RLS/BOLA | MAÎTRISÉ |
| 11 | Contournement de la première installation | Création du Manager impossible dès qu'un Manager existe ; code d'installation exigible ; limité à 10/h par adresse | `test_local_closure_20261006` ; `rate_limit.py` | MAÎTRISÉ |
| 12 | Routes interdites | Test statique : toute route non publique exige `require_school_actor` ou `require_platform_actor` ; chaque mutation plateforme vérifie sa capacité ; compte école refusé sur l'Atelier Pro et inversement | `test_every_non_public_api_route…`, `team-live.json`, `notifications-live.json` | MAÎTRISÉ |
| 13 | Abus d'un rôle PLATFORM_CUSTOM | Un rôle plateforme ne peut contenir que des capacités plateforme (déclencheur SQL) ; invisible au rôle tenant (RLS) ; un rôle en brouillon ou archivé ne donne plus rien (correctif de sécurité de cette passe) ; archivage = effet immédiat | `team-live.json` | MAÎTRISÉ |
| 14 | Abus du ciblage des notifications | Capacité d'envoi exigée ; destinataires recalculés côté serveur (comptes actifs, écoles actives, comptes plateforme non suspendus) ; 50 000 destinataires max ; 20 campagnes/h ; une notification par destinataire ; idempotence | `notifications-live.json` | MAÎTRISÉ |
| 15 | Téléversement malveillant | Logo : PNG/JPEG vérifiés par signature, 1 Mo max ; clés d'objets construites côté serveur, préfixe `schools/<id>/` vérifié en base ; documents servis en `nosniff`, `no-store` | probes de clôture documents ; `test_object_keys_cannot_escape_their_prefix` | MAÎTRISÉ |
| 16 | Fuite de secrets / données personnelles | Secrets uniquement dans `.local/` (non versionné) ; scan de secrets avant chaque commit ; mots de passe jamais dans l'audit (vérifié) ; push sans corps de message ; adresse d'appareil push stockée en empreinte ; journaux sans paramètres, sans utilisateur, sans contenu | `team-live.json` « Mot de passe jamais écrit dans l'audit », `notifications-live.json` push, `secret_scan.py` | MAÎTRISÉ |
| 17 | Déni de service applicatif | Limitation de débit des opérations sensibles ; bornes de taille de requête (ApiGuard) ; exports d'audit bornés (92 j, 10 000 lignes) | `hardening-http-live.json` | PARTIEL : limitation en mémoire Redis, ouverte si Redis tombe (choix de disponibilité) ; protection réseau en amont à prévoir au déploiement |
| 18 | Clickjacking | `frame-ancestors 'none'` + `X-Frame-Options: DENY` (API et interface) | `hardening-http-live.json` | MAÎTRISÉ |
| 19 | Interception réseau | Cookie `Secure` en production ; HSTS émis par l'API sur HTTPS | — | BLOCKED_EXTERNAL (pas de HTTPS public en local) |
| 20 | Compromission d'un mot de passe plateforme | Changement de mot de passe et déconnexion de tous les appareils en libre-service ; réinitialisation par un Manager ; audit | `prereq-live.json` 1.4, `team-live.json` | PARTIEL : pas de second facteur → voir `MFA_PROPOSAL.md` (OWNER_DECISION) |
| 21 | Worker détourné | Rôle PostgreSQL dédié sans super-droits, sans contournement RLS, propriétaire d'aucune table, accès aux seules files ; refuse de démarrer avec une autre URL | `prereq-live.json` 1.3 (10 contrôles) | MAÎTRISÉ |
| 22 | Altération de l'audit | Déclencheur interdisant UPDATE/DELETE, même pour le propriétaire de la base ; conservé après restauration | `audit-live.json` (4 contrôles), `backup-restore-live.json` | MAÎTRISÉ |

## Choix documentés

* **Limiteur ouvert si Redis tombe** : toutes les opérations limitées sont authentifiées (sauf la première
  installation, déjà verrouillée), autorisées et auditées ; bloquer toute la plateforme pendant une panne de
  cache serait pire pour les écoles. La connexion garde Argon2 et les réponses identiques.
* **Styles inline autorisés par la CSP** : nécessaires à l'écran de démarrage (affiché avant tout chargement)
  et aux propriétés de style React. Aucun script inline n'est autorisé.
* **Pas de reconnexion périodique** : décision du propriétaire. Compensée par la rotation, la détection de
  rejeu, la révocation immédiate par appareil, la déconnexion globale et l'audit.
