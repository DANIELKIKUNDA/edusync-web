# Point 6G — Rapports dynamiques + audit « Suivi opérateur »

## Rapports
- Suppression doctrinale des rapports propres à une école codés en dur.
- 4 modèles système non supprimables: Rapport journalier de caisse, Journal des mouvements, Situation des encaissements, Situation consolidée des caisses.
- Modèles personnalisés par école: rubriques + périmètre; données issues des opérations réellement configurées.
- Périodes: aujourd’hui, semaine, mois, personnalisée.
- Périmètres: ma caisse / un caissier / toutes les caisses, sous RBAC.
- CDF et USD séparés.
- Une dette ancienne encaissée aujourd’hui appartient au rapport de caisse d’aujourd’hui tout en conservant l’année d’origine de l’obligation.
- UI dense: barre de critères compacte, tableau dominant.

## Audit « Suivi opérateur »
Verdict: le libellé/onglet « Suivi opérateur » n’est pas un bon agrégat métier et ne doit pas survivre comme fourre-tout.
Cependant ses 3 domaines sont importants et NE DOIVENT PAS être supprimés:
1. Décisions financières / exonérations: critiques, serveur seulement, auditées; à ranger sous « Décisions financières » pour rôles autorisés.
2. Responsabilité prévue (famille/paie/tiers): donnée métier importante pour déterminer qui supporte l’obligation; mutation critique et auditée.
3. Crédits / trop-perçus: contrôle financier nécessaire pour résidus, remboursements/imputations; lecture haute sensibilité.

Ils ne sont pas des opérations quotidiennes à encombrer dans le guichet du caissier. L’audit technique global doit devenir un module transversal séparé, pas un sous-onglet du Centre financier.
