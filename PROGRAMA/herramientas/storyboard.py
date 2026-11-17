# -*- coding: utf-8 -*-
"""
storyboard.py - (16-nov) El plan de una version SIN abrir DaVinci, para mirarlo antes de armar: un cuadro del medio de
cada plano, con su toma, su lugar en el video y lo que vio la IA local en ese tramo (los cuadros que no sirven).

La persona (2026-11-16): «me estás entregando videos muy mediocres». Antes de armar y renderizar (una hora), se mira esto.

Uso (con los datos del programa, o los de otra carpeta con TRAILER_DATOS / TRAILER_BASE):
    python PROGRAMA/herramientas/storyboard.py 1min salida.jpg [--vertical] [--evento NOMBRE] [--tipo boda]
Imprime una linea por plano: momento, segundo, toma (L = camara lenta, E = estabilizar), ini y duracion en la toma, y
MALOS con los cuadros que la IA marco en ese tramo (deberia salir vacio).
"""
import os
import sys
import json
import math
import re
import argparse
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))
import rutas  # noqa: E402
import motor  # noqa: E402
import analizar_material as am  # noqa: E402

FUENTE = "C\\:/Windows/Fonts/arial.ttf" if os.name == "nt" else "/System/Library/Fonts/Supplemental/Arial.ttf"


def planear(version, formato="horizontal", evento="", tipo="xv"):
    an = am.analizar(rutas.BASE, log=lambda m: None)
    with open(os.path.join(rutas.RECURSOS, "plantillas_marcadores.json"), encoding="utf-8") as f:
        plantillas = json.load(f)
    ruta = rutas.codigo("build_trailers.py")
    g = {"__name__": "build_trailers", "resolve": motor._ResolveFalso(plantillas), "BASE": rutas.BASE, "ANALISIS": an,
         "EVENTO": evento or None, "SOLO": [version], "REHACER": True, "DRY_RUN": True, "SIN_RESOLVE": True,
         "TIPO_EVENTO": tipo, "VERTICALES": True, "FORMATO": formato, "print": lambda *a, **k: print(*a)}
    with open(ruta, encoding="utf-8") as f:
        exec(compile(f.read(), ruta, "exec"), g)
    return g.get("PLANES") or []


def cuadro(it, t, texto, salida):
    filtro = ("scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,"
              "drawtext=fontfile='%s':text='%s':x=3:y=3:fontsize=11:fontcolor=yellow:box=1:boxcolor=black@0.6"
              % (FUENTE, re.sub(r"[^A-Za-z0-9 .()]", " ", texto)))
    entrada = ["-i", it["ruta"]] if it["tipo"] == "foto" else ["-ss", "%.2f" % t, "-i", it["ruta"]]
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + entrada + ["-vf", filtro, "-frames:v", "1", salida],
                   creationflags=rutas.SIN_VENTANA)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("version")
    a.add_argument("salida")
    a.add_argument("--vertical", action="store_true")
    a.add_argument("--evento", default="")
    a.add_argument("--tipo", default="xv")
    a.add_argument("--fps", type=float, default=24.0)
    o = a.parse_args()
    planes = planear(o.version, "vertical" if o.vertical else "horizontal", o.evento, o.tipo)
    if not planes:
        print("sin plan")
        return 1
    _, _, _, zonas = planes[0]
    tmp = o.salida + "_cuadros"
    os.makedirs(tmp, exist_ok=True)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    k = 0
    for nombre, z0, _, piezas in zonas:
        pos = z0
        for p in piezas:
            it = p["item"]
            dur_s = p["dur_f"] / o.fps * p.get("vel", 1.0)
            ini = p.get("ini", 0.0)
            inst = [x for x in (it.get("ia") or {}).get("instantes") or [] if ini - 1.5 <= x[0] <= ini + dur_s + 1.5]
            malos = ["%.0f:%s" % (x[0], x[3] if len(x) > 3 else "?") for x in inst if len(x) > 2 and x[2] is False]
            texto = "%s %5.1fs %s %s%s" % (nombre[:4], pos / o.fps, os.path.basename(it["ruta"])[:34].replace("VIDEO ", ""),
                                          "L" if p.get("vel", 1) < 1 else "", "E" if p.get("estabilizar") else "")
            print("%-60s ini=%6.1f dur=%4.1f %s" % (texto, ini, dur_s, ("MALOS " + ",".join(malos)) if malos else ""))
            cuadro(it, ini + dur_s / 2.0, texto, os.path.join(tmp, "%03d.jpg" % k))
            k += 1
            pos += p["dur_f"]
    cols = 6
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(tmp, "%03d.jpg"), "-vf",
                    "tile=%dx%d:color=black" % (cols, int(math.ceil(k / float(cols)))), "-frames:v", "1", o.salida],
                   creationflags=rutas.SIN_VENTANA)
    print("planos: %d -> %s" % (k, o.salida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
