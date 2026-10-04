# Point 4D — Matrice Desktop certifié → Web

| Contrat Desktop fermé | Web Point 4D | Statut |
|---|---|---|
| Toute l'école / Maternelle / Primaire / Secondaire | `EffectifsScope` + filtre SQL + intersection RBAC | PRÉSERVÉ |
| KPI élèves actifs | `GET /effectifs/overview` | PRÉSERVÉ |
| KPI classes actives | `GET /effectifs/overview` | PRÉSERVÉ |
| KPI moyenne par classe | `GET /effectifs/overview` | PRÉSERVÉ |
| Par classe | 14 colonnes, 4 groupes F/G/T | PRÉSERVÉ |
| Par section | mêmes 4 groupes F/G/T | PRÉSERVÉ |
| Par filière / option | mêmes 4 groupes F/G/T | PRÉSERVÉ |
| Mouvements | année + cycle + classe + type + recherche + pagination | PRÉSERVÉ |
| Total général | ligne calculée F/G/T pour chaque groupe | PRÉSERVÉ |
| Excel filtré | titre, périmètre, groupes fusionnés, total | PRÉSERVÉ |
| PDF filtré | A4 paysage, identité/logo, groupes, total | PRÉSERVÉ |
| Imprimer | route PDF dédiée protégée par `headcounts.print` | PRÉSERVÉ |
| Registre dépôts | filtre identique au périmètre Effectifs | PRÉSERVÉ |
| Saisie dépôt année ACTIVE | trigger PostgreSQL + API | PRÉSERVÉ / DURCI |
| Historique dépôts | append-only | DURCI |
| Scope utilisateur | permission + scope, jamais élargi par l'export | DURCI |
| Multi-école | `school_id` + FORCE RLS | AJOUT WEB |
