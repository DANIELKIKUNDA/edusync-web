# Point 12F — Centre d’import / fermeture

- Modèles officiels XLSX uniquement.
- Registre serveur des contrats/version et limites publiées.
- Limite 10 Mio et 5 000 lignes par lot.
- Lots analysés/stagés, jamais écriture directe.
- Annulation explicite d’un lot non exécuté, verrou FOR UPDATE et audit.
- Un lot exécuté est immuable et ne peut pas être annulé.
- Historique et rapport de contrôle du Point 12E conservés.
- Finance historique reste hors caisse.
