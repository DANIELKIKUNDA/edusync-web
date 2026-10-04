# Décisions verrouillées — Point 2

1. Le protocole Finance offline courant est `AUTHORIZED_PARTITIONED_CASH_V2`.
2. Plusieurs caissiers peuvent avoir un lease offline actif dans la même école.
3. L'autorité est exclusive **par charge**, pas par école entière.
4. Une charge `ACTIVE` ou `QUARANTINED` ne peut appartenir qu'à un seul lease.
5. Le routing par défaut garde toutes les charges d'un élève sur le même appareil; le routing par famille sera activable lorsque `family_id` sera porté côté Web.
6. CASH peut être final offline sous autorité préarmée. Mobile Money/Banque gardent une finalité dépendante d'une preuve externe.
7. Aucun auto-release serveur sur simple expiration horaire.
8. Force release d'un lease actif => quarantaine des charges concernées, jamais réattribution silencieuse.
9. Retry réseau/double clic/replay => exact-once par operation_id + idempotency_key + reçu + séquence + hash.
10. La synchronisation peut être incrémentale, ancrée sur le checkpoint serveur `last_seq/last_hash`.
11. Le navigateur doit disposer de stockage persistant, WebCrypto et Web Locks avant d'autoriser CASH offline définitif.
12. Une anomalie de solde serveur n'autorise jamais la perte de cash : le posting canonique doit expliquer 100% du montant par allocation réelle + éventuel crédit résiduel explicite de même devise.
13. RLS `school_id` reste obligatoire sur tous les artefacts multi-caissier.
14. Redis n'est jamais source de vérité financière.
15. Aucune permission du nouveau flux incident n'est attribuée définitivement à un rôle au Point 2; Daniel décidera la matrice rôles/permissions au Point 3.
