# -*- coding: utf-8 -*-
"""
analizar_material.py - Analiza en local (sin internet) las fotos, videos y tomas de dron del evento
y los clasifica por momento: MAQUILLAJE, IGLESIA o FIESTA (los mismos nombres que los marcadores
de las plantillas).

  - Lee la hora real de cada archivo: EXIF de las fotos, metadatos del iPhone, nombre de archivo DJI,
    hora de la camara (Nikon/Sony...). Se puede corregir el reloj de una camara en CLASIFICACION_EVENTO.json.
  - Mide duracion, fps, orientacion y brillo, y detecta tramos negros (ffmpeg blackdetect) para no usarlos.
  - Clasifica por hora con CLASIFICACION_EVENTO.json (se crea solo y se puede editar a mano).
  - Guarda todo en PROGRAMA\\datos\\analisis\\material.json. Es cache: solo vuelve a analizar lo nuevo o cambiado.

Uso suelto:   python analizar_material.py
Desde codigo: analizar(base, log=print) -> dict con "fecha", "items", "huella", "clasificacion"
"""
import os
import re
import json
import datetime
import subprocess
from concurrent.futures import ThreadPoolExecutor

import rutas

DEF_BASE = rutas.BASE
CARPETAS = rutas.CARPETAS             # {"foto": .../1 MATERIAL/FOTOS, "video": .../VIDEOS, "dron": .../DRON}
EXT = {"foto": {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".webp"},
       "video": {".mp4", ".mov", ".mkv", ".avi", ".mxf", ".m4v", ".mts", ".m2ts", ".wmv"}}
EXT["dron"] = EXT["video"]
MOMENTOS = ["MAQUILLAJE", "IGLESIA", "FIESTA"]
ARCHIVO_CLASIF = os.path.basename(rutas.CLASIFICACION)
SIN_VENTANA = rutas.SIN_VENTANA        # que ffmpeg no abra ventanas negras

try:
    from PIL import Image, ImageOps
except ImportError:      # sin Pillow: las fotos se usan igual, sin brillo ni EXIF
    Image = None


def _run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=SIN_VENTANA)


def _fecha(s):
    m = re.match(r"\s*(\d{4})[:-](\d{2})[:-](\d{2})[T ](\d{2}):(\d{2}):(\d{2})", s or "")
    return datetime.datetime(*map(int, m.groups())) if m else None


def listar(base):
    """[(tipo, ruta)] de todo el material, en orden."""
    out = []
    for tipo, raiz in CARPETAS.items():
        for r, _, fs in os.walk(raiz):
            for f in sorted(fs):
                if not f.startswith(("~", ".")) and os.path.splitext(f)[1].lower() in EXT[tipo]:
                    out.append((tipo, os.path.join(r, f)))
    return out


def huella(base):
    """Firma del material (nombre, tamano, fecha): cambia cuando se sube, borra o termina de copiar algo."""
    h = []
    for tipo, ruta in listar(base):
        try:
            st = os.stat(ruta)
            h.append("%s|%d|%d" % (os.path.relpath(ruta, base), st.st_size, int(st.st_mtime)))
        except OSError:
            pass
    return "\n".join(h)


# ------------------------------------------------------------------ analisis de un archivo
def _info_foto(ruta):
    d = {"hora": None, "origen_hora": "archivo", "horizontal": True, "brillo": 0.5}
    if Image is not None:
        try:
            im = Image.open(ruta)
            ex = im.getexif()
            dt = _fecha(ex.get_ifd(0x8769).get(36867) or ex.get(306))
            if dt:
                d["hora"], d["origen_hora"] = dt, "exif"
            im.draft("L", (256, 256))
            im = ImageOps.exif_transpose(im).convert("L")
            im.thumbnail((128, 128))
            d["horizontal"] = im.width >= im.height
            d["brillo"] = round(sum(im.getdata()) / (255.0 * im.width * im.height), 3)
        except Exception:
            pass
    return d


