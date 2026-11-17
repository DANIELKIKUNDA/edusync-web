param(
    [Parameter(Mandatory)][string]$NodeDist,
    [Parameter(Mandatory)][string]$SumatraDist,
    [Parameter(Mandatory)][string]$InnoCompiler,
    [string]$SignToolCommand
)

$ErrorActionPreference = 'Stop'
$node = (Resolve-Path -LiteralPath $NodeDist).Path
$sumatra = (Resolve-Path -LiteralPath $SumatraDist).Path
$compiler = (Resolve-Path -LiteralPath $InnoCompiler).Path
foreach ($file in @("$node\node.exe", "$node\LICENSE", "$sumatra\SumatraPDF.exe", "$sumatra\COPYING")) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Composant manquant : $file" }
}
$payload = Join-Path $PSScriptRoot 'payload'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
Copy-Item -LiteralPath "$node\node.exe", "$sumatra\SumatraPDF.exe" -Destination $payload -Force
Copy-Item -LiteralPath "$node\LICENSE" -Destination "$payload\Node-LICENSE.txt" -Force
Copy-Item -LiteralPath "$sumatra\COPYING" -Destination "$payload\Sumatra-COPYING.txt" -Force

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$launcher = Join-Path $payload 'EduSyncPrintConnector.exe'
& $csc /nologo /codepage:65001 /target:winexe "/out:$launcher" /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll (Join-Path $PSScriptRoot 'Connector.cs')
if ($LASTEXITCODE -ne 0) { throw 'La compilation du connecteur a échoué.' }

$innoArgs = @()
if ($SignToolCommand) {
    if (-not $SignToolCommand.Contains('$f')) {
        throw 'La commande Inno Setup doit contenir le paramètre $f.'
    }
    $innoArgs += '/DSignStaging'
    $innoArgs += "/Sedusync=$SignToolCommand"
}
$innoArgs += (Join-Path $PSScriptRoot 'installer.iss')
& $compiler @innoArgs
if ($LASTEXITCODE -ne 0) { throw "La création de l’installateur a échoué." }

if ($SignToolCommand) {
    $setup = Join-Path $PSScriptRoot 'dist\EduSync-Print-Setup-Staging-Signed.exe'
    foreach ($file in @($launcher, $setup)) {
        $signature = Get-AuthenticodeSignature -LiteralPath $file
        if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
            Remove-Item -LiteralPath $setup -ErrorAction SilentlyContinue
            throw "Signature Authenticode horodatée invalide : $file ($($signature.Status))"
        }
    }
}
