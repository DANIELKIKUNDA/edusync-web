# Point 6H — Décisions financières, responsabilités, crédits/trop-perçus

## Décision produit
Le conteneur historique **Suivi opérateur** disparaît. Il mélangeait trois responsabilités financières distinctes.

1. **Décisions & exonérations** : registre métier des exonérations, réductions, prises en charge et autres décisions. Une faveur ne devient jamais un tarif zéro. Création/annulation sont des opérations critiques, serveur uniquement, avec les capacités certifiées existantes.
2. **Responsabilités prévues** : famille, retenue/paie, école ou tiers, avec période d'effet. Le changement de responsable ne réécrit jamais silencieusement les paiements historiques.
3. **Crédits & trop-perçus** : registre de contrôle. Le RBAC existant ne possède que `finance.credits.read`; aucune création/suppression manuelle par le caissier n'est inventée. Les crédits doivent provenir d'un événement financier réel et rester traçables.

## Interface
Le nouvel espace s'appelle **Décisions financières**. Il utilise trois sous-onglets compacts et donne la priorité aux grands tableaux. Pas de mur de KPI/cartes.

## Sécurité
Migration `0022_finance_controls.sql`, RLS + FORCE RLS sur les trois registres. Les décisions sont annulées et tracées, pas supprimées. CDF/USD restent séparés.

## Audit transversal
Le journal d'audit n'est pas réintroduit dans le Centre financier. La cible reste un module transversal système, couvrant Finance, Personnel, Scolarité, Paramètres et Intendance.
