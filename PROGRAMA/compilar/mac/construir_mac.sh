#!/bin/bash
# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/construir_mac.sh — arma "Instalar Tráiler automático" (.dmg con el .pkg) EN UNA MAC, como CineCaptions.
# ============================================================================
#   bash PROGRAMA/compilar/mac/construir_mac.sh                  todo de principio a fin
#   bash PROGRAMA/compilar/mac/construir_mac.sh --solo-instalador   reusa la app ya compilada
# Hace: venv -> ffmpeg (estatico, si se puede) -> PyInstaller (TrailerAutomatico.app) -> autoprueba -> paquete oculto -> .dmg
#   de «Arrastralo a Aplicaciones» (la app y el enlace a Aplicaciones; sin instalador que pida contrasena).
# Compila para la arquitectura de ESA Mac (Apple Silicon o Intel). Deja el .dmg en "3 INSTALADORES/Mac".
# Variables opcionales: TRAILER_PYTHON (interprete), TRAILER_SIN_PANTALLA=1 (autoprueba sin pantalla, para GitHub Actions),
#   FIRMA_APP / FIRMA_PKG (Developer ID de Apple; sin ellas: firma ad-hoc y la primera vez se abre con clic derecho > Abrir).
# ============================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
COMPILAR="$(dirname "$AQUI")"
PROG="$(dirname "$COMPILAR")"
BASE="$(dirname "$PROG")"
OBRA="${TRAILER_OBRA:-${GITHUB_WORKSPACE:-$HOME}/trailer_automatico_mac}"
DIST="$OBRA/dist"
APP="$DIST/TrailerAutomatico.app"
VENV="$OBRA/venv"
VPY="$VENV/bin/python"
SOLO_INSTALADOR=0
[ "${1:-}" = "--solo-instalador" ] && SOLO_INSTALADOR=1

paso() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
falla() { printf '\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || falla "Este script solo corre en una Mac (PyInstaller no compila para Mac desde Windows). Ver compilar/mac/0_LEEME.txt."
ARQ="$(uname -m)"
case "$ARQ" in arm64) NOMBRE_ARQ=AppleSilicon; FF_ARQ=arm64 ;; x86_64) NOMBRE_ARQ=Intel; FF_ARQ=amd64 ;; *) falla "Arquitectura no soportada: $ARQ" ;; esac
VERSION="$(tr -d ' \r\n' < "$PROG/config/version.txt")"
echo "Tráiler automático $VERSION ($NOMBRE_ARQ)"
mkdir -p "$OBRA"
export PYTHONIOENCODING=utf-8 PIP_DISABLE_PIP_VERSION_CHECK=1

if [ "$SOLO_INSTALADOR" = 0 ]; then
paso "Entorno de compilacion"
if [ ! -x "$VPY" ]; then
    PY="${TRAILER_PYTHON:-$(command -v python3.13 || command -v python3 || true)}"
    [ -n "$PY" ] || falla "Falta Python 3: instalalo desde python.org y vuelve a correr esto."
    "$PY" -m venv "$VENV"
fi
"$VPY" -m pip install --progress-bar off -q PySide6 numpy Pillow pyinstaller 'dmgbuild==1.6.7' cryptography

# la musica, los SFX y las fuentes con licencia vienen CIFRADOS en el repositorio publico (recursos_protegidos/): se descifran
# con la clave TRAILER_CLAVE (secreto de GitHub, o PROGRAMA/datos/clave_recursos.txt en tu PC)
#   TRAILER_SIN_MUSICA=1: version PUBLICA para las actualizaciones (sin musica, SFX ni fuente con licencia; usa la ya instalada)
if [ "${TRAILER_SIN_MUSICA:-0}" = 1 ]; then
    paso "Version publica (actualizaciones): sin musica, SFX ni fuente con licencia"
    rm -rf "$PROG/recursos/audio"; rm -f "$PROG/recursos/fuentes/FogtwoNo5.ttf"
    export TRAILER_SIN_MUSICA
elif [ ! -d "$PROG/recursos/audio" ] || [ -z "$(ls -A "$PROG/recursos/audio" 2>/dev/null)" ]; then
    paso "Musica y SFX (cifrados)"
    "$VPY" "$COMPILAR/protegidos.py" descifrar || falla "No pude descifrar la musica y los SFX: falta el secreto TRAILER_CLAVE"
fi

