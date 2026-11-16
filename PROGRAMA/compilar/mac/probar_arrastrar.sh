#!/bin/bash
# ============================================================================
# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/probar_arrastrar.sh — prueba EN UNA MAC el disco de «Arrástralo a Aplicaciones» (desde la 1.5.2, como CineCaptions):
#   0. (PROBAR_VIEJAS=1) una Mac que instalo con el .pkg publicado: el paquete OCULTO del disco nuevo la actualiza (lo instala
#      su servicio de root con `installer`), y despues se desinstala todo para seguir con la Mac limpia;
#   1. el disco: la app, el enlace a Aplicaciones, el paquete oculto y el fondo; captura de la ventana;
#   2. «arrastrar»: se copia la app a /Applications como la persona (SIN sudo: no pide contrasena) y se abre; o, en el disco de
#      «Doble clic para instalar» (desde la 1.5.7), doble clic en el instalador: copia, Dock, primer arranque, abre el programa,
#      se cierra y expulsa el disco; la segunda vez solo abre el programa;
#   3. primer arranque: lo que hacia el instalador lo hace el programa (musica aparte, fuentes, servicio de actualizaciones
#      del usuario cargado, sin servicio de root);
#   4. actualizacion sin contrasena: el servicio del usuario atiende un pedido y `--tarea instalar_dmg` reemplaza la app;
#   5. (PROBAR_ACTUALIZACION=1) con una version vieja, el servicio la actualiza solo a la publicada;
#   6. (PROBAR_EXTRA=1) autoprueba, el servicio lee la version publicada y desinstalar sin dejar nada.
# La llama probar_instalacion.sh cuando el .dmg trae la app. Deja capturas y registros en prueba/ (Artifact).
# ============================================================================
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$AQUI/../../.." && pwd)"
SAL="${GITHUB_WORKSPACE:-$BASE}/prueba"
mkdir -p "$SAL"
MAL=0
ok() { echo "OK     $1" | tee -a "$SAL/resultado.txt"; }
falla() { echo "FALLA  $1" | tee -a "$SAL/resultado.txt"; MAL=1; }
nota() { echo "NOTA   $1" | tee -a "$SAL/resultado.txt"; }
foto() { screencapture -x "$SAL/$1.png" 2>/dev/null || true; }
APP="/Applications/TrailerAutomatico.app"
BIN="$APP/Contents/MacOS/TrailerAutomatico"
ETQ="com.cinemaproductions.trailerautomatico.actualizar"
AGENTE="$HOME/Library/LaunchAgents/$ETQ.plist"
DATOS="$HOME/Library/Application Support/TrailerAutomatico"
OCULTO=".Actualizar Trailer automatico.pkg"
INSTALADOR="Instalar Trailer automatico.app"
# la app en el disco: en la raiz (arrastrar) o dentro del instalador (doble clic para instalar, desde la 1.5.7)
app_disco() { if [ -d "$1/TrailerAutomatico.app" ]; then echo "$1/TrailerAutomatico.app"; else echo "$1/$INSTALADOR/Contents/Resources/TrailerAutomatico.app"; fi; }
# si el instalador se cayo: el informe de macOS (DiagnosticReports/instalar-*.ips) con el motivo y las primeras funciones
informe_fallo() {
    for f in "$HOME"/Library/Logs/DiagnosticReports/instalar*.ips; do
        [ -f "$f" ] && [ "$(stat -f%m "$f")" -ge "$1" ] || continue
        cp "$f" "$SAL/"
        falla "el instalador se cayo: $(python3 - "$f" <<'PY'
import json, sys
crudo = open(sys.argv[1], encoding="utf-8", errors="replace").read().split("\n", 1)
b = json.loads(crudo[1]) if len(crudo) > 1 else {}
e = b.get("exception", {})
asi = " ".join(" ".join(v) if isinstance(v, list) else str(v) for v in b.get("asi", {}).values())[:300]
imgs = b.get("usedImages", [])
hilos = [t for t in b.get("threads", []) if t.get("triggered")]
fr = []
for x in (hilos[0].get("frames", []) if hilos else [])[:10]:
    im = imgs[x["imageIndex"]].get("name", "?") if "imageIndex" in x and x["imageIndex"] < len(imgs) else "?"
    fr.append("%s:%s" % (im, x.get("symbol", "?")))
print(e.get("type"), e.get("signal"), "|", asi, "|", " < ".join(fr))
PY
)"
    done
}
VER_TXT() { cat "$(find "$1" -name version.txt 2>/dev/null | head -1)" 2>/dev/null | tr -d ' \r\n'; }
montar() { hdiutil attach "$1" -noverify ${2:-} | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1 | sed 's/[[:space:]]*$//'; }
PUBLICADA_JSON="https://github.com/AlejandroPiedrasanta/trailer-automatico-releases/releases/latest/download/version.json"

