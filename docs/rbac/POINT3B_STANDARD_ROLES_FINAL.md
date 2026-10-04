# EduSync — Point 3B — rôles standards verrouillés

Date: 2026-09-12

## Doctrine

- Les rôles standards sont des **baselines sûres et stables**. Une école qui veut une variante crée/clone un rôle `SCHOOL_CUSTOM` au lieu de modifier silencieusement le standard.
- Un utilisateur peut cumuler plusieurs rôles. Une fonction métier n’implique jamais automatiquement une autre fonction.
- Les permissions restent des capacités atomiques. Les invariants métier, l’audit, l’idempotence et les règles offline restent supérieurs à la permission.
- Le périmètre est indépendant du rôle. Le Chef de section est limité à `SECTION/CYCLE/CLASS` selon l’affectation.

## Rôles standards

| Rôle | Capacités | Doctrine |
|---|---:|---|
| Manager système / Atelier Pro (`MANAGER_SYSTEME`) | 10 | Plateforme uniquement; notifications système incluses. |
| Administrateur système école (`ADMIN_SYSTEME_ECOLE`) | 84 | Administration technique; aucun métier opérationnel implicite. |
| Promoteur (`PROMOTEUR`) | 104 | Consultation de gouvernance: voir, suivre, imprimer/exporter; aucune mutation métier ou communication parent. |
| Gestionnaire (`GESTIONNAIRE`) | 104 | Gouvernance locale et contrôle; les normes sont décidées administrativement mais paramétrées par un utilisateur technique autorisé. |
| Responsable chargé des finances (`RESPONSABLE_FINANCE`) | 67 | Contrôle et lecture financière globale; pas d’encaissement ni de manipulation de caisse. |
| Préfet des études (`PREFET_ETUDES`) | 79 | Chef de section Secondaire; opérations scolaires et communication parents strictement dans son périmètre. |
| Directeur / Directrice de section (`DIRECTION_SECTION`) | 79 | Même pouvoirs que le Préfet, avec périmètre Primaire, Maternelle, ou les deux. |
| Directeur des études (`DIRECTEUR_ETUDES`) | 41 | Secondaire uniquement; suivi pédagogique/scolaire; Finance lecture optionnelle mais non attribuée par défaut. |
| Directeur de discipline (`DIRECTEUR_DISCIPLINE`) | 38 | Secondaire uniquement; suivi quotidien et communication parents forte. |
| Caissier (`CAISSIER`) | 91 | Opérateur inscription/encaissement; caisse propre détaillée, total agrégé via dashboard, corrections de ses paiements selon workflow audité. |
| Secrétariat (`SECRETARIAT`) | 24 | Rôle optionnel minimal centré production documentaire; pas de Finance par défaut. |
| Intendant (`INTENDANT`) | 29 | Stocks, consommables, matériel durable, inventaires, états/réparations, impressions/exports. |

## Rôles personnalisés

`ASSISTANT_PROMOTEUR` n’est pas figé comme standard. Une école peut cloner `PROMOTEUR` puis cocher/décocher les capacités nécessaires. Le même mécanisme couvre tout titre local supplémentaire.

## Points de sécurité métier verrouillés

- Promoteur: consultation, impression/export, aucune mutation et aucun SMS/communiqué parent.
- Gestionnaire: consultation/contrôle; une décision prise en réunion ne lui donne pas automatiquement la permission de paramétrer EduSync.
- Chef de section: communication parent, personnel et élèves seulement dans son périmètre; transfert/réintégration lui appartiennent.
- Direction des études / discipline: rôles Secondaire seulement; Finance non accordée par défaut au Directeur des études et ajoutable explicitement en lecture.
- Caissier: détail de sa caisse seulement; le total global peut être affiché de manière agrégée via le dashboard; aucune ventilation des collègues par défaut.
- Correction de paiement: jamais d’UPDATE/DELETE silencieux. Réversal audité; propre paiement + caisse encore ouverte. Une caisse clôturée ou le paiement d’un autre caissier exige une autorisation supérieure.
- Secrétariat: rôle facultatif et minimal.
- Intendance: stocks/matériel/inventaires sans transformer le produit en ERP achats/finance.
