# Point 12E — Traçabilité et contrôle des imports

EduSync conserve désormais une vue serveur paginée des lots Élèves, Personnel et Historique financier, strictement isolée par école. Chaque lot expose fichier, statut, volumes valides/avertissements/erreurs, date d'analyse et date d'exécution.

Un rapport XLSX de contrôle peut être produit pour n'importe quel lot autorisé. Il contient chaque ligne, son état, les codes/champs/messages de contrôle et les données source. Ce rapport permet à l'opérateur de corriger le modèle d'origine sans deviner la cause du rejet.

Le type d'import est résolu par une allow-list serveur fermée ; aucun nom de table fourni par le client n'est accepté. Les permissions d'analyse existantes gouvernent la consultation du journal et des rapports.

Cette passe complète les modèles officiels 12D : modèle versionné → analyse → staging → rapport de contrôle → correction → nouvelle analyse → exécution auditée.


## UI
Les trois surfaces métier affichent maintenant un historique paginé des lots et permettent de télécharger le rapport XLSX de contrôle de chaque analyse.

## Validation locale
- pytest : 430/430 PASS
- compileall : PASS
- build Vite/Excel réel : non certifiés dans cet environnement.
