# N2 — Écarts du design system

Date : 2026-10-14. Constat mesuré dans N2_UI_STACK_AUDIT.md. Ce document dit ce qui manque pour parler d'un design
system unifié, ce qui a été fait en N2, et ce qui est reporté.

## 1. Ce qui existe

- **Jetons du shell** (`platform/shell.css`, préfixe `--es-*`) : marque, encres, fonds, lignes, états (ok, warn,
  bad), largeur de la barre (`--es-side:216px`), du rail (`--es-rail:64px`), hauteur de la barre du haut.
- **Composants communs** : `AppShell`, `StatusChip`, `AccountMenu`, `FormField`, `formDefaults`, `promptText`,
  `confirmAction` (N2), `formatMoney` / `formatDate` (N2), `Panel`, `Kpi`, icônes `NavGlyph`.
- **Motifs récurrents** : cartes de liste (`cardsList`), pastilles d'état (`pill`, `status`), feuille du bas sur
  téléphone (`mobileSheetBackdrop`, `memberSheet`), barre du bas (`es-bottom`).

## 2. Écarts

| # | Écart | Gravité | Fait en N2 | Reste à faire |
|---|-------|---------|------------|---------------|
| G1 | 468 couleurs hexadécimales distinctes ; les jetons `--es-*` ne sont utilisés que par le shell | moyenne | nouvelles feuilles N2 limitées à la palette du shell (bleu `#0f4fbf`, encres ardoise, rouge `#b91c1c`, vert) | remplacer les couleurs en dur par les jetons, feuille par feuille |
| G2 | 92 `!important`, surtout dans `styles.css` et `modern.css` (couches qui se contredisent) | moyenne | aucune nouvelle couche contradictoire ; les surcharges N2 sont ciblées sur leur écran | supprimer `modern.css` en reportant ses règles dans les feuilles d'origine |
| G3 | `styles.css` compacté (lignes de plus de 2 000 caractères), difficile à relire | moyenne | — | reformater sans changement visuel (vérifiable par captures avant/après) |
| G4 | Deux familles de boutons (`primaryBtn`/`softBtn`/`ghost` et styles locaux par écran) | faible | boutons N2 sur `primaryBtn`/`softBtn`/`ghost` ; état désactivé visible | composant `Button` unique |
| G5 | Échelle typographique non formalisée (tailles en dur de 11,5 à 22 px) | faible | — | 5 tailles nommées |
| G6 | Échelle d'espacement non formalisée | faible | — | jetons d'espacement 4/8/12/16/24 |
| G7 | Pas de composant « liste de réglages » réutilisable | faible | motifs `classList`, `moneyList`, `switchRow` créés dans `settings.css` | les promouvoir en composants communs en N3 |
| G8 | Confirmations natives du navigateur (`window.confirm`) | — | contrôle du code : aucune occurrence dans le frontend ; les écrans N2 utilisent `confirmAction` | — |
| G9 | Pas de thème sombre | info | — | non exigé ; à décider (OWNER_DECISION si demandé) |

## 3. Règles proposées pour la suite

1. Toute nouvelle couleur passe par un jeton `--es-*` (les feuilles N2 utilisent encore des valeurs en dur, limitées à la palette du shell : à convertir avec G1).
2. Aucune nouvelle règle `!important` hors des surcharges de mise en page téléphone déjà en place.
3. Toute action lourde passe par `confirmAction` ; tout montant par `formatMoney` ; toute date par `formatDate`.
4. Les superpositions (feuilles, dialogues) sont rendues sur `document.body` (portail) : un ancêtre animé avec
   `transform` casse `position:fixed`.
