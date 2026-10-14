# Parité Paramètres ↔ Finance — plan de portage (avant N3 Finance)

Date : 2026-10-14. Décision du propriétaire : remettre les Paramètres Web au niveau fonctionnel du Desktop pour tout ce
dont la Finance dépend, puis seulement certifier N3 Finance. Source de vérité : golden master Desktop
(`C:\Users\cs-ap\dev\edusync-desktop-golden`, EduSync École Offline 0.11.0-rc.1, lecture seule).
Doctrine : COPIER → COMPARER → CERTIFIER LA PARITÉ → ENRICHIR. Aucune règle Finance redéfinie.

## Chaîne Desktop à reproduire

```
types de frais (périodicité)  ─┐
règles tarifaires datées       ├─► résolution par classe et par date ─► échéances par classe ─► frais dus par élève
groupes tarifaires d'options   │     (classe 600 > classe académique 500      (mensuel : un poste par mois     (réduction d'avantage,
mois de facturation            ─┘      > groupe d'Humanités 350 > section 200   facturé ; tranche : 3 postes ;    jamais sous le déjà payé)
                                       > école 100 ; statut ACTIVE et montant)  autre : un poste)
conditions d'admission ─► à l'inscription          règles d'encaissement ─► caisse (partiel, minimum, mois futurs, modes)
avantages (par année) ─► désignation à l'inscription + réduction        plans anticipés ─► imputation mois courant puis mois ciblés
documents ─► préfixes, copies, signataire, formats
```

Sources Desktop : `app/db/configuration.py` (tarifs, groupes, mois, conditions, avantages, encaissement, documents),
`app/db/database.py:349-480` (échéances, génération des frais), `app/db/schooling.py` (inscription, avantages),
`app/db/finance_checkout.py` (caisse), `app/db/anticipation.py` (plans), `app/domain/benefits.py`, `app/db/schema.sql`.

## Lots

| Lot | Contenu Desktop | État Web avant | Travail |
|-----|-----------------|----------------|---------|
| L1 Tarifs | règles tarifaires (portée école / section / classe académique / classe), date d'effet, statut ACTIVE / PENDING_OFFICIAL / INACTIVE, référence officielle ; groupes d'Humanités GENERAL / TECHNICAL / OTHER et leurs règles ; mois de facturation et mois exigé à l'inscription ; résolution par priorité | tarifs par classe ou section, sans date ni statut ni groupe ; mois par tarif | étendre `tariffs` (portée, date d'effet, statut, référence, groupe), liste fermée des groupes sur les options, politique des mois, résolution identique, écrans |
| L2 Échéances et frais dus | « Appliquer les barèmes aux classes » → échéances par classe ; frais dus par élève générés à l'application et à l'inscription ; modification interdite si déjà payé ; jamais sous le déjà payé | **absent** (frais créés par import ou SQL) | échéances + génération dans `finance_charges` (type de frais, période, date d'échéance, ordre), mêmes protections |
| L3 Avantages | politique par année (famille nombreuse : seuil, gratuits, % ; personnel : plafond par agent, %, gratuits ; frais concerné), cumul interdit, réduction sur les frais, désignation manuelle à l'inscription | règles codées en dur, sans effet financier, pas de désignation dans l'interface | table de politiques par année, contrôles à l'inscription, réduction portée par le frais dû, écran Avantages, cases dans l'assistant d'inscription |
| L4 Conditions d'admission | obligations annuelles (frais lié, obligatoire, moment, différé possible, regroupement, portée), validation de la rubrique | absent | table + écran + lecture à l'inscription |
| L5 Règles d'encaissement | partiel oui/non, acompte minimum, présentation dans les rapports, anticipé, mois futurs, modes acceptés | règles codées en dur, aucun mode de paiement | politique lue par la caisse, mode de paiement enregistré, présentation des acomptes dans le recouvrement |
| L6 Plans anticipés | plans (portée dont groupe d'Humanités, mois ciblés, répartition, facultatif / obligatoire, date d'effet), adhésions, échéancier | lus à la caisse, non créables | création, activation, écran, comparaison fine de l'imputation |
| L7 Documents | préfixes reçus / rapports, copies, format 80 mm / 58 mm / A5, impression automatique, signataire, logo | format A5 / 80 mm, politique d'impression, logo | compléter les réglages et les brancher sur la numérotation et les PDF |

Hors parité (décision du propriétaire) : restauration directe par l'école (`NOT_APPLICABLE_IN_SAAS`) ; SMS et
communications (`WEB_EXTENSION`, ne bloque pas).

Chaque lot : migration, dépôt, routes avec droits du registre (`settings.*` déjà présents), écran mobile-first, tests de
contrat, sonde réelle, commit. À la fin : comparaison des 13 rubriques (`PARITY_OK` / `PARITY_GAP` / `WEB_EXTENSION` /
`NOT_APPLICABLE_IN_SAAS`), tests N2 affectés, régression N0/N1, tag sur le SHA retesté.
