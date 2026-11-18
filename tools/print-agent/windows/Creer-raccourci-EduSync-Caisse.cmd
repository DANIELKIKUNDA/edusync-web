@echo off
rem EduSync - poste de caisse : impression directe des recus sans programme a installer (decision du 17/11/2026).
rem Cree sur le Bureau le raccourci "EduSync Caisse" : Chrome (ou Edge) ouvre EduSync dans un profil a part, avec
rem l'impression directe (--kiosk-printing) sur l'imprimante PAR DEFAUT de Windows. Aucun programme non signe,
rem aucun droit administrateur, aucun reglage de securite modifie. Le Chrome habituel de l'utilisateur n'est pas touche.
rem Usage : double-clic (production) ; pour le staging : Creer-raccourci-EduSync-Caisse.cmd https://staging.myeducsync.com
setlocal
set "EDUSYNC_URL=%~1"
if "%EDUSYNC_URL%"=="" set "EDUSYNC_URL=https://app.myeducsync.com"
powershell -NoProfile -Command ^
  "$url=$env:EDUSYNC_URL; if($url -notmatch '^https://[a-z0-9.-]+$'){Write-Host 'Adresse EduSync invalide.'; exit 1};" ^
  "$browser=@(\"$env:ProgramFiles\Google\Chrome\Application\chrome.exe\",\"${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe\",\"$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe\",\"${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe\",\"$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe\") | Where-Object {Test-Path $_} | Select-Object -First 1;" ^
  "if(-not $browser){Write-Host 'Ni Chrome ni Edge trouve sur ce poste.'; exit 1};" ^
  "$staging=$url -match 'staging'; $name=if($staging){'EduSync Caisse (staging)'}else{'EduSync Caisse'}; $profile=Join-Path $env:LOCALAPPDATA ($(if($staging){'EduSyncCaisseStaging'}else{'EduSyncCaisse'}));" ^
  "New-Item -ItemType Directory -Force -Path $profile | Out-Null; $ico=Join-Path $profile 'EduSync.ico'; $icon=$browser+',0';" ^
  "try{Invoke-WebRequest -UseBasicParsing -Uri ($url+'/icons/favicon.ico') -OutFile $ico; $icon=$ico+',0'}catch{Write-Host 'Logo EduSync indisponible : icone du navigateur utilisee.'};" ^
  "$lnk=Join-Path ([Environment]::GetFolderPath('Desktop')) ($name+'.lnk'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath=$browser; $s.Arguments=('--user-data-dir=\"{0}\" --kiosk-printing --app={1}' -f $profile,$url); $s.IconLocation=$icon; $s.Description='EduSync - caisse avec impression directe des recus'; $s.Save();" ^
  "$def=(Get-CimInstance Win32_Printer | Where-Object Default).Name;" ^
  "Write-Host ''; Write-Host ('Raccourci cree sur le Bureau : '+$name); Write-Host ('Navigateur : '+$browser);" ^
  "Write-Host ('Imprimante par defaut actuelle : '+$(if($def){$def}else{'aucune'})); Write-Host 'Les recus imprimes depuis ce raccourci partent directement sur cette imprimante.'"
echo.
pause
