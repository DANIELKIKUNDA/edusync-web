# EduSync — plan d'implémentation du moteur SaaS d'abonnements

Date : 20 novembre 2026

Statut : plan directeur avant implémentation

Produit cible : `edusync-web` en production

## 1. Objectif

Permettre à Volcano Tech de vendre EduSync à plusieurs écoles sans collecte
physique récurrente : souscription à un plan, activation de modules, facturation,
paiement à distance, relances, grâce, limitation, régularisation et réactivation
automatiques.

Le moteur doit fonctionner avant même l'intégration d'un prestataire Mobile Money.
Le paiement manuel contrôlé et le paiement par API utilisent le même registre.

## 2. Principes non négociables

1. `edusync-web` reste l'unique application de production.
2. Le moteur commercial est séparé de la finance interne des écoles.
3. Un impayé ne supprime jamais les données d'une école.
4. La suspension commerciale est distincte de la suspension technique.
5. Une école garde toujours un chemin pour voir et payer sa facture.
6. Le backend décide des modules utilisables ; masquer un menu ne suffit pas.
7. Toutes les mutations financières sont idempotentes et auditées.
8. Les montants utilisent `Decimal` et une devise explicite (`USD` ou `CDF`).
9. Aucun numéro de carte, PIN ou secret Mobile Money n'est stocké par EduSync.
10. Un prestataire de paiement est remplaçable par configuration/adaptateur.
11. Les écoles déjà en production sont migrées sans interruption et sans dette créée implicitement.
12. Toute activation, remise, prolongation ou suspension manuelle est motivée et traçable.

## 3. Séparation des domaines

### 3.1 Domaine Commercial SaaS

- catalogue des plans ;
- prix et versions tarifaires ;
- catalogue des modules vendables ;
- droits d'usage d'une école ;
- abonnement et cycle ;
- facture Volcano Tech → école ;
- paiement de l'abonnement ;
- crédit, remise et ajustement ;
- échéance, grâce et limitation ;
- rapprochement et reçus ;
- indicateurs de revenu.

### 3.2 Finance scolaire existante

- frais scolaires ;
- charges des élèves ;
- encaissements ;
- caisse ;
- recouvrement ;
- rapports financiers de l'école.

Les tables, permissions, factures et reçus de ces deux domaines ne doivent jamais
être confondus.

## 4. États métier

### 4.1 Abonnement

| État | Signification |
| --- | --- |
| `TRIAL` | Essai limité dans le temps |
| `PENDING_PAYMENT` | Offre choisie, premier paiement attendu |
| `ACTIVE` | Accès payé ou accordé |
| `PAST_DUE` | Échéance dépassée, relances en cours |
| `GRACE` | Accès conservé pendant la période de grâce |
| `LIMITED` | Utilisation limitée, paiement et restitution disponibles |
| `SUSPENDED` | Accès métier suspendu sans suppression de données |
| `CANCELLED` | Résiliation explicite, historique conservé |
| `EXPIRED` | Contrat à durée déterminée arrivé à terme |

Transitions autorisées et raisons doivent être codifiées. Aucune transition directe
arbitraire ne sera réalisée par l'interface.

### 4.2 Facture

`DRAFT → ISSUED → PARTIALLY_PAID → PAID`

Branches possibles : `VOID`, `OVERDUE`, `REFUNDED`.

Une facture émise est immuable. Une correction passe par un avoir ou un ajustement.

### 4.3 Paiement

`CREATED → PENDING → SUCCEEDED`

Branches possibles : `FAILED`, `CANCELLED`, `EXPIRED`, `REFUNDED`.

## 5. Modèle de données cible

### 5.1 Catalogue

- `saas_modules`
  - code stable ;
  - libellé ;
  - description ;
  - dépendances ;
  - statut vendable ;
  - version.
- `saas_plans`
  - code ;
  - nom ;
  - description ;
  - statut brouillon/actif/retiré ;
  - public ou offre négociée.
- `saas_plan_versions`
  - plan ;
  - périodicité ;
  - prix et devise ;
  - durée ;
  - jours de grâce ;
  - date d'effet ;
  - règles de renouvellement.
- `saas_plan_modules`
  - version de plan ;
  - module ;
  - niveau/limite éventuelle.

