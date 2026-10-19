# Niveau plateforme — liste de contrôle « terminé » (lot 2026-10)

Chaque ligne a une **preuve**. « À FAIRE (propriétaire) » = action qui ne peut pas être faite par le code.

| # | Exigence | Statut | Preuve |
|---|---|---|---|
| 1 | Surveillance extérieure au serveur | FAIT | `.github/workflows/uptime.yml` : toutes les 30 min (minutes GitHub facturées sur dépôt privé), accueil + API + base ; ticket GitHub après 2 échecs, fermé au retour |
| 2 | Alertes qui préviennent quelqu'un | FAIT | `alerts.py` : e-mail après 5 min « Hors service » + e-mail de résolution, Managers Système + adresses d'astreinte ; `tools/local/alerts_probe.py` 21/21 PASS (un seul envoi, verrou multi-processus, remise réelle par le worker, confirmation par code pour ajouter une adresse) |
| 2b | Votre adresse d'astreinte | À FAIRE (propriétaire) | État du service → Incidents et alertes → « Ajouter une adresse d'astreinte » → « Envoyer un e-mail de test » (2 minutes, confirmation par code) |
| 3 | Restauration de sauvegarde prouvée | FAIT | restauration d'essai complète **chaque nuit** sur le serveur (deploy/backup/backup.sh), durée mesurée affichée ; exercice local 19/10/2026 : 18,5 s, 8/8 contrôles |
| 4 | Tests de bout en bout sur staging dans la CD | FAIT (compte à créer) | `.github/workflows/e2e-staging.yml` après chaque déploiement ; `tools/ci/e2e_staging.py` 19/19 PASS en local ; compte de test : RUNBOOK_INCIDENT.md §6 |
| 5 | Procédure de secours (accès perdu) | FAIT | codes de secours, réinitialisation par un autre Manager, procédure opérateur sans porte dérobée — testés (mfa_probe 60/60) ; RUNBOOK_INCIDENT.md §4 |
| 6 | Mise en production avec retour arrière | FAIT | `deploy-production.yml` manuel, SHA + confirmation, contrôles CI/staging/E2E ; retour arrière **exécuté** sur staging le 19/10/2026 (76 s aller, 74 s retour) ; PRODUCTION.md |
| 6b | Relecteur obligatoire sur l'environnement production | À FAIRE (propriétaire) | GitHub → Settings → Environments → production → Required reviewers (PRODUCTION.md §2) |
| 7 | Test sur vrai Android d'entrée de gamme en 3G | À FAIRE (propriétaire) | seule l'émulation 375 px a été testée |
| 8 | Test de charge au volume visé | FAIT, avec réserve | voir « Charge » ci-dessous |
| 9 | Scan de sécurité automatisé | FAIT | `.github/workflows/security-scan.yml` (OWASP ZAP passif, chaque semaine) |
| 9b | Audit de sécurité externe (pentest) | À DÉCIDER | BUSINESS_DECISION_REQUIRED : prestataire, budget, date, avant l'ouverture au public |
| 10 | Conservation et purge | FAIT, désactivé | `retention_purge.py` (comptage par défaut) ; durées à valider : RETENTION.md |
| 11 | Runbook d'incident | FAIT | docs/architecture/RUNBOOK_INCIDENT.md |

## Charge (tools/local/load_test.py, 19/10/2026, PC portable Ryzen 5, tout sur la même machine)

Objectif écrit avant mesure : 1 000 écoles, 200 utilisateurs simultanés, p95 < 1 s, 0 erreur 5xx.

| Configuration | Profil | Débit | p95 | 5xx |
|---|---|---|---|---|
| 1 processus API | 200 utilisateurs réalistes (un écran toutes les 3–10 s) | 26 req/s | 523 ms | 0 — **objectif atteint** |
| 4 processus API | 400 utilisateurs réalistes | 53 req/s | 138 ms | 0 — **objectif atteint, 2× les utilisateurs** |
| 4 processus API | 200 utilisateurs en stress (un clic toutes les 0,2–1 s) | 75 req/s | 4,7 s côté client, **≤ 250 ms côté serveur** | 0 |

Constats : une requête seule prend 10 à 35 ms ; un processus Python plafonne vers 33 req/s, d'où
`WEB_CONCURRENCY=2` par défaut dans l'image (à porter au nombre de cœurs du serveur de production). En stress, les
secondes d'attente se forment dans le générateur de charge, qui partage le processeur avec le serveur (les signaux
mesurés côté serveur restent sous 250 ms). **Réserve** : un test de stress probant demande une machine de charge
séparée et un serveur de la taille de la production, jamais le staging partagé.
