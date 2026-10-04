# WEB-0C — Rapport d'implémentation

Date : 2026-09-11  
Cible : EduSync Web multi-école, SaaS sur VPS distant  
Doctrine : DDD + Clean Architecture + Hexagonale + preservation-first

## 1. Objectif

WEB-0C ferme l'écart principal laissé par WEB-0A/WEB-0B : l'Atelier Pro ne doit plus dépendre d'un repository mémoire ni d'un header de développement. Le lot fournit le câblage PostgreSQL/JWT/RBAC/RLS réel, tout en conservant les contrats d'idempotence, concurrence, audit, outbox et offline déjà posés.

## 2. Persistance et isolation multi-école

Les adapters PostgreSQL existent maintenant pour : écoles, utilisateurs, memberships, audit et outbox. Les écoles portent une version d'agrégat et les sauvegardes utilisent un `UPDATE ... WHERE version=:expected RETURNING version` pour la concurrence optimiste.

La migration `0003_g1_live_security.sql` ajoute :

- RLS sur `schools` ;
- `FORCE ROW LEVEL SECURITY` sur les tables tenant ;
- policy plateforme réservée au rôle DB `edusync_platform` ;
- policy tenant liée à `app.current_school_id` ;
- policy utilisateur self-only liée à `app.current_user_id` ;
- isolation de `membership_roles` via son membership ;
- cohérence `scope_key ↔ school_id` du registre d'idempotence.

Les rôles `edusync_tenant` et `edusync_platform` sont `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEROLE`, `NOCREATEDB`, `NOINHERIT`.

## 3. Séparation des secrets

Le rôle `edusync_owner` est exclusivement utilisé par le service one-shot `migrator`. Le conteneur API ne reçoit ni l'URL owner ni le mot de passe bootstrap Atelier Pro. Il ne reçoit que les URLs tenant/platform nécessaires au runtime, Redis et le secret JWT.

Cette séparation est un invariant de déploiement.

## 4. Authentification / autorisation

`POST /api/v1/auth/login` fournit deux scopes : `PLATFORM` et `SCHOOL`.

Les mots de passe utilisent Argon2. Les JWT HS256 sont courts, avec `sub`, `iss`, `aud`, `iat`, `nbf`, `exp`, `jti` et `typ=access`.

Le token n'est pas la source autoritaire des permissions : pour un appel école, le serveur recharge le membership et ses permissions depuis PostgreSQL. Un membership révoqué ou une école suspendue bloque donc immédiatement l'accès. Les versions utilisateur/membership permettent aussi de refuser un jeton devenu obsolète.

Le header historique `X-Platform-Admin: web0a-dev-platform-admin` a été supprimé du frontend et n'accorde plus aucun accès.

## 5. Idempotence

Toute mutation Atelier Pro exige `Idempotency-Key`.

La clé est couplée à : scope, opération et hash canonique du payload. Une même clé :

- même commande réussie → réponse originale rejouée sans nouvel effet ;
- payload/opération différente → HTTP 409 ;
- requête concurrente identique → la contrainte unique PostgreSQL sérialise la propriété logique ;
- échec transactionnel → un retry sûr peut reprendre la même clé, à condition que les effets critiques restent transactionnels/outbox-only.

Audit, écritures métier, outbox et finalisation d'idempotence s'exécutent dans la même transaction PostgreSQL pour les mutations Atelier Pro.

## 6. Concurrence

Les écoles ont un champ `version`. Le repository PostgreSQL utilise un compare-and-swap. Deux transactions parties de la même version ne peuvent pas toutes les deux gagner.

Le hook `FOR UPDATE` du lot WEB-0B est conservé pour le futur portage Finance. Finance devra verrouiller/recalculer les charges dans la même transaction que paiement, allocations, reçu, caisse, audit et outbox.

WEB-0C ne prétend pas encore certifier la concurrence du domaine Finance : ce gate sera exécuté lorsque les agrégats financiers réels seront portés.

## 7. Audit

`audit_events` reste append-only. Le backend persiste désormais les événements d'Atelier Pro avec `school_id`, acteur, action, ancien/nouveau état, source, correlation ID et idempotency key.

La suppression ou modification d'un événement d'audit reste interdite par le trigger DB et par les grants minimaux des rôles applicatifs.

## 8. Cache et offline-first

Le cache Redis est namespacé par scope et TTL borné. Il ne doit servir que des read-models/accélérations ; il n'est jamais une source de vérité financière.

Le Service Worker ne met plus en cache les réponses `/api/`, les requêtes authentifiées ni les ressources cross-origin. L'IndexedDB outbox est scindé par `schoolId`, `userId`, `deviceId`, avec unicité de la clé d'idempotence à l'intérieur du tenant.

Le paiement final offline reste explicitement fail-closed jusqu'au gate Finance Offline.

## 9. Déploiement Docker

`docker-compose.yml` contient PostgreSQL 16, Redis 7, migrator one-shot, backend FastAPI et frontend Nginx/PWA. Le frontend parle à `/api/v1` en same-origin et Nginx reverse-proxy `/api/` vers FastAPI : aucune URL VPS n'est figée dans le bundle frontend.

Le TLS public/Caddy, monitoring et stratégie de sauvegarde VPS seront fermés avant l'exposition Internet.

## 10. Verdict

**WEB-0C CODE FOUNDATION: VALIDATED LOCALLY.**  
**G1 LIVE: READY TO EXECUTE, NOT YET CLAIMED PASS.**

Aucun module métier Desktop n'a été appauvri ou remplacé dans ce lot.
