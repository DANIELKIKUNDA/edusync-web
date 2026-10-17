# SMS — intégration Orange Developer (SMS API)

Statut : **adaptateur prêt, `SMS_ORANGE_REAL_CERTIFIED` = NON** tant que les secrets ne sont pas fournis et que
`sms_provider_probe` n'a pas été exécuté avec un vrai compte.

## 1. Source du contrat

Le contrat a été lu dans la documentation officielle Orange Developer le 2026-10-17, pas reconstitué de mémoire :

* page générique « SMS API — Getting started » (commune à tous les pays de l'offre Afrique / Moyen-Orient) ;
* référence et Swagger de la variante **RD Congo** (`sms-cd`), FAQ et page tarifs RDC ;
* guide « 2-legged OAuth flow step by step ».

> **Contrôle externe obligatoire** : sur Orange Developer, la page de l'API SMS **RD Congo est marquée « API
> deprecated »**. Avant toute mise en production, confirmer auprès d'Orange RDC (formulaire de contact) que les
> nouvelles souscriptions et le service restent disponibles, ou obtenir le produit de remplacement. L'adaptateur peut
> être remplacé sans toucher au métier (port `SmsProviderPort`).

## 2. Contrat implémenté (`backend/src/edusync/shared/messaging/sms_orange.py`)

| Élément | Implémentation |
|---|---|
| Jeton | `POST https://api.orange.com/oauth/v3/token`, `Authorization: Basic base64(client_id:client_secret)`, `Accept: application/json`, `grant_type=client_credentials` |
| Durée du jeton | 3600 s ; mis en cache (Redis, sinon mémoire) jusqu'à 2 min avant expiration ; `expires_in` lu en texte ou en nombre ; jamais stocké comme configuration |
| Envoi | `POST /smsmessaging/v1/outbound/{tel%3A%2B…}/requests`, corps `outboundSMSMessageRequest` (`address`, `senderAddress`, `senderName` facultatif, `outboundSMSTextMessage.message`) |
| Preuve d'envoi | `201 Created`, identifiant = dernier segment de `resourceURL` (ou `Location`) |
| Jeton expiré | `401` code 42 : jeton supprimé, une nouvelle tentative immédiate |
| Débit | 5 SMS / seconde par worker (`EDUSYNC_ORANGE_SMS_MAX_TPS`) ; endpoint jeton limité à 50 / min (cache) |
| Classement des erreurs | `429` / `403` code 53 → réessayable (Retry-After) ; `408`, `5xx` → réessayable ; `400 SVC0004/SVC0002` → numéro invalide ; `400 SVC0280` → message trop long ; autres `4xx` → définitif ; délai / réseau → réessayable |
| Accusés de livraison | callback déclaré à Orange : `POST /api/v1/webhooks/orange/sms-dr/{secret}` |

Statuts d'accusé documentés : `DeliveredToTerminal` → **DELIVERED** ; `DeliveryImpossible` → FAILED (un accusé
`DeliveredToTerminal` ultérieur peut encore le corriger) ; `DeliveredToNetwork`, `DeliveryUncertain`,
`MessageWaiting` → restent `SENT` (aucune preuve de réception sur le téléphone).

Sécurité du callback : Orange ne documente **aucune signature** ; seule son adresse IP source est indiquée. EduSync
exige donc un secret de chemin imprévisible (≥ 24 caractères, comparaison à temps constant) **et** la liste des IP
fournies par Orange (`EDUSYNC_ORANGE_SMS_DR_ALLOWED_IPS`). L'accusé est stocké une seule fois
(`provider_receipts`, clé unique) puis appliqué par le worker.

## 3. Longueur et facturation

La page tarifs RDC facture par tranches de caractères : 1 à 160 → 1 unité, 161 à 320 → 2, 321 à 400 → 3. Le Swagger
indique `maxLength: 160` pour le champ message : les deux sources se contredisent. EduSync :

* estime les unités par le maximum entre les tranches Orange et le calcul GSM-7 / UCS-2 (prudent) ;
* refuse les SMS de plus de 400 caractères avant tout appel ;
* **point à vérifier lors du premier test réel** : un message de 161 à 400 caractères est-il accepté ou refusé
  (`SVC0280`) par le compte souscrit ? Si refusé, abaisser `MAX_SMS_CHARS` à 160.

## 4. Ce que l'opérateur doit récupérer dans Orange Developer (checklist)

1. **Produit souscrit** : nom exact de l'API (« SMS RD Congo » ou équivalent) et pays de l'offre ; confirmation
   qu'elle n'est pas en fin de vie (voir l'avertissement ci-dessus).
2. **Application** (menu *MyApps*) : `Client ID` et `Client secret`.
3. **Adresse d'expéditeur du pays** : par exemple `tel:+2430000` pour la RDC (tableau des pays de la documentation).
4. **Nom d'expéditeur** (*Sender name*) : nom personnalisé demandé via le formulaire « SMS API queries » (type
   « Sender name »), 11 caractères alphanumériques au plus ; attendre l'e-mail de validation avant de l'utiliser.
   Dans certains pays, le nom par défaut n'est plus accepté depuis juin 2026.
5. **État du compte et crédits** : contrat actif, date d'expiration, unités disponibles (écran *Configure*, ou
   `GET /sms/admin/v1/contracts` — la sonde réelle l'affiche) ; achat d'un pack si nécessaire.
6. **Accusés de livraison** : déclarer l'URL `https://<domaine-staging>/api/v1/webhooks/orange/sms-dr/<secret>` via le
   formulaire (type « Real time SMS DR ») ; noter l'**adresse IP publique** qu'Orange communiquera.
7. **Contrat commercial** : confirmer par écrit que les conditions Orange autorisent l'usage par plusieurs écoles
   clientes d'EduSync (revente / sous-allocation). EduSync ne présume pas la réponse juridique.

## 5. Où saisir les secrets (jamais dans le chat, jamais dans Git)

* **Local** : `.local/certification.env` (non versionné).
* **Staging / production (Coolify)** : variables secrètes du service *communications-worker* :
  `EDUSYNC_SMS_PROVIDER=orange`, `EDUSYNC_ORANGE_SMS_CLIENT_ID`, `EDUSYNC_ORANGE_SMS_CLIENT_SECRET`,
  `EDUSYNC_ORANGE_SMS_SENDER_ADDRESS`, `EDUSYNC_ORANGE_SMS_SENDER_NAME`. Sur le service *backend* (API) :
  `EDUSYNC_SMS_PROVIDER`, `EDUSYNC_ORANGE_SMS_CLIENT_ID`, `EDUSYNC_ORANGE_SMS_SENDER_ADDRESS` (identifiants non
  secrets), `EDUSYNC_ORANGE_SMS_DR_SECRET`, `EDUSYNC_ORANGE_SMS_DR_ALLOWED_IPS`. Le secret client n'est donné qu'au worker.
* **Sonde réelle** : `EDUSYNC_PROBE_SMS_TO` = votre propre numéro de test (E.164).
