# Point 4A — Matrice de préservation Paramètres

| Domaine Desktop / besoin | Port Web | Statut Point 4A |
|---|---|---|
| École & identité | API versionnée + écran Centre de configuration | PORTÉ |
| Années scolaires | PREPARED/ACTIVE/CLOSED/ARCHIVED, activate/close/archive/reopen, copie configuration | PORTÉ |
| Structure / sections | référentiel RDC + activation explicite | PORTÉ |
| Options | CRUD/upsert tenant + scope section | PORTÉ BACKEND |
| Classes | création annuelle, cohérence section/option, rename/activation API | PORTÉ |
| Types de frais | catalogue référence + création/mise à jour/activation | PORTÉ |
| Tarifs | montant > 0, CDF/USD, scope classe/section/option, mois, update, déduplication | PORTÉ |
| Règles d'encaissement | politique versionnée `PAYMENT` | PORTÉ BACKEND |
| Inscription & admission | politique versionnée `ENROLLMENT` | PORTÉ BACKEND |
| Avantages | politique versionnée `BENEFITS` | PORTÉ BACKEND |
| Contributions en nature | catalogue tenant + update/activation | PORTÉ BACKEND |
| Articles scolaires | catalogue, devise, prix, suivi stock flag, update/activation | PORTÉ BACKEND |
| Documents | politique versionnée ; génération/historique riche au Point 5 | CONTRAT PORTÉ / SORTIES POINT 5 |
| Sauvegardes | politique serveur/offsite ; exécution/restauration certifiée au Point 5/production | CONTRAT PORTÉ / EXÉCUTION À RACCORDER |
| Diagnostics avancés | capabilities RBAC conservées | À RACCORDER À L'UI FINALE |
| Global setup lock | remplacé par readiness par use case | AMÉLIORÉ |

Aucune fonction Desktop mature ne doit être supprimée par la migration Web. Les fonctions documentaires riches et la restauration ne sont pas simplifiées : elles sont déplacées dans le lot où elles peuvent être portées correctement sur l'architecture VPS.
