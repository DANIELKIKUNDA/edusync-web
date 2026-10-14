# N2 — Benchmark UX (administration de l'école)

Date : 2026-10-14. Objet : situer les choix UX du N2 (centre de configuration, navigation, formulaires, accessibilité)
par rapport à des références publiques. Les sources sont citées telles que consultées. Lorsqu'une source est secondaire
(miroir, compilation, extension d'un design system), c'est indiqué, et la règle n'est alors reprise que si elle concorde
avec au moins une autre source.

## 1. Références consultées

| # | Référence | Ce qu'on en retient | Statut de la source |
|---|-----------|---------------------|---------------------|
| R1 | Apple HIG, tab bars ([miroir](https://developer-rno.apple.com/design/human-interface-guidelines/components/navigation-and-search/tab-bars)) | Barre d'onglets de 3 à 5 entrées sur iPhone ; au-delà, une entrée « Plus » qui ouvre une liste ; utiliser le moins d'onglets possible | miroir du HIG |
| R2 | Apple HIG, lists and tables ([miroir](https://developer-rno.apple.com/design/human-interface-guidelines/components/layout-and-organization/lists-and-tables)) | Les Réglages d'iOS = hiérarchie de listes ; un chevron (disclosure indicator) signale le passage au niveau suivant | miroir du HIG |
| R3 | Material 3 navigation rail / drawer, via SAP Fiori for Android ([rail](https://www.sap.com/design-system/fiori-design-android/v26-4/components/m3-standard-components/navigation-rail/usage), [drawer](https://www.sap.com/design-system/fiori-design-android/v26-4/components/m3-standard-components/navigation-drawer/usage)) | Rail pour 3 à 7 destinations sur écran moyen/large ; tiroir modal sur écran compact ; le tiroir est en voie d'être remplacé par le rail déployé (M3 Expressive) | extension de M3, à confirmer sur m3.material.io |
| R4 | Android Developers, panneau de navigation ([fr](https://developer.android.com/develop/ui/compose/components/drawer?hl=fr)) | Tiroir modal fermé par le voile ou le bouton | officiel |
| R5 | WCAG 2.2, critère 2.5.8 Target Size (Minimum) ([DAISY KB](https://kb.daisy.org/publishing/docs/wcag/target-size-minimum.html), [BOIA](https://www.boia.org/blog/understanding-target-size-under-wcag-2.2-and-how-it-affects-people-with-disabilities)) | AA : cible d'au moins 24×24 px CSS (ou espacement équivalent) ; AAA 2.5.5 : 44×44 | secondaire, concordant |
| R6 | GOV.UK Design System, question pages ([pattern](https://design-system.service.gov.uk/patterns/question-pages)) et Service Manual ([help text](https://www.gov.uk/service-manual/design/help-text)) | Une question par page quand c'est possible, lien retour, titre, bouton « Continuer » ; messages d'erreur sans jargon, qui disent comment corriger | officiel |
| R7 | Shopify Polaris, app settings layout ([pattern](https://polaris.shopify.com/patterns/app-settings-layout)) et App Home settings ([template](https://shopify.dev/docs/api/app-home/patterns/settings)) | Réglages groupés en cartes, libellé et description courte par groupe, groupes empilés verticalement ; barre d'enregistrement qui protège les changements non enregistrés | officiel |
| R8 | Barres latérales repliables : Linear ([changelog](https://linear.app/changelog/unpublished-collapsible-sidebar)), Notion ([aide](https://www.notion.com/en-gb/help/home-and-my-tasks)), Atlassian AUI ([sidebar](https://aui.atlassian.com/aui/9.1/docs/sidebar.html), [JRACLOUD-71357](https://jira.atlassian.com/browse/JRACLOUD-71357)), Schoox ([aide](https://sigmasupport.schoox.com/hc/en-us/articles/33172984817687-Collapsible-Sidebars)), plugin Obsidian ([GitHub](https://github.com/toiq/obsidian-sidebar-expand-on-hover)) | Repli par un petit contrôle discret (icône, bordure, raccourci) ; rail d'icônes avec infobulles ; Jira : la navigation repliée se déploie au survol ; Obsidian : survol + épingle. Aucune source officielle unique ne décrit « survol + épingle » | mixte : officiel (Linear, Notion, AUI) et tiers |

Non retenu : les pages de « bonnes pratiques » génériques (blogs, compilations de skills) n'ont servi qu'à repérer des
sources ; aucune règle n'en a été reprise seule.

## 2. Confrontation avec EduSync N2

| Sujet | Référence | Choix EduSync N2 | Écart restant |
|-------|-----------|------------------|---------------|
| Navigation mobile | R1, R3 | Barre du bas : 4 modules + « Menu » (tiroir avec tous les modules autorisés) | aucun |
| Paramètres sur téléphone | R2, R6 | Liste des sections avec description et chevron → écran de la section avec « ‹ Paramètres » ; le retour Android ramène à la liste | aucun |
| Paramètres sur bureau | R7 | Navigation latérale des sections + cartes ; identité groupée en Établissement / Contact / Adresse | descriptions annotées en colonne gauche (style Polaris) non reprises : la navigation latérale joue déjà ce rôle |
| Barre latérale bureau | R3, R8 | Petit bouton icône dans l'en-tête de la barre (aria-label + infobulle) ; rail de 64 px ; aperçu complet au survol (souris, délai 280 ms) ou au focus clavier, Échap ferme ; « Épingler le menu » depuis l'aperçu ; jamais de survol sur écran tactile | raccourci clavier global (type Linear `[` ou Notion `Ctrl+\`) non ajouté : à proposer en N3 |
| Tiroir mobile | R4 | Modal, fermé par le voile, Échap, la croix ou le retour Android ; se ferme seul au passage en largeur bureau | aucun |
| Cibles tactiles | R5 | Mesuré par le parcours N2 : aucune cible < 24 px sur les écrans N2 (balayage 320 → 1440) ; actions principales à 44–48 px sur téléphone | 2.5.5 (AAA, 44 px) non visé partout : boutons secondaires de 32–36 px sur bureau |
| Formulaires | R6, R7 | Une colonne sur téléphone ; libellés visibles ; claviers adaptés (`tel`, `email`, `decimal`) ; messages qui disent comment corriger (« Adresse e-mail incomplète, par exemple direction@ecole.cd. ») ; bouton d'enregistrement collant, inactif tant que rien n'a changé | pas de récapitulatif d'erreurs en tête de formulaire (GOV.UK) : les formulaires N2 sont courts, l'erreur est sous le champ |
| Actions irréversibles ou lourdes | R6 | Confirmation explicite (boîte `alertdialog`, focus sur « Annuler ») avant d'activer, clôturer, archiver ou rouvrir une année, et avant de désactiver une classe ou une option ; le serveur garde ses propres contrôles | aucun |
| Montants | — | Formatés à partir du texte (jamais via un flottant) : `1 250 000,50 CDF` ; CDF et USD jamais additionnés | aucun |
| Mise en service | R6 | « Prochaine étape » avec un seul bouton « Continuer », puis un lien « Ouvrir » par point restant | parcours pas à pas complet (assistant) non construit : voir SCHOOL_ONBOARDING_GAP_REPORT.md |

## 3. Conclusion

Les choix N2 suivent les références sur les points structurants : nombre d'entrées de la navigation mobile, passage
liste → détail sur téléphone, rail et aperçu de la barre latérale, taille minimale des cibles en AA, messages
d'erreur actionnables, confirmation des actions lourdes. Les écarts restants sont des améliorations, pas des défauts
bloquants. Ils sont reportés dans N2_TO_N3_READINESS.md : raccourci clavier pour la barre latérale, cibles de 44 px
partout (AAA), récapitulatif d'erreurs pour les longs formulaires, assistant de mise en service.
