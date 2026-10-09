# EduSync Web — rapport de certification Niveau 1 (plateforme / Atelier Pro)

Pas de PASS global. Preuves exécutées sur l'instance locale isolée ; SHA exact et résultats de la dernière
exécution complète : `CERTIFICATION_EVIDENCE_MANIFEST.md`. Niveau 2 non commencé.

## Synthèse par exigence

| Exigence | État | Preuve (sondes réelles) |
|---|---|---|
| Inventaire des rôles PLATFORM | PASS | `PLATFORM_ROLES_INVENTORY.md` |
| Gouvernance PLATFORM_CUSTOM (créer, brouillon, activer, archiver, cloner, attribuer, retirer, cumuler, permissions effectives, audit) | PASS | `team-live.json` 58/58 |
| Aucune capacité SCHOOL implicite, aucun contournement RLS | PASS (API + déclencheur SQL + RLS) | idem ; RLS « le rôle tenant ne voit aucun rôle plateforme » |
| Anti-escalade (A) | PASS | idem : auto-promotion, délégation de capacité non détenue, capacité réservée, compte plus puissant, dernier Manager (concurrence) |
| Rôles industriels proposés | OWNER_DECISION (non activés) | `PLATFORM_ROLES_PROPOSAL.md` |
| Utilisateurs plateforme (création, statut, rôles, permissions, profil, sécurité, sessions, mot de passe, appareils, audit, dernière activité) | PASS | `team-live.json`, captures `n1-team-1280.png` |
| Tableau de bord réel (aucune fausse métrique) | PASS | chiffres issus des tables (`/platform/dashboard`) |
| Menu selon les permissions | PASS (calculé serveur, chargements conditionnés) | `team-live.json` ; `n1-custom-role-1280.png` |
| Création d'école complète | PASS (défaut 500 en concurrence corrigé) | `school-lifecycle-live.json` 31/31 ; `SCHOOL_PROVISIONING_REPORT.md` |
| Premier ADMIN_SYSTEME_ECOLE | PASS ; réinitialisation de mot de passe : OWNER_DECISION | `SCHOOL_PROVISIONING_REPORT.md`, `SCHOOL_ONBOARDING_GAP_REPORT.md` |
| Activation / suspension : effets réels | PASS (4 trous comblés : sessions, renouvellement, documents signés, SMS) | `school-lifecycle-live.json` |
| Santé mesurée, libellés humains | PASS ; sauvegarde rapportée | `health-live.json` 12/12, `backup-restore-live.json` |
| Audit (filtres, recherche, export, détail avant/après, corrélation, ajout seul) | PASS | `audit-live.json` 25/25 |
| Notifications in-app (ciblage, lu/non lu, historique, expiration, liens sûrs, sans doublon) | PASS | `notifications-live.json` 44/44 ; `PLATFORM_NOTIFICATIONS_REPORT.md` |
| Centre de notifications | PASS | idem ; `n1-bell-1280.png` |
| Push | PASS (abstraction + simulateur) ; réel BLOCKED_EXTERNAL | idem |
| SMS ≠ in-app | PASS | aucune campagne n'envoie de SMS |
| Sécurité multi-tenant rejouée | PASS | BOLA notifications, sessions, RLS rôles et statuts, compte école refusé sur l'Atelier Pro |
| UX desktop / tablette / mobile | PASS VISUEL sur les écrans capturés | `captures/n1-*-{375,640,768,1280,1440}.png` |
| Parcours N1 reproductible | voir ci-dessous | `n1_journey.mjs`, `n1-journey-live.json` |

## Défauts trouvés et corrigés pendant la passe (extraits)
1. **Sécurité** : `require_platform_actor` additionnait les capacités de rôles non actifs (brouillon/archivé).
2. **Sécurité** : suspension d'école sans effet sur les sessions ouvertes, le renouvellement, les liens signés,
   les SMS en attente.
3. **Disponibilité** : la garde de connexion bloquait toute une adresse IP après 7 échecs, donc une école
   entière derrière un NAT.
4. **Robustesse** : 500 au lieu de 409 lors de créations d'école concurrentes ; 500 au lieu de 503 en cas de
   panne de base ou de stockage ; requêtes bloquées sans délai de connexion.
5. **Exploitation** : lanceur tué par WSL, lent après redémarrage, planté par un WSL bloqué.
6. **Chaîne d'approvisionnement** : dépendances Python non figées ; PyJWT et source-map-js vulnérables.

## Parcours N1 (base de démonstration, UI uniquement)
Manager → connexion automatique Atelier Pro → tableau de bord → équipe, rôles, éditeur de rôle (capacité
réservée non cochable) → santé → audit (détail avant/après) → notifications (cloche) → nouvelle école
(validations) → second compte à rôle personnalisé : menu réduit, pas de création d'école → déconnexion,
reconnexion, rechargement (session persistante) → largeurs 375/640/768/1440.
Les étapes « écoles A, B, C + administrateurs, isolation, suspension/réactivation de B, notifications ciblées,
lecture, audit » sont prouvées par les sondes API correspondantes (mêmes routes que l'interface).

## Limites déclarées
* Machine de recette très chargée (≈ 600 Mo libres) : durées indicatives.
* Contrastes vérifiés automatiquement sur la page de connexion ; pas d'audit outillé (axe/Lighthouse) de tous les
  écrans.
* Pas de HTTPS public : cookie Secure, HSTS, installation PWA, push réel non testables (BLOCKED_EXTERNAL).
