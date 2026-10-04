# ADR-001 — VPS distant et multi-école

**Décision : acceptée et verrouillée.**

EduSync Web est hébergé sur un VPS distant. Aucune école n'a besoin d'un serveur local. Le produit est multi-école, avec Atelier Pro comme niveau de plateforme léger. La séparation tenant repose sur le contexte serveur + `school_id` + RLS/FORCE RLS et des namespaces cohérents dans tous les stockages secondaires.

Conséquence : une coupure Internet ne doit pas rendre le produit inutilisable; la PWA et le moteur de synchronisation sont des composants de premier rang.
