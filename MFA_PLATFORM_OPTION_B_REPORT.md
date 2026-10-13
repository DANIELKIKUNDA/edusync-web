# EduSync Web — second facteur des comptes plateforme (option B) et verrou Git N0/N1

**Date** : 13 octobre 2026 · **Ingénieur** : Claude (Opus 5.5), mandat de Daniel KIKUNDA
**Périmètre** : comptes plateforme (Atelier Pro) uniquement. Aucun changement pour les comptes école.
**Hors périmètre** : N2, staging, production.

---

## 1. Verrou Git de la certification N0/N1

Commandes exécutées : `git status`, `git log --oneline --decorate -10`,
`git diff --name-status bbe90e2..4c3df8c`, puis `git diff` complet du manifeste et des preuves.

| Question | Réponse |
|---|---|
| Fichiers différents entre `bbe90e2` et `4c3df8c` | **10**, tous des preuves : `CERTIFICATION_EVIDENCE_MANIFEST.md` et 9 fichiers `certification/n0-n1-20261007/*.json` (`certify-run`, `audit-live`, `health-live`, `notifications-live`, `prereq-live`, `realtime-live`, `resilience-live`, `team-live`, `sbom.cdx`) |
| Code applicatif, migrations, dépendances, configuration, sécurité, RBAC, sessions, scripts | **Aucun changement** (81 lignes +, 81 lignes −, toutes des valeurs de preuve) |
| Parent de `4c3df8c` | `bbe90e2` (historique linéaire) |
| **SHA N0/N1 certifié localement (avant MFA)** | **`bbe90e2da8580fddbbfed8d6c0c220be3785e907`** |
| Étiquette | `n0-n1-local-certified-2026-10-10` → `bbe90e2`, déjà présente sur le dépôt distant |

**Ambiguïté levée** : le manifeste de `4c3df8c` indiquait « arbre de travail modifié au moment de l'exécution ».
Le script (`tools/certification/n0_n1_certify.py`) contrôlait `git status` **après** les étapes, alors que les
sondes venaient d'écrire leurs fichiers de preuve : la mention était inévitable et ne prouvait rien. Le seul
changement commité ensuite étant ces preuves, le code certifié est bien celui de `bbe90e2`.
**Correction** : le script contrôle désormais l'arbre **avant** toute étape, enregistre la liste des fichiers
modifiés dans `certify-run.json`, et un arbre non propre fait **échouer** la certification.

## 2. `MFA_PROPOSAL.md` — les options (le document en compte quatre, pas trois)

| Option | Définition exacte (document) | UX | Sécurité | Récupération | Exploitation |
|---|---|---|---|---|---|
| **A** | Aucun MFA pour l'instant | Aucune friction | Risque 20 du modèle de menaces inchangé : un mot de passe volé suffit pour créer, suspendre des écoles, réinitialiser un administrateur, notifier toutes les écoles | Sans objet | Rien à faire |
| **B** | MFA **obligatoire pour les comptes plateforme** (Atelier Pro seulement) | Un code à chaque nouvelle connexion de l'équipe plateforme ; appareils approuvés restent connectés | Protège les comptes les plus puissants | Codes de secours, réinitialisation par un autre Manager | Effort modéré ; écoles non impactées |
| **C** | B + MFA **facultatif** pour les `ADMIN_SYSTEME_ECOLE` volontaires | Choix laissé aux grandes écoles | Mieux pour les écoles qui l'activent | Support accru (perte de téléphone) côté écoles | Charge de support |
| **D** | MFA **obligatoire pour tous** | Forte friction pour caissiers et personnel | Maximale | Téléphones partagés ou absents | Déconseillé sans étude terrain |

**Pourquoi B au minimum** (recommandation du document : « Recommandé comme minimum avant production ») : les comptes
plateforme concentrent les pouvoirs transverses (toutes les écoles), le coût est limité à une petite équipe et les
écoles ne subissent aucune friction. **Aucune contradiction** n'a été trouvée dans l'architecture : l'option B est
adoptée telle que décrite (TOTP RFC 6238, jeton intermédiaire, codes de secours Argon2, réinitialisation par un
autre Manager, limitation 5 essais → 15 min).

## 3. Ce qui a été implémenté

