# -*- coding: utf-8 -*-
"""
estabilizar.py - (16-nov) Estabilizador propio: quita el temblor, conserva los paneos y acerca lo MINIMO.

La persona (2026-11-16): «hay tomas que no apuntan a nada, tal vez el error es al estabilizarlo, que se arruina la toma
ya que esta muy movida»; y luego, con un script de Fusion de otro autor («Stabilize Tracker Transform»): «mira esta
opcion para estabilizar en Fusion… ¿sirve, o mejor crea algo mejor tu?». Ese script es manual (en cada toma hay que
poner el tracker o dibujar una forma) y su licencia no deja incluirlo en otro programa; este hace lo mismo SOLO, en
cada plano del armado:

1. MIDE el movimiento cuadro a cuadro del tramo que usa el plano (y medio segundo antes y despues): la imagen chica
   en gris (ffmpeg), partida en 12 tejas; en cada teja, correlacion de fase (FFT) -> cuanto se movio; con las 12 se
   ajusta un movimiento de camara (desplazamiento + giro) y se descartan las tejas que no concuerdan (la gente que
   baila o cruza no arrastra la medida).
2. SEPARA el temblor del movimiento que la camara queria hacer: el camino de la camara se suaviza (gaussiana de
   ~1 s; un paneo parejo pasa entero y uno brusco queda suave) y la correccion es «camino suave - camino real».
3. ZOOM MINIMO: el acercamiento justo para que la correccion no deje ver bordes. Si pasa de ZOOM_MAX, se suaviza menos
   (se sigue mas a la camara) y, si aun asi no alcanza, se corrige solo una parte. Nunca deforma la imagen (solo
   mueve, gira y acerca: sin perspectiva).
4. Se APLICA en DaVinci como un Transform de Fusion («ESTABILIZADOR») en el clip, con un keyframe por cuadro: se ve,
   se puede retocar o apagar en la pagina Fusion, y no crea archivos nuevos.

calcular(ruta, ini, dur, ...) -> {"t0", "fps", "cx", "cy", "ang", "zoom", "antes", "despues"} o None
aplicar(item, corr, fps_linea, ini, vel) -> True si quedo puesto
"""
import os
import json
import math
import subprocess

import numpy as np

import rutas

ANCHO = 384                   # px de ancho de la imagen con que se mide (alto proporcional)
TEJAS = (4, 3)                # columnas x filas de tejas para la correlacion de fase
PICO_MIN = 0.06               # una teja sin un pico claro (pared lisa, cielo) no vota
MARGEN_S = 0.5                # se mide un poco antes y despues del plano: el suavizado no se tuerce en los bordes
# (19-nov, la persona: «pule más la estabilidad») primero 1,6 s (casi de tripode); si el zoom no alcanza, mas suelto
SUAVES_S = (1.6, 1.0, 0.6, 0.35)   # suavizado (s) que se prueba, de mas firme a mas suelto, hasta que el zoom alcance
ZOOM_MAX = 1.08               # nunca se acerca mas que esto en tomas HD (se notaria)
ZOOM_MAX_4K = 1.18            # (19-nov) en tomas de 4K o mas la linea es HD: sobra resolucion, acercar 18 % no se nota
ANCHO_4K = 3000               # px del lado mayor desde el que una toma cuenta como 4K
GIRO_MAX = 3.0                # grados de giro que se corrigen como mucho


_GPU = {"sirve": True, "fallos": 0}


_INFO = {}


def _info(ruta):
    """(1.8.0, auditoria) fps, ancho y alto (ya girados) de la toma con UN ffprobe por archivo: antes eran 3 por plano
    (122 ms cada uno, ~0,37 s de los ~0,61 s que tarda estabilizar un plano)."""
    if ruta in _INFO:
        return _INFO[ruta]
    d = {}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,avg_frame_rate:stream_side_data=rotation", "-of", "default=nw=1",
                            ruta], capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        for linea in r.stdout.splitlines():
            k, _, v = linea.partition("=")
            d.setdefault(k.strip(), v.strip())
    except Exception:
        pass
    try:
        a, _, b = (d.get("avg_frame_rate") or "30/1").partition("/")
        fps = float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    try:
        w, h = int(d["width"]), int(d["height"])
        if abs(int(float(d.get("rotation", 0) or 0))) % 180 == 90:
            w, h = h, w
    except (KeyError, ValueError):
        w = h = 0
    if w and h:                       # un fallo pasajero (disco dormido) no queda guardado
        _INFO[ruta] = (fps, w, h)
    return fps, w, h


