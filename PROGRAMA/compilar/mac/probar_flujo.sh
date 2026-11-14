#!/bin/bash
# ============================================================================
# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/probar_flujo.sh — con el programa YA INSTALADO en la Mac desde el .dmg (lo deja probar_instalacion.sh),
# comprueba lo que la persona espera al instalar:
#   1. el instalador lo trae todo: plantillas de DaVinci, musica y SFX, fuentes, looks y filtros de color, ffmpeg;
#   2. la autoprueba del programa instalado;
#   3. el flujo completo con el programa instalado: se suelta una carpeta con fotos, videos y dron (y basura), el
#      programa la ordena en FOTOS / VIDEOS / DRON, la organiza por momentos y calcula el plan de las 4 plantillas.
# En las Mac de GitHub no hay DaVinci Resolve: el armado dentro de DaVinci NO se prueba aqui (llega hasta el plan y el
# aviso claro de que falta DaVinci). Deja resultado.txt y capturas en prueba/flujo (se suben como Artifact).
# ============================================================================
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
PROG="$(dirname "$(dirname "$AQUI")")"
BASE="$(dirname "$PROG")"
APP="/Applications/TrailerAutomatico.app"
BIN="$APP/Contents/MacOS/TrailerAutomatico"
GUARDADO="/Users/Shared/TrailerAutomatico"
SAL="${SALIDA_PRUEBA:-$BASE/prueba}/flujo"
mkdir -p "$SAL"
RES="$SAL/resultado.txt"
MAL=0
ok() { echo "OK     $1" | tee -a "$RES"; }
falla() { echo "FALLA  $1" | tee -a "$RES"; MAL=1; }
nota() { echo "NOTA   $1" | tee -a "$RES"; }
cuenta() { find "$@" 2>/dev/null | wc -l | tr -d ' '; }

echo "equipo: $(sw_vers -productName) $(sw_vers -productVersion) · $(uname -m)" | tee "$RES"
if [ ! -x "$BIN" ]; then
    falla "el programa no esta instalado en $APP"
    exit 1
fi
VERSION="$(find "$APP" -name version.txt -exec cat {} \; 2>/dev/null | head -1 | tr -d ' \r\n')"
ok "programa instalado: version $VERSION"

# ---- 1. lo que trae el instalador
DRP="$(find "$APP" -name '*.drp' 2>/dev/null | head -1)"
if [ -n "$DRP" ]; then
    ok "trae las plantillas de DaVinci: $(basename "$DRP") ($(du -h "$DRP" | cut -f1 | tr -d ' '))"
else
    falla "no trae las plantillas de DaVinci (.drp)"
fi
[ "$(cuenta "$APP" -name plantillas_marcadores.json)" -ge 1 ] && ok "trae los marcadores de las 4 plantillas (plan sin DaVinci)" \
    || falla "faltan los marcadores de las plantillas"
[ "$(cuenta "$APP" -name perfiles_evento.json)" -ge 1 ] && ok "trae los tipos de evento (XV, boda, bautizo...)" \
    || falla "faltan los tipos de evento"
N="$(cuenta "$APP" -name 'XV_*_REC709.cube')"
[ "$N" -ge 4 ] && ok "trae los 4 looks de color suaves" || falla "faltan looks de color (hay $N de 4)"
[ "$(cuenta "$APP" -name XV_CORRECCION_COLOR.dctl)" -ge 1 ] && ok "trae el filtro de color" || falla "falta el filtro de color"
N="$(cuenta "$APP" "$GUARDADO" \( -name '*.mp3' -o -name '*.wav' \))"
[ "$N" -ge 15 ] && ok "trae la musica y los efectos de sonido ($N archivos)" || falla "falta musica o efectos de sonido (hay $N)"
N="$(cuenta "$APP" "$GUARDADO" \( -name '*.ttf' -o -name '*.otf' \))"
[ "$N" -ge 5 ] && ok "trae las fuentes de los titulos ($N)" || falla "faltan fuentes de los titulos (hay $N)"
N="$(cuenta "$HOME/Library/Fonts" \( -name '*.ttf' -o -name '*.otf' \))"
[ "$N" -ge 1 ] && ok "las fuentes quedaron instaladas en la Mac ($N en Library/Fonts)" || nota "no veo fuentes en ~/Library/Fonts"
FF="$(find "$APP" -type f -name ffmpeg 2>/dev/null | head -1)"
if [ -n "$FF" ] && "$FF" -version >/dev/null 2>&1; then
    ok "trae ffmpeg y funciona ($("$FF" -version | head -1 | cut -c1-40))"
else
    falla "no trae ffmpeg o no arranca"
fi
LUT="/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/MCP"
if [ -d "$LUT" ]; then
    ok "el color quedo en la carpeta de LUT de DaVinci ($(cuenta "$LUT" -type f) archivos)"
else
    nota "esta Mac no tiene DaVinci Resolve: la carpeta de LUT se llena al instalarlo y abrir el programa"
fi
[ -d "/Applications/DaVinci Resolve/DaVinci Resolve.app" ] && nota "esta Mac tiene DaVinci Resolve" \
    || nota "esta Mac NO tiene DaVinci Resolve: el armado dentro de DaVinci no se prueba aqui"

# ---- 2. autoprueba del programa instalado
"$BIN" --tarea verificar "$SAL/autoprueba.txt" >/dev/null 2>&1
FIN="$(tail -1 "$SAL/autoprueba.txt" 2>/dev/null)"
case "$FIN" in
    OK\|*) ok "autoprueba del programa instalado: ${FIN#OK|}" ;;
    *) falla "autoprueba: ${FIN:-sin respuesta}" ;;
esac

# ---- 3. el flujo completo con el programa instalado (se cierra antes la ventana que abrio el instalador)
osascript -e 'tell application "TrailerAutomatico" to quit' >/dev/null 2>&1
for i in $(seq 1 15); do pgrep -f "$BIN" >/dev/null || break; sleep 1; done
pkill -f "$BIN" >/dev/null 2>&1
sleep 2
PY="$(command -v python3)"
for CASO in "soltar" "evento_nuevo"; do
    EXTRA=""; [ "$CASO" = "evento_nuevo" ] && EXTRA="--dos-eventos"
    "$PY" "$PROG/herramientas/probar_arrastre.py" $EXTRA --programa "$BIN" --salida "$SAL/$CASO" > "$SAL/$CASO.log" 2>&1
    COD=$?
    ULT="$(tail -1 "$SAL/$CASO/resultado.txt" 2>/dev/null)"
    BIEN="$(grep -c '^OK' "$SAL/$CASO/resultado.txt" 2>/dev/null || echo 0)"
    if [ $COD = 0 ]; then
        ok "soltar una carpeta ($CASO): $BIEN comprobaciones bien · $ULT"
    else
        falla "soltar una carpeta ($CASO): codigo $COD · $ULT"
        grep '^FALLA' "$SAL/$CASO/resultado.txt" 2>/dev/null | head -5 | tee -a "$RES"
        tail -5 "$SAL/$CASO.log" 2>/dev/null
    fi
    grep -E 'ordenado solo|organizado por momentos|plan de las' "$SAL/$CASO/resultado.txt" 2>/dev/null | sed 's/^OK    /       /' | tee -a "$RES"
done

[ $MAL = 0 ] && echo "TODO BIEN" | tee -a "$RES" || echo "CON FALLAS" | tee -a "$RES"
exit $MAL
