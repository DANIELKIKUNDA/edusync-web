# EduSync École Web — Point 5B Documents / Exports / Impression
Date: 2026-09-13
Verdict: PASS LOCAL BACKEND + CORRECTION DOCUMENTAIRE; validation navigateur Windows réelle encore requise.

## Corrections profondes
- Suppression de l'impression automatique `window.print()` du module Effectifs. Le bouton Imprimer ouvre désormais le PDF pour prévisualisation; l'utilisateur décide ensuite d'imprimer.
- Introduction de `frontend/src/document_io.ts`: prévisualisation PDF séparée de l'export et dossier d'exports géré avec File System Access API lorsque le navigateur l'autorise.
- Arborescence locale canonique: `Documents EduSync / École / Année / Module / Catégorie / fichier`.
- Réexport d'un même fichier dans le dossier géré: ouverture avec `create:true` puis `createWritable()`, donc remplacement du fichier logique courant au lieu de créer `(1)`, `(2)`.
- Fallback honnête: sans permission File System Access, téléchargement navigateur standard; EduSync ne prétend pas contrôler le renommage du navigateur.
- Exports XLSX branchés sur le gestionnaire pour Personnel, Élèves, Familles, Effectifs, Dépôts et modèle d'import.
- Migration `0017_documents_logical_current.sql`: séparation entre historique append-only (`generated_documents`) et pointeur courant (`current_documents`).
- Clé logique stable et hiérarchique + adaptateur stockage local atomique pour dev/test; compatible future implémentation S3 derrière port.
- Politique de reçus verrouillée pour le Point Finance: paiement et impression découplés; aucune impression automatique par défaut; politique école configurable au futur Centre financier.

## Invariants
- Une régénération documentaire ne recrée ni n'annule une transaction métier.
- Un document logique possède un seul fichier courant visible.
- L'historique des générations reste traçable et append-only.
- Les golden masters Desktop déjà certifiés restent intouchables sémantiquement.
- PDF d'impression: prévisualisation obligatoire avant décision d'impression.

## Validation
- `python -m compileall`: PASS.
- `pytest`: 229/229 PASS.
- Test nouveau: même clé logique écrite deux fois => un seul fichier courant, contenu actualisé.
- Recherche frontend: aucun appel `.print()` restant.
- Build frontend complet non exécuté: `node_modules` absent dans le checkpoint; validation npm/Windows reste dans le gate machine.

## Gate avant Finance
Point 5B est corrigé comme candidat local. La règle d'impression des reçus sera implémentée dans Finance car elle dépend du workflow transactionnel et des paramètres école. La certification finale de l'accès au dossier et de l'ouverture PDF doit être faite sous Edge/Chrome Windows avec autorisation utilisateur réelle.