def _info_video(ruta):
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", ruta], 120)
    j = json.loads(r.stdout or "{}")
    fmt = j.get("format", {})
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    tags = {k.lower(): val for k, val in (fmt.get("tags") or {}).items()}
    num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    rot = 0
    for sd in v.get("side_data_list") or []:
        rot = int(sd.get("rotation", rot) or 0)
    rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
    # hora local: iPhone (trae zona horaria) > DJI (nombre de archivo) > hora de la camara > fecha del archivo
    hora, origen = None, "archivo"
    if tags.get("com.apple.quicktime.creationdate"):
        hora, origen = _fecha(tags["com.apple.quicktime.creationdate"]), "iphone"
    if hora is None:
        m = re.search(r"DJI_(\d{14})", os.path.basename(ruta))
        if m:
            hora, origen = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S"), "dji"
    if hora is None and tags.get("creation_time"):
        hora, origen = _fecha(tags["creation_time"]), "camara"
    return {"hora": hora, "origen_hora": origen, "dur": float(fmt.get("duration") or 0), "fps": round(fps, 3),
            "ancho": v.get("width"), "alto": v.get("height"), "rotacion": rot,
            "horizontal": (v.get("width") or 16) >= (v.get("height") or 9) if abs(rot) % 180 == 0
            else (v.get("height") or 9) >= (v.get("width") or 16)}


def _oscuros(ruta):
    """Tramos negros (seg). Solo decodifica fotogramas clave: rapido incluso en 4K."""
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-skip_frame", "nokey", "-i", ruta, "-an",
              "-vf", "scale=320:-2,blackdetect=d=1.5:pix_th=0.10:pic_th=0.92", "-f", "null", "-"])
    rangos = []
    for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", r.stderr):
        a, b = round(float(a), 2), round(float(b), 2)
        if rangos and a - rangos[-1][1] < 3.0:      # une negros separados por menos de 3 s
            rangos[-1][1] = b
        else:
            rangos.append([a, b])
    return rangos


PASO_CALIDAD = 0.5          # segundos por muestra de calidad


def _calidad(ruta):
    """Puntaje 0-1 por cada medio segundo del video: nitidez, exposicion y estabilidad (sin temblor).
    Sirve para elegir las mejores tomas en lugar de cortar al azar."""
    try:
        import numpy as np
    except ImportError:
        return []
    w, h = 192, 108
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-hwaccel", "auto", "-i", ruta,
                        "-an", "-vf", "fps=%g,scale=%d:%d,format=gray" % (1 / PASO_CALIDAD, w, h),
                        "-f", "rawvideo", "-"], capture_output=True, timeout=3600, creationflags=SIN_VENTANA)
    datos = np.frombuffer(r.stdout, dtype=np.uint8)
    n = datos.size // (w * h)
    if n < 1:
        return []
    f = datos[:n * w * h].reshape(n, h, w).astype(np.float32) / 255.0
    lap = f[:, 1:-1, 2:] + f[:, 1:-1, :-2] + f[:, 2:, 1:-1] + f[:, :-2, 1:-1] - 4 * f[:, 1:-1, 1:-1]
    nitidez = lap.reshape(n, -1).var(axis=1)
    brillo = f.reshape(n, -1).mean(axis=1)
    mov = np.zeros(n, dtype=np.float32)
    if n > 1:
        mov[1:] = np.abs(np.diff(f, axis=0)).reshape(n - 1, -1).mean(axis=1)
        mov[0] = mov[1]
    s_nit = np.clip(nitidez / (np.median(nitidez) + 1e-9), 0, 1.6) / 1.6
    s_exp = np.clip((brillo - 0.04) / 0.10, 0, 1) * np.clip((0.97 - brillo) / 0.10, 0, 1)
    med = float(np.median(mov)) + 1e-6
    s_est = np.clip(1.0 - (mov - 2 * med) / (4 * med), 0.25, 1.0)
    return [round(float(x), 3) for x in (s_nit ** 0.7) * s_exp * s_est]


def _color(ruta):
    """Por cada medio segundo: [luz media, negro (percentil 2), saturacion media, R, G, B de los grises,
    fraccion de grises]. Sirve para igualar exposicion y balance de blancos entre tomas."""
    try:
        import numpy as np
    except ImportError:
        return []
    w, h = 96, 54
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-hwaccel", "auto", "-i", ruta,
                        "-an", "-vf", "fps=%g,scale=%d:%d,format=rgb24" % (1 / PASO_CALIDAD, w, h),
                        "-f", "rawvideo", "-"], capture_output=True, timeout=3600, creationflags=SIN_VENTANA)
    datos = np.frombuffer(r.stdout, dtype=np.uint8)
    n = datos.size // (w * h * 3)
    if n < 1:
        return []
    f = datos[:n * w * h * 3].reshape(n, w * h, 3).astype(np.float32) / 255.0
    luz = f @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = (mx - mn) / (mx + 1e-4)
    gris = (sat < 0.15) & (luz > 0.15) & (luz < 0.85)          # pixeles casi neutros (paredes, vestido, cielo)
    res = []
    for k in range(n):
        g = gris[k]
        frac = float(g.mean())
        rgb = f[k][g].mean(axis=0) if g.sum() > 20 else np.array([0.0, 0.0, 0.0])
        res.append([round(float(luz[k].mean()), 4), round(float(np.percentile(luz[k], 2)), 4),
                    round(float(sat[k].mean()), 4), round(float(rgb[0]), 4), round(float(rgb[1]), 4),
                    round(float(rgb[2]), 4), round(frac, 4)])
    return res