### Parcours
1. Mot de passe d'un compte plateforme → **aucune session, aucun cookie, aucun jeton d'accès** : le serveur
   renvoie un **jeton d'étape** opaque (haché en base, 5 min, usage unique, 5 essais), accepté **uniquement**
   par `/auth/mfa/*`.
2. Compte sans facteur → **enrôlement forcé** avant tout accès : nouveau secret, QR code généré localement
   (aucun service externe), clé manuelle, **premier code exigé** avant activation, puis **10 codes de secours**
   affichés une seule fois.
3. Compte enrôlé → code à 6 chiffres **ou** code de secours → session d'appareil marquée « second facteur validé ».
4. Appareil approuvé : la session persistante (décision N0 « pas de reconnexion périodique ») se renouvelle sans
   nouveau code ; toute nouvelle connexion redemande le code.

### Garanties
| Exigence du mandat | Mise en œuvre |
|---|---|
| Secret protégé côté serveur | AES-256-GCM, nonce aléatoire, **lié au compte** (donnée associée = identifiant), clé `EDUSYNC_MFA_ENCRYPTION_KEY` distincte du JWT, **obligatoire hors développement** |
| Tables hors de portée des écoles | `user_mfa_factors`, `user_mfa_recovery_codes`, `mfa_challenges` : RLS forcé, accès **rôle plateforme seul**, **aucun droit pour le rôle école**, aucune suppression (révocation tracée) |
| Pas de rejeu, tolérance d'horloge | Fenêtre ±1 pas de 30 s ; un code n'est jamais accepté deux fois (`last_used_step`, compare-and-set contre deux requêtes simultanées) |
| Codes de secours | 10 codes, alphabet sans ambiguïté, hachés Argon2, usage unique, tous invalidés à la régénération (qui exige un code TOTP frais) |
| Contournement par appel direct | Tout jeton plateforme exige une session au second facteur validé (`require_platform_actor`) ; `/auth/refresh` refuse une session sans MFA ; les sessions antérieures sont donc inutilisables |
| Pas d'auto-suppression | **Aucune route** de désactivation ; `self_disable_allowed: false` ; la réinitialisation de son propre compte via l'équipe est refusée |
| Réinitialisation autorisée et auditée | Par un **autre** Manager (capacité réservée `platform.collaborators.manage`, anti-escalade, motif, clé d'idempotence), sessions plateforme coupées, `PLATFORM_USER_MFA_RESET` |
| Dernier recours sans porte dérobée | `backend/scripts/reset_platform_mfa.py` : identifiants **propriétaire** de la base (jamais détenus par l'API), ressaisie de l'adresse, motif et nom de l'opérateur, audit `PLATFORM_USER_MFA_RESET_BY_OPERATOR` ; ne donne aucun accès (mot de passe requis, nouveau facteur à enrôler). Pas de code maître |
| Limitation de débit | 5 essais par étape ; verrou **par compte** 5 échecs → 15 min (Redis) ; chaque échec audité `REJECTED` |
| Pas d'énumération | L'étape MFA n'est atteinte qu'après un mot de passe valide ; l'échec du mot de passe reste générique |
| Mot de passe, révocation, désactivation | Changement de mot de passe : sessions coupées, facteur conservé ; compte désactivé ou suspendu entre les deux étapes : étape refusée |
| Journal d'audit | `MFA_ENROLLMENT_STARTED`, `MFA_ENROLLED`, `MFA_VERIFIED`, `MFA_RECOVERY_CODE_USED`, `MFA_RECOVERY_CODES_REGENERATED`, `MFA_FAILED`, `MFA_LOCKED`, `PLATFORM_USER_MFA_RESET`, `PLATFORM_USER_MFA_RESET_BY_OPERATOR` — jamais de code ni de secret |
| Production | Démarrage refusé si la politique est désactivée ou la clé absente/identique au JWT |

### Interface
* Écran **Code de vérification** : saisie numérique (`inputmode=numeric`, `autocomplete=one-time-code`), collage
  accepté, envoi automatique au 6ᵉ chiffre, bascule vers code de secours, messages non techniques (heure du
  téléphone), retour à la connexion si l'étape expire.
* **Assistant d'activation** en 3 étapes avec progression : QR code (balise `<img>`, rien d'exécutable), lien direct
  vers l'application sur le même téléphone, clé manuelle groupée par 4, confirmation, codes de secours (copier,
  télécharger), accès bloqué tant que la conservation n'est pas confirmée.
