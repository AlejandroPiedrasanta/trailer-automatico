# -*- coding: utf-8 -*-
"""
ruido_tomas.py - Mide el ruido de cada video. Es el MISMO proceso para cualquier toma que entre a una plantilla:
camara, celular o dron, de dia o de noche.

Como se mide: 3 cuadros del video llevados al tamano de la linea de tiempo (1920x1080, que es donde se ve el ruido), en
bloques de 16x16. En cada bloque se mira lo que queda al quitar la imagen (un pasa-altos, metodo de Immerkaer) y se toma
el de los bloques mas LISOS (percentil 10) que no esten quemados ni en negro: la textura y el movimiento no cuentan.
Devuelve {"luz", "sombra", "color"} en la escala 0-1 de la imagen; ruido.py lo convierte en un nivel de 1 a 5.

Calibrado con ruido puesto a proposito sobre tomas limpias (x1000): 0.8/255 -> 1.8 · 1.5/255 -> 3.0 · 3.1/255 -> 5.4 ·
5.6/255 -> 9.5 · 8.9/255 -> 14.9. Una toma limpia de camara o celular con buena luz da entre 0.7 y 1.6.

El resultado se guarda en datos/analisis/ruido_tomas.json (por ruta, tamano y fecha del archivo): cada video se mide
una sola vez.
"""
import os
import json
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor

import rutas

ANCHO, ALTO, LADO = 1920, 1080, 16
PUNTOS = (0.25, 0.5, 0.75)                      # en que parte del video se toman los cuadros
REF_SOMBRA, PISO_SOMBRA = 0.25, 0.07            # el ruido de una sombra cuenta como si la zona tuviera luz 0.25
VERSION = 2                                     # sube al cambiar la forma de medir: lo medido antes se vuelve a medir
CACHE = os.path.join(rutas.ANALISIS, "ruido_tomas.json")
_candado = rutas.__dict__.setdefault("_RUIDO_CANDADO", threading.Lock())      # (1.8.1) el mismo en todas las cargas


def _cuadro(ruta, t):
    import numpy as np
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-ss", "%.2f" % t, "-i", ruta, "-frames:v", "1",
           "-vf", "scale=%d:%d:force_original_aspect_ratio=increase:flags=bicubic,crop=%d:%d" % (ANCHO, ALTO, ANCHO, ALTO),
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        b = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=rutas.SIN_VENTANA).stdout
    except Exception:
        return None
    if len(b) != ANCHO * ALTO * 3:
        return None
    return np.frombuffer(b, np.uint8).reshape(ALTO, ANCHO, 3).astype(np.float32) / 255.0


def _alta(c):
    return (c[:-2, :-2] - 2 * c[:-2, 1:-1] + c[:-2, 2:] - 2 * c[1:-1, :-2] + 4 * c[1:-1, 1:-1] - 2 * c[1:-1, 2:]
            + c[2:, :-2] - 2 * c[2:, 1:-1] + c[2:, 2:])


