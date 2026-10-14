# N2 — Audit UX des assistants (wizards) et parcours multi-étapes

Date : 2026-10-14. Base : code du dépôt (frontend/src) au commit audité, parcours réels dans le navigateur
(certification/n2-20261014). Périmètre : parcours d'administration de l'école (N2) et assistants existants
qu'ils croisent.

## 1. Inventaire

| Parcours | Où | Forme | Étapes | Statut N2 |
|----------|----|-------|--------|-----------|
| Mise en service de l'école | Paramètres › Mise en service | Liste de préparation avec **prochaine étape** et liens « Ouvrir » | Identité → Année → Structure → Types de frais → Tarifs (ordre du serveur) | **construit en N2** : guidé, pas d'assistant bloquant |
| Ajout d'un membre | Accès & rôles › Ajouter un membre | Boîte de dialogue, puis écran du mot de passe provisoire (une seule fois, copie, case de confirmation) | 2 | **construit en N2** |
| Première connexion avec mot de passe provisoire | Connexion | Écran dédié avant toute session | 1 (+ reconnexion automatique) | **construit en N2** |
| Préparation d'une année | Paramètres › Années | Formulaire replié derrière « Préparer une nouvelle année », année suivante proposée | 1 | **refait en N2** |
| Ouverture d'une classe | Paramètres › Structure | Section → classe (filtrée par section) → option facultative | 1 écran, choix en cascade | **refait en N2** |
| Inscription d'un élève | Élèves & inscriptions | `EnrollmentWizard` (schooling.tsx) : foyer → enfants → confirmation | 3 | existant (N3) — non modifié |
| Création d'une école | Atelier Pro (plateforme) | school_create.tsx, enchaîne sur l'administrateur initial | 2 | existant (N1) — non modifié |

## 2. Critères et résultats

| Critère | Mise en service | Ajout d'un membre | 1re connexion | Année | Classe |
|---------|-----------------|-------------------|---------------|-------|--------|
| Un objectif clair par écran | oui (« Prochaine étape ») | oui | oui | oui | oui |
| Retour possible sans perte | oui (liste ↔ section, retour Android) | Annuler / Échap | — | Annuler | — |
| Valeurs par défaut utiles, jamais fictives | rien n'est pré-rempli | — | — | année suivante proposée, modifiable | classes de référence de la section choisie |
| Erreur expliquée sur place, avec la correction | message du serveur sous l'écran | sous le champ | sous le champ, mot de passe identique refusé | sous le champ (« La fin d'année doit venir après la rentrée. ») | message en tête |
| Action lourde confirmée | — | secret montré une fois, case « J'ai transmis » | — | activation/clôture/archivage/réouverture confirmés | désactivation confirmée |
| Rejeu sans doublon | — | clé d'idempotence ; le rejeu ne renvoie jamais le mot de passe | jeton à usage unique | clé d'idempotence | clé d'idempotence |
| Téléphone 320 px | oui | feuille du bas | oui | une colonne, boutons 48 px | une colonne |

## 3. Constats et décisions

1. **Pas d'assistant bloquant pour la mise en service.** Le serveur déclare `global_blocking: false` : chaque action
   n'est bloquée que par son propre prérequis. Un assistant obligatoire contredirait ce principe. On guide donc
   (prochaine étape + liens) sans enfermer.
2. **L'inscription d'un élève** (3 étapes) relève du N3 et n'a pas été modifiée. Point à reprendre en N3 :
   indicateur d'étapes lisible au lecteur d'écran (`aria-current="step"`).
3. **Aucun assistant n'invente de données** : pas de classes, tarifs ou membres d'exemple.

## 4. Écarts reportés (N3)

- Assistant pas à pas facultatif de première configuration (même ordre que la liste de préparation), utile
  pour une école qui démarre de zéro : voir SCHOOL_ONBOARDING_GAP_REPORT.md.
- `EnrollmentWizard` : indicateur d'étapes accessible, enregistrement du brouillon.
