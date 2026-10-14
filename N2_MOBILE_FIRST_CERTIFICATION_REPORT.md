# N2 — Certification mobile-first

Date : 2026-10-14. Preuve principale : `certification/n2-20261014/n2_journey.mjs` → `n2-journey.json`, exécuté dans
Edge (Chromium) piloté par le protocole DevTools, émulation téléphone (user agent mobile, tactile) sous 768 px.
Captures : `certification/n2-20261014/captures/journey-*` (320, 390, 768, 1280) et captures dédiées citées plus bas.

## 1. Parcours réel sur téléphone (390 × 844)

Uniquement par l'interface (barre du bas, tiroir, boutons), compte administrateur de l'école A :

| # | Étape | Résultat |
|---|-------|----------|
| 1 | Connexion | OK |
| 2 | Identité : logo vérifié, plus de champ « URL du logo » | OK |
| 3 | Identité : clavier téléphone (`inputMode=tel`) et e-mail | OK |
| 4 | Années : une année en cours, mise en évidence | OK |
| 5 | Années : « Clôturer » ouvre une confirmation explicite (`alertdialog`) | OK |
| 6 | Années : « Annuler » ne clôture pas | OK |
| 7 | Structure : classes en liste, aucun tableau débordant | OK |
| 8 | Inscriptions : 7 règles appliquées par le serveur | OK |
| 9 | Tarifs : montants formatés (`12 345,67 USD`, `1 500 000,05 CDF`) | OK |
| 10 | Accès : liste des membres visible sans défiler | OK |
| 11 | Rôles : onglet accessible | OK |
| 12 | Accueil | OK |
| 13 | Déconnexion par le menu du compte | OK |
| 14 | Reconnexion | OK |

## 2. Balayage des largeurs

10 écrans N2 (accueil des Paramètres, mise en service, identité, années, structure, inscriptions, tarifs, articles,
membres, accueil) × 7 largeurs = **70 mesures**.

| Largeur | Débordement horizontal | Cibles < 24 px (WCAG 2.2 AA 2.5.8) |
|---------|------------------------|------------------------------------|
| 320 | 0 | 0 |
| 375 | 0 | 0 |
| 390 | 0 | 0 |
| 768 | 0 | 0 |
| 1024 | 0 | 0 |
| 1280 | 0 | 0 |
| 1440 | 0 | 0 |

Erreurs console : aucune.

## 3. Exigences du mandat

| Exigence | Réalisation |
|----------|-------------|
| Conception d'abord pour 320–390 px | Paramètres : liste des sections → écran de la section ; formulaires sur une colonne ; actions principales pleine largeur (48 px) |
| Pas de tableau à défilement horizontal sur téléphone | classes, tarifs, membres en listes ; contrôle automatique (étape 7) |
| Filtres en pastilles | membres : Actifs / Désactivés / Tous |
| Action principale accessible | bouton d'enregistrement collant au-dessus de la barre du bas (identité, inscriptions) |
| Claviers adaptés | `tel`, `email`, `decimal` |
| Navigation mobile de 3 à 5 entrées + « Plus » | barre du bas : 4 modules + « Menu » |
| Retour Android | ferme d'abord la boîte ouverte, puis revient de la section à la liste, puis quitte le module (settings_back.mjs) |
| Zones sûres (encoches) | `env(safe-area-inset-bottom)` sur la barre du bas et les feuilles |
| Mouvement réduit | `prefers-reduced-motion` respecté (aperçu de la barre latérale, interrupteurs, transitions) |
| Tablette | rail de 64 px ; Paramètres en deux colonnes avec navigation verticale (tablet_check.mjs) |
| Tiroir après rotation | se ferme au passage en largeur bureau (rail_check.mjs) |

## 4. Défauts trouvés à l'œil et corrigés pendant la certification

Les mesures automatiques ne voient pas tout ; les captures ont été relues :

- Tarifs sur téléphone : le formulaire passait avant la liste → formulaire replié derrière « + Ajouter un tarif »,
  la liste vient en premier.
- Paramètres à 768 px : bande d'onglets horizontale tronquée (« Ins… ») → navigation verticale entre 721 et 1100 px.
- Infobulle restée visible au-dessus de l'aperçu de la barre latérale → masquée à l'ouverture de l'aperçu.
- Après une boîte de confirmation, « ‹ Paramètres » demandait deux appuis → retour en une fois (settings_back.mjs).

## 5. Limites

- Émulation Chromium, pas d'appareil physique : le rendu iOS Safari (zones sûres réelles, clavier) n'a pas été vu
  sur un iPhone. À faire sur appareil au premier déploiement de recette.
- Performance mobile mesurée par le poids (159 Ko gzip pour le fragment principal), pas par un profil sur téléphone
  d'entrée de gamme.

## 6. Verdict

**PASS LOCAL mobile-first** pour les écrans N2.
