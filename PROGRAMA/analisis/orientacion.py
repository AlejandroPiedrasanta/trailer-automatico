# -*- coding: utf-8 -*-
"""
orientacion.py - (1.8.7) Cuanto hay que girar una toma para que se vea DERECHA, mirando lo que se ve, no lo que dice el
archivo.

La persona (22-nov): «verifica que no haya tomas al revés, ya vi algunas, que la IA reconozca eso».
MEDIDO en NUESTRA BODA: el celular marca mal la rotacion cuando arranca a grabar casi plano. Con la rotacion del archivo
aplicada (como la muestra DaVinci):
  - HORIZONTAL 024/045/056/060/088 (marcan -180) salen DE CABEZA (el archivo crudo esta derecho);
  - VERTICAL 018/019/024/025 (marcan +90) salen DE LADO (son tomas horizontales derechas); la IA del analisis las vio
    «de cabeza» y las descarto: tomas buenas de la ceremonia perdidas.
Antes se giraba 180 todo lo que marcaba -180 (bien aqui, pero un archivo bien marcado habria quedado de cabeza).

medir(ruta, dur) mira 5 cuadros tal como se ven (ffmpeg aplica la rotacion del archivo, igual que DaVinci) y busca
caras (YuNet, la IA local de caras.py) en las 4 rotaciones: gana la que muestra caras derechas de verdad. Sin caras
(aereas, detalles), la IA de vista (Qwen3-VL) dice si se ve derecha, de cabeza o de lado.
Devuelve {"girar": 0 | 90 | 180 | 270 | None, "como": "caras" | "ia", "fuerza": [4 numeros]}: los grados que hay que
girar la imagen EN SENTIDO ANTIHORARIO (numpy.rot90) para verla derecha. None = no se sabe (se deja como esta).
Queda en datos/analisis/orientacion.json (clave archivo|tamaño).
"""
import io
import json
import os
import subprocess
import threading

import rutas

CACHE = os.path.join(rutas.ANALISIS, "orientacion.json")
VERSION = 2
CUADROS = 5
LADO = 640
CARA_MIN = 0.7                   # puntaje de YuNet para contar una cara
VENTAJA = 2.5                    # la rotacion ganadora tiene que tener esto mas caras que la que sigue
FUERZA_CUADRO = 3.0              # minimo de evidencia en un cuadro (suma de alto x puntaje de sus caras, en %)
GIRO_VOTOS = 3                   # cuadros (de CUADROS) que tienen que ver la toma girada para girarla
_candado = threading.Lock()
_cache = {}

FORMATO = {"type": "object", "properties": {"orientation": {"type": "string",
                                                             "enum": ["upright", "upside_down", "rotated_left",
                                                                      "rotated_right"]}},
           "required": ["orientation"]}
PROMPT = ('This is a frame from a wedding or quinceañera video. Is the image shown upright, upside down, or rotated '
          'sideways? "rotated_left" means the top of the scene points to the left edge; "rotated_right" means it '
          'points to the right edge. Look at people, the floor, the ceiling, lamps and text. Answer JSON: '
          '{"orientation": "upright" | "upside_down" | "rotated_left" | "rotated_right"}')
# grados antihorarios que hay que girar la imagen para verla derecha
GIRO_IA = {"upright": 0, "upside_down": 180, "rotated_left": 270, "rotated_right": 90}


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
            json.dump({"v": VERSION, "datos": _cache}, f, ensure_ascii=False)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def _clave(ruta):
    try:
        return "%s|%d" % (os.path.basename(ruta), os.path.getsize(ruta))
    except OSError:
        return None


def _cuadro(ruta, t):
    """El cuadro del segundo t COMO SE VE (ffmpeg aplica la rotacion del archivo, como DaVinci), en RGB numpy."""
    import numpy as np
    from PIL import Image
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % max(0.0, t), "-i", ruta,
                            "-frames:v", "1", "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (LADO, LADO),
                            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                           capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
        if not r.stdout:
            return None
        return np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB"))
    except Exception:
        return None


