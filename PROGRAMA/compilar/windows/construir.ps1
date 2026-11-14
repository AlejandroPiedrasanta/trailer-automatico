# construir.ps1 - Compila el "Trailer automatico" y crea su instalador .exe para Windows.
#   1. icono   2. PyInstaller (carpeta, sin consola, con ffmpeg y recursos)   3. autoprueba del .exe
#   4. zip del programa   5. instalador C# (csc de Windows)   6. instalador (.exe de 1 MB) + programa (.dat)
# Resultado: <carpeta principal>\3 INSTALADORES\Windows\Instalar Trailer automatico <version>.exe y su .dat
#   El programa va en el .dat de al lado para que el .exe abra AL INSTANTE: con los 560 MB dentro, el antivirus de
#   Windows lo revisaba entero antes de dejarlo arrancar (8 s o mas sin ver nada). Los dos archivos van juntos.
#   La actualizacion publica (datos\publicar) sigue siendo un solo .exe con el zip pegado: se instala sola.
# Uso:  pwsh -File PROGRAMA\compilar\windows\construir.ps1
param([switch]$SoloInstalador)      # -SoloInstalador: reutiliza el programa ya compilado y solo rehace el instalador
$ErrorActionPreference = "Stop"
$win = $PSScriptRoot                        # PROGRAMA\compilar\windows
$compilar = Split-Path $win -Parent
$prog = Split-Path $compilar -Parent
$base = Split-Path $prog -Parent
$icono = Join-Path $compilar "icono"
$ver = (Get-Content "$prog\config\version.txt" -Raw).Trim()
$trabajo = Join-Path $env:TEMP "trailer_automatico_build"
$dist = Join-Path $trabajo "dist"
$salida = Join-Path $base "3 INSTALADORES\Windows"
$t0 = Get-Date
function Paso($m) { Write-Host ("[{0:mm\:ss}] {1}" -f ((Get-Date) - $t0), $m) }

Paso "Version $ver"
New-Item -ItemType Directory -Force $trabajo, $salida | Out-Null

