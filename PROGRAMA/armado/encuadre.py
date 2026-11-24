# -*- coding: utf-8 -*-
"""
encuadre.py - (1.8.7) Acercar y centrar lo importante de un plano, con IA local.

La persona (20-nov): «la persona que habla, un par de tomas que la enfoque para dar contexto quién está hablando»;
«hay tomas aéreas que no apuntan a nada... y centra al objeto que se está grabando»; «todo debe correr en local con
inteligencia de IA muy avanzada».

  - cara(ruta, t): la cara principal del cuadro (YuNet, la misma IA local de caras.py): centro y alto, de 0 a 1.
  - sujeto_aereo(ruta, t): lo importante de una toma de dron (la iglesia, el salon, el grupo, los novios), segun la IA
    local de vision_ia (Qwen3-VL en Ollama): centro de 0 a 1, o None si no hay nada claro.
  - quien_habla(ruta, t): la cara de QUIEN HABLA: la boca que se mueve en 2 s (YuNet: comisuras y ojos) y, si no
    esta claro, la IA de vista con una cara dentro de su caja. None si no se sabe (el plano queda abierto).
  - el_sacerdote(ruta, t): en la ceremonia la voz es la del sacerdote: la IA de vista lo reconoce por la ropa y se
    toma la cara de arriba al centro de su caja.
  - acercar(fx, fy, zoom): el Pan / Tilt (pixeles de la linea) para que ese punto quede al centro con ese zoom, sin que
    se vean los bordes de la imagen. DaVinci: Pan = posicion X (derecha +), Tilt = posicion Y (arriba +).
    (MEDIDO) GetProperty devuelve Pan x alto/ancho y Tilt x ancho/alto de lo puesto, pero lo que se ve es lo puesto en
    pixeles: sin franjas negras con Tilt 181 a 1,38x (la lectura decia 322, que si las habria dejado).
Lo medido queda en datos/analisis/encuadre.json (clave archivo|tamaño|segundo): el siguiente armado no vuelve a mirar.
"""
import io
import json
import os
import subprocess
import threading

import rutas

CACHE = os.path.join(rutas.ANALISIS, "encuadre.json")
VERSION = 1
ANCHO, ALTO = 1920, 1080          # la linea horizontal de las plantillas
_candado = threading.Lock()
_cache = {}

