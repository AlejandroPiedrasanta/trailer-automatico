# -*- coding: utf-8 -*-
"""
preparar_animaciones.py - (1.6.0) Convierte los videos de Higgsfield (Kling 3.0) en las animaciones de la ventana
(PROGRAMA/recursos/animaciones). Se corre a mano, una vez, cuando se generan videos nuevos:

    python PROGRAMA/herramientas/preparar_animaciones.py CARPETA_CON_LOS_MP4

En la carpeta: reposo.mp4, trabajo.mp4, despertar.mp4, hecho.mp4 (el astrolabio sobre negro puro, 1920x1080, en la
caja 400,110,1119x860 como I_negro.png / T_negro.png) y cielo.mp4 (el cielo, 16:9).

Astrolabio: el fondo es negro puro, asi que la transparencia sale del brillo (lo que no es negro es objeto o luz) mas
la silueta quieta de recursos/astrolabio_*.png (el metal oscuro adentro queda opaco); la luz que se sale de la caja se
desvanece en los bordes. Se guarda «apilado»: color arriba, alfa abajo, en un H.264 chico que ffmpeg vuelve a unir
al reproducir (animacion.Pelicula). Los bucles se cortan en el cuadro mas parecido al primero y dormir = despertar al
reves. Cielo: bucle con un fundido de 2 s entre el final y el principio. Todo con -tune fastdecode: se decodifica
en la mitad de tiempo (menos CPU mientras la ventana esta abierta).
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
RECURSOS = os.path.join(AQUI, "..", "recursos")
SALIDA = os.path.join(RECURSOS, "animaciones")
CAJA = (400, 110, 1119, 860)            # x, y, ancho, alto en 1920x1080 (preparar: I_negro.png)
LADO = (1118, 860)                      # tamaño guardado (pares)
FPS = 24


def _info(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", ruta], capture_output=True, text=True)
    return tuple(int(x) for x in r.stdout.strip().split(","))


def cuadros(ruta, caja=None, tam=None, ref=1920.0):
    """Los cuadros (uint8 RGB) recortados a la caja (en coordenadas de un video de ref de ancho) y escalados a tam."""
    W, H = _info(ruta)
    vf = []
    if caja:
        k = W / ref
        x, y, w, h = (int(round(v * k)) for v in caja)
        vf.append("crop=%d:%d:%d:%d" % (w, h, x, y))
    if tam:
        vf.append("scale=%d:%d:flags=lanczos" % tam)
    else:
        tam = (W, H)
    cmd = ["ffmpeg", "-v", "error", "-i", ruta] + (["-vf", ",".join(vf)] if vf else []) + [
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    datos = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(datos, np.uint8).reshape(-1, tam[1], tam[0], 3)


def corte_bucle(a, ultimos=12):
    """El cuadro del final mas parecido al primero: el bucle va de 0 a ese (sin incluirlo)."""
    chico = a[:, ::8, ::8].astype(np.float32)
    paso = np.median(np.abs(np.diff(chico, axis=0)).mean(axis=(1, 2, 3)))
    difs = [(np.abs(chico[i] - chico[0]).mean(), i) for i in range(len(a) - ultimos, len(a))]
    d, i = min(difs)
    print("   corte en %d de %d (salto %.2f, paso normal %.2f)" % (i, len(a), d, paso))
    return i


def silueta(nombre, tam):
    """La silueta quieta (0..1) de recursos/astrolabio_<nombre>.png dentro de la caja, como la dibuja la ventana."""
    img = Image.open(os.path.join(RECURSOS, "astrolabio_%s.png" % nombre)).convert("RGBA")
    w, h = tam
    e = min(w / img.width, h / img.height)
    tw, th = int(round(img.width * e)), int(round(img.height * e))
    lienzo = Image.new("L", tam, 0)
    lienzo.paste(img.getchannel("A").resize((tw, th), Image.LANCZOS), ((w - tw) // 2, (h - th) // 2))
    return np.asarray(lienzo, np.float32) / 255.0


def _suave(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def borde(tam, ancho=0.05):
    """Hasta donde llega la luz: redondo (un destello no deja ver la caja) y nada en los bordes."""
    w, h = tam
    fx = np.minimum(np.arange(w), np.arange(w)[::-1]) / (ancho * h)
    fy = np.minimum(np.arange(h), np.arange(h)[::-1]) / (ancho * h)
    lados = _suave(0.0, 1.0, np.minimum.outer(np.clip(fy, 0, 1), np.clip(fx, 0, 1)))
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot((xx - w / 2.0) / (w / 2.0), (yy - h / 2.0) / (h / 2.0))
    return lados * _suave(1.05, 0.80, r)


def con_alfa(c, sil, plumas):
    """c: cuadro RGB sobre negro -> (color sin premultiplicar, alfa 0..1)."""
    c = c.astype(np.float32)
    m = c.max(axis=2)
    luz = np.maximum(m / 255.0, _suave(4.0, 40.0, m)) * plumas
    objeto = sil * np.clip((m - 1.5) / 4.0, 0.0, 1.0)
    a = np.maximum(objeto, luz)
    a[m < 2.0] = 0.0
    color = np.where(a[..., None] > 0.004, np.clip(c / np.maximum(a, 1e-4)[..., None], 0, 255), 0)
    # bajo lo transparente, el color de al lado (el 4:2:0 no oscurece los bordes)
    pre = Image.fromarray((c).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    aa = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    relleno = np.asarray(pre, np.float32) / np.maximum(np.asarray(aa, np.float32)[..., None] / 255.0, 1e-3)
    color = np.where(a[..., None] > 0.02, color, np.clip(relleno, 0, 255))
    return color, a


def guardar_apilado(cuadros_alfa, salida, lado=LADO):
    w, h = lado
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, 2 * h),
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-tune", "fastdecode", "-crf", "18",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", salida], stdin=subprocess.PIPE)
    for color, a in cuadros_alfa:
        abajo = np.repeat((a * 255.0 + 0.5).astype(np.uint8)[..., None], 3, axis=2)
        p.stdin.write(np.vstack([color.astype(np.uint8), abajo]).tobytes())
    p.stdin.close()
    p.wait()
    print("   %s  %.1f MB" % (os.path.basename(salida), os.path.getsize(salida) / 1e6))


def astrolabio(entrada, nombre, sil0, sil1=None, bucle=True):
    print(nombre)
    a = cuadros(entrada, CAJA, LADO)
    fin = corte_bucle(a) if bucle else len(a)
    plumas = borde(LADO)
    n = max(1, fin - 1)
    k = 10 if bucle else 0
    resto = a[0].astype(np.float32) - a[fin].astype(np.float32) if bucle else None

    def gen():
        for i in range(fin):
            sil = sil0 if sil1 is None else sil0 + (sil1 - sil0) * _suave(0.3, 0.75, i / n)
            c = a[i]
            if k and i >= fin - k:            # lo que falta para volver al primer cuadro se reparte en los ultimos
                c = np.clip(c.astype(np.float32) + resto * ((i - (fin - k) + 1) / (k + 1.0)), 0, 255)
            yield con_alfa(c, sil, plumas)
    guardar_apilado(gen(), os.path.join(SALIDA, nombre))


def bodegon(entrada, salida):
    """Ajustes: el bodegon (9:16, 1080x1920, en la caja 41,117,998x1686 como B_negro.png) con la silueta de
    recursos/ajustes_bodegon.png: solo se mueve la luz (brillos en el oro, la tiara y la lente)."""
    print("bodegon")
    img = Image.open(os.path.join(RECURSOS, "ajustes_bodegon.png")).convert("RGBA")
    lado = (img.width // 2 * 2, img.height // 2 * 2)
    sil = np.asarray(img.getchannel("A").resize(lado, Image.LANCZOS), np.float32) / 255.0
    a = cuadros(entrada, (41, 117, 998, 1686), lado, ref=1080.0)
    fin = corte_bucle(a)
    plumas = borde(lado)
    resto = a[0].astype(np.float32) - a[fin].astype(np.float32)
    k = 10

    def gen():
        for i in range(fin):
            c = a[i]
            if i >= fin - k:
                c = np.clip(c.astype(np.float32) + resto * ((i - (fin - k) + 1) / (k + 1.0)), 0, 255)
            yield con_alfa(c, sil, plumas)
    guardar_apilado(gen(), salida, lado)


def cielo(entrada, salida, cruce=48):
    print("cielo")
    a = cuadros(entrada).astype(np.float32)
    n = len(a) - cruce                      # bucle: el final se funde con el principio
    out = a[:n].copy()
    for j in range(cruce):
        w = (j + 1) / (cruce + 1.0)
        out[j] = a[n + j] * (1 - w) + a[j] * w
    H, W = out.shape[1:3]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-tune", "fastdecode", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", salida], stdin=subprocess.PIPE)
    for f in out:
        p.stdin.write(np.clip(f + 0.5, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()
    print("   %s  %.1f MB, %d cuadros" % (os.path.basename(salida), os.path.getsize(salida) / 1e6, n))


def main():
    ent = sys.argv[1]
    os.makedirs(SALIDA, exist_ok=True)
    s_i, s_t = silueta("inicio", LADO), silueta("trabajo", LADO)
    que = sys.argv[2:] or ["reposo", "trabajo", "despertar", "hecho", "cielo", "bodegon"]
    if "reposo" in que:
        astrolabio(os.path.join(ent, "reposo.mp4"), "astro_reposo.mp4", s_i)
    if "trabajo" in que:
        astrolabio(os.path.join(ent, "trabajo.mp4"), "astro_trabajo.mp4", s_t)
    if "despertar" in que:
        astrolabio(os.path.join(ent, "despertar.mp4"), "astro_despertar.mp4", s_i, s_t, bucle=False)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(SALIDA, "astro_despertar.mp4"), "-vf",
                        "reverse", "-c:v", "libx264", "-preset", "slow", "-tune", "fastdecode", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", os.path.join(SALIDA, "astro_dormir.mp4")], check=True)
        print("   astro_dormir.mp4 (al reves)")
    if "hecho" in que and os.path.isfile(os.path.join(ent, "hecho.mp4")):
        astrolabio(os.path.join(ent, "hecho.mp4"), "astro_hecho.mp4", s_t, bucle=False)
    if "cielo" in que and os.path.isfile(os.path.join(ent, "cielo.mp4")):
        cielo(os.path.join(ent, "cielo.mp4"), os.path.join(SALIDA, "cielo.mp4"))
    if "bodegon" in que and os.path.isfile(os.path.join(ent, "bodegon.mp4")):
        bodegon(os.path.join(ent, "bodegon.mp4"), os.path.join(SALIDA, "bodegon.mp4"))


if __name__ == "__main__":
    main()
