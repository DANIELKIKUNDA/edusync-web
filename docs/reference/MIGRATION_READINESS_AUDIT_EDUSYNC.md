# MIGRATION_READINESS_AUDIT — EduSync École Offline → Web / Offline-first

**Date d’audit : 2026-09-11**  
**Source auditée : ZIP transmis par l’utilisateur**  
**Mode : lecture seule — aucune modification du code ni des données**

## 1. Verdict exécutif

La migration est **faisable** et le produit actuel constitue une base métier solide. En revanche, EduSync ne doit pas être « converti automatiquement » de PySide6 vers le Web. La bonne stratégie est une **migration par couches** : conserver les règles métier et les comportements certifiés comme référence, extraire une API serveur, remplacer progressivement la couche SQLite locale par une persistance serveur, puis reconstruire l’interface en Web/PWA.

La recommandation principale est une architecture **Web locale + serveur d’école** avant le véritable offline-first distribué : les postes et téléphones ouvrent une PWA dans le navigateur, mais toutes les écritures convergent vers un serveur local de l’école sur le LAN. Ainsi, l’école continue de fonctionner sans Internet tout en évitant les conflits de synchronisation financière entre plusieurs appareils. Le cloud et le vrai mode offline par appareil viennent ensuite.

## 2. État technique constaté

- Application : `0.11.0-rc.1`.
- UI : Python + PySide6.
- Persistance : SQLite locale.
- Architecture de démarrage : `app/main.py` ouvre une seule base locale et applique un `QLockFile`, donc l’application est volontairement mono-instance par base.
- Schéma courant du code : migration `LATEST_SCHEMA_VERSION = 17`.
- Documentation racine encore ancienne : README/CHECKPOINT annoncent v14 ; cette documentation doit être alignée avant une future release.
- Environ **45 fichiers Python applicatifs / 19 500 lignes**.
- Schéma : **71 tables** et **52 index** observés.
- `SchoolDatabase` agrège les mixins Configuration, Terrain, Personnel, StaffFinance, FinancialDecisions, Schooling, Anticipation, FinanceCheckout, FinancialViews et Operational.
- L’UI appelle directement environ **173 méthodes DB distinctes** sur **324 sites d’appel** ; 17 références directes `db.conn` existent encore dans les écrans.
- La couche `domain` est petite mais pure Python. Une grande partie du métier se trouve dans les mixins `app/db/*`, sans dépendance PySide6 : c’est positif pour la migration.
- Les documents PDF/Excel sont majoritairement générés avec ReportLab/openpyxl et sont donc réutilisables côté serveur. L’impression directe dépend de PySide6/Windows et devra être remplacée/adaptée côté Web.

## 3. Ce qui est réellement réutilisable

### Réutilisable comme code ou référence forte

- calculs financiers purs dans `app/domain` ;
- règles d’inscription/réinscription ;
- famille / foyer / responsables ;
- logique des charges, paiements et allocations ;
- décisions financières et responsabilités ;
- caisse, reçus et audit ;
- fonds anticipés et plans anticipés ;
- règles multi-années ;
- personnel ;
- règles de configuration ;
- génération de nombreux PDF/Excel ;
- scénarios de certification existants et tests comme **oracle de comportement**.

### À adapter

- mixins `app/db/*` : très utiles comme spécification et parfois comme code de transition, mais elles utilisent `sqlite3` et du SQL SQLite directement ;
- mécanismes de sauvegarde/restauration : actuellement orientés fichier SQLite ;
- documents et historique : les chemins locaux Windows devront devenir des objets/fichiers serveur et des téléchargements clients ;
- authentification : le PIN local PBKDF2 est adapté à un poste local, pas à une application exposée sur Internet ;
- rôles : modèle trop grossier pour une plateforme Web étendue.

### À réécrire

- interface PySide6 ;
- navigation Qt ;
- dialogues/modales Qt ;
- impression native Windows ;
- stockage des préférences lié au poste ;
- gestion du fichier SQLite comme base active côté client.

