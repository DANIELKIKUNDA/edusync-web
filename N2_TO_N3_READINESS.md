# Passage N2 → N3 — préparation

Date : 2026-10-14. Le N3 couvre les opérations quotidiennes de l'école (élèves et inscriptions, finance, documents,
personnel…). Ce document dit si les fondations posées par le N2 suffisent pour l'ouvrir, et ce qui doit être traité
avant ou pendant le N3. **Le N3 n'est pas démarré** (hors mandat).

## 1. Prérequis du N3 fournis par le N2

| Prérequis N3 | État | Où |
|--------------|------|----|
| L'école crée et gère ses utilisateurs sans la plateforme | PRÊT | Accès & rôles (D1–D4), sonde 50/50 |
| Rôles et droits fiables, révocation immédiate, anti-escalade | PRÊT | SCHOOL_RBAC_CERTIFICATION_REPORT.md |
| Isolation entre écoles | PRÊT (administration) ; modules N3 couverts par des sondes antérieures à rejouer | SCHOOL_MULTI_TENANT_SECURITY_REPORT.md |
| Année active, structure (sections, options, classes) | PRÊT | Paramètres |
| Règles d'inscription paramétrables et appliquées | PRÊT | Paramètres › Inscriptions |
| Frais et tarifs avec montants exacts, CDF et USD séparés | PRÊT | Paramètres › Types de frais, Tarifs |
| Socle mobile-first (shell, barre du bas, feuilles, confirmations, formats) | PRÊT | N2_MOBILE_FIRST_CERTIFICATION_REPORT.md |

## 2. À traiter en N3 (aucun ne bloque l'ouverture)

| # | Sujet | Origine | Priorité |
|---|-------|---------|----------|
| 1 | Décisions ouvertes O1 (administrateur initial), O2 (classe avec élèves), O5 (groupes tarifaires des options), O6 (droit de réactivation des classes) | N2_OWNER_DECISIONS.md | haute pour O2 (touche les inscriptions) |
| 2 | Rejouer la sonde d'isolation sur les modules N3 avec les écoles jumelles A/B (y compris le logo) | multi-tenant | haute |
| 3 | Mesure de contraste automatique (axe-core) et passage lecteur d'écran | UX/UI §3 | moyenne |
| 4 | Test sur appareils physiques (Android d'entrée de gamme, iPhone) | mobile §5 | moyenne |
| 5 | Sortir les Paramètres de `App.tsx` dans un module chargé à la demande (fragment principal > 500 Ko brut) | pile UI | moyenne |
| 6 | Design system : jetons de couleur, réduction des `!important`, reformatage de `styles.css` | design system G1–G3 | moyenne |
| 7 | Assistant de première configuration facultatif ; écran « reprendre la structure de l'année précédente » (route serveur existante) | onboarding E2, E4 | basse |
| 8 | `EnrollmentWizard` : indicateur d'étapes accessible, brouillon | wizards | moyenne |
| 9 | Récapitulatif d'erreurs pour les longs formulaires ; traduction des derniers messages serveur techniques | formulaires | basse |
| 10 | Raccourci clavier de la barre latérale ; cibles de 44 px (AAA) | benchmark | basse |
| 11 | Politiques PAYMENT, DOCUMENTS, etc. : écran seulement quand un module les applique | O3 | au fil des modules |

## 3. Verdict

**READY_FOR_N3** : les fondations d'administration de l'école sont certifiées localement ; les points du §2 sont des
améliorations ou des décisions à prendre pendant le N3, pas des prérequis manquants.
