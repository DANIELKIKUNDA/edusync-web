# Kit d’interface EduSync (École et Plateforme) — 24/10/2026

Composants : `frontend/src/platform/ui.tsx` · styles : `frontend/src/platform/ui.css` (jetons `--es-*` du shell : thème
clair et sombre suivent). À réutiliser dans Élèves, Finance, Personnel, Documents… plutôt que de recréer des styles.

| Composant | Usage | Règles |
|---|---|---|
| `PageHeader` | En-tête de page : surtitre, titre, sous-titre orienté usage, actions, encart | Une seule action primaire |
| `Section` | Groupe de cartes avec titre | Titre court, sous-titre facultatif |
| `Card` | 3 niveaux : `priority` (action attendue), `info` (un chiffre), `secondary` (contexte) | Avec `onClick`, la carte entière est le bouton : **jamais de « Voir » à l’intérieur**, chevron discret en haut à droite |
| `StatusBadge` | `ok` Configuré · `todo` À compléter · `warn` À vérifier · `blocked` Prioritaire · `neutral` Facultatif · `locked` · `brand` | Texte toujours présent (pas seulement la couleur) |
| `Button` | `primary` / `secondary` / `quiet` / `danger`, tailles `md` (44 px) / `sm` | 44 px minimum sur téléphone |
| `ProgressRing`, `ProgressJourney` | Pourcentage + étapes restantes avec statut, priorité et action directe | Étapes prioritaires en premier |
| `Skeleton`, `EmptyState` | Chargement, état vide | Même géométrie que le contenu |
| `ScreenError`, `ScreenBoundary` (`screen_boundary.tsx`) | Erreur localisée avec « Réessayer » | Le shell ne disparaît jamais |
| `PageTrail` (`navigation.tsx`) | Fil d’Ariane bureau, bouton retour sur téléphone | Parents fournis par l’écran autorisé |

Accessibilité : focus clavier visible (`--es-focus`), `prefers-reduced-motion` coupe animations et transitions, cibles
tactiles ≥ 44 px, `env(safe-area-inset-bottom)` en bas de page, contrastes des badges sur fond doux.
Mouvement : apparition 320 ms décalée (`--i`), survol −2 px + ombre, pression scale(.992). Aucune dépendance ajoutée.

Écrans passés au kit : accueil École (`home.tsx`), Paramètres École (`App.tsx` : `SettingsHome`, navigation groupée avec
pastilles d’état, fil d’Ariane jusqu’à la sous-section). Libellés du journal : `platform/labels.ts` (aucun code technique
affiché). Captures avant/après : `browser-tests/capture_school.spec.ts` (`EDUSYNC_CAPTURE=before|after`).