* **Sécurité et appareils** → onglet « Validation en 2 étapes » : état, codes restants, régénération (code exigé),
  aucune désactivation.
* **Équipe plateforme** : statut par membre (« Sécurité à configurer »), fiche avec réinitialisation motivée.

## 4. Défauts trouvés et corrigés pendant la passe

| # | Défaut | Correction |
|---|---|---|
| M1 | Certification : `git status` contrôlé après les étapes (mention « arbre modifié » sans valeur probante) | Contrôle avant les étapes, liste enregistrée, arbre non propre = échec |
| M2 | Un prototype MFA local, jamais commité, avait laissé dans la base de démonstration des tables de même nom (schéma différent) et une migration `0056_platform_mfa` enregistrée : `CREATE TABLE IF NOT EXISTS` aurait silencieusement conservé l'ancien schéma | Migration renommée `0056_platform_mfa_totp` ; tables du prototype renommées `legacy_prototype_*` (traçabilité), sans aucun droit applicatif ; les 7 sessions qu'il marquait « vérifiées » perdent ce statut |
| M3 | Droit `DELETE` hérité des privilèges par défaut sur les tables MFA | Retiré (migration + provisionneur) |
| M4 | QR code invisible dans le navigateur (SVG sans espace de noms utilisé comme image) — vu sur capture | SVG autonome avec `xmlns` et `viewBox`, test unitaire ajouté |
| M5 | Verrou MFA par adresse IP : les erreurs d'un compte bloquaient toute l'équipe derrière la même adresse (constaté : le Manager bloqué en recette) | Second facteur limité par compte uniquement ; l'étape mot de passe garde son compteur par adresse |
| M6 | Liste de l'équipe : étiquette MFA chevauchant la colonne « Dernière activité » — vu sur capture | Étiquette courte « Sécurité à configurer » placée avec les rôles |
| M7 | Sonde : test « hors fenêtre » sensible à la frontière d'un pas de 30 s | Envoi au milieu d'un pas |

## 5. Tests

| Niveau | Contenu | Résultat |
|---|---|---|
| Unitaires et contrats (`backend/tests/test_platform_mfa_option_b.py`) | Vecteurs RFC 6238, rejeu, dérive ±1/±2, formats invalides, chiffrement lié au compte, clé obligatoire en production, codes de secours, URI et QR, absence de route de désactivation, session MFA exigée, échecs commités avant refus, gouvernance de la réinitialisation, procédure opérateur, verrou par compte, tables réservées, audit sans secret, écrans présents | **32/32 PASS** |
| Suite backend complète | 538 tests N0/N1 + MFA ; 3 contrats existants mis à jour (justification ci-dessous) | **570/570 PASS** |
| Sonde réelle `mfa_probe.py` (API + PostgreSQL + Redis) | Activation, connexion, mauvais/bon code, rejeu, hors fenêtre, codes de secours, régénération, absence de désactivation, jeton plateforme sans MFA refusé, `/refresh` sans MFA refusé, appareil approuvé, isolation tenant, 5 essais, verrou par compte, réinitialisation par un Manager (autorisée / interdite à soi-même / interdite sans capacité), procédure opérateur, changement de mot de passe, désactivation entre deux étapes, compte école non bloqué, aucune fuite (audit, journaux), Manager système | **60/60 PASS** |
| Sondes N0/N1 (8) | Rejouées en passant réellement le second facteur (aucune porte dérobée) | voir manifeste |
| Parcours UI (`n1_journey.mjs`) | Connexion Manager avec code, rôle personnalisé, assistant d'activation à 390 px, codes de secours, code faux, code de secours, 320 px, onglet Sécurité, fiche Équipe | **51/51 PASS** |

