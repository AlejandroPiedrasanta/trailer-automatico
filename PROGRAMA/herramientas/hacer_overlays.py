# -*- coding: utf-8 -*-
"""
hacer_overlays.py - Los OVERLAYS propios del programa (recursos/overlays/*.mp4), hechos con numeros: sin licencias, sin
internet y sin gastar creditos. Son video sobre NEGRO: en la linea van en una pista de arriba en modo «Pantalla»
(Screen), asi solo se ve la luz.

(17-nov, la persona: «crea elementos, overlays o transiciones súper potentes, dependiendo si son bodas o XV años»)

    DESTELLO  1,25 s  una banda de luz cruza el cuadro y lo llena en el centro: tapa el corte entre dos momentos
    BRILLOS   4 s     polvo de luz que sube y titila: para el titulo con el nombre y la tarjeta final

Un juego por tipo de evento (el color) y por formato (H 16:9, V 9:16):
    XV: dorado con rosa      BODA: blanco calido      (los demas tipos usan el de XV)

    python PROGRAMA/herramientas/hacer_overlays.py            los hace todos (si ya existen, los rehace)
"""
import os
import subprocess
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(os.path.dirname(AQUI), "recursos", "overlays")
FPS = 24
COLORES = {"XV": ((1.0, 0.80, 0.46), (1.0, 0.62, 0.80)),          # (luz, acento): dorado y rosa
           "BODA": ((1.0, 0.95, 0.86), (1.0, 0.86, 0.66))}        # blanco calido y champan
FORMATOS = {"H": (960, 540), "V": (540, 960)}                     # se calcula a la mitad y ffmpeg lo sube al doble


def destello(w, h, luz, acento, rng):
    """Banda de luz en diagonal que cruza de izquierda a derecha; en el cuadro del medio el cuadro entero queda casi
    blanco (ahi va el corte). Con una raya horizontal fina, como de lente anamorfico."""
    n = 30
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (x + 0.35 * (y - h / 2.0)) / float(w)                      # la banda va inclinada
    f1, f2 = rng.uniform(0, 6.28, 2)                               # luz desigual, suave (con ruido en bloques se pixelaba)
    ruido = (0.10 * np.sin(x * 0.011 + f1) * np.sin(y * 0.017 + f2) + 0.06 * np.sin((x + y) * 0.006 + f2)).astype(np.float32)
    for i in range(n):
        t = i / float(n - 1)
        pos = -0.3 + 1.6 * t
        banda = np.exp(-((u - pos) / 0.22) ** 2)
        lleno = np.exp(-((t - 0.5) / 0.16) ** 2)                   # el fogonazo del medio
        raya = np.exp(-((y - h * 0.5) / (h * 0.012)) ** 2) * np.exp(-((u - pos) / 0.5) ** 2)
        env = np.sin(np.pi * t) ** 0.8
        a = np.clip((0.75 * banda + 0.9 * lleno) * env * (1.0 + ruido), 0, 1)
        b = np.clip(raya * env * 0.9, 0, 1)
        yield np.clip(a[..., None] * np.array(luz, np.float32) + b[..., None] * np.array(acento, np.float32), 0, 1)


def brillos(w, h, luz, acento, rng):
    """Polvo de luz: puntos desenfocados que suben despacio y titilan, mas densos abajo. Entra y sale fundiendo."""
    n, k = 96, 150
    px = rng.uniform(0, w, k)
    py = rng.uniform(h * 0.15, h * 1.15, k)
    vel = rng.uniform(h * 0.04, h * 0.16, k)                       # px por segundo hacia arriba
    tam = rng.uniform(1.5, 7.0, k) * (h / 540.0)
    fase, ritmo = rng.uniform(0, 6.28, k), rng.uniform(2.0, 7.0, k)
    rosa = rng.uniform(0, 1, k) < 0.3
    der = rng.uniform(-8, 8, k)
    for i in range(n):
        t = i / float(FPS)
        cuadro = np.zeros((h, w, 3), np.float32)
        env = min(1.0, t / 0.7) * min(1.0, (n / float(FPS) - t) / 0.9)
        for j in range(k):
            cx, cy, s = px[j] + der[j] * t, py[j] - vel[j] * t, tam[j]
            r = int(s * 3) + 1
            x0, x1, y0, y1 = int(cx) - r, int(cx) + r + 1, int(cy) - r, int(cy) + r + 1
            if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
                continue
            xs, ys = np.arange(max(0, x0), min(w, x1)), np.arange(max(0, y0), min(h, y1))
            g = np.exp(-((xs[None, :] - cx) ** 2 + (ys[:, None] - cy) ** 2) / (2.0 * s * s))
            brillo = (0.35 + 0.65 * (0.5 + 0.5 * np.sin(fase[j] + ritmo[j] * t))) * (0.4 + 0.6 * min(1.0, cy / h + 0.4))
            cuadro[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1] += (g * brillo)[..., None] * np.array(
                acento if rosa[j] else luz, np.float32)
        yield np.clip(cuadro * env, 0, 1)


def guardar(nombre, w, h, cuadros):
    os.makedirs(DESTINO, exist_ok=True)
    ruta = os.path.join(DESTINO, nombre + ".mp4")
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", "%dx%d" % (w, h), "-r", str(FPS), "-i", "-", "-vf", "scale=%d:%d:flags=bicubic" % (w * 2, h * 2),
                          "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p", "-an", ruta],
                         stdin=subprocess.PIPE)
    n = 0
    for c in cuadros:
        p.stdin.write((c * 255.0 + 0.5).astype(np.uint8).tobytes())
        n += 1
    p.stdin.close()
    p.wait()
    return ruta, n


def main():
    for tipo, (luz, acento) in COLORES.items():
        for fmt, (w, h) in FORMATOS.items():
            for efecto, fn in (("DESTELLO", destello), ("BRILLOS", brillos)):
                nombre = "%s_%s_%s" % (tipo, efecto, fmt)
                ruta, n = guardar(nombre, w, h, fn(w, h, luz, acento, np.random.default_rng(len(nombre) * 7 + n_semilla(nombre))))
                print("%-22s %3d cuadros  %5.0f KB" % (nombre + ".mp4", n, os.path.getsize(ruta) / 1024.0))


def n_semilla(nombre):
    return sum(ord(c) for c in nombre)


if __name__ == "__main__":
    sys.exit(main())
