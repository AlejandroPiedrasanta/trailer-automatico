# -*- coding: utf-8 -*-
"""
preparar_iconos.py - (1.6.0) Los iconos de la ventana hechos en Higgsfield (gpt_image_2_6): hojas de 4 x 4 iconos de
trazo dorado sobre negro puro -> recursos/iconos/<nombre>.png (blanco con su transparencia, 256 x 256). La ventana los
pinta del color que pida (piezas.icono): oro en las tarjetas, blanco en los botones, gris en lo pendiente.

    python PROGRAMA/herramientas/preparar_iconos.py hoja1.png nombres1 hoja2.png nombres2 ...

nombres = los 16 de la hoja en orden de lectura, separados por coma ('-' = no usar esa celda). Ejemplo:
    hojaA.png foto,video,pelicula,claqueta,dron,reloj,carpeta,chip,onda,disco,engrane,papelera,refrescar,lapiz,texto,info

La transparencia sale del brillo (el fondo es negro puro); cada icono se recorta, se centra en un cuadro y se ajusta a
un mismo tamaño (84 % del lado). GROSOR engrosa un poco el trazo para que a 24-50 px no se vea lavado.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "recursos", "iconos")
LADO = 256
OCUPA = 0.84
GROSOR = 3          # pixeles de mas por lado (a 1024) al engrosar el trazo; 0 = como viene


def _mascara(celda):
    a = np.asarray(celda.convert("RGB"), np.float32)
    m = a.max(axis=2)
    alfa = np.clip((m - 18.0) / (150.0 - 18.0), 0.0, 1.0)      # negro -> 0; el oro (aun el oscuro) -> 1
    return Image.fromarray((alfa * 255).astype(np.uint8), "L")


def cortar(hoja, nombres):
    im = Image.open(hoja).convert("RGB")
    W, H = im.size
    hechos = []
    for i, nombre in enumerate(nombres):
        if not nombre or nombre == "-":
            continue
        fila, col = divmod(i, 4)
        x0, y0 = int(W * col / 4), int(H * fila / 4)
        x1, y1 = int(W * (col + 1) / 4), int(H * (fila + 1) / 4)
        m = _mascara(im.crop((x0 + 6, y0 + 6, x1 - 6, y1 - 6)))
        caja = m.point(lambda v: 255 if v > 40 else 0).getbbox()
        if not caja:
            print("  %-12s celda %d vacia" % (nombre, i + 1))
            continue
        m = m.crop(caja)
        lado = max(m.width, m.height)
        cuadro = Image.new("L", (lado, lado), 0)
        cuadro.paste(m, ((lado - m.width) // 2, (lado - m.height) // 2))
        k = 1024.0 / lado * OCUPA                          # a 1024 para engrosar y reducir con calidad
        grande = Image.new("L", (1024, 1024), 0)
        g = cuadro.resize((max(1, int(lado * k)), max(1, int(lado * k))), Image.LANCZOS)
        grande.paste(g, ((1024 - g.width) // 2, (1024 - g.height) // 2))
        if GROSOR:
            grande = grande.filter(ImageFilter.MaxFilter(2 * GROSOR + 1))
        final = grande.resize((LADO, LADO), Image.LANCZOS)
        rgba = Image.new("RGBA", (LADO, LADO), (255, 255, 255, 0))
        rgba.putalpha(final)
        os.makedirs(SALIDA, exist_ok=True)
        rgba.save(os.path.join(SALIDA, nombre + ".png"), optimize=True)
        hechos.append(nombre)
    print("  %s: %s" % (os.path.basename(hoja), ", ".join(hechos)))
    return hechos


def main():
    args = sys.argv[1:]
    for hoja, nombres in zip(args[0::2], args[1::2]):
        cortar(hoja, [n.strip() for n in nombres.split(",")])


if __name__ == "__main__":
    main()
