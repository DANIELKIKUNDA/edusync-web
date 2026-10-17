# Revue de sécurité — messagerie externe

| Risque | Mesure | Preuve |
|---|---|---|
| Secret fournisseur divulgué | secrets uniquement dans l'environnement / coffre de déploiement ; secret Orange, mot de passe SMTP et compte de service Firebase donnés au **seul worker** ; l'API ne reçoit que des identifiants non secrets ; `.env.example` sans valeur réelle | revue du compose ; scan de secrets de la certification |
| Secret dans un journal / une réponse | codes d'erreur courts (`safe_error`), jamais de corps fournisseur ; jeton OAuth Orange jamais journalisé ni renvoyé ; jetons push et liens jamais renvoyés par l'API | `messaging_local_probe` : aucun jeton dans les réponses ni dans le journal du worker ; tests SMTP / Orange |
| Service account Firebase côté navigateur | seule la configuration Web publique et la clé VAPID publique sont servies (`/push/config`, liste blanche de clés) | revue `notifications_center` |
| Faux fournisseur en production | refus par la fabrique, par le contrôle de démarrage et à l'enregistrement d'un appareil | `test_fakes_refused_in_protected_environments`, `test_s1_*` |
| Jeton push volé en base | chiffré AES-256-GCM (clé dérivée dédiée), empreinte pour l'unicité | probe : aucun jeton en clair |
| Push vers le mauvais compte / la mauvaise école | appareils filtrés par utilisateur **et** école ; jeton réattribué → ancien révoqué ; désactivation du membre, déconnexion globale, changement de mot de passe → révocation | probe (TOKEN_REASSIGNED, isolation B) |
| Contenu sensible sur écran verrouillé | un push ne porte jamais le corps du message | règle N1, test et probe N1 |
| Rejeu de lien d'invitation / de récupération | empreinte seule, usage unique sous verrou, expiration courte, révocation à chaque nouveau lien et au changement de mot de passe, fragment d'URL | probe (rejeu refusé, expiration refusée) |
| Énumération de comptes | même réponse 202 pour une adresse connue ou inconnue ; limite 5 / h / IP | probe |
| Lecture des messages des écoles par la plateforme | supervision par métadonnées (statut, canal, quantités) ; politique RLS plateforme limitée à `SELECT` des livraisons, aucun corps exposé | probe (aucun corps dans `/platform/messaging/status`) |
| Fraude sur les crédits SMS | grand livre en ajout seul, verrou, idempotence, rôles vérifiés dans la base, aucun solde négatif, crédit audité avec second facteur récent | probe (concurrence, immuabilité, RBAC) |
| Envoi de masse non voulu | droits `communications.sms.bulk_send` / `send.all_parents`, aperçu obligatoire, confirmation liée à l'empreinte, audit, limite 60 envois / h / compte | probe |
| Callback Orange falsifié | secret de chemin ≥ 24 caractères (temps constant) + liste d'IP Orange ; idempotent | tests webhook |
| Injection dans les e-mails | échappement HTML de chaque valeur ; destinataire sans retour à la ligne (anti-injection d'en-têtes) | tests modèles et SMTP |
| SMTP en clair | refusé hors développement | contrôle de démarrage |
| Lien de compte non HTTPS | refusé hors développement quand l'e-mail est actif | contrôle de démarrage |
| Dépendances | `firebase-admin`, `aiosmtplib` (Python), `@firebase/app` et `@firebase/messaging` (npm, sans Firestore ni gRPC) figés ; `npm audit` : 0 vulnérabilité ; licences Apache-2.0 / MIT / BSD ; scripts post-installation npm bloqués par la politique d'autorisation | supply chain + npm audit de la certification |

Limites assumées : Orange ne signe pas ses accusés (IP + secret de chemin compensent) ; SMTP ne prouve pas la livraison
(`SENT` seulement) ; la consommation SMS est l'estimation réservée (réconciliation par ajustement motivé).