def leer(ruta, ini, dur, ancho=ANCHO):
    """Los cuadros del tramo, en gris y chicos: (array n x alto x ancho uint8, fps) o (None, fps)."""
    fps = _info(ruta)[0]
    if not (5.0 <= fps <= 240.0):
        fps = 30.0
    # (18-nov, la persona: «mejora el proceso en paralelo con GPU al 100») leer el tramo era lo mas lento del armado
    # (0,70 s por plano decodificando 4K con el procesador); con la tarjeta de video, 0,33 s. Si la GPU no puede con
    # ese archivo (o no hay), sale vacio y se lee con el procesador como antes.
    # (19-nov) el alto se fija aqui: con «-2» ffmpeg redondeaba distinto (682 contra 684 en los 4K girados) y
    # ninguna toma vertical se media
    alto = _alto(ruta, ancho)
    if not alto:
        return None, fps
    datos = b""
    for gpu in ((["-hwaccel", "auto"],) if _GPU["sirve"] else ()) + ([],):
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error"] + gpu + [
                                "-ss", "%.3f" % max(0.0, ini), "-t", "%.3f" % dur, "-i", ruta, "-an",
                                "-vf", "scale=%d:%d,format=gray" % (ancho, alto), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                               capture_output=True, timeout=300, creationflags=rutas.SIN_VENTANA)
            datos = r.stdout
        except Exception:
            datos = b""
        if datos:
            break
        if gpu:
            _GPU["fallos"] += 1
            if _GPU["fallos"] >= 3:          # esta PC no decodifica con la tarjeta: no se insiste
                _GPU["sirve"] = False
    if not datos:
        return None, fps
    if len(datos) % (ancho * alto):
        return None, fps
    n = len(datos) // (ancho * alto)
    return np.frombuffer(datos, np.uint8).reshape(n, alto, ancho), fps


def _alto(ruta, ancho):
    _, w, h = _info(ruta)
    if not (w and h):
        return None
    alto = int(round(ancho * h / float(w)))
    return alto + (alto % 2)


def _ventana(h, w):
    return np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)


def _subpixel(r, py, px):
    """Pico con decimales (parabola en cada eje)."""
    h, w = r.shape

    def eje(m, c, p):
        d = m - 2.0 * c + p
        return 0.0 if abs(d) < 1e-9 else 0.5 * (m - p) / d
    dy = eje(r[(py - 1) % h, px], r[py, px], r[(py + 1) % h, px])
    dx = eje(r[py, (px - 1) % w], r[py, px], r[py, (px + 1) % w])
    return py + dy, px + dx


def _corr_fase(fa, fb, forma):
    """Cuanto se movio el contenido de la teja b respecto de la a: (dx, dy, pico)."""
    R = fb * np.conj(fa)
    R /= np.abs(R) + 1e-9
    r = np.fft.irfft2(R, s=forma)
    k = int(np.argmax(r))
    py, px = divmod(k, forma[1])
    pico = float(r[py, px])
    y, x = _subpixel(r, py, px)
    if y > forma[0] / 2.0:
        y -= forma[0]
    if x > forma[1] / 2.0:
        x -= forma[1]
    return x, y, pico


def _tejas(h, w):
    """[(y0, y1, x0, x1, cy, cx)] de cada teja (centro relativo al centro de la imagen)."""
    cols, filas = TEJAS
    th, tw = h // filas, w // cols
    out = []
    for i in range(filas):
        for j in range(cols):
            y0, x0 = i * th, j * tw
            out.append((y0, y0 + th, x0, x0 + tw, y0 + th / 2.0 - h / 2.0, x0 + tw / 2.0 - w / 2.0))
    return out