Un changement de prix crée une nouvelle version. Il ne modifie jamais rétroactivement
le contrat d'une école.

### 5.2 Contrats et droits

- `saas_subscriptions`
  - école ;
  - version de plan ;
  - état ;
  - période courante ;
  - prochaine échéance ;
  - renouvellement automatique ;
  - politique de grâce ;
  - version optimiste.
- `saas_subscription_events`
  - ancien/nouvel état ;
  - raison ;
  - acteur ;
  - horodatage ;
  - corrélation.
- `saas_entitlements`
  - école ;
  - module ;
  - source (`PLAN`, `ADDON`, `TRIAL`, `MANUAL`) ;
  - début/fin ;
  - limite ;
  - état.
- `saas_addons`
  - module supplémentaire ;
  - prix versionné ;
  - période.

### 5.3 Facturation et paiement

- `saas_invoices`
  - numéro séquentiel ;
  - école ;
  - période ;
  - devise ;
  - sous-total, remise, frais, total, payé, solde ;
  - échéance ;
  - état ;
  - instantané de l'identité facturée.
- `saas_invoice_lines`
  - description ;
  - quantité ;
  - prix unitaire ;
  - taxe éventuelle ;
  - total ;
  - module/plan d'origine.
- `saas_payments`
  - référence EduSync ;
  - facture ;
  - canal ;
  - prestataire ;
  - référence prestataire ;
  - montant/devise ;
  - état ;
  - dates d'initiation/confirmation.
- `saas_payment_attempts`
  - requête/réponse normalisée et expurgée ;
  - code d'erreur ;
  - numéro de téléphone masqué ;
  - idempotency key.
- `saas_payment_webhooks`
  - prestataire ;
  - identifiant d'événement unique ;
  - signature vérifiée ;
  - empreinte du corps ;
  - résultat de traitement ;
  - dates reçue/traitée.
- `saas_credits` et `saas_refunds`
  - ajustements contrôlés, jamais modification silencieuse d'une facture.

### 5.4 Relances et exploitation

- `saas_dunning_actions`
  - échéance ;
  - canal ;
  - modèle ;
  - tentative ;
  - résultat.
- `saas_commercial_overrides`
  - prolongation, remise, grâce exceptionnelle ;
  - approbateur ;
  - motif ;
  - début/fin.
- `saas_provider_accounts`
  - fournisseur actif ;
  - environnement sandbox/live ;
  - capacités ;
  - aucun secret en clair dans PostgreSQL.

## 6. Catalogue initial proposé

### Modules vendables

- `CORE_SCHOOL`
- `FINANCE`
- `ENROLLMENT`
- `RECOVERY`
- `REPORTS`
- `PERSONNEL`
- `DOCUMENTS`
- `ACADEMIC`
- `GRADES`
- `REPORT_CARDS`
- `PARENT_PORTAL`
- `COMMUNICATIONS`
- `ADVANCED_ANALYTICS`
- `MULTI_SCHOOL`

Les modules non encore livrés restent `DRAFT` et ne peuvent pas être vendus.

### Plans initiaux

- `FINANCE` ;
- `GESTION` ;
- `SCHOOL_COMPLETE` (non vendable avant certification pédagogique) ;
- `PREMIUM` (non vendable avant portail parent) ;
- `CUSTOM` pour une offre négociée.

Les prix restent des données administrables et versionnées, pas des constantes du code.

## 7. API cible

### 7.1 Atelier Pro / Volcano Tech

- `GET /api/v1/platform/billing/plans`
- `POST /api/v1/platform/billing/plans`
- `POST /api/v1/platform/billing/plans/{id}/publish`
- `GET /api/v1/platform/billing/subscriptions`
- `GET /api/v1/platform/billing/schools/{school_id}`
- `POST /api/v1/platform/billing/schools/{school_id}/subscribe`
- `POST /api/v1/platform/billing/subscriptions/{id}/change-plan`
- `POST /api/v1/platform/billing/subscriptions/{id}/grant-grace`
- `POST /api/v1/platform/billing/subscriptions/{id}/cancel`
- `POST /api/v1/platform/billing/invoices/{id}/record-payment`
- `POST /api/v1/platform/billing/invoices/{id}/void`
- `GET /api/v1/platform/billing/dashboard`

