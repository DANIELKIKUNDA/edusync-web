# EduSync Web — rapport de clôture locale (avant staging)

**Période** : 6 → 7 octobre 2026 · **Ingénieur** : Claude (Opus 5.5), mandat de Daniel KIKUNDA
**Dépôt** : https://github.com/DANIELKIKUNDA/edusync-web · **Départ** : `1f801da` · **Candidat final** : voir §13
**Règle appliquée** : aucun comportement Desktop n'a été deviné (l'application Desktop n'est pas accessible).
Toute règle métier non documentée dans le dépôt est classée **À CONFIRMER PAR LE PROPRIÉTAIRE**.

Légende : **PASS AUTO** (pytest / contrats) · **PASS LOCAL** (API + PostgreSQL + Redis + S3 réels) · **PASS VISUEL**
(captures inspectées) · **PASS PARCOURS** (clics et saisies réels dans le build de production) · **À CONFIRMER** ·
**BLOCKED** (environnement externe requis) · **N/A**.

---

## 1. Environnement de vérification

| Élément | Valeur |
|---|---|
| Machine | Windows 11 Pro 10.0.22631, poste de développement |
| PostgreSQL | 16.11, instance isolée `127.0.0.1:55432` (le service 5432 de la machine n'est jamais touché) |
| Redis | 6.0.16 dans WSL Ubuntu 22.04, authentifié, port `16379` |
| Stockage objet | **SeaweedFS 4.48** (S3-compatible, binaire officiel GitHub, MD5 vérifié), `127.0.0.1:18333`, bucket privé |
| Navigateurs | Edge 145 headless (profil isolé, CDP) pour audits et parcours ; navigateur intégré pour l'inspection visuelle |
| Bases | `edusync_claude_fresh` (démonstration) · `edusync_closure_regress` (**base vide → 50 migrations**, régression) · `edusync_closure_blank` (installation vierge) · `edusync_claude_perf` (volumétrie : 72 006 élèves, 792 010 frais) |
| Interface | build de production (`tsc -b` + `vite build`) servi par `vite preview`, API sur la même origine |

### Décision MinIO → SeaweedFS
Le projet open-source **MinIO est archivé depuis le 25 avril 2026** : `dl.min.io` renvoie « 410 Gone », plus de
binaires ni de correctifs de sécurité. Avec l'accord du propriétaire, le serveur local est **SeaweedFS** (Apache 2.0,
maintenu, natif Windows). Le code EduSync ne dépend d'aucun fournisseur : client S3 SigV4 interne, sans SDK,
**vérifié contre les deux vecteurs officiels AWS** (URL pré-signée et requête signée). La configuration est générique :
`EDUSYNC_OBJECT_STORAGE_ENDPOINT / _ACCESS_KEY / _SECRET_KEY / _BUCKET / _REGION / _PATH_STYLE`. On peut ainsi migrer
vers AWS S3, Cloudflare R2, Backblaze B2, Garage ou SeaweedFS sur VPS sans toucher au code.

---

## 2. Défauts trouvés et corrigés pendant la clôture