def _ajustar(c, u, peso):
    """Movimiento de camara (tx, ty, giro en radianes) que mejor explica los desplazamientos u de las tejas con centro
    c (minimos cuadrados con pesos; giro pequeno: u = t + giro x (-y, x)). Quita las tejas que no concuerdan."""
    usar = peso > 0
    sol = (0.0, 0.0, 0.0)
    for _ in range(3):
        if usar.sum() < 4:
            return None
        cy, cx = c[usar, 0], c[usar, 1]
        n = len(cx)
        A = np.zeros((2 * n, 3))
        b = np.zeros(2 * n)
        A[:n, 0], A[:n, 2], b[:n] = 1.0, -cy, u[usar, 0]
        A[n:, 1], A[n:, 2], b[n:] = 1.0, cx, u[usar, 1]
        W = np.sqrt(np.concatenate([peso[usar], peso[usar]]))
        x, *_ = np.linalg.lstsq(A * W[:, None], b * W, rcond=None)
        sol = (float(x[0]), float(x[1]), float(x[2]))
        pred = np.stack([sol[0] - sol[2] * c[:, 0], sol[1] + sol[2] * c[:, 1]], axis=1)
        res = np.hypot(*(u - pred).T)
        lim = max(0.75, 2.5 * float(np.median(res[usar])))
        nuevo = usar & (res <= lim)
        if nuevo.sum() == usar.sum():
            break
        usar = nuevo
    return sol


def _puntos(cuadros):
    """(19-nov, la persona: «busca IAs para estabilizar las tomas movidas, mejora ese flujo») El movimiento siguiendo
    puntos (OpenCV: esquinas + Lucas-Kanade + RANSAC, lo que usan vidstab y Gyroflow sin giroscopio): la gente que se
    mueve queda fuera del ajuste. Medido en las 14 tomas mas movidas de la boda, con jueces independientes (flujo
    denso DIS y el propio LK): quita 44 % / 94 % del temblor contra 40 % / 33 % de las tejas por fase, y mide en 5,1 s
    contra 6,6 s. Devuelve (movimiento, [pares que no se pudieron medir]) o None sin OpenCV."""
    try:
        import cv2
    except Exception:
        return None
    n = len(cuadros)
    out = np.zeros((max(0, n - 1), 3))
    fallan = []
    p0 = None
    for k in range(1, n):
        a, b = cuadros[k - 1], cuadros[k]
        if p0 is None or len(p0) < PUNTOS_MIN * 2:
            p0 = cv2.goodFeaturesToTrack(a, 300, 0.01, 8)
        if p0 is None or len(p0) < PUNTOS_MIN:
            fallan.append(k - 1)
            p0 = None
            continue
        p1, st, _e = cv2.calcOpticalFlowPyrLK(a, b, p0, None, winSize=(21, 21), maxLevel=3)
        ok = st.ravel() == 1
        M = None
        if ok.sum() >= PUNTOS_MIN:
            M, dentro = cv2.estimateAffinePartial2D(p0[ok], p1[ok], method=cv2.RANSAC, ransacReprojThreshold=1.5)
        if M is None:
            fallan.append(k - 1)
            p0 = None
            continue
        out[k - 1] = (M[0, 2], M[1, 2], math.atan2(M[1, 0], M[0, 0]))
        # los puntos que siguen sirviendo pasan al cuadro siguiente (no se buscan de nuevo cada vez)
        p0 = p1[ok][dentro.ravel() == 1].reshape(-1, 1, 2) if dentro is not None else None
    return out, fallan


PUNTOS_MIN = 12               # puntos seguidos que hacen falta para fiarse del ajuste (si no, las tejas por fase)


def movimiento(cuadros):
    """(tx, ty, giro) de cada cuadro respecto del anterior (n-1 filas), en px de la imagen chica y radianes. Siguiendo
    puntos (_puntos); los pares que asi no se pudieron medir, con las tejas por fase (_fase)."""
    r = _puntos(cuadros)
    if r is None:
        out, malos = _fase(cuadros, con_fallos=True)
    else:
        out, fallan = r
        malos = []
        for k in fallan:
            m, f = _fase(cuadros[k:k + 2], con_fallos=True)
            out[k] = m[0]
            if f:
                malos.append(k)
    return _rellenar(out, malos)


def _rellenar(out, malos):
    """(1.8.0, auditoria) Un par que ni los puntos ni la fase pudieron medir valia 0 = «la camara no se movio»: en un
    paneo rapido con desenfoque eso cortaba el camino y la correccion metia un tiron de un cuadro (MEDIDO: paneo de
    6 px/cuadro con un hueco, salto de 8,3 px contra 0,07 sin hueco). Ahora se rellena con lo de los vecinos."""
    if not len(malos) or len(malos) >= len(out):
        return out
    buenos = np.setdiff1d(np.arange(len(out)), malos)
    for c in range(out.shape[1]):
        out[malos, c] = np.interp(malos, buenos, out[buenos, c])
    return out


