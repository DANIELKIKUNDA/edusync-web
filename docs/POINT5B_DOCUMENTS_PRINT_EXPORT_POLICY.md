# Point 5B — Politique Documents / Export / Impression

## Règles verrouillées
1. **Imprimer un PDF = prévisualiser d’abord.** EduSync génère/ouvre le PDF dans un visualiseur navigateur/lecteur; aucune boîte d’impression n’est déclenchée automatiquement par les modules documentaires.
2. **Paiement et impression sont découplés.** Un paiement validé reste validé même si le PDF ou l’imprimante échoue. La politique de reçu sera configurable au Centre financier: aucune impression automatique (défaut), proposition après validation, ou automatique explicitement activée par l’école.
3. **Un document logique = un fichier courant.** Réexporter le même Excel/PDF avec le même périmètre met à jour le fichier courant. Les suffixes `(1)`, `(2)` ne font pas partie de la stratégie EduSync.
4. **Traçabilité sans encombrement.** `generated_documents` garde les générations append-only; `current_documents` pointe vers la version visible courante. Réimprimer/régénérer ne recrée aucune transaction métier.
5. **Dossier unique hiérarchisé.** Quand l’école autorise l’accès au dossier via l’API File System du navigateur: `Documents EduSync / École / Année / Module / Catégorie / fichier`. Edge/Chrome demandent l’autorisation utilisateur; sans cette autorisation, le navigateur impose son téléchargement standard et EduSync ne prétend pas pouvoir écraser silencieusement un fichier local.
6. **Stockage serveur.** La même clé logique hiérarchique est utilisée derrière `ObjectStoragePort`; l’adaptateur local est destiné dev/test, S3-compatible à la production.
7. **Golden masters.** Aucune modernisation de l’interface ne permet de supprimer colonne, total, filtre, logo, pagination ou format d’un document Desktop certifié.
