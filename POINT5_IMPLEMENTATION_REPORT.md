# EduSync — Point 5 Documents / Exports — rapport d’implémentation

Date : 2026-09-12
Baseline : Point 4D Effectifs & Dépôts.

## Travail réalisé
- Audit réel du checkpoint Point 4D et de ses générateurs ReportLab/XLSX existants.
- Création du bounded context `documents` sans réécriture destructive des générateurs certifiés.
- Catalogue canonique de 16 familles documentaires, avec statut explicite par famille.
- Aucun document Finance non vérifié n’est faussement déclaré certifié : il reste `DESKTOP_GOLDEN_REQUIRED`.
- Nouveau Centre documentaire Web : recherche, filtre par module, formats, état de portage, accès au modèle d’import.
- Nouveau modèle XLSX d’import élèves professionnel : colonnes obligatoires, validation F/M, feuille Instructions, gel des volets, filtres.
- Migration `0016_documents_domain.sql` : historique documentaire append-only, `school_id`, RLS forcée, SHA-256, taille, object key, auteur, date, filtres, lien de régénération.
- La régénération crée une nouvelle preuve documentaire ; elle ne modifie jamais la transaction métier source.
- Le contrat de santé Point 4D a été conservé afin de ne pas casser les tests de non-régression.

## Préservation
Déjà portés et conservés : registre Personnel PDF/XLSX, fiche agent PDF, liste élèves PDF/XLSX, répertoire familles PDF/XLSX, fiche élève PDF, effectifs PDF/XLSX, dépôts XLSX.

Les sorties Finance/Caisse dont le golden master Desktop exact n’est pas disponible dans le checkpoint restent bloquées en certification documentaire. Aucune structure n’a été inventée à leur place.

## Validation locale
- `python -m compileall -q src tests` : PASS.
- `pytest -q` : **227 PASS / 0 FAIL**.
- XLSX modèle import : génération réelle + réouverture openpyxl : PASS via tests.
- TypeScript complet : NON CERTIFIÉ dans cet environnement, dépendances React absentes ; tentative d’installation npm expirée. Aucun PASS fictif.
- PostgreSQL/RLS live, navigateur Windows et impression physique : restent dans le dernier lot machine réelle.
