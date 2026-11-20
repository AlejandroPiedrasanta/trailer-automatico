# -*- coding: utf-8 -*-
"""
caras.py - Las PERSONAS de cada foto y video con una IA propia (18-nov), sin esperar a DaVinci.

La persona (18-nov): «debería usar el 100 % de CPU o GPU para terminar luego y no lo está haciendo»; «si no lo
analizara DaVinci fuera más rápido, o sea con otra IA». El reconocimiento de personas de DaVinci (IntelliSearch) tarda
~20 min en un evento, trabaja con un solo nucleo y no se puede apurar. Esto hace lo mismo durante el analisis, con
todos los nucleos y sobre unos pocos cuadros de cada toma:

    1. detectar las caras de cada cuadro     YuNet  (recursos/modelos/face_detection_yunet_2023mar.onnx, licencia MIT)
    2. la «huella» de cada cara (128 numeros) SFace (recursos/modelos/face_recognition_sface_2021dec.onnx, Apache 2.0)
    3. agrupar las huellas parecidas          -> «Persona 1», «Persona 2»... (la 1 es la que sale en mas archivos)

Queda en el MISMO sitio y formato que lo de DaVinci (escenas_ia: personas.json, {nombre|tamaño: [personas]}), asi el
armado no nota la diferencia (aplicar_personas -> it["caras"], it["prota"]) y DaVinci ya no tiene nada que reconocer.
Solo onnxruntime + numpy + Pillow (lo que ya trae el instalador): sin OpenCV.

    reconocer(items, log)   -> {clave: [personas]} de todo el evento (lo ya visto no se repite: datos/analisis/caras.json)
    disponible()            -> estan los dos modelos y onnxruntime
"""
import os
import io
import json
import math
import time
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import rutas

VERSION = 1
LADO = 640                       # YuNet mira la imagen en 640 x 640 (se rellena con negro lo que falte)
PUNTAJE_MIN = 0.80               # confianza minima de que es una cara
ALTO_MIN = 0.045                 # la cara debe medir al menos esto del alto de la imagen (las del fondo no dicen nada)
MISMA = 0.42                     # parecido (coseno) desde el que dos huellas son la misma persona (SFace: 0,363)
CUADROS_VIDEO = 6                # cuadros que se miran de cada video (repartidos)
HILOS = max(2, min(8, (os.cpu_count() or 4) - 2))
PLANTILLA = ((38.2946, 51.6963), (73.5318, 51.5014), (56.0252, 71.7366), (41.5493, 92.3655), (70.7299, 92.2041))

_ses = {}
_candado = threading.Lock()


def _ruta(nombre):
    return os.path.join(rutas.RECURSOS, "modelos", nombre)


