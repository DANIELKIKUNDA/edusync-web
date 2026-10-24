# Paramètres École — comparaison desktop (edusync-desktop-golden) ↔ web, onglet par onglet (24/10/2026)

Source desktop : `app/ui/settings_page.py` (13 rubriques), `app/ui/configuration_wizard.py` (assistant en 7 étapes),
`app/db/configuration.py` (référentiel RDC). Principe repris : **l’utilisateur ne saisit jamais un code interne**.

| Rubrique | Desktop | Web avant | Web après cette passe | Reste à faire |
|---|---|---|---|---|
| Vue d’ensemble | Assistant intelligent, progression, numérotation automatique (prochain matricule élève / famille), état par rubrique | Parcours de progression | **Assistant de mise en service** (école + année → sections → options → classes et parallèles) + parcours | Afficher le prochain matricule (pas d’API aujourd’hui) |
| École & identité | Nom, téléphone, e-mail, adresse, ville, province, devise / mention, logo | Formulaire présent mais **enregistrement impossible** (HTTP 500 : droit SQL manquant) ; logo qui recouvrait le texte | Enregistrement corrigé (migration 0086, colonnes d’identité seulement), logo cloisonné, erreurs expliquées | « Devise / mention » (nouvelle colonne à décider) |
| Années scolaires | Créer, reprendre l’année précédente, activer, clôturer, archiver | Présent, **code saisi à la main** | Code généré depuis le libellé (« 2027-2028 ») | — |
| Structure & classes | Sections cochées ; options **seulement en Humanités** (catalogue RDC + groupe tarifaire) ; ouvrir une classe ; **créer plusieurs classes** ; parallèles | Options ajoutables à toutes les sections (Maternelle, Primaire) ; une classe déjà ouverte disparaissait de la liste : **pas de classes parallèles** | Options réservées au Secondaire (règle serveur aussi), catalogue RDC du desktop (12 options, groupes générales / techniques), **assistant « Ouvrir des classes »** : lot, parallèles A à E, une classe par option en Humanités, aperçu, jamais de doublon ; grille compacte | — |
| Types de frais | 11 modèles + personnalisé, codes générés, modification depuis la ligne | 5 modèles seulement, aucun frais personnalisé | 11 modèles (dont frais de l’État, Examen d’État, TENASOSP, écusson, journal) + **frais personnalisé** (code généré) | Modifier / désactiver un frais existant depuis sa ligne |
| Tarifs & barèmes | Règles hiérarchiques datées, facturation mensuelle, « Configurer les frais réglementaires », appliquer les barèmes | Présent (règles, mois, application) | Inchangé | Assistant « frais réglementaires » (capacité `settings.regulatory_fees.configure` encore PLANNED) |
| Inscriptions | Conditions d’admission, validation de la rubrique | Présent | Inchangé | — |
| Avantages | Famille nombreuse, enfants du personnel | Présent | Inchangé | — |
| Encaissement | Acomptes, modes, fonds anticipés, plans anticipés | Présent (deux rubriques) | Inchangé | — |
| Contributions en nature | Modèles (savon, rame, PH, cahier…), codes générés | **Code saisi à la main** | Modèles en un clic, code généré | — |
| Articles scolaires | Modèles (pull, uniforme, tenue de sport, T-shirt) | **Code saisi à la main** | Modèles en un clic, code généré | — |
| Documents & sauvegardes | Préfixes reçus / rapports, copies, format, signataire, imprimantes, dossier, sauvegarde / restauration | Logo et en-têtes dans le module Documents ; sauvegardes côté serveur | Lien « Ailleurs dans EduSync » | Préfixes / signataire / copies côté web (à confirmer) ; sauvegarde à la demande (capacités PLANNED) |
| Assistance technique | Export du diagnostic | — | — | Capacités `settings.diagnostics.*` PLANNED |

## Preuve « vrai administrateur » (stack locale, école C vierge)

Parcours automatisé dans un vrai navigateur, branché sur le vrai serveur (`frontend/browser-tests/local_settings_walkthrough.mjs`) :
connexion → assistant (école, année 2026-2027, Maternelle / Primaire / Secondaire, options Commerciale et gestion,
Scientifique, Électricité, 2 parallèles) → identité enregistrée → ajout d’une parallèle C → 3 modèles de frais + 1 frais
personnalisé → contribution → article. 19 étapes sur 20 réussies au premier passage complet ; l’échec restant était une
lenteur d’affichage après enregistrement (5 à 7 s), corrigée en ne rechargeant que la liste modifiée (≈ 2 s en local).
