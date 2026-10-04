# WEB-0D — Runbook Finance Offline

## Sur Windows / Docker Desktop

Après avoir fermé G1 et configuré `.env` :

```powershell
.\RUN_G2_WINDOWS.ps1
```

Résultats attendus :

```text
G2_OFFLINE_FINANCE_PROTOCOL_POSTGRES_PASS
OFFLINE_FINANCE_HASH_VECTOR_PASS
```

Ne mettre **jamais** en production :

```text
EDUSYNC_OFFLINE_FINANCE_ENABLED=true
```

avant d'avoir également :

```text
EDUSYNC_OFFLINE_FINANCE_CERTIFIED=true
```

et seulement après le gate G2-B du ledger Finance canonique.

## Parcours opérateur cible

1. Le caissier ouvre sa caisse alors que le VPS est joignable.
2. EduSync arme automatiquement le lease si l'utilisateur possède `finance.offline.arm`.
3. Snapshot + reçus + limites sont stockés durablement sur l'appareil.
4. En ligne, la caisse continue avec le même lease.
5. Si Internet tombe, seuls les paiements CASH autorisés sont acceptés ; les reçus préalloués sont émis.
6. À la reconnexion, le client envoie **le journal complet** afin de vérifier la chaîne puis rejoue exact-once.
7. Après application de tout le journal, EduSync rapproche count/CDF/USD/hash.
8. Les reçus inutilisés deviennent VOID, le lease est CLOSED, les autres writers Finance peuvent reprendre.

## Incident appareil perdu/cassé

Ne pas créer immédiatement une nouvelle caisse Finance. Chercher d'abord la récupération du stockage local et les reçus papier. Si l'appareil est irrécupérable, utiliser le processus administratif force-release avec motif, audit et rapprochement manuel. Cette action ne doit jamais être déléguée au rôle CAISSIER ordinaire.
