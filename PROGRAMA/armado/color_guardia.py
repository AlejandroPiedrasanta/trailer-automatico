# -*- coding: utf-8 -*-
"""
color_guardia.py - (1.8.1, la persona: «al colorizar satura o expone demasiado... cuida esos detalles en cualquier
plantilla... utiliza el vectorscopio o la forma de onda para medir») Antes de poner el CDL de un plano se MIDE el
resultado: se toma un cuadro real del tramo que usa el plano, se le hace en numpy la misma cadena que DaVinci
(DCTL de correccion del grupo PRE-CLIP -> CDL del plano -> look _REC709 del POST-CLIP) y se mira con las medidas
de los monitores:

  forma de onda: medios (p50), % quemado (> 0,98), % negros aplastados (< 0,02)
  vectorscopio: saturacion p95 (radio Cb/Cr Rec.709) y dominante de los grises (Cb, Cr de lo casi neutro)

Si el CDL hace que el plano QUEME mas, APLASTE los negros, SATURE mas que la toma, deje los grises TEÑIDOS o mueva
la exposicion de mas, se suaviza (100 % -> 70 % -> 45 % -> 20 % -> nada) hasta que pase. Asi una medida vieja o
equivocada del analisis (MEDIDO: «061» tenia la de otro archivo y salia con los medios en 0,22 y 12 % de negros
aplastados) no puede estropear un plano. El ruido (DCTL del nodo del clip) no cambia los niveles: no se simula.

Por que en numpy y no con DaVinci: la API no deja agregar nodos ni leer el scope; renderizar cada plano para medirlo
costaria minutos. La simulacion se comparo con el render real (sim.py del 20-nov): mismos medios +-0,05 y misma
saturacion +-0,01 en los planos sin titulos encima.
"""
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

import rutas

ANCHO = 240                               # (240x135: las medidas salen iguales que a 640 +-0,01 y 4 veces mas rapido)
QUEMADO, APLASTADO = 0.98, 0.02
PASOS = (1.0, 0.7, 0.45, 0.2, 0.0)       # cuanto del CDL se deja al suavizar
# limites (contra la TOMA original, y para quemado contra la cadena sin CDL: el look ya suaviza las altas)
MAS_QUEMADO = 0.3                        # % de pixeles quemados que el CDL puede sumar
MAS_NEGROS = 1.5                         # % de negros aplastados que puede sumar
SAT_TOPE = 1.0                           # saturacion p95 del final contra la de la toma (nunca mas)
SAT_MARGEN = 0.004
EXPOSICION_MAX = 0.10                    # cuanto pueden moverse los medios (igualar sin desfigurar)
DOMINANTE_MAX = 0.02                     # Cb/Cr de los grises: mas que esto (y mas que la toma) es dominante


# ------------------------------------------------------------------ la cadena de DaVinci en numpy
_PRE = {}


def _pre_constantes():
    """Las constantes del DCTL PRE-CLIP leidas del archivo (si cambia el DCTL, cambia la simulacion)."""
    if not _PRE:
        d = {"NEGROS": 0.0, "CONTRASTE": 1.0, "PIVOTE": 0.42, "SATURACION": 0.93, "VIVOS": 0.22, "RODILLA": 0.86,
             "LUCES_SIN_COLOR": 0.55}
        try:
            with open(os.path.join(rutas.PROGRAMA, "dctl", "XV_CORRECCION_COLOR.dctl"), encoding="utf-8") as f:
                for nombre, valor in re.findall(r"__CONSTANT__\s+float\s+(\w+)\s*=\s*([-\d.]+)f?", f.read()):
                    d[nombre] = float(valor)
        except Exception:
            pass
        _PRE.update(d)
    return _PRE