DMG="$(ls "$BASE/3 INSTALADORES/Mac/"*.dmg 2>/dev/null | head -1)"
[ -f "$DMG" ] || { falla "no hay .dmg en 3 INSTALADORES/Mac"; exit 1; }
echo "dmg: $DMG"
COMPLETO=1; case "$(basename "$DMG")" in Actualizar_*) COMPLETO=0 ;; esac     # el publico no trae musica

# ---- 0. una Mac que instalo con el .pkg publicado se actualiza con el paquete oculto del disco nuevo
#      PROBAR_VIEJAS=1: la version publicada ahora mismo.  PROBAR_VIEJAS=1.5.1: ESA version (su .dmg sigue en su release); si es
#      mas vieja que la publicada, se deja que su servicio de root se actualice SOLO (la prueba de verdad de las Mac de antes).
if [ "${PROBAR_VIEJAS:-0}" != 0 ]; then
    CLAVE="mac_arm64"; ARQ_N="AppleSilicon"; [ "$(uname -m)" = "x86_64" ] && { CLAVE="mac_x86_64"; ARQ_N="Intel"; }
    PUBLICADA="$(curl -sL "$PUBLICADA_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["estable"]["version"])' 2>/dev/null)"
    if [ "$PROBAR_VIEJAS" = 1 ]; then
        URL="$(curl -sL "$PUBLICADA_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['estable']['archivos']['$CLAVE']['url'])" 2>/dev/null)"
    else
        URL="https://github.com/AlejandroPiedrasanta/trailer-automatico-releases/releases/download/v$PROBAR_VIEJAS/Actualizar_Trailer_automatico_Mac_${ARQ_N}_$PROBAR_VIEJAS.dmg"
    fi
    VIEJO="$SAL/publicado.dmg"
    curl -sL "$URL" -o "$VIEJO"
    M0="$(montar "$VIEJO" -nobrowse)"
    PKG0="$(ls "$M0"/*.pkg 2>/dev/null | head -1)"
    if [ -n "$PKG0" ]; then
        touch /Users/Shared/.trailer_prueba 2>/dev/null
        sudo mkdir -p /Users/Shared/TrailerAutomatico && sudo touch /Users/Shared/TrailerAutomatico/.sin_abrir
        sudo installer -pkg "$PKG0" -target / > "$SAL/viejo_installer.txt" 2>&1
        hdiutil detach "$M0" -quiet 2>/dev/null
        V0="$(VER_TXT "$APP")"
        [ -n "$V0" ] && ok "Mac con la version publicada $V0 instalada con su .pkg (servicio de root)" || falla "no se instalo la publicada"
        sudo launchctl print "system/$ETQ" >/dev/null 2>&1 && ok "tiene el servicio de root de antes" || nota "sin servicio de root"
        if [ -n "$V0" ] && [ -n "$PUBLICADA" ] && [ "$V0" != "$PUBLICADA" ]; then
            # la prueba de verdad: su servicio de root (el codigo VIEJO) baja la publicada, que ya es un disco de arrastrar,
            # y la instala con el paquete oculto, sin contrasena
            pkill -f "$BIN" 2>/dev/null; sleep 4
            sudo rm -f "/Library/Application Support/TrailerAutomatico/actualizar/fondo.json"
            sudo launchctl kickstart -k "system/$ETQ"
            INI=$(date +%s); V="$V0"
            for i in $(seq 1 300); do V="$(VER_TXT "$APP")"; [ -n "$V" ] && [ "$V" != "$V0" ] && [ ! -e "$APP.nuevo" ] && break; sleep 2; done
            sleep 8
            sudo cat "/Library/Application Support/TrailerAutomatico/actualizar/fondo.log" > "$SAL/viejas_fondo.log" 2>/dev/null
            [ "$V" = "$PUBLICADA" ] && ok "la Mac de antes se actualizo SOLA de $V0 a $V con su servicio de root (en $(( $(date +%s) - INI )) s, sin contrasena)" \
                || falla "la Mac de antes no se actualizo (sigue en $V, publicada $PUBLICADA): $(tail -1 "$SAL/viejas_fondo.log" 2>/dev/null | cut -c1-150)"
            [ "$(stat -f%Su "$APP")" = "root" ] && ok "la app sigue siendo del sistema (root)" || falla "la app quedo de $(stat -f%Su "$APP")"
            sudo launchctl print "system/$ETQ" >/dev/null 2>&1 && ok "su servicio de root sigue cargado" || falla "se perdio el servicio de root"
            [ -f "$AGENTE" ] && falla "se creo ademas un servicio del usuario (no debia)" || ok "no se creo un segundo servicio"
        fi
        M1="$(montar "$DMG" -nobrowse)"
        # lo mismo que hace su servicio de root: el primer *.pkg del disco, con installer
        sudo touch /Users/Shared/TrailerAutomatico/.sin_abrir
        sudo installer -pkg "$M1/$OCULTO" -target / > "$SAL/oculto_installer.txt" 2>&1 \
            && ok "el paquete oculto se instalo con installer (como lo hace el servicio de root)" \
            || falla "el paquete oculto fallo: $(tail -3 "$SAL/oculto_installer.txt" | tr '\n' ' ')"
        V1="$(VER_TXT "$APP")"; VN="$(VER_TXT "$(app_disco "$M1")")"
        [ "$V1" = "$VN" ] && ok "la Mac ya instalada quedo en la version del disco nuevo ($V0 -> $V1)" || falla "sigue en $V1 (el disco trae $VN)"
        [ "$(stat -f%Su "$APP")" = "root" ] && ok "la app sigue siendo del sistema (root): su servicio la seguira actualizando" \
            || falla "la app quedo de $(stat -f%Su "$APP")"
        "$BIN" --tarea verificar "$SAL/viejas_autoprueba.txt" >/dev/null 2>&1
        case "$(tail -1 "$SAL/viejas_autoprueba.txt" 2>/dev/null)" in OK*) ok "la app actualizada arranca (autoprueba completa)" ;; *) falla "la app actualizada no pasa la autoprueba" ;; esac
        hdiutil detach "$M1" -quiet 2>/dev/null
        # se deja la Mac limpia para la prueba de arrastrar
        pkill -f "$BIN" 2>/dev/null
        sudo launchctl bootout "system/$ETQ" >/dev/null 2>&1
        sudo rm -f "/Library/LaunchDaemons/$ETQ.plist"
        sudo rm -rf "$APP" "/Library/Application Support/TrailerAutomatico" /Users/Shared/TrailerAutomatico "$DATOS"
        sudo pkgutil --forget com.cinemaproductions.trailerautomatico >/dev/null 2>&1
    else
        hdiutil detach "$M0" -quiet 2>/dev/null
        nota "la version publicada ya es de arrastrar: no hay Mac «de antes» que probar"
    fi