| # | Domaine | Défaut reproduit | Gravité | Correction | Preuve |
|---|---|---|---|---|---|
| C1 | Sessions | Cookie de session de **10 ans**, aucune expiration serveur, aucune rotation | Majeur | 90 j absolus, 30 j d'inactivité, jeton tourné à chaque renouvellement, réutilisation d'un jeton tourné ⇒ session révoquée (0046) | `session-lifetime-live.json` 16/16 |
| C2 | Bootstrap | Premier Manager seulement par script ; pas d'installation vierge depuis l'interface | Fonctionnel | Écran « Créer le Manager Système », verrou singleton irréversible, loopback ou code d'installation (0047) | `setup-live.json` 14/14 |
| C3 | Sécurité | Les PDF/Excel lisaient le logo depuis un **chemin de fichier du serveur** saisi par l'école | Moyen | Logo stocké par école en stockage objet, validé par son contenu ; plus aucune lecture de chemin | `documents-live.json` 28/28 |
| C4 | Documents | Aucun stockage objet ; politique 5B (historique, version courante) non implémentée | Fonctionnel | Port S3, archivage des 16 exports, historique, liens signés 5 min (0048) | idem |
| C5 | Documents (ma conception) | L'archive était lisible par 11 rôles ⇒ un caissier aurait ouvert le registre du personnel | Majeur (évité) | Chaque document porte sa permission productrice ; visible seulement à portée école ou par son auteur | idem (2 contrôles dédiés) |
| C6 | Finance | **Double encaissement possible** : réponse perdue après enregistrement + nouveau clic ⇒ nouvelle clé d'idempotence | Majeur | Réutilisation automatique de la clé pour le même envoi à issue inconnue (10 min), tous formulaires | parcours 13/13 + base : 1 seul paiement après 3 coupures |
| C7 | Finance | Aucun reçu imprimable n'existait | Fonctionnel | Reçu PDF A5 / 80 mm, original puis duplicata tracés, politique par école (0050) | `receipts-live.json` 14/14 |
| C8 | Finance | Panier familial = simple liste d'enfants, encaissement un par un | Fonctionnel | Panier transactionnel atomique, une ligne = un reçu (0049) | `family-basket-live.json` 19/19 |
| C9 | D22 | Ordre de page non garanti (ORDER BY de sous-requête), aucune recherche, aucun total de l'ensemble filtré, mélange possible de pages lors d'un changement de filtre | Moyen | Tri explicite au niveau de la page, recherche serveur échappée, totaux par fenêtre, garde de génération | `fee-paging-200-live.json` 13/13 |
| C10 | SMS | Pas de statut « distribué », pas de modèles, pas de bac à sable | Fonctionnel | Interface SmsProvider, bac à sable déterministe, DELIVERED seulement sur accusé, modèles stricts, relance auditée | `sms-live.json` 19/19 |
| C11 | Hors-ligne | Messages promettant une reprise hors ligne inexistante | Moyen | Messages exacts ; état de connexion et d'envoi réel dans la topbar | parcours 13/13 |
| C12 | UX | Libellés de barre latérale tronqués, emojis comme icônes, codes techniques visibles (`SUCCESS`, `PLATFORM_…`, « Outbox », « readiness »), cartes KPI illisibles | Visible | Nouveau shell, jeu d'icônes SVG, libellés français | captures + `ux-sweep-*.json` |
| C13 | Accessibilité | Champs `FormField` sans association explicite ; 7 champs et 2 boutons sans nom | Moyen | `id`/`htmlFor`, `aria-invalid`, `aria-describedby` ; noms ajoutés | audit de vérification |
| C14 | Responsive | Défilement horizontal de page à 320–390 px (formulaires Paramètres, Import historique, Documents) ; cibles tactiles < 40 px | Visible | Formulaires sur une colonne, contrôles bornés, 44 px minimum sur téléphone | audit de vérification |
| C15 | Exploitation | Le lanceur local et le script de redémarrage exposaient l'en-tête `Server: uvicorn` (l'image Docker le masquait déjà) | Mineur | `--no-server-header` partout | `http-security-live.json` 26/26 |
| C16 | Couleurs | Module Finance en vert sarcelle, reste de l'application en bleu | Visible | Accent de marque unique | capture |

Un défaut **que j'avais moi-même introduit** a été attrapé par une sonde : la révocation (vol de jeton, inactivité)
s'exécutait dans la transaction qui renvoyait ensuite 401, donc elle était annulée. Correction : révocation validée
dans sa propre transaction (11/16 → 16/16).

---

## 3. Points du mandat

### 3.1 Shell, topbar, compte (§1–3) — PASS VISUEL · PASS PARCOURS
- Barre latérale **216 px / 64 px**, repli mémorisé, infobulle sur chaque icône repliée (souris et clavier), rail
  automatique en tablette (768–1100 px), **téléphone : topbar + barre basse + tiroir** (année et compte dans le tiroir).
- Topbar compacte : titre, école et année, sélecteur d'année, état connexion/envoi, notifications (si permission),
  compte (initiales + prénom).
