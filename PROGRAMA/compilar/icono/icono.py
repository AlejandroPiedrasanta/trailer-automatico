# -*- coding: utf-8 -*-
"""Guarda el icono del programa como .ico (Windows, 16 a 256 px) y .png. El dibujo esta en interfaz/icono_app.py
(el mismo que usa la ventana). Tambien lo usa compilar/mac/construir_mac.sh: dibujar(1024) -> .icns."""
import os
import sys
import io

PROG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))       # compilar/icono -> PROGRAMA
sys.path.insert(0, os.path.join(PROG, "nucleo"))
sys.path.insert(0, os.path.join(PROG, "interfaz"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402


def dibujar(t):
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    import icono_app
    return icono_app.dibujar(t)


def guardar(ruta_ico):
    from PIL import Image
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    imgs = []
    for t in (256, 128, 64, 48, 32, 24, 16):
        buf = QByteArray()
        b = QBuffer(buf)
        b.open(QIODevice.WriteOnly)
        dibujar(t).save(b, "PNG")
        imgs.append(Image.open(io.BytesIO(bytes(buf))).convert("RGBA"))
    # cada tamano con su propio dibujo (los chicos van simplificados), no reescalados del grande
    imgs[0].save(ruta_ico, format="ICO", sizes=[(i.width, i.height) for i in imgs], append_images=imgs[1:])
    imgs[0].save(ruta_ico.replace(".ico", ".png"))


def limpiar(entrada, salida=None, lado=1024):
    """Prepara una imagen del icono (cuadro redondeado sobre fondo claro, con sombra) como icono_fuente.png: recorta
    el cuadro, le quita el fondo y la sombra (esquinas transparentes con borde suave) y la deja de lado x lado."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    salida = salida or os.path.join(PROG, "recursos", "icono_fuente.png")
    im = Image.open(entrada).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    lum = a.mean(axis=2)
    fondo = float(np.median(np.concatenate([lum[:5, :5].ravel(), lum[-5:, -5:].ravel()])))
    oscuro = lum < fondo - 60                               # el cuadro es oscuro; el fondo y la sombra, claros
    filas = np.where(oscuro.sum(axis=1) > oscuro.shape[1] * 0.10)[0]
    cols = np.where(oscuro.sum(axis=0) > oscuro.shape[0] * 0.10)[0]
    x0, x1, y0, y1 = int(cols.min()), int(cols.max()) + 1, int(filas.min()), int(filas.max()) + 1
    s = 0                                                   # radio de las esquinas: por la diagonal de arriba-izquierda
    while s < (x1 - x0) // 3 and not oscuro[y0 + s, x0 + s]:
        s += 1
    radio = max(4.0, s / (1 - 2 ** -0.5))
    recorte = im.crop((x0, y0, x1, y1)).resize((lado, lado), Image.LANCZOS)
    k = 4                                                   # mascara con antialias (4x), un poco hacia adentro: fuera
    dentro = lado * 0.006                                   # del borde neon queda el canto claro del fondo
    esc = lado / float(max(x1 - x0, y1 - y0))
    m = Image.new("L", (lado * k, lado * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((k * dentro, k * dentro, lado * k - k * dentro, lado * k - k * dentro),
                                        radius=(radio * esc - dentro) * k, fill=255)
    m = m.resize((lado, lado), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.4))
    recorte.putalpha(m)
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    recorte.save(salida)
    return salida, (x0, y0, x1, y1), round(radio, 1)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "limpiar":     # python icono.py limpiar <imagen>  -> recursos/icono_fuente.png
        print(limpiar(sys.argv[2]))
    else:
        guardar(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico"))