def _fase(cuadros, con_fallos=False):
    """(tx, ty, giro) de cada cuadro respecto del anterior con correlacion de fase en tejas. Donde no se pudo medir
    (cuadro liso), 0."""
    n, h, w = cuadros.shape
    tejas = _tejas(h, w)
    win = {}
    centros = np.array([[t[4], t[5]] for t in tejas], np.float64)
    prev = None
    out = np.zeros((max(0, n - 1), 3))
    fallos = []
    for k in range(n):
        f = cuadros[k].astype(np.float32)
        ffts = []
        for (y0, y1, x0, x1, _, _) in tejas:
            t = f[y0:y1, x0:x1]
            forma = t.shape
            if forma not in win:
                win[forma] = _ventana(*forma)
            ffts.append((np.fft.rfft2((t - t.mean()) * win[forma]), forma))
        if prev is not None:
            u = np.zeros((len(tejas), 2))
            peso = np.zeros(len(tejas))
            for i, ((fa, forma), (fb, _)) in enumerate(zip(prev, ffts)):
                dx, dy, pico = _corr_fase(fa, fb, forma)
                u[i] = (dx, dy)
                peso[i] = pico if pico >= PICO_MIN else 0.0
            sol = _ajustar(centros, u, peso)
            if sol is not None:
                out[k - 1] = sol
            else:
                fallos.append(k - 1)
        prev = ffts
    return (out, fallos) if con_fallos else out


def _suavizar(x, sigma):
    """Gaussiana con los bordes reflejados en punta (un paneo parejo sigue derecho hasta el final)."""
    n = len(x)
    if n < 3 or sigma <= 0:
        return x.copy()
    r = int(min(n - 1, max(1, round(3 * sigma))))
    izq = 2 * x[0] - x[r:0:-1]
    der = 2 * x[-1] - x[-2:-r - 2:-1]
    ext = np.concatenate([izq, x, der])
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / float(sigma)) ** 2)
    k /= k.sum()
    return np.convolve(ext, k, mode="same")[r:r + n]


def zoom_max(ruta):
    """Lo maximo que se puede acercar esa toma: ZOOM_MAX_4K si es de 4K o mas (la linea es HD), si no ZOOM_MAX."""
    _, w, h = _info(ruta)
    return ZOOM_MAX_4K if max(w, h) >= ANCHO_4K else ZOOM_MAX


def zoom_para(cx, cy, ca, w, h):
    """Acercamiento que hace falta para que, movida (cx, cy px) y girada (ca rad), la imagen siga cubriendo el cuadro."""
    z = 1.0
    for px, py in ((w / 2.0, h / 2.0), (-w / 2.0, h / 2.0), (w / 2.0, -h / 2.0), (-w / 2.0, -h / 2.0)):
        c, s = np.cos(ca), np.sin(ca)
        xs = c * (px - cx) + s * (py - cy)
        ys = -s * (px - cx) + c * (py - cy)
        z = max(z, float(np.max(np.abs(xs))) / (w / 2.0), float(np.max(np.abs(ys))) / (h / 2.0))
    return z


def temblor(mov, fps):
    """Temblor (px por cuadro de la imagen chica) = lo que se mueve de mas sobre el camino suave de ~0,2 s."""
    if len(mov) < 4:
        return 0.0
    x, y = np.cumsum(mov[:, 0]), np.cumsum(mov[:, 1])
    s = max(1.0, 0.2 * fps)
    return float(np.mean(np.hypot(np.diff(x - _suavizar(x, s)), np.diff(y - _suavizar(y, s)))))


VERSION = 4                  # (19-nov: 4, mas firme y zoom 1,18 en 4K; 3, siguiendo puntos; 2, los girados no se median) sube si cambia la cuenta: lo guardado deja de valer
_guardado = {"datos": None, "sucio": False}
_candado = __import__("threading").Lock()


def _archivo():
    return os.path.join(rutas.ANALISIS, "estabilizar.json")


