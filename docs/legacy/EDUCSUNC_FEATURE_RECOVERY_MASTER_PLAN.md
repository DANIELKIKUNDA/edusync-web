# Plan directeur de récupération fonctionnelle EducSyn → EduSync Web

Date d'inventaire : 20 novembre 2026

## Décision d'architecture

`edusync-web` demeure l'unique produit de production. Le dépôt historique
`DANIELKIKUNDA/educsunc-platform` sert de catalogue métier, de banque de règles,
de maquettes, de jeux de données et de preuves. Aucun composant TypeScript/Vue ou
Fastify n'est copié directement dans le socle FastAPI/React sans réécriture,
adaptation au modèle actuel, migration, tests de périmètre et validation mobile.

## Taille du patrimoine historique

- 85 workflows officiellement documentés ;
- 18 rôles de sécurité, plus l'acteur dérivé `TITULAIRE` ;
- 10 grands domaines frontend ;
- environ 165 migrations, 557 fichiers de tests et 100 000 lignes de code ;
- référentiels MINEDUC, modèles de bulletins, proclamations et synthèses PDF ;
- architecture multi-organisation, multi-école et multi-périmètre.

## Statuts utilisés

- `PRÉSENT` : capacité déjà disponible dans EduSync Web ;
- `PARTIEL` : fondation présente, parité historique non atteinte ;
- `ABSENT` : capacité à construire ;
- `À AUDITER` : présence probable, mais contrat métier/parité à prouver.

## Inventaire maître