def _analizar_archivo(tipo, ruta):
    st = os.stat(ruta)
    d = {"tipo": tipo, "ruta": ruta, "nombre": os.path.basename(ruta)}
    if tipo == "foto":
        d.update(_info_foto(ruta))
    else:
        d.update(_info_video(ruta))
        d["oscuros"] = _oscuros(ruta) if d["dur"] > 0 else []
        d["calidad"] = _calidad(ruta) if d["dur"] > 0 else []
        d["color"] = _color(ruta) if d["dur"] > 0 else []
    if d["hora"] is None:
        d["hora"] = datetime.datetime.fromtimestamp(st.st_mtime)
    d["hora"] = d["hora"].isoformat(timespec="seconds")
    return d


# ------------------------------------------------------------------ clasificacion por hora
def _min(hora_iso, fecha):
    dt = datetime.datetime.fromisoformat(hora_iso)
    return (dt - datetime.datetime.combine(fecha, datetime.time())).total_seconds() / 60.0


def _hhmm(minutos):
    minutos = int(max(0, minutos))
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def _a_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _auto(items, fecha):
    """Propone la hora de inicio de IGLESIA y FIESTA buscando los huecos mas grandes del dia."""
    mins = sorted(_min(i["hora"], fecha) for i in items)
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


def clasificar(items, base, log=print):
    ruta = rutas.CLASIFICACION
    cfg = {}
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as ex:
            log("Aviso: %s no se pudo leer (%s); se regenera." % (ARCHIVO_CLASIF, ex))
            cfg = {}
    # correccion de relojes: {"PREFIJO_DEL_ARCHIVO": horas}
    for it in items:
        for pref, horas in (cfg.get("ajuste_horas") or {}).items():
            if it["nombre"].upper().startswith(pref.upper()):
                it["hora"] = (datetime.datetime.fromisoformat(it["hora"]) +
                              datetime.timedelta(hours=float(horas))).isoformat(timespec="seconds")
    fecha = min(datetime.datetime.fromisoformat(i["hora"]) for i in items).date()
    if cfg.get("fecha") != fecha.isoformat() or not cfg.get("momentos"):
        nuevo = {"fecha": fecha.isoformat(), "revisado": False,
                 "momentos": _auto(items, fecha),
                 "archivos": {}, "descartar": [], "zonas_inutiles": {},
                 "ajuste_horas": cfg.get("ajuste_horas", {}),
                 "ayuda": "momentos = hora de inicio de cada momento (HH:MM, puede pasar de 24:00). "
                          "archivos = excepciones {archivo: MOMENTO}. descartar = archivos que no se usan. "
                          "zonas_inutiles = {archivo: [[seg_ini, seg_fin], ...]}. "
                          "ajuste_horas = {PREFIJO: horas} si el reloj de una camara estaba mal. "
                          "Pon revisado=true cuando lo corrijas a mano."}
        cfg = nuevo
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log("Clasificacion automatica creada en %s (revisala si algo cae en el momento equivocado)." % ARCHIVO_CLASIF)
    inicios = sorted(((_a_min(h), m.upper()) for m, h in cfg["momentos"]))
    excep = {k.upper(): v.upper() for k, v in (cfg.get("archivos") or {}).items()}
    fuera = {x.upper() for x in cfg.get("descartar") or []}
    inutil = {k.upper(): v for k, v in (cfg.get("zonas_inutiles") or {}).items()}
    for it in items:
        n = it["nombre"].upper()
        m = _min(it["hora"], fecha)
        mom = inicios[0][1]
        for ini, nombre in inicios:
            if m >= ini:
                mom = nombre
        it["momento"] = excep.get(n, mom)
        it["descartar"] = n in fuera
        if n in inutil:
            it["oscuros"] = (it.get("oscuros") or []) + inutil[n]
    return cfg


