# -*- coding: utf-8 -*-
"""
analizar_material.py - Analiza en local (sin internet) las fotos, videos y tomas de dron del evento y los ordena por
momento: MAQUILLAJE, IGLESIA o FIESTA (los mismos nombres que los marcadores de las plantillas).

  - Hora real de cada archivo: EXIF de las fotos, metadatos del iPhone, nombre DJI / Pixel / Samsung, hora de la camara.
  - RELOJES: agrupa el material por camara. Si una camara tiene la hora corrida (otra zona horaria, reloj mal puesto)
    la alinea con las demas; si su reloj marca otro dia o no sirve, la ordena por CONTENIDO (luz, negros, color, luces
    de fiesta) y por el orden de sus propios archivos, siempre MAQUILLAJE -> IGLESIA -> FIESTA.
  - VIDEOS, en UNA sola lectura del archivo: calidad cada 0,5 s (nitidez, luz, temblor), color, tramos negros y nivel
    del audio (aplausos, gritos, brindis). Los videos largos que pasan de un momento a otro se parten en tramos.
  - FOTOS: nitidez, luz y una huella (dHash) para no repetir fotos casi iguales de una rafaga.
  - CLASIFICACION_EVENTO.json: horas de inicio de cada momento (se crea solo; se puede corregir desde la ventana).
  - Cache en datos/analisis/material.json: solo vuelve a medir lo nuevo o cambiado.

Uso suelto:   python analizar_material.py
Desde codigo: analizar(base, log=print) -> {"fecha", "items", "huella", "clasificacion", "avisos", "camaras"}
              reclasificar(log)          -> lo mismo, sin volver a medir (tras mover los limites en la ventana)
"""
import os
import re
import json
import math
import bisect
import datetime
import tempfile
import threading
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

if __name__ == "__main__":                 # suelto: PROGRAMA/nucleo para encontrar rutas
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))
import rutas

DEF_BASE = rutas.BASE
CARPETAS = rutas.CARPETAS             # {"foto": .../1 MATERIAL/FOTOS, "video": .../VIDEOS, "dron": .../DRON}
# (1.5.7, la persona: «solo imágenes JPG; las demás no las tomes en cuenta»): RAW, DNG, PNG, HEIC... ni se usan ni se tocan
EXT = {"foto": {".jpg", ".jpeg"},
       "video": {".mp4", ".mov", ".mkv", ".avi", ".mxf", ".m4v", ".mts", ".m2ts", ".wmv"}}
EXT["dron"] = EXT["video"]
CARPETAS_DRON = ("dron", "drone", "aereo", "aéreo", "aerea", "aérea", "mavic")


def tipo_de_archivo(ruta):
    """'foto', 'video' o 'dron' segun la extension. Dron: archivos DJI_ o «DRON ...» (ya renombrados) o dentro de una
    carpeta llamada DRON, Drone, Aereo, Mavic... None si no sirve."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext in EXT["foto"]:
        return "foto"
    if ext in EXT["video"]:
        if os.path.basename(ruta).upper().startswith(("DJI_", "DJI-", "DRON ")):
            return "dron"
        carpeta = os.path.basename(os.path.dirname(ruta)).lower()
        return "dron" if any(p in carpeta for p in CARPETAS_DRON) else "video"
    return None
MOMENTOS = ["MAQUILLAJE", "IGLESIA", "FIESTA"]
ARCHIVO_CLASIF = os.path.basename(rutas.CLASIFICACION)
SIN_VENTANA = rutas.SIN_VENTANA        # que ffmpeg no abra ventanas negras
VERSION = 5                            # sube cuando cambia lo que se mide: lo viejo se completa solo (3: temblor;
#                                        4: "vista" de cada medio segundo: enfoque real, luces quemadas, camara
#                                        torcida, barrido y huella de la imagen; 5: "capa" = el color por zonas,
#                                        para saber si dos planos son la misma escena)
PASO_CALIDAD = 0.5                     # segundos por muestra (calidad, color y audio)
CONFIANZA = {"iphone": 3, "dji": 3, "exif": 2, "nombre": 1, "camara": 1, "archivo": 0}

class _AlUsar:
    """Un modulo que se carga la primera vez que se usa. numpy y Pillow solo hacen falta al analizar, pero este
    archivo lo importa el motor al abrir el programa: cargarlos ahi costaba 80 ms antes de que saliera nada en
    pantalla (y bastante mas la primera vez tras encender la PC, que hay que leer sus DLL del disco)."""

    def __init__(self, nombre):
        self.__dict__["_nombre"], self.__dict__["_modulo"] = nombre, None

    def __getattr__(self, atributo):
        m = self.__dict__["_modulo"]
        if m is None:
            import importlib
            m = self.__dict__["_modulo"] = importlib.import_module(self.__dict__["_nombre"])
        return getattr(m, atributo)


def _hay(nombre):
    """True si el modulo esta instalado (sin cargarlo)."""
    try:
        import importlib.util
        return importlib.util.find_spec(nombre) is not None
    except Exception:
        return False


def _para_el_empaquetador():        # nunca se llama: PyInstaller sigue los import escritos, no los de importlib
    import numpy  # noqa: F401
    from PIL import Image, ImageOps  # noqa: F401


np = _AlUsar("numpy") if _hay("numpy") else None            # sin numpy: sin calidad ni color (se usa igual)
Image = _AlUsar("PIL.Image") if _hay("PIL") else None       # sin Pillow: las fotos se usan igual, sin brillo ni EXIF
ImageOps = _AlUsar("PIL.ImageOps") if Image is not None else None


def _run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=SIN_VENTANA)


def _fecha(s):
    m = re.match(r"\s*(\d{4})[:-](\d{2})[:-](\d{2})[T ](\d{2}):(\d{2}):(\d{2})", str(s or ""))
    try:
        return datetime.datetime(*map(int, m.groups())) if m else None
    except ValueError:                   # 0000:00:00 00:00:00 de camaras sin reloj
        return None


def _hora_de_nombre(nombre):
    """Hora escrita en el nombre: DJI_20261107153012, PXL_20261107_153012, 20261107_153012 (Samsung), IMG_20261107_..."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})", nombre)
    if not m:
        return None
    try:
        return datetime.datetime(*map(int, m.groups()))
    except ValueError:
        return None


def listar(base):
    """[(tipo, ruta)] de todo el material, en orden (sin archivos vacios ni ocultos)."""
    out = []
    for tipo, raiz in CARPETAS.items():
        for r, dirs, fs in os.walk(raiz):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for f in sorted(fs):
                if f.startswith(("~", ".")) or os.path.splitext(f)[1].lower() not in EXT[tipo]:
                    continue
                ruta = os.path.join(r, f)
                try:
                    if os.path.getsize(ruta) > 0:
                        out.append((tipo, ruta))
                except OSError:
                    pass
    # (1.5.7) las carpetas del evento DONDE ESTAN (soltadas: no se copian) y las capturas de la intro
    vistos = {os.path.normcase(os.path.abspath(r)) for _, r in out}
    for raiz in rutas.fuentes():
        for r, dirs, fs in os.walk(raiz):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "$")) and d.lower() != "anteriores")
            for f in sorted(fs):
                if f.startswith(("~", ".")):
                    continue
                ruta = os.path.join(r, f)
                tipo = tipo_de_archivo(ruta)
                clave = os.path.normcase(os.path.abspath(ruta))
                if tipo is None or clave in vistos:
                    continue
                try:
                    if os.path.getsize(ruta) > 0:
                        out.append((tipo, ruta))
                        vistos.add(clave)
                except OSError:
                    pass
    return out


def no_compatibles(base=None):
    """Archivos en 1 MATERIAL que el programa no usa (formato no compatible o vacios): [(carpeta, nombre)]."""
    out = []
    for tipo, raiz in CARPETAS.items():
        for r, dirs, fs in os.walk(raiz):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in fs:
                if f.startswith(("~", ".")) or f.lower() in ("desktop.ini", "thumbs.db"):
                    continue
                ruta = os.path.join(r, f)
                try:
                    vacio = os.path.getsize(ruta) == 0
                except OSError:
                    continue
                if vacio or os.path.splitext(f)[1].lower() not in EXT[tipo]:
                    out.append((os.path.basename(raiz), f))
    return out


def huella(base):
    """Firma del material (nombre, tamano, fecha): cambia cuando se sube, borra o termina de copiar algo."""
    h = []
    for tipo, ruta in listar(base):
        try:
            st = os.stat(ruta)
            try:
                rel = os.path.relpath(ruta, base)
            except ValueError:                    # carpeta del evento en otro disco (D:\BODA...)
                rel = ruta
            h.append("%s|%d|%d" % (rel, st.st_size, int(st.st_mtime)))
        except OSError:
            pass
    return "\n".join(h)


# ------------------------------------------------------------------ medidas de imagen (numpy)
LUMA = (0.2126, 0.7152, 0.0722)


def _color_cuadros(f):
    """f: (n, h, w, 3) en 0-1 -> por cuadro [luz media, negro p2, saturacion, R, G, B de los grises, fraccion de grises]
    y la fraccion de pixeles negros (para los tramos negros)."""
    n = f.shape[0]
    px = f.reshape(n, -1, 3)
    luz = px @ np.array(LUMA, dtype=np.float32)
    mx, mn = px.max(axis=2), px.min(axis=2)
    sat = (mx - mn) / (mx + 1e-4)
    gris = (sat < 0.15) & (luz > 0.15) & (luz < 0.85)          # pixeles casi neutros (paredes, vestido, cielo)
    p2 = np.percentile(luz, 2, axis=1)
    negro = (luz < 0.10).mean(axis=1)
    res = []
    for k in range(n):
        g = gris[k]
        rgb = px[k][g].mean(axis=0) if g.sum() > 20 else np.zeros(3, dtype=np.float32)
        res.append([round(float(luz[k].mean()), 4), round(float(p2[k]), 4), round(float(sat[k].mean()), 4),
                    round(float(rgb[0]), 4), round(float(rgb[1]), 4), round(float(rgb[2]), 4),
                    round(float(g.mean()), 4)])
    return res, negro


def _quemado(f):
    """Fraccion de la imagen con las luces reventadas (los tres colores pegados al tope): f (..., h, w, 3) en 0-1."""
    return (f.min(axis=-1) >= 0.955).reshape(f.shape[:-3] + (-1,)).mean(axis=-1)


