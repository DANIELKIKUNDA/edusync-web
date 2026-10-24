# Certification — rôle « Caissier » (24/10/2026)

Décision du propriétaire préalable : en RDC, le caissier est généralement aussi le secrétaire. Le rôle standard
Caissier détient donc tous les droits du Secrétariat (migration `0090`, PR « Rôles : le caissier a tous les droits du
secrétariat »), chaque droit restant ajustable par l’école. L’import des élèves appartient au Secrétariat (donc au
Caissier), l’import du personnel au Gestionnaire.

## Méthode

1. L’administrateur crée la caissière avec le formulaire « Ajouter un membre » (mot de passe provisoire affiché une fois) ;
   elle se connecte et choisit son mot de passe (`frontend/browser-tests/local_caissier_prepare.mjs`).
2. Elle fait une vraie journée de guichet dans un vrai navigateur, sur le vrai serveur et la vraie base
   (`frontend/browser-tests/local_caissier_certification.mjs`) : **12 étapes sur 12, aucune erreur serveur**.

| Étape | Résultat |
|---|---|
| Accueil | Outils du guichet (Nouvel encaissement, Ma caisse du jour, recherche d’élève) ; plus de bloc de paramétrage |
| Menu | Élèves & inscriptions, Centre financier, Personnel, Effectifs & dépôts, Communication, Documents, Synchronisation |
| Ouverture de caisse | Caisse ouverte, fonds initial, entrées, sorties, solde théorique par devise |
| Inscription | Nouveau foyer + élève, matricule automatique ; période d’inscription signalée, jamais bloquante |
| Encaissement | Recherche, échéances dans l’ordre (une tranche verrouillée tant que la précédente n’est pas soldée), action conseillée, encaissement, numéro de reçu |
| Reçu | Aperçu imprimable sans blocage de sécurité, impression séparée de l’encaissement |
| Plan anticipé | Le plan créé pour quelques classes est bien proposé à un élève de ces classes |
| Vente d’article | Article en stock, total, encaissement de la vente ; le stock baisse |
| Dépense de caisse | Confirmation explicite, dépense enregistrée et tracée |
| Clôture | Montant compté, « Journée de caisse clôturée » |

## Défauts trouvés et corrigés pendant la certification

- **Aperçu du reçu vide (staging et production)** : la politique de sécurité du site (CSP) n’autorisait pas le PDF
  fabriqué par le navigateur dans le cadre d’aperçu. Ajout de `frame-src 'self' blob:` (documents d’EduSync seulement),
  `frame-ancestors 'none'` et `object-src 'none'` inchangés.
- Accueil et Paramètres : le bloc de mise en service, « Compléter le paramétrage » et « Lancer l’assistant » ne
  s’affichent plus qu’à qui peut modifier le paramétrage.
- Personnel : plus de cartes en chargement infini pour un rôle sans résumé du personnel ; ouverture sur l’Annuaire.
- Vente d’articles : stock lisible (« En stock : 50 » au lieu de « 50.000 »), mention inutile retirée, ruptures en fin
  de liste.
- Caisse : boutons « Clôturer ma caisse » et « Enregistrer la dépense » au style de l’application (plus de bouton gris
  du navigateur).
- Élèves & inscriptions : en-tête avec ses marges ; message de période d’inscription aligné dans l’assistant.

## Reste pour ce rôle

- **Impression directe des reçus** (sans fenêtre d’aperçu), demandée par le propriétaire pour après les paramètres :
  poste de caisse configuré en impression directe et, plus tard si besoin, un agent d’impression local.
- Vérification visuelle du PDF du reçu sur staging par le propriétaire (le navigateur de test sans écran ne dessine pas
  les PDF ; l’absence de blocage de sécurité est, elle, vérifiée automatiquement).
