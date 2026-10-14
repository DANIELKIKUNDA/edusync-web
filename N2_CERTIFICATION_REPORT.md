# Certification N2 — Administration de l'école (+ UX/UI premium, mobile-first)

Date : 2026-10-14. Portée : locale (instance isolée : PostgreSQL 16 RLS forcée, Redis WSL, SeaweedFS S3, API FastAPI,
interface Vite). Ni staging ni production. Le N3 n'est pas démarré.

## 1. Base et commits

- Base : `888bb0d` (preuves N0/N1 + décisions MFA, code `bc2344c` certifié et étiqueté).
- Commits N2 (locaux) : `ae03fb2` (utilisateurs gérés par l'école, anti-escalade, inventaire), `82d7733` (centre de
  configuration mobile-first), `62304ef` (barre latérale), `75ad92a` (règles d'inscription), `212bbbc` (mise en service
  guidée), `d631dca` (options), puis le commit des rapports et corrections finales.
- Le SHA exact certifié est celui inscrit par le script dans `CERTIFICATION_EVIDENCE_MANIFEST.md` (arbre propre exigé
  au démarrage).

## 2. Ce qui a été livré

| Domaine | Livré | Rapport |
|---------|-------|---------|
| Utilisateurs de l'école | création (mot de passe provisoire montré une fois), changement obligatoire à la 1re connexion, rattachement d'un compte existant, renommage, réinitialisation (sessions coupées), désactivation/réactivation (révocation immédiate) | SCHOOL_RBAC_CERTIFICATION_REPORT.md |
| Droits | anti-escalade sur la gouvernance, cible jamais soi-même, gestionnaire des accès toujours présent, audit complet | idem |
| Isolation | écoles jumelles A/B, 0 fuite | SCHOOL_MULTI_TENANT_SECURITY_REPORT.md |
| Configuration | identité + logo vérifié, années (confirmations, année suivante proposée), sections, options, classes (désactivation confirmée), règles d'inscription, frais, tarifs et articles (montants exacts) | SCHOOL_CONFIGURATION_REPORT.md |
| Mise en service | prochaine étape + liens par point | SCHOOL_ONBOARDING_GAP_REPORT.md |
| UX/UI et mobile | Paramètres liste → section sur téléphone, navigation verticale sur tablette, barre latérale en rail avec aperçu et épingle, tiroir fermé au passage bureau, listes au lieu de tableaux | N2_UX_UI_CERTIFICATION_REPORT.md, N2_MOBILE_FIRST_CERTIFICATION_REPORT.md |
| Audits | pile UI, design system, assistants, formulaires, benchmark | N2_UI_STACK_AUDIT.md, N2_DESIGN_SYSTEM_GAPS.md, N2_WIZARD_UX_AUDIT.md, N2_FORM_VALIDATION_REPORT.md, N2_UX_BENCHMARK.md |
| Décisions | D1–D4 prises ; O1–O6 ouvertes | N2_OWNER_DECISIONS.md |

## 3. Preuves

| Preuve | Résultat |
|--------|----------|
| Suite backend `pytest` | 589 passed (dont 15 contrats N2 dans `test_n2_school_autonomy.py`) |
| Typecheck `tsc` / build Vite | 0 erreur / OK |
| Sonde réelle N2 `n2_probe.py` | 50/50 PASS |
| Parcours UI N2 `n2_journey.mjs` | téléphone 14/14 ; 70 mesures (10 écrans × 7 largeurs) : 0 débordement, 0 cible < 24 px, 0 erreur console |
| Vérifications ciblées | settings_check, settings_back, rail_check, enrollment_check, readiness_check, options_check, tablet_check, access_check, sidebar_check (`certification/n2-20261014/`) |
| Régression N0/N1 | script de certification complet (désormais avec la sonde et le parcours N2) : voir `CERTIFICATION_EVIDENCE_MANIFEST.md` |

## 4. Limites connues

- Émulation Chromium, pas d'appareil physique ; pas de mesure de contraste outillée ni de session lecteur d'écran.
- Décisions ouvertes O1–O6 ; politiques autres que l'inscription sans écran (O3) ; invitation par lien BLOCKED_EXTERNAL.
- Dettes de style (palette, `!important`) et fragment principal > 500 Ko brut (159 Ko gzip).
- Données de test laissées dans la base de certification : une option « Option certification N2 … » désactivée
  (rien n'est supprimable, par conception).

## 5. Verdict

Le verdict final (**PASS LOCAL N2** ou **N2 NON FERMÉ**) et l'étiquette `n2-local-certified-2026-10-14` dépendent de
l'exécution du script de certification sur l'arbre propre : ils sont consignés dans `CERTIFICATION_EVIDENCE_MANIFEST.md`
et repris dans le message de fin de mandat. Préparation N3 : **READY_FOR_N3** (N2_TO_N3_READINESS.md), sous réserve du
verdict ci-dessus.
