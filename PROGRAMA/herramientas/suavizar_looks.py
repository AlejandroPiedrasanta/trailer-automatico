# -*- coding: utf-8 -*-
"""
suavizar_looks.py - Hace la version SUAVE de cada LOOK (LUT .cube) de PROGRAMA/dctl mezclandolo con «sin cambio».
Las tomas de los eventos ya vienen en Rec.709 (color terminado de camara): un look entero les sube demasiado el
contraste y la saturacion. Con FUERZA 0.5 el look se nota pero la toma sigue siendo la de camara.

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
                    f.write("%.6f %.6f %.6f\n" % tuple(min(1.0, max(0.0, a + fuerza * (x - a))) for a, x in zip(ident, v)))
    return salida


def main(args):
    for ruta in sorted(glob.glob(os.path.join(DCTL, "XV_*.cube"))):
        if ruta.endswith(SUFIJO):
            continue
        fuerza = float(args[0]) if args else next((v for k, v in FUERZAS.items() if k in ruta), FUERZA)
        print("%s -> %s (fuerza %.2f)" % (os.path.basename(ruta), os.path.basename(suavizar(ruta, fuerza)), fuerza))


if __name__ == "__main__":
    main(sys.argv[1:])
