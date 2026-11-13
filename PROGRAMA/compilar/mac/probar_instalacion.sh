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

# 4. (PROBAR_ACTUALIZACION=1, con una version VIEJA instalada) el servicio de root la actualiza solo a la publicada en
#    trailer-automatico-releases, sin contrasena, y la musica guardada aparte sigue ahi
if [ "${PROBAR_ACTUALIZACION:-0}" = 1 ]; then
    ETQ="com.cinemaproductions.trailerautomatico.actualizar"
    VER_TXT() { cat "$(find /Applications/TrailerAutomatico.app/Contents/Resources /Applications/TrailerAutomatico.app/Contents/Frameworks \
        -maxdepth 1 -name version.txt 2>/dev/null | head -1)" 2>/dev/null | tr -d ' \r\n'; }
    V0="$(VER_TXT)"
    if [ -n "${VIEJA:-}" ]; then          # el servicio NO debe instalar encima mientras la primera instalacion sigue en marcha
        [ "$V0" = "$VIEJA" ] && ok "sigue instalada la $VIEJA: el servicio no se metio durante la instalacion" \
            || falla "la version instalada es $V0 y no $VIEJA: el servicio instalo durante la instalacion"
    fi
    PUBLICADA="$(curl -sL https://github.com/AlejandroPiedrasanta/trailer-automatico-releases/releases/latest/download/version.json \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["estable"]["version"])' 2>/dev/null)"
    echo "instalada $V0 · publicada $PUBLICADA"
    N_AUD=$(ls /Users/Shared/TrailerAutomatico/audio 2>/dev/null | wc -l | tr -d ' ')
    [ "$N_AUD" -ge 15 ] && ok "musica guardada aparte ($N_AUD archivos)" || falla "la musica no se guardo aparte ($N_AUD)"
    sudo launchctl print "system/$ETQ" >/dev/null 2>&1 && ok "servicio de actualizaciones cargado" || falla "el servicio no esta cargado"
    pkill -f "$APP_BIN" 2>/dev/null; sleep 4                  # cerrado: el servicio actualiza solo
    sudo launchctl kickstart -k "system/$ETQ"
    INI=$(date +%s); V="$V0"
    for i in $(seq 1 300); do
        V="$(VER_TXT)"; [ -n "$V" ] && [ "$V" != "$V0" ] && break
        sleep 2
    done
    sleep 5
    T=$(( $(date +%s) - INI ))
    [ "$V" = "$PUBLICADA" ] && ok "el servicio actualizo solo de $V0 a $V (en ${T} s, sin contrasena)" \
        || falla "no se actualizo (sigue en $V, publicada $PUBLICADA)"
    N2=$(ls /Users/Shared/TrailerAutomatico/audio 2>/dev/null | wc -l | tr -d ' ')
    [ "$N2" -ge 15 ] && ok "la musica sigue despues de actualizar ($N2 archivos)" || falla "se perdio la musica ($N2)"
    pgrep -f "$APP_BIN" >/dev/null && echo "nota: el programa quedo abierto" || ok "con el programa cerrado no lo abre (actualizacion silenciosa)"
    [ -d "$MONTAJE" ] || true
    sudo cat "/Library/Application Support/TrailerAutomatico/actualizar/fondo.log" > "$SAL/servicio_fondo.log" 2>/dev/null
    sudo cat "/Library/Application Support/TrailerAutomatico/actualizar/servicio.log" > "$SAL/servicio.log" 2>/dev/null
    foto 3_despues_de_actualizar
fi
# 5. (PROBAR_EXTRA=1) autoprueba, servicio de actualizaciones con la version publicada y desinstalar sin dejar nada
if [ "${PROBAR_EXTRA:-0}" = 1 ]; then
    ETQ="com.cinemaproductions.trailerautomatico.actualizar"
    BIN="/Applications/$APP_BIN"
    EST_A="$SAL/autoprueba.txt"
    TRAILER_SIN_MUSICA=1 "$BIN" --tarea verificar "$EST_A" >/dev/null 2>&1
    FIN="$(grep -v '^PROGRESO' "$EST_A" 2>/dev/null | tail -1)"
    case "$FIN" in OK*) ok "autoprueba: $FIN" ;; *) falla "autoprueba: $FIN" ;; esac
    sudo launchctl print "system/$ETQ" >/dev/null 2>&1 && ok "servicio de actualizaciones cargado" || falla "el servicio no esta cargado"
    pkill -f "$APP_BIN" 2>/dev/null; sleep 3
    sudo launchctl kickstart -k "system/$ETQ"; sleep 25
    sudo cat "/Library/Application Support/TrailerAutomatico/actualizar/fondo.log" > "$SAL/servicio_fondo.log" 2>/dev/null
    tail -1 "$SAL/servicio_fondo.log" | grep -q "al_dia" && ok "el servicio lee la version publicada (al dia)" \
        || falla "servicio: $(tail -1 "$SAL/servicio_fondo.log")"
    REG="$(ls "$HOME/Library/Application Support/TrailerAutomatico/registro/registro.log" 2>/dev/null)"
    [ -n "$REG" ] && cp "$REG" "$SAL/registro.log"
    if [ -n "$REG" ] && grep -qE "Traceback|ERROR " "$REG"; then falla "errores en el registro: $(grep -m1 -E 'Traceback|ERROR ' "$REG")"
    else ok "registro sin errores"; fi
    # lo que hace Desinstalar.command (sin los cuadros de dialogo)
    sudo launchctl bootout "system/$ETQ" >/dev/null 2>&1
    sudo rm -f "/Library/LaunchDaemons/$ETQ.plist"
    sudo rm -rf /Applications/TrailerAutomatico.app "/Library/Application Support/TrailerAutomatico"
    sudo pkgutil --forget com.cinemaproductions.trailerautomatico >/dev/null 2>&1
    QUEDA=""
    [ -d /Applications/TrailerAutomatico.app ] && QUEDA="$QUEDA app"
    sudo launchctl print "system/$ETQ" >/dev/null 2>&1 && QUEDA="$QUEDA servicio"
    pkgutil --pkg-info com.cinemaproductions.trailerautomatico >/dev/null 2>&1 && QUEDA="$QUEDA recibo"
    [ -z "$QUEDA" ] && ok "desinstalado sin dejar nada" || falla "al desinstalar quedo:$QUEDA"
fi
echo
cat "$SAL/resultado.txt"
exit $MAL
