# probar_equipo.ps1 - Prueba en un Windows de GitHub (2022, 2025, 11 ARM...) el instalador PUBLICADO en trailer-automatico-releases:
# instalar en silencio, autoprueba, abrir el programa, tarea de actualizaciones, el servicio dice "al dia", instalar en una carpeta
# con espacios y acentos, el instalador con ventana (abre el programa y se cierra solo) y desinstalar sin dejar nada.
# Deja resultado.txt, registros y capturas en prueba\ (se suben como Artifact). Sale con 1 si algo falla.
$ErrorActionPreference = "Continue"
$SAL = Join-Path ($env:GITHUB_WORKSPACE ?? (Get-Location).Path) "prueba"
New-Item -ItemType Directory -Force $SAL | Out-Null
$global:MAL = 0
function Ok($t) { "OK     $t" | Tee-Object -FilePath "$SAL\resultado.txt" -Append }
function Falla($t) { "FALLA  $t" | Tee-Object -FilePath "$SAL\resultado.txt" -Append; $global:MAL = 1 }
function Foto($n) {
    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
        $bmp.Save("$SAL\$n.png"); $bmp.Dispose()
    } catch { }
}
$os = Get-CimInstance Win32_OperatingSystem
"equipo: $($os.Caption) $($os.Version) · $env:PROCESSOR_ARCHITECTURE · usuario $env:USERNAME · idioma $((Get-Culture).Name)" |
    Tee-Object -FilePath "$SAL\resultado.txt" -Append
$REL = "https://github.com/AlejandroPiedrasanta/trailer-automatico-releases/releases/latest/download"
$man = Invoke-RestMethod "$REL/version.json"
$ver = $man.estable.version
$exe = Join-Path $env:TEMP "Actualizar_Trailer_automatico_$ver.exe"
Invoke-WebRequest $man.estable.archivos.windows.url -OutFile $exe
if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLower() -eq $man.estable.archivos.windows.sha256) { Ok "instalador $ver bajado (huella correcta)" }
else { Falla "la huella del instalador no coincide" }
$DIR = "$env:LOCALAPPDATA\Programs\TrailerAutomatico"
$DAT = "$env:LOCALAPPDATA\TrailerAutomatico"

# 1. instalar en silencio
$t0 = Get-Date
$p = Start-Process $exe -ArgumentList "/silencioso" -PassThru -Wait
if ($p.ExitCode -eq 0 -and (Test-Path "$DIR\TrailerAutomatico.exe")) { Ok ("instalado en silencio ({0:N0} s)" -f ((Get-Date) - $t0).TotalSeconds) }
else { Falla "instalacion silenciosa (codigo $($p.ExitCode))" }
if ((Get-Content "$DIR\_internal\version.txt" -Raw -ErrorAction SilentlyContinue).Trim() -eq $ver) { Ok "version instalada $ver" } else { Falla "version instalada distinta" }
if (Test-Path "$env:USERPROFILE\Desktop\Tráiler automático.lnk") { Ok "acceso directo en el Escritorio" } else { Falla "no hay acceso directo en el Escritorio" }