## 4. Bloqueurs principaux d’une conversion Web directe

### 4.1 Couplage SQLite

La couche métier et la couche de données sont souvent dans la même méthode. Les requêtes utilisent `?`, `INSERT OR IGNORE/REPLACE`, PRAGMA, `COLLATE NOCASE`, fonctions SQLite et accès direct `self.conn`.

Conclusion : **on ne remplace pas simplement `sqlite3` par PostgreSQL**. Il faut créer une vraie frontière repository/service ou migrer progressivement les opérations critiques.

### 4.2 Couplage UI → DB

Les écrans appellent directement un grand nombre de méthodes `SchoolDatabase`. Le Web doit passer par des contrats d’API explicites : DTO/JSON, validation, permissions, erreurs métier et idempotence.

### 4.3 Mono-école

Le code traite l’école comme une racine unique (`SELECT * FROM school LIMIT 1`) et les grandes tables ne portent pas un `school_id`/`tenant_id` généralisé.

Pour remplacer rapidement un premier logiciel scolaire, c’est acceptable. Pour plusieurs écoles du même patron, deux options :

1. **court terme : un déploiement / une base par école** ;
2. **moyen terme : multi-tenant véritable**, plutôt dans la plateforme EduSync/EduSyn plus large.

Il ne faut pas forcer le mono-école actuel à devenir multi-tenant en urgence.

### 4.4 Authentification Web

`local_users` utilise un rôle unique parmi `ADMIN`, `SECRETARIAT`, `CAISSIER`, `DIRECTION` et un PIN local. Pour le Web, il faut :

- authentification serveur ;
- sessions/tokens ;
- mots de passe ou autre facteur adapté ;
- rate limiting ;
- journalisation de connexion ;
- récupération/rotation de secrets ;
- permissions plus fines.

### 4.5 Offline-first financier

Le vrai offline-first multi-appareils demande des garanties supplémentaires :

- identifiants de commande uniques ;
- idempotency keys ;
- journal d’opérations local ;
- synchronisation ordonnée ;
- gestion des conflits ;
- numérotation des reçus ;
- caisse et journée de caisse ;
- double validation ;
- reprise après réseau ;
- résolution des écritures concurrentes.

Il serait risqué de rendre les paiements offline multi-appareils dès la première version Web.

## 5. Architecture recommandée

### Phase A — Web local / serveur d’école

```text
PC / Téléphone / Tablette
        |
        | navigateur / PWA
        v
React + TypeScript
        |
        | HTTP/API sur réseau local
        v
FastAPI Python
        |
        v
PostgreSQL local au serveur de l’école
        |
        +--> PDF / Excel / documents
        +--> sauvegardes locales
        +--> copie chiffrée externe/cloud quand Internet revient
```

Avantages :

- plusieurs utilisateurs simultanés ;
- l’école fonctionne sans Internet ;
- une seule source de vérité ;
- pas de synchronisation concurrente par appareil au départ ;
- même interface disponible sur PC et téléphone ;
- base prête pour une future connexion cloud.

### Phase B — Web distant / cloud

Ajouter :

- serveur cloud ou réplication contrôlée ;
- HTTPS ;
- accès distant sécurisé ;
- sauvegardes hors site ;
- monitoring ;
- politique de récupération après sinistre.

### Phase C — vrai offline-first par appareil

Ajouter IndexedDB/local store + journal d’opérations + moteur de synchronisation. Commencer par cache de lecture et brouillons. Les paiements offline ne seront activés qu’après certification d’un protocole d’idempotence et de conflit.

### Distribution

Une fois la PWA stable :

- Web : navigateur / PWA ;
- Android : Capacitor si besoin d’APK ;
- Windows : Tauri ou PWA installée ;
- éviter de multiplier les wrappers avant stabilisation du Web.

## 6. Stratégie de migration recommandée

