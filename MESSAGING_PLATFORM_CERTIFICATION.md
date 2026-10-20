# Messagerie plateforme — certification (lot 2026-10)

Niveaux : **A** code / statique · **B** automatisé · **C** environnement réel · **D** validation humaine fonctionnelle /
UX · **E** production / externe. Aucun niveau n'est déclaré sans la preuve correspondante.

## 1. Architecture (inchangée dans ses principes, complétée)

```
Cas d'usage (transaction) ─▶ message + destinataires + événement outbox ─▶ worker communications
   └ invitation, récupération, alerte, communiqué      └ NotificationPolicy ─▶ livraisons ─▶ port fournisseur
                                                          (EmailProviderPort = SMTP Brevo, PushProviderPort = FCM HTTP v1,
                                                           SmsProviderPort = Orange, non branché en réel)
worker ─▶ contrôle réel des fournisseurs toutes les 5 min (sans envoi) ─▶ Redis edusync:messaging:health ─▶ cockpit
```

* Aucun module métier n'appelle Brevo ou Firebase : uniquement l'outbox (test existant `test_no_business_module_imports_a_provider`).
* `DELIVERED` uniquement sur accusé fournisseur ; `SENT` = acceptation avec preuve (identifiant), jamais « distribué ».
* La plateforme lit les **métadonnées** de toutes les livraisons, jamais le contenu ni les destinataires des messages
  d'école (sécurité au niveau des lignes : `communication_messages` d'école invisibles au rôle plateforme).

## 2. Ce qui a été ajouté