Chaque mutation requiert idempotence, permission, audit et motif selon le risque.

### 7.2 Espace école

- `GET /api/v1/subscription/current`
- `GET /api/v1/subscription/modules`
- `GET /api/v1/subscription/invoices`
- `GET /api/v1/subscription/invoices/{id}`
- `GET /api/v1/subscription/invoices/{id}/document`
- `POST /api/v1/subscription/invoices/{id}/checkout`
- `GET /api/v1/subscription/payments/{id}`
- `POST /api/v1/subscription/cancel-renewal`

Une école ne voit que son contrat et ses documents.

### 7.3 Prestataires

- `POST /api/v1/webhooks/payments/{provider}`

Cette route n'utilise pas un JWT utilisateur. Elle exige la signature du prestataire,
une protection anti-rejeu et un identifiant d'événement unique.

## 8. Permissions RBAC

### Plateforme

- `platform.billing.read`
- `platform.billing.plans.manage`
- `platform.billing.subscriptions.manage`
- `platform.billing.invoices.manage`
- `platform.billing.payments.reconcile`
- `platform.billing.overrides.grant`
- `platform.billing.export`

### École

- `subscription.read`
- `subscription.invoices.read`
- `subscription.payments.initiate`
- `subscription.renewal.cancel`

Les droits sensibles restent réservés au Manager Système et exigent MFA récente.

## 9. Moteur d'accès aux modules

Une décision d'accès doit satisfaire simultanément :

1. école techniquement active ;
2. abonnement commercial autorisant l'usage ;
3. entitlement actif pour le module ;
4. rôle et capacité de l'utilisateur ;
5. périmètre métier autorisé ;
6. éventuelle feature flag de déploiement.

Le backend applique cette décision. Le frontend consomme une projection signée/relue
depuis le backend et adapte sa navigation.

### Mode limité

Toujours accessibles :

- connexion des responsables autorisés ;
- page abonnement ;
- factures et reçus ;
- paiement ;
- support ;
- export/restauration réglementaire défini par la politique ;
- changement de mot de passe et sécurité.

Bloqués progressivement : nouvelles écritures métier, nouveaux documents et actions
payantes. Les lectures historiques sensibles suivent une politique explicite.

## 10. Moteur d'échéance et relance

Tâche planifiée quotidienne, avec verrou distribué et traitement idempotent :

1. créer les factures à venir ;
2. notifier à J-7 et J-3 ;
3. marquer `PAST_DUE` à l'échéance ;
4. entrer en `GRACE` selon le contrat ;
5. relancer à J+1, J+3 et J+7 ;
6. passer en `LIMITED` à la fin de grâce ;
7. suspendre seulement selon la politique approuvée ;
8. réactiver immédiatement après paiement intégral ;
9. produire les événements d'audit et métriques.

Le moteur ne dépend pas de l'heure locale du serveur : les échéances utilisent la
timezone contractuelle de l'école, par défaut `Africa/Lubumbashi`.

## 11. Architecture des paiements

Interface `PaymentProviderPort` :

- `create_checkout()` ;
- `get_payment_status()` ;
- `verify_webhook()` ;
- `refund()` lorsque disponible ;
- `capabilities()` ;
- `health()`.

Adaptateurs successifs :

1. `ManualPaymentAdapter` pour dépôt/virement contrôlé ;
2. `SandboxPaymentAdapter` pour certification complète ;
3. premier prestataire RDC retenu ;
4. second prestataire de secours si le volume le justifie.

Le navigateur ne décide jamais qu'un paiement a réussi. Seul un webhook vérifié ou
une vérification serveur-à-serveur peut confirmer le paiement.

## 12. Interfaces utilisateur

### Cockpit Volcano Tech

- revenu mensuel récurrent ;
- revenu annuel récurrent ;
- écoles actives, essai, grâce, limitées et suspendues ;
- échéances des 7/30 prochains jours ;
- factures impayées ;
- paiements à rapprocher ;
- modules vendus ;
- historique et export.

### Fiche commerciale d'une école

- plan actuel ;
- modules ;
- prix contractuel ;
- cycle ;
- prochaine échéance ;
- factures/paiements ;
- événements ;
- changement de plan ;
- prolongation motivée ;
- lien de paiement.

