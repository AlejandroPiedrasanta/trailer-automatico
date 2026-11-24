# -*- coding: utf-8 -*-
"""
vertical.py - (1.9.1) Lo grabado en HORIZONTAL dentro de una linea 9:16 (las plantillas verticales y el formato
VERTICAL): se ve la franja de lo importante, no la del centro.

La persona (22-nov): «si escojo plantillas, igual armas con lo de video en horizontal adaptado a vertical para llenar
las plantillas; pule más eso y en los videos largos hazlo mejor». Su XV 2026-11-15 no tenia ni un video vertical y en
9:16 solo entraban los verticales y el dron: las 4 plantillas salieron con 2-3 tomas de dron (20 huecos, 3 tomas).

Un 16:9 que llena el alto de un 9:16 deja ver una franja de 9/16 : 16/9 = 31,6 % de su ancho (de un 5,3K son 1681 px:
sobra para los 1080 de la linea; de un HD, 607 px: se ve blando, por eso pesa menos en el plan). Esa franja se corre:

  medir(item, ini, dur, ps, tipo)  las caras de unos cuadros del tramo (YuNet, como caras.py; del proxy si lo hay: se
                                   lee 10 veces mas rapido), cuales son de la festejada (SFace contra la huella media de
                                   su persona) y, si asi no se supo, DONDE esta ella segun la IA de vista (Qwen3-VL, una
                                   caja). MEDIDO con el XV 2026-11-15: en los planos abiertos de la fiesta su cara mide
                                   3-5 % del alto y SFace no la distingue: la franja se iba a la persona mas cercana a la
                                   camara (6 de 12 planos peor que el centro); la IA la ubico por el vestido en 7 de 7 y
                                   dijo «nadie» en el que no estaba (0,85 s por cuadro). Queda en datos/analisis/vertical.json.
  camino(medida, franja, dur)      donde va la franja: la festejada al centro; si no sale, lo principal (la IA) o las
                                   caras grandes; una cara cortada por el borde cuenta EN CONTRA (mejor fuera que a
                                   medias). Fija si todo cabe; en los planos largos (MOVER_MIN_S) que lo necesitan,
                                   sigue a la persona con un movimiento suave, como un camarografo («en los videos
                                   largos hazlo mejor»).
  pan_para(c, ...)                 el Pan de DaVinci (pixeles de la linea) para una franja fija.
  aplicar_camino(x, ...)           la franja que se mueve: un Transform de Fusion «REENCUADRE» despues del
                                   estabilizador (Fusion junta los dos Transform: se remuestrea una sola vez).
"""
import hashlib
import io
import json
import math
import os
import subprocess
import threading

import rutas

