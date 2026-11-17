#!/bin/bash
# Desinstalar Tráiler automático (Mac). Quita la app y su servicio de actualizaciones; tus carpetas de trabajo y tus videos NO se
# tocan. Va dentro de la app (Contents/Resources o Frameworks): desde la 1.5.2 el disco solo trae la app y el enlace a Aplicaciones.
# Sirve para las dos formas de instalar: arrastrada a Aplicaciones (es tuya: no pide contraseña) y con el .pkg de antes (pide la
# contraseña de la Mac para quitar la app y el servicio del sistema).
osascript -e 'display dialog "¿Desinstalar Tráiler automático?\n\nTus eventos terminados (EVENTO TERMINADO en el Escritorio) y el material guardado no se borran." buttons {"Cancelar", "Desinstalar"} default button 2 with title "Tráiler automático"' >/dev/null 2>&1 || exit 0
ETQ="com.cinemaproductions.trailerautomatico.actualizar"
APP="/Applications/TrailerAutomatico.app"
pkill -f "TrailerAutomatico.app/Contents/MacOS/TrailerAutomatico" 2>/dev/null
# el servicio del usuario (app arrastrada)
launchctl bootout "gui/$(id -u)/$ETQ" >/dev/null 2>&1
rm -f "$HOME/Library/LaunchAgents/$ETQ.plist"
if [ -f "/Library/LaunchDaemons/$ETQ.plist" ] || { [ -d "$APP" ] && [ ! -w "$APP" ]; }; then
    # instalada con el .pkg de antes: la app y el servicio son del sistema
    osascript -e 'do shell script "launchctl bootout system/com.cinemaproductions.trailerautomatico.actualizar >/dev/null 2>&1; rm -f /Library/LaunchDaemons/com.cinemaproductions.trailerautomatico.actualizar.plist; rm -rf /Applications/TrailerAutomatico.app \"/Library/Application Support/TrailerAutomatico\"; pkgutil --forget com.cinemaproductions.trailerautomatico >/dev/null 2>&1; true" with administrator privileges' >/dev/null 2>&1 || exit 0
else
    rm -rf "$APP"
fi
osascript -e 'display dialog "Tráiler automático se desinstaló." buttons {"OK"} default button 1 with title "Tráiler automático"' >/dev/null 2>&1