| Élément | Fichiers |
|---|---|
| Contrôle réel des fournisseurs par le worker (SMTP : connexion + STARTTLS + AUTH puis QUIT ; FCM : jeton OAuth2 du compte de service ; Orange : jeton OAuth2), instantané sans secret | `shared/messaging/health.py`, `email_smtp.py`, `push_fcm.py`, `sms_orange.py`, `fakes.py`, `communications/worker.py` |
| États fournisseur NON_CONFIGURÉ / CONFIGURÉ / OPÉRATIONNEL / DÉGRADÉ / INDISPONIBLE, état courant (15 min) séparé de l'historique | `communications/api/platform_router.py` (`channel_state`) |
| Explorateur de la file (filtres serveur canal / état / origine / événement / période / identifiant / adresse exacte, pagination par curseur, destinataire masqué) et diagnostic d'un envoi (tentatives première / dernière / prochaine, codes, message, outbox, corrélation, référence fournisseur, impact) | idem + migration `0084` |
| Relance manuelle e-mail / push : capacité dédiée `platform.messaging.retry`, motif, confirmation par code, idempotence, audit, jamais un SMS (portefeuille de l'école) — doublé par la sécurité au niveau des lignes | idem |
| Portefeuilles SMS : pagination et recherche serveur, totaux, solde avant / après, recharge avec référence + date + montant + devise obligatoires, ajustement séparé `platform.sms_wallet.adjust` (justification ≥ 10 caractères), jamais négatif | idem |
| Cockpit (cartes centrées entièrement cliquables, page canal, explorateur, détail, portefeuille), mobile en cartes + filtres en feuille + « Afficher plus », mode sombre, hors connexion | `frontend/src/platform/messaging.tsx`, `messaging_api.ts`, `messaging.css` |
| Notifications push sur l'appareil du compte plateforme (nécessaire au push de test) | `messaging.tsx` (`ThisDevice`, client `push_client.ts` existant) |
| Signature discrète « From Volcano Tech » (HTML + texte) sur tous les e-mails | `communications/domain/email_templates.py` |
| Rétention technique (désactivée par défaut) : envois / messages plateforme et compte terminés 180 j, appareils push révoqués 90 j ; jamais l'historique d'une école ni l'audit | `backend/scripts/retention_purge.py`, `docs/architecture/RETENTION.md` |

Migration : `0084_platform_messaging_cockpit.sql` (colonne `first_attempt_at`, 6 index de recherche, 2 capacités, droits
de relance limités aux lignes e-mail / push). Registre : 282 capacités.

## 3. Configuration attendue (noms seulement, jamais les valeurs)

| Variable | Où | Rôle |
|---|---|---|
| `EDUSYNC_EMAIL_PROVIDER=smtp` | API + worker | canal e-mail réel |
| `EDUSYNC_SMTP_HOST=smtp-relay.brevo.com`, `EDUSYNC_SMTP_PORT=587`, `EDUSYNC_SMTP_SECURITY=starttls` | worker (hôte aussi API) | relais Brevo |
| `EDUSYNC_SMTP_USERNAME`, `EDUSYNC_SMTP_PASSWORD` (secret) | worker uniquement | identifiants SMTP Brevo |
| `EDUSYNC_SMTP_FROM_EMAIL`, `EDUSYNC_SMTP_FROM_NAME` | worker + API | expéditeur vérifié chez Brevo |
| `EDUSYNC_PUSH_PROVIDER=fcm` | API + worker | canal push réel |
| `EDUSYNC_FCM_SERVICE_ACCOUNT_JSON` (secret, recommandé : le JSON **encodé en base64**, sur une seule ligne) **ou** `EDUSYNC_FCM_SERVICE_ACCOUNT_FILE` (fichier qui doit être visible **dans le conteneur**) | worker uniquement | compte de service Firebase |
| `EDUSYNC_FCM_WEB_CONFIG_JSON`, `EDUSYNC_FCM_VAPID_PUBLIC_KEY` (publics) | API | jeton push côté navigateur |
| `EDUSYNC_PUBLIC_APP_URL` | worker | liens d'invitation / récupération |

Sur staging, ces valeurs vivent dans `/etc/edusync-deploy/staging.env` (installation administrative, jamais dans Git).
**Attention** : le compose installé ne monte aucun fichier secret dans le worker ; avec `…_FILE`, le fichier doit se
trouver dans un montage autorisé, sinon le cockpit affiche « Compte de service : fichier monté — illisible ». La
variable `…_JSON` évite ce point.

## 4. Preuves

| Niveau | Preuve |
|---|---|
| A | revue de code, `tsc`, build, scan de secrets (0), registre 282 capacités |
| B | tests backend : 896 passés (dont `test_platform_messaging_cockpit.py`, 8 contrats : machine d'états, erreur ancienne non dégradante, masquage, contrôle SMTP sans secret, worker non bloqué par un contrôle en échec, RBAC, gabarits HTML + texte + signature) ; sondes locales sur la vraie pile : `messaging_cockpit_probe` (toutes PASS : états, contrôle réel à la demande, recherche, pagination, détail, relance avec capacité / motif / code / idempotence / aucun double envoi / SMS refusé, portefeuilles), `account_flows_probe` (toutes PASS, deux fois : invitation reçue via outbox + worker, aucun mot de passe envoyé, jeton haché, renvoi qui invalide l'ancien lien, activation, usage unique, mot de passe oublié sans énumération, sessions fermées, alerte de sécurité) |
| C (partiel) | **contrôle SMTP réel contre `smtp-relay.brevo.com:587`** depuis le poste de développement : connexion + STARTTLS réussis (≈ 8 s) ; identifiants volontairement faux → `SMTP_AUTHENTICATION` ; serveur injoignable → `SMTP_UNAVAILABLE`. FCM : contrôle non concluant depuis ce poste (`oauth2.googleapis.com` injoignable d'ici) — à constater depuis staging |
| C (à faire sur staging) | voir §5 : contrôle des fournisseurs, e-mail de test reçu, push reçu sur l'appareil, invitation et récupération réelles |
| D | non déclaré : validation humaine à faire |
| E | non applicable (pas de production) |

## 5. Certification C sur staging — à faire par le propriétaire (15 minutes, aucune valeur secrète à manipuler)

1. Staging → Plateforme → **Messagerie** → **Contrôler les fournisseurs** : E-mail et Push doivent passer à
   « Opérationnel » (contrôle réel réussi). Sinon la page du canal affiche le code (`SMTP_AUTHENTICATION`,
   `PUSH_CREDENTIALS`, « fichier illisible »…).
2. Page **E-mail** → **M'envoyer un e-mail de test** → réception dans Gmail (vérifier l'expéditeur et la signature).
3. Sur votre téléphone Android (Chrome, PWA installée) : Messagerie → **Push** → **Activer sur cet appareil** →
   **Envoyer un push à mes appareils** → notification reçue, PWA fermée puis ouverte ; toucher la notification ouvre EduSync.
4. Équipe plateforme → ajouter un collaborateur **par invitation** vers une seconde adresse à vous → e-mail reçu →
   activation → connexion. Puis « Mot de passe oublié » d'un compte école de test → e-mail reçu → réinitialisation.
5. Messagerie → **Rechercher dans tous les envois** : les envois ci-dessus apparaissent en « Envoyé » avec une
   référence fournisseur ; le Journal d'audit contient les tests et l'invitation.
6. Me transmettre (sans secret) : le SHA déployé (pied de page / Actions), les captures des étapes 1 à 5.

## 6. Diagnostic sur le serveur (lecture seule, aucune valeur affichée)

La page Messagerie → canal → « Diagnostic de configuration » liste, pour l'API et pour le worker, chaque variable
attendue avec son résultat (présente / absente / mauvais format), jamais sa valeur. La même vérification se lance dans
les conteneurs de staging, sans rien modifier :

```bash
cd /etc/edusync-deploy/compose
sudo docker compose -p edusync-staging --env-file /etc/edusync-deploy/staging.env -f docker-compose.yml -f compose.staging.yml   exec -T communications-worker python -m edusync.shared.messaging.diagnose worker
sudo docker compose -p edusync-staging --env-file /etc/edusync-deploy/staging.env -f docker-compose.yml -f compose.staging.yml   exec -T backend python -m edusync.shared.messaging.diagnose api
```

Causes « Non configuré » trouvées dans le code et l'installation (19-21/10/2026) :

| Cause | Symptôme dans le diagnostic | Correction (staging.env, puis redéploiement par le pipeline) |
|---|---|---|
| `staging.env` créé depuis `.env.example` : fournisseurs restés `disabled` | `EDUSYNC_EMAIL_PROVIDER vaut « disabled »`, `EDUSYNC_PUSH_PROVIDER vaut « disabled »` | `EDUSYNC_EMAIL_PROVIDER=smtp`, `EDUSYNC_PUSH_PROVIDER=fcm` |
| clé Brevo sous un autre nom | `EDUSYNC_SMTP_PASSWORD : absent dans ce processus` | la renommer `EDUSYNC_SMTP_PASSWORD` (et `EDUSYNC_SMTP_USERNAME` = login SMTP Brevo) |
| URL publique non HTTPS : démarrage refusé si l'e-mail est actif | `EDUSYNC_PUBLIC_APP_URL doit commencer par https://` | `EDUSYNC_PUBLIC_APP_URL=https://staging.myeducsync.com` |
| compte de service en fichier sur l'hôte, jamais monté dans le worker | `PUSH_CREDENTIAL_FILE_MISSING : fichier absent dans le conteneur (non monté)` | mettre le JSON **en base64** dans `EDUSYNC_FCM_SERVICE_ACCOUNT_JSON` : `base64 -w0 fichier.json` (aucun montage nécessaire) |
| configuration Web Firebase absente côté API | `EDUSYNC_FCM_WEB_CONFIG_JSON absente ou incomplète` | JSON public de l'application Web Firebase, sur une seule ligne |
| projets Firebase différents | « Projet Firebase différent entre l'API et le worker » | même projet pour la configuration Web et le compte de service |

Aucun redémarrage manuel : après modification de `staging.env`, relancer *Deploy staging* (Actions → Run workflow,
SHA courant) ; le contrôleur recrée l'API et le worker avec la nouvelle configuration.
