# -*- coding: utf-8 -*-
"""
empaquetar.py - Crea "3 INSTALADORES/Mac/Trailer automatico (Mac).zip": el programa listo para copiar a una Mac
(o a otra PC), sin el material ni los videos del evento.

  - ARMAR TRAILERS.command con permiso de ejecucion (el doble clic funciona al descomprimir en la Mac).
  - Carpetas vacias 1 MATERIAL/FOTOS|VIDEOS|DRON (lo terminado sale en «EVENTO TERMINADO - <evento>»).
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


def empaquetar(log=print):
    os.makedirs(os.path.join(rutas.BASE, "3 INSTALADORES", "Mac"), exist_ok=True)
    destino = os.path.join(rutas.BASE, "3 INSTALADORES", "Mac", NOMBRE)
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
        for f in ("ARMAR TRAILERS.command", "ARMAR TRAILERS.bat", "LEEME.txt"):
            p = os.path.join(rutas.BASE, f)
            if os.path.exists(p):
                agregar(p, f, f.endswith(".command"))
                n += 1
        for sub in ("FOTOS", "VIDEOS", "DRON"):
            carpeta_vacia("1 MATERIAL/" + sub)          # lo terminado sale en «EVENTO TERMINADO - <evento>» (1.5.7)
        for raiz, dirs, archivos in os.walk(rutas.PROGRAMA):
            dirs[:] = [d for d in dirs if d not in SALTAR]
            for f in archivos:
                if f.endswith((".pyc", ".tmp")):
                    continue
                p = os.path.join(raiz, f)
                rel = os.path.relpath(p, rutas.BASE).replace(os.sep, "/")
                agregar(p, rel)
                n += 1
    os.replace(tmp, destino)
    log("Paquete para Mac: %s (%d archivos, %.0f MB)" % (destino, n, os.path.getsize(destino) / 1e6))
    return destino


if __name__ == "__main__":
    empaquetar()