fi

# ---- 1. el disco
MONTAJE="$(montar "$DMG")"
[ -d "$(app_disco "$MONTAJE")" ] || { falla "el disco no trae la app"; ls -la "$MONTAJE"; exit 1; }
ok "disco montado en $MONTAJE con la app"
[ -f "$MONTAJE/$OCULTO" ] && ok "trae el paquete oculto para las Mac ya instaladas" || falla "falta el paquete oculto"
VISIBLES="$(ls "$MONTAJE" | tr '\n' '|')"
if [ -d "$MONTAJE/$INSTALADOR" ]; then
    MODO=instalador
    [ "$VISIBLES" = "$INSTALADOR|" ] && ok "a la vista solo esta «Instalar Trailer automatico» (doble clic para instalar)" || falla "a la vista hay: $VISIBLES"
    FIRMA="$(codesign -v --deep "$MONTAJE/$INSTALADOR" 2>&1)" && ok "el instalador esta firmado" \
        || falla "la firma del instalador no se verifica: $(echo "$FIRMA" | tail -1 | cut -c1-160)"
else
    MODO=arrastrar
    [ "$(readlink "$MONTAJE/Aplicaciones" 2>/dev/null)" = "/Applications" ] && ok "trae el enlace a Aplicaciones" || falla "falta el enlace a Aplicaciones"
    [ "$VISIBLES" = "Aplicaciones|TrailerAutomatico.app|" ] && ok "a la vista solo estan el programa y Aplicaciones" || falla "a la vista hay: $VISIBLES"
