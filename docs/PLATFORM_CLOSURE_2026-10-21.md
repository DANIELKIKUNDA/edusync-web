# Clôture plateforme — preuves locales et certification restante

Date : 21 octobre 2026. Source de départ : `9a02964ac9f7163e68ee384cb297e88f8de6cf27`.
Le SHA de correction est celui du commit contenant ce rapport. Aucun changement de code métier backend,
aucune migration, aucun changement de contrôleur privilégié, aucun déploiement production.

**PLATFORM_FINAL_STATUS = BLOCKED** : la certification distante de ce nouveau commit et la réception FCM
sur un vrai appareil restent à réaliser. Les preuves de l'ancien staging ne certifient pas ce commit.

## Corrections

- Modal partagé : le cycle de vie du focus dépend de l'ouverture, plus de l'identité d'un callback inline.
  Escape utilise le callback actuel ; la restauration du focus intervient au démontage. Les champs MFA
  gardent leurs règles numériques, collage, Backspace, saisie mobile et confirmation.
- Le wrapper réseau traitait tous les `fetch`, y compris ceux de Firebase, avec `credentials: include`,
  reprise de session et éventuelle confirmation MFA. Il traite maintenant seulement l'API EduSync de
  même origine. Les requêtes tierces gardent exactement leurs options. Ce défaut est démontré par test ;
  le lien causal avec l'erreur du téléphone doit encore être confirmé en staging.
- L'activation Push retourne un message français stable. Les journaux contiennent seulement une étape
  (`configuration`, `permission`, `firebase-token`, `device-registration`), jamais une exception Firebase,
  une URL contenant des paramètres, un jeton ou un secret. La révocation doit être confirmée par le serveur
  avant d'effacer l'identifiant local. L'affichage distingue appareil enregistré et réception réellement testée.
- Les appareils actifs sont interrogés sur l'endpoint plateforme existant, limité au propriétaire authentifié.
  Le chiffrement, la déduplication, la réattribution de jeton et le retrait des jetons invalides existants ne sont
  pas réécrits. Leur certification DB/FCM réelle n'est pas remplacée par les mocks frontend.
- Breadcrumb commun : parents cliquables, contexte courant, troncature, retour mobile tactile de 44 px et
  parent autorisé fourni par l'écran. Fiches écoles, comptes, équipe, audit, notifications, service, messagerie.
- Titres normalisés `Contexte — EduSync`, y compris entrée/sortie d'une fiche profonde.
- Un seul bouton de défilement plateforme : haut/mini-page masqués, direction adaptative, inactivité,
  safe-area, réduction du mouvement et détection des actions qu'il pourrait recouvrir.
- Navigation par menu calculé côté serveur pour tous les rôles. Un deep link ou un ancien état d'historique
  ne monte plus les modules notifications/audit/messagerie/service sans leur entrée autorisée.
- États explicites `ONLINE_AUTHENTICATED`, `OFFLINE_AUTHENTICATED_CACHED`, `AUTH_REQUIRED`.
  Le contexte de consultation conservé dans sessionStorage ne contient aucun bearer/refresh token.
  Sa restauration est bornée à 24 h ; il sert à l'affichage, jamais à autoriser une écriture.
- Réutilisation d'IndexedDB existant : magasin séparé de snapshots JSON, namespace de session/identité,
  au maximum 40 réponses de 256 000 caractères. Les secrets, MFA, sessions, configurations Push, exports,
  fichiers et flux ne sont pas mis en cache. Le changement d'espace, la déconnexion et la révocation effacent
  le contexte. Aucun cache n'est utilisé comme repli d'un refus HTTP d'autorisation.
- Le garde-fou réseau bloque les mutations sensibles hors connexion avant tout appel réseau ; les boutons
  concernés partagent également un composant de désactivation. Les filtres et la navigation restent utilisables.
  Aucune mutation plateforme n'est ajoutée à l'outbox école.
- Réouverture hors connexion : cache explicite des ressources publiques déjà chargées avant activation du
  Service Worker, y compris modules différés. Les assets publics hachés tolèrent `Vary: Origin` ; les API,
  les requêtes authentifiées et les sondes de santé restent hors du cache partagé.
- La sonde de santé interroge `/health-api` et exige le JSON `status=ok`, au lieu d'accepter la page HTML `/health`.

## Tests et limites de preuve

Niveaux : A = code/statique ; B = automatisation locale ; C = staging réel ; D = validation humaine ; E = production.
Les tests navigateur emploient les vrais composants/application avec des réponses API de test. Ils ne prouvent
ni l'existence des rôles en staging, ni une connexion réelle de ces quatre comptes, ni une réception FCM.

