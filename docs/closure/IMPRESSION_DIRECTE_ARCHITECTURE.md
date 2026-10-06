# Impression directe — état réel et architecture proposée

## Ce qui existe (vérifié, clôture locale 2026-10)

| Élément | État |
|---|---|
| Reçu PDF A5 et ticket 80 mm, généré à la demande depuis le grand livre | Fait — `POST /finance/checkout/receipts/{id}/print` |
| Lot de reçus d'un panier familial (un reçu par enfant, un seul PDF) | Fait — `POST /finance/checkout/family-baskets/{id}/receipts/print` |
| Original puis duplicata tracés (`finance_receipt_prints`, append-only) + audit | Fait |
| Politique d'impression par école : ne rien proposer / proposer / ouvrir l'aperçu | Fait — `school_print_settings` |
| Format par défaut A5 ou 80 mm | Fait |
| Aperçu dans EduSync puis impression confirmée par le caissier | Fait (iframe + bouton Imprimer) |
| Impression **silencieuse** sur une imprimante précise, sans boîte de dialogue | **Non faisable dans un navigateur** |

`window.print()` n'est pas une impression directe : le navigateur affiche toujours sa boîte de dialogue et choisit
l'imprimante par défaut du poste. Ce n'est donc pas présenté comme l'équivalent de l'impression directe historique.

## Architecture proposée : agent d'impression local

```text
Navigateur (EduSync)                Poste de caisse                      Imprimante
 POST /print-jobs  ──HTTPS──▶  [API EduSync] crée un travail signé
                                     │
 agent local EduSync  ◀──── interroge (WebSocket/HTTPS sortant, authentifié par appareil enregistré)
   • télécharge le PDF du reçu (lien signé court)
   • imprime via l'API Windows (spooler) sur l'imprimante configurée pour ce poste
   • renvoie le statut (imprimé / erreur) → finance_receipt_prints
```

Principes :
1. Le paiement reste validé même si l'agent ou l'imprimante échoue (doctrine Point 5B).
2. L'agent n'expose **aucun port** sur le réseau : il appelle le serveur en sortant, comme un appareil enregistré.
3. Configuration par poste : imprimante, format (A5 / 80 mm), nombre de copies, coupe papier (ESC/POS pour les
   imprimantes thermiques ou PDF via le pilote Windows).
4. Chaque impression reste tracée (original / duplicata) exactement comme aujourd'hui.

## Ce qui reste à décider ou à tester

| Sujet | Classement |
|---|---|
| Modèle d'imprimante thermique réellement utilisé dans les écoles | À CONFIRMER PAR LE PROPRIÉTAIRE |
| Mise en page exacte du reçu Desktop (golden master) | À CONFIRMER PAR LE PROPRIÉTAIRE |
| Développement et signature de l'agent Windows | Étape ultérieure (hors clôture locale) |
| Impression réelle sur matériel | BLOCKED — matériel requis |
