# Notifications de la plateforme — rapport N1

Preuve principale : `certification/n0-n1-20261007/notifications-live.json` (44/44 en conditions réelles).

## Modèle
* Une **notification** est un objet métier : destinataire (compte, et école s'il s'agit d'un membre), gravité
  (information, avertissement, critique), titre, message, lien interne facultatif, expiration facultative,
  date de lecture. Rattachée à une **campagne** quand elle vient de l'Atelier Pro.
* Une campagne ne crée **jamais deux notifications pour le même destinataire** (index unique), même rejouée ou
  envoyée en parallèle (3 envois simultanés même clé → 1 campagne).
* Les liens sont des chemins internes (`/…`) : refusés par l'API et impossibles en base (contrainte SQL) pour
  `https://`, `//`, `javascript:` et les barres obliques inverses.

## Ciblage (7 cibles, vérifiées)
Toutes les écoles actives · écoles choisies · un rôle école (toutes ou certaines écoles) · un membre d'une
école · toute l'équipe plateforme · un rôle plateforme · un compte plateforme. Les écoles suspendues, comptes
désactivés et comptes plateforme suspendus sont exclus ; une cible vide est refusée ; 50 000 destinataires
maximum ; 20 campagnes par heure.

## Centre de notifications
Cloche avec compteur dans l'espace école **et** dans l'Atelier Pro ; panneau rapide (8 dernières) ; écran
complet avec filtres (toutes / non lues / lues, gravité), historique paginé sans recouvrement, « tout marquer
comme lu », expiration respectée, mobile 44 px. Gravité indiquée par texte et icône, pas seulement la couleur.

## Isolation
Boîte plateforme et boîte école séparées ; un membre ne voit ni ne peut marquer la notification d'un autre ;
le Manager ne peut pas agir sur une notification d'école via sa boîte (404).

## Push
Abstraction `PushProvider` : désactivée par défaut ; simulateur (`mock`) pour la recette locale. Abonnement par
appareil (plusieurs appareils), désabonnement, révocation automatique à la déconnexion globale et au changement
de mot de passe. L'adresse d'abonnement n'est jamais stockée en clair (empreinte SHA-256). La charge envoyée
contient titre, gravité et lien interne, **jamais le corps** ni de donnée personnelle.
**Web Push / Firebase réels : BLOCKED_EXTERNAL** (clés VAPID / compte Firebase et domaine HTTPS nécessaires).

## SMS ≠ notification
Aucune campagne n'envoie de SMS ; l'interface le dit à chaque envoi. Les SMS restent dans le module
Communication (fournisseur réel non connecté : sandbox).

## Audit
Chaque campagne : `PLATFORM_NOTIFICATION_CAMPAIGN_SENT` (cible, gravité, nombre de destinataires, lien,
expiration). La liste des campagnes affiche le taux de lecture.