def disponible():
    try:
        import onnxruntime  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        return False
    return all(os.path.isfile(_ruta(f)) for f in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"))


def _sesion(nombre):
    with _candado:
        if nombre not in _ses:
            import onnxruntime as ort
            op = ort.SessionOptions()
            op.log_severity_level = 3
            op.intra_op_num_threads = 1          # el paralelo va por archivos (HILOS), no dentro de cada cara
            _ses[nombre] = ort.InferenceSession(_ruta(nombre), op, providers=["CPUExecutionProvider"])
        return _ses[nombre]


def detectar(img):
    """Caras de una imagen RGB (array alto x ancho x 3, uint8): [(x, y, ancho, alto, [5 puntos (x, y)], puntaje)]."""
    import numpy as np
    from PIL import Image
    h, w = img.shape[:2]
    esc = LADO / float(max(h, w))
    nw, nh = max(1, int(round(w * esc))), max(1, int(round(h * esc)))
    chica = np.asarray(Image.fromarray(img).resize((nw, nh), Image.BILINEAR))
    lienzo = np.zeros((LADO, LADO, 3), np.float32)
    lienzo[:nh, :nw] = chica[:, :, ::-1]                         # BGR, 0-255 (como lo pide el modelo)
    s = _sesion("face_detection_yunet_2023mar.onnx")
    sal = dict(zip([o.name for o in s.get_outputs()], s.run(None, {"input": lienzo.transpose(2, 0, 1)[None]})))
    cajas = []
    for paso in (8, 16, 32):
        cols = LADO // paso
        cls = sal["cls_%d" % paso][0, :, 0]
        obj = sal["obj_%d" % paso][0, :, 0]
        p = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        cuales = np.nonzero(p >= PUNTAJE_MIN)[0]
        if not len(cuales):
            continue
        bb, kp = sal["bbox_%d" % paso][0][cuales], sal["kps_%d" % paso][0][cuales]
        c, r = (cuales % cols).astype(np.float32), (cuales // cols).astype(np.float32)
        cx, cy = (c + bb[:, 0]) * paso, (r + bb[:, 1]) * paso
        ww, hh = np.exp(bb[:, 2]) * paso, np.exp(bb[:, 3]) * paso
        for i in range(len(cuales)):
            pts = [((kp[i, 2 * n] + c[i]) * paso / esc, (kp[i, 2 * n + 1] + r[i]) * paso / esc) for n in range(5)]
            cajas.append(((cx[i] - ww[i] / 2) / esc, (cy[i] - hh[i] / 2) / esc, ww[i] / esc, hh[i] / esc, pts, float(p[cuales[i]])))
    cajas.sort(key=lambda b: -b[5])
    out = []
    for b in cajas:                                              # una sola caja por cara (se quita la que se encima)
        if all(_encima(b, o) < 0.3 for o in out):
            out.append(b)
    return [b for b in out if b[3] >= ALTO_MIN * h]


def _encima(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return inter / max(1e-6, a[2] * a[3] + b[2] * b[3] - inter)


def _semejanza(origen, destino):
    """La transformacion (escala + giro + traslado) que lleva los puntos de origen a los de destino (Umeyama): 2 x 3."""
    import numpy as np
    a, b = np.asarray(origen, np.float64), np.asarray(destino, np.float64)
    ma, mb = a.mean(0), b.mean(0)
    da, db = a - ma, b - mb
    cov = db.T @ da / len(a)
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(2)
    if np.linalg.det(cov) < 0:
        d[-1] = -1
    rot = u @ np.diag(d) @ vt
    escala = (s * d).sum() / max(1e-9, da.var(0).sum())
    m = np.zeros((2, 3))
    m[:, :2] = escala * rot
    m[:, 2] = mb - escala * rot @ ma
    return m


def huella(img, puntos):
    """La huella (128 numeros, de largo 1) de la cara cuyos 5 puntos (ojos, nariz, boca) se dan, en la imagen RGB."""
    import numpy as np
    from PIL import Image
    pts = np.asarray(puntos, np.float64)
    m = _semejanza(pts, PLANTILLA)                               # imagen -> cara derecha de 112 x 112
    fuente = Image.fromarray(img)
    escala = math.hypot(m[0, 0], m[0, 1])
    if escala < 0.6:                 # cara grande: se achica antes con buen filtro (reducir 3-5 veces de golpe da ruido)
        f = escala / 0.9
        fuente = fuente.resize((max(1, int(round(fuente.width * f))), max(1, int(round(fuente.height * f)))), Image.LANCZOS)
        pts = pts * [fuente.width / float(img.shape[1]), fuente.height / float(img.shape[0])]
        m = _semejanza(pts, PLANTILLA)
    inv = np.linalg.inv(np.vstack([m, [0, 0, 1]]))[:2]           # PIL pide la inversa (de la cara a la imagen)
    cara = fuente.transform((112, 112), Image.AFFINE, tuple(inv.reshape(-1)), Image.BICUBIC)
    x = np.asarray(cara, np.float32).transpose(2, 0, 1)[None]    # RGB, 0-255
    v = _sesion("face_recognition_sface_2021dec.onnx").run(None, {"data": x})[0][0]
    return v / max(1e-9, float(np.linalg.norm(v)))


def _imagenes(item):
    """Los cuadros a mirar de un archivo, en RGB (arrays): la foto, o CUADROS_VIDEO repartidos del video."""
    import numpy as np
    from PIL import Image, ImageOps
    ruta = item["ruta"]
    if item.get("tipo") == "foto":
        try:
            with Image.open(ruta) as im0:
                im0.draft("RGB", (1600, 1600))
                im = ImageOps.exif_transpose(im0).convert("RGB")
            im.thumbnail((1280, 1280))
            return [np.asarray(im)]
        except Exception:
            return []
    dur = float(item.get("dur") or 0.0)
    n = 2 if dur < 4 else (4 if dur < 12 else CUADROS_VIDEO)
    out = []
    for k in range(n):
        t = dur * (k + 0.5) / n if dur > 0 else 0.0
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % t, "-i", ruta,
                                "-frames:v", "1", "-vf", "scale=960:960:force_original_aspect_ratio=decrease",
                                "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                               capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
            if r.stdout:
                out.append(np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB")))
        except Exception:
            pass
    if n and not out:
        # (1.8.0, auditoria) ningun cuadro (ffmpeg fallo o paso el plazo, disco dormido): antes quedaba guardado como
        # «nadie sale» y la festejada podia perder sus tomas para siempre; asi no se guarda y se mira otra vez
        raise RuntimeError("sin cuadros de %s" % os.path.basename(ruta))
    return out


def huellas_de(item):
    """Las huellas de las personas DISTINTAS que salen en el archivo: [[128 numeros], ...] ([] = nadie de frente)."""
    import numpy as np
    juntas = []
    for img in _imagenes(item):
        for cara in detectar(img):
            try:
                v = huella(img, cara[4])
            except Exception:
                continue
            for g in juntas:                                     # la misma persona en otro cuadro: se promedia
                if float(np.dot(g[0] / np.linalg.norm(g[0]), v)) >= MISMA:
                    g[0] += v
                    break
            else:
                juntas.append([v.copy()])
    return [[round(float(x), 4) for x in (g[0] / np.linalg.norm(g[0]))] for g in juntas]


def agrupar(por_archivo):
    """{clave: [huellas]} -> {clave: ["Persona 1", ...]}: las huellas parecidas son la misma persona en todo el evento.
    «Persona 1» es la que sale en mas archivos. Siempre da lo mismo con los mismos datos (orden fijo)."""
    import numpy as np
    todas = [(k, np.asarray(v, np.float32)) for k in sorted(por_archivo) for v in por_archivo[k]]
    centros, cuenta, de = [], [], []
    for _vuelta in range(2):                                     # la segunda vuelta, con los centros ya asentados
        de = []
        for k, v in todas:
            if centros:
                c = np.stack([x / max(1e-9, np.linalg.norm(x)) for x in centros])
                par = c @ v
                j = int(par.argmax())
                if par[j] >= MISMA:
                    if _vuelta == 0:
                        centros[j] += v
                        cuenta[j] += 1
                    de.append(j)
                    continue
            if _vuelta == 0:
                centros.append(v.copy())
                cuenta.append(1)
                de.append(len(centros) - 1)
            else:
                de.append(-1)
    archivos = {}
    for (k, _v), j in zip(todas, de):
        if j >= 0:
            archivos.setdefault(j, set()).add(k)
    orden = sorted(archivos, key=lambda j: (-len(archivos[j]), j))
    nombre = {j: "Persona %d" % (n + 1) for n, j in enumerate(orden)}
    out = {k: [] for k in por_archivo}
    for (k, _v), j in zip(todas, de):
        if j >= 0 and nombre[j] not in out[k]:
            out[k].append(nombre[j])
    return out


def _archivo():
    return os.path.join(rutas.ANALISIS, "caras.json")


def _clave(ruta):
    return "%s|%d" % (os.path.basename(ruta), os.path.getsize(ruta))


def leer():
    viajero = {}
    try:                                         # lo que viaja con el material (.trailer/caras.json)
        import escenas_ia
        viajero = escenas_ia._leer_viajero("caras.json")
    except Exception:
        pass
    try:
        with open(_archivo(), encoding="utf-8") as f:
            j = json.load(f)
        return dict(viajero, **(j.get("huellas", {}) if j.get("version") == VERSION else {}))
    except Exception:
        return viajero


def guardar_personas(items, personas):
    """Deja las personas de la IA propia donde el armado las lee (escenas_ia: personas.json y la copia que viaja con el
    material). Reemplaza lo que hubiera de DaVinci en esos archivos: los nombres deben ser de una sola fuente."""
    import escenas_ia
    cache = escenas_ia.leer_personas()
    n = 0
    for it in items:
        try:
            k = _clave(it["ruta"])
        except OSError:
            continue
        if k in personas:
            cache[k] = personas[k]
            n += 1
    escenas_ia._guardar_personas(cache)
    try:
        escenas_ia._guardar_viajero("caras.json", leer())
    except Exception:
        pass
    return n


def reconocer(items, log=print):
    """Las personas de cada archivo del evento: {clave: [personas]}. Lo ya visto (caras.json) no se vuelve a mirar."""
    if not disponible():
        return None
    guardado = leer()
    faltan, claves = [], {}
    for it in items:
        try:
            k = _clave(it["ruta"])
        except OSError:
            continue
        claves[k] = it
        if k not in guardado and not it.get("error"):
            faltan.append((k, it))
    t0 = time.time()
    if faltan:
        log("Reconociendo a las personas con la IA propia: %d fotos y %d videos (%d a la vez)…" % (
            sum(1 for _, i in faltan if i.get("tipo") == "foto"), sum(1 for _, i in faltan if i.get("tipo") != "foto"), HILOS))

        def uno(par):
            rutas.revisar_parada()
            try:
                return par[0], huellas_de(par[1])
            except rutas.Detenido:
                raise
            except Exception:
                return par[0], None
        with ThreadPoolExecutor(HILOS) as ex:
            for n, (k, h) in enumerate(ex.map(uno, faltan), 1):
                if h is not None:
                    guardado[k] = h
                if n % 100 == 0:
                    log("  personas %d/%d" % (n, len(faltan)))
        try:
            os.makedirs(rutas.ANALISIS, exist_ok=True)
            with open(_archivo() + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"version": VERSION, "huellas": guardado}, f)
            os.replace(_archivo() + ".tmp", _archivo())
        except OSError:
            pass
    personas = agrupar({k: guardado[k] for k in claves if k in guardado})
    if faltan:
        con = sum(1 for v in personas.values() if v)
        log("Personas reconocidas en %d archivos en %.0f s: %d personas distintas; sale alguien de frente en %d." % (
            len(faltan), time.time() - t0, len({p for v in personas.values() for p in v}), con))
    return personas
