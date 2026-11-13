# publicar_version.ps1 - Publica una version de Tráiler automático para que los programas instalados se actualicen solos
# (como Publicar_Version.ps1 de CineCaptions). Todo va al repositorio PUBLICO de versiones trailer-automatico-releases:
#   1. compila Windows (construir.ps1): instalador completo (3 INSTALADORES\Windows) + el publico sin musica (datos\publicar)
#   2. compila los .dmg publicos de Mac en GitHub Actions ("Instaladores Mac" con publico=true) y los baja
#   3. arma version.json (url, sha256 y tamano de cada instalador) y lo FIRMA (firmar_manifiesto.py, clave fuera del repo)
#   4. crea el release vX.Y.Z con los 3 instaladores + version.json (queda como "latest": de ahi leen los programas)
# Los instaladores publicos NO traen musica, SFX ni la fuente con licencia: los programas instalados usan la que ya tienen.
# Uso:  pwsh -File PROGRAMA\herramientas\publicar_version.ps1 -Notas "Lo nuevo en una o dos lineas"
#       -SinCompilar   reusa lo ya compilado en datos\publicar     -SinMac   publica solo Windows
param([Parameter(Mandatory = $true)][string]$Notas, [switch]$SinCompilar, [switch]$SinMac)
$ErrorActionPreference = "Stop"
$herr = $PSScriptRoot
$prog = Split-Path $herr -Parent
$base = Split-Path $prog -Parent
$REPO_CODIGO = "AlejandroPiedrasanta/trailer-automatico"
$REPO_VERSIONES = "AlejandroPiedrasanta/trailer-automatico-releases"
$ver = (Get-Content "$prog\config\version.txt" -Raw).Trim()
$pub = Join-Path $prog "datos\publicar"
New-Item -ItemType Directory -Force $pub | Out-Null
$t0 = Get-Date
function Paso($m) { Write-Host ("[{0:mm\:ss}] {1}" -f ((Get-Date) - $t0), $m) }

Paso "Version $ver"
if (gh release view "v$ver" --repo $REPO_VERSIONES 2>$null) { throw "La version $ver ya esta publicada: sube PROGRAMA\config\version.txt" }
if (-not (Test-Path "$HOME\TrailerAutomatico_claves\firma_principal.txt") -and -not $env:TRAILER_CLAVE_FIRMA) {
    throw "Falta la clave de firma en $HOME\TrailerAutomatico_claves: sin ella los programas no aceptan la version"
}
if (git -C $base status --porcelain) { throw "Hay cambios sin subir a GitHub: haz commit y push antes de publicar" }
git -C $base push -q 2>$null

if (-not $SinCompilar) {
    Paso "Windows (construir.ps1)"
    pwsh -NoProfile -File "$prog\compilar\windows\construir.ps1"
    if ($LASTEXITCODE -ne 0) { throw "La compilacion de Windows fallo" }
}
$exe = Join-Path $pub "Actualizar_Trailer_automatico_$ver.exe"
if (-not (Test-Path $exe)) { throw "No esta $exe" }

$dmgs = @{}
if (-not $SinMac) {
    $listos = Get-ChildItem $pub -Filter "Actualizar_Trailer_automatico_Mac_*_$ver.dmg" -ErrorAction SilentlyContinue
    if ($SinCompilar -and $listos.Count -eq 2) {
        Paso "Mac: reuso los .dmg ya bajados"
    } else {
        Paso "Mac: compilando los .dmg publicos en GitHub (unos 20 min)"
        $sha = (git -C $base rev-parse HEAD).Trim()
        gh workflow run "Instaladores Mac" --repo $REPO_CODIGO -f publico=true | Out-Null
        $id = $null
        for ($i = 0; $i -lt 30 -and -not $id; $i++) {
            Start-Sleep 5
            $id = gh run list --repo $REPO_CODIGO --workflow "Instaladores Mac" --limit 5 --json databaseId,headSha,event `
                --jq "[.[] | select(.headSha == `"$sha`" and .event == `"workflow_dispatch`")][0].databaseId"
        }
        if (-not $id) { throw "No encuentro la compilacion de Mac en GitHub" }
        for ($intento = 1; $intento -le 3; $intento++) {
            gh run watch $id --repo $REPO_CODIGO --exit-status --interval 60 | Out-Null
            $jobs = gh run view $id --repo $REPO_CODIGO --json jobs --jq '[.jobs[] | select(.conclusion != "success")] | length'
            if ($jobs -eq "0") { break }
            Paso "  Mac: alguna compilacion no termino (sin Mac libre en GitHub): reintento $intento de 3"
            gh run rerun $id --failed --repo $REPO_CODIGO | Out-Null
            Start-Sleep 20
        }
        $tmp = Join-Path $pub "dmg_$ver"
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        gh run download $id --repo $REPO_CODIGO -D $tmp
        Get-ChildItem $tmp -Recurse -Filter "Actualizar_*_$ver.dmg" | Move-Item -Destination $pub -Force
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
    foreach ($a in @(@("mac_arm64", "AppleSilicon"), @("mac_x86_64", "Intel"))) {
        $d = Join-Path $pub "Actualizar_Trailer_automatico_Mac_$($a[1])_$ver.dmg"
        if (-not (Test-Path $d)) { throw "Falta $d" }
        $dmgs[$a[0]] = $d
    }
}

Paso "version.json firmado"
$url = "https://github.com/$REPO_VERSIONES/releases/download/v$ver"
function Archivo($ruta) {
    @{ url = "$url/" + [Uri]::EscapeDataString((Split-Path $ruta -Leaf)); sha256 = (Get-FileHash $ruta -Algorithm SHA256).Hash.ToLower();
       tam = (Get-Item $ruta).Length }
}
$archivos = [ordered]@{ windows = (Archivo $exe) }
foreach ($k in $dmgs.Keys) { $archivos[$k] = (Archivo $dmgs[$k]) }
$manifiesto = [ordered]@{ estable = [ordered]@{ version = $ver; notas = $Notas; fecha = (Get-Date -Format "yyyy-MM-dd"); archivos = $archivos } }
$json = Join-Path $pub "version.json"
$manifiesto | ConvertTo-Json -Depth 6 | Set-Content $json -Encoding utf8NoBOM
python "$herr\firmar_manifiesto.py" $json
if ($LASTEXITCODE -ne 0) { throw "No se pudo firmar version.json" }

Paso "Release v$ver en $REPO_VERSIONES"
if (-not (gh repo view $REPO_VERSIONES --json name 2>$null)) {
    gh repo create $REPO_VERSIONES --public --add-readme `
        --description "Instaladores y actualizaciones de Tráiler automático (CINEMA PRODUCTIONS)" | Out-Null
}
$subir = @($exe) + @($dmgs.Values) + @($json)
gh release create "v$ver" --repo $REPO_VERSIONES --title "Tráiler automático $ver" --notes $Notas --latest @subir
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el release" }
Paso "Publicada: https://github.com/$REPO_VERSIONES/releases/tag/v$ver (los programas instalados la toman en menos de 4 h)"