# ------------------------------------------------------------------ todo junto
def analizar(base=DEF_BASE, log=print, hilos=4):
    lista = listar(base)
    if not lista:
        log("No hay material en 1 MATERIAL (FOTOS, VIDEOS, DRON).")
        return {"fecha": None, "items": [], "huella": "", "clasificacion": {}}
    dir_an = rutas.ANALISIS
    os.makedirs(dir_an, exist_ok=True)
    cache_ruta = os.path.join(dir_an, "material.json")
    cache = {}
    if os.path.exists(cache_ruta):
        try:
            with open(cache_ruta, encoding="utf-8") as f:
                cache = json.load(f).get("cache", {})
        except Exception:
            cache = {}

    def clave(ruta):                    # nombre + tamano: sirve aunque se muevan las carpetas o se pase a Mac
        return "%s|%d" % (os.path.basename(ruta), os.stat(ruta).st_size)

    viejo = {}                          # cache de versiones anteriores: "ruta completa|tamano|fecha"
    for k, v in cache.items():
        partes = k.split("|")
        nueva = "%s|%s" % (re.split(r"[\\/]", partes[0])[-1], partes[1]) if len(partes) == 3 else k
        viejo[nueva] = v
    cache = viejo
    for _, r in lista:                  # la ruta guardada sigue al archivo
        if clave(r) in cache:
            cache[clave(r)]["ruta"] = r

    if Image is None:
        log("Aviso: falta Pillow (python -m pip install pillow): las fotos se ordenan por fecha de archivo.")
    faltan = [(t, r) for t, r in lista if clave(r) not in cache
              or (Image is not None and t == "foto" and cache[clave(r)].get("origen_hora") == "archivo")]
    if faltan:
        log("Analizando %d archivos nuevos (de %d)..." % (len(faltan), len(lista)))
        hechos = [0]

        def uno(par):
            try:
                d = _analizar_archivo(*par)
            except Exception as ex:
                d = {"tipo": par[0], "ruta": par[1], "nombre": os.path.basename(par[1]), "error": str(ex)[:120]}
            hechos[0] += 1
            if hechos[0] % 25 == 0 or par[0] != "foto":
                log("  %d/%d  %s" % (hechos[0], len(faltan), d["nombre"]))
            return par[1], d
        with ThreadPoolExecutor(hilos) as ex:
            for r, d in ex.map(uno, faltan):
                cache[clave(r)] = d
    sin_calidad = [k for t, r in lista for k in [clave(r)] if t != "foto" and "calidad" not in cache.get(k, {"calidad": 0})]
    if sin_calidad:
        log("Midiendo la calidad de %d videos (nitidez, luz, temblor)..." % len(sin_calidad))

        def medir(k):
            cache[k]["calidad"] = _calidad(cache[k]["ruta"])
            log("  calidad lista: %s" % cache[k]["nombre"])
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(medir, sin_calidad))
    sin_color = [k for t, r in lista for k in [clave(r)] if t != "foto" and "color" not in cache.get(k, {"color": 0})]
    if sin_color:
        log("Midiendo luz, negros y balance de blancos de %d videos..." % len(sin_color))

        def medir_color(k):
            cache[k]["color"] = _color(cache[k]["ruta"])
            log("  color listo: %s" % cache[k]["nombre"])
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(medir_color, sin_color))
    vivos = {clave(r) for _, r in lista}
    cache = {k: v for k, v in cache.items() if k in vivos}
    items = []
    for k in sorted(cache):
        d = dict(cache[k])
        if d.get("error") or not d.get("hora"):
            log("No se pudo leer %s (%s)" % (d["nombre"], d.get("error", "sin hora")))
            continue
        if d["tipo"] != "foto" and d.get("dur", 0) <= 0:
            log("Video sin duracion, se omite: %s" % d["nombre"])
            continue
        items.append(d)
    if not items:
        return {"fecha": None, "items": [], "huella": huella(base), "clasificacion": {}}
    cfg = clasificar(items, base, log)
    items.sort(key=lambda i: i["hora"])
    res = {"fecha": cfg["fecha"], "items": items, "huella": huella(base), "clasificacion": cfg}
    with open(cache_ruta, "w", encoding="utf-8") as f:
        json.dump({"cache": cache, "fecha": res["fecha"], "items": items}, f, ensure_ascii=False, indent=1)
    # resumen
    for mom in MOMENTOS:
        sel = [i for i in items if i["momento"] == mom and not i["descartar"]]
        vids = [i for i in sel if i["tipo"] != "foto"]
        log("%-10s %3d fotos | %2d videos (%2d dron) | %5.1f min de video" % (
            mom, sum(1 for i in sel if i["tipo"] == "foto"), len(vids),
            sum(1 for i in vids if i["tipo"] == "dron"), sum(i["dur"] for i in vids) / 60.0))
    return res


if __name__ == "__main__":
    import sys
    analizar(sys.argv[1] if len(sys.argv) > 1 else DEF_BASE)