CACHE = os.path.join(rutas.ANALISIS, "vertical.json")
VERSION = 1
ANCHO_LEER = 960                  # px de ancho de los cuadros que se miran (el proxy ya viene asi)
CADA_S = 0.4                      # un cuadro cada tanto del tramo...
CUADROS_MIN, CUADROS_MAX = 3, 14  # ...entre tantos
CARA_MIN = 0.03                   # caras desde este alto (las de 3-4,5 % no las cuenta caras.py, pero cortarlas se ve)
HUELLA_MIN = 0.07                 # alto desde el que se mira QUIEN es (mas chica, SFace no la distingue)
PARECIDO_PROTA = 0.36             # coseno con la huella media de la festejada desde el que es ella (caras.MISMA = 0,42
#                                   entre dos huellas; contra una media se parece un poco menos)
PROTAS_POR_TIPO = {"boda": 2}     # como escenas_ia: en una boda, los dos novios
SFACE_BASTA = 0.5                 # si SFace la reconocio en al menos esta parte de los cuadros, no se pregunta a la IA
# (MEDIDO, VERTICAL 15 min del XV: 2,1 s por plano con dos preguntas por plano largo = 8 min para 267 planos) una sola
# pregunta por plano (a la mitad) y a ella se la sigue de cuadro en cuadro por su cara (_seguir_prota); y no se pregunta
# en las tomas donde ella no puede estar: ni SFace la vio en el archivo ni la IA del analisis la nombro
PUEDE_ESTAR = ("festejada", "novia", "novio", "vestido", "baile", "primer_baile", "beso", "votos")
IA_LENTA_S = 3.0                  # si la IA tarda mas que esto por cuadro (DaVinci lleno la tarjeta y quedo en el
#                                   procesador: 5-10 veces mas lenta), se deja y sigue con las caras
IA_PRESUPUESTO_S = 180.0          # segundos de IA por armado como mucho (lo demas, con las caras)
PESO_PROTA = 3.0                  # la festejada pesa como tres caras de su tamaño
PESO_CAJA_PROTA = 0.6             # la caja de la festejada que dio la IA (como una cara grande de ella)
PESO_CAJA_OTRO = 0.25             # la caja de lo principal cuando ella no esta
PESO_FOCO = 0.6                   # quien habla / lo que vio la IA en un dron (lo pone quien llama)
CORTE = 1.5                       # una cara a medias: suma lo que se ve de ella MENOS esto (x su peso)
CENTRADO = 0.5                    # cuanto pesa que lo principal quede al centro (contra que entre: 1)
# (1.9.1) la franja que SIGUE a la persona va en un Transform de Fusion (aplicar_camino) y no se ha visto todavia en un
# render de una linea 9:16: si DaVinci le diera al comp la imagen ya recortada al 9:16 (y no la toma entera), correrla
# descubriria bordes negros. Apagado hasta verlo en DaVinci (TRAILER_SEGUIR=1 lo prende para probar); mientras, cada
# plano va con la mejor franja FIJA para todo el plano (en la prueba con el XV, 35 de 40 planos largos igual quedaban
# fijos)
SEGUIR = os.environ.get("TRAILER_SEGUIR") == "1"
MOVER_MIN_S = 2.0                 # solo los planos de al menos esto (en la linea) pueden mover la franja
MOVER_MIN = 0.04                  # si el camino recorre menos que esto (del ancho de la toma), queda fija
MOVER_GANA = 0.12                 # y solo se mueve si asi se ve al menos un 12 % mejor que fija
VEL_MAX = 0.30                    # lo mas rapido que se corre la franja (anchos de la toma por segundo)
QUEDARSE = 2.0                    # costo de correrse (x lo corrido x el peso tipico): no salta de una cara a otra
SUAVE_S = 0.5                     # suavizado del camino (s)
PASO = 0.01                       # rejilla de posiciones de la franja (parte del ancho de la toma)

# quien es lo principal de cada tipo de evento (la pregunta va en ingles: Qwen3-VL ubica mejor asi, ver encuadre.py)
QUIEN = {"xv": "the quinceañera (the birthday girl wearing the big ball gown, sometimes with a crown)",
         "boda": "the bride and the groom (one box around both; if only one of them is in the frame, that one)",
         "bautizo": "the baby being baptized (with whoever is holding the baby)",
         "graduacion": "the graduate (wearing the cap and gown)",
         "cumpleanos": "the birthday person (the one being celebrated)"}
PROMPT = ('This frame of a {evento} video will be cropped to a vertical 9:16 video. Is {quien} in the frame? If so, set '
          '"found" to true and locate them. If not, set "found" to false and locate the main subject instead (a '
          'person speaking, people dancing, the cake, a decoration). Output JSON: {{"found": true or false, "label": '
          '"...", "bbox_2d": [x1, y1, x2, y2]}} with coordinates from 0 to 1000.')
EVENTO = {"xv": "quinceañera party", "boda": "wedding", "bautizo": "baptism", "graduacion": "graduation",
          "cumpleanos": "birthday party"}
