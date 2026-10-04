> **Historique V1 :** ce document décrit WEB-0D single-writer. Depuis le Point 2, la cible et l’implémentation courante sont `AUTHORIZED_PARTITIONED_CASH_V2`. Voir `POINT2_FINANCE_OFFLINE_MULTI_CAISSIER.md`.

# WEB-0D — Doctrine officielle d'encaissement Finance Offline

## Règle 1 — Offline-first ne signifie pas écriture financière anarchique

Un paiement physique peut être définitif hors connexion seulement si l'appareil possède avant la coupure une autorité d'écriture financière bornée délivrée par le serveur.

## Règle 2 — V1 = un writer Finance par école

Le mode `EXCLUSIVE_SINGLE_WRITER_CASH_V1` privilégie la sûreté. Une seule caisse/appareil possède l'autorité financière à un instant donné pour l'école. Elle peut travailler en ligne ou hors ligne ; les autres writers Finance sont bloqués tant que le lease n'est pas réconcilié.

Pour une école à un seul caissier, l'armement peut être automatique lors de l'ouverture de caisse. L'utilisateur travaille normalement, puis continue sans interruption si Internet tombe.

Une future V2 pourra partitionner l'autorité entre plusieurs caisses, mais seulement avec une règle métier explicite de partitionnement. WEB-0D n'invente pas une fusion concurrente des paiements.

## Règle 3 — CASH uniquement en offline définitif v1

CASH représente un argent physiquement reçu par le caissier. MOBILE_MONEY et BANQUE demandent une confirmation externe et ne sont donc pas déclarés définitivement payés sans réseau dans cette première doctrine.

## Règle 4 — Les obligations sont figées avant la coupure

Le caissier ne peut régler offline que des charges présentes dans le snapshot serveur. Il ne peut pas créer un nouveau tarif, inventer une remise, accorder une exemption, transformer une devise ou déplacer silencieusement l'argent sur une autre obligation.

## Règle 5 — Un reçu existe avant le paiement

Le serveur réserve des numéros officiels au lease. L'appareil consomme un jeton une seule fois. Le reçu peut donc être remis immédiatement même lorsque le VPS est inaccessible.

Le reçu doit comporter l'identifiant d'opération/QR prévu par le futur générateur. Sa synchronisation n'attribue pas un nouveau numéro : elle conserve le numéro préalloué.

## Règle 6 — Exact-once, jamais « au moins une fois » pour l'argent

Retry réseau, double clic, reprise après timeout et rejeu de journal utilisent toujours la même identité logique. Le serveur ne poste pas un deuxième paiement.

## Règle 7 — CDF et USD restent séparés

Les plafonds, allocations et rapprochements sont calculés séparément. Aucune conversion implicite et aucune somme CDF+USD n'est permise.

## Règle 8 — Le serveur ne libère pas automatiquement un lease offline

La date locale arrête l'appareil mais ne rend pas l'autorité à un autre writer. Une libération automatique créerait une fenêtre où deux caissiers pourraient posséder des vérités différentes. Seule la réconciliation ou une procédure d'incident explicite libère l'école.

## Règle 9 — La clôture est une preuve

Le système compare : nombre d'opérations, nombre de reçus consommés, total CDF, total USD et hash final. Tant qu'un seul élément diverge, la caisse reste en état à traiter.

## Règle 10 — Force-release est une procédure d'incident

Il ne s'agit jamais d'un bouton « débloquer ». Il exige une permission forte, un motif, une trace d'audit et un contrôle des opérations déjà reçues. Il peut être utilisé après perte/casse d'appareil seulement dans un processus de rapprochement manuel documenté.

## Règle 11 — IndexedDB n'est pas le serveur, mais devient une preuve temporaire critique

La PWA exige le stockage persistant avant d'armer la caisse. L'argent offline ne doit pas dépendre d'un simple cache Service Worker. Le journal Finance possède son propre store, ses contraintes uniques et sa chaîne SHA-256.

Pour les postes de caisse les plus critiques, un futur packaging Tauri/desktop pourra reprendre la même architecture avec stockage local durable renforcé, sans modifier les règles métier.

## Règle 12 — Le Desktop existant reste l'oracle métier

Le passage Web ne change pas les règles déjà certifiées : exact allocations, reçu officiel, caisse réelle, absence de conversion implicite, post-commit document séparé, audit et historique. WEB-0D ajoute un transport offline sûr autour de ces invariants ; il ne les remplace pas.