# 2. autoprueba (el instalador publico no trae la musica)
$env:TRAILER_SIN_MUSICA = "1"
$f = "$SAL\autoprueba.txt"
Start-Process "$DIR\TrailerAutomatico.exe" -ArgumentList "--tarea", "verificar", "`"$f`"" -Wait -NoNewWindow
$fin = Get-Content $f -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch '^PROGRESO' } | Select-Object -Last 1
if ($fin -like "OK|*") { Ok "autoprueba: $fin" } else { Falla "autoprueba: $fin" }
Remove-Item Env:TRAILER_SIN_MUSICA

# 3. tarea programada de actualizaciones (la crea la instalacion)
$q = schtasks /Query /TN "Trailer automatico Actualizaciones" /XML 2>$null
if ($LASTEXITCODE -eq 0 -and ($q -join "") -match "actualizar_fondo") { Ok "tarea programada de actualizaciones" }
else {
    $inst = Select-String -Path "$DAT\registro\registro.log" -Pattern "Instalacion:" -ErrorAction SilentlyContinue | Select-Object -Last 1
    Falla ("no esta la tarea programada al instalar (" + ($inst.Line ?? "sin registro") + ")")
}

# 4. abrir el programa (ventana real)
$app = Start-Process "$DIR\TrailerAutomatico.exe" -PassThru
Start-Sleep 25
Foto "1_programa_abierto"
$vivo = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
if ($vivo) { Ok ("el programa abre y sigue vivo (ventana '{0}', responde {1})" -f $vivo.MainWindowTitle, $vivo.Responding) } else { Falla "el programa se cerro solo al abrir" }
$reg = "$DAT\registro\registro.log"
Copy-Item $reg "$SAL\registro.log" -ErrorAction SilentlyContinue
$err = Select-String -Path $reg -Pattern "Traceback|ERROR " -ErrorAction SilentlyContinue
if (-not $err) { Ok "registro sin errores" } else { Falla ("errores en el registro: " + (($err | Select-Object -First 2 | ForEach-Object { $_.Line }) -join " | ")) }
if (Test-Path "$DAT\registro\fallo_nativo.log" ) { if ((Get-Item "$DAT\registro\fallo_nativo.log").Length -gt 0) { Falla "fallo nativo (faulthandler)" } }
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Start-Sleep 3

# 5. actualizaciones con el programa cerrado: lee el manifiesto firmado publicado
Start-Process "$DIR\TrailerAutomatico.exe" -ArgumentList "--tarea", "actualizar_fondo" -Wait
$log = Get-Content "$DAT\actualizacion\fondo.log" -ErrorAction SilentlyContinue
Copy-Item "$DAT\actualizacion\fondo.log" "$SAL\fondo.log" -ErrorAction SilentlyContinue
if (($log | Select-Object -Last 1) -match "al_dia") { Ok "el servicio de actualizaciones lee la version publicada (al dia)" } else { Falla ("actualizaciones: " + ($log | Select-Object -Last 1)) }

# 6. instalador con ventana (doble clic): instala, abre el programa y se cierra solo
$t0 = Get-Date
$g = Start-Process $exe -PassThru
$g.WaitForExit(240000) | Out-Null
Start-Sleep 6
Foto "2_despues_del_instalador_con_ventana"
if ($g.HasExited) { Ok ("el instalador con ventana se cerro solo ({0:N0} s)" -f ((Get-Date) - $t0).TotalSeconds) } else { Falla "el instalador con ventana no se cerro"; Stop-Process -Id $g.Id -Force }
$abierto = Get-Process TrailerAutomatico -ErrorAction SilentlyContinue
if ($abierto) { Ok "el programa se abrio solo al terminar" } else { Falla "el programa no se abrio al terminar" }
Get-Process TrailerAutomatico -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 3

# 7. carpeta con espacios y acentos
$otra = "C:\Programas Ñandú\Tráiler Prueba"
$p = Start-Process $exe -ArgumentList "/silencioso", "/noabrir", "/sinescritorio", "`"/dir=$otra`"" -PassThru -Wait
$env:TRAILER_SIN_MUSICA = "1"
$f2 = "$SAL\autoprueba_acentos.txt"
Start-Process "$otra\TrailerAutomatico.exe" -ArgumentList "--tarea", "verificar", "`"$f2`"" -Wait -NoNewWindow -ErrorAction SilentlyContinue
Remove-Item Env:TRAILER_SIN_MUSICA
$fin2 = Get-Content $f2 -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch '^PROGRESO' } | Select-Object -Last 1
if ($p.ExitCode -eq 0 -and $fin2 -like "OK|*") { Ok "instalado y probado en '$otra'" } else { Falla "carpeta con acentos: codigo $($p.ExitCode) · $fin2" }

# 8. desinstalar en silencio: no queda el programa, ni el acceso, ni la tarea, ni la entrada de Aplicaciones
$des = Get-ChildItem $DIR -Filter "Desinstalar*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($des) {
    Start-Process $des.FullName -ArgumentList "/desinstalar", "/silencioso" -Wait
    Start-Sleep 5
    $quedan = @()
    if (Test-Path "$DIR\_internal") { $quedan += "programa" }
    if (Test-Path "$env:USERPROFILE\Desktop\Tráiler automático.lnk") { $quedan += "acceso directo" }
    schtasks /Query /TN "Trailer automatico Actualizaciones" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $quedan += "tarea programada" }
    if (Test-Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\TrailerAutomatico") { $quedan += "entrada de Aplicaciones" }
    if (-not $quedan) { Ok "desinstalado sin dejar nada" } else { Falla ("al desinstalar quedo: " + ($quedan -join ", ")) }
} else { Falla "no encuentro el desinstalador en $DIR" }
""
Get-Content "$SAL\resultado.txt"
exit $global:MAL