FORMATO = {"type": "object", "properties": {
    "found": {"type": "boolean"}, "label": {"type": "string"},
    "bbox_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}},
    "required": ["found", "label", "bbox_2d"]}

_candado = threading.Lock()
_cache = {}
_protas = {}
_gasto = {"s": 0.0, "lentas": 0, "apagada": False, "preguntas": 0}


def preparar(presupuesto=IA_PRESUPUESTO_S, log=None):
    """Antes de medir un armado: la IA de vista en la GPU y con varias preguntas a la vez si se puede
    (vision_ia.en_gpu enciende el servidor propio), y el presupuesto de tiempo de IA de nuevo."""
    _gasto.update({"s": 0.0, "lentas": 0, "apagada": False, "preguntas": 0, "tope": float(presupuesto)})
    try:
        import vision_ia
        if vision_ia.modelo() and not vision_ia.en_gpu():
            _gasto["apagada"] = True              # en el procesador: 5-10 veces mas lenta; con las caras alcanza
            if log:
                log("  9:16: la IA de vista no cabe en la tarjeta (DaVinci la ocupa): se encuadra con las caras.")
    except Exception:
        pass


def puede_estar(item):
    """¿Puede salir la festejada en esta toma? (SFace la vio en el archivo o la IA del analisis la nombro)."""
    if item.get("prota") is not False:
        return True
    etiquetas = set((item.get("ia") or {}).get("etiquetas") or [])
    return not (item.get("ia") or {}).get("etiquetas") or bool(etiquetas & set(PUEDE_ESTAR))


# --------------------------------------------------------------------------------------------- lo guardado

def _leer():
    if not _cache:
        try:
            with open(CACHE, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("v") == VERSION:
                _cache.update(d.get("datos") or {})
        except (OSError, ValueError):
            pass
        _cache.setdefault("_", 1)
    return _cache


def guardar():
    """Deja en el disco lo medido (lo llama quien midio, al terminar: una escritura por armado)."""
    with _candado:
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            tmp = CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"v": VERSION, "datos": _leer()}, f, ensure_ascii=False, default=rutas.a_json)
            os.replace(tmp, CACHE)
        except (OSError, TypeError, ValueError):   # (23-nov) guardar lo medido NUNCA tumba el armado
            pass


# --------------------------------------------------------------------------------------------- quien es la festejada

def protas(items, tipo="xv"):
    """Las huellas medias (largo 1) de la festejada de ESTE evento (en una boda, los dos novios): las personas que salen
    en mas archivos, como escenas_ia.aplicar_personas. [] si no hay IA de caras o nadie sale lo bastante."""
    claves = []
    for it in items or []:
        try:
            if it.get("ruta"):
                claves.append("%s|%d" % (os.path.basename(it["ruta"]), os.path.getsize(it["ruta"])))
        except OSError:
            continue
    firma = (tipo, hashlib.sha1("\n".join(sorted(claves)).encode("utf-8")).hexdigest())
    if firma in _protas:
        return _protas[firma]
    res = []
    try:
        import caras
        if caras.disponible():
            guardado = caras.leer()
            por = {k: guardado[k] for k in claves if k in guardado}
            cs = caras.centros(por)
            orden = sorted(cs, key=lambda n: -cs[n][1])
            minimo = max(3, 0.08 * len(por))          # escenas_ia.PROTA_MINIMO
            res = [cs[n][0] for n in orden[:PROTAS_POR_TIPO.get(tipo, 1)] if cs[n][1] >= minimo]
    except Exception:
        res = []
    _protas[firma] = res
    return res


def _firma_protas(ps):
    if ps is None or not len(ps):
        return "-"
    return hashlib.sha1(b"".join(bytes(str([round(float(x), 2) for x in p[:16]]), "ascii") for p in ps)).hexdigest()[:8]


# --------------------------------------------------------------------------------------------- medir

def _fuente(item):
    """El proxy (960 x 540) si lo hay y la toma no lleva giro; si no, el original."""
    ruta = item["ruta"]
    try:
        if abs(int(float(item.get("rotacion") or 0))) % 360 == 0 and item.get("girar") in (None, 0):
            px = rutas.ruta_proxy(ruta)
            if os.path.isfile(px) and os.path.getsize(px) > 100000:
                return px
    except (OSError, ValueError, TypeError):
        pass
    return ruta