if (-not $SoloInstalador) {
Paso "Icono"
python "$icono\icono.py" "$icono\icono.ico"
python "$prog\herramientas\hacer_portada.py"      # recursos\portada.bmp: lo que se ve al instante al abrir el programa

Paso "PyInstaller (unos minutos)"
$env:TRAILER_PROGRAMA = $prog
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
$env:TRAILER_FFMPEG = if ($ff) { Split-Path $ff.Source } else { "" }
if (Test-Path "$dist\TrailerAutomatico") { Remove-Item "$dist\TrailerAutomatico" -Recurse -Force }
python -m PyInstaller --noconfirm --log-level WARN --distpath $dist --workpath "$trabajo\work" "$win\trailer.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }
$app = Join-Path $dist "TrailerAutomatico"

Paso "Autoprueba del .exe"
$prueba = Join-Path $trabajo "autoprueba.txt"
$p = Start-Process -FilePath "$app\TrailerAutomatico.exe" -ArgumentList "--tarea", "verificar", "`"$prueba`"" -PassThru -Wait
$fin = (Get-Content $prueba -ErrorAction SilentlyContinue | Select-Object -Last 1)
Paso "  $fin"
if (-not $fin -or -not $fin.StartsWith("OK|")) { throw "La autoprueba fallo: $fin" }

Paso "Comprimiendo el programa"
$zip = Join-Path $trabajo "programa.zip"
$zpy = Join-Path $trabajo "zipear.py"
@"
import os, sys, zipfile
app, zipr = sys.argv[1], sys.argv[2]
publico = len(sys.argv) > 3 and sys.argv[3] == 'publico'      # sin musica, SFX ni fuente con licencia (actualizaciones publicas)
guardar = ('.mp3', '.png', '.jpg', '.drp', '.zip', '.pyd', '.dll')
with zipfile.ZipFile(zipr, 'w') as z:
    for raiz, _, fs in os.walk(app):
        for f in fs:
            p = os.path.join(raiz, f)
            rel = os.path.relpath(p, app).replace(os.sep, '/')
            if publico and ('/recursos/audio/' in '/' + rel or f == 'FogtwoNo5.ttf'):
                continue
            z.write(p, rel, zipfile.ZIP_STORED if f.lower().endswith(guardar) else zipfile.ZIP_DEFLATED)
print('%.0f MB' % (os.path.getsize(zipr) / 1e6))
"@ | Set-Content $zpy -Encoding utf8
python $zpy $app $zip
if ($LASTEXITCODE -ne 0) { throw "No se pudo comprimir" }
python $zpy $app (Join-Path $trabajo "programa_publico.zip") publico
if ($LASTEXITCODE -ne 0) { throw "No se pudo comprimir la version publica" }
}
$zip = Join-Path $trabajo "programa.zip"
$zip_pub = Join-Path $trabajo "programa_publico.zip"
if (-not (Test-Path $zip)) { throw "No hay programa compilado: corre sin -SoloInstalador" }

Paso "Instalador (C#)"
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$cs = Join-Path $trabajo "Instalador.cs"
(Get-Content "$win\Instalador.cs" -Raw -Encoding utf8).Replace("__VERSION__", $ver) | Set-Content $cs -Encoding utf8BOM
$base_exe = Join-Path $trabajo "instalador_base.exe"
$b = Join-Path $win "banner"
if (-not (Test-Path "$b\banner.jpg")) { python "$win\banner.py" "$b\banner.jpg" }
& $csc /nologo /target:winexe /codepage:65001 /optimize+ "/out:$base_exe" "/win32icon:$icono\icono.ico" `
    "/win32manifest:$win\app.manifest" /reference:System.IO.Compression.dll /reference:System.Windows.Forms.dll `
    /reference:System.Drawing.dll "/resource:$b\banner.jpg,banner.jpg" "/resource:$icono\icono.png,logo.png" `
    "/resource:$b\marca.png,marca.png" "/resource:$b\astro_runas.png,astro_runas.png" "/resource:$b\astro_engr.png,astro_engr.png" `
    "/resource:$b\astro_fili.png,astro_fili.png" "/resource:$b\astro_nucleo.png,astro_nucleo.png" $cs
if ($LASTEXITCODE -ne 0) { throw "csc fallo" }

function Unir($destino, $zipr) {          # instalador + programa.zip + pie (posicion del zip y la marca TRAILER1)
    $tmp = "$destino.tmp"
    Copy-Item $base_exe $tmp -Force
    $ini = (Get-Item $tmp).Length
    $s = [System.IO.File]::Open($tmp, "Append")
    $z = [System.IO.File]::OpenRead($zipr)
    $z.CopyTo($s); $z.Close()
    $pie = [BitConverter]::GetBytes([long]$ini) + [Text.Encoding]::ASCII.GetBytes("TRAILER1")
    $s.Write($pie, 0, $pie.Length); $s.Close()
    Move-Item $tmp $destino -Force
}
Paso "Instalador (.exe que abre al instante) + programa (.dat)"
$final = Join-Path $salida ("Instalar Trailer automatico {0}.exe" -f $ver)
$final_dat = [IO.Path]::ChangeExtension($final, ".dat")
Copy-Item $base_exe $final -Force
Copy-Item $zip $final_dat -Force
Get-ChildItem $salida -Filter "Instalar Trailer automatico *" |
    Where-Object { $_.FullName -ne $final -and $_.FullName -ne $final_dat } | Remove-Item -Force
Paso ("Listo: {0} ({1:N1} MB) + {2} ({3:N0} MB)" -f $final, ((Get-Item $final).Length / 1MB),
      (Split-Path $final_dat -Leaf), ((Get-Item $final_dat).Length / 1MB))
# la de las actualizaciones publicas (sin musica, SFX ni fuente con licencia): la sube herramientas\publicar_version.ps1
$pub_dir = Join-Path $prog "datos\publicar"
New-Item -ItemType Directory -Force $pub_dir | Out-Null
$publico = Join-Path $pub_dir ("Actualizar_Trailer_automatico_{0}.exe" -f $ver)
if (Test-Path $zip_pub) {
    Unir $publico $zip_pub
    Get-ChildItem $pub_dir -Filter "Actualizar_Trailer_automatico_*.exe" | Where-Object { $_.FullName -ne $publico } | Remove-Item -Force
    Paso ("Actualizacion publica (sin musica): {0} ({1:N0} MB)" -f $publico, ((Get-Item $publico).Length / 1MB))
}