paso "Icono"
ICONSET="$OBRA/icono.iconset"; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
"$VPY" - "$COMPILAR" "$OBRA/icono_1024.png" <<'PY'
import sys, importlib.util
from PySide6.QtGui import QGuiApplication
app = QGuiApplication(sys.argv[:1])
spec = importlib.util.spec_from_file_location("icono", sys.argv[1] + "/icono/icono.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.dibujar(1024).save(sys.argv[2])
PY
for s in 16 32 128 256 512; do
    sips -z $s $s "$OBRA/icono_1024.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$OBRA/icono_1024.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$OBRA/TrailerAutomatico.icns"

paso "ffmpeg estatico (para que la app lo traiga dentro)"
FF="$OBRA/ffmpeg"; mkdir -p "$FF"
if [ ! -x "$FF/ffmpeg" ] || [ ! -x "$FF/ffprobe" ]; then
    for B in ffmpeg ffprobe; do
        curl -fsSL "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$FF_ARQ/release/$B.zip" -o "$OBRA/$B.zip" \
          && unzip -o -q "$OBRA/$B.zip" -d "$FF" && chmod +x "$FF/$B" || echo "    AVISO: no pude bajar $B estatico: la app usara el de Homebrew"
    done
fi
"$FF/ffmpeg" -version >/dev/null 2>&1 && FF_OK="$FF" || FF_OK=""

paso "Compilando TrailerAutomatico.app (PyInstaller, unos minutos)"
rm -rf "$DIST"
(cd "$AQUI" && TRAILER_PROGRAMA="$PROG" TRAILER_FFMPEG="$FF_OK" TRAILER_ICNS="$OBRA/TrailerAutomatico.icns" \
    TRAILER_VERSION="$VERSION" "$VPY" -m PyInstaller --noconfirm --log-level WARN --distpath "$DIST" --workpath "$OBRA/work" trailer_mac.spec)
[ -d "$APP" ] || falla "PyInstaller no dejo TrailerAutomatico.app"
if [ -n "${FIRMA_APP:-}" ]; then
    codesign --force --deep --options runtime --timestamp --sign "$FIRMA_APP" "$APP"
else
    codesign --force --deep --sign - "$APP"
fi

paso "Autoprueba del programa compilado"
ESTADO="$OBRA/autoprueba.txt"; : > "$ESTADO"
if [ "${TRAILER_SIN_PANTALLA:-0}" = 1 ]; then export QT_QPA_PLATFORM=offscreen; fi
set +e
"$APP/Contents/MacOS/TrailerAutomatico" --tarea verificar "$ESTADO"
CODIGO_SALIDA=$?
set -e
grep -v '^PROGRESO' "$ESTADO" | sed 's/^/    /'
[ "$CODIGO_SALIDA" = 0 ] || falla "La autoprueba fallo: no se arma el instalador"
unset QT_QPA_PLATFORM
fi

[ -d "$APP" ] || falla "No hay app compilada: corre el script sin --solo-instalador"

# Desde la 1.5.2 el disco es «Arrastralo a Aplicaciones» (como CineCaptions 5.91): sin un .pkg que abrir, porque instalar en
# /Applications con un .pkg SIEMPRE pide la contrasena de la Mac. Pero las Mac que instalaron con el .pkg (hasta la 1.5.1)
# tienen un servicio de root que busca un *.pkg en el disco y lo instala: este paquete SIN la app (solo su postinstall) la
# copia del mismo disco y hace lo de siempre. Va OCULTO (nombre con punto).
paso "Paquete oculto para las Mac que instalaron con el .pkg"
chmod +x "$AQUI/pkg/scripts/postinstall"
SELLO_PKG=(); [ -n "${FIRMA_PKG:-}" ] && SELLO_PKG=(--sign "$FIRMA_PKG")
PKG="$OBRA/actualizar_instaladas.pkg"; rm -f "$PKG"
pkgbuild --nopayload --scripts "$AQUI/pkg/scripts" --identifier com.cinemaproductions.trailerautomatico --version "$VERSION"     ${SELLO_PKG[@]+"${SELLO_PKG[@]}"} "$PKG" >/dev/null || falla "pkgbuild no pudo armar el paquete de las Mac ya instaladas"

paso "Imagen de disco .dmg (arrastrar a Aplicaciones)"
STAGE="$OBRA/dmg"; rm -rf "$STAGE"; mkdir -p "$STAGE"
# nombres y volumen SIN tildes: con «Tráiler automático» el punto de montaje queda en NFD, mac_alias lo compara en NFC, sale de
# la imagen («..») y toma IDs de APFS de 64 bits -> struct.error en backgroundImageAlias (fallo del 2026-11-13 en GitHub)
ditto "$APP" "$STAGE/TrailerAutomatico.app"
cp "$PKG" "$STAGE/.Actualizar Trailer automatico.pkg"
FONDO="$OBRA/fondo_dmg.tiff"
tiffutil -cathidpicheck "$AQUI/dmg/fondo.png" "$AQUI/dmg/fondo@2x.png" -out "$FONDO" >/dev/null || falla "No pude preparar el fondo del .dmg"
SALIDA="${TRAILER_SALIDA:-$BASE/3 INSTALADORES/Mac}"; mkdir -p "$SALIDA"
PREFIJO="Instalar"; [ "${TRAILER_SIN_MUSICA:-0}" = 1 ] && PREFIJO="Actualizar"     # el publico (sin musica) se llama Actualizar_
rm -f "$SALIDA"/${PREFIJO}_Trailer_automatico_Mac_${NOMBRE_ARQ}_*.dmg
DMG="$SALIDA/${PREFIJO}_Trailer_automatico_Mac_${NOMBRE_ARQ}_$VERSION.dmg"
for intento in 1 2 3 4 5; do                      # hdiutil a veces responde «Resource busy»: hasta 5 intentos
    "$VPY" -m dmgbuild -s "$AQUI/dmg/ajustes_dmg.py" -D stage="$STAGE" -D fondo="$FONDO" -D icono="$OBRA/TrailerAutomatico.icns" \
        "Trailer automatico $VERSION" "$DMG" >/dev/null && break
    rm -f "$DMG"
    if [ "$intento" = 5 ]; then                    # ultimo recurso: .dmg sencillo (sin fondo) para no quedarse sin instalador
        echo "    AVISO: dmgbuild fallo 5 veces: armo un .dmg sencillo sin fondo"
        ln -s /Applications "$STAGE/Aplicaciones"
        hdiutil create -volname "Trailer automatico $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG" >/dev/null \
            || falla "hdiutil no pudo crear la imagen de disco"
        break
    fi
    echo "    hdiutil ocupado (intento $intento de 5): reintento en 15 s"; sleep 15
done
[ -n "${FIRMA_APP:-}" ] && codesign --sign "$FIRMA_APP" "$DMG"
paso "LISTO  $DMG  ($(du -h "$DMG" | cut -f1))"
