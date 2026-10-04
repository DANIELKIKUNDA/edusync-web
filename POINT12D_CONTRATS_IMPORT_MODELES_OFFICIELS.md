# Point 12D — Contrats d'import et modèles Excel officiels

## Décision
EduSync n'accepte plus un classeur arbitraire pour les imports Élèves, Personnel et Reprise historique financière. Le flux canonique est : **Télécharger le modèle EduSync → remplir → analyser → staging → prévisualiser → confirmer → exécuter**.

## Contrats versionnés
- Élèves : `EDUSYNC-STUDENTS-v1`
- Personnel : `EDUSYNC-STAFF-v1`
- Historique financier : `EDUSYNC-FINANCE-HISTORY-v1`
- Version de contrat : `1.0`

Chaque XLSX contient une feuille de données, `Instructions`, `Référentiels` masquée et `_EDUSYNC_CONTRACT` très masquée. Le contrat embarque produit, type, version, feuille de données, ligne d'en-têtes et empreinte SHA-256 de la structure attendue.

## Fail closed
Avant lecture métier, le serveur vérifie le marqueur EduSync, le type de contrat, la version, l'empreinte des colonnes, la feuille et les en-têtes exacts. Un fichier Excel ordinaire, un modèle d'un autre import, une version non supportée ou une structure modifiée est refusé. CSV n'est plus accepté sur ces trois flux sécurisés.

## Ergonomie du modèle
Les cellules de données sont éditables ; la structure/en-tête est protégée contre les modifications accidentelles. Les référentiels alimentent les listes Excel quand ils sont disponibles (sexe, catégorie, devise et classes pour le modèle Élèves téléchargé avec l'année scolaire). Les instructions rappellent les champs obligatoires et les règles métier.

## Finance
La reprise historique conserve sa doctrine : hors caisse, aucun nouveau paiement, aucun mouvement de caisse et aucun reçu EduSync. Le modèle officiel est obligatoire.

## Validation locale
- `pytest`: 426/426 PASS
- `python -m compileall -q src`: PASS
- Build Vite / navigateur / Excel réel : non certifiés dans cet environnement sans `node_modules` et sans poste Excel/Android réel.
