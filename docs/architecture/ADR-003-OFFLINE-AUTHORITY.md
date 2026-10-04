# ADR-003 — Offline par autorité bornée, pas par blocage global

**Décision : acceptée et verrouillée.**

EduSync classe les opérations selon leur preuve de finalité. Les activités scolaires courantes restent disponibles offline quand elles peuvent être synchronisées avec conflit explicite. Les écritures critiques finales exigent une autorité préalablement accordée et bornée. Les écritures nécessitant une preuve externe ou modifiant les pouvoirs d'accès restent online pour leur finalité.

Cette décision privilégie simultanément la disponibilité dans un contexte Internet instable et l'intégrité du système.