def _fuerza(img):
    """Evidencia de caras DERECHAS en la imagen: suma de alto (% del cuadro) x puntaje de las caras seguras."""
    import caras
    h = float(img.shape[0])
    return float(sum(100.0 * float(b[3]) / h * float(b[5]) for b in caras.detectar(img) or [] if b[5] >= CARA_MIN))


def _por_ia(img):
    """La IA de vista: grados antihorarios para verla derecha, o None."""
    try:
        import base64
        import vision_ia
        from PIL import Image
        modelo = vision_ia.modelo()
        if not modelo:
            return None
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG", quality=85)
        cuerpo = {"model": modelo, "stream": False, "format": FORMATO, "keep_alive": "10m",
                  "options": {"temperature": 0, "num_predict": 30, "num_ctx": 4096},
                  "messages": [{"role": "user", "content": PROMPT,
                                "images": [base64.b64encode(buf.getvalue()).decode("ascii")]}]}
        d = json.loads(vision_ia._pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
        return GIRO_IA.get(str(d.get("orientation") or ""))
    except Exception:
        return None


def medir(ruta, dur, usar_ia=True):
    """{"girar", "como", "fuerza"} de la toma (ver arriba). Lo medido queda guardado."""
    import numpy as np
    k = _clave(ruta)
    with _candado:
        c = _leer()
        if k and k in c:
            return c[k]
    dur = float(dur or 0.0)
    tiempos = [dur * (i + 0.5) / CUADROS for i in range(CUADROS)] if dur > 1.0 else [0.0]
    imgs = [x for x in (_cuadro(ruta, t) for t in tiempos) if x is not None]
    res = {"girar": None, "como": "", "fuerza": [0.0] * 4, "votos": []}
    if imgs:
        # (MEDIDO) sumando las caras de los 5 cuadros, YuNet veia «caras» en flores y adornos girados (ramo y zapatos
        # del 009, maquillaje del 001 / 002: derechos): ahora cada cuadro vota y un giro necesita 3 votos de 5 y que la
        # IA de vista lo confirme; «derecha» (0) basta con la mayoria de los que tienen caras
        fuerza, votos = [0.0] * 4, []
        for img in imgs:
            f = [_fuerza(np.ascontiguousarray(np.rot90(img, q))) for q in range(4)]   # q x 90 grados antihorarios
            fuerza = [a + b for a, b in zip(fuerza, f)]
            orden = sorted(range(4), key=lambda q: -f[q])
            if f[orden[0]] >= FUERZA_CUADRO and f[orden[0]] >= VENTAJA * max(f[orden[1]], 0.5):
                votos.append(orden[0] * 90)
        res["fuerza"] = [round(float(f), 1) for f in fuerza]          # (numpy no va a JSON)
        res["votos"] = votos
        gana = max(set(votos), key=votos.count) if votos else None
        if gana == 0 and votos.count(0) > len(votos) / 2.0:
            res.update(girar=0, como="caras")
        elif gana and votos.count(gana) >= GIRO_VOTOS and votos.count(gana) > len(votos) / 2.0:
            if not usar_ia:
                res.update(girar=gana, como="caras")
            else:                                     # la IA de vista tiene que ver lo mismo en los cuadros con caras
                ia = [g for g in (_por_ia(img) for img in imgs[:3]) if g is not None]
                if ia.count(gana) >= 2:
                    res.update(girar=gana, como="caras+ia")
        elif usar_ia and not votos:
            # sin caras claras (aereas, detalles): la IA de vista en 3 cuadros; vale si al menos 2 coinciden
            ia = [g for g in (_por_ia(img) for img in imgs[:3]) if g is not None]
            gana = max(set(ia), key=ia.count) if ia else None
            if gana is not None and ia.count(gana) >= 2:
                res.update(girar=gana, como="ia")
    with _candado:
        if k:
            _leer()[k] = res
            _guardar()
    return res
