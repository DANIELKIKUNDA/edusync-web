# Creates the EduSync desktop shortcuts (owner's workstation). Safe to run again: shortcuts are replaced.
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$desktop = [Environment]::GetFolderPath('Desktop')
$icon = Join-Path $root 'frontend\public\icons\favicon.ico'
$shell = New-Object -ComObject WScript.Shell
function New-EduSyncShortcut($name, $target, $arguments, $description, $style) {
  $lnk = $shell.CreateShortcut((Join-Path $desktop "$name.lnk"))
  $lnk.TargetPath = $target
  $lnk.Arguments = $arguments
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = "$icon,0"
  $lnk.Description = $description
  $lnk.WindowStyle = $style
  $lnk.Save()
  Write-Output "Raccourci cree : $name"
}
New-EduSyncShortcut 'EduSync' (Join-Path $root 'tools\local\EduSync-Demarrer.cmd') '' 'Demarrer EduSync et ouvrir l''application' 1
New-EduSyncShortcut 'Arreter EduSync' (Join-Path $root 'tools\local\EduSync-Arreter.cmd') '' 'Arreter proprement tous les services EduSync' 1
New-EduSyncShortcut 'Journaux EduSync' (Join-Path $root 'tools\local\EduSync-Journaux.cmd') '' 'Ouvrir le dossier des journaux EduSync' 7