def _pre(img):
    import numpy as np
    k = _pre_constantes()

    def suave(v):
        v = (v - k["NEGROS"]) / (1 - k["NEGROS"])
        v = k["PIVOTE"] + (v - k["PIVOTE"]) * k["CONTRASTE"]
        rod = k["RODILLA"]
        v = np.where(v > rod, rod + (1 - rod) * np.tanh((v - rod) / (1 - rod)), v)
        return np.clip(v, 0, 1)

    def esc(a, b, x):
        t = np.clip((x - a) / (b - a), 0, 1)
        return t * t * (3 - 2 * t)
    R, G, B = img[..., 0], img[..., 1], img[..., 2]
    y0 = 0.2126 * R + 0.7152 * G + 0.0722 * B
    sat = (img.max(-1) - img.min(-1)) / (img.max(-1) + 1e-4)
    r, g, b = suave(R), suave(G), suave(B)
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    piel = np.clip((r - b) * 4, 0, 1) * np.clip(1 - np.abs((g - b) / (r - b + 1e-4) - 0.5) * 2, 0, 1)
    s = k["SATURACION"] * (1 - k["VIVOS"] * esc(0.45, 0.95, sat))
    s = 1 - (1 - s) * (1 - 0.5 * piel)
    s = s * (1 - k["LUCES_SIN_COLOR"] * esc(0.82, 1.0, y0))
    return np.clip(np.stack([y + (c - y) * s for c in (r, g, b)], -1), 0, 1)


def _cdl(img, c):
    import numpy as np
    sl = np.array([float(x) for x in c["Slope"].split()], np.float32)
    of = np.array([float(x) for x in c["Offset"].split()], np.float32)
    pw = np.array([float(x) for x in c["Power"].split()], np.float32)
    o = np.clip(img * sl + of, 0, 1) ** pw
    y = (o * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    return np.clip(y + (o - y) * float(c["Saturation"]), 0, 1)


_LUTS = {}


def _lut(ruta):
    import numpy as np
    if ruta not in _LUTS:
        n, v = 33, []
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for linea in f:
                p = linea.split()
                if p and p[0] == "LUT_3D_SIZE":
                    n = int(p[1])
                elif len(p) == 3 and p[0][0] in "0123456789.-":
                    v.append([float(x) for x in p])
        _LUTS[ruta] = np.array(v, np.float32).reshape(n, n, n, 3)
    return _LUTS[ruta]


def _look(img, ruta):
    import numpy as np
    if not ruta or not os.path.exists(ruta):
        return img
    L = _lut(ruta)
    n = L.shape[0]
    x = np.clip(img, 0, 1) * (n - 1)
    i0 = np.floor(x).astype(np.int32).clip(0, n - 2)
    f = x - i0
    out = 0
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[..., 0] if dr else 1 - f[..., 0]) * (f[..., 1] if dg else 1 - f[..., 1]) * \
                    (f[..., 2] if db else 1 - f[..., 2])
                out = out + w[..., None] * L[i0[..., 2] + db, i0[..., 1] + dg, i0[..., 0] + dr]
    return out


def medidas(img):
    """Lo que dirian los monitores de DaVinci (forma de onda y vectorscopio) de esa imagen RGB 0-1."""
    import numpy as np
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cb, cr = (b - y) / 1.8556, (r - y) / 1.5748
    rad = np.sqrt(cb * cb + cr * cr)
    neutro = (rad < 0.04) & (y > 0.25) & (y < 0.9)
    hay = neutro.sum() > 150
    return {"y50": float(np.percentile(y, 50)), "quem": float((y > QUEMADO).mean() * 100),
            "aplast": float((y < APLASTADO).mean() * 100), "s95": float(np.percentile(rad, 95)),
            "cb": float(cb[neutro].mean()) if hay else 0.0, "cr": float(cr[neutro].mean()) if hay else 0.0}


# ------------------------------------------------------------------ cuadros
def _guardado(ruta, t):
    """(1.8.2) El cuadro que la IA ya saco al analizar (vision_ia.cuadro_guardado), achicado: sin abrir el video."""
    try:
        import numpy as np
        import vision_ia
        from PIL import Image
        p = vision_ia.cuadro_guardado(ruta, t)
        if not p:
            return None
        im = Image.open(p).convert("RGB")
        im = im.resize((ANCHO, max(2, int(round(ANCHO * im.height / float(im.width))))), Image.BILINEAR)
        return np.asarray(im, np.float32) / 255.0
    except Exception:
        return None