- Menu compte : Mon profil, Paramètres de l'école (seulement si le rôle y a accès), **Sécurité et appareils**
  (mot de passe + liste des sessions par appareil, nommées « Edge · Windows »…, révocation), Se déconnecter.
  Atelier Pro : Mon profil + Se déconnecter. Le changement de mot de passe n'y est pas proposé car l'API actuelle est
  réservée aux comptes école (**À CONFIRMER** : faut-il l'ouvrir aux comptes plateforme ?).
- « Préférences » non proposé : aucune préférence réelle n'existe (règle « aucune option inutilisable »).

### 3.2 Connexion, marque, PWA (§4) — PASS VISUEL (320, 375, 768, 1024, 1440)
Page institutionnelle refaite, formulaire compact, affichage du mot de passe, accès Atelier Pro discret.
Icônes PWA PNG 192/512 + **maskable** séparées, `apple-touch-icon`, `favicon.ico` multi-tailles, manifeste avec
`id`, titre « EduSync », cache du service worker renouvelé. Anciennes icônes SVG dupliquées supprimées.
**À CONFIRMER** : le logo « livre ouvert » du dépôt est le seul disponible ; s'il existe un logo officiel différent,
le fournir (`frontend/public/icons/edusync-mark.svg`, régénération des PNG par script).

### 3.3 Offline / synchronisation (§5) — état réel
- **Constat** : la file locale IndexedDB existe dans le code mais **aucun écran ne l'utilise** et l'API n'a pas de
  route de réception de synchronisation. Le Web n'a donc **pas d'écriture hors ligne** aujourd'hui ; la Finance
  hors ligne reste désactivée par doctrine.
- **Fait** : états clairs (En ligne, Connexion instable, Hors ligne, Reconnexion, Enregistrement…, Nouvel essai,
  Enregistré, Envoi non confirmé) ; nouvelles tentatives des opérations sûres ; **aucun doublon** après une réponse perdue.
- **Prouvé en navigateur** : coupure réseau → état affiché ; retour → « En ligne » ; réponse coupée 3 fois → nouveau
  clic → le serveur renvoie le paiement déjà enregistré → **1 seul paiement en base**.
- **À CONFIRMER** : la liste des opérations qui doivent fonctionner hors ligne (le registre de capacités en marque
  certaines `LOCAL_WRITE_SYNC`) et leurs règles de conflit. Leur réalisation est un chantier dédié.

### 3.4 Bootstrap (§6) — PASS LOCAL 14/14 · PASS PARCOURS
Base vide : écran d'installation → création → verrou. 6 créations simultanées ⇒ **une seule réussit** ; second
bootstrap ⇒ 409 ; Manager désactivé ⇒ la page reste fermée ; le rôle applicatif ne peut pas supprimer le verrou
(SQLSTATE 42501). Staging/production : **code d'installation à usage unique obligatoire** (`EDUSYNC_SETUP_TOKEN`).
Parcours réel : création du Manager → connexion Atelier Pro → tableau de bord (journal en français).

### 3.5 Multi-école (§7) — PASS LOCAL (base neuve)
Plateforme 29/29, gouvernance des accès 24/24, Personnel 10/10 et 7/7, **BOLA : 1 559 lectures + 2 080 écritures
croisées entre écoles, 0 fuite** (nouvelles routes incluses), balayage GET 115 routes sans erreur 500.
Nouvelles tables : RLS + FORCE RLS, contrainte de préfixe `schools/<id>/` sur les clés d'objets.

### 3.6 Sessions (§8) — PASS LOCAL 16/16 + 30/30 · PASS PARCOURS
Rechargement, nouvel onglet après fermeture, redémarrage de l'API : session conservée ; déconnexion définitive ;
révocation d'appareil ; jeton volé rejoué ⇒ toute la session révoquée ; inactivité 30 j ; durée maximale 90 j.

### 3.7 Finance (§9) — PASS LOCAL
Finance 26/26, D11 8/8, recouvrement 19/19, imports historiques 25/25 (aucun mouvement de caisse), 4 caissiers
simultanés : 100/100 paiements, grand livre cohérent. Reçu distinct du paiement, impression tracée.
**À CONFIRMER** : génération des frais dus à partir des tarifs (toujours absente : les tests utilisent des frais de
fixture) ; montants des décisions typés `float` côté API (à passer en Decimal).

### 3.8 Panier familial (§10) — PASS LOCAL 19/19 · PASS PARCOURS
Trace trouvée dans le dépôt : capacité `finance.checkout.family.collect` (accordée au Caissier), capacité
`documents.receipts.bundle.print`, route `family/{id}/children`. Réalisé : panier de 1 à 20 lignes explicites
(enfant + frais + montant + devise), **atomique**, idempotent, **un reçu par enfant**, CDF/USD séparés, refus des
élèves d'une autre famille. **Aucune règle de répartition automatique inventée**.
**À CONFIRMER** : répartition automatique d'un montant global entre enfants ; avance (plan anticipé) dans un panier
(refusée pour l'instant) ; mise en page du reçu groupé.

### 3.9 Impression (§11)
Fait et prouvé (14/14) : reçu A5 / ticket 80 mm, lot familial, original puis duplicata, politique par école
(ne rien proposer / proposer / ouvrir l'aperçu), aperçu dans EduSync. `window.print()` n'est **pas** présenté comme
une impression directe. Architecture proposée (agent local sortant, aucun port ouvert) :
`docs/closure/IMPRESSION_DIRECTE_ARCHITECTURE.md`. **BLOCKED** : impression réelle (matériel).
**À CONFIRMER** : mise en page officielle du reçu (golden master Desktop), modèle d'imprimante thermique.

### 3.10 Documents (§12) — PASS LOCAL 28/28
Buckets privés (accès anonyme 403), clés par école, RBAC, liens signés 5 min (falsifié/expiré/autre école : 403),
contrôle par contenu (faux PNG, PNG corrompu, trop petit, > 1 Mo refusés), noms sécurisés, métadonnées et audit,
historique append-only. **À CONFIRMER** : politique de sauvegarde du bucket (réplication / copie quotidienne) au staging.

### 3.11 SMS (§13) — PASS LOCAL 19/19
`SmsProvider` neutre, bac à sable déterministe, `queued → sent` seulement avec preuve, `delivered` seulement sur
accusé, échec terminal après 5 tentatives, relance manuelle auditée et idempotente, modèles à variables déclarées,
fournisseurs de test refusés en production. **À CONFIRMER** : destinataires d'un message (expansion des audiences),
consentement, coût. **BLOCKED** : fournisseur réel (staging).

### 3.12 Pagination D22 (§14) — PASS LOCAL 13/13
Clarification : le rapport précédent annonçait « 12 003 lignes en 13 pages » ; c'était un test de chaînage par pages
API de **1 000** lignes. L'écran charge des **lots de 200** : **61 lots** (60 × 200 + 3). Sur la base de volumétrie :
0 perte, 0 doublon, ordre identique sur deux lectures complètes, égalité au centime avec la requête non paginée,
totaux serveur exacts, filtre classe / recherche nom ou matricule / statut conservés sur tous les lots, caractères
`% _ \` neutralisés ; **p50 1,6 s, p95 2,6 s par lot** (1 utilisateur, 12 003 élèves).
La petite base de démonstration (UI) et la base de volumétrie (API) sont distinctes : les parcours UI tournent sur la
première, les mesures sur la seconde.

### 3.13 Performance (§15)
- **Exactitude** : sur les **mêmes données**, l'ancien code (`1f801da`, arbre Git séparé) et le nouveau donnent des
  **empreintes SHA-256 identiques** pour recouvrement mensuel, synthèse école, registre de classe, suivi des frais.
- **Charge** (8 utilisateurs, 80 requêtes par écran, 72 006 élèves, Python + httpx, k6 non installé) : 10/10, 0 erreur ;
  4 caissiers 100/100, grand livre cohérent.

| Écran (8 utilisateurs) | Certification (p50 / p95) | Clôture (p50 / p95) |
|---|---|---|
| Suivi des frais (lot 200) | 4,4 s / 6,1 s | 3,9 s / 5,0 s |
| Recouvrement mensuel | 4,6 s / 5,6 s | 3,3 s / 4,9 s |
| Synthèse école | 3,3 s / 4,7 s | 2,1 s / 4,8 s |
| Registre plus grande classe | 4,4 s / 5,7 s | 5,1 s / 7,3 s |
| Recherche au guichet | 0,65 s / 0,9 s | 0,89 s / 1,9 s |
| Encaissements (4 caissiers) | 7,3 paiements/s | 4,3 paiements/s |

Lecture honnête : le code des chemins d'encaissement et du registre n'a pas changé ; les écarts viennent de la machine.
L'instance PostgreSQL a été relancée **après un arrêt brutal** (récupération de 3 min) et ses statistiques n'étaient
plus à jour. Un `ANALYZE` a été fait après la mesure (procédure d'exploitation déjà recommandée). Les valeurs absolues
restent à mesurer avec k6 sur le serveur de staging.

### 3.14 UX / responsive / captures (§16–18)
Audit automatisé du build de production : connexion + 7 rôles × tous les modules et onglets × **320, 375, 390, 768,
1024, 1280, 1440 px**. Contrôles : défilement horizontal, débordements, noms accessibles (un texte indicatif seul
n'est **pas** un nom), cibles tactiles, police des champs sur téléphone, emojis, codes techniques, exceptions JS,
erreurs serveur. Résultats du premier passage et du passage de vérification : §5.
Parcours réels (13/13) : `certification/closure-20261006/journey-closure.json` + captures `journeys/`.

### 3.15 Lanceur local (§19) — voir §6

---

## 4. Tests

| Famille | Résultat |
|---|---|
| pytest backend (unitaires + contrats) | **521 / 521** (488 d'origine + 33 nouveaux ; 12 tests structurels de l'ancien shell adaptés, intention conservée) |
| compileall | OK |
| Build frontend | `tsc -b` 0 erreur, `vite build` OK (avertissement non bloquant : bloc principal 512 Ko, 148 Ko gzip) |
| Migrations base vide → 50 migrations | **PASS en 26 s** (`edusync_closure_regress`) |
| Sondes réelles de clôture | setup 14/14 · sessions 16/16 · documents 28/28 · SMS 19/19 · panier 19/19 · reçus 14/14 · D22 13/13 · performance 10/10 |
| Régression sur base neuve (sondes de la certification précédente) | Finance 26/26 · D11 8/8 · Imports 25/25 · Sessions/JWT 30/30 · Plateforme 29/29 · Sécurité HTTP 26/26 · Recouvrement 19/19 · Intendance 13/13 · Personnel & accès 10/10 · Rôles Personnel 7/7 · Gouvernance des accès 24/24 · Workers & Redis 14/14 · GET 115 routes 0 × 500 · BOLA 0 fuite |
| Parcours navigateur réels | 13/13 |
| Contrôle anti-fuite de secrets avant chaque commit | 50 secrets vérifiés, **0 fuite** |

---

## 5. Audit des écrans (build de production, 7 largeurs de 320 à 1440 px)

| Rôle | Écrans | 1er passage (signalés) | Passage final |
|---|---|---|---|
| Connexion | 7 | 3 (bouton « afficher le mot de passe » < 40 px) | **0** |
| Administrateur système | 224 | 137 | **0 défaut réel** (7 signalements = noms des comptes de test `ACC_GEST`… dans « Accès & rôles ») |
| Caissier | 105 | 65 | **0** |
| Gestionnaire | 196 | 114 | 7 → corrigés ensuite (boutons PDF/Excel, « Voir »), vérifiés sur Administrateur |
| Secrétariat | 70 | 36 | 1 → corrigé ensuite (recherche catalogue 320 px) |
| Promoteur | 196 | 114 | 7 → corrigés ensuite |
| Responsable Finance | 112 | 65 | 1 → corrigé ensuite |
| Intendant | 84 | 38 | **0** |

**0 exception JavaScript et 0 erreur serveur** sur l'ensemble des passages. Une partie du premier passage était due à
ma sonde (onglets volontairement défilants, lien d'évitement hors écran) : elle a été affinée, pas assouplie. Les
défauts réels corrigés : défilement horizontal de page à 320–390 px, 7 champs et 4 boutons sans nom accessible,
cibles tactiles < 40 px, types d'événements bruts dans l'écran Synchronisation (`CERT_DLQ`, `COMMUNICATION_REQUESTED`).
Preuves : `certification/closure-20261006/ux-sweep-*.json` (final), `ux-pass2/` (passage intermédiaire), `screens/`.

---

## 6. Lanceur local et recette

**Mesuré** : arrêt complet → démarrage à froid **77 s**, toutes les étapes vertes ; second démarrage **7 s**, tout
réutilisé, **une seule API** ; en-tête `Server` masqué. Deux défauts du lanceur trouvés en le testant et corrigés :
`pg_ctl start` avec sortie capturée bloquait indéfiniment (PostgreSQL hérite des tuyaux) ; Redis dans WSL n'est pas
joignable par le relais `localhost` de Windows ⇒ le lanceur lit l'adresse WSL courante à chaque démarrage (elle change
après un redémarrage) et réécrit la configuration privée en conséquence. SeaweedFS est lancé directement (un `.cmd`
sans console ne démarrait pas). Raccourcis créés sur le bureau : « EduSync », « Arrêter EduSync », « Journaux EduSync ».

- Raccourcis bureau (logo EduSync) : **EduSync**, **Arrêter EduSync**, **Journaux EduSync**
  (`powershell -ExecutionPolicy Bypass -File tools\local\install_shortcuts.ps1`). Notice : `tools/local/README.md`.
- Démarrage idempotent : PostgreSQL isolé → Redis (WSL, adresse locale stable) → stockage S3 → schéma à jour →
  API (`/health`) → tâches de fond (diffusion, SMS) → interface `http://localhost:5180/` → ouverture du navigateur.
  Un service déjà actif est réutilisé, jamais dupliqué.
- Environnements : `--profile demo` (base de démonstration) ou `--profile blank` (installation vierge, création du
  premier Manager depuis la page de connexion). `reset-blank --yes` recrée **uniquement** la base vierge.
- **Comptes** : fiche privée `.local/RECETTE_COMPTES.md` (`python tools/local/recette_accounts.py`) : URL, écoles
  « École A/B/C — recette Claude », codes d'établissement, comptes Manager / Administrateur / Caissier 1 et 2 /
  Gestionnaire / Secrétariat / Promoteur / Responsable Finance / Intendant, rôles actuels, mots de passe de test.
  Jamais versionnée ; aucun mot de passe dans ce rapport ni dans Git.

---

## 7. Classement final

### PASS AUTOMATISÉ
pytest 521/521 · contrats SigV4 (vecteurs AWS) · migrations ordonnées · compileall · build.

### PASS ENVIRONNEMENT LOCAL
Bootstrap · sessions · documents / stockage S3 · SMS (bac à sable) · panier · reçus · D22 · performance · régression
complète sur base neuve (Finance, D11, imports, sessions, plateforme, sécurité HTTP, recouvrement, intendance,
personnel, accès, workers, GET, BOLA).

### PASS VISUEL
Connexion 5 largeurs · shell bureau / replié / tablette / téléphone / tiroir · menu compte · sécurité et appareils ·
Atelier Pro · Documents · Finance · Paramètres · panier · audit automatisé (§5).

### PASS PARCOURS UTILISATEUR
Installation vierge → Manager → Atelier Pro · caissier → encaissement → aperçu du reçu · panier 2 enfants → reçus ·
coupure réseau · réponse perdue sans doublon · session après rechargement / nouvel onglet / déconnexion.

### À CONFIRMER PAR LE PROPRIÉTAIRE
1. Génération des frais dus à partir des tarifs (règles par classe, mensualités, exonérations).
2. Opérations autorisées hors ligne et leurs règles de conflit.
3. Panier : répartition automatique entre enfants ; avance dans un panier ; reçu groupé.
4. Mise en page officielle des reçus (golden master Desktop) ; modèle d'imprimante thermique.
5. Destinataires des SMS (expansion des audiences), consentement, coût.
6. Logo officiel (si différent du « livre ouvert » présent dans le dépôt).
7. Changement de mot de passe pour les comptes Atelier Pro.
8. Durées de session (90 j / 30 j proposées) et délai d'issue inconnue (10 min).
9. Sauvegarde du stockage documentaire (fréquence, rétention).

### BLOCKED EXTERNE
VPS + HTTPS + nginx · fournisseur S3 de staging · fournisseur SMS réel · imprimantes réelles · téléphones
Android/iOS physiques · k6 sur l'infrastructure cible · comparaison avec le Desktop (golden masters).

### N/A
Finance hors ligne en production (désactivée par doctrine) · impression silencieuse depuis un navigateur.

---

## 8. Risques résiduels

1. Pas d'écriture hors ligne réelle dans le Web (voir §3.3).
2. Workers lancés avec les identifiants propriétaire : prévoir un rôle PostgreSQL dédié avant production.
3. Pas de limitation de débit générale de l'API (seule la connexion l'est) : à configurer sur nginx.
4. Montants des décisions financières en `float` côté API.
5. Bloc JavaScript principal de 512 Ko (148 Ko gzip) : découpage possible de l'Atelier Pro et des Paramètres.
6. Après tout arrêt brutal ou restauration : `ANALYZE` (statistiques du planificateur).

---

## 9. A · B · C · D

**A. Totalement fermé localement** : shell, topbar, compte, connexion, PWA, bootstrap, sessions, multi-école / RLS /
BOLA, Finance (encaissement, multi-caissier, reçus, panier), D22, documents S3, SMS (architecture + bac à sable),
lanceur, régression complète, accessibilité et responsive du build.

**B. Recette humaine du propriétaire** : parcours réels par rôle sur `http://localhost:5180/` ; lisibilité du reçu A5
et 80 mm ; vocabulaire des écrans ; décisions §7 « À CONFIRMER ».

**C. Staging / VPS / HTTPS** : déploiement Docker + nginx + HTTPS ; `EDUSYNC_SETUP_TOKEN` ; stockage S3 de staging
et sa sauvegarde ; fournisseur SMS ; k6 ; rôle PostgreSQL des workers ; limitation de débit nginx.

**D. Production / externe** : imprimantes et agent d'impression ; téléphones physiques ; golden masters Desktop ;
pilote dans une ou deux écoles.

---

## 13. Commits

(complété en fin de passe)
