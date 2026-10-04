# WEB-0C — Gates

## Gate local

| Contrôle | Verdict |
|---|---|
| Compilation Python `src/tests/scripts` | PASS |
| Pytest | PASS — 41/41 |
| JSON frontend / manifest | PASS |
| YAML Docker Compose | PASS |
| Syntaxe Service Worker | PASS |
| Transpilation syntaxique TS/TSX | PASS — 4/4 |
| Header dev Atelier Pro supprimé | PASS |
| PostgreSQL adapters Atelier Pro | PASS statique/unitaire |
| JWT + Argon2 + versions de jeton | PASS statique/unitaire |
| RLS/FORCE RLS migration | PASS statique |
| Owner secret absent du conteneur API | PASS statique |
| Idempotence replay/conflit/retry | PASS unitaire |
| Double-submit thread-safe mémoire | PASS unitaire |
| Redis cache explicitement scoped | PASS unitaire |
| Service Worker ne cache pas l'API | PASS statique |

## G1 LIVE PostgreSQL — script `g1_live_certification.py`

Le script doit prouver sur PostgreSQL réel :

- rôles DB applicatifs sans superuser/BYPASSRLS/CREATEROLE/CREATEDB ;
- École A ne lit pas École B ;
- utilisateur A ne lit pas utilisateur B ;
- membership A ne lit pas membership B ;
- École A ne peut pas écrire un audit pour École B ;
- le rôle tenant ne peut pas `SET ROLE edusync_platform` ;
- deux CAS concurrents sur la même version produisent exactement un gagnant ;
- deux réservations idempotentes concurrentes produisent exactement un propriétaire logique.

## G1 LIVE API — script `g1_api_probe.py`

Le script doit prouver :

- Atelier Pro refuse l'absence de Bearer ;
- login JWT plateforme valide ;
- deux créations concurrentes avec la même `Idempotency-Key` créent une seule école et rejouent le même résultat ;
- même clé + payload différent → 409 ;
- bootstrap admin école ;
- login JWT école ;
- résolution du contexte école via RLS + permissions DB ;
- token école refusé sur Atelier Pro ;
- école de probe suspendue à la fin pour conserver une trace non-production.

## Gate explicitement non fermé ici

Le présent environnement n'a pas Docker/PostgreSQL live ni les dépendances npm installées. Par conséquent :

- build Docker réel : **À EXÉCUTER** ;
- migrations PostgreSQL réelles : **À EXÉCUTER** ;
- G1 DB live : **À EXÉCUTER** ;
- G1 API live : **À EXÉCUTER** ;
- `npm run build` complet avec dépendances résolues : **À EXÉCUTER**.

**Verdict global actuel : `READY_FOR_G1_LIVE`, pas `G1_PASS`.**
