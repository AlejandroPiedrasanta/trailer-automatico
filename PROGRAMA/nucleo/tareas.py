# -*- coding: utf-8 -*-
"""
tareas.py - Trabajos sin ventana que llama el instalador (o la compilacion) con
    TrailerAutomatico.exe --tarea <instalar|verificar> <archivo_estado.txt>

El archivo de estado recibe lineas "PROGRESO|n|texto" y termina con "OK|texto" o "ERROR|texto"; el instalador
lo va leyendo (mismo patron que CineCaptions).

  instalar   carpetas de trabajo, fuentes de los titulos, DCTL/LUT de color en DaVinci, datos de la version anterior
  verificar  autoprueba: librerias, recursos, ffmpeg y el modulo de scripting de DaVinci (sin abrirlo)
"""
import os
import sys
import shutil
import subprocess
import traceback

import rutas


class Estado:
    def __init__(self, ruta):
        self.ruta = ruta
        if ruta:
            open(ruta, "w", encoding="utf-8").close()

    def _escribir(self, linea):
        if self.ruta:
            with open(self.ruta, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
        else:
            print(linea, flush=True)

    def progreso(self, n, texto):
        self._escribir("PROGRESO|%d|%s" % (n, texto))

    def fin(self, ok, texto):
        self._escribir("%s|%s" % ("OK" if ok else "ERROR", texto))


def instalar(est):
    import motor
    est.progreso(10, "Creando las carpetas de trabajo")
    rutas.crear_carpetas()
    leeme = os.path.join(rutas.BASE, "LEEME.txt")
    origen = os.path.join(rutas.CONFIG_PROG, "LEEME.txt")
    if not os.path.exists(leeme) and os.path.exists(origen):
        shutil.copy2(origen, leeme)
    est.progreso(35, "Instalando las fuentes de los titulos")
    n_f = motor.instalar_fuentes(lambda m: None)
    est.progreso(60, "Instalando el color y la reduccion de ruido en DaVinci")
    n_l = 0
    try:
        os.makedirs(rutas.DIR_LUT_MCP, exist_ok=True)
        for f in os.listdir(rutas.DCTL):
            o, d = os.path.join(rutas.DCTL, f), os.path.join(rutas.DIR_LUT_MCP, f)
            if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(o):
                shutil.copy2(o, d)
                n_l += 1
    except Exception as ex:
        est.progreso(70, "Aviso: no se pudo escribir en la carpeta de LUT de DaVinci (%s)" % ex)
    est.progreso(85, "Trayendo los analisis anteriores")
    n_m = rutas.migrar_datos()
    est.fin(True, "Listo: carpeta %s · %d fuentes · %d archivos de color · %d datos" % (rutas.BASE, n_f, n_l, n_m))


def verificar(est):
    fallas = []

    def prueba(nombre, fn):
        try:
            r = fn()
            if r is False:
                fallas.append(nombre)
        except Exception as ex:
            fallas.append("%s (%s)" % (nombre, ex))
    est.progreso(10, "Librerias")
    prueba("PySide6", lambda: __import__("PySide6.QtWidgets"))
    prueba("numpy", lambda: __import__("numpy"))
    prueba("Pillow", lambda: __import__("PIL.Image"))
    for m in ("motor", "analizar_material", "renderizar", "masterizar", "mezcla", "ritmo", "ruido", "sfx", "indexar"):
        prueba(m, lambda m=m: __import__(m))
    est.progreso(40, "Recursos")
    for r in ("build_trailers.py", "perfiles_evento.json", "LEEME.txt", "version.txt"):
        prueba(r, lambda r=r: os.path.exists(rutas.codigo(r) if r.endswith(".py") else os.path.join(rutas.CONFIG_PROG, r)))
    prueba("plantillas .drp", lambda: os.path.exists(rutas.PLANTILLAS_DRP))
    prueba("musica y SFX", lambda: len(os.listdir(rutas.AUDIO)) >= 15)
    prueba("fuentes", lambda: len(os.listdir(rutas.FUENTES)) >= 5)
    prueba("DCTL", lambda: any(f.endswith(".dctl") for f in os.listdir(rutas.DCTL)))
    est.progreso(60, "ffmpeg")
    prueba("ffmpeg", lambda: subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30,
                                            creationflags=rutas.SIN_VENTANA).returncode == 0)
    prueba("ffprobe", lambda: subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=30,
                                             creationflags=rutas.SIN_VENTANA).returncode == 0)
    est.progreso(80, "Scripting de DaVinci")
    if os.path.exists(rutas.SCRIPT_LIB):
        import motor
        prueba("DaVinciResolveScript", lambda: motor._dvr() is not None)
    if fallas:
        est.fin(False, "Fallan: " + ", ".join(fallas))
    else:
        est.fin(True, "Autoprueba completa")
    return not fallas


def correr(nombre, archivo):
    est = Estado(archivo)
    try:
        if nombre == "instalar":
            instalar(est)
        elif nombre == "verificar":
            return 0 if verificar(est) else 1
        else:
            est.fin(False, "Tarea desconocida: %s" % nombre)
            return 2
    except Exception as ex:
        est.fin(False, "%s | %s" % (ex, traceback.format_exc().replace("\n", " · ")[-600:]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(correr(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