fi
[ -n "$(find "$MONTAJE" -maxdepth 2 -name '*.tiff' 2>/dev/null | head -1)" ] && ok "trae el fondo de la ventana" || nota "no veo el fondo (disco sencillo, sin fondo)"
open "$MONTAJE"; sleep 6
foto "1_disco_$MODO"
VN="$(VER_TXT "$(app_disco "$MONTAJE")")"

if [ "$MODO" = instalador ]; then
    # ---- 2. doble clic en «Instalar Trailer automatico», como la persona: la ventana copia, fija en el Dock, prepara y abre
    INI=$(date +%s)
    open "$MONTAJE/$INSTALADOR"
    for s in 2 5 9 15; do                                  # capturas de la ventana mientras instala
        while [ $(( $(date +%s) - INI )) -lt $s ]; do sleep 0.5; done
        foto "2_instalador_${s}s"
    done
    for i in $(seq 1 240); do pgrep -f "$INSTALADOR/Contents/MacOS/instalar" >/dev/null || break; sleep 1; done
    SEG=$(( $(date +%s) - INI ))
    sleep 3
    foto 3_instalador_termino
    cp "$DATOS/registro/instalador_mac.log" "$SAL/instalador_mac.log" 2>/dev/null
    informe_fallo "$INI"
    pgrep -f "$INSTALADOR/Contents/MacOS/instalar" >/dev/null && falla "el instalador sigue abierto despues de 4 minutos" \
        || ok "el instalador termino y se cerro solo (en $SEG s, sin contrasena)"
    grep -q "listo:" "$SAL/instalador_mac.log" 2>/dev/null && ok "registro del instalador: $(grep -m1 'tarea instalar' "$SAL/instalador_mac.log" | cut -c22-160)" \
        || falla "el instalador no termino bien: $(grep -m1 -E 'ERROR|AVISO' "$SAL/instalador_mac.log" 2>/dev/null | cut -c22-180)"
    grep -q "AVISO" "$SAL/instalador_mac.log" 2>/dev/null && nota "avisos: $(grep 'AVISO' "$SAL/instalador_mac.log" | cut -c22-160 | tr '\n' ' ')"
    [ -x "$BIN" ] && ok "la app quedo en Aplicaciones ($(VER_TXT "$APP"))" || falla "no esta $APP"
    [ "$(stat -f%Su "$APP")" = "$(id -un)" ] && ok "la app es del usuario (se podra actualizar sin contrasena)" || falla "la app es de $(stat -f%Su "$APP")"
    xattr -p com.apple.quarantine "$APP" >/dev/null 2>&1 && falla "la app quedo en cuarentena" || ok "la app no quedo en cuarentena"
    defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "TrailerAutomatico.app" && ok "fijada en el Dock" || falla "no quedo en el Dock"
    for i in $(seq 1 30); do pgrep -f "$BIN" >/dev/null && break; sleep 1; done
    pgrep -f "$BIN" >/dev/null && ok "el instalador abrio el programa" || falla "el programa no se abrio al terminar"
    for i in $(seq 1 15); do [ -d "$MONTAJE" ] || break; sleep 1; done
    [ -d "$MONTAJE" ] && falla "el disco no se expulso solo" || ok "el disco se expulso solo"
    [ -d "$MONTAJE" ] && { hdiutil detach "$MONTAJE" -quiet 2>/dev/null || hdiutil detach "$MONTAJE" -force -quiet 2>/dev/null; }
    # segunda vez: con la misma version ya instalada, el instalador solo abre el programa (sin ventana)
    pkill -f "$BIN" 2>/dev/null; sleep 3
    M2="$(montar "$DMG")"
    INI=$(date +%s)
    open "$M2/$INSTALADOR"
    for i in $(seq 1 30); do pgrep -f "$BIN" >/dev/null && break; sleep 1; done
    sleep 2
    foto 4_segunda_vez
    pgrep -f "$BIN" >/dev/null && ok "segunda vez: abre el programa ya instalado (en $(( $(date +%s) - INI )) s)" || falla "segunda vez: no abrio el programa"
    pgrep -f "$INSTALADOR/Contents/MacOS/instalar" >/dev/null && falla "segunda vez: el instalador quedo abierto" || ok "segunda vez: sin ventana de instalar"
    hdiutil detach "$M2" -quiet 2>/dev/null || hdiutil detach "$M2" -force -quiet 2>/dev/null
