# Impression directe des reçus EduSync Web

## Fonctionnement

Sur un poste Windows associé, le bouton **Imprimer** obtient le PDF officiel et l’envoie à
l’agent EduSync, qui utilise SumatraPDF et le pilote Windows de l’imprimante configurée.
Les boutons de la caisse, des paniers familiaux, des fonds, de l’encaissement après
l’inscription et de la file des reçus utilisent la même liaison. Ouvrir l’aperçu reste
possible pour inspecter le document ou utiliser le dialogue d’impression.

L’agent reçoit seulement des PDF de l’origine EduSync choisie à l’installation,
sur `127.0.0.1:47319`, avec une clé aléatoire par poste. Aucun port entrant du réseau
n’est nécessaire. La clé est propre au profil du navigateur. Le PDF temporaire est retiré
après chaque tentative normale. Le paiement et les droits de génération du PDF
restent gérés par EduSync, ainsi que la trace original/duplicata et la file des reçus.

L’indication **Reçu envoyé** confirme la remise au système d’impression Windows.
Après la sortie papier, le caissier peut confirmer l’impression dans la file.
Une interruption réseau ou du processus d’impression peut laisser un envoi non confirmé.
Contrôler dans ce cas le ticket et la file Windows avant de relancer. L’application
n’envoie pas automatiquement une deuxième copie par le navigateur.

## Installer sur le poste de caisse

1. Installer le pilote Windows du constructeur et imprimer une page de test depuis Windows.
   Choisir la largeur adéquate dans les préférences du pilote et dans EduSync.
   Les options de coupe dépendent du pilote de l’imprimante.
2. Installer Node.js 22 ou ultérieur et une version récente de
   [SumatraPDF](https://www.sumatrapdfreader.org/download-free-pdf-viewer).
   Récupérer `install.ps1` et `server.mjs` du dossier `tools/print-agent` du même commit EduSync.
3. Depuis PowerShell, dans le dossier contenant ces deux fichiers, exécuter
   `Get-Printer | Select-Object Name` pour relever le nom exact de l’imprimante.
   Installer ensuite l’agent pour l’origine de recette, en remplaçant le nom
   et le chemin par les valeurs du poste :

   ```powershell
   .\install.ps1 -Origin 'https://staging.myeducsync.com' -Printer 'Nom exact' -SumatraPdf 'C:\Chemin\SumatraPDF.exe'
   ```

   Ajouter `-StartAtLogon` pour démarrer l’agent à l’ouverture de la session Windows.
   Le raccourci **Agent impression EduSync** permet de le lancer immédiatement.
4. Dans EduSync, ouvrir les **réglages d’impression des reçus**, puis
   **Impression directe sur ce poste**. Saisir la clé affichée après l’installation et
   cliquer sur **Associer ce poste**. Autoriser l’accès au réseau local dans le navigateur
   si la permission est demandée pour l’origine EduSync configurée.
   La vérification confirme la liaison et affiche le nom de l’imprimante configurée.

Pour changer d’imprimante ou d’environnement, arrêter l’agent, relancer l’installation
avec les nouveaux paramètres puis relancer le raccourci. Pour revenir au dialogue
standard, cliquer sur **Désactiver l’impression directe** dans le profil du navigateur.

## Recette matérielle

Sur staging avec un reçu de recette, vérifier la sortie au format configuré, les
caractères accentués, les montants, la largeur et la coupe. Tester ensuite un lot,
une imprimante éteinte et un agent arrêté. Vérifier qu’un refus d’impression ne modifie
pas le paiement et que la confirmation papier reste une action explicite dans la file.
