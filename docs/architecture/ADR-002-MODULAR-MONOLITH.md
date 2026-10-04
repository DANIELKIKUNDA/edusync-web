# ADR-002 — DDD + Clean + Hexagonale en monolithe modulaire

**Décision : acceptée et verrouillée.**

La cible initiale est un monolithe modulaire FastAPI structuré en bounded contexts. Le domaine et les use cases sont indépendants des frameworks. Les ports isolent DB, cache, documents, notifications et synchronisation. Les microservices sont différés jusqu'à preuve d'un besoin opérationnel réel.
