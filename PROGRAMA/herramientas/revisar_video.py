# -*- coding: utf-8 -*-
"""
revisar_video.py - Revisa un video terminado SIN verlo entero (para quien desarrolla; usa ffmpeg, numpy y Pillow).

  python PROGRAMA/herramientas/revisar_video.py hoja    <video> <salida.jpg> [n=48] [desde_s hasta_s]
        hoja de contactos: n cuadros repartidos, con su tiempo; dice cuantos salen con luces quemadas
  python PROGRAMA/herramientas/revisar_video.py cuadros <video> <salida.jpg> t1 t2 ...
        esos segundos en grande (para leer los textos y ver el final)
  python PROGRAMA/herramientas/revisar_video.py audio   <video> [a-b ...]
        tramos casi en silencio (2 s o mas por debajo de -38 dB: huecos entre canciones) y, de cada tramo a-b pedido,
        el volumen cada medio segundo (para ver cruces de cancion, la voz y los golpes de SFX)

Lo que mide el programa al terminar un render (saturacion, luz, LUFS) esta en entrega/masterizar.py.
"""
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw


def _cuadro(video, t, w, h):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % max(0.0, t), "-i", video, "-frames:v", "1", "-vf",
                        "scale=%d:%d" % (w, h), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True).stdout
    if len(r) < w * h * 3:
        return None
    return np.frombuffer(r[:w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def _duracion(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       capture_output=True, text=True).stdout.strip()
    return float(r or 0)


def _vertical(video):
    """True si el video es mas alto que ancho (formato vertical 9:16)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip().splitlines()
    try:
        r = r[0].split(",")
        return int(r[1]) > int(r[0])
    except (ValueError, IndexError):
        return False


def _hoja(video, salida, tiempos, w, h, cols):
    hoja = Image.new("RGB", (cols * w, ((len(tiempos) + cols - 1) // cols) * (h + 13)), (0, 0, 0))
    dr = ImageDraw.Draw(hoja)
    quemados = []
    for i, t in enumerate(tiempos):
        x, y = (i % cols) * w, (i // cols) * (h + 13)
        c = _cuadro(video, t, w, h)
        if c is not None:
            quemados.append(float((c.min(axis=2) >= 243).mean()))
            hoja.paste(Image.fromarray(c), (x, y))
        dr.text((x + 2, y + h), "%d:%05.2f" % (t // 60, t % 60), fill=(255, 255, 255))
    hoja.save(salida, quality=84)
    return quemados


def hoja(video, salida, n=48, desde=None, hasta=None):
    dur = _duracion(video)
    a = 3.0 if desde is None else desde
    b = dur - 0.3 if hasta is None else hasta
    tam = (135, 240, 12) if _vertical(video) else (240, 135, 8)
    q = _hoja(video, salida, [a + (b - a) * (i + 0.5) / n for i in range(n)], *tam)
    print("%s: %d cuadros | quemado medio %.1f %% | maximo %.1f %% | con mas de 10 %%: %d" % (
        salida, len(q), 100 * np.mean(q), 100 * max(q), sum(x > 0.10 for x in q)))


def cuadros(video, salida, tiempos):
    _hoja(video, salida, tiempos, *((360, 640, 5) if _vertical(video) else (640, 360, 3)))
    print("%s: %d cuadros" % (salida, len(tiempos)))


def _volumen(video, a=None, b=None, paso=0.5):
    cmd = ["ffmpeg", "-v", "error"]
    if a is not None:
        cmd += ["-ss", "%.2f" % a, "-t", "%.2f" % (b - a)]
    cmd += ["-i", video, "-vn", "-ac", "1", "-ar", "4000", "-f", "s16le", "pipe:1"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.int16).astype(np.float32) / 32768.0
    k = int(4000 * paso)
    n = len(x) // k
    return 20 * np.log10(np.sqrt((x[:n * k].reshape(n, k) ** 2).mean(axis=1)) + 1e-6)


def audio(video, tramos):
    db = _volumen(video)
    n = len(db)
    huecos, i = [], 0
    while i < n:
        if db[i] < -38:
            j = i
            while j + 1 < n and db[j + 1] < -38:
                j += 1
            if (j - i + 1) * 0.5 >= 2.0 and i * 0.5 > 5 and (j + 1) * 0.5 < n * 0.5 - 3:
                huecos.append("%d:%04.1f (%.1f s)" % (i * 0.5 // 60, (i * 0.5) % 60, (j - i + 1) * 0.5))
            i = j + 1
        else:
            i += 1
    print("%s: %.0f s | silencios de 2 s o mas: %s" % (video.replace("\\", "/").split("/")[-1], n * 0.5,
                                                    ", ".join(huecos) or "ninguno"))
    for t in tramos:
        a, b = (float(x) for x in t.split("-"))
        print("  %6.1f-%6.1f: %s" % (a, b, " ".join("%.0f" % d for d in _volumen(video, a, b))))


def main(args):
    if len(args) < 2:
        print(__doc__)
        return 1
    if args[0] == "hoja":
        nums = [float(x) for x in args[3:]]
        hoja(args[1], args[2], int(nums[0]) if nums else 48, *(nums[1:3] if len(nums) >= 3 else ()))
    elif args[0] == "cuadros":
        cuadros(args[1], args[2], [float(x) for x in args[3:]])
    elif args[0] == "audio":
        audio(args[1], args[2:])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
