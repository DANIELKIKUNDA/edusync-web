# Runbook d'incident — Plateforme EduSync (lot 2026-10)

Une page : quoi regarder, quoi faire, qui prévenir. Aucune commande ne se tape « au hasard » sur le VPS :
les déploiements et retours arrière passent **uniquement** par le pipeline officiel (CICD.md).

## 1. Être prévenu

| Signal | Qui le reçoit | Délai |
|---|---|---|
| E-mail « [EduSync] Incident : … hors service » | Managers Système actifs + adresses d'astreinte (État du service → Incidents et alertes) | après 5 min de panne |
| E-mail « [EduSync] Résolu : … » | les mêmes | au retour à la normale |
| Ticket GitHub « [Disponibilité] Staging injoignable » | propriétaire du dépôt (e-mail GitHub) | 2 sondes externes ratées (≈ 30 à 60 min) ; fermé automatiquement au retour |

Les alertes de l'application ne peuvent pas partir si la base de données est elle-même arrêtée : c'est la sonde
externe GitHub (`.github/workflows/uptime.yml`) qui couvre ce cas, ainsi que le serveur injoignable.

## 2. Diagnostiquer (5 minutes)

1. **EduSync → État du service.** Le bandeau dit ce qui ne va pas et pourquoi (alertes expliquées).
2. **Erreurs serveur** → groupe → référence (`correlation_id`). Sur le serveur : `docker compose logs api | grep <référence>`.
3. **Serveur d'application** → signaux clés : trafic, erreurs, latence, saturation du pool base.
4. **Workers** : dernier signal, file en attente, quarantaine. **Sauvegarde** : dernière exécution, restauration.
5. Site complètement injoignable : vérifier le ticket GitHub « Disponibilité » et l'onglet Actions (Uptime staging).

## 3. Agir

| Situation | Action |
|---|---|
| Une version vient d'être déployée et casse quelque chose | Retour arrière : Actions → *Deploy staging* (ou *Deploy production*) → **Run workflow** avec le SHA précédent. Mesuré le 19/10/2026 : 76 s pour revenir, 74 s pour repartir. Impossible si les migrations ont changé entre les deux : arrêt sûr, CICD.md §7 |
| Base de données injoignable | Le contrôleur de déploiement et les sondes le signalent ; restauration supervisée CICD.md §7, sauvegarde du jour (§5 ci-dessous) |
| Worker arrêté (signal absent) | Les files s'accumulent sans perte ; redéployer le même SHA par le pipeline relance tous les services |
| Fournisseur SMS / e-mail en échec | État du service → Fournisseurs : dernier code d'erreur ; Messagerie → configuration |
| Erreur 500 répétée sur une route | Groupe d'erreurs → référence → journal ; correctif → CI → staging → E2E → production |

## 4. Accès perdu (« bris de glace »), sans porte dérobée

1. **Téléphone perdu, codes de secours conservés** : se connecter avec un code de secours, puis reconfigurer.
2. **Codes perdus aussi** : un **autre Manager Système** réinitialise le second facteur (Équipe plateforme → fiche →
   Réinitialiser la validation en deux étapes). D'où la règle : toujours au moins deux Managers actifs.
3. **Plus aucun Manager disponible** : procédure opérateur `backend/scripts/reset_platform_mfa.py` avec les
   identifiants **propriétaire** de la base (jamais détenus par l'API) : ressaisie de l'adresse, motif, nom de
   l'opérateur, audit `PLATFORM_USER_MFA_RESET_BY_OPERATOR`. Ne donne aucun accès : mot de passe toujours exigé,
   nouveau facteur à enrôler. Testé par la sonde MFA (60/60, MFA_PLATFORM_OPTION_B_REPORT.md).

## 5. Restaurer une sauvegarde

Chaque nuit, le service de sauvegarde : `pg_dump` + copie des documents + empreintes SHA-256, **restauration d'essai
complète** dans une base isolée avec comptage des tables, copie hors site si configurée, rapport lu par État du service
(durée de restauration mesurée). Exercice local du 19/10/2026 (400 écoles, 11 190 événements d'audit) : sauvegarde
4,6 s, restauration 10,9 s, 8/8 contrôles d'intégrité, **18,5 s au total** (`tools/local/backup_restore.py`).
Restauration réelle : procédure supervisée CICD.md §7 (jamais d'improvisation sur le VPS).

## 6. Compte de test du parcours de bout en bout (à faire une fois par le propriétaire)

Le workflow *E2E staging* vérifie après chaque déploiement : connexion avec code, écrans, changement d'espace,
session, déconnexion. Il lui faut un compte **dédié, en lecture** :
1. Sur staging, Équipe plateforme → **Ajouter** → adresse du type `e2e-staging@<votre domaine>` → rôle **Support
   niveau 1** (jamais Manager) → mot de passe temporaire.
2. Se connecter une fois avec ce compte, changer le mot de passe, activer la validation en deux étapes et **noter la
   clé manuelle** affichée (groupes de 4 caractères).
3. GitHub → Settings → Environments → **staging** → ajouter 3 secrets : `E2E_PLATFORM_EMAIL`,
   `E2E_PLATFORM_PASSWORD`, `E2E_PLATFORM_TOTP_SECRET` (la clé manuelle, sans espaces).
4. Actions → *E2E staging* → **Run workflow** : tout doit être PASS.

## 7. Après l'incident

Noter dans le ticket : début, fin, cause, correctif, ce qui aurait permis de le voir plus tôt. Les incidents
« Hors service » sont conservés automatiquement (État du service → Incidents et alertes).
