# Point 4C — Gate corrigé

## PASS local

- Contrat de préservation Desktop relu dans le code source : PASS
- Colonnes annuaire élèves 12/12 identiques au Desktop : PASS
- Filtres Année/Section/Classe/Statut/Sexe : PASS
- En-tête école + coordonnées + total + date d'édition : PASS
- Style documentaire canonique (bleu #175CD3, PDF paysage, XLSX filtrable) : PASS
- Répertoire familles canonique : PASS
- Sexe obligatoire à l'inscription : PASS
- Nom/Postnom/Prénom/Sexe/Classe obligatoires par défaut : PASS
- Date/lieu de naissance non bloquants par défaut : PASS
- Foyer != responsable : PASS
- Résolution assistée sans fusion silencieuse : PASS
- Réinscription / identité permanente : PASS contractuel
- Famille nombreuse / bénéficiaire explicite : PASS contractuel
- Enfant d'agent explicite : PASS contractuel
- Scope école/section/classe : PASS contractuel
- Idempotence / concurrence / audit / outbox : PASS contractuel
- PDF corrigés re-rendus et inspectés visuellement : PASS
- XLSX canonique inspecté/rendu : PASS
- Régression backend complète : 206 PASS / 0 FAIL
- Python compileall : PASS
- TypeScript syntaxique (schooling.tsx, api.ts, App.tsx) : 3/3 PASS

## 1 % machine/VPS

- migrations PostgreSQL réelles ;
- RLS A/B réel avec deux écoles ;
- build React complet ;
- navigateur 1366x768/mobile ;
- impression Windows ;
- scénarios opérateur réels ;
- coupure/reconnexion réseau réelle.

Verdict : **READY FOR FINAL LIVE CERTIFICATION, NOT YET LIVE-CERTIFIED**.

L'ancien ZIP Point 4C généré avant cette correction est **SUPERSEDED**.
