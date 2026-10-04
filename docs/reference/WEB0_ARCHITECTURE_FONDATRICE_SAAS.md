# WEB-0 — Architecture fondatrice EduSync SaaS multi-école

**Cible :** EduSync Web/PWA multi-école, hébergé sur VPS distant, offline-first, DDD + Clean Architecture + Hexagonal Architecture.

## 1. Architecture cible

```text
Navigateur / PWA
  React + TypeScript
  ├─ App Shell cache
  ├─ LocalStorePort (IndexedDB au Web)
  ├─ Query cache
  ├─ Outbox locale
  └─ Sync Engine
          │ HTTPS
          ▼
Reverse proxy (Caddy/Nginx)
          │
          ▼
FastAPI — monolithe modulaire
  ├─ Platform / Atelier Pro
  ├─ IAM / RBAC
  ├─ School Configuration
  ├─ Schooling
  ├─ Personnel
  ├─ Finance
  ├─ Cash
  ├─ Documents
  ├─ Imports
  ├─ Audit
  ├─ Notifications
  ├─ Sync
  └─ Intendance (phase ultérieure)
          │
  ┌───────┼──────────┐
  ▼       ▼          ▼
PostgreSQL Redis   Object Storage
source vérité cache/queue PDF/Excel/pièces
          │
          ▼
Worker asynchrone
notifications, documents lourds, imports, tâches planifiées
```

## 2. Choix structurant : monolithe modulaire

Le premier déploiement VPS doit être un **monolithe modulaire**, pas un ensemble de microservices.

Raisons :

- domaines fortement transactionnels ;
- finance et caisse nécessitent des transactions fortes ;
- équipe de développement réduite ;
- déploiement/monitoring simples ;
- DDD/Hexagonal n’exigent pas les microservices ;
- les bounded contexts pourront être séparés plus tard si une charge réelle le justifie.

Chaque module doit cependant être isolé par interfaces/ports et ne pas importer directement les tables d’un autre domaine hors contrats explicitement autorisés.

## 3. Bounded contexts

### 3.1 Platform / Atelier Pro

Responsabilités :

- créer une école ;
- suspendre/réactiver une école ;
- créer l’administrateur initial ;
- branding initial ;
- feature flags ;
- statut de déploiement ;
- quotas éventuels ;
- état sauvegarde/santé ;
- audit plateforme.

**Interdiction :** l’Atelier Pro ne doit pas exposer automatiquement les données financières détaillées d’une école. Tout accès support futur doit être explicite, temporaire, justifié et audité.

### 3.2 Identity & Access Management

- utilisateurs plateforme ;
- memberships d’école ;
- rôles ;
- permissions ;
- rôle(s) d’un membre ;
- sessions/appareils ;
- révocation ;
- sécurité.

### 3.3 School Configuration

- identité école ;
- années ;
- sections/options/classes ;
- politiques ;
- tarifs ;
- contributions ;
- articles ;
- documents ;
- préférences.

### 3.4 Schooling

- familles ;
- responsables ;
- élèves ;
- inscriptions ;
- réinscriptions ;
- affectations classe ;
- mouvements ;
- avantages ;
- effectifs/read models.

### 3.5 Personnel

- agents ;
- fonctions ;
- affectations ;
- statut ;
- liens avec les comptes ;
- liens enfant-personnel.

### 3.6 Finance

- charges ;
- politiques de frais ;
- décisions financières ;
- responsabilités ;
- paiements ;
- allocations ;
- reçus ;
- plans anticipés ;
- fonds anticipés ;
- règlements hors caisse ;
- vues financières.

### 3.7 Cash

- journées de caisse ;
- entrées/sorties ;
- dépenses ;
- clôture/réouverture ;
- snapshots ;
- journal.

### 3.8 Documents

- génération ;
- historique ;
- stockage ;
- impression côté client ;
- réimpression ;
- templates ;
- conservation.

### 3.9 Imports

- upload ;
- staging ;
- mapping ;
- validation ;
- simulation ;
- lot ;
- erreurs ;
- idempotence ;
- finalisation.

### 3.10 Audit

- audit plateforme ;
- audit école ;
- audit sécurité ;
- audit sync ;
- recherches ;
- export audit.

### 3.11 Notifications

- notifications in-app ;
- préférences ;
- Web Push ;
- email/SMS via adapters futurs ;
- statut lu/non lu ;
- événements métier.

### 3.12 Sync

- appareils ;
- cursors ;
- outbox/inbox ;
- idempotence ;
- change feed ;
- conflits ;
- politiques offline.

### 3.13 Intendance — extension future déjà réservée

- besoins ;
- fournisseurs ;
- achats ;
- commandes ;
- réceptions ;
- stocks ;
- sorties ;
- affectations ;
- patrimoine ;
- inventaires ;
- maintenance ;
- pièces justificatives ;
- workflow de validation.

