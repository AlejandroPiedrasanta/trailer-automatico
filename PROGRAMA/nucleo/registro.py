# -*- coding: utf-8 -*-
"""
registro.py - Registro del programa en archivo (para encontrar bugs despues) y ganchos de errores.

  datos/registro/registro.log todo lo que hace el programa (rota a 1 MB, guarda 3)
  datos/registro/fallo_nativo.log si Python o Qt se caen del todo (faulthandler)
Cualquier excepcion no atrapada (en la ventana o en un hilo) queda en el registro con su traza.
"""
import os
import sys
import logging
import threading
import traceback
from logging.handlers import RotatingFileHandler

import rutas

_log = logging.getLogger("trailer")
_fallo = None


def preparar():
    """Llamar una sola vez al arrancar."""
    global _fallo
    os.makedirs(os.path.dirname(rutas.REGISTRO), exist_ok=True)
    if sys.stdout is None:                 # .exe sin consola: print() no debe romper nada
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if not _log.handlers:
        h = RotatingFileHandler(rutas.REGISTRO, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
        _log.addHandler(h)
        _log.setLevel(logging.INFO)
    try:
        import faulthandler
        _fallo = open(os.path.join(os.path.dirname(rutas.REGISTRO), "fallo_nativo.log"), "a", encoding="utf-8")
        faulthandler.enable(_fallo, all_threads=True)
    except Exception:
        pass

    def gancho(tipo, valor, tb):
        _log.error("Error no atrapado:\n%s", "".join(traceback.format_exception(tipo, valor, tb)))
    sys.excepthook = gancho

    def gancho_hilo(args):
        if args.exc_type is SystemExit:
            return
        _log.error("Error en el hilo %s:\n%s", getattr(args.thread, "name", "?"),
                   "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = gancho_hilo
    _log.info("=== Trailer automatico %s · %s · Python %s · %s", rutas.version(),
              "instalado" if rutas.CONGELADO else "codigo", sys.version.split()[0], sys.platform)
    _log.info("Carpeta de trabajo: %s | datos: %s", rutas.BASE, rutas.DATOS)


def info(msg):
    _log.info(str(msg))


def error(msg):
    _log.error(str(msg))


def aviso(msg, origen=""):
    """Compatibilidad con los modulos de la escena de Inicio (vienen de CineCaptions)."""
    _log.warning("%s%s" % (("[%s] " % origen) if origen else "", msg))
