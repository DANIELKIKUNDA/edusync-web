param(
    [Parameter(Mandatory)][string]$Origin,
    [Parameter(Mandatory)][string]$Printer,
    [Parameter(Mandatory)][string]$SumatraPdf,
    [switch]$StartAtLogon
)

$ErrorActionPreference = 'Stop'
$uri = [Uri]$Origin
if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or
    $uri.GetLeftPart([UriPartial]::Authority) -cne $Origin) {
    throw 'Indiquer uniquement l’origine HTTPS EduSync, sans barre finale.'
}
if (-not (Get-Printer -Name $Printer -ErrorAction SilentlyContinue | Where-Object { $_.Name -ceq $Printer })) {
    throw 'Imprimante introuvable. Consultez les noms exacts avec Get-Printer.'
}
$renderer = (Resolve-Path -LiteralPath $SumatraPdf).Path
if ((Split-Path -Leaf $renderer) -ine 'SumatraPDF.exe') {
    throw 'Indiquer le chemin vers SumatraPDF.exe.'
}
$node = (Get-Command node.exe -CommandType Application | Select-Object -First 1).Source
$root = Join-Path $env:LOCALAPPDATA 'EduSyncPrintAgent'
$config = Join-Path $root 'config.json'
New-Item -ItemType Directory -Path $root -Force | Out-Null

$key = $null
if (Test-Path -LiteralPath $config) {
    $previous = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    if ($previous.origin -ceq $Origin -and $previous.key -cmatch '^[a-f0-9]{64}$') { $key = $previous.key }
}
if (-not $key) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $key = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'server.mjs') -Destination $root -Force
@{origin=$Origin; key=$key; printer=$Printer; renderer=$renderer} |
    ConvertTo-Json | Set-Content -LiteralPath $config -Encoding UTF8

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Agent impression EduSync.lnk'))
$shortcut.TargetPath = $node
$shortcut.Arguments = '"{0}" "{1}"' -f (Join-Path $root 'server.mjs'), $config
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$shortcut.Save()
if ($StartAtLogon) {
    Copy-Item -LiteralPath $shortcut.FullName -Destination ([Environment]::GetFolderPath('Startup')) -Force
}
Write-Host 'Agent installé. Ouvrez le raccourci Agent impression EduSync sur le Bureau.'
Write-Host 'Collez cette clé privée dans le réglage Impression directe sur ce poste :'
Write-Host $key
