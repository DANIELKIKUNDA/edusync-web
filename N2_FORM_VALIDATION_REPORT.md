# N2 — Validation des formulaires

Date : 2026-10-14. Pile : react-hook-form 7 + zod 4 (`zodResolver`), valeurs par défaut communes `formDefaults`
(platform/forms.tsx), champ commun `FormField` (libellé visible + message d'erreur relié au champ).
Règle : **le serveur valide toujours** ; le navigateur ne fait qu'éviter un aller-retour et expliquer plus tôt.

## 1. Formulaires N2

| Formulaire | Validation navigateur | Validation serveur | Clavier / saisie | Message type |
|------------|-----------------------|--------------------|------------------|--------------|
| Identité de l'école | zod : nom ≥ 2, e-mail valide ou vide, téléphone limité à chiffres, espaces, `+ ( ) -` | PATCH `/settings/identity` avec `If-Match` (version) | `type=tel inputMode=tel`, `type=email inputMode=email`, `autocomplete` (organization, tel, email, street-address, address-level1/2) | « Adresse e-mail incomplète, par exemple direction@ecole.cd. » |
| Logo | type PNG/JPEG et taille ≤ 1 Mo avant envoi | contenu identifié par ses octets (signature PNG/JPEG), décodage Pillow, ≤ 1 Mo | sélecteur de fichier `accept=image/png,image/jpeg` | « Le logo dépasse 1 Mo : réduisez l'image puis réessayez. » |
| Nouvelle année | zod : code et libellé ≥ 4, dates obligatoires, fin après rentrée, code non déjà utilisé | domaine AcademicYear + unicité | `type=date` | « La fin d'année doit venir après la rentrée. » / « Cette année existe déjà. » |
| Ouverture d'une classe | bouton inactif tant qu'aucune classe n'est choisie ; classe filtrée par section | section/classe de référence cohérentes, année active ou préparée | listes déroulantes avec libellés visibles | « La classe de référence ne correspond pas à la section choisie » |
| Option de section | nom ≥ 2, code dérivé (majuscules, sans accents, ≤ 48), doublon refusé | `OptionPut` (code 1–48, libellé 1–120), version attendue | texte | « Cette option existe déjà dans la section. » |
| Règles d'inscription | interrupteurs (`role=switch`), les 5 champs de terrain ne sont pas décochables | le serveur ne retient que les champs autorisés et rajoute toujours les 5 champs de terrain | — | message du serveur |
| Tarif | zod existant ; montant `inputMode=decimal` | `Decimal`, montant > 0, devise CDF/USD | `inputMode=decimal` | existant |
| Ajout d'un membre | zod : nom, e-mail, au moins un rôle | anti-escalade, unicité, rattachement d'un compte existant | `type=email`, `autocomplete=off` | existant N2 étape 1 |
| Changement du mot de passe provisoire | zod : ≥ 10 caractères, confirmation identique | ≥ 10, différent du provisoire, jeton à usage unique | `autocomplete=new-password` | « Choisissez un mot de passe différent du mot de passe provisoire. » |

## 2. Règles transverses vérifiées

- Tous les champs N2 ont un **libellé visible** (pas seulement un `placeholder`) ; test existant
  `test_form_fields_are_explicitly_labelled`.
- Taille de police 16 px sur téléphone pour éviter le zoom automatique d'iOS (styles.css, `font-size:16px!important`).
- Bouton d'enregistrement **inactif tant que rien n'a changé** (identité) et pendant l'envoi (« Enregistrement… »).
- **Conflit de version** : chaque modification envoie la version lue ; une modification concurrente est refusée par le
  serveur avec un message clair au lieu d'écraser.
- **Formulaire non enregistré** : le garde-fou `installUnsavedFormGuard` demande confirmation avant de quitter la page.
- Montants : jamais convertis en nombre flottant ; affichés par `formatMoney` à partir du texte.

## 3. Écarts

- Pas de récapitulatif d'erreurs en tête de formulaire (modèle GOV.UK). Les formulaires N2 ont au plus 7 champs ;
  l'erreur sous le champ suffit. À reconsidérer pour les longs formulaires du N3 (inscription, personnel).
- Les messages renvoyés par le serveur sont en français mais certains restent techniques (ex. « Version d'année
  obsolète ») : `friendlyError` les traduit pour les cas connus ; liste à compléter en N3.