## 4. Clean + Hexagonal : structure backend

Proposition de structure :

```text
backend/
  src/edusync/
    shared/
      domain/
      application/
      ports/
      infrastructure/
    modules/
      platform/
        domain/
        application/
        ports/
        adapters/
        api/
      iam/
      configuration/
      schooling/
      personnel/
      finance/
      cash/
      documents/
      imports/
      audit/
      notifications/
      sync/
      intendance/
    bootstrap/
      settings.py
      container.py
      app.py
```

Règles de dépendance :

```text
Domain        -> aucune dépendance framework
Application   -> Domain + Ports
Adapters      -> Ports + frameworks
API           -> Application
Infrastructure-> Adapters
```

Les entités du domaine ne doivent importer ni FastAPI, ni SQLAlchemy, ni Redis, ni React.

## 5. Structure frontend

```text
web/
  src/
    app/
      router/
      providers/
      shell/
    modules/
      platform/
      configuration/
      schooling/
      personnel/
      finance/
      cash/
      documents/
      audit/
      notifications/
      intendance/
    shared/
      ui/
      icons/
      permissions/
      api/
      offline/
      sync/
      formatting/
    pwa/
      service-worker/
      manifest/
```

Technologies recommandées :

- React + TypeScript ;
- Vite ;
- TanStack Query pour cache réseau/mémoire ;
- React Router ;
- Zod pour validation de contrats côté client ;
- Dexie/IndexedDB comme premier adapter `LocalStorePort` Web ;
- Service Worker/Workbox ou équivalent ;
- design system maison reproduisant l’UI EduSync actuelle.

Le choix final des bibliothèques reste remplaçable derrière les ports.

## 6. Multi-tenancy PostgreSQL

### 6.1 Stratégie retenue

**Une base PostgreSQL partagée + schéma partagé + `school_id` sur toutes les données métier d’école**, renforcé par Row Level Security (RLS).

Avantages :

- exploitation simple sur un VPS ;
- migrations uniques ;
- coût faible ;
- requêtes/admin plus simples ;
- évolutif jusqu’à un nombre important d’écoles ;
- possibilité de sortir une grosse école vers une base dédiée plus tard si nécessaire.

### 6.2 Tables plateforme

Exemples :

- `platform_users`
- `schools`
- `school_memberships`
- `roles`
- `permissions`
- `role_permissions`
- `membership_roles`
- `devices`
- `feature_flags`
- `platform_audit_events`

### 6.3 Tables métier

Toutes les tables d’école reçoivent `school_id UUID NOT NULL`.

Les contraintes globales actuelles doivent devenir tenant-aware :

- `UNIQUE (school_id, academic_year_label)` ;
- `UNIQUE (school_id, matricule)` ;
- `UNIQUE (school_id, family_code)` ;
- `UNIQUE (school_id, receipt_no)` ;
- séquences de reçu par école et éventuellement terminal/caisse selon politique offline.

### 6.4 RLS

Le backend fixe le tenant courant dans la transaction. RLS constitue une défense supplémentaire aux filtres applicatifs.

**Test obligatoire :** aucune API d’école A ne doit pouvoir lire/écrire un ID appartenant à école B, même en devinant l’UUID.

## 7. Argent et types PostgreSQL

L’actuel SQLite utilise des `REAL`. Le Web doit utiliser :

- `NUMERIC(18,2)` pour montants usuels ;
- `Decimal` côté Python ;
- code devise explicite (`CDF`, `USD`) ;
- jamais `float` pour calcul métier financier.

La migration doit comparer tous les agrégats avant/après par :

`school + academic_year + currency + fee + student`.

## 8. RBAC permission-based

### 8.1 Principe

Un rôle est un **template de permissions**, pas une autorisation codée en dur.

Exemples de permissions :

```text
students.read
students.create
students.update
students.lifecycle.change
families.manage
enrollments.create
enrollments.reenroll
finance.read
payments.create
payments.reverse
cash.open
cash.close
cash.reopen
reports.export
staff.manage
users.manage
settings.manage
inventory.read
inventory.receive
purchases.create
purchases.approve
audit.read
```

### 8.2 Rôles initiaux proposés

- Administrateur école
- Direction
- Préfet / Responsable scolaire
- Secrétariat
- Caissier
- Intendant
- Enseignant (si activé plus tard)

Chaque école peut recevoir des rôles système par défaut. Les personnalisations futures doivent être encadrées pour ne pas rendre les permissions incohérentes.

### 8.3 Atelier Pro

Le super-admin plateforme n’est pas un `ADMIN` d’école. Ce sont deux espaces de pouvoir distincts.

## 9. Audit industrialisé

### 9.1 Table cible

`audit_events` :

