# Point 11C — Atelier Pro : Notifications système & supervision

## Fermé localement
- Module réel **Notifications système** dans Atelier Pro.
- Diffusion interne vers une école ACTIVE ou toutes les écoles ACTIVE.
- Destinataires calculés côté serveur : appartenances actives + utilisateurs actifs.
- Campagne durable `platform_system_notifications`, nombre de destinataires conservé.
- Idempotency-Key obligatoire ; permission `platform.notifications.system.send` ; audit append-only `PLATFORM_SYSTEM_NOTIFICATION_SENT`.
- Aucun SMS/WhatsApp implicite : ce module est strictement une notification système interne.
- Historique paginé des campagnes dans l'interface.
- Diagnostics enrichis : PostgreSQL, outbox, conflits Sync, écoles actives, sessions appareil non révoquées, livraisons SMS terminalement échouées.
- Doctrine maintenue : aucun verrou global des écoles.

## Validation locale
- `pytest`: 379/379 PASS.
- `python -m compileall -q src`: PASS.
- Build Vite/TypeScript non certifié dans cet environnement si `node_modules` est absent.

## Gates machine restant
PostgreSQL/Redis réels, migrations sur base de recette, navigateur/Windows, tests de charge, reprise worker, tests offensifs et fournisseur SMS réel.