def _cuadros(ruta, ini, dur, n):
    """n cuadros RGB repartidos en [ini, ini + dur]: [(segundo, array alto x ancho x 3)]."""
    import numpy as np
    import estabilizar
    _fps, w, h = estabilizar._info(ruta)
    if not (w and h):
        return []
    alto = max(2, int(round(ANCHO_LEER * h / float(w) / 2.0)) * 2)
    tam = ANCHO_LEER * alto * 3
    datos = b""
    grande = w > 2 * ANCHO_LEER
    for gpu in ((["-hwaccel", "auto"],) if grande and estabilizar._GPU["sirve"] else ()) + ([],):
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error"] + gpu + [
                "-ss", "%.3f" % max(0.0, ini), "-t", "%.3f" % max(0.1, dur), "-i", ruta, "-an",
                "-vf", "fps=%.5f,scale=%d:%d" % (n / max(0.1, dur), ANCHO_LEER, alto),
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                capture_output=True, timeout=300, creationflags=rutas.SIN_VENTANA)
            datos = r.stdout
        except Exception:
            datos = b""
        if datos and len(datos) % tam == 0:
            break
        datos = b""
    k = len(datos) // tam if datos else 0
    if not k:
        return []
    arr = np.frombuffer(datos, np.uint8).reshape(k, alto, ANCHO_LEER, 3)
    # el filtro fps da el cuadro mas cercano a ini + i x dur / n (copias: PIL no quiere memoria de solo lectura)
    return [(ini + i * dur / float(n), arr[i].copy()) for i in range(min(k, n))]


