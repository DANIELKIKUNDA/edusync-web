# Portefeuille SMS par école

## 1. Modèle commercial retenu

École → achète des crédits SMS auprès d'EduSync → EduSync crédite le portefeuille de l'école → EduSync consomme son
propre compte Orange. Les écoles n'ouvrent pas de compte Orange. Première version : le paiement se fait hors
application ; un Manager Système crédite le portefeuille depuis l'Atelier Pro. Aucune plateforme de paiement en ligne
n'est développée maintenant.

> Contrôle externe avant la commercialisation : confirmer que le contrat Orange autorise cet usage multi-école.

## 2. Unité

L'unité interne est le **segment SMS facturable**, pas une somme d'argent. Un message long compte plusieurs unités
(tranches Orange 160 / 320 / 400 caractères, ou calcul GSM-7 / UCS-2 si plus élevé). Le prix payé par l'école
(`commercial_price`, `commercial_currency`) et le coût fournisseur (`provider_cost`, `provider_cost_currency`) sont
enregistrés à part, sans lien avec la comptabilité scolaire, et peuvent évoluer indépendamment.

## 3. Tables

* `school_sms_wallets(school_id, balance, reserved)` — `balance ≥ 0`, `reserved ≥ 0`, `reserved ≤ balance` ;
  disponible = `balance − reserved`.
* `school_sms_ledger` — **ajout seul** (déclencheur qui refuse UPDATE / DELETE, droits révoqués) : école, type,
  sens, quantité, solde et réservé après, source, acteur, référence, motif, identifiant de message fournisseur,
  clé d'idempotence (unique par école), coût et prix.

## 4. Mouvements

| Type | Effet | Qui peut le faire (vérifié dans la base) |
|---|---|---|
| `TOPUP` | solde + q (référence obligatoire) | plateforme |
| `RESERVATION` | réservé + q, refusé si disponible < q (`SMS_INSUFFICIENT_CREDIT`) | école (au moment de la confirmation) |
| `CONSUMPTION` | réservé − q, solde − q (au-delà de la réservation : pris sur le disponible) | worker (fournisseur a accepté) |
| `RELEASE` | réservé − q | école, worker (échec définitif, annulation, crédits non utilisés) |
| `ADJUSTMENT` | crédit ou débit motivé (5 caractères au moins), jamais négatif | plateforme |
| `REFUND` | solde + q, uniquement sur justification fournisseur | plateforme |

Tout mouvement passe par la fonction `school_sms_wallet_apply` : verrou de ligne sur le portefeuille (les mouvements
d'une école sont sérialisés), puis contrôle de la clé d'idempotence — un rejeu (double clic, nouvelle tentative du
worker) renvoie la première ligne sans rien modifier. Clés : `reserve:<message>`, `consumption:<livraison>`,
`release:<livraison>`, `release-dispatch:<message>`, `topup:<Idempotency-Key>`.

## 5. Envoi de masse

Aperçu → nombre de destinataires → numéros invalides → doublons retirés → unités estimées → crédits nécessaires →
solde après envoi → confirmation. La confirmation est liée à une empreinte de l'aperçu (audience, canaux, texte) : si
quoi que ce soit change, le serveur refuse et demande un nouvel aperçu. Le serveur recalcule tout et ne fait jamais
confiance aux chiffres du navigateur.

## 6. Réconciliation

Orange ne renvoie pas de nombre d'unités par message ; la consommation enregistrée est l'estimation réservée.
La réconciliation globale se fait avec `GET /sms/admin/v1/contracts` et `/statistics` (unités consommées du compte
EduSync). Un écart constaté se corrige par un `ADJUSTMENT` motivé, jamais par une modification du grand livre.

## 7. Preuves

`messaging_local_probe` : crédit idempotent (rejeu = même ligne, un seul audit), 5 crédits concurrents + 5 rejeux
concurrents = +60 exactement, débit refusé sous zéro, réservation unique, consommation / libération, grand livre
immuable même pour le propriétaire, isolation école A / école B.
