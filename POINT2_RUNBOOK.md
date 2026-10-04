# Runbook — certification Point 2 sur Windows

Ce runbook constitue le 1% de certification machine réelle.

## Préconditions

- Docker Desktop actif ;
- Python disponible ;
- Node/TypeScript disponibles ;
- fichier `.env` créé depuis `.env.example` ;
- base Docker/dev jetable, jamais une base production.

## Commande unique

Depuis la racine du checkpoint :

```powershell
.\RUN_POINT2_WINDOWS.ps1
```

## Sorties attendues

Le script doit montrer :

- tous les tests Python PASS ;
- provision PostgreSQL PASS ;
- G1 RLS/security PASS ;
- `G3_MULTI_CASHIER_POSTGRES_PASS` ;
- `OFFLINE_FINANCE_HASH_VECTOR_PASS` ;
- TypeScript PASS.

## Test opérateur à ajouter lors de la certification finale

Sur deux navigateurs/appareils :

1. ouvrir deux caisses ;
2. armer deux partitions distinctes ;
3. couper Internet ;
4. encaisser un élève autorisé sur chaque poste ;
5. vérifier les reçus distincts ;
6. reconnecter ;
7. synchroniser ;
8. vérifier une seule écriture par opération ;
9. répéter la synchronisation ;
10. vérifier qu'aucun doublon n'apparaît ;
11. tenter une charge appartenant à l'autre poste ;
12. vérifier le refus local/serveur ;
13. clôturer et comparer CDF/USD, nombre de reçus et hash final.

## Incident appareil perdu

Ne jamais réarmer automatiquement les charges du poste perdu.

1. force release documenté ;
2. réservations => `QUARANTINED` ;
3. rapprochement physique des reçus/cash ;
4. récupération/synchronisation si possible ;
5. résolution explicite de quarantaine ;
6. seulement ensuite réattribution.
