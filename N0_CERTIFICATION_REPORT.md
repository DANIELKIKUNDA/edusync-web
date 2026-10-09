# EduSync Web — rapport de certification Niveau 0 (socle)

Pas de PASS global : chaque point donne sa preuve, ses limites, et le SHA exact figure dans
`CERTIFICATION_EVIDENCE_MANIFEST.md`. Instance locale isolée uniquement (aucun staging, aucune production).

## Prérequis 1.1 à 1.4 — `prereq-live.json` (42/42)

| # | Exigence | Résultat |
|---|---|---|
| 1.1 | Session persistante sans reconnexion périodique | Session de 400 jours inactive 120 jours toujours renouvelée ; `expires_at` nul ; rotation à chaque renouvellement ; rejeu d'un jeton tourné → session entière révoquée et jeton d'accès coupé ; cookie HttpOnly, SameSite=Lax, chemin restreint, Secure en production ; contrôle d'origine (CSRF) sur login/refresh/logout/logout-all ; déconnexion de tous les appareils (auditée) ; désactivation, changement de mot de passe et révocation coupent immédiatement. Politiques d'expiration encore disponibles par configuration (désactivées par défaut, `docker-compose.yml` compris). |
| 1.2 | Montants en `Decimal` | Plus aucun `float` sur les montants (contrôles financiers, rapports, documents de recouvrement) ; le JSON émet des chaînes décimales exactes (`"12345.67"`, `"1500000.05"` aller-retour en CDF et USD). |
| 1.3 | Rôle PostgreSQL dédié aux workers | `edusync_worker` : NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE, propriétaire d'aucune table ; lecture refusée sur comptes, élèves, paiements ; insertion/suppression/DDL refusées ; seules ses files sont accessibles ; les workers refusent de démarrer avec toute autre URL. |
| 1.4 | Sécurité du compte plateforme | Changement du mot de passe, liste des appareils avec « Cet appareil », révocation d'un appareil, déconnexion de tous les appareils, audit ; impossible de révoquer la session d'un autre compte. |

## Écran de démarrage
Logo officiel (livre ouvert, `docs/BRAND_ASSETS.md`), nom, barre de progression juste sous le contenu,
signature « from VolcanoTech », styles intégrés à la page (affichage avant tout chargement), fondu de sortie.
L'écran reste affiché pendant la vérification réelle de la session puis disparaît (aucun minuteur artificiel,
aucun second écran de chargement). Mouvement réduit respecté. Captures : `captures/n0-boot-1280.png`.

## Connexion
* **Sans code établissement** : le contexte est déterminé après authentification. Un seul espace → ouverture
  directe ; plusieurs → écran « Choisir un espace » (aucune session n'existe avant le choix). Accès Atelier Pro
  en pied de page **uniquement tant qu'aucun Manager système n'existe** (décision du propriétaire) ; ensuite le
  Manager se connecte comme tout le monde. La sécurité reste côté serveur : masquer le lien n'en est pas une.
* Interface modernisée (couche `modern.css`, présentation seulement) : police Inter Variable auto-hébergée,
  chiffres tabulaires, cartes indicateurs avec pastille d'icône, nombre centré et libellé centré dans tous les
  modules, ombres douces, dialogues et focus modernisés. Parcours visuel `n1-journey-live.json` 35/35.
* Photo professionnelle d'un campus, sous licence Unsplash, servie localement (WebP 2000 px, WebP mobile, JPEG
  de repli), voile sombre pour la lisibilité, crédit discret.
* Afficher/masquer le mot de passe, focus initial, ordre de tabulation, erreurs sans énumération, verrouillage
  après tentatives (par compte ; seuil par adresse relevé pour ne pas bloquer une école entière derrière un NAT).
* Largeurs vérifiées : 320, 375, 390, 768, 1024, 1280, 1440 — sans défilement horizontal
  (`captures/n0-login-*.png`, `n1-journey-live.json`).

## PWA
Manifeste (`id`, nom, nom court, thème), favicon, apple-touch-icon, icônes 192/512 et maskable séparées, cache
du service worker versionné (`edusync-shell-2026-10-n0n1`, l'ancien est supprimé à l'activation), réponses API
jamais mises en cache. Installation réelle sur téléphone : nécessite HTTPS public → **BLOCKED_EXTERNAL**.

## Réseau et hors ligne (inventaire honnête)
* Fonctionne hors ligne : affichage du shell, états « Hors ligne / Reconnexion / Enregistrement… » exacts,
  réessai sans doublon (clés d'idempotence réutilisées après une réponse perdue).
* Lecture en cache : aucune donnée métier n'est servie hors ligne par le service worker (choix de sécurité).
* Interdit hors ligne : Finance (doctrine), toutes les opérations plateforme.
* `LOCAL_WRITE_SYNC` du registre de capacités : non câblé côté Web → **OWNER_DECISION** (liste des opérations
  et règles de conflit à décider).

## Lanceur local (raccourcis Bureau)
Défauts trouvés et corrigés pendant cette passe, preuves dans les commits :
1. L'API et les workers étaient tués par chaque appel `wsl.exe` ultérieur (reproduit 4/4, corrigé 0/4 : console
   privée cachée par service).
2. **Après un redémarrage réel de Windows (2026-10-08 17:09)** : le stockage de documents a mis ≈ 4 min à
   démarrer à froid → attente portée à 6 min ; démarrage complet ensuite réussi.
3. WSL bloqué (`hostname -I` > 60 s) : le lanceur réutilise la dernière adresse connue au lieu de planter, et
   n'écrit plus de double `bind` Redis.
4. Après le redémarrage, Windows (Hyper-V/WSL) a réservé les plages de ports 58929–59628 : l'outil de recette
   utilisait 59223 (corrigé, port configurable). Les ports d'EduSync (5180, 58100, 55432, 16379, 18333) n'étaient
   pas dans ces plages, mais une réservation future pourrait toucher 58100 : à surveiller, ou à déplacer hors
   de la plage dynamique au déploiement.
Limite : la machine de test n'avait que ≈ 600 Mo de mémoire libre sur 8 Go pendant ces essais ; les durées
mesurées en dépendent.

## En-têtes HTTP (D) — `hardening-http-live.json`
CSP stricte (scripts du seul domaine), `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`,
Referrer-Policy, Permissions-Policy, COOP, cache immuable des fichiers versionnés et revalidation du shell,
aucun en-tête serveur, CORS fermé aux origines étrangères. HSTS : **BLOCKED_EXTERNAL** (pas de HTTPS public).

## Accessibilité (I) — état
Vérifié par le parcours automatisé : focus initial, tabulation, nom accessible des boutons d'icône, messages
d'erreur annoncés (`role=alert`), Échap ferme les dialogues et rend le focus, cibles tactiles 44 px en mobile,
mouvement réduit, gravité et statuts jamais signalés par la seule couleur. **Non vérifié** : audit de contraste
outillé (axe/Lighthouse non disponibles hors ligne) et zoom 200 % sur toutes les pages → limite déclarée.