| Domaine | Capacité historique | État dans EduSync Web | Décision |
| --- | --- | --- | --- |
| Gouvernance | Plusieurs organisations, chacune avec plusieurs écoles | PARTIEL | Consolider après les modules pédagogiques essentiels |
| Gouvernance | Registre, création, modification et fiche d'organisation | PARTIEL | Réécrire sur les contrats plateforme actuels |
| Gouvernance | Écoles rattachées et modules autorisés/activés | PARTIEL | Conserver la doctrine modules organisation/école |
| Gouvernance | Synthèse consolidée de 10 à 100 écoles | PARTIEL | Version ultérieure après stabilisation des agrégats |
| Académique | Années scolaires et activation | PRÉSENT | Vérifier la parité et les transitions d'état |
| Académique | Référentiel officiel sections/options/classes/cours | PARTIEL | Récupérer les données et règles, pas l'ancien code |
| Académique | Versions, publication, activation et comparaison de référentiels | ABSENT/PARTIEL | Lot plateforme avancé |
| Académique | Classes pédagogiques et responsabilités de classe | PARTIEL | Nécessaire avant notes et bulletins |
| Académique | Calendrier académique | ABSENT | Après le socle pédagogique |
| Académique | Programmes locaux par niveau/classe | ABSENT | Après référentiel officiel |
| Scolarité | Inscription complète | PRÉSENT | Préserver la production |
| Scolarité | Registre et dossier élève | PRÉSENT | Vérifier la parité des champs et documents |
| Scolarité | Familles, responsables et liens parent-enfant | PARTIEL | Priorité haute |
| Scolarité | Affectation élève-classe | PRÉSENT/PARTIEL | Vérifier historique et périmètres |
| Scolarité | Cycle de vie : transfert, promotion, réinscription, sortie | PARTIEL | Industrialiser par états et audit |
| Scolarité | Suspension et réactivation | À AUDITER | Porter uniquement si besoin terrain validé |
| Pédagogie | Fiche de cotation électronique | ABSENT | Priorité majeure |
| Pédagogie | Saisie des notes par enseignant et cours affectés | ABSENT | Priorité majeure |
| Pédagogie | Contrôle des périodes, maximums et verrouillages | ABSENT | Inclus dans le moteur de cotation |
| Pédagogie | Calcul des résultats et totaux | ABSENT | Après cotation certifiée |
| Pédagogie | Analyse des résultats | ABSENT | Après calcul des résultats |
| Pédagogie | Détail du résultat d'un élève | ABSENT | Après calcul des résultats |
| Pédagogie | Statistiques par classe/section/école | ABSENT | Après agrégats pédagogiques |
| Pédagogie | Classement de classe | ABSENT | Politique configurable et auditée |
| Pédagogie | Encodage de la conduite | ABSENT | Lot discipline |
| Pédagogie | Génération des bulletins officiels | ABSENT | Priorité haute après résultats |
| Pédagogie | Génération des proclamations | ABSENT | Après bulletins |
| Pédagogie | Modèles MINEDUC et calibration PDF | ABSENT | Réutiliser les assets et zones historiques |
| Finance | Perception, reçus, caisse et clôture | PRÉSENT | Ne pas remplacer le moteur de production |
| Finance | Historique et situation financière élève | PRÉSENT | Continuer l'industrialisation mobile |
| Finance | Arriérés, recouvrement et registre de classe | PRÉSENT | Vérifier la parité des agrégats |
| Finance | Synthèse classe, section, école, organisation | PARTIEL | Ajouter progressivement le niveau organisation |
| Finance | Exonérations | PRÉSENT/PARTIEL | Auditer les règles et validations |
| Finance | Restitution d'excédent | À AUDITER | Porter seulement avec workflow d'autorisation |
| Finance | Fonds anticipés | PARTIEL | Comparer les règles anciennes et actuelles |
| Finance | Analyse par type de frais | PARTIEL | Consolider les rapports actuels |
| Finance | Paiements par caissier | PRÉSENT/PARTIEL | Vérifier multi-caissier et clôtures |
| Finance | Tarification et paramètres de paiement | PRÉSENT | Préserver le modèle actuel |
| Finance | Rapports journalier, hebdomadaire, mensuel, période | PRÉSENT/PARTIEL | Achever détails, justificatifs et exports |
| Parent | Compte parent | ABSENT/PARTIEL | Priorité haute après liens familiaux |
| Parent | Enfants autorisés uniquement | ABSENT/PARTIEL | Contrôle serveur obligatoire |
| Parent | Consultation dette et historique des paiements | ABSENT | Premier portail parent livrable |
| Parent | Consultation résultats et bulletin | ABSENT | Après certification pédagogique |
| Parent | Notifications liées à l'enfant | PARTIEL | Brancher sur le centre existant |
| Personnel | Enseignants, fonctions et affectations | PRÉSENT/PARTIEL | Enrichir avec cours/classes |
| Personnel | Titulariat comme capacité dérivée, pas comme rôle | PARTIEL | Conserver cette doctrine |
| Personnel | Responsables par section | PRÉSENT/PARTIEL | Continuer le filtrage par périmètre |
| Sécurité | Rôles, permissions et restrictions | PRÉSENT | Le moteur actuel reste autoritaire |
| Sécurité | Scopes plateforme/organisation/école/section/classe/cours | PARTIEL | Compléter avant pédagogie et parent |
| Sécurité | Sessions, révocation, verrouillage et tentatives | PRÉSENT/PARTIEL | Comparer les protections historiques |
| Sécurité | Administration des rôles personnalisés | PARTIEL | Version plateforme avancée |
| Audit | Journaux plateforme, organisation, école et pédagogie | PARTIEL | Étendre aux nouvelles écritures métier |
| Audit | Export, replay, rétention et intégrité | ABSENT/PARTIEL | Lot conformité avancé |
| Notifications | Centre école, organisation et plateforme | PRÉSENT/PARTIEL | Consolider plutôt que dupliquer |
| Notifications | Temps réel, escalades et dead-letter | PARTIEL | Récupérer les règles d'exploitation utiles |
| Monitoring | Santé, métriques, alertes et incidents | PARTIEL | Après les priorités métier |
| Monitoring | Diagnostics, traces, capacité et saturation | ABSENT/PARTIEL | Lot exploitation plateforme |
| Configuration | Configuration plateforme/organisation/école/utilisateur | PARTIEL | Unifier avec les paramètres actuels |
| Configuration | Branding école | PARTIEL | Vérifier logo, identité et documents |
| Hors ligne | Consultation hors connexion par rôle | PRÉSENT/PARTIEL | Étendre selon les données sensibles |
| Hors ligne | File d'écritures idempotentes chiffrées | PRÉSENT/PARTIEL | Ne pas régresser le protocole actuel |

## Rôles et acteurs historiques à conserver dans la cible

### Plateforme

- `MANAGER_SYSTEME`
- `OPERATEUR_SYSTEME`
- `SUPPORT_SYSTEME`

### Organisation

- `PROMOTEUR_ORGANISATION`
- `ADMIN_SYSTEME_ORGANISATION`
- `GESTIONNAIRE_ORGANISATION`

### École et pédagogie

- `ADMINISTRATEUR_ECOLE`
- `ADMIN_SYSTEME_ECOLE`
- `PREFET_ETUDES`
- `DIRECTEUR_ETUDES`
- `DIRECTEUR_DISCIPLINE`
- `DIRECTEUR_PRIMAIRE`
- `DIRECTEUR_MATERNELLE`
- `ENSEIGNANT`
- `CAISSIER`
- `COMPTABLE`

### Externe et dérivé

- `PARENT`
- `TITULAIRE`, uniquement comme capacité dérivée d'un enseignant affecté.

Chaque rôle doit recevoir une projection calculée par le backend. Une interface ne
doit jamais fusionner plusieurs rôles pour créer implicitement plus de droits.

## Ordre de montée de version recommandé

### V1.0-SaaS — Abonnements et commercialisation (priorité immédiate)