else
# ---- 2. «arrastrar» a Aplicaciones como la persona: sin sudo
INI=$(date +%s)
if ditto "$MONTAJE/TrailerAutomatico.app" "$APP" 2> "$SAL/arrastrar.txt"; then
    ok "la app se copio a Aplicaciones sin contrasena (en $(( $(date +%s) - INI )) s)"
else
    falla "no se pudo copiar a Aplicaciones sin contrasena: $(tail -1 "$SAL/arrastrar.txt")"
fi
[ "$(stat -f%Su "$APP")" = "$(id -un)" ] && ok "la app es del usuario (se podra actualizar sin contrasena)" || falla "la app es de $(stat -f%Su "$APP")"
osascript -e 'tell application "Finder" to close every window' >/dev/null 2>&1
hdiutil detach "$MONTAJE" -quiet 2>/dev/null || hdiutil detach "$MONTAJE" -force -quiet 2>/dev/null
open "$APP"
for i in $(seq 1 60); do pgrep -f "$BIN" >/dev/null && break; sleep 1; done
pgrep -f "$BIN" >/dev/null && ok "el programa abre desde Aplicaciones" || falla "el programa no abrio"
fi

# ---- 3. primer arranque: lo que hacia el instalador lo hace el programa
for i in $(seq 1 120); do [ "$(cat "$DATOS/instalado.txt" 2>/dev/null)" = "$VN" ] && break; sleep 2; done
sleep 4
foto 2_programa_abierto
[ "$(cat "$DATOS/instalado.txt" 2>/dev/null)" = "$VN" ] && ok "primer arranque hecho para la $VN: $(tail -1 "$DATOS/instalacion.txt" 2>/dev/null | cut -c1-150)" \
    || falla "el primer arranque no termino ($(tail -1 "$DATOS/instalacion.txt" 2>/dev/null | cut -c1-120))"
