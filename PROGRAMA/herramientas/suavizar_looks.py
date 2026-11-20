# -*- coding: utf-8 -*-
"""
suavizar_looks.py - Hace la version SUAVE de cada LOOK (LUT .cube) de PROGRAMA/dctl mezclandolo con «sin cambio».
Las tomas de los eventos ya vienen en Rec.709 (color terminado de camara): un look entero les sube demasiado el
contraste y la saturacion. Con FUERZA 0.5 el look se nota pero la toma sigue siendo la de camara, y ademas el
look nunca sube la saturacion de un color (sin_subir_saturacion).

  python PROGRAMA/herramientas/suavizar_looks.py            escribe XV_*_REC709.cube junto a los originales
  python PROGRAMA/herramientas/suavizar_looks.py 0.4        con otra fuerza para todos

build_trailers pone el _REC709 en el nodo POST-CLIP del grupo de color (LOOK_REC709). Los originales no se tocan.
"""
import os
import sys
import glob

DCTL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dctl")
SUFIJO = "_REC709.cube"
FUERZA = 0.5                                   # 0 = sin look, 1 = el look entero
# el Kodak 2383 de Resolve espera imagen Cineon Log: sobre Rec.709 sube el contraste +45 %. Va a un cuarto.
FUERZAS = {"FILM_KODAK": 0.25}
# El look da el TONO (calido, frio en las sombras...) pero NO sube la saturacion: la persona ve chillon todo lo que
# pasa de lo que trae la camara. Cada color sale, como mucho, con su saturacion de entrada mas este margen (que es lo
# que deja tenir un poco los grises).
MARGEN_SATURACION = 0.035


def _sat(c):
    mx = max(c)
    return (mx - min(c)) / mx if mx > 1e-6 else 0.0


def sin_subir_saturacion(entra, sale):
    """Devuelve `sale` con la saturacion recortada a la de `entra` (+ margen), sin cambiarle la luz."""
    tope = _sat(entra) + MARGEN_SATURACION * (1.0 - _sat(entra))
    for _ in range(3):
        s = _sat(sale)
        if s <= tope + 1e-4:
            break
        y = 0.2126 * sale[0] + 0.7152 * sale[1] + 0.0722 * sale[2]
        k = tope / s
        sale = tuple(min(1.0, max(0.0, y + (x - y) * k)) for x in sale)
    return sale


# (1.8.1, la persona: «al colorizar satura o expone demasiado... usa el vectorscopio o la forma de onda») MEDIDO en los
# _REC709 de antes con la saturacion de arriba ((max - min) / max + 0,035): la piel salia con +5-10 % de croma, el lila
# +6-8 % y un blanco calido +16-34 % (ese margen es enorme para un color casi gris), y el Kodak aclaraba las altas
# (0,70 -> 0,75) y hundia los negros (0,10 -> 0,08). Ahora se mide como el VECTORSCOPIO (radio Cb/Cr Rec.709) y la
# FORMA DE ONDA (luz Rec.709): el look cambia el TONO (hacia donde va el color) pero no la cantidad ni la exposicion.
KR, KB = 0.2126, 0.0722
CROMA_MARGEN = 0.004            # radio Cb/Cr que el look puede sumar (tono): un gris queda gris, sin dominante
LUZ_SUBE, LUZ_BAJA = 0.015, 0.025   # cuanto puede aclarar / oscurecer el look los medios
ALTAS = 0.75                    # desde esta luz el look nunca aclara (no quema)
# por debajo de SOMBRAS el look no oscurece NADA y hasta SOMBRAS_HASTA cada vez menos (MEDIDO en DaVinci: con 0,01 de
# margen la 071 pasaba de 5 % a 11 % de negros aplastados: los pixeles justo encima de 0,02 caian debajo)
SOMBRAS, SOMBRAS_HASTA, SOMBRAS_BAJA = 0.15, 0.25, 0.0


def _ycc(c):
    y = KR * c[0] + (1 - KR - KB) * c[1] + KB * c[2]
    return y, (c[2] - y) / (2 * (1 - KB)), (c[0] - y) / (2 * (1 - KR))


def _rgb(y, cb, cr):
    r = y + 2 * (1 - KR) * cr
    b = y + 2 * (1 - KB) * cb
    g = (y - KR * r - KB * b) / (1 - KR - KB)
    return (r, g, b)


def proteger(entra, sale):
    """`sale` con la luz y el croma acotados por `entra` (forma de onda y vectorscopio): ver arriba."""
    y0, cb0, cr0 = _ycc(entra)
    y1, cb1, cr1 = _ycc(sale)
    baja = LUZ_BAJA
    if y0 <= SOMBRAS:
        baja = SOMBRAS_BAJA
    elif y0 < SOMBRAS_HASTA:
        baja = SOMBRAS_BAJA + (LUZ_BAJA - SOMBRAS_BAJA) * (y0 - SOMBRAS) / (SOMBRAS_HASTA - SOMBRAS)
    y = min(max(y1, y0 - baja), y0 + LUZ_SUBE)
    if y0 >= ALTAS:
        y = min(y, y0)
    c0, c1 = (cb0 * cb0 + cr0 * cr0) ** 0.5, (cb1 * cb1 + cr1 * cr1) ** 0.5
    k = min(1.0, (c0 + CROMA_MARGEN) / c1) if c1 > 1e-6 else 1.0
    for _ in range(8):                           # que entre en 0-1 sin cambiar la luz: se le quita croma
        rgb = _rgb(y, cb1 * k, cr1 * k)
        if min(rgb) >= -1e-4 and max(rgb) <= 1 + 1e-4:
            break
        k *= 0.85
    return tuple(min(1.0, max(0.0, x)) for x in _rgb(y, cb1 * k, cr1 * k))


def suavizar(ruta, fuerza):
    cab, vals, n = [], [], 33
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        for linea in f:
            p = linea.split()
            if len(p) == 3 and p[0][0] in "0123456789.-":
                vals.append([float(x) for x in p])
            elif linea.strip():
                if p[0] == "LUT_3D_SIZE":
                    n = int(p[1])
                cab.append(linea.strip())
    if len(vals) != n ** 3:
        raise ValueError("%s: se esperaban %d valores y hay %d" % (os.path.basename(ruta), n ** 3, len(vals)))
    salida = ruta[:-5] + SUFIJO
    with open(salida, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(c for c in cab if not c.upper().startswith("TITLE")) + "\n\n")
        i = 0
        for b in range(n):                      # en un .cube el rojo es el que cambia mas rapido
            for g in range(n):
                for r in range(n):
                    ident = (r / (n - 1.0), g / (n - 1.0), b / (n - 1.0))
                    v = vals[i]
                    i += 1
                    mezcla = tuple(min(1.0, max(0.0, a + fuerza * (x - a))) for a, x in zip(ident, v))
                    f.write("%.6f %.6f %.6f\n" % proteger(ident, sin_subir_saturacion(ident, mezcla)))
    return salida


def main(args):
    for ruta in sorted(glob.glob(os.path.join(DCTL, "XV_*.cube"))):
        if ruta.endswith(SUFIJO):
            continue
        fuerza = float(args[0]) if args else next((v for k, v in FUERZAS.items() if k in ruta), FUERZA)
        print("%s -> %s (fuerza %.2f)" % (os.path.basename(ruta), os.path.basename(suavizar(ruta, fuerza)), fuerza))


if __name__ == "__main__":
    main(sys.argv[1:])
