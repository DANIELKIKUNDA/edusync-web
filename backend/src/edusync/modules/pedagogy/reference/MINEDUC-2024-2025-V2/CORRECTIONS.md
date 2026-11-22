# Référentiel officiel MINEDUC 2024-2025 (version V2)

## Provenance

Ces données viennent du projet père `DANIELKIKUNDA/educsunc-platform`, dossier `docs/donnees-reference/referentiel-academique` (commit `4dc18864`). Elles ont été extraites des bulletins officiels du MINEDUC 2024-2025.

| Fichier | Contenu | Nombre |
|---|---|---|
| `sections.json` | Maternelle, Primaire, Secondaire | 3 |
| `options.json` | options d'études : code officiel, sigle et groupe (GENERAL, GROUPE_1, GROUPE_2) | 51 |
| `classes.json` | classes officielles : section, option, cycle, structure d'évaluation | 215 |
| `courses.json` | cours officiels, chacun présent une seule fois | 485 |
| `programmes.json` | programmes par classe : ordre du bulletin, maxima P1 P2 EX1 P3 P4 EX2 P5 P6 EX3 | 130 programmes, 2 658 lignes |

**Structures d'évaluation**
- Primaire : trimestriel, soit P1 à P6 et EX1 à EX3.
- 7e et 8e EB, et humanités : semestriel. P5, P6 et EX3 valent toujours 0.

## Corrections du propriétaire (22/11/2026)

Règles : **« l'examen est toujours le double de la période »** ; un cours sans examen n'a aucun point d'examen, et ses périodes valent la même chose.

| Classe | Cours | Champ | Avant | Après |
|---|---|---|---|---|
| 2HYDRO | Français | EX1 | 10 | 100 |
| 2HYDRO | Mathématiques | EX1 | 10 | 100 |
| 3SC | Systématique et Jardinage | EX1, EX2 | 20 | 40 |
| 3SC | Géologie / Écologie | EX1, EX2 | 20 | 40 |
| 4HR | Pratique professionnelle (sans examen) | P3 | 200 | 100 |

27 noms étaient mal encodés dans la source (par exemple « PÃ©dagogie » au lieu de « Pédagogie ») ; ils ont été réparés.

Les intitulés de domaine utilisent désormais tous la même apostrophe. Par exemple, « L’UNIVERS SOCIAL ET ENVIRONNEMENT » s'écrivait de deux façons.

## Ce qui manque dans la source

- Aucun programme pour la maternelle, 3NOR et 4NOR.
- Aucun programme pour 20 options : AD, EC, HA, TOUR, CHI, EI, IMP, COM, RT, METEO, AC, MD, PETRO, CM, MINGEO, METAL, DB, PIS, MC et GEO.

EduSync signale ces classes à l'école, sans rien inventer.

## Contrôles

Ces règles sont vérifiées à chaque chargement et par la base elle-même :
- chaque cours existe ;
- un cours n'apparaît qu'une fois par programme ;
- une classe semestrielle a P5, P6 et EX3 à 0 ;
- un cours avec examen a EX = 2 × P pour chaque période ;
- un cours sans examen a tous ses examens à 0.