N_AUD=$(ls /Users/Shared/TrailerAutomatico/audio 2>/dev/null | wc -l | tr -d ' ')
if [ $COMPLETO = 1 ]; then
    [ "$N_AUD" -ge 15 ] && ok "musica y efectos guardados aparte ($N_AUD archivos)" || falla "la musica no se guardo aparte ($N_AUD)"
else
    nota "instalador publico (sin musica): $N_AUD archivos de musica"
fi
N_F=$(ls "$HOME/Library/Fonts" 2>/dev/null | grep -ci -E '\.(ttf|otf)$')
[ "$N_F" -ge 5 ] && ok "fuentes de los titulos instaladas ($N_F)" || falla "faltan fuentes en Library/Fonts ($N_F)"
[ -f "$AGENTE" ] && ok "servicio de actualizaciones del usuario creado (LaunchAgent)" || falla "no se creo el servicio del usuario"
launchctl print "gui/$(id -u)/$ETQ" >/dev/null 2>&1 && ok "servicio del usuario cargado" || falla "el servicio del usuario no esta cargado"
grep -q "$BIN" "$AGENTE" 2>/dev/null && ok "el servicio apunta a la app de Aplicaciones" || falla "el servicio apunta a otro lado"
[ -f "/Library/LaunchDaemons/$ETQ.plist" ] && falla "se creo un servicio de root (no debia)" || ok "sin servicio de root: nada pidio contrasena"
REG="$DATOS/registro/registro.log"
cp "$REG" "$SAL/registro.log" 2>/dev/null
if grep -qE "Traceback|ERROR " "$REG" 2>/dev/null; then falla "errores en el registro: $(grep -m1 -E 'Traceback|ERROR ' "$REG" | cut -c1-160)"
else ok "registro sin errores"; fi

# ---- 4. actualizacion sin contrasena
pkill -f "$BIN" 2>/dev/null; sleep 4
mkdir -p "$DATOS/actualizacion/pedidos"
echo '{"dmg": "", "reabrir": false, "pid": 0}' > "$DATOS/actualizacion/pedidos/pedido_prueba.json"
for i in $(seq 1 45); do [ -z "$(ls -A "$DATOS/actualizacion/pedidos" 2>/dev/null)" ] && break; sleep 2; done
cp "$DATOS/actualizacion/fondo.log" "$SAL/fondo_usuario.log" 2>/dev/null
[ -z "$(ls -A "$DATOS/actualizacion/pedidos" 2>/dev/null)" ] && ok "el servicio del usuario atiende los pedidos del programa: $(tail -1 "$SAL/fondo_usuario.log" 2>/dev/null | cut -c21-110)" \
    || falla "el servicio no atendio el pedido"
I0="$(stat -f%i "$APP")"
INI=$(date +%s)
"$BIN" --tarea instalar_dmg "$DMG" > "$SAL/instalar_dmg.txt" 2>&1
COD=$?
I1="$(stat -f%i "$APP" 2>/dev/null)"
if [ $COD = 0 ] && [ -n "$I1" ] && [ "$I1" != "$I0" ] && [ "$(VER_TXT "$APP")" = "$VN" ]; then
    ok "la app se reemplazo con la del disco sin contrasena (en $(( $(date +%s) - INI )) s)"
else
    falla "no se reemplazo la app (codigo $COD): $(tail -2 "$SAL/instalar_dmg.txt" | tr '\n' ' ' | cut -c1-200)"
