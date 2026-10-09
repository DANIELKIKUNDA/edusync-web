# Provisionnement des écoles — rapport N1

## Ce qui est livré et prouvé

| Exigence | Implémentation | Preuve |
|---|---|---|
| Identité | Nom (2–160), code 2–32 caractères `A-Z 0-9 -`, normalisé en majuscules | `school-lifecycle-live.json` |
| Contacts | E-mail et téléphone facultatifs, validés (format) | idem « Création complète », « Validation » ×3 |
| Adresse | Adresse, ville, province facultatives | idem |
| Logo | Pas d'URL externe acceptée (ignorée) ; le logo est téléversé par l'école (PNG/JPEG vérifiés, 1 Mo, stockage privé) | idem « URL de logo externe ignorée » ; probes de clôture documents |
| Statut | Créée ACTIVE ; suspension / réactivation avec motif | idem |
| Unicité | Contrainte `schools_code_key` + contrôle applicatif | « Code déjà utilisé -> 409 » |
| Idempotence | `Idempotency-Key` obligatoire ; même clé = même école (en-tête `Idempotent-Replayed`), clé réutilisée pour un autre contenu = 409 | « Réponse perdue / double clic », « Même clé, contenu différent » |
| Concurrence | 4 créations simultanées du même code → 1 école, 3 × 409 | « 4 créations simultanées » (31/31, 2 exécutions). **Défaut corrigé** dans cette passe : une des réponses était un 500 |
| Audit | `SCHOOL_CREATED` avec identité et contacts ; suspension, réactivation, admin initial tracés | « Audit de création », « Audit : création, admin initial… » |
| RLS | La nouvelle école n'est visible qu'à ses membres (RLS FORCE par `app.current_school_id`) | probes de clôture RLS/BOLA ; `notifications-live.json` (isolation des boîtes) |
| Limitation | 30 créations / heure / compte | `hardening-http-live.json` |
| Interface | Dialogue « Nouvelle école » (identité, contacts, adresse), puis directement l'étape administrateur initial | build + capture du parcours |

## Administrateur initial (`platform.school_admin.bootstrap`)
* Nouveau compte : créé avec le mot de passe fourni (hors charge d'idempotence, jamais journalisé) et le rôle
  `ADMIN_SYSTEME_ECOLE`.
* Compte existant (même e-mail) : rattaché à l'école avec le rôle ; **son mot de passe n'est pas modifié**.
* Remplacement d'un administrateur : possible (nouvel administrateur, puis retrait du rôle de l'ancien depuis
  la fiche école).
* Connexion de l'administrateur : automatique dans son école (sans code), vérifiée.
* École suspendue : l'opération est acceptée (préparation), mais personne ne peut se connecter tant que l'école
  est suspendue.

## Effets réels de la suspension (preuve `school-lifecycle-live.json`, 25 contrôles dédiés)
Sessions de l'école fermées, jeton en cours refusé, renouvellement refusé, connexion refusée (automatique et
explicite), liens de documents signés refusés, SMS en attente retenus puis repris à la réactivation, école
exclue des notifications ciblées. Réactivation : tout revient, sans perte.
