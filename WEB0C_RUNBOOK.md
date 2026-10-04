# WEB-0C — Runbook G1 Windows / Docker Desktop

Ce runbook sert à faire la première vraie preuve PostgreSQL/JWT/RLS sur la machine Windows de certification ou sur un VPS de staging. Ne pas l'exécuter contre la production contenant des données réelles.

## Préparation

Dans le dossier WEB-0C, créer `.env` à partir de `.env.example`. Remplacer au minimum :

- mot de passe PostgreSQL owner ;
- mot de passe PostgreSQL tenant ;
- mot de passe PostgreSQL platform ;
- secret JWT d'au moins 32 caractères ;
- mot de passe bootstrap Atelier Pro.

`POSTGRES_OWNER_PASSWORD` doit correspondre au mot de passe présent dans `EDUSYNC_OWNER_DATABASE_URL`.

## Commandes PowerShell, une par une

```powershell
Copy-Item .env.example .env
```

Éditer ensuite `.env`, puis :

```powershell
docker compose up -d --build
```

```powershell
docker compose ps
```

```powershell
docker compose run --rm migrator python scripts/g1_live_certification.py
```

```powershell
docker compose run --rm -e EDUSYNC_API_BASE_URL=http://backend:8000/api/v1 migrator python scripts/g1_api_probe.py
```

Ou lancer directement :

```powershell
.\RUN_G1_WINDOWS.ps1
```

Le script PowerShell refuse les placeholders `CHANGE_...`.

## Résultat attendu

Les deux probes doivent finir par :

```text
G1 LIVE PASS: ...
G1 API PASS
```

Toute ligne `FAIL` bloque le portage des modules métier.

## URLs locales après démarrage

- EduSync Web / Atelier Pro : `http://localhost:8080`
- API : `http://localhost:8000`
- OpenAPI : `http://localhost:8000/docs`

Le frontend Docker utilise aussi `/api/v1` en same-origin via Nginx.

## Après certification

Conserver la sortie terminal complète. Le prochain lot ne doit commencer qu'après analyse de cette sortie et déclaration explicite `G1 LIVE PASS`.