### Espace abonnement de l'école

- offre actuelle ;
- modules inclus ;
- prochaine échéance ;
- facture en attente ;
- bouton de paiement ;
- historique ;
- reçus ;
- état clair et jours de grâce restants.

Les trois interfaces sont mobile-first et utilisables avec connexion instable.

## 13. Notifications

Réutiliser les e-mails, notifications internes et push déjà opérationnels :

- facture émise ;
- échéance proche ;
- paiement reçu ;
- paiement échoué ;
- entrée en grâce ;
- limitation imminente ;
- limitation active ;
- réactivation ;
- changement de plan.

Destinataires configurables : promoteur, gestionnaire, responsable financier et
administrateur principal. Aucun numéro ou destinataire n'est codé en dur.

## 14. Sécurité et conformité

- secrets prestataires dans les secrets de production ;
- signatures HMAC/webhook vérifiées en temps constant ;
- anti-rejeu et événements uniques ;
- rate limiting spécifique ;
- MFA step-up pour remises, annulations, paiements manuels et prolongations ;
- séparation stricte plateforme/tenant ;
- RLS ou transactions plateforme appropriées ;
- journal append-only des événements commerciaux ;
- masquage des téléphones et références sensibles ;
- exports sans secrets ;
- sauvegardes avant migration ;
- politique de conservation documentée.

## 15. Observabilité

Métriques minimales :

- factures créées/échues/payées ;
- taux de succès par prestataire ;
- temps de confirmation ;
- webhooks invalides/dupliqués ;
- abonnements par état ;
- transitions automatiques ;
- erreurs du job d'échéance ;
- montant à rapprocher ;
- MRR et ARR.

Alertes : job non exécuté, webhook en échec répété, divergence facture/paiement,
prestataire indisponible, volume inhabituel de suspensions.

## 16. Migration des écoles actuelles

1. recenser les écoles de production ;
2. créer le catalogue initial sans l'activer ;
3. créer pour chaque école un abonnement `ACTIVE` migré ;
4. attribuer les modules correspondant aux fonctions déjà disponibles ;
5. fixer une première échéance explicitement validée ;
6. ne générer aucune dette rétroactive ;
7. vérifier l'accès de chaque rôle ;
8. activer le moteur en mode observation ;
9. comparer les décisions pendant au moins sept jours ;
10. activer les relances, puis la limitation dans un second déploiement.

## 17. Découpage d'implémentation

### Phase S0 — Décisions et contrats

- prix et cycles ;
- modules vendables ;
- durée d'essai ;
- grâce ;
- règle de limitation ;
- destinataires ;
- conditions générales ;
- choix du premier prestataire à tester.

**Sortie :** ADR, contrats API, diagramme d'état, matrice RBAC.

### Phase S1 — Domaine et PostgreSQL

- migrations et rollback ;
- agrégats/objets valeur ;
- transitions ;
- repository ports ;
- tests du domaine ;
- seed catalogue non destructif.

**Gate :** migrations aller/retour, invariants et isolation validés.

### Phase S2 — API Atelier Pro

- plans ;
- souscriptions ;
- entitlements ;
- factures ;
- paiements manuels ;
- audit/RBAC/MFA/idempotence.

**Gate :** tests API et PostgreSQL, aucune exposition inter-école.

### Phase S3 — API et UI école

- état de l'abonnement ;
- factures ;
- reçus ;
- paiement ;
- mode limité ;
- projection des modules.

**Gate :** mobile, accessibilité, offline de consultation et rôles.

### Phase S4 — Automatisation

- génération périodique ;
- échéances ;
- relances ;
- grâce ;
- limitation ;
- réactivation ;
- notifications existantes.

**Gate :** horloge simulée, concurrence, reprise après panne et idempotence.

### Phase S5 — Paiement sandbox

- port prestataire ;
- checkout ;
- webhook ;
- statuts ;
- rapprochement ;
- échecs, doublons et retards.

**Gate :** campagne sandbox complète, secrets absents du dépôt.

### Phase S6 — Cockpit et rapports commerciaux

- MRR/ARR ;
- échéances ;
- impayés ;
- rapprochement ;
- exports ;
- alertes.

