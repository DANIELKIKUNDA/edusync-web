# Journal des versions — EduSync

Les versions suivent la **gestion sémantique de version** ([SemVer](https://semver.org/lang/fr/)) : `MAJEUR.MINEUR.CORRECTIF`.

- **MAJEUR** (2.0.0) : changement qui oblige les écoles à changer leur façon de travailler ou leurs données.
- **MINEUR** (1.1.0) : nouvelle fonctionnalité, sans rien casser.
- **CORRECTIF** (1.0.1) : correction de défaut.
- Préversion : `-rc.1`, `-rc.2`… (candidate avant la sortie officielle).

La valeur unique se trouve dans le fichier `VERSION` ; `frontend/package.json` et `backend/pyproject.toml` portent la même
(le test `backend/tests/test_release_version.py` le vérifie). Publier une version : mettre à jour ces trois valeurs et ce
journal, fusionner, puis créer l'étiquette Git `vX.Y.Z` sur `main` — la CI refuse une étiquette différente de `VERSION`
et publie les images Docker sous ce nom. Les utilisateurs voient « Version X.Y.Z » ; le code du commit reste visible
seulement comme « compilation » pour le support.

## [1.0.0-rc.2] — 2026-11-01

### Ajouté — moteur d'exigibilité financière annuelle (PR #33)
- Par école et par année scolaire, une **politique d'exigibilité** décide, frais par frais, ce qui est réellement dû
  quand un élève arrive en cours d'année : mois antérieurs à l'inscription non exigibles, dus en entier, ou dus à un
  pourcentage choisi ; et pour le mois d'arrivée, un pourcentage selon le jour d'inscription (tranches de jours).
- La politique se prépare en brouillon (Paramètres › Tarifs), s'essaie par un **aperçu par classe**, puis s'active
  (droit `settings.tariffs.apply`) ; elle s'applique à la génération des frais, et le recouvrement distingue « non
  exigible » d'une exonération. Migration `0105_finance_annual_exigibility`.
- Certifié sur PostgreSQL réel dans la CI (`tools/ci/mef_postgres_integration.py`).

### Corrigé — mise à jour de l'application (audit)
- La nouvelle version se télécharge en arrière-plan pendant que l'on travaille ; l'avis « Nouvelle version disponible »
  n'apparaît qu'une fois ce téléchargement terminé.
- La version en cours n'est plus remplacée sous les doigts de l'utilisateur (ses modules hors ligne restent jusqu'au clic).
- « Mettre à jour » redémarre depuis l'appareil : mesuré sur réseau lent, 2,9 s au lieu de 13,8 s, avec le message
  « Installation de la mise à jour… » au lieu d'un écran sombre muet.
- L'application s'ouvre depuis l'appareil à chaque démarrage (plus d'attente du réseau pour la page).
- Un écran d'une ancienne version qui n'existe plus sur le serveur se recharge une seule fois sur la nouvelle, au lieu
  d'afficher « Connexion impossible ».

## [1.0.0-rc.1] — 2026-11-01

Première version candidate.

### Ajouté
- **Temps réel pour tous les rôles de l'école** : ce qu'un membre enregistre (encaissement, inscription, stock,
  personnel…) apparaît chez les autres en une à deux secondes, sans recharger — accueil et « Le point du jour »,
  caisses, reçus, recouvrement, panier d'encaissement (un autre caissier encaisse le même élève : les frais réglés
  disparaissent aussitôt), élèves, effectifs, intendance, personnel, communication, accès, documents. Le signal ne
  contient que le domaine changé ; chaque écran relit ses données avec les droits du membre.
- **Travail hors ligne pour tous les rôles de l'école** (et non plus seulement la caisse), opérations rejouées sans
  doublon au retour du réseau ; comptes et accès, imports, annulations et clôture de journée restent en ligne.
- **Passe « mobile d'abord »** sur l'école et la plateforme : barre du bas propre à chaque rôle (dont « Encaisser »
  pour qui encaisse), un seul titre par écran, petites cartes en blocs 2 × 2, tableaux en cartes, fenêtres en feuilles.
- Rôles créés par l'école à partir d'un rôle standard (ex. « Assistant du promoteur » depuis le Promoteur).
- Numéro de version standard affiché dans l'application (« Version 1.0.0-rc.1 ») et dans l'avis de mise à jour.
- Encaissement en mode caisse : action conseillée présélectionnée au choix de l'élève.
- Téléphone : barre d'encaissement fixe (« Encaisser 25 USD », puis « Imprimer »), panier familial depuis la même barre.
- Ordinateur : l'encaissement tient dans la fenêtre (liste qui défile dans sa colonne, panneau « Encaisser » toujours
  visible) et se fait au clavier : recherche → Entrée → Entrée ; F9 encaisser, Échap effacer, F2 rechercher.
- Famille : F4 charge les enfants ; Entrée met l'enfant au panier et ouvre le suivant avec son mois conseillé ;
  au dernier, Entrée (ou F9) encaisse le panier. Même principe sur téléphone (« Au panier », puis « Encaisser le panier »).

### Modifié
- Réseau : « Hors ligne » seulement après vérification (3 échecs sur 10 s) ; retour en ligne après 2 réponses
  d'affilée ; une coupure d'une seconde ne fait plus basculer l'application.
- Après un retour du réseau, la session est revalidée (une révocation est appliquée).

### Corrigé
- L'application installée ne se recharge plus quand on glisse l'écran vers le bas, y compris téléphone tourné.
- **Sécurité** : pypdf 6.21.2 → 6.21.4 et pyasn1 0.6.4 → 0.6.5 (11 failles publiées, détectées par l'audit de la CI).
- Une dépense de caisse rejouée après une réponse perdue n'est plus enregistrée deux fois (idempotence côté serveur).
- La mensualité exigée à l'inscription peut être encaissée avant les mois précédents ; seule elle échappe à l'ordre (PR #29).
- « Superviser les caisses » ouvre bien la Caisse (et non le Recouvrement).