```text
id UUID
school_id UUID NULL       # NULL pour événement plateforme
occurred_at TIMESTAMPTZ
actor_user_id UUID NULL
actor_membership_id UUID NULL
actor_role_snapshot JSONB
action TEXT
entity_type TEXT
entity_id UUID/TEXT NULL
result TEXT
source TEXT               # WEB/OFFLINE/SYNC/SYSTEM/IMPORT
reason TEXT NULL
old_json JSONB NULL
new_json JSONB NULL
device_id UUID NULL
request_id UUID NULL
correlation_id UUID NULL
causation_id UUID NULL
idempotency_key TEXT NULL
metadata JSONB
```

### 9.2 Règles

- append-only ;
- pas de secrets/PIN/tokens dans old/new ;
- mutation métier critique + audit atomiques ;
- les refus d’autorisation sensibles peuvent également être audités ;
- filtre par école, utilisateur, action, domaine, période, résultat ;
- export audit ;
- conservation configurable ;
- opérations Atelier Pro séparées des opérations d’école.

## 10. Notifications

### 10.1 Architecture

```text
Use case métier
  -> Domain Event
  -> Transactional Outbox
  -> Worker
  -> Notification policy
  -> notifications table
  -> WebSocket/SSE / Web Push / Email adapter
```

### 10.2 Premiers événements utiles

- paiement enregistré ;
- reçu à réimprimer ;
- caisse non clôturée ;
- dette/relance selon politique ;
- nouvelle inscription ;
- stock faible ;
- demande d’achat à approuver ;
- sauvegarde en échec ;
- import terminé/partiellement rejeté.

Les notifications doivent être tenant-scoped et permission-aware.

## 11. Cache

### 11.1 Côté client

- Service Worker : assets/app shell ;
- TanStack Query : cache mémoire réseau ;
- LocalStore : données offline autorisées ;
- invalidation sur événements/synchronisation.

### 11.2 Côté serveur

Redis peut servir à :

- cache de read models coûteux ;
- rate limiting ;
- coordination de tâches ;
- notifications temps réel ;
- verrous courts/idempotency si nécessaire.

**Interdiction :** Redis n’est jamais la source de vérité des paiements, allocations, caisse ou audit.

Clés toujours préfixées par tenant :

`edusync:{school_id}:...`

## 12. Offline-first

### 12.1 Principe

Offline-first ne signifie pas « tout est modifiable sans connexion et on fusionne plus tard ».

Chaque commande reçoit une politique :

- `OFFLINE_SAFE`
- `OFFLINE_WITH_CONFIRMATION`
- `ONLINE_REQUIRED`
- `OFFLINE_FINANCE_CONTROLLED`

### 12.2 Client Outbox

Une commande offline stocke :

```text
command_id UUID
school_id
user_id/membership_id
device_id
command_type
aggregate_id
base_version
payload
created_at_device
idempotency_key
status
retry_count
```

### 12.3 Server Inbox

Le serveur garde l’idempotency key/command id afin qu’un retry réseau ne crée pas deux opérations.

### 12.4 Change feed

Le client tire les modifications après un curseur serveur. Les suppressions logiques utilisent des tombstones lorsque nécessaires.

### 12.5 Conflits

Pas de règle générique « dernier gagne » pour le métier.

Exemples :

- modification de téléphone : résolution contrôlée ;
- inscription annuelle unique : invariant serveur ;
- changement de classe : commande métier ;
- paiement : idempotence stricte ;
- clôture de caisse : serveur autoritaire.

## 13. Finance offline — protocole séparé

La finance est le domaine le plus critique.

Première release recommandée :

- consultation offline : oui ;
- préparation de panier/draft : oui ;
- paiement final offline : uniquement après activation d’un protocole contrôlé.

Pour autoriser un vrai encaissement hors ligne plus tard :

- terminal/device enregistré ;
- session de caisse locale autorisée ;
- bloc de numéros/reçus réservé ou identifiant global UUID + numéro final serveur selon doctrine retenue ;
- snapshot des charges synchronisé ;
- idempotency key serveur ;
- aucune allocation au-delà du snapshot autorisé ;
- journal local append-only ;
- synchronisation obligatoire avant nouvelle clôture globale ;
- détection/traitement explicite des conflits.

**Gate :** aucun paiement offline en production avant certification dédiée multi-appareils.

## 14. Documents et exports

### 14.1 Stratégie

Conserver le moteur Python actuel derrière :

`DocumentGeneratorPort`.

FastAPI demande un document ; un worker peut le générer ; l’historique est enregistré ; le fichier est stocké via `ObjectStoragePort`.

### 14.2 Stockage

Cible : stockage S3-compatible ou service équivalent, séparé de PostgreSQL.

Chemin logique :

`schools/{school_id}/{academic_year}/{category}/{period}/...`

### 14.3 Impression