# (1.8.7, MEDIDO) pedir «x, y de 0 a 100» daba SIEMPRE el centro (50, 50); Qwen3-VL ubica de verdad con su formato de
# cajas («bbox_2d», 0-1000, la pregunta en ingles): la iglesia [335, 49, 793, 632], los novios [462, 233, 553, 483]
FORMATO_AEREO = {"type": "object", "properties": {
    "label": {"type": "string"},
    "bbox_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}},
    "required": ["label", "bbox_2d"]}
PROMPT_AEREO = ('Locate the main subject of this drone shot of a wedding or quinceañera (the church, the venue or house, '
                'the group of people, the couple or their car). If there is only sky, ground, roofs or trees, use the '
                'label "nothing". Output JSON: {"label": "...", "bbox_2d": [x1, y1, x2, y2]} with coordinates from 0 '
                'to 1000.')
NADA = ("nothing", "sky", "ground", "roof", "trees", "tree")


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


def _guardar():
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": VERSION, "datos": _cache}, f, ensure_ascii=False, default=rutas.a_json)
        os.replace(tmp, CACHE)
    except (OSError, TypeError, ValueError):
        pass


def _clave(tipo, ruta, t):
    try:
        return "%s|%s|%d|%.1f" % (tipo, os.path.basename(ruta), os.path.getsize(ruta), round(float(t), 1))
    except OSError:
        return None


def _cuadro(ruta, t, lado=960):
    """El cuadro del segundo t, derecho (ffmpeg aplica la rotacion del celular), en JPG (bytes)."""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % max(0.0, t), "-i", ruta,
                            "-frames:v", "1", "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (lado, lado),
                            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                           capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
        return r.stdout or None
    except Exception:
        return None


def cara(ruta, t):
    """(cx, cy, alto) de 0 a 1 de la cara principal (la mas grande y segura) en el segundo t, o None."""
    k = _clave("cara", ruta, t)
    with _candado:
        c = _leer()
        if k and k in c:
            return c[k]
    res = None
    jpg = _cuadro(ruta, t)
    if jpg:
        try:
            import numpy as np
            from PIL import Image
            import caras
            img = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
            h, w = img.shape[:2]
            cajas = caras.detectar(img)
            if cajas:
                x, y, cw, ch = max(cajas, key=lambda b: b[3] * b[5])[:4]
                res = [round(float(x + cw / 2.0) / w, 4), round(float(y + ch / 2.0) / h, 4), round(float(ch) / h, 4)]
        except Exception:
            res = None
    with _candado:
        if k:
            _leer()[k] = res
            _guardar()
    return res


def sujeto_aereo(ruta, t):
    """(cx, cy) de 0 a 1 de lo importante de una toma de dron en el segundo t, o None (nada claro o sin IA)."""
    k = _clave("aereo", ruta, t)
    with _candado:
        c = _leer()
        if k and k in c:
            return c[k]
    res = None
    try:
        import base64
        import vision_ia
        modelo = vision_ia.modelo()
        if not modelo:
            return None                  # sin IA: no se guarda (se mira otra vez la proxima)
        jpg = _cuadro(ruta, t, 640)
        if jpg:
            cuerpo = {"model": modelo, "stream": False, "format": FORMATO_AEREO, "keep_alive": "10m",
                      "options": {"temperature": 0, "num_predict": 80, "num_ctx": 4096},
                      "messages": [{"role": "user", "content": PROMPT_AEREO,
                                    "images": [base64.b64encode(jpg).decode("ascii")]}]}
            d = json.loads(vision_ia._pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
            caja = [float(x) for x in (d.get("bbox_2d") or [])][:4]
            etiqueta = str(d.get("label") or "").lower()
            if len(caja) == 4 and not any(n in etiqueta for n in NADA):
                x1, y1, x2, y2 = caja
                ancho, alto = (x2 - x1) / 1000.0, (y2 - y1) / 1000.0
                if 0.0 < ancho < 0.9 and 0.0 < alto <= 1.0:          # ocupa casi todo: no hay nada que centrar
                    res = [round((x1 + x2) / 2000.0, 3), round((y1 + y2) / 2000.0, 3)]
    except Exception:
        return None                      # sin IA o fallo: no se guarda (se mira otra vez la proxima)
    with _candado:
        if k:
            _leer()[k] = res
            _guardar()
    return res


PROMPT_HABLA = ('Locate the person who is speaking in this frame of a wedding or quinceañera (the one talking, holding '
                'a microphone, reading aloud or giving a blessing). If nobody is clearly speaking, use the label '
                '"nobody". Output JSON: {"label": "...", "bbox_2d": [x1, y1, x2, y2]} with coordinates from 0 to 1000.')
NADIE = ("nobody", "none", "no one", "nothing")
BOCA_S, BOCA_FPS = 2.0, 6         # cuadros que se miran alrededor del instante (12 en 2 s)
BOCA_CARA_MIN = 0.035             # cara de al menos 3,5 % del alto (si no, la boca no se ve)
BOCA_MIN = 2.5                    # cuanto mas se mueve la boca que la frente (gris 0-255; MEDIDO: el cura 10-14,
                                  # el abuelo 4,6; el novio cabizbajo mientras hablaba otra persona, 1,8)
BOCA_MIN_CHICA = 3.5              # (1.8.7) y si la cara es chica (menos de CARA_CHICA del alto), bastante mas
CARA_CHICA = 0.07
BOCA_VENTAJA = 1.35               # y cuanto mas que la boca de la segunda cara
# (1.8.7, MEDIDO) se probo ademas que el movimiento siguiera el volumen del audio de la toma: con la musica, el eco y la
# gente, fallaba justo en los casos claros (el sacerdote, el abuelo que bendecia). Se quito.


def _cuadros(ruta, t, dur=BOCA_S, fps=BOCA_FPS, lado=960):
    """Los cuadros RGB (numpy) de `dur` segundos alrededor de t, derechos (ffmpeg aplica la rotacion del celular)."""
    import shutil
    import tempfile
    import numpy as np
    from PIL import Image
    tmp = tempfile.mkdtemp(prefix="trailer_boca_")
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % max(0.0, t - dur / 2.0),
                        "-i", ruta, "-t", "%.2f" % dur, "-vf",
                        "fps=%d,scale=%d:%d:force_original_aspect_ratio=decrease" % (fps, lado, lado),
                        "-q:v", "3", os.path.join(tmp, "c%03d.jpg")],
                       capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
        return [np.asarray(Image.open(os.path.join(tmp, f)).convert("RGB")) for f in sorted(os.listdir(tmp))]
    except Exception:
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _por_la_boca(ruta, t):
    """(1.8.7) Quien habla es quien mueve la boca: en 2 s alrededor de t, para cada cara (IA de caras, YuNet, con sus
    puntos de las comisuras y los ojos) se mide cuanto cambia la zona de la boca de un cuadro al otro MENOS cuanto
    cambia la de los ojos y la frente (asi no cuenta que la persona se mueva o que la camara tiemble). Gana la cara
    cuya boca se mueve claramente mas que las demas; una cara chica (de lejos) tiene que moverla mucho mas.
    (cx, cy, alto) de 0 a 1, o None si no esta claro."""
    import numpy as np
    import caras
    cuadros = _cuadros(ruta, t)
    if len(cuadros) < 5:
        return None
    medio = cuadros[len(cuadros) // 2]
    H, W = medio.shape[:2]
    cands = [b for b in caras.detectar(medio) or [] if b[3] / float(H) >= BOCA_CARA_MIN][:8]
    if not cands:
        return None
    grises = [c.astype(np.float32).mean(axis=2) for c in cuadros if c.shape[:2] == (H, W)]

    def cambio(x0, y0, x1, y1):
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(W, int(x1)), min(H, int(y1))
        if x1 - x0 < 3 or y1 - y0 < 3:
            return None
        return float(np.mean([np.abs(b[y0:y1, x0:x1] - a[y0:y1, x0:x1]).mean() for a, b in zip(grises, grises[1:])]))

    puntos = []
    for x, y, w, h, pts, _s in cands:
        (ojo1x, ojo1y), (ojo2x, ojo2y), _nariz, (b1x, b1y), (b2x, b2y) = pts
        ancho_b = max(abs(b2x - b1x), 0.3 * w)
        cy_b = (b1y + b2y) / 2.0
        boca = cambio(min(b1x, b2x) - 0.3 * ancho_b, cy_b - 0.35 * ancho_b, max(b1x, b2x) + 0.3 * ancho_b,
                      cy_b + 0.6 * ancho_b)
        ojos_y = min(ojo1y, ojo2y)
        frente = cambio(min(ojo1x, ojo2x) - 0.15 * w, ojos_y - 0.3 * h, max(ojo1x, ojo2x) + 0.15 * w, ojos_y + 0.08 * h)
        if boca is None or frente is None:
            continue
        puntos.append((boca - frente, float(x + w / 2.0) / W, float(y + h / 2.0) / H, float(h) / H))
    if not puntos:
        return None
    puntos.sort(reverse=True)
    mejor = puntos[0]
    segundo = puntos[1][0] if len(puntos) > 1 else 0.0
    minimo = BOCA_MIN_CHICA if mejor[3] < CARA_CHICA else BOCA_MIN
    if mejor[0] < minimo or (segundo > 0 and mejor[0] < BOCA_VENTAJA * segundo):
        return None
    return [round(mejor[1], 4), round(mejor[2], 4), round(mejor[3], 4)]


PROMPT_CURA = ('Locate the priest or minister in this frame of a wedding ceremony (the man wearing white or colored '
               'liturgical robes, usually holding a microphone or a book). If there is no priest, use the label '
               '"nobody". Output JSON: {"label": "...", "bbox_2d": [x1, y1, x2, y2]} with coordinates from 0 to 1000.')


def el_sacerdote(ruta, t):
    """(1.8.7) La cara del sacerdote (la voz de la ceremonia: el sermon, la bendicion de los anillos). Con el movimiento
    de la boca, en la entrega de anillos ganaba el novio; la IA de vista lo reconoce por la ropa (alba, estola) y la IA de
    caras da su cara dentro de esa caja. (cx, cy, alto) de 0 a 1, o None."""
    k = _clave("cura2", ruta, t)
    with _candado:
        c = _leer()
        if k and k in c:
            return c[k]
    try:
        res = _por_la_ia(ruta, t, PROMPT_CURA)
        if res is False:
            return None
    except Exception:
        return None
    with _candado:
        if k:
            _leer()[k] = res
            _guardar()
    return res


def _por_la_ia(ruta, t, prompt=None):
    """La IA local de vista (Qwen3-VL, cajas bbox_2d) dice quien habla; vale solo si dentro de su caja hay una cara
    (IA de caras): (cx, cy, alto) de esa cara, o None. Sin IA: False (no se guarda)."""
    import base64
    import vision_ia
    modelo = vision_ia.modelo()
    jpg = _cuadro(ruta, t) if modelo else None
    if not jpg:
        return False
    cuerpo = {"model": modelo, "stream": False, "format": FORMATO_AEREO, "keep_alive": "10m",
              "options": {"temperature": 0, "num_predict": 80, "num_ctx": 4096},
              "messages": [{"role": "user", "content": prompt or PROMPT_HABLA,
                            "images": [base64.b64encode(jpg).decode("ascii")]}]}
    d = json.loads(vision_ia._pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
    caja = [float(x) / 1000.0 for x in (d.get("bbox_2d") or [])][:4]
    etiqueta = str(d.get("label") or "").lower()
    if len(caja) != 4 or any(n in etiqueta for n in NADIE) or not (0.0 < caja[2] - caja[0] < 0.7):
        return None
    import numpy as np
    from PIL import Image
    import caras
    img = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
    h, w = img.shape[:2]
    x1, y1, x2, y2 = caja
    # (1.8.7, MEDIDO) la caja es la persona; su cabeza va arriba al centro. Con «la cara mas grande dentro de la caja»
    # salia la novia, que quedaba al borde de la caja del sacerdote (2 de 3)
    ox, oy = (x1 + x2) / 2.0, y1 + 0.15 * (y2 - y1)
    dentro = []
    for b in caras.detectar(img) or []:
        cx, cy = float(b[0] + b[2] / 2.0) / w, float(b[1] + b[3] / 2.0) / h
        if x1 - 0.02 <= cx <= x2 + 0.02 and y1 - 0.02 <= cy <= y2 + 0.02:
            dentro.append((abs(cx - ox) + abs(cy - oy), cx, cy, float(b[3]) / h))
    if not dentro:
        return None
    _d, cx, cy, alto = min(dentro)
    return [round(cx, 4), round(cy, 4), round(alto, 4)]


def quien_habla(ruta, t):
    """(1.8.7) (cx, cy, alto) de 0 a 1 de la cara de QUIEN HABLA en el segundo t, o None si no esta claro (entonces el
    plano no se acerca: abierto da mas contexto que una cara cualquiera). MEDIDO en NUESTRA BODA: con la cara mas
    grande del cuadro se centraba al padrino mientras hablaba el sacerdote, y la IA de vista sola, con un cuadro, no
    sabia quien bendecia. Primero la boca que se mueve (_por_la_boca); si no esta clara, la IA de vista con una cara
    dentro de su caja (_por_la_ia)."""
    k = _clave("habla5", ruta, t)
    with _candado:
        c = _leer()
        if k and k in c:
            return c[k]
    try:
        res = _por_la_boca(ruta, t)
        if res is None:
            res = _por_la_ia(ruta, t)
            if res is False:             # sin IA de vista: no se guarda (se mira otra vez la proxima)
                return None
    except Exception:
        return None
    with _candado:
        if k:
            _leer()[k] = res
            _guardar()
    return res


def acercar(fx, fy, zoom, objetivo=(0.5, 0.5), ancho=ANCHO, alto=ALTO, prop=None):
    """(pan, tilt) en pixeles para que el punto (fx, fy) (0-1, y hacia abajo) quede en `objetivo` con ese zoom, sin
    descubrir los bordes. prop: ancho / alto de la toma (1.9.1: una toma 16:9 en una linea 9:16 llena el alto y le
    sobran los lados, asi que se puede correr aunque no se acerque); sin prop, la de la linea."""
    prop = float(prop or ancho / float(alto))
    if prop >= ancho / float(alto):              # llena el alto (sobra a los lados)
        img_w, img_h = alto * prop * zoom, alto * zoom
    else:                                        # llena el ancho (sobra arriba y abajo)
        img_w, img_h = ancho * zoom, ancho / prop * zoom
    max_x = max(0.0, (img_w - ancho) / 2.0)
    max_y = max(0.0, (img_h - alto) / 2.0)
    # (1.8.7) el punto queda en 0,5 + (f - 0,5) x zoom + corrimiento: asi cae justo en `objetivo` (antes, con objetivo
    # fuera del centro, el corrimiento se multiplicaba por el zoom y la cara quedaba mas arriba de lo pedido)
    pan = (objetivo[0] - 0.5) * ancho - (fx - 0.5) * img_w
    tilt = (fy - 0.5) * img_h - (objetivo[1] - 0.5) * alto
    return (round(max(-max_x, min(max_x, pan)), 1), round(max(-max_y, min(max_y, tilt)), 1))
