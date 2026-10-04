# Matrice officielle des opérations offline — Point 1

| Domaine/opération | Hors ligne | Finalité | Conflit / synchronisation |
|---|---|---|---|
| Consultations/référentiels déjà synchronisés | Oui | Lecture locale | fraîcheur affichée, refresh au retour réseau |
| Profil élève/famille | Oui | locale puis sync | optimistic lock + revue humaine |
| Inscription/réinscription | Oui | locale puis sync | version obligatoire, stale rejeté |
| Paramètres scolaires syncables | Oui | locale puis sync | stale rejeté, pas de last-write-wins |
| Encaissement CASH | Oui | **définitif sous préautorisation** | exact-once, reçus uniques, no auto-merge, rapprochement |
| Mobile Money/Banque | Saisie offline possible | finalité différée | validation externe avant solde définitif |
| Mouvement stock | Oui | locale puis sync | recalcul transactionnel serveur |
| Audit | Oui | append local puis serveur | append-only/dédoublonné |
| Rôles/permissions | Non pour changement définitif | serveur | autorité IAM live requise |
| Création/suspension école Atelier Pro | Non | serveur | autorité plateforme live requise |

Cette matrice indique une **capacité technique**, pas une permission utilisateur. Les permissions finales sont définies au point 3 par Daniel.