1. **Geler un checkpoint Desktop canonique** comme solution de secours.
2. Créer un nouveau workspace `edusync-web` sans modifier la branche Desktop certifiée.
3. Définir les contrats API par domaine : Auth, School/Years, Students/Families, Enrollment, Finance, Cash, Personnel, Settings, Documents.
4. Reproduire les invariants métier existants sous forme de tests d’API.
5. Créer le schéma PostgreSQL en conservant les UUID et identifiants métier existants.
6. Écrire un migrateur SQLite → PostgreSQL, sans renumérotation des IDs/matricules/reçus.
7. Migrer d’abord les parcours prioritaires : connexion, année, annuaire, inscription/réinscription, encaissement, reçus, caisse.
8. Comparer systématiquement les résultats Desktop vs Web sur une base DEMO copiée.
9. Faire un pilote LAN dans une école.
10. Ajouter ensuite les vues, rapports, personnel, paramètres avancés et nouveaux modules.

## 7. Priorité pour un remplacement rapide

Pour une première bascule opérationnelle, viser seulement :

- authentification ;
- établissement + année ;
- élèves/familles ;
- inscription/réinscription ;
- effectifs ;
- encaissement rapide ;
- caisse du jour ;
- reçus ;
- historique financier essentiel ;
- sauvegarde serveur.

Ne pas attendre que toutes les pages analytiques et tous les réglages avancés soient réécrits avant le pilote.

## 8. Intendance — intégration recommandée

Le code possède déjà la **fonction personnel `INTENDANT`**, mais le système d’accès ne possède pas encore un rôle `INTENDANT`. Cela confirme que le futur module doit être ajouté comme domaine séparé avec des permissions propres.

Ne pas mélanger l’Intendance directement dans les tables `payments` / `cash_operations` comme si achat, réception et décaissement étaient une seule opération.

### Domaine Intendance proposé

- demandes de besoins ;
- fournisseurs ;
- demandes de prix / devis ;
- bons de commande ;
- validations ;
- réceptions ;
- magasins / stocks ;
- mouvements de stock ;
- affectations aux services ;
- patrimoine / immobilisations ;
- inventaires ;
- maintenance ;
- pièces justificatives ;
- liens contrôlés avec la finance pour les décaissements.

### Contrôle interne

Séparer au minimum :

- demandeur ;
- approbateur ;
- acheteur/intendant ;
- réceptionnaire ;
- payeur/caissier.

Même si une petite école cumule des fonctions humaines, le logiciel doit conserver des traces distinctes.

## 9. Point important : documentation de version

Le README/CHECKPOINT annonce encore « schéma v14 », alors que `migrations.py` annonce `LATEST_SCHEMA_VERSION = 17` et les bases de recette récentes sont bien en v17. Avant le prochain packaging canonique, corriger cette incohérence documentaire.

## 10. Décision recommandée

**Ne pas transformer immédiatement le Desktop existant en faux Web.**

Décision cible :

> **Construire EduSync Web École comme une nouvelle présentation et un nouveau backend serveur, en conservant le Desktop actuel comme référence métier et solution de secours.**

Pour aller vite, le premier déploiement Web doit fonctionner sur le réseau local de l’école avec un serveur central. Cela donne déjà une expérience « Web sans dépendance Internet » et évite le risque majeur du vrai offline-first distribué.

## 11. Prochaine mission technique proposée

**LOT WEB-0 — Extraction des contrats et squelette de migration**

Sans supprimer ni modifier le Desktop :

1. inventaire des 173 méthodes appelées par l’UI ;
2. classement READ / WRITE / TRANSACTION / DOCUMENT ;
3. sélection des ~20 opérations nécessaires au premier pilote ;
4. définition des endpoints FastAPI ;
5. définition du schéma PostgreSQL initial ;
6. plan de migration SQLite → PostgreSQL ;
7. squelette React/TypeScript ;
8. tests contractuels contre une copie DEMO ;
9. aucun changement fonctionnel du produit Desktop.

Ce LOT WEB-0 doit précéder toute réécriture massive de l’interface.
