# Push — intégration Firebase Cloud Messaging (FCM)

Statut : **adaptateur et PWA prêts, `PUSH_FCM_REAL_CERTIFIED` = NON** tant que le projet Firebase n'est pas fourni et
que les essais sur appareils physiques n'ont pas été faits. La tarification et les conditions Firebase sont à
vérifier avant la production ; l'architecture n'en dépend pas (port `PushProviderPort`).

## 1. Backend

* `FcmPushProvider` (`shared/messaging/push_fcm.py`) sur le SDK officiel **firebase-admin** ; appel bloquant exécuté
  hors de la boucle (`asyncio.to_thread`), uniquement depuis le worker.
* Compte de service : fichier secret monté (`EDUSYNC_FCM_SERVICE_ACCOUNT_FILE`, recommandé) ou JSON injecté par
  l'outil de déploiement (`EDUSYNC_FCM_SERVICE_ACCOUNT_JSON`). Jamais dans Git, jamais envoyé au navigateur.
* Messages **data-only** : titre, texte court, lien interne. Un push ne porte jamais le corps du message ni une donnée
  personnelle (règle N1 conservée : « Ouvrez EduSync pour lire le message »).
* Classement : `UnregisteredError` / `SenderIdMismatchError` / argument invalide → `INVALID_TOKEN` (appareil désactivé
  automatiquement, les autres appareils de la personne restent actifs) ; quota → réessayable (5 min) ; indisponible /
  interne → réessayable ; identifiants refusés → définitif.
* Point à vérifier lors du test réel : firebase-admin 7.7 marque `Message.token` comme déprécié au profit de `fid`
  (identifiant d'installation). EduSync envoie la valeur de `getToken()` comme jeton d'enregistrement, toujours
  accepté ; confirmer sur un appareil réel et, si nécessaire, basculer vers `fid` dans l'adaptateur seulement.

## 2. Frontend / PWA

* SDK officiel Firebase, limité à ses deux paquets utiles **@firebase/app 0.16.2** et **@firebase/messaging 0.13.3** (ceux du SDK firebase 12.19 ; le paquet parapluie entraînait Firestore et une vulnérabilité gRPC inutile côté navigateur), chargé à la demande uniquement après l'action « Activer les notifications »
  (Centre de communication → Réglages → Notifications sur cet appareil). Aucune demande de permission au chargement.
* Le jeton est obtenu avec **le service worker EduSync existant** (`/sw.js`, `serviceWorkerRegistration`) : pas de
  second service worker. `sw.js` affiche les messages (`push`), ouvre la route EduSync au clic (`notificationclick`,
  même origine uniquement) et prévient la page ouverte (toast au premier plan).
* CSP : `connect-src` n'ajoute que `https://firebaseinstallations.googleapis.com` et
  `https://fcmregistrations.googleapis.com` (nécessaires à `getToken`).
* Le jeton n'est ni affiché ni conservé dans le navigateur ; seul l'identifiant serveur de l'abonnement est mémorisé
  pour la désactivation sur cet appareil.

## 3. Modèle d'appareil (`push_subscriptions`)

`user_id`, `membership_id`, `school_id`, `device_id`, navigateur / plateforme, empreinte SHA-256 du jeton (unicité),
**jeton chiffré** (AES-256-GCM, clé dérivée de `EDUSYNC_MFA_ENCRYPTION_KEY` pour ce seul usage), création, dernière
utilisation, révocation et motif, dernière erreur fournisseur. Plusieurs appareils par personne ; révoquer un appareil
ne touche pas les autres. Un même navigateur réenregistré par un autre compte ou une autre école révoque l'ancien
enregistrement (`TOKEN_REASSIGNED`). Déconnexion globale, changement de mot de passe, désactivation du membre :
appareils révoqués.

## 4. Ce que l'opérateur doit préparer dans Firebase

1. **Projet Firebase** à créer (ou sélectionner) ; activer Cloud Messaging.
2. **Application Web** du projet : configuration publique (`apiKey`, `projectId`, `messagingSenderId`, `appId`,
   `authDomain`) → variable `EDUSYNC_FCM_WEB_CONFIG_JSON` (publique, mais gérée comme configuration de déploiement).
3. **Clé Web Push (VAPID)** : Paramètres du projet → Cloud Messaging → *Web Push certificates* → générer une paire ;
   la **clé publique** → `EDUSYNC_FCM_VAPID_PUBLIC_KEY`.
4. **Compte de service** : Paramètres → Comptes de service → *Générer une clé privée* (JSON) → secret du service
   *communications-worker* (`EDUSYNC_FCM_SERVICE_ACCOUNT_FILE` monté, ou `EDUSYNC_FCM_SERVICE_ACCOUNT_JSON`).
   Ne jamais le coller dans le chat ni le committer.
5. **Domaines** : servir EduSync en HTTPS sur le domaine de staging (obligatoire pour le push web) ; si la clé API
   Web est restreinte par référent HTTP, autoriser ce domaine.
6. `EDUSYNC_PUSH_PROVIDER=fcm` sur l'API et le worker.

## 5. Certification réelle (appareils physiques)

`push_provider_probe` (jeton d'un appareil de test) puis, sur un **Android Chrome avec la PWA installée** :
notification au premier plan, PWA fermée / arrière-plan, clic vers la route EduSync, révocation d'un appareil, jeton
invalide, utilisateur déconnecté, changement d'école (aucune fuite école A → école B). **iOS / Safari** : à tester à
part sur iPhone réel (PWA ajoutée à l'écran d'accueil) avant toute déclaration de support ; une émulation Chromium ne
suffit pas.
