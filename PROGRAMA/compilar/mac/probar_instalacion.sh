#!/bin/bash
# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/probar_instalacion.sh — prueba EN UNA MAC (la usa GitHub Actions, workflow "Probar instalador Mac") que al
# terminar de instalar el programa se abre solo y el Instalador de macOS se cierra solo:
#   1. monta el .dmg y abre el .pkg con el Instalador de macOS (con ventana, como la persona);
#   2. instala ese mismo .pkg (con su postinstall) mientras la ventana del Instalador sigue abierta;
#   3. comprueba: el programa quedo abierto, el Instalador se cerro, el .dmg se expulso y el registro lo anota.
# Deja capturas de pantalla y registros en prueba/ (se suben como Artifact).
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$AQUI/../../.." && pwd)"
SAL="${GITHUB_WORKSPACE:-$BASE}/prueba"
mkdir -p "$SAL"
MAL=0
ok() { echo "OK     $1" | tee -a "$SAL/resultado.txt"; }
falla() { echo "FALLA  $1" | tee -a "$SAL/resultado.txt"; MAL=1; }
foto() { screencapture -x "$SAL/$1.png" 2>/dev/null || true; }
APP_BIN="TrailerAutomatico.app/Contents/MacOS/TrailerAutomatico"
: > "$SAL/resultado.txt"

DMG="$(ls "$BASE/3 INSTALADORES/Mac/"*.dmg 2>/dev/null | head -1)"
[ -f "$DMG" ] || { falla "no hay .dmg en 3 INSTALADORES/Mac"; exit 1; }
echo "dmg: $DMG"
echo "usuario frente a la Mac: $(stat -f%Su /dev/console)"
MONTAJE="$(hdiutil attach "$DMG" -nobrowse -noverify | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1 | sed 's/[[:space:]]*$//')"
PKG="$MONTAJE/Instalar Trailer automatico.pkg"
[ -f "$PKG" ] || { falla "no esta el .pkg en '$MONTAJE'"; ls -la "$MONTAJE"; exit 1; }
ok "dmg montado en $MONTAJE"

# 1. la ventana del Instalador de macOS, como cuando la persona hace doble clic en el .pkg
open -a Installer "$PKG"
for i in $(seq 1 30); do pgrep -x Installer >/dev/null && break; sleep 1; done
sleep 6
foto 1_instalador_abierto
pgrep -x Installer >/dev/null && ok "el Instalador de macOS abrio el paquete" || falla "el Instalador de macOS no abrio"

# 2. se instala ese mismo .pkg (corre su postinstall) con la ventana del Instalador abierta
INI=$(date +%s)
sudo installer -pkg "$PKG" -target / > "$SAL/installer.txt" 2>&1 && ok "el .pkg se instalo" \
    || falla "el .pkg no se instalo: $(tail -3 "$SAL/installer.txt" | tr '\n' ' ')"
[ -d "/Applications/TrailerAutomatico.app" ] && ok "la app esta en Aplicaciones" || falla "no esta /Applications/TrailerAutomatico.app"

# 3. lo que debe pasar solo, en segundo plano, al terminar
ABRIO=0; CERRO=0; EXPULSO=0
for i in $(seq 1 120); do
    pgrep -f "$APP_BIN" >/dev/null && ABRIO=1
    pgrep -x Installer >/dev/null || CERRO=1
    [ -d "$MONTAJE" ] || EXPULSO=1
    [ $ABRIO = 1 ] && [ $CERRO = 1 ] && [ $EXPULSO = 1 ] && break
    sleep 1
done
sleep 6
foto 2_despues_de_instalar
T=$(( $(date +%s) - INI ))
[ $ABRIO = 1 ] && ok "el programa se abrio solo (en ${T} s)" || falla "el programa NO se abrio solo"
[ $CERRO = 1 ] && ok "el Instalador se cerro solo" || falla "el Instalador NO se cerro solo"
[ $EXPULSO = 1 ] && ok "el .dmg se expulso solo" || falla "el .dmg NO se expulso"
LOG="$HOME/Library/Logs/TrailerAutomatico_instalacion.log"
cp "$LOG" "$SAL/registro_instalacion.log" 2>/dev/null
grep -q "abierto el programa y cerrado el Instalador" "$LOG" 2>/dev/null && ok "el registro de instalacion lo anota" \
    || falla "el registro de instalacion no lo anota"
pgrep -fl "$APP_BIN" > "$SAL/procesos.txt" 2>&1
pkgutil --pkg-info com.cinemaproductions.trailerautomatico >> "$SAL/procesos.txt" 2>&1
echo
cat "$SAL/resultado.txt"
exit $MAL
