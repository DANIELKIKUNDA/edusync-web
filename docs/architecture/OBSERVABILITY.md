# Observabilité de la plateforme EduSync (lot 2026-10)

Ce document décrit ce qui est **réellement en place**, ce qui est **différé par conception** (DEFERRED_BY_DESIGN) et
comment diagnostiquer un incident depuis l'écran « État du service ».

## 1. En place

| Signal | Source | Conservation | Où le voir |
|---|---|---|---|
| Journal structuré (JSON) de chaque requête : `correlation_id`, chemin, méthode, statut | `shared/infrastructure/observability.py` (structlog) | journaux du conteneur API | `docker compose logs api` |
| Exception non gérée : ligne `http_unhandled_error` + trace complète **côté serveur uniquement** | idem | journaux du conteneur API | idem |
| Trafic, latence (tranches), erreurs 5xx, refus 4xx par minute et par heure | `shared/infrastructure/signals.py` (Redis) | 26 h par minute, 8 jours par heure | État du service → Serveur d'application |
| Erreurs 5xx regroupées (méthode + modèle de route + code + type), première/dernière occurrence, 20 dernières occurrences avec `correlation_id` | idem | 7 jours | État du service → Erreurs serveur |
| Battements des workers (diffusion, SMS) | `shared/infrastructure/heartbeat.py` | 10 min | État du service → workers |
| Files (outbox, SMS) : profondeur, âge du plus ancien, quarantaine | PostgreSQL | temps réel | État du service → workers |
| Sauvegarde : dernière exécution, retard (> 26 h), restauration vérifiée, copie hors site | fichier d'état du service de sauvegarde | dernier rapport | État du service → Sauvegarde |
| Fournisseurs de messagerie : état de configuration, dernier succès, dernier échec, dernier code d'erreur | `channel_status` + `communication_deliveries` | 7 jours | État du service → Fournisseurs |
| Saturation : connexions base utilisées / capacité du pool de l'API | SQLAlchemy | temps réel | État du service → Serveur d'application |
| Alertes dérivées (chaque composant non opérationnel, avec sa raison) | `platform_health/api/router.py` | temps réel | bandeau « Incident en cours / À surveiller » |
| Incidents « Hors service » + e-mail après 5 min et à la résolution (Managers Système + adresses d'astreinte) | `platform_health/application/alerts.py`, table `platform_incidents` | 2 ans (proposé) | État du service → Incidents et alertes |
| Sonde de disponibilité externe (toutes les 5 min, hors VPS) + ticket automatique | `.github/workflows/uptime.yml` | historique GitHub Actions | onglet Actions, tickets « Disponibilité » |

### Règles techniques (documentées, non métier)

* **État courant ≠ historique.** Une erreur est « en cours » pendant `ACTIVE_WINDOW_S` = 300 s (5 min) après sa
  dernière occurrence. Seules les erreurs en cours dégradent l'état. Les compteurs 1 h / 24 h / 7 j sont de
  l'historique : ils informent et ne dégradent jamais l'état courant. Le retour à « Opérationnel » est automatique.
* **Erreurs attendues.** Les refus 4xx (validation, mauvais mot de passe, 403, 404, format de fichier refusé) sont
  comptés à part (`client_refusals`) et ne dégradent jamais.
* **Erreurs inattendues.** Tout statut ≥ 500, y compris les dépendances indisponibles converties en 503 (base de
  données, stockage), étiquetées par leur type (« Base de données indisponible (OperationalError) »).
* **Latence.** Donnée par tranche (≤ 50, 100, 250, 500 ms, 1 s, 2,5 s, au-delà) : le p95 affiché est la borne de la
  tranche, jamais un chiffre faussement précis. L'API est « Dégradée » si le p95 sur 5 min dépasse 2,5 s.
* **Fournisseur simulé.** Jamais « certifié » ni « opérationnel » : il est « Non configuré » pour l'envoi réel.
* **Expurgation.** Seul le modèle de route est conservé (`/api/v1/platform/schools/{school_id}`), jamais le chemin
  concret. Le message d'erreur est réduit à sa première ligne, sans SQL, adresse, chemin, e-mail, identifiant, valeur
  entre guillemets, nombre long ni secret (`password=…`, `token=…`, `Bearer …`). Aucun utilisateur, aucune charge utile.
* **Sans impact sur les requêtes.** L'écriture des signaux est confiée à un thread par le middleware ; une panne de
  Redis n'empêche aucune réponse (et l'écran affiche « Compteur indisponible », jamais « Opérationnel »).

## 2. Diagnostiquer une erreur

1. État du service → **Erreurs serveur** : l'état courant, puis la liste des groupes (fenêtre 1 h / 24 h / 7 j).
2. Ouvrir un groupe : type, message expurgé, route, code, première et dernière occurrence, impact (part des erreurs
   des 24 h), 20 dernières occurrences avec leur **référence** (`correlation_id`).
3. La même référence est renvoyée à l'utilisateur (« Une erreur inattendue est survenue. Référence : xxxxxxxx ») et
   inscrite dans les journaux du serveur. Pour la trace complète, sur le serveur :
   `docker compose logs api | grep <correlation_id>`.
4. Le journal d'audit n'est pas lié : une erreur serveur n'est pas une action métier journalisée (NOT_AVAILABLE).

## 3. Différé par conception (DEFERRED_BY_DESIGN)

| Brique | Statut | Raison | Prérequis pour l'activer |
|---|---|---|---|
| OpenTelemetry (traces distribuées) | DEFERRED_BY_DESIGN | monolithe modulaire unique, `correlation_id` de bout en bout suffit au diagnostic actuel | collecteur OTLP hébergé, budget mémoire VPS |
| Prometheus (métriques) | DEFERRED_BY_DESIGN | les signaux d'or sont déjà mesurés (Redis) et visibles dans l'application | serveur Prometheus, endpoint `/metrics` protégé |
| Grafana (tableaux) | DEFERRED_BY_DESIGN | l'écran « État du service » couvre le besoin d'exploitation actuel | Prometheus/Loki en place |
| Loki (journaux centralisés) | DEFERRED_BY_DESIGN | un seul VPS : `docker compose logs` + `correlation_id` | stockage des journaux, rétention décidée par le propriétaire |
| Alertes par SMS ou messagerie instantanée | DEFERRED_BY_DESIGN | l'e-mail (application) et le ticket GitHub (sonde externe) couvrent l'astreinte actuelle | fournisseur et coût à décider |
| Disponibilité sur la durée (SLA), maintenances planifiées | NOT_AVAILABLE | aucune donnée conservée à ce jour | — |

## 4. Changement d'espace (lien avec l'observabilité)

* `CONTEXT_SWITCHED` et `CONTEXT_SWITCH_REFUSED` sont journalisés dans l'audit (catégorie Sécurité, `UserSecurity`),
  sans secret ; un refus mentionne l'espace demandé.
* Un espace retiré pendant la session (appartenance terminée, école suspendue, accès plateforme révoqué ou suspendu,
  plus aucun rôle) répond 403 avec l'en-tête `X-EduSync-Space: WITHDRAWN` : l'interface propose les autres espaces
  de l'identité au lieu d'une erreur générique, sans déconnexion.
