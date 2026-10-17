# EduSync — Architecture de la messagerie externe (e-mail, SMS, push)

Date : 2026-10-17. Mandat « FINAL EXTERNAL MESSAGING INDUSTRIALIZATION ». Aucun second système de notifications n'a
été créé : le pipeline existant (`communication_messages`, `communication_deliveries`, outbox transactionnelle,
worker `communications`) a été étendu.

## 1. Chaîne canonique

```
Cas d'usage métier (transaction)                       Worker communications (après commit)
──────────────────────────────────                     ───────────────────────────────────────────────
message + destinataires (instantané)  ──outbox──▶  dispatch : NotificationPolicy → livraisons
réservation des crédits SMS                         envoi : port fournisseur (hors verrou, hors transaction)
événement COMMUNICATION_REQUESTED                   résultat : SENT / FAILED_RETRYABLE / FAILED_PERMANENT
                                                    portefeuille : CONSUMPTION ou RELEASE
                                                    accusés : DELIVERED / FAILED (uniquement sur preuve)
```

* Aucun cas d'usage n'appelle Orange, Firebase ou SMTP. Un test vérifie qu'aucun module métier n'importe un adaptateur
  (`test_no_business_module_imports_a_provider`).
* Une panne fournisseur n'annule jamais une inscription, un paiement, une clôture de caisse ou un import : le métier a
  déjà validé sa transaction ; l'événement reste dans l'outbox (PostgreSQL) et le worker réessaie.
* Redis reste un simple signal de réveil ; PostgreSQL est la source de vérité (baux, `SKIP LOCKED`, reprise après crash).

## 2. Ports et adaptateurs

| Port (`edusync/shared/messaging/ports.py`) | Adaptateur réel | Simulation (dev/tests uniquement) |
|---|---|---|
| `SmsProviderPort.send_sms` | `OrangeSmsProvider` (`sms_orange.py`, httpx.AsyncClient) | `FakeSmsProvider` |
| `EmailProviderPort.send_email` | `SmtpEmailProvider` (`email_smtp.py`, aiosmtplib + `EmailMessage`) | `FakeEmailProvider` |
| `PushProviderPort.send_push` | `FcmPushProvider` (`push_fcm.py`, firebase-admin) | `FakePushProvider` |

Chaque adaptateur classe son résultat sans que le worker connaisse le fournisseur : `SENT` (preuve = identifiant),
`RETRYABLE`, `PERMANENT`, `INVALID_DESTINATION`, `INVALID_TOKEN`. `SendResult("SENT")` sans identifiant est refusé
par construction ; `DELIVERED` n'est jamais un résultat d'envoi.

Les simulations sont refusées en staging et en production par trois verrous : la fabrique (`factory.py`),
`Settings.assert_runtime_safe()` (démarrage refusé) et l'enregistrement des appareils push.

## 3. États de livraison

`QUEUED` → `PROCESSING` → `SENT` → `DELIVERED` (uniquement sur accusé fournisseur) ;
`FAILED_RETRYABLE` (nouvel essai planifié) ; `FAILED_PERMANENT` (lettre morte visible, relance manuelle possible) ;
`CANCELLED` (écarté par la politique ou canal désactivé). Colonnes : `provider_message_id`, `attempts`,
`last_error_code`, `last_attempt_at`, `sent_at`, `delivered_at`, `failed_at`, `cancelled_at`, `segments_billed`,
`wallet_state`.

Nouvelles tentatives : 30 s, 60 s, 120 s… plafonnées à 1 h, gigue ±20 %, `Retry-After` respecté, 6 tentatives au plus,
puis `FAILED_PERMANENT`. Aucune boucle infinie.

## 4. NotificationPolicy (`modules/communications/domain/policy.py`)

Seul endroit qui décide des canaux :

* **SMS** : école SMS activée, numéro E.164 valide, non dupliqué, crédits réservés ;
* **E-mail** : adresse présente, e-mail activé pour l'école (les e-mails de compte ne dépendent que de la plateforme) ;
* **Push** : appareils actifs du destinataire *dans la même école* (appareils plateforme pour un message plateforme),
  push non coupé par l'école.

Un canal écarté produit une livraison `CANCELLED` avec un motif (`NO_VALID_PHONE`, `SMS_DISABLED_FOR_SCHOOL`…), jamais
une erreur métier. Les crédits non utilisés sont libérés au moment du dispatch.

## 5. Données et multi-école

| Table | Rôle | Isolation |
|---|---|---|
| `communication_messages` | message (école ou compte / plateforme) | RLS FORCE ; `school_id` NULL réservé aux messages ACCOUNT / PLATFORM |
| `communication_recipients` | instantané des destinataires résolu par le cas d'usage | RLS FORCE ; secret à usage unique chiffré puis effacé |
| `communication_deliveries` | une livraison par (message, canal, destination) | RLS FORCE ; plateforme : métadonnées seulement |
| `school_sms_wallets` / `school_sms_ledger` | portefeuille SMS (voir SMS_WALLET_MODEL.md) | RLS FORCE, grand livre en ajout seul |
| `push_subscriptions` | appareils push (jeton chiffré) | RLS (école + utilisateur) |
| `account_tokens` | invitations / récupérations (empreinte SHA-256) | rôle plateforme uniquement |
| `provider_receipts` | accusés fournisseur reçus par webhook | appliqués par le worker, idempotents |

Le rôle `edusync_worker` n'atteint que les tables de file, le portefeuille, les appareils, les accusés et les colonnes
`id`, `status`, `name` des écoles — jamais les élèves, la finance ou le personnel.

## 6. Interfaces

* **École — Centre de communication** (menu « Communication ») : composer (individuel, classe, section, école selon
  les droits), aperçu avant envoi (destinataires, numéros invalides, doublons retirés, unités SMS, solde après envoi),
  confirmation liée à l'aperçu, historique (canal, statut, auteur, destinataires, unités, erreurs synthétiques, détail et
  relance), réglages (canaux de l'école, seuil, portefeuille, notifications de cet appareil).
* **Atelier Pro — Messagerie** : état des fournisseurs, santé du worker et de la file, volumes et taux d'échec 24 h,
  portefeuille SMS de chaque école, recharge et ajustement audités (second facteur récent), tests e-mail / push vers
  soi-même. Aucun corps de message d'école n'y est exposé.
* **Connexion** : « Mot de passe oublié ? », page de nouveau mot de passe, page d'acceptation d'invitation.

## 7. Droits (registre des capacités)

Réutilisées : `communications.compose`, `communications.send.individual|class|section|all_parents`,
`communications.sms.send`, `communications.sms.bulk_send`, `communications.history.read`, `communications.read`
(lecture du solde), `communications.delivery.retry`, `notifications.internal.configure` (canaux de l'école).
Ajoutées (Manager Système) : `platform.messaging.read`, `platform.sms_wallet.credit`. Registre : 280 capacités.

## 8. Hors ligne

Le brouillon du Centre de communication est conservé sur l'appareil hors connexion ; l'envoi n'est possible qu'en
ligne et n'est affiché comme accepté qu'après la réponse du serveur. Les opérations métier qui demandent une
notification restent valides même si les fournisseurs sont indisponibles (outbox).

## 9. Documents liés

SMS_ORANGE_INTEGRATION.md · SMS_WALLET_MODEL.md · PUSH_FCM_INTEGRATION.md · EMAIL_TRANSACTIONAL_INTEGRATION.md ·
EXTERNAL_MESSAGING_SECURITY_REVIEW.md · EXTERNAL_MESSAGING_CERTIFICATION.md.
