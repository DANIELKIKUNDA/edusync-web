# Point 16 — fermeture des limites HTTP et cohérence des imports

- Ferme le contournement des limites de corps HTTP quand `Content-Length` est absent (transfert chunked) : le middleware borne désormais réellement les octets avant FastAPI/parsing.
- Conserve 2 Mio pour les mutations API ordinaires et autorise 10 Mio uniquement sur les trois routes d'analyse XLSX officielles.
- Les handlers d'import lisent eux-mêmes le flux avec un plafond de 10 Mio, défense en profondeur.
- Aligne le contrat 12F : 5 000 lignes maximum pour élèves, personnel **et historique financier**. L'ancien plafond finance à 10 000 était incohérent avec le registre de contrats.
- Aucun élargissement générique de la surface d'attaque.
- La dette npm `latest` reste non modifiée : registre npm inaccessible dans cet environnement, donc aucune version n'est inventée.
