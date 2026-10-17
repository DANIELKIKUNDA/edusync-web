# Certification — messagerie externe (e-mail, SMS, push)

Date : 2026-10-17. Commit certifié : **`2ad66ef`** (arbre propre au démarrage).
Certification complète N0 / N1 / N2 / N3 + messagerie externe : **47 / 47 étapes PASS**
(`CERTIFICATION_EVIDENCE_MANIFEST.md`, `certification/n0-n1-20261007/certify-run.json`).

## 1. Verdicts séparés

| Verdict | Résultat | Fondement |
|---|---|---|
| `EMAIL_LOCAL_READY` | **OUI** | pipeline outbox → worker → port e-mail ; invitation 48 h, récupération 30 min, alertes de sécurité ; rejeu et expiration refusés ; fournisseur simulé de développement (sonde locale 53/53, contrôle UI) |
| `EMAIL_REAL_PROVIDER_CERTIFIED` | **NON — EXTERNAL_REQUIRED** | aucun relais SMTP réel fourni ; `email_provider_probe` = EXTERNAL_REQUIRED |
| `SMS_LOCAL_READY` | **OUI** | portefeuille et grand livre, aperçu / confirmation, réservation → consommation / libération, nouvelles tentatives bornées, SMS désactivé sans impact métier, isolation A / B ; adaptateur Orange testé sur le contrat documenté (transport simulé) |
| `SMS_ORANGE_REAL_CERTIFIED` | **NON — EXTERNAL_REQUIRED** | identifiants Orange non fournis ; `sms_provider_probe` = EXTERNAL_REQUIRED ; API RDC marquée « deprecated » à confirmer avec Orange |
| `PUSH_LOCAL_READY` | **OUI** | appareils multiples, jeton chiffré, jeton invalide désactivé, jeton réattribué révoqué, révocation unitaire, envoi par l'outbox, service worker existant ; fournisseur simulé de développement |
| `PUSH_FCM_REAL_CERTIFIED` | **NON — EXTERNAL_REQUIRED** | projet Firebase non fourni ; `push_provider_probe` = EXTERNAL_REQUIRED ; essais sur appareils physiques (Android PWA, iOS à part) non faits |

Aucune simulation n'est confondue avec une certification fournisseur : les sondes réelles refusent les fournisseurs
simulés et n'enregistrent PASS que sur une réponse réelle (`REAL_ACCEPTED`), puis demandent une confirmation humaine
de la réception.

## 2. Preuves de la certification sur `2ad66ef`

| Étape | Résultat |
|---|---|
| Tests backend | 647 passed (dont 20 contrats de messagerie : ports, contrat Orange simulé, SMTP, FCM, politique, unités, nouvelles tentatives, simulations refusées, échappement, liens) |
| tsc, build | 0 erreur, build OK (SDK Firebase chargé à la demande) |
| Sondes N0 / N1 (10) | PASS (isolation 58/58, MFA 83/83, résilience 16/16, notifications 44/44 avec push par l'outbox, cycle de vie 33/33) |
| N2 (sonde, parcours UI 7 largeurs, 8 sondes de lot) | PASS |
| N3 lots A à H (sondes + contrôles UI) | PASS |
| `messaging_local_probe` | **53 / 53** |
| `messaging_ui_check` (390 px + 1280 px) | **PASS** |
| Fournisseurs réels | e-mail, SMS, push : **EXTERNAL_REQUIRED** (hors total) |
| Sauvegarde + restauration, licences, `npm audit` (0), scan de secrets (0 fuite) | PASS |

Quatre runs précédents ont été arrêtés et non comptés : sonde N1 encore écrite avec l'ancien statut `PENDING`
(corrigée), vulnérabilités gRPC du paquet `firebase` complet (remplacé par `@firebase/app` + `@firebase/messaging`),
blocage ponctuel du navigateur piloté, mise en veille moderne de la machine (maintien en éveil de l'écran ajouté).

## 3. Ce qui reste pour les certifications réelles

1. **E-mail** : choisir le relais SMTP, vérifier le domaine d'expédition (SPF, DKIM, DMARC), fournir les paramètres
   (EMAIL_TRANSACTIONAL_INTEGRATION.md §3), exécuter `email_provider_probe`, constater la réception.
2. **SMS Orange** : checklist SMS_ORANGE_INTEGRATION.md §4 (produit, identifiants, adresse et nom d'expéditeur, crédits,
   callback, contrat multi-école), exécuter `sms_provider_probe` vers votre numéro, constater la réception et l'accusé.
3. **Push FCM** : PUSH_FCM_INTEGRATION.md §4 (projet, configuration Web, clé VAPID, compte de service, domaine HTTPS),
   exécuter `push_provider_probe`, puis les essais sur Android Chrome / PWA installée et, séparément, sur iPhone.
4. **Pile Docker staging** : le dernier passage réel est celui de `aed2305` (28 / 28) ; il n'a pas pu être rejoué ici
   après l'ajout des variables de messagerie au compose (mémoire du poste insuffisante pour Docker Desktop) — à
   rejouer sur le serveur de staging.

Les secrets se saisissent dans `.local/` (local) ou dans le coffre de déploiement (Coolify), jamais dans le chat ni
dans Git.