def cuadro(ruta, t):
    import numpy as np
    img = _guardado(ruta, t)
    if img is not None:
        return img
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % max(0.0, t), "-i", ruta,
                            "-frames:v", "1", "-vf", "scale=%d:-2:flags=area,format=rgb24" % ANCHO, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=60, creationflags=rutas.SIN_VENTANA)
    except Exception:
        return None
    b = r.stdout
    if not b or len(b) % (ANCHO * 3):
        return None
    return np.frombuffer(b, np.uint8).reshape(-1, ANCHO, 3).astype(np.float32) / 255.0


def cuadros(pedidos, hilos=8):
    """pedidos: [(ruta, segundo)] -> {(ruta, segundo): imagen o None}, en paralelo."""
    unicos = list(dict.fromkeys(pedidos))
    with ThreadPoolExecutor(hilos) as ex:
        return dict(zip(unicos, ex.map(lambda p: cuadro(*p), unicos)))


# ------------------------------------------------------------------ la revision
def _mezcla(c, t):
    """El CDL al t (0 = sin tocar, 1 = entero)."""
    def m(clave, neutro):
        return " ".join("%.4f" % (neutro + t * (float(x) - neutro)) for x in c[clave].split())
    return dict(c, Slope=m("Slope", 1.0), Offset=m("Offset", 0.0), Power=m("Power", 1.0),
                Saturation="%.3f" % (1.0 + t * (float(c["Saturation"]) - 1.0)))


def _fallas(mt, ms, mb):
    """Que esta mal en el final (mt) contra la toma (ms) y contra la cadena sin CDL (mb)."""
    f = []
    if mt["quem"] > max(ms["quem"], mb["quem"]) + MAS_QUEMADO:
        f.append("quema")
    if mt["aplast"] > max(ms["aplast"], mb["aplast"]) + MAS_NEGROS:
        f.append("negros")
    if mt["s95"] > max(ms["s95"] * SAT_TOPE, mb["s95"]) + SAT_MARGEN:
        f.append("satura")
    if abs(mt["y50"] - ms["y50"]) > EXPOSICION_MAX:
        f.append("exposicion")
    dom = max(abs(mt["cb"]), abs(mt["cr"]))
    if dom > DOMINANTE_MAX and dom > max(abs(ms["cb"]), abs(ms["cr"]), abs(mb["cb"]), abs(mb["cr"])) + 0.003:
        f.append("dominante")
    return f


def vigilar(cdl, img, look=None):
    """El CDL que se puede poner sin que el plano queme, aplaste negros, sature, se tiña o cambie de mas, medido en la
    imagen `img` (la toma, RGB 0-1) con la cadena PRE -> CDL -> look. Devuelve (cdl, [fallas que tenia el CDL entero],
    t con que quedo)."""
    if cdl is None or img is None:
        return cdl, [], 1.0
    base = _pre(img)
    ms, mb = medidas(img), medidas(_look(base, look))
    primeras = None
    for t in PASOS:
        c = _mezcla(cdl, t) if t < 1.0 else cdl
        f = _fallas(medidas(_look(_cdl(base, c), look)), ms, mb)
        if primeras is None:
            primeras = f
        if not f:
            return c, primeras, t
    return _mezcla(cdl, 0.0), primeras, 0.0


def vigilar_varios(trabajos, look=None, hilos=8):
    """trabajos: {clave: (cdl, imagen)} -> {clave: (cdl, fallas, t)}, en paralelo (numpy suelta el GIL)."""
    claves = list(trabajos)
    with ThreadPoolExecutor(hilos) as ex:
        res = list(ex.map(lambda k: vigilar(trabajos[k][0], trabajos[k][1], look), claves))
    return dict(zip(claves, res))
