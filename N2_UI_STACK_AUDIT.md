# N2 — Audit de la pile UI

Date : 2026-10-14. Mesures prises sur le dépôt et sur le build de production (`npm run build`).

## 1. Pile

| Élément | Version | Rôle | Avis |
|---------|---------|------|------|
| React / React DOM | 19.3.0 | rendu | à jour |
| Vite (rolldown) | 8.3.0 | build, découpage par module (`lazy()`) | à jour |
| TypeScript | 7.0.2 | typage strict, `tsc --noEmit` = 0 erreur | à jour |
| react-hook-form + @hookform/resolvers + zod | 7.62 / 5.2 / 4.1 | formulaires et validation | homogène sur les écrans N2 |
| sonner | 2.0 | notifications éphémères (toasts) | utilisé pour les confirmations de succès |
| @fontsource-variable/inter | 5.3 | police embarquée (pas de dépendance réseau à un CDN) | adapté au hors-ligne |

Aucune bibliothèque de composants tierce (pas de MUI, Chakra, Radix…) : composants maison (`platform/shell.tsx`,
`platform/forms.tsx`, `platform/dialogs.ts`, `platform/account.tsx`), icônes SVG maison (`platform/nav_icons.tsx`).
Conséquence : poids réduit et contrôle total, mais l'accessibilité des composants (focus, rôles ARIA) est à notre
charge ; elle a été vérifiée écran par écran pour le N2.

## 2. Poids (build de production)

| Fichier | Brut | gzip |
|---------|------|------|
| `index-*.js` (shell, connexion, paramètres) | 562 Ko | **159 Ko** |
| `index-*.css` (toutes les feuilles) | 167 Ko | 33 Ko |
| plus gros module chargé à la demande (finance) | 60 Ko | — |

Le build signale un fragment de plus de 500 Ko (brut). Les modules métier sont déjà chargés à la demande ; les
Paramètres restent dans le fragment principal parce que des tests d'ancrage exigent leur code dans `App.tsx`.
Piste N3 : sortir les Paramètres dans un module `lazy()` en adaptant ces tests (`App.tsx` pèse 75 Ko de source,
dont la majeure partie est le centre de configuration).

## 3. Styles

| Mesure | Valeur | Lecture |
|--------|--------|---------|
| Feuilles CSS | 15 (1 395 lignes, dont 15 lignes de plus de 2 000 caractères dans `styles.css`) | `styles.css` est historique et compacté ; les nouvelles feuilles (shell, access, settings) sont lisibles |
| Couleurs hexadécimales distinctes | 468 | pas de palette unique : voir N2_DESIGN_SYSTEM_GAPS.md |
| Variables CSS distinctes | 44 (jetons `--es-*` du shell) | les jetons existent mais ne sont pas utilisés partout |
| `!important` | 92 (dont 53 dans `styles.css`, 19 dans `modern.css`) | signe de couches qui se contredisent ; à réduire |
| `prefers-reduced-motion` | présent dans 6 feuilles | animations coupées pour qui le demande |
| `prefers-color-scheme` | absent | pas de thème sombre : choix assumé, non exigé par le mandat |

## 4. Composants N2 ajoutés ou modifiés

| Composant | Fichier | Accessibilité |
|-----------|---------|---------------|
| `confirmAction` | platform/dialogs.ts | `role=alertdialog`, `aria-modal`, `aria-labelledby/-describedby`, focus initial sur « Annuler », Échap, voile, × |
| `formatMoney`, `formatDate`, `suggestNextYear` | platform/format.ts | montants exacts à partir du texte ; dates sans décalage de fuseau |
| Navigation des Paramètres (liste → section) | App.tsx `SettingsPage` | boutons avec texte, `aria-current`, retour Android |
| `LogoField` | App.tsx | `alt` explicite, erreurs `role=alert` |
| `EnrollmentPolicySettings` | App.tsx | interrupteurs `role=switch`, libellé cliquable de 52 px |
| Barre latérale (rail, aperçu, épingle) | platform/shell.tsx | `aria-label`, `aria-expanded`, infobulle `role=tooltip`, focus clavier, Échap |
| Membres (feuille, ajout, secret) | access.tsx | rendu par portail sur `document.body`, focus, Échap |

## 5. Verdict

La pile est moderne et cohérente ; elle ne bloque rien pour le N2. Les dettes portent sur les styles (palette non
unifiée, `!important`, feuille historique compactée) et sur le poids du fragment principal. Elles sont listées
dans N2_DESIGN_SYSTEM_GAPS.md et N2_TO_N3_READINESS.md.
