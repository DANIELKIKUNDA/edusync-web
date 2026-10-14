# Configuration de l'école — rapport N2

Date : 2026-10-14. Périmètre : ce qu'une école configure elle-même dans Paramètres. Chaque ligne indique la route
serveur, le droit exigé, la protection contre l'écrasement et l'audit. Preuves : tests
`backend/tests/test_n2_school_autonomy.py`, parcours `certification/n2-20261014/n2_journey.mjs`
(n2-journey.json), sonde `n2_probe.py` (n2-live.json).

## 1. Domaines

| Domaine | Écran | Route | Droit | Concurrence | Audit | Statut |
|---------|-------|-------|-------|-------------|-------|--------|
| Identité | École & identité | `PATCH /settings/identity` | `settings.school_identity.update` | `If-Match` (version) | `SCHOOL_IDENTITY_UPDATED` | EXISTANT, refait N2 |
| Logo | École & identité | `PUT /documents/branding/logo` | `settings.documents.manage` | remplacement atomique | `SCHOOL_LOGO_UPDATED` | **construit N2** à la place du champ « URL du logo » |
| Années | Années scolaires | `POST /settings/academic-years`, `…/activate`, transitions `close` / `archive` / `reopen` | `settings.academic_year.*` | `If-Match` | oui | EXISTANT, confirmations N2 |
| Sections | Structure | `PUT /settings/sections/{code}` | `settings.sections.manage` | version attendue | `SCHOOL_SECTION_UPSERTED` | EXISTANT |
| Options | Structure | `GET /settings/options`, `PUT /settings/options/{code}` | `settings.structure.read`, `settings.options.manage` | version attendue | `SCHOOL_OPTION_UPSERTED` | **écran construit N2** |
| Classes | Structure | `POST /settings/classes`, `PUT /settings/classes/{id}` | `settings.classes.create`, `.activate` (désactiver), `.rename` (réactiver, voir O6) | `If-Match` | `SCHOOL_CLASS_UPDATED` | EXISTANT, liste et bascule N2 |
| Règles d'inscription | Inscriptions | `GET/PUT /settings/policies/ENROLLMENT` | `settings.enrollment_policy.read/.manage` | version attendue | `ENROLLMENT_POLICY_UPDATED` | **écran construit N2** |
| Types de frais | Types de frais | `POST /settings/fee-types`, `PUT /settings/fee-types/{id}` | `settings.fee_types.manage` | `If-Match` (modification) | oui | EXISTANT |
| Tarifs | Tarifs & barèmes | `POST /settings/tariffs`, `PUT /settings/tariffs/{id}` | `settings.tariffs.manage` | `If-Match` (modification) | oui | EXISTANT, montants formatés N2 |
| Contributions en nature | Contributions | `POST /settings/contributions`, `PUT /settings/contributions/{id}` | `settings.contributions.manage` | `If-Match` (modification) | oui | EXISTANT |
| Articles scolaires | Articles | `POST /settings/products`, `PUT /settings/products/{id}` | `settings.products.manage` | `If-Match` (modification) | oui | EXISTANT, prix formaté N2 |
| Autres politiques (paiement, avantages, documents, sauvegarde, communications) | — | `GET/PUT /settings/policies/{kind}` | droits dédiés | version attendue | oui | **sans écran** : aucun module ne les applique (O3) |

Toutes les mutations passent par une clé d'idempotence : un double clic ou une réponse perdue ne crée pas de doublon.

## 2. Règles de données

- **Rien n'est supprimé** : classes, options et années se désactivent, se clôturent ou s'archivent ; l'historique reste
  consultable (aucune route de suppression dans les Paramètres).
- **Une année active à la fois** ; activer une année préparée suppose d'avoir clôturé l'année en cours. L'écran le dit
  (« Clôturez d'abord … ») au lieu d'afficher l'erreur du serveur.
- **Argent** : montants en `Decimal` côté serveur, transportés en texte, affichés par `formatMoney` sans passage par un
  nombre flottant ; CDF et USD restent séparés (une devise par tarif, jamais de conversion implicite).
- **Logo** : PNG ou JPEG identifié par ses octets, 1 Mo maximum, décodé avant stockage ; le nom de fichier et le type
  déclarés par le navigateur ne sont pas crus.
- **Dates** : affichage français (`1 sept. 2026`) sans décalage de fuseau horaire.

## 3. Vérifications réalisées

| Vérification | Résultat |
|--------------|----------|
| Parcours téléphone : identité (logo, claviers), années (confirmation, annulation sans effet), structure, inscriptions, tarifs | 14/14 OK (n2-journey.json) |
| Règles d'inscription : enregistrement conservé après rechargement, puis remise à l'état initial | OK (enrollment_check.mjs) |
| Options : ajout, confirmation, désactivation | OK (options_check.mjs) — l'option de test « Option certification N2 … » reste désactivée dans la base de certification, rien n'étant supprimable |
| Isolation : l'école A ne voit ni ne modifie la configuration de B (classes, tarifs, types de frais, UUID deviné) | OK (n2_probe.py : contrôles « Configuration jumelle », « École A : ne voit que ses classes / tarifs / types de frais », « UUID deviné : modifier la classe de B ») |
| Formatage des montants (`12 345,67 USD`, `1 500 000,05 CDF`) | OK (parcours) + test qui interdit `Number(` dans `formatMoney` |
