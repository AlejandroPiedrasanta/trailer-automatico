# -*- coding: utf-8 -*-
"""
empaquetar.py - Crea "3 INSTALADORES/Mac/Trailer automatico (Mac).zip": el programa listo para copiar a una Mac
(o a otra PC), sin el material ni los videos del evento.

  - ARMAR TRAILERS.command con permiso de ejecucion (el doble clic funciona al descomprimir en la Mac) y el LEEME.
  - El material va por dentro (PROGRAMA/datos/trabajo, se crea solo); lo terminado sale en «EVENTO TERMINADO - <evento>».
  - PROGRAMA completo: codigo, plantillas de Resolve (.drp), musica y SFX, fuentes, DCTL y LUTs.
    Sin PROGRAMA/datos (analisis, respaldos, entorno de Python): se crean solos en la Mac.

Uso:  python empaquetar.py
"""
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))   # PROGRAMA/nucleo: rutas pone las demas carpetas
import rutas  # noqa: E402

NOMBRE = "Trailer automatico (Mac).zip"
RAIZ_ZIP = "TRAILER AUTOMATICO"
SALTAR = {"datos", "__pycache__", "compilar"}


RAIZ = os.path.dirname(rutas.PROGRAMA)        # la carpeta del proyecto (solo PROGRAMA y 3 INSTALADORES, 16-nov)
HERRAMIENTAS = os.path.join(rutas.PROGRAMA, "herramientas")


def empaquetar(log=print):
    os.makedirs(os.path.join(RAIZ, "3 INSTALADORES", "Mac"), exist_ok=True)
    destino = os.path.join(RAIZ, "3 INSTALADORES", "Mac", NOMBRE)
    tmp = destino + ".tmp"
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        def agregar(origen, nombre, ejecutable=False):
            info = zipfile.ZipInfo(RAIZ_ZIP + "/" + nombre, time.localtime(os.path.getmtime(origen))[:6])
            info.compress_type = zipfile.ZIP_STORED if origen.lower().endswith((".mp3", ".png", ".drp")) \
                else zipfile.ZIP_DEFLATED
            info.external_attr = ((0o100755 if ejecutable else 0o100644) << 16)
            with open(origen, "rb") as f:
                z.writestr(info, f.read())

        def carpeta_vacia(nombre):
            info = zipfile.ZipInfo(RAIZ_ZIP + "/" + nombre.rstrip("/") + "/")
            info.external_attr = (0o40755 << 16) | 0x10
            z.writestr(info, b"")
        # (16-nov) los lanzadores viven en PROGRAMA/herramientas y el LEEME en PROGRAMA/config; en el paquete van a la
        # vista, junto a PROGRAMA (los lanzadores sirven en los dos sitios). El material va por dentro (datos/trabajo).
        for f, p in (("ARMAR TRAILERS.command", os.path.join(HERRAMIENTAS, "ARMAR TRAILERS.command")),
                     ("ARMAR TRAILERS.bat", os.path.join(HERRAMIENTAS, "ARMAR TRAILERS.bat")),
                     ("LEEME.txt", os.path.join(rutas.CONFIG_PROG, "LEEME.txt"))):
            if os.path.exists(p):
                agregar(p, f, f.endswith(".command"))
                n += 1
        for raiz, dirs, archivos in os.walk(rutas.PROGRAMA):
            dirs[:] = [d for d in dirs if d not in SALTAR]
            for f in archivos:
                if f.endswith((".pyc", ".tmp")):
                    continue
                p = os.path.join(raiz, f)
                rel = os.path.relpath(p, RAIZ).replace(os.sep, "/")
                agregar(p, rel)
                n += 1
    os.replace(tmp, destino)
    log("Paquete para Mac: %s (%d archivos, %.0f MB)" % (destino, n, os.path.getsize(destino) / 1e6))
    return destino


if __name__ == "__main__":
    empaquetar()