**Gate :** chiffres réconciliés avec les factures et paiements sources.

### Phase S7 — Pilote puis production

- une école interne/pilote ;
- mode observation ;
- paiement réel de faible montant ;
- validation du reçu et du règlement ;
- test de grâce ;
- test de réactivation ;
- déploiement progressif ;
- runbook support et incident.

**Gate :** aucun blocage des workflows école existants.

## 18. Stratégie de déploiement

Feature flags séparés :

- `saas_catalog_enabled` ;
- `saas_billing_enabled` ;
- `saas_school_portal_enabled` ;
- `saas_dunning_enabled` ;
- `saas_enforcement_enabled` ;
- `saas_payment_provider_enabled`.

Ordre : catalogue → lecture → facturation → paiement → relances → limitation.
L'enforcement est le dernier drapeau activé et possède un arrêt d'urgence.

## 19. Tests obligatoires

### Domaine

- toutes les transitions ;
- calcul des périodes ;
- devises/arrondis ;
- remises/crédits ;
- grâce ;
- changement de plan ;
- annulation et renouvellement.

### PostgreSQL

- contraintes ;
- unicité ;
- concurrence ;
- isolation ;
- migrations et rollback ;
- reprise idempotente.

### API et sécurité

- RBAC ;
- MFA ;
- tenant isolation ;
- IDOR ;
- idempotency ;
- webhooks signés ;
- anti-rejeu ;
- rate limits.

### Paiements

- succès ;
- refus ;
- timeout ;
- webhook avant/après retour utilisateur ;
- webhook dupliqué ;
- montant/devise incorrects ;
- remboursement ;
- rapprochement manuel contrôlé.

### E2E

- souscription → facture → paiement → activation ;
- échéance → grâce → paiement → réactivation ;
- changement de plan ;
- module non acheté refusé côté backend ;
- école existante migrée sans interruption ;
- mobile 360/390 px ;
- connexion instable.

## 20. Critères de clôture

Le moteur est terminé lorsque :

1. une école peut souscrire sans intervention SQL ;
2. une facture exacte est générée et téléchargeable ;
3. un paiement confirmé ne peut être compté deux fois ;
4. l'abonnement se prolonge automatiquement ;
5. les modules sont réellement gouvernés côté backend ;
6. les relances utilisent les canaux existants ;
7. la grâce et le mode limité sont prédictibles ;
8. une régularisation réactive l'école automatiquement ;
9. les données restent intactes après suspension ;
10. le cockpit permet de suivre les revenus et impayés ;
11. sauvegarde, monitoring, audit et runbook sont validés ;
12. le pilote réel est certifié avant généralisation.

## 21. Estimation réaliste

| Bloc | Durée indicative |
| --- | ---: |
| S0 contrats | 1 à 2 jours |
| S1 domaine et base | 3 à 5 jours |
| S2 API plateforme | 3 à 5 jours |
| S3 portail école | 3 à 5 jours |
| S4 automatisation | 3 à 4 jours |
| S5 prestataire sandbox | 3 à 5 jours, hors délai KYC |
| S6 cockpit | 2 à 4 jours |
| S7 certification/pilote | 5 à 7 jours |

Total technique : environ quatre à six semaines avec certification sérieuse. Le KYC
et l'activation live du prestataire sont des dépendances externes et peuvent continuer
en parallèle ; le paiement manuel et les liens peuvent permettre le lancement initial.

## 22. Décisions propriétaire à figer au début de S0

1. prix de lancement et devise contractuelle ;
2. mensualité, trimestre, année ou les trois ;
3. durée d'essai ;
4. nombre de jours de grâce ;
5. moment du passage en mode limité ;
6. modules vendables au lancement ;
7. politique de remboursement ;
8. personnes autorisées à accorder une remise/prolongation ;
9. premier prestataire sandbox ;
10. identité légale et coordonnées figurant sur les factures Volcano Tech.

Les valeurs proposées pour le pilote sont : cycles mensuel/trimestriel/annuel,
14 jours d'essai, 10 jours de grâce, limitation progressive, aucune suppression,
prix en USD avec affichage indicatif CDF et `FINANCE` comme premier plan vendable.
