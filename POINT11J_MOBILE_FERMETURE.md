# Point 11J — Fermeture mobile / Retour Android

## Implémenté
- Coordination réelle avec l'historique navigateur/PWA (`pushState`, `replaceState`, `popstate`).
- Retour Android ferme d'abord la couche transitoire supérieure : bottom-sheet, modal/wizard, drawer, dialogue.
- Ensuite, retour vers l'écran/module précédent pour l'espace École et Atelier Pro.
- L'historique ne contient ni token ni donnée métier.
- Protection `beforeunload` pour formulaires modifiés avant sortie/rechargement navigateur.
- La racine n'est pas piégée : sans écran antérieur EduSync, le navigateur/PWA garde son comportement de sortie normal.

## Limites de certification
La logique est implémentée et couverte par les gates statiques/tests. Le comportement matériel de la touche Retour, le clavier virtuel, la PWA installée et les gestes système doivent encore être certifiés sur un appareil Android réel avec le build Vite de production.
