# N2 — Certification UX/UI

Date : 2026-10-14. Synthèse des preuves UX/UI du N2. Détails : N2_MOBILE_FIRST_CERTIFICATION_REPORT.md (largeurs,
parcours), N2_UX_BENCHMARK.md (références), N2_FORM_VALIDATION_REPORT.md, N2_WIZARD_UX_AUDIT.md,
N2_UI_STACK_AUDIT.md, N2_DESIGN_SYSTEM_GAPS.md.

## 1. Constats de l'inventaire et traitement

| # | Constat (N2_INVENTORY.md §8) | Traitement | Preuve |
|---|------------------------------|------------|--------|
| 1 | Clôture d'année sans confirmation | confirmation explicite pour activer, clôturer, archiver, rouvrir | parcours étapes 5–6 |
| 2 | Logo saisi comme une URL | envoi d'un fichier vérifié (PNG/JPEG ≤ 1 Mo), aperçu | parcours étape 2 |
| 3 | Politiques sans écran | écran « Inscriptions » pour la seule politique appliquée ; les autres restent sans écran (O3) | enrollment_check.mjs |
| 4 | Options sans écran | options par section, désactivation confirmée | options_check.mjs |
| 5 | Montants et dates bruts | `formatMoney` exact (texte) et `formatDate` français | parcours étape 9 |
| 6 | Tiroir mobile qui reste ouvert au redimensionnement | fermeture au passage en largeur bureau | rail_check.mjs |
| 7 | Membres non paginés | lots de 30, filtres en pastilles (étape 1 du N2) | access_check.mjs |
| 8 | Grande ligne « Réduire le menu » | petit bouton icône, rail, aperçu au survol/focus, épingle | rail_check.mjs |
| 9 | Pas de mise en service guidée | « Prochaine étape » + liens par point | readiness_check.mjs (école C) |
| 10 | Multi-école à certifier | sonde 50/50 | SCHOOL_MULTI_TENANT_SECURITY_REPORT.md |

## 2. Critères UX/UI

| Critère | Résultat |
|---------|----------|
| Hiérarchie claire sur téléphone (le contenu utile d'abord) | liste des sections, liste des membres et liste des tarifs avant les formulaires |
| Une action principale par écran | « Continuer » (mise en service), « Enregistrer » (identité, inscriptions), « Préparer l'année », « Ouvrir la classe » |
| États vides guidés, sans données fictives | aucune année, aucune section, aucun tarif : phrase qui dit quoi faire et dans quel ordre |
| Retour d'information | notifications de succès explicites ; boutons « Enregistrement… » pendant l'envoi ; erreurs `role=alert` |
| Actions lourdes | confirmations `alertdialog`, focus sur « Annuler » ; rien n'est supprimable |
| Accessibilité (WCAG 2.2 AA, points vérifiés) | cibles ≥ 24 px partout (mesuré) ; libellés visibles ; `aria-label` sur les icônes seules ; focus visible ; Échap ferme ; navigation clavier de la barre latérale ; mouvement réduit respecté |
| Cohérence visuelle | palette du shell, boutons communs ; dettes listées (design system) |
| Barre latérale fixe | reste à 100 % de la hauteur de la fenêtre pendant le défilement (sidebar_check.mjs, remarque du propriétaire) |

## 3. Points non vérifiés (honnêteté)

- Contraste : pas d'outil automatique exécuté ; la palette reprend celle du shell (texte ardoise foncé sur blanc,
  bleu `#0f4fbf` sur blanc), mais aucune mesure chiffrée n'est jointe. À faire au N3 avec un outil (axe-core).
- Lecteur d'écran : pas de session NVDA/VoiceOver ; les rôles et libellés ARIA ont été vérifiés dans le code.
- Appareil physique : émulation Chromium uniquement.

## 4. Verdict

**PASS LOCAL UX/UI N2**, avec les réserves du §3 reportées dans N2_TO_N3_READINESS.md.
