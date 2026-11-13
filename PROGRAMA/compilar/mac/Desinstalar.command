#!/bin/bash
# Desinstalar Tráiler automático (Mac). Quita la app; tus carpetas de trabajo y tus videos NO se tocan.
osascript -e 'display dialog "¿Desinstalar Tráiler automático?\n\nTus carpetas de trabajo (1 MATERIAL, 2 VIDEOS TERMINADOS) y tus videos no se borran." buttons {"Cancelar", "Desinstalar"} default button 2 with title "Tráiler automático"' >/dev/null 2>&1 || exit 0
pkill -f "TrailerAutomatico.app/Contents/MacOS/TrailerAutomatico" 2>/dev/null
osascript -e 'do shell script "rm -rf /Applications/TrailerAutomatico.app; pkgutil --forget com.cinemaproductions.trailerautomatico >/dev/null 2>&1; true" with administrator privileges' >/dev/null 2>&1 \
  && osascript -e 'display dialog "Tráiler automático se desinstaló." buttons {"OK"} default button 1 with title "Tráiler automático"' >/dev/null 2>&1