def _ia(img, tipo):
    """Donde esta la festejada (o lo principal, si ella no sale) segun la IA de vista: [encontrada 0/1, x0, x1, y0, y1]
    (de 0 a 1), [0] si no hay nada que ubicar, o None si no hay IA (no se guarda: se mira la proxima vez)."""
    import time
    if _gasto["apagada"] or _gasto["s"] > _gasto.get("tope", IA_PRESUPUESTO_S):
        return None
    t0 = time.time()
    try:
        import base64
        import vision_ia
        from PIL import Image
        modelo = vision_ia.modelo()
        if not modelo:
            return None
        im = Image.fromarray(img)
        im.thumbnail((640, 640))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        texto = PROMPT.format(evento=EVENTO.get(tipo, "celebration"),
                              quien=QUIEN.get(tipo, "the person being celebrated"))
        cuerpo = {"model": modelo, "stream": False, "format": FORMATO, "keep_alive": "10m",
                  "options": {"temperature": 0, "num_predict": 90, "num_ctx": 4096},
                  "messages": [{"role": "user", "content": texto,
                                "images": [base64.b64encode(buf.getvalue()).decode("ascii")]}]}
        d = json.loads(vision_ia._pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
    except Exception:
        return None
    finally:
        dt = time.time() - t0
        with _candado:
            _gasto["s"] += dt
            _gasto["preguntas"] += 1
            if dt > IA_LENTA_S and _gasto["preguntas"] > 1:     # (la 1.a carga el modelo: 7 s)
                _gasto["lentas"] += 1
                if _gasto["lentas"] >= 2:
                    _gasto["apagada"] = True
    caja = [float(x) / 1000.0 for x in (d.get("bbox_2d") or [])][:4]
    if len(caja) != 4:
        return [0]
    x0, y0, x1, y1 = caja
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 0.01 or x1 - x0 >= 0.9:           # nada, o todo el cuadro: no hay que correr la franja
        return [0]
    return [int(bool(d.get("found"))), round(x0, 4), round(x1, 4), round(y0, 4), round(y1, 4)]


def _seguir_prota(res):
    """Marca como de la festejada su cara en cada cuadro: en el cuadro que miro la IA, la cara que cae en la mitad de
    arriba de su caja (no la de quien esta delante del vestido); de ahi, cuadro a cuadro hacia los dos lados, la cara
    mas cercana a donde estaba y de tamaño parecido (asi una sola pregunta sirve para todo el plano)."""
    cajas = [(t, c) for t, c in res.get("ia") or [] if c and c[0] == 1 and len(c) == 5]
    if not cajas:
        return
    ts, filas = res["t"], res["caras"]
    for tc, c in cajas:
        i = min(range(len(ts)), key=lambda k: abs(ts[k] - tc))
        x0, x1, y0, y1 = c[1], c[2], c[3], c[4]
        dentro = [f for f in filas[i] if x0 - 0.03 <= f[0] <= x1 + 0.03 and y0 - 0.05 <= f[3] <= y0 + (y1 - y0) * 0.55]
        if not dentro:
            continue
        ancla = max(dentro, key=lambda f: f[4])
        ancla[5] = 1
        for paso in (1, -1):                         # hacia adelante y hacia atras
            prev, t_prev, k = ancla, ts[i], i + paso
            while 0 <= k < len(ts):
                dt = abs(ts[k] - t_prev)
                if dt > 1.6:                         # perdida mas de 1,6 s (se giro, alguien delante): hasta ahi
                    break
                cerca = [f for f in filas[k] if abs(f[0] - prev[0]) <= 0.06 + 0.15 * dt
                         and 0.6 <= f[4] / max(1e-4, prev[4]) <= 1.6]
                if cerca:
                    f = min(cerca, key=lambda g: abs(g[0] - prev[0]))
                    f[5] = 1
                    prev, t_prev = f, ts[k]
                k += paso


def medir(item, ini, dur, ps=(), tipo="xv", ia=True):
    """Lo que hay en el tramo [ini, ini + dur] de la toma: {"t": [segundos], "caras": [[[cx, x0, x1, cy, alto, prota],
    ...] por cuadro] (de 0 a 1 de la imagen; prota 1 si es la festejada), "ia": [[segundo, caja de _ia()], ...]}, o
    None si no se pudo leer."""
    if not item.get("ruta"):
        return None
    n = max(CUADROS_MIN, min(CUADROS_MAX, int(round(dur / CADA_S)) + 1))
    try:
        k = "%s|%d|%.2f|%.2f|%d|%s|%s|%d" % (os.path.basename(item["ruta"]), os.path.getsize(item["ruta"]), ini, dur,
                                             n, _firma_protas(ps), tipo, int(bool(ia)))
    except OSError:
        return None
    with _candado:
        c = _leer()
        if k in c:
            return c[k]
    try:
        import numpy as np
        import caras
        cuadros = _cuadros(_fuente(item), ini, dur, n)
        if not cuadros:
            return None
        con_caras = caras.disponible()
        res = {"t": [], "caras": [], "ia": []}
        for t, img in cuadros:
            h, w = img.shape[:2]
            fila = []
            for x, y, cw, ch, pts, _p in (caras.detectar(img, CARA_MIN) if con_caras else []):
                prota = 0
                if ps is not None and len(ps) and ch >= HUELLA_MIN * h:
                    try:
                        v = caras.huella(img, pts)
                        prota = int(max(float(np.dot(v, p)) for p in ps) >= PARECIDO_PROTA)
                    except Exception:
                        prota = 0
                # (23-nov, VISTO en el registro: «Object of type float32 is not JSON serializable» tumbo el 9:16 y las 4
                # plantillas) caras.detectar da numeros de numpy y round() los deja de numpy: float() antes de guardar
                x, y, cw, ch = float(x), float(y), float(cw), float(ch)
                fila.append([round((x + cw / 2.0) / w, 4), round(max(0.0, x) / w, 4), round(min(w, x + cw) / w, 4),
                             round((y + ch / 2.0) / h, 4), round(ch / float(h), 4), prota])
            res["t"].append(round(float(t), 3))
            res["caras"].append(fila)
        reconocida = sum(1 for f in res["caras"] if any(c[5] for c in f))
        todas = [c for f in res["caras"] for c in f]
        caben = bool(todas) and max(c[2] for c in todas) - min(c[1] for c in todas) <= ventana_tipica(item)
        sin_ia = False
        # la IA solo si hace falta: ni SFace supo quien es ella ni las caras caben todas en la franja (hay que
        # elegir), o no hay caras (puede que ella este de espaldas, lejos); y solo si ella puede estar en esa toma
        if ia and reconocida < SFACE_BASTA * len(cuadros) and not caben and puede_estar(item):
            i = len(cuadros) // 2                     # una pregunta, a la mitad; _seguir_prota hace el resto
            caja = _ia(cuadros[i][1], tipo)
            if caja is None:
                sin_ia = True                         # sin IA (o sin tiempo): lo de las caras y no se guarda
            else:
                res["ia"].append([round(cuadros[i][0], 3), caja])
                _seguir_prota(res)
    except Exception:
        return None
    if not sin_ia:
        with _candado:
            _leer()[k] = res
    return res


# --------------------------------------------------------------------------------------------- donde va la franja

def franja(w, h, ancho=1080, alto=1920, zoom=1.0):
    """Que parte del ancho de una toma w x h se ve en una linea ancho x alto que llena (y acercada `zoom`)."""
    if not (w and h) or w / float(h) <= ancho / float(alto):
        return 1.0
    return (ancho / float(alto)) / (w / float(h)) / max(1.0, zoom)


def ventana_tipica(item):
    """La franja de esa toma en un 9:16, con un poco de margen (para decidir si hace falta preguntar a la IA)."""
    try:
        w, h = float(item.get("ancho") or 16), float(item.get("alto") or 9)
    except (TypeError, ValueError):
        w, h = 16.0, 9.0
    return franja(max(w, h), min(w, h)) * 0.9


def _rejilla(fr):
    import numpy as np
    lo, hi = fr / 2.0, 1.0 - fr / 2.0
    if hi - lo < PASO:
        return np.array([0.5])
    return np.linspace(lo, hi, int(math.ceil((hi - lo) / PASO)) + 1)


def _caja_en(medida, t):
    """La caja de la IA mas cercana en el tiempo (a menos de 1,5 s) o None."""
    cajas = [(tc, c) for tc, c in (medida or {}).get("ia") or [] if c and len(c) == 5]
    if not cajas:
        return None
    tc, c = min(cajas, key=lambda x: abs(x[0] - t))
    return c if abs(tc - t) <= 1.5 else None


def _puntaje(caras_c, cs, fr, caja=None, foco=None):
    """Lo bien que se ve este cuadro con la franja en cada posicion cs: cada cara entera suma su peso (alto; x3 la
    festejada), una a medias resta; la caja de la IA (ella o lo principal) suma lo que entra de ella; y lo principal
    (su cara > su caja > el foco de quien llama > la cara mas grande > la caja) quiere estar al centro."""
    import numpy as np
    s = np.zeros(len(cs))
    a, b = cs - fr / 2.0, cs + fr / 2.0

    def entra(x0, x1, base):
        return np.clip((np.minimum(b, x1) - np.maximum(a, x0)) / max(1e-4, base), 0.0, 1.0)
    principal = None
    for cx, x0, x1, _cy, alto, prota in caras_c:
        w = alto * (PESO_PROTA if prota else 1.0)
        o = entra(x0, x1, x1 - x0)
        s += w * np.where(o >= 0.97, 1.0, np.where(o <= 0.03, 0.0, o - CORTE))
        rango = 3 if prota else 1
        if principal is None or (rango, w) > (principal[2], principal[1]):
            principal = (cx, w, rango)
    otros = []
    if caja is not None:
        x0, x1 = caja[1], caja[2]
        w = PESO_CAJA_PROTA if caja[0] == 1 else PESO_CAJA_OTRO
        s += w * entra(x0, x1, min(x1 - x0, fr))
        otros.append(((x0 + x1) / 2.0, w, 2 if caja[0] == 1 else 1.5))    # lo principal de la IA > una cara suelta
    if foco is not None:
        fx = float(foco[0])
        fw = max(0.03, float(foco[2]) * 0.6) if len(foco) > 2 and foco[2] else 0.05
        s += PESO_FOCO * entra(fx - fw / 2.0, fx + fw / 2.0, fw)
        otros.append((fx, PESO_FOCO, 2.5))
    for o in otros:
        if principal is None or (o[2], o[1]) > (principal[2], principal[1]):
            principal = o
    if principal is not None:
        s -= CENTRADO * principal[1] * np.minimum(1.0, np.abs(cs - principal[0]) / (fr / 2.0)) ** 2
    return s


def camino(medida, fr, dur_linea, foco=None, mover=True):
    """Donde va la franja (centro, de 0 a 1 del ancho de la toma): {"fija": c} o {"t": [s], "c": [centros]} (se
    mueve), o None si no hay nada que mirar (sin caras, caja ni foco: queda al centro). fr = franja(); dur_linea = lo
    que dura el plano en la linea (los cortos nunca se mueven: un plano de 1 s que se corre se ve nervioso)."""
    import numpy as np
    if fr >= 0.999:
        return None
    ts = list((medida or {}).get("t") or [])
    filas = list((medida or {}).get("caras") or [])
    if not ts:
        ts, filas = [0.0], [[]]
    cajas = [_caja_en(medida, t) for t in ts]
    if not any(filas) and not any(cajas) and foco is None:
        return None
    cs = _rejilla(fr)
    S = np.stack([_puntaje(f, cs, fr, c, foco) for f, c in zip(filas, cajas)])      # cuadros x posiciones
    total = S.sum(0)
    fija = float(cs[int(total.argmax())])
    if not (mover and SEGUIR and dur_linea >= MOVER_MIN_S and len(ts) >= 3):
        return {"fija": round(fija, 4)}
    # el camino que mejor se ve, con un costo por correrse y una velocidad maxima (programacion dinamica)
    escala = max(1e-3, float(np.mean(S.max(1))))
    d = np.abs(cs[:, None] - cs[None, :])
    mejor, atras = S[0].copy(), []
    for k in range(1, len(ts)):
        dt = max(0.05, ts[k] - ts[k - 1])
        paso = np.where(d <= VEL_MAX * dt + 1e-9, -QUEDARSE * escala * d, -np.inf)
        cand = mejor[None, :] + paso
        j = cand.argmax(1)
        mejor = cand[np.arange(len(cs)), j] + S[k]
        atras.append(j)
    i = int(mejor.argmax())
    idx = [i]
    for j in reversed(atras):
        i = int(j[i])
        idx.append(i)
    idx.reverse()
    cam = np.array([cs[i] for i in idx])
    valor_mov = float(sum(S[k, idx[k]] for k in range(len(ts))))
    valor_fijo = float(total.max())
    if cam.max() - cam.min() < MOVER_MIN or valor_mov < valor_fijo + MOVER_GANA * max(abs(valor_fijo), escala):
        return {"fija": round(fija, 4)}
    # suave: gaussiana sobre los cuadros medidos (con los bordes repetidos), sin pasar de los limites
    sig = max(0.5, SUAVE_S / max(0.05, (ts[-1] - ts[0]) / max(1, len(ts) - 1)))
    r = int(math.ceil(3 * sig))
    pad = np.concatenate([[cam[0]] * r, cam, [cam[-1]] * r])
    ker = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    suave = np.clip(np.convolve(pad, ker / ker.sum(), mode="valid"), cs[0], cs[-1])
    return {"t": [round(float(t), 3) for t in ts], "c": [round(float(c), 4) for c in suave]}


def centro_medio(cam):
    """El centro de la franja (fija, o el promedio si se mueve), o 0,5."""
    if not cam:
        return 0.5
    if "fija" in cam:
        return float(cam["fija"])
    c = cam.get("c") or [0.5]
    return sum(c) / float(len(c))


def en(cam, t):
    """El centro de la franja en el segundo t de la toma (interpolado)."""
    if not cam:
        return 0.5
    if "fija" in cam:
        return float(cam["fija"])
    ts, cs = cam["t"], cam["c"]
    if t <= ts[0]:
        return cs[0]
    if t >= ts[-1]:
        return cs[-1]
    for k in range(1, len(ts)):
        if t <= ts[k]:
            f = (t - ts[k - 1]) / max(1e-6, ts[k] - ts[k - 1])
            return cs[k - 1] * (1 - f) + cs[k] * f
    return cs[-1]


def resumen(cams):
    """«12 planos: 7 en la festejada...» para el registro: cuantos fijos, cuantos se mueven y cuantos al centro."""
    fijos = sum(1 for c in cams if c and "fija" in c and abs(c["fija"] - 0.5) >= 0.01)
    mueven = sum(1 for c in cams if c and "fija" not in c)
    return "%d corridos a lo importante, %d siguiendo a la persona, %d al centro" % (fijos, mueven,
                                                                                     len(cams) - fijos - mueven)


# --------------------------------------------------------------------------------------------- en DaVinci

def pan_para(c, w, h, ancho=1080, alto=1920, zoom=1.0, zs=1.0):
    """El Pan (pixeles de la linea; derecha +) para que se vea la franja con centro c (de 0 a 1 de la toma) de una
    toma w x h que llena la linea (acercada `zoom` en DaVinci y `zs` por el estabilizador), sin descubrir bordes."""
    img_w = alto * (w / float(h)) * max(1.0, zoom)
    pan = (0.5 - c) * zs * img_w
    tope = max(0.0, (img_w - ancho) / 2.0)
    return round(max(-tope, min(tope, pan)), 1)


def aplicar_camino(x, cam, fps_linea, ini, vel=1.0, zs=1.0, zoom=1.0, fr=None, log=None):
    """La franja que se mueve: un Transform de Fusion «REENCUADRE» (Center X con un keyframe por cuadro) detras de lo
    que ya llegue a MediaOut (el estabilizador). Cada cuadro del comp avanza vel / fps_linea segundos de la toma (como
    estabilizar.aplicar). Va ANTES del primer render del clip. True si quedo."""
    try:
        comp = x.GetFusionCompByIndex(1) if x.GetFusionCompCount() else None
        comp = comp or x.AddFusionComp()
    except Exception:
        comp = None
    if comp is None:
        return False
    tope = 0.5 - (fr or 0.0) / 2.0 / max(1.0, zoom) - 0.01        # sin descubrir los bordes de la toma
    comp.Lock()
    try:
        mi, mo = comp.FindTool("MediaIn1"), comp.FindTool("MediaOut1")
        if mi is None or mo is None:
            return False
        tr = comp.FindTool("REENCUADRE")
        if tr is None:
            tr = comp.AddTool("Transform", -32768, -32768)
            tr.SetAttrs({"TOOLS_Name": "REENCUADRE"})
            antes = mo.Input.GetConnectedOutput()
            tr.ConnectInput("Input", antes.GetTool() if antes is not None else mi)
            mo.ConnectInput("Input", tr)
        at = comp.GetAttrs() or {}
        f0 = int(at.get("COMPN_RenderStart", 0) or 0)
        f1 = f0 + int(x.GetDuration() or 0) + 1
        base = f0
        tr.Center = comp.XYPath()
        camino_xy = tr.Center.GetConnectedOutput().GetTool()
        camino_xy.X = comp.BezierSpline()
        camino_xy.Y = comp.BezierSpline()
        kx, ky = {}, {}
        for f in range(f0 - 2, f1 + 1):
            c = en(cam, ini + (f - base) * vel / float(fps_linea))
            dx = max(-tope, min(tope, (0.5 - c) * zs))
            kx[f] = {1: 0.5 + dx}                 # Fusion: x hacia la derecha
            ky[f] = {1: 0.5}
        for entrada, keys in ((camino_xy.X, kx), (camino_xy.Y, ky)):
            entrada.GetConnectedOutput().GetTool().SetKeyFrames(keys, True)
        return True
    except Exception as ex:
        if log:
            log("Aviso: no se pudo mover el encuadre vertical (%s)" % ex)
        return False
    finally:
        comp.Unlock()
