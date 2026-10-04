# EduSync — Point 10G — Fermeture pré-production

Date: 2026-09-13
Version: 0.21.0-point10g

## Corrections réalisées
- Sécurité du compte activée: changement de mot de passe réel, vérification Argon2 du mot de passe courant, nouveau hash Argon2 et incrément atomique de `users.version`. Les anciens JWT deviennent immédiatement obsolètes grâce au contrôle `user_version` déjà exécuté à chaque requête.
- Le bouton « Sécurité du compte » du menu utilisateur n'est plus factice/désactivé. Une boîte de dialogue dédiée est branchée au backend; après modification, reconnexion obligatoire.
- Suppression du composant de connexion historique `LegacyLogin`; `SecureLogin` reste l'unique surface de connexion.
- Passe globale sur les erreurs frontend: suppression des rendus directs `String(e)` / `e.message` identifiés; passage par `friendlyError()` et conservation des diagnostics techniques hors interface.
- Versions harmonisées: frontend `0.21.0-point10g`, backend `0.21.0`, API `0.21.0-point10g-preproduction`.
- Tests de non-régression Point 10G ajoutés pour sécurité du compte, absence de fuite d'erreur brute et cohérence des versions.

## Validation locale
- `pytest`: 325/325 PASS.
- `python -m compileall -q src`: PASS.
- Audit statique ciblé: aucun `setError(String(e))`, aucun ancien pattern direct `e.message`, aucun `window.alert()` dans `frontend/src`.

## Gates qui restent volontairement au Point 11
- Build React/TypeScript réel: tentative d'installation npm dans cet environnement interrompue par timeout; aucune certification frontend n'est revendiquée.
- PostgreSQL live + FORCE RLS + concurrence multi-caissier.
- Redis live, reprise après panne et workers de communication.
- HTTPS/reverse proxy, navigateur Windows, PWA/offline, réseau lent/coupures, impression et exports.
- Tests offensifs sécurité (XSS, CSRF selon stratégie de session finale, IDOR/BOLA, cross-tenant, replay, brute force distribué, uploads).
- Parité documentaire Finance marquée `DESKTOP_GOLDEN_REQUIRED` là où les golden masters bruts restent nécessaires.

## Reliquats fonctionnels connus, non maquillés
- Intendance: l'ajustement de stock générique doit encore recevoir une sémantique explicite hausse/baisse avant exposition complète; les workflows patrimoine/inventaires physiques restent à fermer.
- Sync: l'API d'administration complète des appareils/conflits n'est pas encore fermée.
- Communications externes: aucun fournisseur SMS réel n'est certifié sans credentials et tests live.
- `/health` conserve volontairement le lot historique Point 4D pour ne pas casser le contrat de préservation; la metadata de release est portée par la version API. Sa séparation définitive doit être faite avec les tests d'infrastructure du Point 11.