Le Web télécharge/ouvre le PDF et utilise l’impression navigateur. Pour un futur client Desktop Tauri, un adapter d’impression directe pourra être ajouté sans changer le domaine Documents.

## 15. Migration SQLite v17 → PostgreSQL

### 15.1 Étapes

1. sauvegarde SQLite source + SHA-256 ;
2. `integrity_check` + `foreign_key_check` ;
3. créer l’école cible dans Atelier Pro ;
4. injecter `school_id` ;
5. conserver les IDs existants quand possible ;
6. convertir montants vers Decimal/NUMERIC ;
7. migrer référentiels ;
8. familles/élèves/personnel ;
9. inscriptions/charges ;
10. paiements/allocations/reçus/caisse ;
11. décisions/avances/historique ;
12. documents ;
13. audit ;
14. rapprochement des compteurs ;
15. rapprochement financier par devise ;
16. golden tests ;
17. rapport de migration.

### 15.2 Validation financière

Pour chaque année/devise :

```text
Σ charges nettes
Σ paiements valides
Σ allocations
Σ fonds anticipés reçus/disponibles/imputés
Σ règlements hors caisse
Σ caisse entrées/sorties
nombre de reçus
numéros min/max
```

Aucune bascule si les écarts ne sont pas expliqués.

## 16. Déploiement VPS

### 16.1 Docker Compose initial

```text
caddy/nginx
web
api
worker
postgres
redis
object-storage (ou adapter externe)
backup-agent
```

### 16.2 Environnements

- local dev ;
- staging séparé ;
- production.

Jamais de migration de schéma expérimentale directement sur production.

### 16.3 Sauvegardes

- dump PostgreSQL automatique ;
- sauvegarde volumes/documents ;
- copie hors VPS ;
- rétention ;
- chiffrement ;
- test périodique de restauration.

## 17. Observabilité

À prévoir dès WEB-0 :

- logs structurés JSON ;
- request/correlation ID ;
- métriques API ;
- santé DB/Redis/worker ;
- erreurs applicatives ;
- suivi jobs ;
- dashboard technique Atelier Pro limité aux métadonnées opérationnelles.

## 18. Sécurité

- HTTPS obligatoire ;
- mots de passe Argon2id ;
- tokens/sessions courts et révocables ;
- cookies sécurisés si auth Web par cookie ;
- CSRF selon mécanisme d’auth ;
- rate limiting ;
- RLS ;
- validation stricte de tenant ;
- permissions deny-by-default ;
- MFA recommandé pour Atelier Pro ;
- secrets hors repository ;
- aucune donnée sensible dans logs/audit non nécessaire.

## 19. Roadmap technique

### WEB-0A — Fondation repository

- monorepo ;
- conventions ;
- ADR ;
- lint/typecheck/tests ;
- Docker dev ;
- CI.

### WEB-0B — Platform + Tenant

- PostgreSQL ;
- Alembic ;
- schools ;
- memberships ;
- tenant context ;
- RLS ;
- Atelier Pro minimal.

### WEB-0C — IAM/RBAC

- login ;
- sessions ;
- permissions ;
- rôles par défaut ;
- audit de sécurité.

### WEB-0D — Audit/Outbox/Notifications foundation

- audit_events ;
- outbox ;
- worker ;
- notifications in-app foundation.

### WEB-0E — Web/PWA shell

- design system ;
- navigation ;
- school context ;
- offline shell ;
- LocalStorePort ;
- Sync contracts.

### WEB-0F — Migration harness

- extracteur SQLite ;
- mapping PostgreSQL ;
- réconciliation ;
- golden baseline.

**Aucun portage du domaine Finance avant WEB-0A..F certifiés.**

## 20. Critères de certification WEB-0 Fondation

WEB-0 Fondation est PASS uniquement si :

1. une école A et une école B peuvent être créées ;
2. isolation API A/B prouvée ;
3. RLS A/B prouvée ;
4. super-admin plateforme distinct de l’admin école ;
5. RBAC deny-by-default ;
6. audit d’une mutation école contient tenant/actor/correlation ;
7. audit est append-only pour le rôle applicatif ;
8. notification in-app de test passe par outbox/worker ;
9. cache Redis est tenant-scoped ;
10. PWA démarre et recharge son shell offline ;
11. une commande non financière idempotente peut être rejouée sans doublon ;
12. harness de migration lit une copie SQLite v17 sans l’altérer ;
13. golden exports sont inventoriés ;
14. CI passe ;
15. stack Docker démarre sur staging VPS.

**VERDICT CIBLE : WEB-0 FONDATION SAAS MULTI-ÉCOLE CERTIFIÉE — TENANCY, IAM/RBAC, AUDIT, CACHE, PWA, SYNC FOUNDATION, MIGRATION HARNESS ET DÉPLOIEMENT VPS VALIDÉS.**