def _clave(ruta, ini, dur):
    return "%s|%d|%.2f|%.2f" % (os.path.basename(ruta), os.path.getsize(ruta), ini, dur)


def _leer_guardado():
    with _candado:
        if _guardado["datos"] is None:
            try:
                with open(_archivo(), encoding="utf-8") as f:
                    j = json.load(f)
                _guardado["datos"] = j.get("planos", {}) if j.get("version") == VERSION else {}
            except Exception:
                _guardado["datos"] = {}
        return _guardado["datos"]


def guardar():
    """Deja en el disco lo medido en este armado (lo llama el armado al terminar de estabilizar)."""
    with _candado:
        if not _guardado["sucio"] or _guardado["datos"] is None:
            return
        try:
            os.makedirs(rutas.ANALISIS, exist_ok=True)
            with open(_archivo() + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"version": VERSION, "planos": _guardado["datos"]}, f, default=rutas.a_json)
            os.replace(_archivo() + ".tmp", _archivo())
            _guardado["sucio"] = False
        except (OSError, TypeError, ValueError):
            pass


def calcular(ruta, ini, dur, dur_video=None):
    """La correccion de un plano (ver _calcular). (18-nov, la persona: «con el análisis ya deberías saber dónde ir de
    una vez») Lo ya medido de un plano (mismo archivo, mismo tramo) se guarda en datos/analisis/estabilizar.json: al
    volver a armar, o en otra version que usa el mismo plano, no se vuelve a leer el video."""
    try:
        k = _clave(ruta, ini, dur)
    except OSError:
        return _calcular(ruta, ini, dur, dur_video)
    datos = _leer_guardado()
    if k in datos:
        return datos[k] or None
    c = _calcular(ruta, ini, dur, dur_video)
    with _candado:
        datos[k] = c or 0
        _guardado["sucio"] = True
    return c


def _calcular(ruta, ini, dur, dur_video=None):
    """La correccion de un plano: lo que hay que mover, girar y acercar cada cuadro del tramo [ini, ini + dur] de la
    toma. Devuelve {"t0": segundo del primer valor en la toma, "fps", "cx", "cy" (fraccion del ancho / alto, + =
    derecha / abajo), "ang" (grados, + = horario), "zoom", "antes", "despues" (temblor medido)} o None."""
    a = max(0.0, ini - MARGEN_S)
    b = ini + dur + MARGEN_S
    if dur_video:
        b = min(b, dur_video)
    cuadros, fps = leer(ruta, a, b - a)
    if cuadros is None or len(cuadros) < 6:
        return None
    n, h, w = cuadros.shape
    tope = zoom_max(ruta)
    mov = movimiento(cuadros)
    X = np.concatenate([[0.0], np.cumsum(mov[:, 0])])
    Y = np.concatenate([[0.0], np.cumsum(mov[:, 1])])
    A = np.concatenate([[0.0], np.cumsum(mov[:, 2])])
    k0 = int(round((ini - a) * fps))
    k1 = min(n, k0 + int(round(dur * fps)) + 1)
    if k1 - k0 < 3:
        return None
    mejor = None
    for sigma_s in SUAVES_S:
        sg = sigma_s * fps
        cx = _suavizar(X, sg) - X
        cy = _suavizar(Y, sg) - Y
        ca = np.clip(_suavizar(A, sg) - A, -math.radians(GIRO_MAX), math.radians(GIRO_MAX))
        tramo = slice(k0, k1)
        z = zoom_para(cx[tramo], cy[tramo], ca[tramo], w, h)
        mejor = (z, cx, cy, ca)
        if z <= tope:
            break
    z, cx, cy, ca = mejor
    if z > tope:                           # ni siguiendo mas a la camara alcanza: se corrige solo una parte
        f = (tope - 1.0) / (z - 1.0)
        cx, cy, ca = cx * f, cy * f, ca * f
        z = tope
    tramo = slice(k0, k1)
    corr_mov = np.stack([np.diff(X + cx), np.diff(Y + cy), np.diff(A + ca)], axis=1)
    return {"t0": a + k0 / fps, "fps": fps,
            "cx": (cx[tramo] / w).round(5).tolist(), "cy": (cy[tramo] / h).round(5).tolist(),
            "ang": np.degrees(ca[tramo]).round(4).tolist(), "zoom": round(float(z) * 1.003, 4),
            "antes": round(temblor(mov[k0:k1 - 1], fps), 3), "despues": round(temblor(corr_mov[k0:k1 - 1], fps), 3)}


