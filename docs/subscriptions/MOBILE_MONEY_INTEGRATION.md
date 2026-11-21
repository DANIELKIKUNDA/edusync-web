# Paiement Mobile Money des abonnements EduSync

Ce moteur concerne uniquement les factures commerciales Volcano Tech. Il ne lit ni ne modifie la caisse, les frais ou les paiements d’élèves d’une école.

## Contrat de sécurité

- L’école initie le paiement seulement pour une facture liée à l’école inscrite dans son jeton.
- Le numéro complet est envoyé à l’opérateur, mais seule une version masquée est conservée.
- Une réponse d’initiation ne confirme jamais le paiement. Seul un webhook signé HMAC-SHA256 peut le faire.
- Le montant, la devise, l’opérateur et sa référence doivent correspondre à la demande enregistrée.
- Chaque événement fournisseur est unique. Une répétition retourne un succès sans créditer deux fois la facture.
- L’identité de l’événement est lue dans le corps SIGNÉ (`event_id`), jamais dans un en-tête non signé ; à défaut, l’empreinte SHA-256 du corps signé sert d’identité (revue du 21/11/2026).
- Un message non signé ou mal signé est refusé (401) sans rien écrire en base : il est seulement journalisé.
- Un refus (montant ou devise différents, contenu invalide) reste enregistré avec sa raison.
- Le verrouillage du paiement et de la facture rend le rapprochement atomique.
- Une facture intégralement payée active ou renouvelle l’abonnement et ses droits. Un paiement partiel reste visible sans activer une période complète.
- Les demandes sans confirmation expirent automatiquement.

## Variables à fournir après choix de l’opérateur

`EDUSYNC_MOBILE_MONEY_MODE=live`, `EDUSYNC_MOBILE_MONEY_PROVIDER`, `EDUSYNC_MOBILE_MONEY_API_BASE`,
`EDUSYNC_MOBILE_MONEY_API_KEY`, `EDUSYNC_MOBILE_MONEY_WEBHOOK_SECRET` et `EDUSYNC_MOBILE_MONEY_CALLBACK_URL`.

En staging et production, le mode `sandbox` est refusé. En mode `live`, les URL HTTPS et tous les secrets sont obligatoires. Les secrets ne doivent jamais être enregistrés dans Git.

## Mise en service

1. Choisir l’agrégateur ou les opérateurs et obtenir un compte marchand ainsi que les clés de test.
2. Adapter, si nécessaire, les noms de champs de leur API au port générique `payment_provider.py`.
3. Déclarer l’URL publique `/api/v1/subscription-payments/webhooks/{FOURNISSEUR}` chez le fournisseur.
4. Injecter les secrets dans Coolify, déployer d’abord en staging et exécuter les cas succès, refus, délai dépassé, doublon et montant falsifié.
5. Vérifier la facture, l’abonnement, les droits et le journal Atelier Pro avant activation live.
