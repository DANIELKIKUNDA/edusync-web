# Point 14 — Mobile premium et collaboration Atelier Pro

## Fermeture réalisée
- KPI/cartes mobiles normalisés en grille compacte 2×2 sur Cockpit, Scolarité, Personnel, Effectifs et tableaux de bord; conservation de cartes compactes même sur très petits écrans.
- Navigation mobile Atelier Pro existante conservée: barre basse, feuille « Plus », cibles tactiles et modales en bottom-sheet.
- Nouveau rôle plateforme `COLLABORATEUR_PLATEFORME`, actif et à privilèges minimaux: lecture écoles, audit plateforme et diagnostics.
- Nouvelle capacité critique `platform.collaborators.manage`, accordée uniquement au `MANAGER_SYSTEME`.
- Attribution/retrait du collaborateur depuis Accès Atelier Pro, avec motif, verrouillage `FOR UPDATE`, audit et révocation des sessions plateforme lors du retrait.
- La connexion Atelier Pro est désormais fondée sur un rôle RBAC plateforme actif et non exclusivement sur le drapeau historique `is_platform_admin`.
- Correction supplémentaire détectée pendant l’audit: le refresh de session utilisait encore l’ancien nom `memberships`; il utilise désormais `school_memberships`.

## Doctrine
Le Collaborateur plateforme n’est pas un second super-administrateur. Par défaut il ne peut pas créer/suspendre une école, créer un administrateur initial, gérer les accès école, envoyer des notifications système ni déléguer lui-même l’accès plateforme. Les pouvoirs restent atomiques et pourront être élargis explicitement plus tard.

## Validation locale
- pytest: 438/438 PASS
- compileall backend: PASS
- frontend Vite/TypeScript: non exécuté, `node_modules` absent.
- PostgreSQL/Redis/Docker/browser/appareil réel: non certifiés dans cet environnement.
