# EduSync Print Connector pour staging

L’installateur est destiné à Windows x64. Il installe le lanceur, le runtime Node.js et SumatraPDF dans le profil Windows de l’utilisateur, sans élévation. Le pilote de l’imprimante doit déjà être installé.

## Construire

Sur un poste de build Windows avec Inno Setup 6, préparer la distribution Windows x64 de Node.js (`node.exe` et `LICENSE`) et la distribution portable Windows x64 de SumatraPDF (`SumatraPDF.exe` et le fichier `COPYING` de la même version). Utiliser des distributions de provenance vérifiée et conserver les versions et empreintes pour reproduire la livraison.

```powershell
.\build.ps1 -NodeDist C:\build\node -SumatraDist C:\build\sumatra -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

Le build sans signature produit `dist\EduSync-Print-Setup-Staging.exe` pour les tests internes. Respecter les conditions de redistribution de SumatraPDF et fournir le code source correspondant lors de la distribution du binaire.

### Produire la version signée

La machine de build doit avoir accès à un certificat de signature de code reconnu par Windows. Utiliser la commande du fournisseur comme argument `-SignToolCommand` lors du build. La commande Inno Setup doit contenir `$f` pour le fichier à signer et appliquer un horodatage RFC 3161.

Pour un certificat utilisable via le magasin Windows du compte de build, exemple avec SignTool dans le PATH :

```powershell
$sign = 'signtool.exe sign /sha1 EMPREINTE_CERTIFICAT /fd SHA256 /tr URL_HORODATAGE_FOURNISSEUR /td SHA256 $f'
.\build.ps1 -NodeDist C:\build\node -SumatraDist C:\build\sumatra -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' -SignToolCommand $sign
```

L’installateur signé est `dist\EduSync-Print-Setup-Staging-Signed.exe`. Inno Setup signe le lanceur, l’installateur et le désinstallateur. Le build vérifie les signatures horodatées du lanceur et de l’installateur. Avant diffusion, vérifier aussi le désinstallateur installé et refaire l’installation et l’impression directe sur un PC où Smart App Control est actif.

## Valider sur Windows

1. Fermer l’ancien agent s’il occupe le port local 47319. Installer le connecteur sur un profil Windows vierge et sélectionner l’imprimante déclarée dans Windows (par exemple `XP-80C`).
2. Sur staging, ouvrir **Documents → Logo et impression**. Si ce navigateur garde la liaison de l’ancien agent, la désactiver. Cliquer sur **Connecter mon imprimante** et confirmer dans Windows. Autoriser l’accès au réseau local si le navigateur le demande.
3. Sélectionner **Ticket thermique 80 mm**, puis imprimer un reçu existant. Vérifier sa lisibilité, le total et les bords du ticket. Tester également le refus de la demande, le redémarrage Windows, la reconnexion et l’impression classique en secours.
4. Pour arrêter le processus avant une mise à jour, utiliser **Quitter le connecteur** dans la zone de notification. L’installateur conserve la configuration du profil lors d’une mise à jour.

Le connecteur utilise uniquement l’origine staging. Il écoute sur l’adresse locale, vérifie l’origine des demandes et requiert une confirmation Windows avant de transmettre la clé au navigateur. Les demandes d’impression restent authentifiées. Un envoi dont le résultat est incertain doit être vérifié avant toute réimpression.