**Contrats existants mis à jour** (la propriété vérifiée est conservée ou renforcée) :
`test_d6_access_tokens_are_bound_to_a_live_device_session` (le résolveur plateforme exige en plus le second
facteur), `test_every_non_public_api_route_has_server_side_actor_dependency` (les trois routes `/auth/mfa/*` sont
publiques par construction, authentifiées par le jeton d'étape), et une chaîne exacte de `login.tsx` conservée.

## 6. OWNER_DECISION encore ouvertes

1. **Redemande du code pour les actions sensibles** (« step-up » de la proposition : suspendre une école,
   réinitialiser un administrateur, ajouter un Manager) — non implémenté, à décider.
2. **Comptes plateforme ouvrant un espace école** : l'option B protège la console Atelier Pro ; un compte qui
   possède aussi un rattachement école se connecte à cet espace école sans second facteur. À confirmer.
3. **Réinitialisation par un seul Manager** : faut-il exiger deux Managers, un délai, ou coupler avec une
   réinitialisation du mot de passe ?
4. **Nombre de Managers** : recommandation d'exploitation — au moins deux Managers actifs, pour que la voie normale
   de récupération existe toujours et que la procédure opérateur reste exceptionnelle.
5. **Option C** (MFA facultatif pour les administrateurs d'école) : non activée, conformément au mandat.

## 7. Commits et certification

| Élément | Valeur |
|---|---|
| SHA N0/N1 certifié avant MFA | `bbe90e2` (étiquette `n0-n1-local-certified-2026-10-10`) |
| Commits MFA | `7463b9c` (implémentation), `9c5d5fa` (procédure opérateur, verrou par compte) |
| **SHA final certifié après MFA** | **`9c5d5fae1bde0000c11c842c0ed712446b73daa8`** |
| Étiquette proposée | `n0-n1-mfa-local-certified-2026-10-13` → `9c5d5fa` |
| Preuves | `CERTIFICATION_EVIDENCE_MANIFEST.md`, `certification/n0-n1-20261007/` (dont `mfa-live.json`, captures `mfa-*.png`) |

L'étiquette `n0-n1-local-certified-2026-10-10` ne couvre **pas** le code MFA : seul `9c5d5fa`, retesté, reçoit la
nouvelle étiquette.

## 8. Exécutions de la certification N0/N1 sur `9c5d5fa` (traçabilité complète)

| Exécution | Résultat | Cause des échecs | Action |
|---|---|---|---|
| 0 (sur `7463b9c`) | interrompue volontairement | — | ajout de la procédure opérateur (commit `9c5d5fa`) |
| 1 | 17/20 | `health_probe` et `notifications_probe` : Redis injoignable — l'adresse WSL du fichier privé `certification.env` était celle de l'autre machine ; `npm audit` : coupure réseau vers le registre | le lanceur privé des sondes (`.local/closure/run.py`, non versionné) utilise désormais l'adresse WSL courante, comme le lanceur EduSync ; `npm audit` rejoué : 0 vulnérabilité |
| 2 | 19/20 | `notifications_probe` 43/44 : un abonnement push de test, créé par l'exécution 0 interrompue, restait actif (l'application envoyait donc correctement à un appareil encore abonné) | abonnement de test révoqué en base locale (motif `TEST_RUN_INTERRUPTED_CLEANUP`) |
| **3** | **20/20 PASS** | — | arbre propre au démarrage ; parcours UI 51/51 sur le même commit |

| Étape (exécution 3) | Résultat |
|---|---|
| Arbre Git propre au démarrage | PASS (`9c5d5fa`) |
| pytest | 570 passed |
| compileall · tsc · build | PASS · 0 erreur · PASS |
| Migrations sur base vierge | PASS (dont `0056_platform_mfa_totp`) |
| Sondes : prérequis 42/42 · équipe 58/58 · cycle de vie école 31/31 · santé 12/12 · audit 25/25 · notifications 44/44 · temps réel 8/8 · durcissement HTTP 17/17 · **MFA 60/60** · résilience 16/16 | PASS |
| Sauvegarde + restauration vérifiée | 8/8 |
| Chaîne d'approvisionnement · npm audit · secrets | 46 paquets Python (dont `cryptography`, `segno`) · 0 vulnérabilité · 0 fuite sur 81 secrets |

Les captures `mfa-enroll-key-390.png` et `mfa-enroll-codes-390.png` montrent la clé et les codes d'un compte de
test jetable de l'instance locale ; son second facteur a été révoqué après le parcours (procédure opérateur,
auditée) : ces valeurs ne permettent plus rien.

Aucune certification globale, staging ou production n'est prononcée : instance locale uniquement.