Cette fondation passe avant la récupération pédagogique. Elle ne modifie pas les
workflows école déjà en production et reste indépendante du prestataire de paiement.
Le cahier d'implémentation détaillé est
[`docs/subscriptions/SAAS_SUBSCRIPTION_IMPLEMENTATION_PLAN.md`](../subscriptions/SAAS_SUBSCRIPTION_IMPLEMENTATION_PLAN.md).

1. catalogue de plans et prix versionnés ;
2. modules activables par école et droits d'usage (`entitlements`) ;
3. abonnements mensuels, trimestriels et annuels ;
4. factures, paiements, reçus et rapprochement ;
5. rappels automatiques, période de grâce et relances ;
6. mode limité puis suspension commerciale sans suppression des données ;
7. réactivation automatique après confirmation du paiement ;
8. webhooks signés, idempotence et journal d'audit ;
9. premier connecteur Mobile Money en sandbox, remplaçable sans toucher au domaine ;
10. cockpit Volcano Tech : revenus, échéances, impayés et modules actifs.

La suspension commerciale ne doit pas réutiliser aveuglément la suspension technique
d'une école : l'accès à la facture, au paiement, aux exports de restitution et au
support doit rester disponible. Les données ne sont jamais supprimées pour impayé.

### V1.1 — Socle pédagogique et liens familiaux

1. cours, enseignants et affectations cours/classes ;
2. responsabilités et titulariats ;
3. familles et lien sécurisé parent-enfant ;
4. scopes section, classe et cours ;
5. audit des changements.

### V1.2 — Cotation

1. périodes et règles de cotation ;
2. fiche de cotation électronique ;
3. saisie enseignant mobile et hors ligne contrôlé ;
4. verrouillage, validation et correction auditée ;
5. tests de périmètre enseignant/directeur/préfet.

### V1.3 — Résultats et pilotage pédagogique

1. moteur de calcul ;
2. détails par élève ;
3. statistiques classe/section/école ;
4. classements selon politique d'école ;
5. centre d'analyse pédagogique.

### V1.4 — Bulletins et proclamations

1. modèles officiels MINEDUC ;
2. génération PDF ;
3. contrôle et publication ;
4. proclamations et synthèses ;
5. historique et réédition.

### V1.5 — Portail parent

1. activation/invitation du compte ;
2. sélection de l'enfant autorisé ;
3. dette et paiements ;
4. résultats et bulletin publié ;
5. notifications ciblées et préférences.

### V1.6 — Groupe scolaire multi-écoles

1. organisations et rattachement des écoles ;
2. tableaux consolidés finance/effectifs/pédagogie ;
3. comparaison des écoles ;
4. délégations organisationnelles ;
5. exports consolidés.

### V1.7 — Exploitation avancée

1. audit enrichi ;
2. monitoring, incidents et diagnostics ;
3. configuration hiérarchique ;
4. référentiel officiel versionné ;
5. gouvernance avancée de plateforme.

## Plan de six semaines

| Semaine | Résultat attendu |
| --- | --- |
| 1 | Domaine abonnement, plans, modules, factures, grâce et migrations |
| 2 | Cockpit, relances, paiement manuel contrôlé et connecteur sandbox |
| 3 | Affectations pédagogiques, titulariat, familles et parent-enfant |
| 4 | Cotation : domaine, API, sécurité, audit et première UI mobile |
| 5 | Calculs, résultats, statistiques et premiers bulletins officiels |
| 6 | Stabilisation, responsive, pilote abonnement et pilote pédagogique |

Ce calendrier vise un premier ensemble pédagogique utilisable. Il ne prétend pas
porter les 85 workflows en six semaines. Les modules multi-écoles avancés,
monitoring et gouvernance plateforme continuent ensuite par versions.

## Garde-fous obligatoires pour chaque récupération

1. Écrire le contrat métier cible avant le code.
2. Conserver FastAPI, React, PostgreSQL/RLS et le modèle de production actuel.
3. Migrer les données par scripts versionnés et réversibles.
4. Vérifier permission et périmètre côté backend, jamais seulement dans l'UI.
5. Concevoir mobile dès la première maquette.
6. Ajouter tests unitaires, intégration PostgreSQL, API, navigateur et rôles.
7. Activer par feature flag ou module d'école.
8. Déployer d'abord en staging avec une école pilote.
9. Prévoir rollback et sauvegarde avant chaque migration.
10. Ne jamais perturber encaissement, inscription ou rapports déjà en production.

## Prochaine spécification à produire

La première étude détaillée doit être `V1.1 — fondations pédagogiques` : modèle
des cours, affectations enseignant-classe-cours, périodes, titulariat, familles,
lien parent-enfant et matrice exacte des rôles. Elle constitue la dépendance de
la cotation, des résultats, des bulletins et du portail parent.