- Build TypeScript + Vite réussi ; avertissements existants Sonner et taille de chunk conservés.
- Tests frontend : focus stable, callback Escape courant, collage, Backspace, soumission unique,
  requêtes Firebase inchangées, permission refusée, erreurs sanitizées, jeton existant, révocation non confirmée,
  isolation du cache, refus d'écriture, breadcrumb, titre, bouton vertical et désactivation/reprise des actions.
- Chromium réel : MFA aux largeurs 320/390/480/768/1440, géométrie, retour, titres ; quatre menus de capacités,
  sidebar repliée/clavier, tiroir mobile ; scroll/inactivité/collision/orientation/reduced-motion ;
  perte réseau, reconnexion et révocation. Le build compilé vérifie aussi la première réouverture offline.
- Backend portable : 854 réussites, 1 ignoré, 45 désélectionnés explicitement (`not gate_ and not scripts_are_valid_bash`).
  La tentative complète UTF-8 donne 856 réussites, 1 ignoré, 43 échecs exclusivement dans les contrôles Bash :
  le Bash Windows/WSL renvoie accès refusé. Cela n'est pas une certification Linux ; la CI conserve tous ces tests.
- Audit npm runtime : aucune vulnérabilité détectée. Scanner de secrets : aucune détection.
- Le contrat textuel de bannière offline est actualisé pour le libellé demandé ; les autres assertions restent présentes.
- Les deux fichiers SBOM/supply-chain déjà modifiés avant la mission sont conservés hors de ce commit.

La CI existante reçoit les tests unitaires et navigateur, les captures et le test offline du build compilé.
Les workflows CD, certification Linux et E2E staging existants gardent leurs déclenchements.

## Matrice multi-rôle

`B menu` signifie uniquement visibilité, absence des entrées interdites, shell partagé et navigation clavier/mobile.
`À certifier C/D` interdit de transformer ces preuves en recette fonctionnelle réelle.

| MODULE | ROLE | DESKTOP | MOBILE | OFFLINE | RBAC | UX | TEST | STATUS |
|---|---|---|---|---|---|---|---|---|
| Menus plateforme | Manager (fixture) | B menu | B 360 | B partagé | B visibilité | B partagé | platform.spec | À certifier C/D |
| Menus plateforme | Collaborateur standard (fixture) | B menu | B 360 | B partagé | B entrées cachées | B partagé | platform.spec | À certifier C/D |
| Menus plateforme | Collaborateur enrichi (fixture) | B menu | B 360 | B partagé | B menu étendu | B partagé | platform.spec | À certifier C/D |
| Menus plateforme | Custom (fixture, existence staging inconnue) | B menu | B 360 | B partagé | B audit seul | B partagé | platform.spec | À certifier C/D |
| Login/session | Compte plateforme de test | B | B shell | B perte/reprise/révocation | B preuve serveur | B | offline.spec | À certifier C/D |
| Dashboard | Rôles autorisés | A/backend B | A | A snapshots | Backend B | Préservé | tests existants | Fonctionnel C/D non certifié |
| Écoles | Rôles autorisés | A/backend B | A trail | A snapshots | Backend B | Composant commun | schools + shared | Fonctionnel C/D non certifié |
| Utilisateurs & accès | Rôles autorisés | A/backend B | A trail | A snapshots | Backend B | Composant commun | identities + shared | Fonctionnel C/D non certifié |
| Équipe | Rôles autorisés | A/backend B | A trail | A snapshots | Backend B | Composant commun | team + shared | Fonctionnel C/D non certifié |
| Notifications système | Rôles autorisés | A/backend B | A trail | A snapshots | Backend B | Composant commun | tests existants | Fonctionnel C/D non certifié |
| Journal d'audit | Fixture custom/collaborateurs | B écran vide | B tiroir | B build compilé | Backend B | B | offline/platform | À certifier C/D |
| État du service | Rôles autorisés | A/backend B | A trail | A snapshots | Backend B | Composant commun | health existant | Fonctionnel C/D non certifié |
| Messagerie | Fixtures Manager/enrichi | B canal Push | B tiroir | A snapshots | Backend B | B navigation | platform + push | Push réel bloquant C/D |
| Profil / sécurité / MFA | Composants partagés | B MFA | B 320–768 | B actions bloquées | Backend B | B focus | shared/unit | Recette compte réel C/D requise |

## Matrice responsive

| LARGEUR / MODE | PÉRIMÈTRE AUTOMATISÉ | NIVEAU | LIMITE |
|---|---|---|---|
| 320 × 850 | MFA, focus, retour compact, titres, largeur | B | Clavier Android réel D requis |
| 390 × 850 | Idem + scroll | B | Réception FCM non testée |
| 480 × 850 | MFA, breadcrumb compact, largeur | B | Tous tableaux/données réelles non parcourus |
| 768 × 850 | MFA et breadcrumb desktop | B | Tablette physique D requise |
| 1440 × 850 | MFA et breadcrumb desktop | B | Grand écran/zoom humain restant |
| Sidebar 1280 / tiroir 360 | Quatre menus de capacités, repli et clavier | B | Comptes réels C requis |
| 850 × 390 | Rotation, scroll, collision avec bouton métier | B | PWA physique D requise |