fi
[ ! -e "$APP.nuevo" ] && [ ! -e "$APP.viejo" ] && ok "no quedaron copias a medias" || falla "quedaron restos (.nuevo / .viejo)"
"$BIN" --tarea verificar "$SAL/autoprueba_reemplazada.txt" >/dev/null 2>&1
case "$(tail -1 "$SAL/autoprueba_reemplazada.txt" 2>/dev/null)" in OK*) ok "la app reemplazada arranca (autoprueba completa)" ;; *) falla "la app reemplazada no pasa la autoprueba" ;; esac
[ $COMPLETO = 1 ] && { N2=$(ls /Users/Shared/TrailerAutomatico/audio 2>/dev/null | wc -l | tr -d ' '); [ "$N2" -ge 15 ] && ok "la musica sigue despues de reemplazar ($N2)" || falla "se perdio la musica ($N2)"; }

# ---- 5. con una version vieja, el servicio la actualiza solo a la publicada
if [ "${PROBAR_ACTUALIZACION:-0}" = 1 ]; then
    V0="$(VER_TXT "$APP")"
    PUBLICADA="$(curl -sL "$PUBLICADA_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["estable"]["version"])' 2>/dev/null)"
    echo "instalada $V0 · publicada $PUBLICADA"
    launchctl kickstart -k "gui/$(id -u)/$ETQ"
    INI=$(date +%s); V="$V0"
    for i in $(seq 1 240); do V="$(VER_TXT "$APP")"; [ -n "$V" ] && [ "$V" != "$V0" ] && break; sleep 2; done
    sleep 5
    cp "$DATOS/actualizacion/fondo.log" "$SAL/fondo_usuario.log" 2>/dev/null
    if [ "$V" = "$PUBLICADA" ]; then
        ok "el servicio del usuario actualizo solo de $V0 a $V (en $(( $(date +%s) - INI )) s, sin contrasena)"
    elif grep -q "instalador .pkg" "$SAL/fondo_usuario.log" 2>/dev/null; then
        nota "la publicada ($PUBLICADA) todavia es un disco con .pkg: el servicio del usuario no puede instalarla (se sabra al publicar la primera de arrastrar)"
    else
        falla "no se actualizo (sigue en $V, publicada $PUBLICADA): $(tail -1 "$SAL/fondo_usuario.log" 2>/dev/null | cut -c1-140)"
    fi
    foto 3_despues_de_actualizar
fi

# ---- 6. autoprueba, el servicio lee la version publicada y desinstalar sin dejar nada
if [ "${PROBAR_EXTRA:-0}" = 1 ]; then
    TRAILER_SIN_MUSICA=1 "$BIN" --tarea verificar "$SAL/autoprueba.txt" >/dev/null 2>&1
    FIN="$(grep -v '^PROGRESO' "$SAL/autoprueba.txt" 2>/dev/null | tail -1)"
    case "$FIN" in OK*) ok "autoprueba: $FIN" ;; *) falla "autoprueba: $FIN" ;; esac
    pkill -f "$BIN" 2>/dev/null; sleep 3
    launchctl kickstart -k "gui/$(id -u)/$ETQ"; sleep 25
    cp "$DATOS/actualizacion/fondo.log" "$SAL/fondo_usuario.log" 2>/dev/null
    tail -1 "$SAL/fondo_usuario.log" 2>/dev/null | grep -q "al_dia" && ok "el servicio lee la version publicada (al dia)" \
        || nota "servicio: $(tail -1 "$SAL/fondo_usuario.log" 2>/dev/null | cut -c1-140)"
    # lo que hace Desinstalar.command con una app arrastrada (sin los cuadros de dialogo): sin sudo
    launchctl bootout "gui/$(id -u)/$ETQ" >/dev/null 2>&1
    rm -f "$AGENTE"
    rm -rf "$APP"
    QUEDA=""
    [ -d "$APP" ] && QUEDA="$QUEDA app"
    launchctl print "gui/$(id -u)/$ETQ" >/dev/null 2>&1 && QUEDA="$QUEDA servicio"
    [ -z "$QUEDA" ] && ok "desinstalado sin contrasena y sin dejar nada" || falla "al desinstalar quedo:$QUEDA"
fi
echo
cat "$SAL/resultado.txt"
exit $MAL
