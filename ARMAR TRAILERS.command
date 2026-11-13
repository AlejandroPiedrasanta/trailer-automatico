#!/bin/bash
# ▶ TRAILER AUTOMATICO (Mac) - doble clic para abrir el programa.
# La primera vez prepara todo solo: librerias de Python, ffmpeg y la carpeta de LUTs de DaVinci.
cd "$(dirname "$0")/PROGRAMA" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
VENV="datos/venv-mac"
LUT="/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/MCP"

aviso() {
  osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with title \"Trailer automatico\"" >/dev/null 2>&1
}

if ! command -v python3 >/dev/null 2>&1; then
  aviso "Falta Python 3. Instalalo desde python.org y vuelve a abrir el programa."
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Instalando ffmpeg (solo la primera vez)..."
    brew install ffmpeg || { aviso "No se pudo instalar ffmpeg. Revisa la ventana de Terminal."; exit 1; }
  else
    aviso "Falta ffmpeg. Instala Homebrew (brew.sh) y luego escribe en Terminal: brew install ffmpeg"
    exit 1
  fi
fi
if [ ! -x "$VENV/bin/python" ]; then
  echo "Preparando el programa (solo la primera vez, tarda unos minutos)..."
  python3 -m venv "$VENV" && "$VENV/bin/pip" install --upgrade pip && "$VENV/bin/pip" install -r config/requisitos.txt \
    || { rm -rf "$VENV"; aviso "No se pudieron instalar las librerias. Revisa la ventana de Terminal."; exit 1; }
fi
if [ ! -w "$LUT" ]; then
  echo "DaVinci necesita una carpeta para el color y el ruido: la Mac te pedira tu clave una sola vez."
  osascript -e "do shell script \"mkdir -p '$LUT' && chmod 777 '$LUT'\" with administrator privileges" >/dev/null 2>&1 \
    || aviso "Sin permiso para la carpeta de LUTs de DaVinci: el color y la reduccion de ruido no se instalaran."
fi
exec "$VENV/bin/python" interfaz/trailer_xv.py
