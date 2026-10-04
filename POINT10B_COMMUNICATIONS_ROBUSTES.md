# Point 10B — Communications robustes

## Architecture retenue
PostgreSQL reste la source de vérité. Redis est un transport léger de jobs/wake-ups, jamais la vérité de livraison. Les événements métier passent par l'outbox transactionnelle. Le worker et les adapters fournisseurs sont découplés du commit métier.

## Niveaux
- Plateforme : notifications système Atelier Pro, sans accès métier automatique aux écoles.
- École/organisation : notifications in-app et communiqués permissionnés.
- Externe : SMS puis adapters EMAIL/WHATSAPP/PUSH, optionnels et activés école par école.

## Sécurité et coûts
- deny-by-default et scopes existants individuel/classe/section/école ;
- SMS individuel et bulk séparés ; bulk reste CRITICAL ;
- fournisseur + sender obligatoires avant envoi externe ;
- estimation de segments SMS ; historique de livraison et retries ;
- aucun statut SENT/DELIVERED sans preuve fournisseur ;
- aucun échec de messagerie ne rollback un paiement/inscription.

## Implémenté dans ce lot
- migration 0025 : settings, templates, messages, deliveries, RLS FORCE ;
- API /api/v1/communications/readiness, /history, /send ;
- réutilisation des capacités RBAC déjà approuvées ;
- outbox COMMUNICATION_REQUESTED ;
- worker Redis fail-closed ;
- tests de contrats.

## Gate externe honnête
Aucun fournisseur Orange/AfricasTalking/Twilio/WhatsApp n'est branché dans ce lot : donc aucun SMS réel n'est déclaré certifié. Le provider adapter et ses credentials seront validés sur l'environnement réel.