def _bloques(d):
    n, m = (d.shape[0] // LADO) * LADO, (d.shape[1] // LADO) * LADO
    return d[:n, :m].reshape(n // LADO, LADO, m // LADO, LADO)


def _mitad(c):
    """La imagen a la mitad (promedio de 2x2): ahi se ve el ruido grueso, el de manchas, que deja la compresion."""
    n, m = (c.shape[0] // 2) * 2, (c.shape[1] // 2) * 2
    return c[:n, :m].reshape(n // 2, 2, m // 2, 2).mean((1, 3))


def _sigma_bloques(c):
    """Ruido por bloque de un canal, en fino y en grueso (2x y 4x). El grueso se multiplica por su escala: con ruido
    de grano fino las tres escalas dan lo mismo; con ruido de manchas (video de noche comprimido) gana la gruesa."""
    import numpy as np
    k = (np.pi / 2) ** 0.5 / 6.0
    fino = np.abs(_bloques(_alta(c))).mean((1, 3)) * k
    res, escala, lado = fino, 1, LADO
    for _ in (2, 4):
        c = _mitad(c)
        escala, lado = escala * 2, lado // 2
        a = np.abs(_alta(c))
        n, m = (a.shape[0] // lado) * lado, (a.shape[1] // lado) * lado
        g = a[:n, :m].reshape(n // lado, lado, m // lado, lado).mean((1, 3)) * k * escala
        f = min(res.shape[0], g.shape[0]), min(res.shape[1], g.shape[1])
        res = np.maximum(res[:f[0], :f[1]], g[:f[0], :f[1]])
    return res


def ruido_de_cuadro(x):
    """Ruido de una imagen RGB float (alto, ancho, 3) en 0-1: {"luz", "sombra", "color"}.
    "sombra" es el ruido de las zonas oscuras en proporcion a su luz (lo que se nota al mirar una toma de noche)."""
    import numpy as np
    y = 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
    sy = _sigma_bloques(y)
    sc = (_sigma_bloques(x[..., 2] - y) + _sigma_bloques(x[..., 0] - y)) / 2
    my = _bloques(y[1:-1, 1:-1]).mean((1, 3))[:sy.shape[0], :sy.shape[1]]
    ok = (my > 0.02) & (my < 0.90)                 # ni negro puro ni quemado: ahi el ruido esta recortado
    if ok.sum() < 50:
        ok = np.ones_like(my, bool)
    som = ok & (my < 0.30)
    r = {"luz": float(np.percentile(sy[ok], 10)), "color": float(np.percentile(sc[ok], 10))}
    if som.sum() >= 50:
        rel = REF_SOMBRA / np.maximum(PISO_SOMBRA, my[som])
        r["sombra"] = float(np.percentile(sy[som] * rel, 10))
        r["color"] = max(r["color"], float(np.percentile(sc[som] * rel, 10)))
    else:
        r["sombra"] = r["luz"]
    return r


def medir(ruta, dur=None):
    """Ruido de un video (mediana de 3 cuadros) o None si no se pudo leer."""
    dur = float(dur or 0) or 4.0
    ms = []
    for f in PUNTOS:
        x = _cuadro(ruta, max(0.1, dur * f))
        if x is not None:
            ms.append(ruido_de_cuadro(x))
    if not ms:
        return None
    return {k: round(sorted(m[k] for m in ms)[len(ms) // 2], 6) for k in ms[0]}


def _clave(ruta):
    try:
        st = os.stat(ruta)
        return "v%d|%s|%d|%d" % (VERSION, os.path.normcase(os.path.abspath(ruta)), st.st_size, int(st.st_mtime))
    except OSError:
        return None


def leer_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _guardar(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE)


# clave -> threading.Event de los videos que se estan midiendo ahora. En rutas (un solo modulo para todos): build_trailers
# carga este archivo como modulo NUEVO en cada armado (_modulo) y con un dict propio no veria lo que mide el motor
_en_curso = rutas.__dict__.setdefault("_RUIDO_EN_CURSO", {})


def _uno(t):
    """Mide un video y lo guarda en el cache (o espera si otro hilo ya lo esta midiendo). Devuelve la medida o None."""
    ruta, dur, k = t
    with _candado:
        ya = leer_cache().get(k)               # otro hilo lo termino justo antes: no se mide otra vez
        if isinstance(ya, dict):
            return ya
        ev = _en_curso.get(k)
        propio = ev is None
        if propio:
            ev = _en_curso[k] = threading.Event()
    if not propio:
        ev.wait(180)
        return leer_cache().get(k)
    try:
        m = None if rutas.PARAR.is_set() else medir(ruta, dur)
        if m:
            with _candado:
                try:
                    c = leer_cache()
                    c[k] = m
                    _guardar(c)
                except Exception:
                    pass
        return m
    finally:
        with _candado:
            _en_curso.pop(k, None)
        ev.set()


def _faltan(videos):
    cache = leer_cache()
    res, faltan = {}, []
    for ruta, dur in videos:
        k = _clave(ruta)
        if k is None:
            continue
        if isinstance(cache.get(k), dict):
            res[os.path.normcase(ruta)] = cache[k]
        elif all(k != x[2] for x in faltan):
            faltan.append((ruta, dur, k))
    return res, faltan


def adelantar(videos, hilos=2):
    """(1.8.1, MEDIDO en DaVinci: en el armado del XV, 1 + 15 min, «Midiendo el ruido» paraba 160 de 404 s) Mide en
    segundo plano, desde que empieza el armado, el ruido de los videos que se pueden usar: mientras DaVinci abre, ordena
    el media pool y escucha las voces, ya queda medido. medir_varios no repite lo que se esta midiendo: lo espera.
    Devuelve cuantos videos quedaron midiendose."""
    _, faltan = _faltan(videos)
    if not faltan:
        return 0

    def correr():
        try:
            with ThreadPoolExecutor(max_workers=max(1, int(hilos))) as ex:
                list(ex.map(_uno, faltan))
        except Exception:
            pass
    threading.Thread(target=correr, name="ruido_adelantado", daemon=True).start()
    return len(faltan)


def medir_varios(videos, log=None, hilos=4):
    """videos: [(ruta, duracion)]. Devuelve {ruta normalizada: medida}; mide solo los que no estan en el cache (los que
    ya se estan midiendo en segundo plano, los espera)."""
    res, faltan = _faltan(videos)
    if faltan:
        if log:
            log("Midiendo el ruido de %d videos..." % len(faltan))
        with ThreadPoolExecutor(max_workers=max(1, int(hilos))) as ex:
            for (ruta, _, k), m in zip(faltan, ex.map(_uno, faltan)):
                if isinstance(m, dict):
                    res[os.path.normcase(ruta)] = m
    return res


def de_ruta(ruta, dur=None):
    """Medida de un solo video (del cache, o midiendolo ahora)."""
    return medir_varios([(ruta, dur)]).get(os.path.normcase(ruta))
