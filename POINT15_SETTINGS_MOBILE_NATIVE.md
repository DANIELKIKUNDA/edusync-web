# Point 15 — Paramètres réels et mobile natif

- Suppression des onglets Paramètres qui n’étaient que des cartes contractuelles sans interface métier.
- École & identité devient éditable via le backend existant, avec contrôle de version et idempotence serveur.
- Tarifs & barèmes permet la création d’un tarif réel pour l’année courante, avec ciblage classe optionnel.
- Contributions en nature et Articles scolaires deviennent des interfaces réelles adossées aux endpoints existants.
- Mobile Atelier Pro : annuaire écoles, accès, audit et notifications passent d’un grand tableau horizontal à des cartes tactiles.
- Readiness mobile reste compacte en grille 2×2.
- Les politiques génériques PAYMENT/ENROLLMENT/BENEFITS ne sont pas exposées comme faux réglages tant que leur contrat UI métier n’est pas suffisamment spécifique.
- Les dépendances `latest` ne sont pas figées sans résolution npm fiable ; aucune version n’est inventée.
