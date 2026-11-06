# CI sans minutes GitHub — runner local WSL

> **Mise à jour 2026-11-06 — dépôt public.** Le dépôt est public : les runners GitHub standard sont gratuits et ne consomment
> aucune minute. Par défaut, la CI et les contrôles planifiés tournent donc sur `ubuntu-24.04` (GitHub), et plus sur le PC.
> Un runner installé chez soi ne doit jamais servir un dépôt public (une PR d'inconnu exécuterait son code sur le PC).
>
> **Revenir au PC (dépôt redevenu privé)** : `Settings > Secrets and variables > Actions > Variables`, créer la variable
> `CI_RUNS_ON` avec la valeur `["self-hosted","linux","x64","volcano-ci"]`, puis démarrer le runner (ci-dessous).
> Supprimer la variable pour revenir aux runners GitHub. Aucun changement de code n'est nécessaire.

## Objectif

Exécuter les workflows privés sur le PC Windows via WSL Ubuntu, sans consommer les minutes des runners hébergés par GitHub. Le VPS de staging n'héberge aucun runner.

## Prérequis Windows

- WSL 2 avec Ubuntu
- Docker Desktop avec l'intégration WSL activée
- au moins 20 Go libres
- le PC branché au secteur pendant une certification

Vérifier dans Ubuntu :

```bash
uname -m
docker version
git --version
```

Le résultat attendu pour l'architecture est `x86_64`.

## Enregistrement du runner

Dans le dépôt GitHub, ouvrir :

`Settings > Actions > Runners > New self-hosted runner > Linux > x64`

Copier les commandes affichées par GitHub dans Ubuntu. Lors de la commande `config.sh`, ajouter le label personnalisé :

```bash
--labels volcano-ci
```

Exemple de forme générale (utiliser impérativement la version et le jeton affichés par GitHub) :

```bash
mkdir -p ~/actions-runner
cd ~/actions-runner
# télécharger et extraire l'archive indiquée par GitHub
./config.sh --url URL_DU_DEPOT --token JETON_TEMPORAIRE --labels volcano-ci --unattended
```

Ne jamais enregistrer le jeton dans Git, une capture ou un fichier du projet. Il expire rapidement.

## Démarrage

Mode interactif, recommandé pour le premier test :

```bash
cd ~/actions-runner
./run.sh
```

Le terminal doit rester ouvert. GitHub affiche alors le runner comme `Idle`.

Après validation, le runner peut devenir un service WSL :

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

## Capacité limitée du PC

- un seul job par instance de runner ;
- ne pas installer deux runners actifs simultanément sur un PC de 8 Go pendant la première validation ;
- commencer par EduSync, puis arrêter son service avant une certification EduNova ;
- fermer Android Studio et les applications lourdes ;
- les workflows en attente ne consomment aucune minute GitHub.

## Sécurité

- uniquement pour les dépôts privés contrôlés par Volcano Tech ;
- ne jamais accepter automatiquement du code provenant d'un fork inconnu ;
- aucun secret de production permanent sur le PC ;
- conserver les déploiements soumis aux validations GitHub existantes ;
- arrêter le runner hors des périodes de travail.

## Retour temporaire aux runners GitHub

Tant que cette branche n'est pas fusionnée, les workflows actuels restent inchangés. Pour revenir plus tard aux runners payants, remplacer :

```yaml
runs-on: [self-hosted, linux, x64, volcano-ci]
```

par :

```yaml
runs-on: ubuntu-24.04
```

## Vérification

1. Le runner apparaît `Idle` dans les paramètres GitHub.
2. Lancer manuellement un workflow léger avec `Run workflow`.
3. Confirmer dans le résumé du job que le runner porte les labels `self-hosted`, `Linux`, `X64` et `volcano-ci`.
4. Vérifier les tests avant de fusionner la branche de contrôle des coûts.


## Validation réelle du 4 novembre 2026

- runner : `volcano-wsl-edusync`
- environnement : Ubuntu 22.04 sous WSL 2, Linux x64
- labels vérifiés : `self-hosted`, `Linux`, `X64`, `volcano-ci`
- Docker : contrôle réussi
- smoke test : [run 41899727852](https://github.com/DANIELKIKUNDA/edusync-web/actions/runs/41899727852), conclusion `success`
- durée du job : 21 secondes
- staging : non sollicité par ce smoke test

Cette preuve valide le routage et l'accès Docker, pas encore la suite fonctionnelle complète.
