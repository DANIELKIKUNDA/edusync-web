# Temps réel dans l'espace école (01/11/2026)

Décision du propriétaire : « quand un caissier encaisse, après la validation, automatiquement tout le monde voit sans
recharger » — pour **tous les rôles de l'école** : dès qu'une information concerne les autres, le temps réel est obligatoire.

## Fonctionnement

- **Serveur** : après **chaque écriture réussie** de l'espace école (n'importe quelle route, y compris les opérations
  rejouées après un travail hors ligne), un signal part sur le canal de l'école (Redis) — `LiveChangesMiddleware`,
  `shared/infrastructure/live_changes.py`. Branché **une seule fois** pour toute l'API : aucune route ne peut l'oublier.
- **Contenu du signal** : uniquement les **domaines** touchés (`finance`, `students`, `headcounts`, `personnel`, `stock`,
  `settings`, `communications`, `access`, `documents`) — **aucun montant, nom ni identifiant**.
- **Écoute** : `GET /api/v1/live/stream` (Server-Sent Events), ouvert à tout membre de l'école ; jeton dans l'en-tête,
  jamais dans l'adresse ; flux renouvelé toutes les 5 minutes (session révoquée = arrêt).
- **Écrans** : chacun se recharge **lui-même** quand son domaine change, avec les droits du membre connecté — personne ne
  peut recevoir par ce canal ce que son rôle ne voit pas. Regroupement des signaux (0,7 s), onglet caché rafraîchi à son
  retour, rattrapage complet après une coupure.

Écrans en direct : accueil (cartes et « Le point du jour »), caisse personnelle et supervision des caisses, journée de
caisse, reçus, recouvrement, panier de l'encaissement (un autre caissier encaisse le même élève : les frais réglés
disparaissent aussitôt — pas de double encaissement), élèves et inscriptions, effectifs, intendance, personnel,
communication, accès et rôles, historique des documents. La cloche des notifications l'était déjà.

## Preuves

| Preuve | Résultat |
|---|---|
| Signal brut (`tools/local/live_signal_probe.py`) : la Secrétaire (aucun droit financier) écoute, le caissier enregistre une dépense | reçu en **2,7 s** ; contenu exact `{"domains": ["finance"]}` |
| Deux navigateurs (`browser-tests/local_realtime_certification.mjs secretariat`) : le caissier inscrit un élève | écran Élèves de la Secrétaire **76 → 77 en 0,6 s**, sans rechargement |
| Deux navigateurs (`… gestionnaire`) : le caissier valide un encaissement | « Le point du jour » du Gestionnaire **12 000 → 24 000 FC en 1,3 s**, sans rechargement |
| Tests backend (`tests/test_live_changes.py`) | 4/4 ; suite complète **1380 passed** |
| Non-régression : caissier, gestionnaire, quatre rôles | 0 échec, **18/18**, **46/46** ; frontend **91/91** |

Les preuves à plusieurs navigateurs n'en ouvrent que **deux à la fois** : l'ordinateur de développement s'est coupé
trois fois par surchauffe sous charge lourde (journal Windows : Kernel-Power 41, sans écran bleu ni bouton).