## Matrice offline

| CAS | COMPORTEMENT | PREUVE | STATUT |
|---|---|---|---|
| Perte réseau avec session connue | Shell conservé, bannière lecture seule | Chromium app | B |
| Écriture sensible | Refus avant requête, bouton désactivé | Unitaire + navigateur | B |
| Première réouverture offline après cache prêt | Shell + journal déjà chargé | Chromium build compilé | B |
| Donnée jamais consultée | Message d'indisponibilité, pas de donnée inventée | Cache unitaire | B |
| Reconnexion | Revalidation silencieuse, reprise | Chromium app | B |
| Révocation confirmée | Contexte effacé, shell fermé | Chromium app | B |
| Changement d'identité | Namespace distinct, pas de snapshot d'autrui | Unitaire | B |
| API / santé dans Cache Storage | Aucune entrée partagée | Chromium build compilé | B |
| Téléphone réel / stockage refusé / autre onglet ancien | Recette encore nécessaire | A uniquement | PENDING HUMAN VALIDATION |

## Matrice navigation

| CAS | PREUVE | STATUT |
|---|---|---|
| Parents cliquables / parent de repli fourni | Unitaire + Chromium partagé | B |
| Deep link vers module hors menu | Application + quatre menus | B |
| Titres entrée/sortie, une seule marque | Chromium partagé/application | B |
| Retour compact 44 px et breadcrumb desktop | Captures 320/390/480/768/1440 | B |
| Bouton vertical unique | Court/haut/milieu/bas unitaire ; interactions Chromium | B |
| Historique et navigation profonde de tous objets réels | Parcours staging restant | À certifier C/D |

## Matrice des défauts

| DEFECT | FIX | TEST | PROOF | STATUS |
|---|---|---|---|---|
| MFA focus | Effet de montage, callback ref | Unitaires + cinq largeurs | Captures MFA | B PASS, C/D restant |
| FCM device registration / Failed to fetch | Isolation du fetch, message humain, étape sanitizée | SDK simulé + appel tiers | Tests push/connectivity | Réception réelle non certifiée |
| Vrai push reçu | Aucun résultat inventé | Test physique requis | Aucune preuve de réception | BLOCKED C/D |
| Révocation appareil trompeuse | Effacement local après réponse serveur | Échec réseau simulé | Test push | B PASS |
| Session perdue sur panne réseau | Contexte sans token, état distinct | Perte/reprise/révocation | Chromium offline | B PASS |
| Cache readonly | IndexedDB séparé, allowlist, pas d'outbox plateforme | Isolation + write guard | Tests offline | B PASS |
| Premier boot offline | Rattrapage des assets publics, Vary public | Rechargement compilé offline | Chromium compilé | B PASS |
| Retour mobile / breadcrumb | Un seul PageTrail | Parent, largeur, clic | Captures trail | B PASS |
| Bouton flottant | Composant shell unique | Inactivité, collision, rotation | shared.spec | B PASS |
| Titres fenêtre | Titre du contexte courant | Entrée/sortie | shared.spec | B PASS |
| Multi-rôle / deep link | Même shell, menu effectif, garde au montage | Quatre fixtures | platform.spec | B partiel ; C requis |

## Blocages de clôture

1. Git distant : le gestionnaire Windows des credentials n'est pas accessible à cette session ; `git ls-remote`
   échoue et le connecteur GitHub retourne 404. Aucune ACL ni clé n'est modifiée. Un lanceur propriétaire
   doit publier le commit exact et suivre les workflows existants, sans redéploiement manuel.
2. CI/CD/certification Linux/E2E staging du nouveau commit non exécutées à la date de ce rapport local.
3. E2E connecté multi-rôle réel : disponibilité des comptes de test et secrets d'environnement à vérifier
   par noms uniquement. Ne jamais coller leurs valeurs dans le chat.
4. Push : permission navigateur/Android, enregistrement serveur et réception réelle encore requis après CD.
   L'e-mail Brevo reçu sur le staging précédent reste une preuve distincte, pas une certification de ce commit.
5. D : **PENDING HUMAN VALIDATION** pour la recette fonctionnelle/ergonomique finale de tous les écrans.
6. E : production hors périmètre ; aucune action effectuée.

La plateforme n'est donc pas déclarée FINAL ni prête au passage École sur la seule base des tests locaux.