def _valor(corr, t):
    """Correccion (cx, cy, ang) en el segundo t de la toma (interpolada)."""
    i = (t - corr["t0"]) * corr["fps"]
    n = len(corr["cx"])
    i = min(max(i, 0.0), n - 1.0)
    i0 = int(math.floor(i))
    i1 = min(n - 1, i0 + 1)
    f = i - i0
    return tuple(corr[k][i0] * (1 - f) + corr[k][i1] * f for k in ("cx", "cy", "ang"))


def velocidad(item, defecto=1.0):
    """Velocidad real del clip en la linea (0-1). Las tomas de 29,97 fps en una linea de 24 van al 80 %: cada cuadro de
    la linea muestra un cuadro de la toma (visto el 16-nov: GetSpeed() = 80,08 % en todos los planos)."""
    try:
        return float((item.GetSpeed() or {}).get("Percentage", defecto * 100.0)) / 100.0
    except Exception:
        return defecto


def aplicar(item, corr, fps_linea, ini, vel=None, log=None):
    """Pone la correccion en el clip de la linea: un Transform de Fusion («ESTABILIZADOR») entre MediaIn y MediaOut,
    con un keyframe por cuadro (centro y giro) y el zoom justo. Cada cuadro del comp avanza vel / fps_linea segundos
    de la toma (vel: la velocidad real del clip). Hay que ponerlo ANTES del primer render del clip: DaVinci reusa lo
    ya renderizado de un clip y no ve los cambios hechos por script en su comp (probado el 16-nov). True si quedo."""
    vel = velocidad(item) if vel is None else vel
    try:
        comp = item.GetFusionCompByIndex(1) if item.GetFusionCompCount() else None
        comp = comp or item.AddFusionComp()
    except Exception:
        comp = None
    if comp is None:
        return False
    comp.Lock()
    try:
        mi, mo = comp.FindTool("MediaIn1"), comp.FindTool("MediaOut1")
        if mi is None or mo is None:
            return False
        tr = comp.FindTool("ESTABILIZADOR") or comp.AddTool("Transform", -32768, -32768)
        tr.SetAttrs({"TOOLS_Name": "ESTABILIZADOR"})
        tr.ConnectInput("Input", mi)
        mo.ConnectInput("Input", tr)
        tr.SetInput("Size", float(corr["zoom"]))
        # el cuadro 0 del comp es el primero del clip en la linea (probado el 16-nov); el rango de render que dice
        # Fusion al crearlo puede ser mas corto que el plano (0-27 en uno de 37): se ponen keys en TODO el plano
        at = comp.GetAttrs() or {}
        f0 = int(at.get("COMPN_RenderStart", 0) or 0)
        f1 = f0 + int(item.GetDuration() or 0) + 1
        base = f0                                 # el cuadro 0 del plano = el segundo «ini» de la toma
        f0 -= 2
        tr.Center = comp.XYPath()
        camino = tr.Center.GetConnectedOutput().GetTool()
        camino.X = comp.BezierSpline()            # X e Y animadas por separado: si no, cada valor pisa al anterior
        camino.Y = comp.BezierSpline()
        tr.Angle = comp.BezierSpline()
        kx, ky, ka = {}, {}, {}
        for f in range(f0, f1 + 1):
            cx, cy, ang = _valor(corr, ini + (f - base) * vel / float(fps_linea))
            kx[f] = {1: 0.5 + cx}                 # Fusion: x hacia la derecha, y hacia ARRIBA
            ky[f] = {1: 0.5 - cy}
            ka[f] = {1: -ang}                     # Fusion: angulo + = antihorario
        # (16-nov) cada curva de UNA vez (SetKeyFrames): un keyframe por llamada eran ~300 llamadas por plano y, con
        # los ~180 planos del de 15 min, el puente con DaVinci se cayo sin aviso
        for entrada, keys in ((camino.X, kx), (camino.Y, ky), (tr.Angle, ka)):
            entrada.GetConnectedOutput().GetTool().SetKeyFrames(keys, True)
        return True
    except Exception as ex:
        if log:
            log("Aviso: no se pudo poner el estabilizador (%s)" % ex)
        return False
    finally:
        comp.Unlock()
