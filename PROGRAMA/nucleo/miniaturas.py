# -*- coding: utf-8 -*-
"""
miniaturas.py - (1.6.0) Miniaturas del material para la ventana (tarjetas de Material y la «Línea del día»): un cuadro
de cada video (a 40 % de su duración, o el segundo pedido) y cada foto, de 320 px, guardadas en DATOS/miniaturas por
ruta, tamaño y fecha del archivo: la segunda vez no se repiten. Siempre en un hilo (nunca en el de la ventana).

  hacer(ruta, tipo, t=None)  -> ruta del .jpg o None
  varias([(ruta, tipo, t)], hilos=3) -> {ruta: jpg}
"""
import os
import hashlib
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

import rutas

LADO = 320


def carpeta():
    return os.path.join(rutas.DATOS, "miniaturas")


def _clave(ruta, t):
    try:
        st = os.stat(ruta)
        firma = "%s|%d|%d|%s|%d" % (os.path.abspath(ruta).lower(), st.st_size, int(st.st_mtime), t, LADO)
    except OSError:
        return None
    return hashlib.sha1(firma.encode("utf-8", "replace")).hexdigest()[:20] + ".jpg"


def _foto(ruta, salida):
    """Con QImageReader de Qt (respeta la orientacion EXIF del celular y no frena la ventana: todo en C++, sin el
    candado de Python); si no, Pillow; si no, ffmpeg."""
    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QImageReader
        r = QImageReader(ruta)
        r.setAutoTransform(True)
        tam = r.size()
        if tam.isValid() and max(tam.width(), tam.height()) > LADO:
            r.setScaledSize(tam.scaled(QSize(LADO, LADO), Qt.KeepAspectRatio))
        img = r.read()
        if not img.isNull() and img.save(salida, "JPG", 82):
            return True
    except Exception:
        pass
    try:
        from PIL import Image, ImageOps
        with Image.open(ruta) as im:
            im = ImageOps.exif_transpose(im)
            im.draft("RGB", (LADO * 2, LADO * 2))
            im = im.convert("RGB")
            im.thumbnail((LADO, LADO))
            im.save(salida, "JPEG", quality=82)
        return True
    except Exception:
        return _ffmpeg(ruta, salida, None)


def _ffmpeg(ruta, salida, t):
    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if t is not None:
        cmd += ["-ss", "%.2f" % max(0.0, t)]
    cmd += ["-i", ruta, "-frames:v", "1", "-vf", "scale=%d:-2" % LADO, "-q:v", "5", salida]
    try:
        r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=60,
                           creationflags=rutas.SIN_VENTANA)
        return r.returncode == 0 and os.path.isfile(salida) and os.path.getsize(salida) > 500
    except Exception:
        return False


def hacer(ruta, tipo, t=None):
    """La miniatura de un medio (tipo foto / video / dron); t = segundo del video (None = 40 % de la duracion)."""
    nombre = _clave(ruta, t)
    if not nombre:
        return None
    destino = os.path.join(carpeta(), nombre)
    if os.path.isfile(destino):
        return destino
    os.makedirs(carpeta(), exist_ok=True)
    tmp = destino + ".tmp.jpg"
    if tipo == "foto":
        ok = _foto(ruta, tmp)
    else:
        if t is None:
            t = _duracion(ruta) * 0.4
        ok = _ffmpeg(ruta, tmp, t)
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    os.replace(tmp, destino)
    return destino


def _duracion(ruta):
    try:
        r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", ruta], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=30, creationflags=rutas.SIN_VENTANA)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def varias(pedidos, hilos=2):
    """[(ruta, tipo, t)] -> {ruta: jpg} (las que se pudieron)."""
    out = {}
    pedidos = [x for x in pedidos if x and x[0] and os.path.isfile(x[0])]
    if not pedidos:
        return out
    with ThreadPoolExecutor(max(1, hilos)) as ex:
        for (ruta, _, _), jpg in zip(pedidos, ex.map(lambda x: hacer(*x), pedidos)):
            if jpg:
                out[ruta] = jpg
    return out
