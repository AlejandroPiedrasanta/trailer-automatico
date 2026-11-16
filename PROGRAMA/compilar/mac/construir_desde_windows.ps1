# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/construir_desde_windows.ps1 — arma los instaladores de Mac DESDE WINDOWS (como CineSlide): Windows no puede
# compilar para Mac, así que lanza «Instaladores Mac» (.github/workflows/mac.yml) en las Mac de GitHub (Apple Silicon e Intel),
# espera y deja los .dmg en «3 INSTALADORES\Mac» (quita los de versiones anteriores) y las capturas de la ventana del
# instalador en PROGRAMA\datos\capturas_mac.
#   pwsh -File PROGRAMA/compilar/mac/construir_desde_windows.ps1            el de la persona («Doble clic para instalar»)
#   pwsh -File PROGRAMA/compilar/mac/construir_desde_windows.ps1 -Publico   el de las actualizaciones (sin música)
# Compila lo que está SUBIDO a GitHub: antes, subir los cambios (git push).
param([switch]$Publico)
$ErrorActionPreference = 'Stop'
$base = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $base

gh auth status *> $null
if ($LASTEXITCODE) { throw 'Falta iniciar sesión en GitHub: gh auth login' }
$rama = (git rev-parse --abbrev-ref HEAD).Trim()
git fetch -q origin $rama
$pendientes = [int](git rev-list --count "origin/$rama..HEAD")
if ($pendientes -gt 0) { throw "Hay $pendientes commit(s) sin subir: GitHub compilaría lo de antes. Súbelos (git push) y vuelve a correr esto." }
if (git status --porcelain -- PROGRAMA .github) { Write-Warning 'Hay cambios sin guardar en git: NO entran en el instalador.' }

$antes = gh run list --workflow mac.yml -L 1 --json databaseId --jq '.[0].databaseId'
gh workflow run mac.yml --ref $rama -f "publico=$($Publico.IsPresent.ToString().ToLower())"
if ($LASTEXITCODE) { throw 'GitHub no aceptó la compilación' }
$id = $null
for ($i = 0; $i -lt 40 -and -not $id; $i++) {
    Start-Sleep -Seconds 3
    $n = gh run list --workflow mac.yml -L 1 --json databaseId --jq '.[0].databaseId'
    if ($n -and $n -ne $antes) { $id = $n }
}
if (-not $id) { throw 'GitHub no empezó la compilación' }
$repo = gh repo view --json nameWithOwner --jq .nameWithOwner
Write-Host "Compilando en las Mac de GitHub (unos 20 min): https://github.com/$repo/actions/runs/$id" -ForegroundColor Cyan
gh run watch $id --exit-status --interval 30 | Out-Null
if ($LASTEXITCODE) { throw "La compilación falló. Detalle: gh run view $id --log-failed" }

$tmp = Join-Path ([IO.Path]::GetTempPath()) "trailer_mac_$id"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
gh run download $id -D $tmp
if ($LASTEXITCODE) { throw 'No se pudieron bajar los instaladores de GitHub' }

$salida = Join-Path $base '3 INSTALADORES\Mac'
New-Item -ItemType Directory -Force $salida | Out-Null
$dmgs = @(Get-ChildItem $tmp -Recurse -Filter *.dmg)
if (-not $dmgs) { throw 'La compilación no dejó ningún .dmg' }
foreach ($d in $dmgs) {
    $tipo = $d.Name -replace '_[0-9.]+\.dmg$', ''                   # Instalar_Trailer_automatico_Mac_AppleSilicon
    Get-ChildItem $salida -Filter "${tipo}_*.dmg" | Where-Object Name -ne $d.Name | Remove-Item -Force
    Move-Item $d.FullName (Join-Path $salida $d.Name) -Force
    Write-Host ("  {0}  ({1:N0} MB)" -f $d.Name, ($d.Length / 1MB)) -ForegroundColor Green
}
$capturas = @(Get-ChildItem $tmp -Recurse -Filter *.png)
if ($capturas) {
    $dc = Join-Path $base 'PROGRAMA\datos\capturas_mac'
    New-Item -ItemType Directory -Force $dc | Out-Null
    foreach ($c in $capturas) { Copy-Item $c.FullName (Join-Path $dc ("{0}_{1}" -f $c.Directory.Name, $c.Name)) -Force }
    Write-Host "  capturas de la ventana del instalador: $dc"
}
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Listo: $salida" -ForegroundColor Cyan