def _vista_cuadros(f, g, lap):
    """Lo que se VE en cada cuadro, en numeros absolutos (no comparado con su propio video: un video entero malo no
    puede puntuar como uno bueno). f: (n, h, w, 3) y g: (n, h, w) en 0-1; lap: laplaciano de g.
    Devuelve por cuadro: nit (enfoque: varianza del laplaciano x1000), con (contraste), quem (fraccion de luces
    reventadas), eje (0-1: cuanto de los bordes va derecho, vertical u horizontal), giro (grados que se aparta de
    derecho la direccion que mas se repite), pico (0-1: cuanto manda esa direccion), hash (huella de la imagen) y
    capa (el color medio de una rejilla de 4 x 3, en hexadecimal: dos planos con la capa parecida son la misma
    escena aunque la camara se haya movido un poco; la huella hash cambia demasiado con un paneo corto)."""
    n = g.shape[0]
    res = {"nit": (lap.reshape(n, -1).var(axis=1) * 1000.0).round(3).tolist(),
           "con": g.reshape(n, -1).std(axis=1).round(3).tolist(),
           "quem": _quemado(f).round(3).tolist(), "eje": [], "giro": [], "pico": [], "hash": [], "capa": []}
    rejilla = (f.reshape(n, 3, 36, 4, 48, 3).mean(axis=(2, 4)) * 255.0).round().astype(np.uint8)
    gx = g[:, 1:-1, 2:] - g[:, 1:-1, :-2]
    gy = g[:, 2:, 1:-1] - g[:, :-2, 1:-1]
    fuerza = gx * gx + gy * gy
    cajon = np.minimum(8, (np.degrees(np.arctan2(gy, gx)) % 90.0 // 10).astype(np.int64))    # 9 cajones de 10 grados
    chico = g[:, :104, :189].reshape(n, 8, 13, 9, 21).mean(axis=(2, 4))
    bits = chico[:, :, 1:] > chico[:, :, :-1]
    for k in range(n):
        h = np.bincount(cajon[k].ravel(), weights=fuerza[k].ravel(), minlength=9)
        tot = float(h.sum()) + 1e-12
        j = int(h.argmax())
        centro = 10 * j + 5
        res["eje"].append(round(float(h[0] + h[8]) / tot, 3))
        res["giro"].append(min(centro, 90 - centro))
        res["pico"].append(round(float(h[j]) / tot, 3))
        res["hash"].append("%016x" % int("".join("1" if b else "0" for b in bits[k].ravel()), 2))
        res["capa"].append(rejilla[k].tobytes().hex())
    return res


def _barrido_de(desp):
    """Cuanto se mueve la camara en cada medio segundo (dx, dy medios, en pixeles por cuadro de 192 de ancho a 10
    cuadros por segundo): el paneo o el barrido, no el temblor."""
    d = np.asarray(desp, dtype=np.float32).reshape(-1, 2)
    n = len(d) // SUB + (1 if len(d) % SUB else 0)
    return [[round(float(x), 2) for x in d[i * SUB:(i + 1) * SUB].mean(axis=0)] for i in range(n)]


def _tramos_negros(fraccion_negra):
    """Tramos (s) donde casi toda la imagen es negra al menos 1,5 s (tapa puesta, camara en el bolsillo)."""
    rangos, ini = [], None
    for k, x in enumerate(list(fraccion_negra) + [0.0]):
        if x >= 0.92 and ini is None:
            ini = k
        elif x < 0.92 and ini is not None:
            if (k - ini) * PASO_CALIDAD >= 1.5:
                a, b = round(ini * PASO_CALIDAD, 2), round(k * PASO_CALIDAD, 2)
                if rangos and a - rangos[-1][1] < 3.0:
                    rangos[-1][1] = b
                else:
                    rangos.append([a, b])
            ini = None
    return rangos


def _puntaje_calidad(nitidez, brillo, mov):
    nitidez, brillo, mov = (np.asarray(x, dtype=np.float32) for x in (nitidez, brillo, mov))
    s_nit = np.clip(nitidez / (np.median(nitidez) + 1e-9), 0, 1.6) / 1.6
    s_exp = np.clip((brillo - 0.04) / 0.10, 0, 1) * np.clip((0.97 - brillo) / 0.10, 0, 1)
    med = float(np.median(mov)) + 1e-6
    s_est = np.clip(1.0 - (mov - 2 * med) / (4 * med), 0.25, 1.0)
    return [round(float(x), 3) for x in (s_nit ** 0.7) * s_exp * s_est]


def _leer_exacto(f, n):
    partes, falta = [], n
    while falta > 0:
        b = f.read(falta)
        if not b:
            break
        partes.append(b)
        falta -= len(b)
    return b"".join(partes)


def _db_audio(muestras):
    """Nivel (dBFS) de cada medio segundo de audio mono a 8 kHz."""
    paso = int(8000 * PASO_CALIDAD)
    n = len(muestras) // paso
    if n < 1:
        return []
    a = muestras[:n * paso].astype(np.float32).reshape(n, paso) / 32768.0
    rms = np.sqrt((a * a).mean(axis=1)) + 1e-6
    return [round(float(x), 1) for x in 20 * np.log10(rms)]


FPS_TEMBLOR = 10            # cuadros por segundo para medir el temblor (el pulso de la mano va de 2 a 10 Hz)
SUB = int(FPS_TEMBLOR * PASO_CALIDAD)     # 1 de cada 5 cuadros va a calidad y color (cada 0,5 s)


def _desplazamientos(previo, g):
    """Movimiento de camara (dx, dy en pixeles) entre cada par de cuadros seguidos, por correlacion de fase.
    previo: el ultimo cuadro del bloque anterior (o None). g: (n, h, w) en gris."""
    if previo is not None:
        g = np.concatenate([previo[None], g])
    if len(g) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    n, h, w = g.shape
    ventana = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    F = np.fft.rfft2((g - g.mean(axis=(1, 2), keepdims=True)) * ventana)
    R = F[1:] * np.conj(F[:-1])
    R /= np.abs(R) + 1e-9
    r = np.fft.irfft2(R, s=(h, w))
    m = r.reshape(n - 1, -1).argmax(axis=1)
    py, px = m // w, m % w
    k = np.arange(n - 1)

    def fino(c, a, b):                                # el pico entre pixeles (parabola por 3 puntos)
        den = a - 2 * c + b
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(np.abs(den) > 1e-9, 0.5 * (a - b) / np.where(den == 0, 1.0, den), 0.0)
    cx = r[k, py, px]
    dx = px + fino(cx, r[k, py, (px - 1) % w], r[k, py, (px + 1) % w])
    dy = py + fino(cx, r[k, (py - 1) % h, px], r[k, (py + 1) % h, px])
    dx = np.where(dx > w / 2, dx - w, dx)
    dy = np.where(dy > h / 2, dy - h, dy)
    return np.stack([dx, dy], axis=1).astype(np.float32)


def _temblor_de(desp):
    """Temblor de cada medio segundo: lo rapido y chico del movimiento (la mano), sin el paneo lento.
    En pixeles de un cuadro de 192 de ancho; mas de ~0,6 ya se nota."""
    d = np.asarray(desp, dtype=np.float32).reshape(-1, 2)
    if len(d) < 6:
        return []
    k = 9
    pad = np.pad(d, ((k // 2, k // 2), (0, 0)), mode="edge")
    suave = np.stack([np.convolve(pad[:, j], np.ones(k) / k, mode="valid") for j in range(2)], axis=1)
    rapido = np.linalg.norm(d - suave, axis=1)
    n = len(rapido) // SUB + (1 if len(rapido) % SUB else 0)
    return [round(float(np.sqrt((rapido[i * SUB:(i + 1) * SUB] ** 2).mean())), 2) for i in range(n)]


def _solo_temblor(ruta, dur):
    """Temblor de un video ya medido con una version anterior (solo gris, sin color ni audio)."""
    W, H = 192, 108
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-hwaccel", "auto", "-i", ruta,
                          "-map", "0:v:0", "-vf", "fps=%d,scale=%d:%d,format=gray" % (FPS_TEMBLOR, W, H),
                          "-f", "rawvideo", "pipe:1"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=SIN_VENTANA)
    reloj = threading.Timer(max(900.0, dur * 3.0), p.kill)
    reloj.start()
    desp, ultimo = [], None
    try:
        while True:
            buf = _leer_exacto(p.stdout, W * H * 100)
            n = len(buf) // (W * H)
            if n < 1:
                break
            g = np.frombuffer(buf[:n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32) / 255.0
            desp.append(_desplazamientos(ultimo, g))
            ultimo = g[-1]
        p.wait(timeout=60)
    finally:
        reloj.cancel()
        if p.poll() is None:
            p.kill()
    return _temblor_de(np.concatenate(desp) if desp else [])


def _medir_video(ruta, dur, con_audio=True):
    """UNA sola lectura del video (a 10 cuadros por segundo, 192x108): temblor con todos los cuadros; calidad, color
    y tramos negros con uno de cada 5 (cada 0,5 s); y el audio. Lee por bloques: no se llena la memoria aunque el
    video dure una hora."""
    W, H = 192, 108
    tam = W * H * 3
    tmp = None
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y", "-hwaccel", "auto", "-i", ruta,
           "-map", "0:v:0", "-vf", "fps=%d,scale=%d:%d,format=rgb24" % (FPS_TEMBLOR, W, H), "-f", "rawvideo", "pipe:1"]
    if con_audio:
        fd, tmp = tempfile.mkstemp(suffix=".pcm")
        os.close(fd)
        cmd += ["-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", tmp]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=SIN_VENTANA)
    reloj = threading.Timer(max(900.0, dur * 3.0), p.kill)           # si ffmpeg se cuelga, no se cuelga el programa
    reloj.start()
    nit, bri, mov, color, negro = [], [], [], [], []
    desp, ultimo_g = [], None
    ultimo = None
    cuenta = 0
    vista = {}
    pesos = np.array((0.299, 0.587, 0.114), dtype=np.float32)
    try:
        while True:
            buf = _leer_exacto(p.stdout, tam * 50)
            n = len(buf) // tam
            if n < 1:
                break
            todos = np.frombuffer(buf[:n * tam], dtype=np.uint8).reshape(n, H, W, 3).astype(np.float32) / 255.0
            gt = todos @ pesos
            desp.append(_desplazamientos(ultimo_g, gt))
            ultimo_g = gt[-1]
            sel = [i for i in range(n) if (cuenta + i) % SUB == 0]
            cuenta += n
            if not sel:
                continue
            f = todos[sel]
            n = len(sel)
            g = gt[sel]
            lap = g[:, 1:-1, 2:] + g[:, 1:-1, :-2] + g[:, 2:, 1:-1] + g[:, :-2, 1:-1] - 4 * g[:, 1:-1, 1:-1]
            nit += lap.reshape(n, -1).var(axis=1).tolist()
            for k, lista in _vista_cuadros(f, g, lap).items():
                vista.setdefault(k, []).extend(lista)
            bri += g.reshape(n, -1).mean(axis=1).tolist()
            previo = g[:1] if ultimo is None else ultimo[None]
            dif = np.abs(np.diff(np.concatenate([previo, g]), axis=0)).reshape(n, -1).mean(axis=1)
            mov += dif.tolist()
            ultimo = g[-1]
            chico = f.reshape(n, H // 2, 2, W // 2, 2, 3).mean(axis=(2, 4))
            c, ng = _color_cuadros(chico)
            color += c
            negro += ng.tolist()
        p.wait(timeout=60)
    finally:
        reloj.cancel()
        if p.poll() is None:
            p.kill()
    if not nit and con_audio:                            # la pista de audio no se pudo leer: solo la imagen
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return _medir_video(ruta, dur, False)
    todo_desp = np.concatenate(desp) if desp else []
    vista["pan"] = _barrido_de(todo_desp)
    res = {"calidad": [], "color": color, "oscuros": _tramos_negros(negro),
           "temblor": _temblor_de(todo_desp), "vista": vista}
    if nit:
        if len(mov) > 1:
            mov[0] = mov[1]
        res["calidad"] = _puntaje_calidad(nit, bri, mov)
    if tmp:
        try:
            res["audio"] = _db_audio(np.fromfile(tmp, dtype=np.int16))
        except Exception:
            res["audio"] = []
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    else:
        res["audio"] = []
    return res


def _solo_audio(ruta, dur):
    """Nivel del audio (para videos medidos con la version anterior, sin volver a leer la imagen)."""
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-i", ruta, "-map", "0:a:0",
                          "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=SIN_VENTANA)
    reloj = threading.Timer(max(600.0, dur * 2.0), p.kill)
    reloj.start()
    try:
        datos = p.stdout.read()
        p.wait(timeout=60)
    finally:
        reloj.cancel()
        if p.poll() is None:
            p.kill()
    return _db_audio(np.frombuffer(datos[:len(datos) // 2 * 2], dtype=np.int16))


# ------------------------------------------------------------------ analisis de un archivo
def _info_foto(ruta):
    d = {"hora": None, "origen_hora": "archivo", "horizontal": True, "brillo": 0.5}
    if Image is None:
        return d
    try:
        with Image.open(ruta) as im0:
            ex = im0.getexif()
            try:
                sub = ex.get_ifd(0x8769)
            except Exception:
                sub = {}
            dt = _fecha(sub.get(36867) or sub.get(36868) or ex.get(306))
            if dt:
                d["hora"], d["origen_hora"] = dt, "exif"
            modelo = " ".join(str(ex.get(t) or "").strip("\x00 ") for t in (271, 272)).strip()
            if modelo:
                d["camara"] = modelo[:40]
            im0.draft("RGB", (320, 320))
            im = ImageOps.exif_transpose(im0).convert("RGB")
        im.thumbnail((256, 256))
        d["horizontal"] = im.width >= im.height
        if np is None:
            g = im.convert("L")
            d["brillo"] = round(sum(g.getdata()) / (255.0 * g.width * g.height), 3)
            return d
        a = np.asarray(im, dtype=np.float32) / 255.0
        g = a @ np.array((0.299, 0.587, 0.114), dtype=np.float32)
        d["brillo"] = round(float(g.mean()), 3)
        d["quemado"] = round(float(_quemado(a)), 3)
        lap = g[1:-1, 2:] + g[1:-1, :-2] + g[2:, 1:-1] + g[:-2, 1:-1] - 4 * g[1:-1, 1:-1]
        d["nitidez"] = round(float(lap.var()) * 1000, 4)
        p = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
        d["dhash"] = "%016x" % int("".join("1" if b else "0" for b in (p[:, 1:] > p[:, :-1]).flatten()), 2)
        c, _ = _color_cuadros(a[None])
        d["color"] = c                                   # misma firma que los videos: sirve para clasificar por contenido
    except Exception as ex:                              # HEIC sin soporte, archivo raro: se usa igual, sin medidas
        d["aviso"] = str(ex)[:80]
    if d["hora"] is None:
        h = _hora_de_nombre(os.path.basename(ruta))
        if h:
            d["hora"], d["origen_hora"] = h, "nombre"
    return d


def _info_video(ruta):
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", ruta], 120)
    try:
        j = json.loads(r.stdout or "{}")
    except ValueError:
        j = {}
    fmt = j.get("format", {})
    streams = j.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    if v is None:
        raise ValueError("no tiene imagen (¿archivo dañado o solo audio?)")
    tags = {k.lower(): val for k, val in (fmt.get("tags") or {}).items()}
    num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "24/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if not 1 <= fps <= 240:
        num, _, den = (v.get("r_frame_rate") or "24/1").partition("/")
        try:
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 24.0
        fps = fps if 1 <= fps <= 240 else 24.0
    rot = 0
    for sd in v.get("side_data_list") or []:
        try:
            rot = int(float(sd.get("rotation", rot) or 0))
        except (TypeError, ValueError):
            pass
    try:
        rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
    except ValueError:
        pass
    # hora local: iPhone (trae zona horaria) > DJI / Pixel / Samsung (nombre) > hora de la camara > fecha del archivo
    hora, origen = None, "archivo"
    if tags.get("com.apple.quicktime.creationdate"):
        hora, origen = _fecha(tags["com.apple.quicktime.creationdate"]), "iphone"
    if hora is None:
        m = re.search(r"DJI_(\d{14})", os.path.basename(ruta))
        if m:
            try:
                hora, origen = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S"), "dji"
            except ValueError:
                hora = None
    if hora is None:
        h = _hora_de_nombre(os.path.basename(ruta))
        if h:
            hora, origen = h, "nombre"
    if hora is None and tags.get("creation_time"):
        hora, origen = _fecha(tags["creation_time"]), "camara"
        if hora is not None and hora.year < 2005:        # reloj de la camara sin poner
            hora, origen = None, "archivo"
    try:
        dur = float(fmt.get("duration") or v.get("duration") or 0)
    except ValueError:
        dur = 0.0
    modelo = (tags.get("com.apple.quicktime.model") or tags.get("model") or tags.get("com.android.model") or "").strip()
    d = {"hora": hora, "origen_hora": origen, "dur": dur, "fps": round(fps, 3),
         "ancho": v.get("width"), "alto": v.get("height"), "rotacion": rot,
         "audio_pista": any(s.get("codec_type") == "audio" for s in streams),
         "horizontal": (v.get("width") or 16) >= (v.get("height") or 9) if abs(rot) % 180 == 0
         else (v.get("height") or 9) >= (v.get("width") or 16)}
    codificador = str(tags.get("encoder") or "").strip()
    if not modelo and codificador.upper().startswith("DJI"):
        modelo = codificador
    if modelo:
        d["camara"] = modelo[:40]
    # dron aunque el archivo se haya renombrado o este en VIDEOS: DJI lo escribe en el archivo (no las camaras de mano
    # de DJI: Osmo, Pocket, Action, Ronin)
    if codificador.upper().startswith("DJI"):
        d["es_dron"] = not re.search(r"osmo|pocket|action|ronin|mic", codificador, re.I)
    return d


def _analizar_archivo(tipo, ruta, previo=None):
    """Mide un archivo. previo: lo medido por una version anterior (se completa sin repetir lo caro)."""
    st = os.stat(ruta)
    d = {"tipo": tipo, "ruta": ruta, "nombre": os.path.basename(ruta), "v": VERSION}
    if tipo == "foto":
        d.update(_info_foto(ruta))
    else:
        d.update(_info_video(ruta))
        dron = d.pop("es_dron", None)                    # lo que dice el archivo manda sobre el nombre y la carpeta
        if dron is True:
            d["tipo"] = "dron"
        elif dron is False and tipo == "dron":           # camara de mano de DJI (Osmo, Pocket): se llama DJI_ pero no vuela
            d["tipo"] = "video"
        if d["dur"] <= 0:
            raise ValueError("no se pudo leer la duración (¿archivo incompleto?)")
        if np is not None:
            if previo and previo.get("calidad") is not None and previo.get("color") is not None \
                    and (previo.get("vista") or {}).get("capa") is not None:
                d["vista"] = previo["vista"]
                for k in ("calidad", "color", "oscuros"):
                    d[k] = previo.get(k) or []
                d["audio"] = previo["audio"] if previo.get("audio") is not None else \
                    (_solo_audio(ruta, d["dur"]) if d["audio_pista"] else [])
                d["temblor"] = previo["temblor"] if previo.get("temblor") is not None else _solo_temblor(ruta, d["dur"])
            else:
                d.update(_medir_video(ruta, d["dur"], d["audio_pista"]))
        else:
            d.update({"calidad": [], "color": [], "oscuros": [], "audio": [], "temblor": [], "vista": {}})
    if d["hora"] is None:
        d["hora"] = datetime.datetime.fromtimestamp(st.st_mtime)
    d["hora"] = d["hora"].isoformat(timespec="seconds")
    return d


# ------------------------------------------------------------------ relojes de las camaras
def _dt(it):
    return datetime.datetime.fromisoformat(it["hora"])


def _jornada(dt):
    """La fiesta pasa de medianoche: hasta las 6 de la manana cuenta como el dia anterior."""
    return (dt - datetime.timedelta(hours=6)).date()


def _camara(it):
    # (1.5.7) el prefijo del nombre ORIGINAL («C0001», «IMG_1246»): renombrados, todos empiezan con «VIDEO»
    pref = re.match(r"[A-Za-z]+", it.get("nombre_original") or it["nombre"])
    nombre = it.get("camara") or (pref.group(0).upper() if pref else "?")
    tipo = {"foto": "fotos", "video": "videos", "dron": "dron"}[it["tipo"]]
    return "%s · %s%s" % (nombre, tipo, " · sin hora" if it.get("origen_hora") == "archivo" else "")


def _numero(nombre):
    m = re.findall(r"\d+", nombre)
    return (int(m[-1]) if m else 0, nombre)


def _relojes_basicos(items, ajuste_manual):
    """Ajuste a mano (ajuste_horas), camaras sin hora real y archivos de otro dia. Marca en cada item
    'reloj': ok | manual | dudoso. Devuelve (dia_del_evento, avisos)."""
    avisos = []
    for it in items:
        it["hora_camara"] = it.get("hora_camara") or it["hora"]
        it["hora"] = it["hora_camara"]
        it["reloj"] = "ok"
        for pref, horas in (ajuste_manual or {}).items():
            if it["nombre"].upper().startswith(str(pref).upper()):
                try:
                    it["hora"] = (_dt(it) + datetime.timedelta(hours=float(horas))).isoformat(timespec="seconds")
                    it["reloj"] = "manual"
                except (TypeError, ValueError):
                    pass
    grupos = _grupos(items)
    # 1) archivos sin hora propia que se copiaron todos juntos (fecha de copia): su hora no dice nada
    for k, g in grupos.items():
        if g[0].get("origen_hora") == "archivo" and len(g) >= 6:
            ts = sorted(_dt(i) for i in g)
            ventana = max(bisect.bisect_right(ts, a + datetime.timedelta(minutes=15)) - n for n, a in enumerate(ts))
            if ventana >= 0.8 * len(g):
                for i in g:
                    i["reloj"] = "dudoso"
                avisos.append("%s: sin hora real (fecha de copia): los ordené por contenido y por nombre." % k)
    # 2) dia del evento: lo deciden las camaras mas confiables (iPhone, DJI, EXIF)
    peso = {3: 4.0, 2: 2.0, 1: 1.0, 0: 0.3}
    votos = Counter()
    for k, g in grupos.items():
        c = _conf(g)
        for i in g:
            if i["reloj"] != "dudoso":
                votos[_jornada(_dt(i))] += peso[c]
    if not votos:
        for i in items:
            votos[_jornada(_dt(i))] += 1
    dia = votos.most_common(1)[0][0]
    # 3) archivos con el reloj en otro dia: si la HORA del dia cuadra con las demas camaras, solo estaba mal la
    #    fecha y se pasa al dia del evento; si no, no se adivina: se ordenan por contenido
    base = datetime.datetime.combine(dia, datetime.time())
    refmin = sorted((_dt(i) - base).total_seconds() / 60.0 for i in items
                    if i["reloj"] != "dudoso" and _jornada(_dt(i)) == dia)
    for k, g in grupos.items():
        fuera = [i for i in g if i["reloj"] != "dudoso" and _jornada(_dt(i)) != dia]
        if not fuera:
            continue
        d = Counter(_jornada(_dt(i)) for i in fuera).most_common(1)[0][0]
        nuevas = []
        for i in fuera:
            t = _dt(i)
            dd = dia + datetime.timedelta(days=1) if t.hour < 6 else dia
            nuevas.append(datetime.datetime.combine(dd, t.time()))
        cubre = 0
        for t in nuevas:
            m = (t - base).total_seconds() / 60.0
            j = bisect.bisect_left(refmin, m - 20)
            cubre += j < len(refmin) and refmin[j] <= m + 20
        if len(fuera) >= 3 and len(refmin) >= 8 and cubre >= 0.8 * len(fuera):
            for i, t in zip(fuera, nuevas):
                i["hora"] = t.isoformat(timespec="seconds")
                i["reloj"] = "corregido"
            avisos.append("%s: fecha mal puesta (%s) pero la hora cuadra con las demás cámaras: la pasé al %s."
                          % (k, d.isoformat(), dia.isoformat()))
            continue
        # 3b) reloj sin poner (otra fecha Y otra hora) pero que corre bien: sus tomas guardan las pausas reales del dia.
        #     Si hay UN corrimiento con el que caen donde trabajaron las demas camaras, se usa.
        corrido = _reloj_corrido([_dt(i) for i in fuera], refmin, base)
        if corrido is not None:
            for i in fuera:
                i["hora"] = (_dt(i) + corrido).isoformat(timespec="seconds")
                i["reloj"] = "corregido"
            avisos.append("%s: el reloj estaba sin poner (marcaba %s) pero corre bien: alineé sus %d archivos con las "
                          "demás cámaras." % (k, d.isoformat(), len(fuera)))
            continue
        for i in fuera:
            i["reloj"] = "dudoso"
        avisos.append("%s: %d archivo%s con fecha %s (no es el día del evento): los ordené por contenido."
                      % (k, len(fuera), "s" if len(fuera) > 1 else "", d.isoformat()))
    return dia, avisos


def _reloj_corrido(ts, refmin, base, ventana=15.0):
    """Corrimiento (timedelta) de una camara con el reloj sin poner pero que corre bien, o None si no hay un encaje claro.
    ts: horas de sus archivos segun su reloj. refmin: minutos (desde `base`, las 00:00 del dia del evento) de los archivos
    de las camaras fiables, ordenados. Se prueba cada corrimiento, minuto a minuto, con el que la camara cabe en el dia, y
    gana aquel con el que mas tomas suyas caen junto a las de las demas (y al reves). Solo se acepta si la camara cubre
    buena parte del dia (si no, encaja en cualquier lado) y si ningun otro corrimiento lejano encaja casi igual."""
    if len(ts) < 6 or len(refmin) < 30:
        return None
    t0 = min(ts)
    mg = sorted((t - t0).total_seconds() / 60.0 for t in ts)
    dur, ref_ini, ref_fin = mg[-1], refmin[0], refmin[-1]
    if dur < 120 or dur < 0.5 * (ref_fin - ref_ini) or dur > (ref_fin - ref_ini) + 90:
        return None

    def cubre(a, b, off, v):                       # parte de `a` que tiene algo de `b` a menos de v minutos
        n = 0
        for m in a:
            j = bisect.bisect_left(b, m + off - v)
            n += j < len(b) and b[j] <= m + off + v
        return n / float(len(a))
    notas = []
    off = ref_ini - 45.0
    while off <= ref_fin - dur + 45.0:
        propia = cubre(mg, refmin, off, ventana)
        notas.append((propia + 0.5 * cubre(refmin, mg, -off, 2 * ventana), propia, off))
        off += 1.0
    if not notas:
        return None
    nota, propia, off = max(notas)
    lejos = [n for n, _, o in notas if abs(o - off) >= 45]
    if propia < 0.75 or (lejos and max(lejos) > nota - 0.10):
        return None
    return (base + datetime.timedelta(minutes=off)) - t0


def _grupos(items):
    g = defaultdict(list)
    for it in items:
        g[_camara(it)].append(it)
    return g


def _conf(g):
    return max(CONFIANZA.get(i.get("origen_hora"), 0) for i in g)


def _momento_por_hora(minuto, inicios):
    mom = inicios[0][1]
    for ini, nombre in inicios:
        if minuto >= ini:
            mom = nombre
    return mom


def _desfase_archivo(i):
    """Minutos entre la fecha del archivo y el fin de la toma segun sus metadatos (None si no se puede leer)."""
    try:
        mt = datetime.datetime.fromtimestamp(os.stat(i["ruta"]).st_mtime)
        return ((mt - datetime.datetime.fromisoformat(i["hora_camara"])).total_seconds() - i.get("dur", 0)) / 60.0
    except (OSError, KeyError, ValueError, TypeError):
        return None


def _desfase_local():
    """Minutos entre la hora local de esta PC y UTC (p. ej. -360 en Centroamerica)."""
    import time
    return int(round(time.localtime().tm_gmtoff / 60.0))


def _alinear_horas(items, fecha, inicios, z):
    """Camaras con la hora corrida. Solo se corrige lo que tiene una explicacion clara:
      - videos con la hora del archivo (creation_time) que viene en UTC: se prueba pasarla a la hora local;
      - una camara que cae casi toda FUERA del horario de las demas: se prueba moverla de media en media hora.
    Gana el desfase con el que la camara cae junto a las demas (lo que se VE solo desempata)."""
    avisos = []
    grupos = _grupos(items)
    orden = sorted(grupos, key=lambda k: (_conf(grupos[k]), len(grupos[k])))
    utc = _desfase_local()
    for k in orden:
        g = [i for i in grupos[k] if i["reloj"] == "ok"]
        if len(g) < 4 or _conf(grupos[k]) >= 2:          # iPhone, DJI y EXIF son la referencia
            continue
        ref = [i for kk in grupos if kk != k for i in grupos[kk] if i["reloj"] in ("ok", "corregido", "manual")]
        if len(ref) < 8:
            continue
        # la prueba mas fiable: la camara escribe la fecha del ARCHIVO en su hora local; si los metadatos dicen
        # otra hora, desfasada siempre lo mismo (un multiplo de media hora), es que vienen en UTC
        difs = [d for d in (_desfase_archivo(i) for i in g if i.get("origen_hora") == "camara") if d is not None]
        if len(difs) >= 3:
            redondos = Counter(int(round(d / 30.0)) * 30 for d in difs if abs(d - round(d / 30.0) * 30) <= 3)
            if redondos:
                k_off, n_off = redondos.most_common(1)[0]
                if n_off >= 0.6 * len(difs):
                    if k_off and abs(k_off) <= 14 * 60:
                        for i in g:
                            i["hora"] = (_dt(i) + datetime.timedelta(minutes=k_off)).isoformat(timespec="seconds")
                            i["reloj"] = "corregido"
                        avisos.append("%s: la hora venía en UTC (%+g h); la pasé a la hora local." % (k, k_off / 60.0))
                    continue                             # k_off == 0: los metadatos ya estan en hora local
        refmin = sorted(_min(i["hora"], fecha) for i in ref)
        mg = [_min(i["hora"], fecha) for i in g]
        lo, hi = refmin[0] - 30, refmin[-1] + 30
        afuera = sum(1 for m in mg if m < lo or m > hi) / float(len(mg))
        candidatos = {0}
        if utc and any(i.get("origen_hora") == "camara" for i in g):
            candidatos.add(utc)
        if afuera >= 0.5:
            candidatos |= set(range(-720, 721, 30))
        if candidatos == {0}:
            continue

        def cubre(off):
            n = 0
            for m in mg:
                j = bisect.bisect_left(refmin, m + off - 20)
                n += j < len(refmin) and refmin[j] <= m + off + 20
            return n / float(len(mg))
        for i in ref:
            i["_m"] = _momento_por_hora(_min(i["hora"], fecha), inicios)
        probs = _probs_contenido(g, ref, z, "_m")

        def vista(off):                                  # cuanto cuadra lo que se ve con el momento (0-1)
            ps = [probs[id(i)][_momento_por_hora(m + off, inicios)] for i, m in zip(g, mg) if id(i) in probs]
            return sum(ps) / len(ps) if ps else 0.0
        c0 = cubre(0)
        cb, ob = max(((cubre(o) + 0.1 * vista(o) - (0.0 if o in (0, utc) else 0.05), o) for o in candidatos),
                     key=lambda t: (t[0], -abs(t[1])))
        cb = cubre(ob)
        necesita = 0.25 if ob == utc else 0.4
        if ob and cb >= 0.7 and cb - c0 >= necesita:
            for i in g:
                i["hora"] = (_dt(i) + datetime.timedelta(minutes=ob)).isoformat(timespec="seconds")
                i["reloj"] = "corregido"
            por = " (venía en hora UTC)" if ob == utc else ""
            avisos.append("%s: reloj corrido %+g h%s; lo alineé con las demás cámaras." % (k, ob / 60.0, por))
        elif afuera >= 0.8:
            for i in g:
                i["reloj"] = "dudoso"
            avisos.append("%s: su hora no cuadra con las demás cámaras: la ordené por contenido." % k)
    for i in items:
        i.pop("_m", None)
    return avisos


def _resumen_camaras(items):
    out = []
    for k, g in sorted(_grupos(items).items(), key=lambda kv: -len(kv[1])):
        out.append({"camara": k, "archivos": len(g),
                    "reloj": Counter(i["reloj"] for i in g).most_common(1)[0][0]})
    return out


# ------------------------------------------------------------------ clasificacion por contenido
def _rasgos(it):
    """[luz, negro, saturacion, calidez, grises] promedio de la toma (sin los cuadros negros)."""
    c = [x for x in (it.get("color") or []) if x[0] > 0.05]
    if not c:
        return None
    luz = sum(x[0] for x in c) / len(c)
    negro = sum(x[1] for x in c) / len(c)
    sat = sum(x[2] for x in c) / len(c)
    cg = [x for x in c if x[6] > 0.02 and sum(x[3:6]) > 0]
    cal = sum((x[3] - x[5]) / (x[3] + x[4] + x[5]) for x in cg) / len(cg) if cg else 0.0
    gris = sum(x[6] for x in c) / len(c)
    return [luz, negro, sat, cal, gris]


def _clase(it):
    return "foto" if it["tipo"] == "foto" else "video"


Z_POR_CAMARA = True       # cada camara en su propia escala (cada una tiene su "look")


def _normalizador(items):
    """Cada camara (o al menos cada clase: fotos / videos) en su propia escala: las fotos salen mas saturadas que
    los videos de la misma escena y cada camara tiene su look, asi que se mide cuanto se aparta cada toma de lo
    tipico de SU camara."""
    por = defaultdict(list)
    for i in items:
        r = _rasgos(i)
        if r:
            por[_clase(i)].append(r)
            if Z_POR_CAMARA:
                por[_camara(i)].append(r)
    est = {}
    for c, rs in por.items():
        if len(rs) < 6:
            continue
        dims = len(rs[0])
        med = [sum(r[d] for r in rs) / len(rs) for d in range(dims)]
        dev = [max(1e-3, (sum((r[d] - med[d]) ** 2 for r in rs) / len(rs)) ** 0.5) for d in range(dims)]
        est[c] = (med, dev)

    def z(it):
        r = _rasgos(it)
        clave = _camara(it) if Z_POR_CAMARA and _camara(it) in est else _clase(it)
        if r is None or clave not in est:
            return None
        med, dev = est[clave]
        return [(a - m) / s for a, m, s in zip(r, med, dev)]
    return z


def _prob_prototipo(zv):
    """Sin material de referencia: mas claro y con paredes neutras = maquillaje; mas oscuro, saturado y sin
    neutros = fiesta (en la escala de su clase)."""
    zl, zn, zs, zc, zg = zv
    s = {"MAQUILLAJE": 0.8 * zl + 1.0 * zg,
         "IGLESIA": 0.3 - 0.4 * abs(zl) + 0.3 * zc,
         "FIESTA": -1.2 * zl + 0.6 * zs - 0.6 * zg}
    e = {k: math.exp(max(-20.0, min(20.0, v))) for k, v in s.items()}
    t = sum(e.values())
    return {k: v / t for k, v in e.items()}


# Medido con un evento real estropeando relojes a proposito: los "vecinos" de OTRAS camaras confunden (cada camara
# tiene su look); lo que mejor ordena es la luz/color en la escala de la propia camara + el orden de sus archivos.
MEZCLA_VECINOS = 0.0      # peso de los vecinos ya clasificados frente al prototipo (luz / color)
POSICION = 2.0            # empujon por el lugar en la secuencia de la camara
CRUZAR_CLASE = False      # comparar fotos con videos (en escalas distintas) cuando falta referencia


def _probs_contenido(objetivos, refs, z, etiqueta="momento"):
    """{id(item): {momento: prob}}: mezcla de los 9 vecinos mas parecidos de la MISMA clase (si hay suficientes)
    con el prototipo de luz y color."""
    pools = defaultdict(list)
    for i in refs:
        zi = z(i)
        if zi is not None and i.get(etiqueta) in MOMENTOS:
            pools[_clase(i)].append((zi, i[etiqueta]))
    todos = [x for p in pools.values() for x in p]
    probs = {}
    for it in objetivos:
        zt = z(it)
        if zt is None:
            continue
        proto = _prob_prototipo(zt)
        pool = pools.get(_clase(it)) or []
        if (len(pool) < 12 or len({m for _, m in pool}) < 2) and CRUZAR_CLASE:
            pool = todos
        if len(pool) < 12 or len({m for _, m in pool}) < 2:
            probs[id(it)] = proto
            continue
        cerca = sorted((sum((a - b) ** 2 for a, b in zip(zt, zr)) ** 0.5, m) for zr, m in pool)[:9]
        p = {m: 0.3 for m in MOMENTOS}
        for dist, m in cerca:
            p[m] += 1.0 / (dist + 0.3)
        t = sum(p.values())
        mix = {m: (p[m] / t) ** MEZCLA_VECINOS * proto[m] ** (1 - MEZCLA_VECINOS) for m in MOMENTOS}
        t = sum(mix.values())
        probs[id(it)] = {m: v / t for m, v in mix.items()}
    return probs


def _cortes_en_orden(seq, probs, posicion=0.0):
    """Reparte una secuencia ordenada en MAQUILLAJE -> IGLESIA -> FIESTA (cada tramo puede quedar vacio)
    maximizando la probabilidad de cada archivo. posicion > 0 suma un empujon suave por el lugar en la
    secuencia (lo primero suele ser maquillaje y lo ultimo fiesta). Programacion dinamica O(n)."""
    n = len(seq)
    lp = {m: [0.0] for m in MOMENTOS}
    for k, it in enumerate(seq):
        p = probs.get(id(it)) or {m: 1.0 / 3 for m in MOMENTOS}
        x = (k + 0.5) / max(1, n)
        empuje = {"MAQUILLAJE": -x, "IGLESIA": -abs(x - 0.5), "FIESTA": -(1 - x)}
        for m in MOMENTOS:
            lp[m].append(lp[m][-1] + math.log(max(1e-6, p[m])) + posicion * empuje[m])
    M, I, F = (lp[m] for m in MOMENTOS)
    mejor = None
    mejor_a, mejor_a_val = 0, M[0] - I[0]
    for b in range(n + 1):
        if M[b] - I[b] > mejor_a_val:
            mejor_a, mejor_a_val = b, M[b] - I[b]
        val = mejor_a_val + I[b] + F[n] - F[b]
        if mejor is None or val > mejor[0]:
            mejor = (val, mejor_a, b)
    _, a, b = mejor
    return [MOMENTOS[0] if k < a else MOMENTOS[1] if k < b else MOMENTOS[2] for k in range(n)]


# ------------------------------------------------------------------ clasificacion por hora
def _min(hora_iso, fecha):
    dt = datetime.datetime.fromisoformat(hora_iso)
    return (dt - datetime.datetime.combine(fecha, datetime.time())).total_seconds() / 60.0


def _hhmm(minutos):
    minutos = int(max(0, minutos))
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def _a_min(hhmm):
    h, m = str(hhmm).strip().split(":")
    return int(h) * 60 + int(m)


def _auto(items, fecha):
    """Propone la hora de inicio de IGLESIA y FIESTA: por lo que se VE (luz y color de cada toma, en orden) afinado con
    los huecos del dia; si no hay suficiente material medido, solo con los huecos."""
    try:
        por_contenido = _auto_contenido(items, fecha)
    except Exception:
        por_contenido = None
    return por_contenido or _auto_huecos(items, fecha)


def _auto_contenido(items, fecha):
    """El dia en orden se reparte en MAQUILLAJE -> IGLESIA -> FIESTA segun la luz y el color de cada toma (lo mismo que
    ordena las camaras sin hora) y cada corte se lleva al hueco mas grande que tenga cerca: el traslado a la iglesia o
    al salon. Asi una pausa larga DENTRO de un momento (el almuerzo) no se confunde con el traslado.
    Medido: en la boda real da 15:32 y 18:16 (lo que la persona dio por bueno)."""
    seq = sorted(items, key=lambda i: i["hora"])
    z = _normalizador(items)
    probs = {}
    for i in seq:
        zi = z(i)
        if zi is not None:
            probs[id(i)] = _prob_prototipo(zi)
    n = len(seq)
    if len(probs) < 20 or len(probs) < 0.5 * n:
        return None
    moms = _cortes_en_orden(seq, probs, POSICION)
    mins = [_min(i["hora"], fecha) for i in seq]
    cerca = max(3, int(n * 0.06))
    inicios = []
    for m in ("IGLESIA", "FIESTA"):
        k = next((j for j, x in enumerate(moms) if x == m or (m == "IGLESIA" and x == "FIESTA")), None)
        if not k:                                        # no hay ese momento (o empieza en el primer archivo)
            return None
        huecos = [(mins[j + 1] - mins[j], mins[j + 1]) for j in range(max(0, k - 1 - cerca), min(n - 1, k + cerca))
                  if mins[j + 1] - mins[j] >= 8]
        inicios.append((max(huecos)[1] if huecos else mins[k]) - 1)
    # Una pausa larga de TODAS las camaras y, enseguida, video grabado casi sin parar: ahi empieza la ceremonia aunque
    # lo que se ve no se parezca a una iglesia (ceremonia en jardin o salon). Solo si el corte por contenido quedo lejos.
    ceremonia = _ceremonia_tras_pausa(seq, mins, fecha)
    if ceremonia is not None and abs(ceremonia - inicios[0]) > 60:
        k = next((j for j, m in enumerate(mins) if m >= ceremonia), None)
        resto = seq[k:] if k else []
        if len(resto) >= 6:
            moms2 = _cortes_en_orden(resto, probs, POSICION)
            f = next((j for j, x in enumerate(moms2) if x == "FIESTA"), None)
            if f:
                f += k
                huecos = [(mins[j + 1] - mins[j], mins[j + 1]) for j in range(max(k, f - 1 - cerca), min(n - 1, f + cerca))
                          if mins[j + 1] - mins[j] >= 8]
                inicios = [ceremonia - 1, (max(huecos)[1] if huecos else mins[f]) - 1]
    if inicios[1] - inicios[0] < 10:                     # sin un tramo claro de iglesia: que decidan los huecos
        return None
    return [["MAQUILLAJE", "00:00"], ["IGLESIA", _hhmm(inicios[0])], ["FIESTA", _hhmm(inicios[1])]]


BLOQUE_VENTANA, BLOQUE_MINIMO = 20.0, 0.35      # min; parte de la ventana con video grabado para decir "sin parar"
PAUSA_MINIMA, PAUSA_CERCA = 60.0, 30.0          # min de pausa; y cuanto antes del tramo puede acabar esa pausa


def _ceremonia_tras_pausa(seq, mins, fecha):
    """Minuto en que arranca la ceremonia segun el ritmo de las camaras, o None. Los preparativos se graban a ratos; una
    ceremonia, casi seguida. Se toma el primer tramo del dia con video grabado al menos el 35 % de 20 minutos y se mira si
    viene justo despues de una pausa larga de todas las camaras (el almuerzo o el traslado; un par de fotos sueltas no la
    rompen). Devuelve la hora del primer archivo despues de la pausa. Si antes del tramo siguieron trabajando (una pausa
    DENTRO de los preparativos, como en la boda de prueba), no dice nada y manda lo que se ve."""
    videos = sorted((m, m + (i.get("dur") or 0) / 60.0) for i, m in zip(seq, mins) if i.get("tipo") != "foto" and i.get("dur"))
    if len(videos) < 8:
        return None
    for t0, _ in videos:
        fin = t0 + BLOQUE_VENTANA
        grabado = sum(max(0.0, min(b, fin) - max(a, t0)) for a, b in videos if a < fin and b > t0)
        if grabado / BLOQUE_VENTANA < BLOQUE_MINIMO:
            continue
        cerca = [m for m in mins if t0 - PAUSA_CERCA <= m < t0]     # la llegada: ya es parte de la ceremonia
        inicio = min(cerca) if cerca else t0
        grupos = []                                      # antes de eso: archivos seguidos (menos de 10 min entre ellos)
        for m in (x for x in mins if x < inicio):
            if grupos and m - grupos[-1][-1] < 10:
                grupos[-1].append(m)
            else:
                grupos.append([m])
        firmes = [g for g in grupos if len(g) > 3 or g[-1] - g[0] >= 5]     # un par de fotos sueltas no cuenta
        if not firmes or inicio - firmes[-1][-1] < PAUSA_MINIMA:
            return None                                  # el primer tramo seguido no viene de una pausa: no se toca
        return inicio
    return None


def _auto_huecos(items, fecha):
    """Propone la hora de inicio de IGLESIA y FIESTA buscando los huecos mas grandes del dia."""
    mins = sorted(_min(i["hora"], fecha) for i in items)
    if not mins:
        return [["MAQUILLAJE", "00:00"], ["IGLESIA", "13:00"], ["FIESTA", "16:00"]]
    a, b = mins[0], mins[-1]
    span = max(1.0, b - a)

    def hueco(lo, hi):
        mejor = (0, None)
        for x, y in zip(mins, mins[1:]):
            if x >= lo and y <= hi and y - x > mejor[0]:
                mejor = (y - x, y)
        return mejor

    g, fiesta = hueco(a + 0.35 * span, b)              # traslado de la iglesia al salon
    if fiesta is None or g < 20:
        fiesta = a + 0.65 * span
    g, iglesia = hueco(a + 0.25 * (fiesta - a), a + 0.85 * (fiesta - a))   # de la casa a la iglesia
    if iglesia is None or g < 10:
        iglesia = a + 0.45 * (fiesta - a)
    return [["MAQUILLAJE", "00:00"], ["IGLESIA", _hhmm(iglesia - 1)], ["FIESTA", _hhmm(fiesta - 1)]]


def _guardar_json(ruta, datos, indent=2):
    """Escritura segura: si se corta la luz a la mitad, el archivo anterior queda entero."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, ruta)


def leer_clasificacion():
    try:
        with open(rutas.CLASIFICACION, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _inicios_validos(cfg):
    try:
        ini = sorted((_a_min(h), str(m).upper()) for m, h in cfg.get("momentos") or [])
    except (ValueError, TypeError):
        return None
    if not ini or any(m not in MOMENTOS for _, m in ini):
        return None
    return ini


def guardar_momentos(inicios):
    """La ventana movio los limites: {"IGLESIA": "15:32", "FIESTA": "18:16"} -> CLASIFICACION (revisado=true)."""
    cfg = leer_clasificacion()
    mom = [["MAQUILLAJE", "00:00"]] + [[m, inicios[m]] for m in ("IGLESIA", "FIESTA") if m in inicios]
    cfg["momentos"] = mom
    cfg["revisado"] = True
    _guardar_json(rutas.CLASIFICACION, cfg)


def clasificar(items, base, log=print):
    """Relojes -> dia del evento -> horas corridas -> momentos por hora -> los dudosos por contenido y en el orden
    de su camara -> tramos de los videos largos que cruzan de un momento a otro."""
    cfg = leer_clasificacion()
    if os.path.exists(rutas.CLASIFICACION) and not cfg:
        try:
            os.replace(rutas.CLASIFICACION, rutas.CLASIFICACION + ".dañado")
        except OSError:
            pass
        log("Aviso: %s estaba dañado; lo guardé aparte y hago uno nuevo." % ARCHIVO_CLASIF)
    if cfg.get("fecha"):                                 # ¿la clasificacion guardada es de OTRO evento?
        fecha0, _ = _relojes_basicos(items, None)
        try:
            otra = abs((fecha0 - datetime.date.fromisoformat(cfg["fecha"])).days) > 1
        except (ValueError, TypeError):
            otra = True
        if otra:                                         # sus excepciones y ajustes de reloj no valen para este
            try:
                os.replace(rutas.CLASIFICACION, rutas.CLASIFICACION + ".anterior")
            except OSError:
                pass
            log("La clasificación guardada era de otro evento (%s): empiezo una nueva." % cfg.get("fecha"))
            cfg = {}
    fecha, avisos = _relojes_basicos(items, cfg.get("ajuste_horas"))
    z = _normalizador(items)
    inicios = _inicios_validos(cfg) if cfg.get("fecha") == fecha.isoformat() else None
    if cfg.get("fecha") == fecha.isoformat() and cfg.get("momentos") and inicios is None:
        log("Aviso: las horas de los momentos en %s no se entienden; las vuelvo a calcular." % ARCHIVO_CLASIF)
    nuevo = inicios is None
    if nuevo:
        inicios = _inicios_validos({"momentos": _auto([i for i in items if i["reloj"] != "dudoso"] or items, fecha)})
    avisos += _alinear_horas(items, fecha, inicios, z)
    avisos += _sincronizar_por_audio(items)          # (1.5.7) la hora real de una camara con el reloj mal, por el sonido
    confiables = [i for i in items if i["reloj"] != "dudoso"]
    if nuevo:                                            # con las camaras ya en hora, los huecos del dia salen mejor
        cfg = {"fecha": fecha.isoformat(), "revisado": False,
               "momentos": _auto(confiables or items, fecha),
               "archivos": cfg.get("archivos") or {}, "descartar": cfg.get("descartar") or [],
               "zonas_inutiles": cfg.get("zonas_inutiles") or {},
               "ajuste_horas": cfg.get("ajuste_horas") or {},
               "ayuda": "momentos = hora de inicio de cada momento (HH:MM, puede pasar de 24:00). "
                        "archivos = excepciones {archivo: MOMENTO}. descartar = archivos que no se usan. "
                        "zonas_inutiles = {archivo: [[seg_ini, seg_fin], ...]}. "
                        "ajuste_horas = {PREFIJO: horas} si el reloj de una camara estaba mal. "
                        "Pon revisado=true cuando lo corrijas a mano."}
        _guardar_json(rutas.CLASIFICACION, cfg)
        inicios = _inicios_validos(cfg)
        log("Clasificacion automatica creada en %s (revisala si algo cae en el momento equivocado)." % ARCHIVO_CLASIF)
    excep = {str(k).upper(): str(v).upper() for k, v in (cfg.get("archivos") or {}).items()
             if str(v).upper() in MOMENTOS}
    fuera = {str(x).upper() for x in cfg.get("descartar") or []}
    inutil = {str(k).upper(): v for k, v in (cfg.get("zonas_inutiles") or {}).items()}
    for it in confiables:
        it["momento"] = _momento_por_hora(_min(it["hora"], fecha), inicios)
        it["por"] = "hora"
    # los dudosos: por contenido (vecinos parecidos ya clasificados) y en el orden de su propia camara
    dudosos = [i for i in items if i["reloj"] == "dudoso"]
    if dudosos:
        probs = _probs_contenido(dudosos, confiables, z)
        sin_ref = len(confiables) < 12
        rango = {}
        for m in MOMENTOS:
            ms = sorted(_min(i["hora"], fecha) for i in confiables if i["momento"] == m)
            if ms:
                rango[m] = (ms[len(ms) // 10], ms[(len(ms) * 9) // 10])
        sinteticos = {"MAQUILLAJE": (10 * 60, 13 * 60), "IGLESIA": (13 * 60 + 30, 15 * 60), "FIESTA": (16 * 60, 23 * 60)}
        for k, g in _grupos(dudosos).items():
            sin_hora = g[0].get("origen_hora") == "archivo"
            seq = sorted(g, key=lambda i: _numero(i["nombre"]) if sin_hora else (i["hora_camara"], i["nombre"]))
            moms = _cortes_en_orden(seq, probs, 2.0 if sin_ref else POSICION)
            for m in MOMENTOS:
                sel = [it for it, mm in zip(seq, moms) if mm == m]
                lo, hi = rango.get(m) or sinteticos[m]
                for n, it in enumerate(sel):       # su hora se reparte dentro del momento, en su orden
                    x = lo + (hi - lo) * (n + 0.5) / len(sel)
                    it["hora"] = (datetime.datetime.combine(fecha, datetime.time()) +
                                  datetime.timedelta(minutes=x)).isoformat(timespec="seconds")
                    it["momento"] = m
                    it["por"] = "contenido"
    _segun_lo_que_ve(items, fecha)
    # excepciones a mano, descartes, zonas inutiles y videos largos que cruzan de un momento a otro
    for it in items:
        n = it["nombre"].upper()
        it.pop("tramos", None)
        if n in excep:
            it["momento"], it["por"] = excep[n], "manual"
        elif it["tipo"] != "foto" and it["reloj"] != "dudoso" and it.get("dur", 0) > 20 and it.get("por") != "ia":
            m0 = _min(it["hora"], fecha)
            m1 = m0 + it["dur"] / 60.0
            cortes = [(ini, nom) for ini, nom in inicios if m0 < ini < m1]
            if cortes:
                tramos, a, mom = [], 0.0, it["momento"]
                for ini, nom in cortes:
                    s = round((ini - m0) * 60.0, 2)
                    tramos.append([a, s, mom])
                    a, mom = s, nom
                tramos.append([a, round(it["dur"], 2), mom])
                it["tramos"] = [t for t in tramos if t[1] - t[0] >= 2.0]
        it["descartar"] = n in fuera
        if n in inutil:
            it["oscuros"] = (it.get("oscuros") or []) + inutil[n]
    # (1.5.7) lo que la IA local ve que no sirve (el piso, la pantalla de una camara, borrosa...) queda fuera del montaje
    # (el archivo no se toca). Si dijera que casi nada sirve, no se le hace caso.
    # (1.5.7, 16-nov) y si en la revision cuadro por cuadro la mayor parte de la toma no sirve (apunta al techo, de
    # cabeza, gente sin cabeza o sin ninguna cara), la toma entera; si sirve una parte, el armado usa solo esa parte
    def _razon(it):
        ia = it.get("ia") or {}
        if ia.get("util") is False:
            return ia.get("escena", "")
        try:
            import vision_ia
            parte, motivo = vision_ia.parte_mala(ia, dron=it["tipo"] == "dron")
            if it["tipo"] == "foto" and parte >= 1.0:          # foto o captura que no cumple la regla
                return vision_ia.MOTIVOS.get(motivo, motivo)
            limite = PARTE_MALA_TOMA if it.get("dur", 0) <= TOMA_CORTA_S else PARTE_MALA_LARGA
            if parte >= limite and len(ia.get("instantes") or []) >= 2:
                return "%s en el %.0f%%" % (vision_ia.MOTIVOS.get(motivo, motivo), 100 * parte)
        except Exception:
            pass
        return None
    inutiles = [(it, _razon(it)) for it in items if it["nombre"].upper() not in excep]
    inutiles = [(it, r) for it, r in inutiles if r is not None]
    if len(inutiles) > PARTE_IA_MAX * len(items):      # si dijera que casi nada sirve: solo las peores
        try:
            import vision_ia
            inutiles.sort(key=lambda p: -(1.0 if (p[0].get("ia") or {}).get("util") is False
                                          else vision_ia.parte_mala(p[0].get("ia"), p[0]["tipo"] == "dron")[0]))
        except Exception:
            pass
        inutiles = inutiles[:int(PARTE_IA_MAX * len(items))]
    if inutiles:
        for it, r in inutiles:
            it["descartar"], it["por_descarte"] = True, "ia: %s" % r
        avisos.append("La IA local dejó fuera %d tomas que no sirven: %s" % (
            len(inutiles), ", ".join("%s (%s)" % (i["nombre"], r) for i, r in inutiles[:4])
            + ("…" if len(inutiles) > 4 else "")))
    cfg["_avisos"], cfg["_camaras"] = avisos, _resumen_camaras(items)
    for a in avisos:
        log("Aviso: " + a)
    return cfg


# ------------------------------------------------------------------ todo junto
def _clave(ruta):                    # nombre + tamano: sirve aunque se muevan las carpetas o se pase a Mac
    return "%s|%d" % (os.path.basename(ruta), os.stat(ruta).st_size)


def _cache_ruta():
    return os.path.join(rutas.ANALISIS, "material.json")


def _leer_cache():
    try:
        with open(_cache_ruta(), encoding="utf-8") as f:
            cache = json.load(f).get("cache", {})
    except Exception:
        return {}
    viejo = {}                          # cache de versiones anteriores: "ruta completa|tamano|fecha"
    for k, v in cache.items():
        partes = k.split("|")
        nueva = "%s|%s" % (re.split(r"[\\/]", partes[0])[-1], partes[1]) if len(partes) == 3 else k
        viejo[nueva] = v
    return viejo


PASO_AUDIO = 0.5             # s por muestra del nivel de audio («audio» de cada video)
SOLAPE_MIN = 24              # muestras (12 s) que dos tomas deben sonar juntas para decir que son el mismo momento
CRUCE_MIN = 0.6              # parecido minimo del sonido (correlacion de los niveles, -1..1)


def _envolvente(it):
    """El nivel del audio de un video, normalizado (media 0, desvio 1); None si no tiene o es plano."""
    if np is None or it["tipo"] == "foto" or not it.get("audio_pista", True):
        return None
    a = np.asarray(it.get("audio") or [], dtype=np.float32)
    if len(a) < SOLAPE_MIN:
        return None
    a = np.maximum(a, -60.0)
    if float(a.std()) < 1.5:
        return None
    return (a - a.mean()) / a.std()


def _cruce(a, b):
    """(parecido, L, solape): el desfase L (en muestras) en que a[i] suena como b[i+L], o None."""
    n, m = len(a), len(b)
    c = np.correlate(b, a, mode="full")                       # c[k]: L = k - (n - 1)
    lags = np.arange(-(n - 1), m)
    solape = np.minimum(n, m - lags) - np.maximum(0, -lags)
    validos = solape >= SOLAPE_MIN
    if not validos.any():
        return None
    r = np.where(validos, c / np.maximum(solape, 1), -9.0)
    k = int(np.argmax(r))
    mejor = float(r[k])
    otro = np.concatenate([r[:max(0, k - 6)], r[k + 7:]])     # el pico debe destacar (no ser musica pareja)
    if mejor < CRUCE_MIN or (len(otro) and float(otro.max()) > mejor - 0.15):
        return None
    return mejor, int(lags[k]), int(solape[k])


def _sincronizar_por_audio(items):
    """(1.5.7) Una camara con el reloj mal (otra fecha, «dudoso») se pone en hora comparando su SONIDO con el de las
    tomas que tienen la hora bien (el celular): si en una toma de la camara y una del celular el nivel del audio sube y
    baja igual, grabaron lo mismo, y eso da la hora real de la camara. Hacen falta 2 tomas que coincidan en el desfase
    (o 1 muy clara). Tambien anota las tomas SIMULTANEAS de distintas camaras («simultaneas»: para alternar angulos)."""
    if np is None:
        return []
    avisos = []
    buenos = [i for i in items if i["tipo"] != "foto" and i.get("reloj") != "dudoso" and _envolvente(i) is not None]
    env = {id(i): _envolvente(i) for i in items if i["tipo"] != "foto"}
    for camara, g in _grupos([i for i in items if i.get("reloj") == "dudoso" and i["tipo"] != "foto"]).items():
        desfases = []
        for d in g:
            ed = env.get(id(d))
            if ed is None or not d.get("hora_camara"):
                continue
            for b in buenos:
                if _camara(b) == camara:
                    continue
                r = _cruce(ed, env[id(b)])
                if r:
                    real = _dt(b) + datetime.timedelta(seconds=r[1] * PASO_AUDIO)
                    camara_dt = datetime.datetime.fromisoformat(d["hora_camara"])
                    desfases.append(((real - camara_dt).total_seconds(), r[0], r[2]))
        if not desfases:
            continue
        valores = sorted(x[0] for x in desfases)
        med = valores[len(valores) // 2]
        cerca = [x for x in desfases if abs(x[0] - med) <= 60]
        if len(cerca) >= 2 or (len(cerca) == 1 and cerca[0][1] >= 0.8 and cerca[0][2] >= 40):
            off = sorted(x[0] for x in cerca)[len(cerca) // 2]
            for i in g:
                if i.get("hora_camara"):
                    i["hora"] = (datetime.datetime.fromisoformat(i["hora_camara"]) +
                                 datetime.timedelta(seconds=off)).isoformat(timespec="seconds")
                    i["reloj"] = "audio"
            avisos.append("%s: el reloj estaba mal; la puse en hora por el SONIDO (coincide con %d tomas de otras camaras)."
                          % (camara, len(cerca)))
    # tomas simultaneas de distintas camaras (con la hora ya buena): para alternar angulos en los momentos clave
    con_hora = [i for i in items if i["tipo"] != "foto" and i.get("reloj") != "dudoso" and i.get("dur")]
    for i in con_hora:
        i.pop("simultaneas", None)
    for x in range(len(con_hora)):
        a = con_hora[x]
        a0 = _dt(a)
        for y in range(x + 1, len(con_hora)):
            b = con_hora[y]
            if _camara(a) == _camara(b):
                continue
            desde = (_dt(b) - a0).total_seconds()             # b empieza «desde» s despues que a
            if desde >= a["dur"] or -desde >= b["dur"]:
                continue
            ea, eb = env.get(id(a)), env.get(id(b))
            oido = False
            if ea is not None and eb is not None:             # el sonido afina el desfase (medio segundo) y CONFIRMA
                r = _cruce(ea, eb)
                if r and abs(-r[1] * PASO_AUDIO - desde) <= 90:
                    desde, oido = -r[1] * PASO_AUDIO, True
            if min(a["dur"], desde + b["dur"]) - max(0.0, desde) < 2.0:
                continue
            a.setdefault("simultaneas", []).append({"ruta": b["ruta"], "desde": round(desde, 2), "audio": oido})
            b.setdefault("simultaneas", []).append({"ruta": a["ruta"], "desde": round(-desde, 2), "audio": oido})
    return avisos


def _nombres_originales(cache):
    """(1.5.7) El nombre con que llego cada archivo (antes de renombrarlo), por la lista datos/analisis/nombres.json: lo
    usa _camara para saber de que camara es. Lo nuevo ya lo anota renombrar_cache; esto completa lo de antes."""
    try:
        with open(os.path.join(rutas.ANALISIS, "nombres.json"), encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        return
    original = {}                                # nombre de hoy -> nombre con que llego
    for vez in hist:                             # cada vez, todos los cambios a la vez (dos archivos pueden intercambiar)
        nuevo, movidos = {}, set()
        for a, b in vez.get("cambios") or []:
            va, vb = os.path.basename(a), os.path.basename(b)
            nuevo[vb] = original.get(va, va)
            movidos.add(va)
        for k, v in original.items():
            if k not in movidos and k not in nuevo:
                nuevo[k] = v
        original = nuevo
    for d in cache.values():
        if "nombre_original" not in d and d.get("nombre") in original:
            d["nombre_original"] = original[d["nombre"]]


MAX_FOTOS_IA = 200         # con mas fotos que esto, las fotos se ordenan por su hora (EXIF) y la IA mira solo los videos
PARTE_MALA_TOMA = 0.5      # si en la revision cuadro por cuadro no sirve esta parte de la toma, fuera la toma entera
PARTE_MALA_LARGA = 0.8     # en las tomas largas (mas de TOMA_CORTA_S) solo si casi toda es mala: lo bueno de una
TOMA_CORTA_S = 30.0        # ceremonia de 7 min se usa aunque la mitad sea de espaldas (el armado usa solo los tramos buenos)
PARTE_IA_MAX = 0.6         # la IA no deja fuera mas de esta parte de los archivos (si no, solo los peores)


def _ver_con_ia(cache, lista, log):
    """(1.5.7) Lo que VE la IA local en cada toma (vision_ia, Qwen3-VL en Ollama): momento, escena, etiquetas y si sirve.
    Una vez por archivo (queda en el cache, «ia»). Sin IA local no hace nada."""
    try:
        import vision_ia
    except Exception:
        return
    falta = [(t, r) for t, r in lista if _clave(r) in cache and not cache[_clave(r)].get("error")
             and (cache[_clave(r)].get("ia") or {}).get("v", 0) < vision_ia.VERSION]
    if sum(1 for t, _ in lista if t == "foto") > MAX_FOTOS_IA:
        falta = [p for p in falta if p[0] != "foto"]
    pocas_fotos = sum(1 for t, _ in lista if t == "foto") <= MAX_FOTOS_IA       # (16-nov) las fotos tambien
    largos = [(t, r) for t, r in lista if (t != "foto" or pocas_fotos) and _clave(r) in cache
              and not cache[_clave(r)].get("error")
              and (t == "foto" or cache[_clave(r)].get("dur", 0) >= vision_ia.INSTANTES_DESDE_S)
              and (cache[_clave(r)].get("ia") or {}).get("instantes_v", 0) < vision_ia.INSTANTES_V]
    if not (falta or largos) or not vision_ia.modelo(log):
        return
    if not falta:
        return _instantes_con_ia(cache, largos, log, vision_ia)
    import time
    log("Viendo cada toma con la IA local (%s): %d archivos..." % (vision_ia.modelo(), len(falta)))
    t0 = time.time()

    def una(par):
        d = cache[_clave(par[1])]
        return d, vision_ia.describir(par[0], par[1], d.get("dur", 0.0), log)
    # en paralelo (la persona: «que use el máximo rendimiento»): mientras la GPU mira una toma, la otra ya saca sus
    # cuadros con ffmpeg; si Ollama atiende varias a la vez (OLLAMA_NUM_PARALLEL), tambien se aprovecha
    with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
        for n, (d, ia) in enumerate(ex.map(una, falta), 1):
            if ia:
                d["ia"] = ia
            if n % 10 == 0 or n == len(falta):
                log("  IA %d/%d  %s: %s" % (n, len(falta), d["nombre"], (ia or {}).get("escena", "?")))
    log("La IA local vio %d tomas en %.0f s." % (len(falta), time.time() - t0))
    largos = [(t, r) for t, r in largos if (cache[_clave(r)].get("ia") or {}).get("instantes_v", 0) < vision_ia.INSTANTES_V]
    _instantes_con_ia(cache, largos, log, vision_ia)


def _oir(cache, lista, log):
    """(1.5.9) El oido (oido.py, earshot en la CPU) escucha cada toma en un hilo mientras la IA local la mira en la
    GPU: aplausos, vitores, risas, discursos, musica. Queda en el cache («oido»). Sin earshot no hace nada."""
    try:
        import oido
    except Exception:
        return None
    tomas = [cache[_clave(r)] for t, r in lista if t != "foto" and _clave(r) in cache and oido.falta(cache[_clave(r)])]
    if not tomas or not oido.python_earshot():
        return None
    hilo = threading.Thread(target=oido.escuchar, args=(tomas, log), daemon=True, name="oido")
    hilo.start()
    return hilo


def _instantes_con_ia(cache, largos, log, vision_ia):
    """(1.5.7) La IA mira cada toma cuadro por cuadro (uno cada 3 s): hacia donde apunta la camara, si esta de cabeza,
    si se ve la cara de la gente (la regla de la persona) y en que segundo esta cada momento clave."""
    largos = [(t, r) for t, r in largos if cache[_clave(r)].get("ia")]
    if not largos:
        return
    if not vision_ia.en_gpu():                     # con DaVinci llenando la GPU iria 5-10 veces mas lento: despues
        log("La GPU está ocupada (DaVinci abierto): la revisión cuadro por cuadro de %d tomas se hace la próxima vez "
            "(cierra DaVinci antes de pulsar ▶ para que se haga ahora)." % len(largos))
        return
    import time
    t0 = time.time()
    total = sum(cache[_clave(r)].get("dur", 0.0) for _, r in largos)
    log("La IA local revisa cada toma cuadro por cuadro (uno cada %.0f s, %.0f min de video): hacia dónde apunta, "
        "si se ven las caras..." % (vision_ia.INSTANTES_CADA_S, total / 60.0))

    def una(par):
        d = cache[_clave(par[1])]
        if par[0] == "foto":                    # la foto entera es un solo cuadro (la misma regla de la cara)
            return d, vision_ia.revisar_foto(par[1], log)
        return d, vision_ia.instantes(par[1], d.get("dur", 0.0), log)
    # las largas primero: asi no queda una sola al final mientras las demas ya terminaron
    largos = sorted(largos, key=lambda p: -cache[_clave(p[1])].get("dur", 0.0))
    with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
        for n, (d, inst) in enumerate(ex.map(una, largos), 1):
            if inst is not None:
                d["ia"]["instantes"] = inst
                d["ia"]["instantes_v"] = vision_ia.INSTANTES_V
            if n % 10 == 0 or n == len(largos):
                parte, motivo = vision_ia.parte_mala(d.get("ia"))
                log("  IA revisión %d/%d  %s: %.0f%% no sirve%s" % (
                    n, len(largos), d["nombre"], 100 * parte,
                    " (%s)" % vision_ia.MOTIVOS.get(motivo, motivo) if motivo else ""))
    cuadros = [x for _, r in largos for x in (cache[_clave(r)]["ia"].get("instantes") or [])]
    claves = sum(1 for x in cuadros if set(x[1]) & {"beso", "anillos", "votos", "primer_baile", "pastel", "brindis",
                                                       "entrada"})
    malos = {}
    for x in cuadros:
        if x[2] is False and len(x) > 3:                  # (en el dron, la falta de caras no cuenta en el armado)
            malos[x[3]] = malos.get(x[3], 0) + 1
    log("La IA local revisó %d cuadros en %.0f s: %d momentos clave; no sirven %d (%s)." % (
        len(cuadros), time.time() - t0, claves, sum(malos.values()),
        ", ".join("%s %d" % (vision_ia.MOTIVOS.get(k, k), v) for k, v in sorted(malos.items(), key=lambda kv: -kv[1]))
        or "ninguno"))


def _en_orden(seq, prohibidos=()):
    """Momentos de una secuencia en el orden del dia (MAQUILLAJE -> IGLESIA -> FIESTA, sin volver atras) que menos
    contradicen a la IA: contradecir lo que la IA vio cuesta 1; cambiar el momento por hora/color de una toma que la IA no
    vio (o no supo), 0,3. Asi una toma suelta mal vista («hombre de traje» en plena fiesta = preparativos) o que la IA no
    sabe (el dron sobre la iglesia, una foto) toma el momento de las de alrededor."""
    n, K = len(seq), len(MOMENTOS)
    if not n:
        return []
    costo = []
    for it in seq:
        ia = (it.get("ia") or {}).get("momento")
        if ia in MOMENTOS:
            fila = [0.0 if ia == m else 1.0 for m in MOMENTOS]
        else:
            fila = [0.0 if it.get("momento") == m else 0.3 for m in MOMENTOS]
        costo.append([c + (5.0 if m in prohibidos else 0.0) for c, m in zip(fila, MOMENTOS)])
    dp = [costo[0][:]]
    atras = [[0] * K]
    for i in range(1, n):
        fila, desde = [], []
        for k in range(K):
            j = min(range(k + 1), key=lambda j: (dp[i - 1][j], j != k))       # empate: seguir en el mismo momento
            fila.append(dp[i - 1][j] + costo[i][k])
            desde.append(j)
        dp.append(fila)
        atras.append(desde)
    k = min(range(K), key=lambda k: dp[-1][k])
    out = [0] * n
    for i in range(n - 1, -1, -1):
        out[i] = k
        k = atras[i][k]
    return [MOMENTOS[k] for k in out]


def _segun_lo_que_ve(items, fecha):
    """(1.5.7) Lo que ve la IA local manda sobre la hora y el color (que siempre repartian tres momentos, aunque el evento
    no tuviera maquillaje). Las tomas que la IA no sabe (OTRO) y tienen el reloj dudoso toman el momento de sus vecinas.
    Las de reloj dudoso que cambian de momento se reparten de nuevo dentro de su momento, en el mismo orden."""
    if not any((i.get("ia") or {}).get("momento") in MOMENTOS for i in items):
        return
    # en orden: las de reloj bueno por su hora (todas las camaras juntas); las de reloj dudoso, en el orden de su camara
    confiables = sorted([i for i in items if i.get("reloj") != "dudoso"], key=lambda i: i["hora"])
    dud = [i for i in items if i.get("reloj") == "dudoso"]
    secuencias = [confiables] if confiables else []
    for g in _grupos(dud).values():
        sin_hora = g[0].get("origen_hora") == "archivo"
        secuencias.append(sorted(g, key=lambda i: _numero(i["nombre"]) if sin_hora else (i.get("hora_camara") or i["hora"],
                                                                                        i["nombre"])))
    # si la IA vio casi todo y NO vio preparativos (maquillaje, vestido, traje), el evento no los tiene: no se fuerzan
    # (antes siempre habia tres momentos y la ceremonia acababa como MAQUILLAJE)
    # (cuentan los preparativos que el orden del dia CONFIRMA: una toma suelta de la fiesta que la IA creyo «traje» no)
    resultado = [_en_orden(seq) for seq in secuencias]
    confirmados = any(m == "MAQUILLAJE" and (it.get("ia") or {}).get("momento") == "MAQUILLAJE"
                      for seq, ms in zip(secuencias, resultado) for it, m in zip(seq, ms))
    if not confirmados and sum(1 for i in items if i.get("ia")) >= 0.6 * len(items):
        resultado = [_en_orden(seq, ("MAQUILLAJE",)) for seq in secuencias]
    for seq, ms in zip(secuencias, resultado):
        for it, m in zip(seq, ms):
            ia = (it.get("ia") or {}).get("momento")
            it["por"] = "ia" if ia == m else ("ia (orden del dia)" if ia in MOMENTOS or it["momento"] != m else it.get("por"))
            it["momento"] = m
    dud.sort(key=lambda i: i["hora"])
    rango = {}
    for m in MOMENTOS:
        ms = sorted(_min(i["hora"], fecha) for i in items if i.get("reloj") != "dudoso" and i["momento"] == m)
        if ms:
            rango[m] = (ms[len(ms) // 10], ms[(len(ms) * 9) // 10])
    sinteticos = {"MAQUILLAJE": (10 * 60, 13 * 60), "IGLESIA": (13 * 60 + 30, 15 * 60), "FIESTA": (16 * 60, 23 * 60)}
    for m in MOMENTOS:
        sel = [i for i in dud if i["momento"] == m]
        lo, hi = rango.get(m) or sinteticos[m]
        for n, it in enumerate(sel):
            x = lo + (hi - lo) * (n + 0.5) / len(sel)
            it["hora"] = (datetime.datetime.combine(fecha, datetime.time()) +
                          datetime.timedelta(minutes=x)).isoformat(timespec="seconds")


def renombrar_cache(cambios):
    """(1.5.7) Los archivos se renombraron en su sitio [(ruta_vieja, ruta_nueva)]: lo ya medido sigue valiendo (la clave
    es nombre|tamaño), asi no se vuelve a leer ningun video. Devuelve cuantos paso."""
    try:
        with open(_cache_ruta(), encoding="utf-8") as f:
            todo = json.load(f)
    except Exception:
        return 0
    cache = todo.get("cache", {})
    n = 0
    for viejo, nuevo in cambios:
        try:
            tam = os.path.getsize(nuevo)
        except OSError:
            continue
        kv, kn = "%s|%d" % (os.path.basename(viejo), tam), "%s|%d" % (os.path.basename(nuevo), tam)
        if kv in cache and kv != kn:
            d = cache.pop(kv)
            d.setdefault("nombre_original", os.path.basename(viejo))
            d["ruta"], d["nombre"] = nuevo, os.path.basename(nuevo)
            cache[kn] = d
            n += 1
    todo["cache"] = cache
    _guardar_json(_cache_ruta(), todo)
    return n


def _organizar(cache, lista, base, log):
    """Del material medido (cache) a la lista ordenada y clasificada que usan las plantillas."""
    vivos = {_clave(r) for _, r in lista}
    cache = {k: v for k, v in cache.items() if k in vivos}
    items, malos = [], []
    for k in sorted(cache):
        d = dict(cache[k])
        if d.get("error") or not d.get("hora"):
            malos.append("%s (%s)" % (d["nombre"], d.get("error", "sin hora")))
            continue
        if d["tipo"] != "foto" and d.get("dur", 0) <= 0:
            malos.append("%s (sin duración)" % d["nombre"])
            continue
        items.append(d)
    for m in malos:
        log("No se pudo leer %s: no se usa." % m)
    if not items:
        return cache, {"fecha": None, "items": [], "huella": huella(base), "clasificacion": {},
                       "avisos": ["No se pudo leer ningún archivo: %s" % "; ".join(malos[:5])] if malos else [],
                       "camaras": []}
    cfg = clasificar(items, base, log)
    avisos = cfg.pop("_avisos", [])
    camaras = cfg.pop("_camaras", [])
    if malos:
        avisos.append("%d archivo%s dañado%s o incompleto%s (no se usan): %s" % (
            len(malos), "s" if len(malos) > 1 else "", "s" if len(malos) > 1 else "", "s" if len(malos) > 1 else "",
            ", ".join(malos[:4]) + ("…" if len(malos) > 4 else "")))
    items.sort(key=lambda i: i["hora"])
    res = {"fecha": cfg["fecha"], "items": items, "huella": huella(base), "clasificacion": cfg,
           "avisos": avisos, "camaras": camaras}
    return cache, res


def _guardar(cache, res):
    _guardar_json(_cache_ruta(), {"version": VERSION, "cache": cache, "fecha": res["fecha"], "items": res["items"],
                                  "huella": res.get("huella", ""),
                                  "avisos": res.get("avisos", []), "camaras": res.get("camaras", []),
                                  "momentos": (res.get("clasificacion") or {}).get("momentos")}, indent=1)


def _resumen_log(items, log):
    for mom in MOMENTOS:
        sel = [i for i in items if i["momento"] == mom and not i["descartar"]]
        vids = [i for i in sel if i["tipo"] != "foto"]
        log("%-10s %3d fotos | %2d videos (%2d dron) | %5.1f min de video" % (
            mom, sum(1 for i in sel if i["tipo"] == "foto"), len(vids),
            sum(1 for i in vids if i["tipo"] == "dron"), sum(i["dur"] for i in vids) / 60.0))


def analizar(base=DEF_BASE, log=print, hilos=4):
    lista = listar(base)
    if not lista:
        log("No hay material: suelta la carpeta del evento (fotos JPG y videos).")
        return {"fecha": None, "items": [], "huella": "", "clasificacion": {}, "avisos": [], "camaras": []}
    os.makedirs(rutas.ANALISIS, exist_ok=True)
    cache = _leer_cache()
    for _, r in lista:                  # la ruta guardada sigue al archivo
        if _clave(r) in cache:
            cache[_clave(r)]["ruta"] = r
    if Image is None:
        log("Aviso: falta Pillow (python -m pip install pillow): las fotos se ordenan por fecha de archivo.")
    faltan = [(t, r) for t, r in lista if cache.get(_clave(r), {}).get("v", 1) < VERSION or cache[_clave(r)].get("error")]
    if faltan:
        nuevos = sum(1 for _, r in faltan if _clave(r) not in cache)
        log("Analizando %d archivos%s (de %d)..." % (
            len(faltan), " nuevos" if nuevos == len(faltan) else " (%d nuevos, el resto se completa)" % nuevos, len(lista)))
        hechos = [0]
        candado = threading.Lock()

        def uno(par):
            previo = cache.get(_clave(par[1]))
            try:
                d = _analizar_archivo(par[0], par[1], previo if previo and not previo.get("error") else None)
            except Exception as ex:
                d = {"tipo": par[0], "ruta": par[1], "nombre": os.path.basename(par[1]), "v": VERSION,
                     "error": str(ex)[:120] or ex.__class__.__name__}
            with candado:
                hechos[0] += 1
                if hechos[0] % 25 == 0 or par[0] != "foto":
                    log("  %d/%d  %s" % (hechos[0], len(faltan), d["nombre"]))
            return par[1], d
        videos = [p for p in faltan if p[0] != "foto"]
        fotos = [p for p in faltan if p[0] == "foto"]
        with ThreadPoolExecutor(hilos) as ex:
            for r, d in ex.map(uno, fotos):
                cache[_clave(r)] = d
        # los videos pesan: 3 a la vez, o mas si la PC tiene nucleos de sobra (hasta 6: el disco y el decodificador de
        # la GPU tambien tienen limite)
        with ThreadPoolExecutor(max(3, min(6, (os.cpu_count() or 4) // 2))) as ex:
            for r, d in ex.map(uno, videos):
                cache[_clave(r)] = d
    _nombres_originales(cache)
    oir = _oir(cache, lista, log)               # (1.5.9) el oido (CPU) escucha mientras la IA local (GPU) mira
    _ver_con_ia(cache, lista, log)
    if oir:
        if oir.is_alive():
            log("El oído termina de escuchar...")
        oir.join()
    cache, res = _organizar(cache, lista, base, log)
    _guardar(cache, res)
    if res["items"]:
        _resumen_log(res["items"], log)
    return res


def reclasificar(base=DEF_BASE, log=print):
    """Vuelve a ordenar por momento lo ya medido (rapido: no lee los videos). Lo nuevo sin medir queda fuera."""
    lista = [(t, r) for t, r in listar(base)]
    cache = _leer_cache()
    lista = [(t, r) for t, r in lista if _clave(r) in cache]
    cache, res = _organizar(cache, lista, base, log)
    if res["items"]:
        _guardar(cache, res)
    return res


CAMPOS_VENTANA = ("nombre", "tipo", "hora", "dur", "momento", "por", "tramos", "descartar", "horizontal")


def _ventana_ruta():
    return os.path.join(rutas.ANALISIS, "material_ventana.json")


def leer_ultimo():
    """El ultimo analisis guardado (para la ventana), sin medir nada. {} si no hay.
    El analisis completo pesa varios MB (la «vista» de cada medio segundo de cada video) y leerlo frena la ventana
    unas decimas (medido: 50 ms con el candado de Python tomado). La ventana solo pinta unos pocos datos de cada
    archivo: se guardan aparte, en un resumen de pocos KB que se rehace solo cuando el analisis es mas nuevo."""
    completo, ligero = _cache_ruta(), _ventana_ruta()
    try:
        if os.path.getmtime(ligero) >= os.path.getmtime(completo):
            with open(ligero, encoding="utf-8") as f:
                return json.load(f)
    except (OSError, ValueError):
        pass
    try:
        with open(completo, encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        return {}
    res = {k: j.get(k) for k in ("fecha", "avisos", "camaras", "momentos", "huella")}
    res["items"] = [{c: i[c] for c in CAMPOS_VENTANA if c in i} for i in j.get("items") or []]
    try:
        tmp = ligero + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(tmp, ligero)
    except OSError:
        pass
    return res


if __name__ == "__main__":
    import sys
    analizar(sys.argv[1] if len(sys.argv) > 1 else DEF_BASE)
