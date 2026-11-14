# -*- coding: utf-8 -*-
"""
motor.py - Motor del programa "Trailer XV automatico" (sin interfaz).

  armar(log, ...)        analiza el material y lo arma en las plantillas de DaVinci Resolve
  estado_davinci()       (conectado, proyecto) sin cambiar nada en Resolve
  resumen_carpetas()     cuantos archivos hay en cada carpeta
  abrir_timeline(nombre) muestra una timeline en Resolve
  huella()               firma del material (cambia al subir o terminar de copiar archivos)

Habla con DaVinci por su API de scripting (la misma que usa el MCP de Resolve), todo en local.
"""
import os
import sys
import json
import time
import threading
import subprocess

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # PROGRAMA (motor esta en nucleo/)
if os.path.join(SKILL_DIR, "nucleo") not in sys.path:
    sys.path.insert(0, os.path.join(SKILL_DIR, "nucleo"))
import rutas  # noqa: E402
import analizar_material as am  # noqa: E402

BASE = rutas.BASE
BASE_DATOS = "EVENTOS"          # base de datos de Resolve donde vive el proyecto (si existe en esta compu)
PROYECTO = "EVENTOS CINEMA"     # proyecto con las plantillas universales
PROYECTOS_ANTERIORES = ["TRAILER DE XV"]   # nombre viejo: se sigue encontrando si no se ha renombrado
VERSIONES = ["1min", "3min", "15min", "30min"]
CARPETAS = am.CARPETAS          # {"foto": .../1 MATERIAL/FOTOS, "video": .../VIDEOS, "dron": .../DRON}
ESPERA_ESTABLE = 30             # segundos sin cambios antes de armar (copia terminada)
ESTADO = rutas.ESTADO
CANDADO = threading.Lock()      # una sola conversacion con Resolve a la vez


def leer_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_estado(d):
    am._guardar_json(ESTADO, d)            # escritura segura: si se corta la luz, el estado anterior queda entero


# ------------------------------------------------------------------ prevenir errores
class SinDormir:
    """Mientras arma y renderiza, que la PC no se suspenda (la pantalla si se puede apagar). Va en el hilo que
    trabaja: en Windows el pedido vale mientras ese hilo lo mantenga; en Mac lo sostiene `caffeinate`."""
    def __enter__(self):
        self.proc = None
        try:
            if rutas.ES_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM
            elif sys.platform == "darwin":
                self.proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        except Exception:
            pass
        return self

    def __exit__(self, *_):
        try:
            if rutas.ES_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            elif self.proc is not None:
                self.proc.terminate()
        except Exception:
            pass


GB_POR_VERSION = {"1min": 0.1, "3min": 0.25, "15min": 1.1, "30min": 2.2}     # MOV H.265 medido: ~71 MB por minuto


def espacio_para_render(versiones):
    """(libre_gb, necesita_gb) en el disco de 2 VIDEOS TERMINADOS (con margen para el masterizado)."""
    import shutil
    d = rutas.TERMINADOS
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    libre = shutil.disk_usage(d or rutas.BASE).free / 1e9
    return libre, sum(GB_POR_VERSION.get(v, 2.2) for v in versiones or VERSIONES) * 2 + 1.0


def esperar_copias(log, max_s=180):
    """Si algo de 1 MATERIAL se esta copiando todavia (el Explorador / Finder), espera a que termine: un video a medio
    copiar se leeria cortado."""
    limite = time.time() + max_s
    avisado = False
    while time.time() < limite:
        ahora = time.time()
        recientes = []
        for _, ruta in am.listar(BASE):
            try:
                if ahora - os.path.getmtime(ruta) < 15:
                    recientes.append(ruta)
            except OSError:
                pass
        if not recientes:
            return True
        tam = {r: os.path.getsize(r) for r in recientes if os.path.exists(r)}
        time.sleep(3)
        if all(os.path.exists(r) and os.path.getsize(r) == t for r, t in tam.items()) and \
                all(time.time() - os.path.getmtime(r) >= 6 for r in tam if os.path.exists(r)):
            return True
        if not avisado:
            log("Esperando a que termine de copiarse el material (%s…)." % os.path.basename(recientes[0]))
            avisado = True
    log("Aviso: hay archivos que siguen cambiando; sigo con lo que hay.")
    return False


def huella():
    return am.huella(BASE)


def resumen_carpetas():
    cuenta = {t: 0 for t in CARPETAS}
    for tipo, _ in am.listar(BASE):
        cuenta[tipo] += 1
    return cuenta


# Lo minimo para armar: 8 fotos para los destellos de la intro y al menos un video. El dron es opcional.
MINIMOS = {"foto": 8, "video": 1, "dron": 0}
NOMBRE_CARPETA = {"foto": "FOTOS", "video": "VIDEOS", "dron": "DRON"}


def revisar_material():
    """{"cuenta": {tipo: n}, "faltan": [(tipo, cuantos_faltan)], "ok": bool}"""
    cuenta = resumen_carpetas()
    faltan = [(t, m - cuenta[t]) for t, m in MINIMOS.items() if cuenta[t] < m]
    return {"cuenta": cuenta, "faltan": faltan, "ok": not faltan}


RAW = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".srw"}
CARPETAS_DRON = ("dron", "drone", "aereo", "aéreo", "aerea", "aérea", "mavic")


def tipo_de_archivo(ruta):
    """'foto', 'video' o 'dron' segun la extension. Dron: archivos DJI_ o dentro de una carpeta llamada DRON, Drone,
    Aereo, Mavic... None si no sirve."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext in am.EXT["foto"]:
        return "foto"
    if ext in am.EXT["video"]:
        if os.path.basename(ruta).upper().startswith(("DJI_", "DJI-")):
            return "dron"
        carpeta = os.path.basename(os.path.dirname(ruta)).lower()
        return "dron" if any(p in carpeta for p in CARPETAS_DRON) else "video"
    return None


class Cancelado(Exception):
    pass


def _fecha_rapida(ruta, tipo):
    """El dia de un archivo sin analizarlo entero: EXIF de la foto, nombre (DJI, Pixel, Samsung) o fecha del archivo."""
    import datetime
    try:
        if tipo == "foto" and am.Image is not None:
            with am.Image.open(ruta) as im:
                ex = im.getexif()
                try:
                    sub = ex.get_ifd(0x8769)
                except Exception:
                    sub = {}
                d = am._fecha(sub.get(36867) or sub.get(36868) or ex.get(306))
                if d:
                    return am._jornada(d)
        d = am._hora_de_nombre(os.path.basename(ruta))
        if d:
            return am._jornada(d)
        return am._jornada(datetime.datetime.fromtimestamp(os.path.getmtime(ruta)))
    except Exception:
        return None


def examinar_origen(rutas_origen, forzar_tipo=None):
    """Mira lo que se quiere agregar SIN copiar nada: {"pares": [(ruta, tipo)], "cuenta": {tipo: n}, "bytes": total,
    "otros": {".ext": n} (lo que no se usa: RAW, documentos...), "fecha": "AAAA-MM-DD" | None, "nombre": carpeta soltada}."""
    from collections import Counter
    archivos = []
    for r in rutas_origen:
        if os.path.isdir(r):
            for d, dirs, fs in os.walk(r):
                dirs[:] = sorted(x for x in dirs if not x.startswith((".", "$")) and x.lower() != "anteriores")
                archivos += [os.path.join(d, f) for f in sorted(fs)]
        elif os.path.isfile(r):
            archivos.append(r)
    pares, otros, total = [], Counter(), 0
    for a in archivos:
        nombre = os.path.basename(a)
        if nombre.startswith((".", "~")) or nombre.lower() in ("thumbs.db", "desktop.ini"):
            continue                          # "._DSC0001.JPG" de la Mac en discos externos, temporales
        t = tipo_de_archivo(a)
        if t is not None:
            try:
                tam = os.path.getsize(a)
            except OSError:
                continue
            if tam == 0:
                otros["vacíos"] += 1
                continue
        if t is None:
            otros[os.path.splitext(a)[1].lower() or "sin extensión"] += 1
            continue
        if forzar_tipo:                       # "Agregar" de una carpeta concreta: fotos con fotos, videos con videos
            if (forzar_tipo == "foto") != (t == "foto"):
                continue
            t = forzar_tipo
        pares.append((a, t))
        total += tam
    cuenta = {t: sum(1 for _, x in pares if x == t) for t in CARPETAS}
    votos = Counter()
    for tipo, cuantos in (("foto", 16), ("video", 8), ("dron", 4)):
        grupo = [a for a, t in pares if t == tipo]
        paso = max(1, len(grupo) // cuantos)
        for a in grupo[::paso][:cuantos]:
            d = _fecha_rapida(a, tipo)
            if d:
                votos[d] += 2 if tipo == "foto" else 1
    fecha = votos.most_common(1)[0][0].isoformat() if votos else None
    primero = rutas_origen[0] if rutas_origen else ""
    nombre = os.path.basename(primero.rstrip("\\/")) if os.path.isdir(primero) else ""
    return {"pares": pares, "cuenta": cuenta, "bytes": total, "otros": dict(otros), "fecha": fecha, "nombre": nombre}


def texto_otros(otros):
    """'12 RAW (.nef) · 3 .txt' para avisar de lo que no se uso."""
    if not otros:
        return ""
    raw = sum(n for e, n in otros.items() if e in RAW)
    partes = []
    if raw:
        partes.append("%d RAW (%s): usa los JPG" % (raw, ", ".join(sorted(e for e in otros if e in RAW))))
    resto = sorted(((n, e) for e, n in otros.items() if e not in RAW), reverse=True)
    partes += [("%d vacío%s" % (n, "s" if n > 1 else "")) if e == "vacíos" else "%d %s" % (n, e) for n, e in resto[:4]]
    return " · ".join(partes)


def evento_actual():
    """(nombre, fecha) del material que hay ahora en 1 MATERIAL, segun el ultimo analisis; (None, None) si esta vacio."""
    if not any(resumen_carpetas().values()):
        return None, None
    fecha = None
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            fecha = json.load(f).get("fecha")
    except Exception:
        pass
    if not fecha:                             # sin analizar todavia: una mirada rapida a lo que hay
        from collections import Counter
        votos = Counter()
        lista = am.listar(BASE)
        for tipo, ruta in lista[::max(1, len(lista) // 20)][:20]:
            d = _fecha_rapida(ruta, tipo)
            if d:
                votos[d] += 1
        fecha = votos.most_common(1)[0][0].isoformat() if votos else None
    return leer_estado().get("evento") or fecha or "evento anterior", fecha


def es_otro_evento(fecha_nueva, fecha_actual):
    """True si lo que se suelta es de otro dia (mas de un dia de diferencia: la fiesta pasa de medianoche)."""
    import datetime
    if not fecha_nueva or not fecha_actual:
        return False
    try:
        a, b = datetime.date.fromisoformat(fecha_nueva), datetime.date.fromisoformat(fecha_actual)
    except ValueError:
        return False
    return abs((a - b).days) > 1


def archivar_material(nombre):
    """Evento nuevo: lo que hay en FOTOS / VIDEOS / DRON pasa a 1 MATERIAL/ANTERIORES/<nombre>/ (no se borra nada) y los
    textos del evento (nombres, frase, fecha) quedan en blanco. Devuelve (carpeta, cuantos)."""
    import re
    import shutil
    limpio = re.sub(r'[\\/:*?"<>|]+', " ", str(nombre or "evento anterior")).strip() or "evento anterior"
    destino = os.path.join(rutas.MATERIAL, "ANTERIORES", limpio)
    k = 2
    while os.path.exists(destino) and os.listdir(destino):
        destino = os.path.join(rutas.MATERIAL, "ANTERIORES", "%s (%d)" % (limpio, k))
        k += 1
    n = 0
    for t, carpeta in CARPETAS.items():
        if not os.path.isdir(carpeta):
            continue
        for f in os.listdir(carpeta):
            sub = os.path.join(destino, NOMBRE_CARPETA[t])
            os.makedirs(sub, exist_ok=True)
            shutil.move(os.path.join(carpeta, f), os.path.join(sub, f))
            n += 1
    if os.path.exists(rutas.CLASIFICACION):               # las correcciones a mano eran de ESE evento
        os.makedirs(destino, exist_ok=True)
        shutil.move(rutas.CLASIFICACION, os.path.join(destino, os.path.basename(rutas.CLASIFICACION)))
    est = leer_estado()
    for clave in ("nombre_xv", "frase", "fecha_lugar", "evento_manual", "evento", "huella", "timelines", "resumen_versiones"):
        est.pop(clave, None)
    guardar_estado(est)
    return destino, n


def _huella_rapida(ruta, tam):
    """Huella de un archivo sin leerlo entero (tamano + primer y ultimo trozo): para no copiar dos veces lo mismo."""
    import hashlib
    h = hashlib.sha1(str(tam).encode())
    with open(ruta, "rb") as f:
        h.update(f.read(262144))
        if tam > 524288:
            f.seek(-262144, 2)
            h.update(f.read(262144))
    return h.hexdigest()


def copiar_material(rutas_origen, avance=None, forzar_tipo=None, cancelado=None, examen=None):
    """Copia archivos (o carpetas completas, con subcarpetas) a 1 MATERIAL/FOTOS|VIDEOS|DRON segun su tipo.
    avance(bytes_hechos, bytes_total, nombre, i, n). No pisa nada: el mismo archivo (aunque tenga otro nombre) se omite, y
    otro distinto con el mismo nombre (dos camaras con DSC_0001.JPG) queda como «DSC_0001 (2).JPG».
    Devuelve {"copiados": {tipo: n}, "ya_estaban": n, "otros": {".ext": n}, "bytes": copiados}."""
    import shutil
    examen = examen or examinar_origen(rutas_origen, forzar_tipo)
    pares, total = examen["pares"], max(1, examen["bytes"])
    libre = shutil.disk_usage(rutas.MATERIAL if os.path.isdir(rutas.MATERIAL) else BASE).free
    if examen["bytes"] > libre - 500e6:
        raise RuntimeError("No hay espacio en el disco de 1 MATERIAL: hacen falta %.1f GB y quedan %.1f GB."
                           % (examen["bytes"] / 1e9, libre / 1e9))
    hechos = {t: 0 for t in CARPETAS}
    ya, hecho_b, copiado_b = 0, 0, 0
    indice = {}                                # tipo -> {tamano: [rutas ya en la carpeta]}

    def tamanos(t):
        if t not in indice:
            d = {}
            os.makedirs(CARPETAS[t], exist_ok=True)
            for e in os.scandir(CARPETAS[t]):
                if e.is_file():
                    d.setdefault(e.stat().st_size, []).append(e.path)
            indice[t] = d
        return indice[t]

    for i, (a, t) in enumerate(pares, 1):
        if cancelado and cancelado():
            raise Cancelado()
        tam = os.path.getsize(a)
        nombre = os.path.basename(a)
        if avance:
            avance(hecho_b, total, nombre, i, len(pares))
        iguales = tamanos(t).get(tam) or []
        if iguales:                            # mismo tamano: ¿es el mismo archivo con otro nombre?
            h = _huella_rapida(a, tam)
            if any(os.path.exists(x) and (os.path.samefile(x, a) or _huella_rapida(x, tam) == h) for x in iguales):
                ya += 1
                hecho_b += tam
                continue
        base, ext = os.path.splitext(nombre)
        destino, k = os.path.join(CARPETAS[t], nombre), 2
        while os.path.exists(destino):
            destino = os.path.join(CARPETAS[t], "%s (%d)%s" % (base, k, ext))
            k += 1
        parcial = destino + ".copiando"        # si se corta (disco lleno, se desconecta), no queda un video a medias
        try:
            with open(a, "rb") as fo, open(parcial, "wb") as fd:
                while True:
                    if cancelado and cancelado():
                        raise Cancelado()
                    buf = fo.read(8 << 20)
                    if not buf:
                        break
                    fd.write(buf)
                    hecho_b += len(buf)
                    if avance:
                        avance(hecho_b, total, nombre, i, len(pares))
            shutil.copystat(a, parcial)        # la fecha del archivo se conserva: el analizador la usa
            os.replace(parcial, destino)
        except BaseException:
            try:
                os.remove(parcial)
            except OSError:
                pass
            raise
        tamanos(t).setdefault(tam, []).append(destino)
        hechos[t] += 1
        copiado_b += tam
    if avance:
        avance(total, total, "", len(pares), len(pares))
    return {"copiados": hechos, "ya_estaban": ya, "otros": examen["otros"], "bytes": copiado_b}


# ------------------------------------------------------------------ plan sin DaVinci
class _PlantillaFalsa:
    def __init__(self, nombre, d):
        self.nombre, self.d = nombre, d

    def GetName(self):
        return self.nombre

    def GetSetting(self, clave):
        return self.d.get("fps", 24.0) if clave == "timelineFrameRate" else None

    def GetMarkers(self):
        return {int(f): m for f, m in (self.d.get("marcadores") or {}).items()}


class _ResolveFalso:
    """Lo minimo de la API para PLANIFICAR sin DaVinci abierto: las 4 plantillas con sus marcadores (los que trae el
    programa en recursos/plantillas_marcadores.json)."""
    def __init__(self, plantillas):
        self.tls = [_PlantillaFalsa(n, d) for n, d in plantillas.items()]

    def GetProjectManager(self):
        return self

    def GetCurrentProject(self):
        return self

    def GetTimelineCount(self):
        return len(self.tls)

    def GetTimelineByIndex(self, i):
        return self.tls[i - 1]


def guardar_plan(rep):
    """El ultimo plan previo queda en datos/analisis/plan_previo.json (lo lee la ventana y las pruebas)."""
    if rep:
        am._guardar_json(os.path.join(rutas.ANALISIS, "plan_previo.json"),
                         {"evento": rep.get("evento"), "versiones": rep.get("versiones", [])})


def plan_previo(analisis, log=print, solo=None, tipo_evento="xv", evento="", **_):
    """El plan de cada version (cuantos planos por zona, camara lenta, estabilizar) SIN conectar con DaVinci: usa los
    marcadores de las plantillas que trae el programa. Devuelve el reporte de build_trailers o None."""
    try:
        with open(os.path.join(rutas.RECURSOS, "plantillas_marcadores.json"), encoding="utf-8") as f:
            plantillas = json.load(f)
    except Exception:
        return None
    import re
    repiten = {}                                # version -> planos que repiten video (un solo aviso al final, no uno por zona)

    def decir(*a, **k):
        t = " ".join(str(x) for x in a)
        m = re.match(r"AVISO: (\S+) .*?: (\d+) planos repiten video", t)
        if m:
            repiten[m.group(1)] = repiten.get(m.group(1), 0) + int(m.group(2))
        else:
            log(t.replace(" | 0 cortes al ritmo", ""))      # el ritmo se mide despues, ya con la musica en DaVinci

    ruta = rutas.codigo("build_trailers.py")
    g = {"__name__": "build_trailers", "resolve": _ResolveFalso(plantillas), "BASE": BASE, "ANALISIS": analisis,
         "EVENTO": evento or None, "SOLO": solo or None, "REHACER": True, "DRY_RUN": True, "SIN_RESOLVE": True,
         "TIPO_EVENTO": tipo_evento, "print": decir}
    with open(ruta, encoding="utf-8") as f:
        exec(compile(f.read(), ruta, "exec"), g)
    if repiten:
        claves = sorted(repiten, key=lambda v: int(re.sub(r"\D", "", v) or 0))
        vs = [re.sub(r"(\d+)", r"\1 ", v) for v in claves]              # «15min» -> «15 min»
        lista = vs[0] if len(vs) == 1 else ", ".join(vs[:-1]) + " y " + vs[-1]
        if len(vs) == 1:
            log("Con el video que hay, la versión de %s repite %d tomas: con más video queda mejor." % (lista, repiten[claves[0]]))
        else:
            log("Con el video que hay, las versiones de %s repiten tomas (%s): con más video quedan mejor."
                % (lista, " · ".join("%s: %d" % (v, repiten[k]) for v, k in zip(vs, claves))))
    res = g.get("result")
    if isinstance(res, dict):
        res["repiten"] = repiten
    return res


def chequeo():
    """Chequeo de arranque: [(nombre, ok, detalle)]. No toca DaVinci."""
    import shutil
    res = []
    rutas.crear_carpetas()
    m = revisar_material()
    c = m["cuenta"]
    res.append(("Fotos de la intro", c["foto"] >= MINIMOS["foto"],
                "%d fotos" % c["foto"] if c["foto"] >= MINIMOS["foto"] else
                "faltan %d fotos en 1 MATERIAL/FOTOS" % (MINIMOS["foto"] - c["foto"])))
    res.append(("Videos", c["video"] >= MINIMOS["video"],
                "%d videos" % c["video"] if c["video"] else "no hay videos en 1 MATERIAL/VIDEOS"))
    res.append(("Dron", True, "%d tomas" % c["dron"] if c["dron"] else "sin tomas de dron (opcional)"))
    ff = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    res.append(("ffmpeg", ff, "listo" if ff else "falta ffmpeg"))
    dv = os.path.exists(rutas.SCRIPT_LIB) and os.path.isdir(rutas.SCRIPT_API)
    res.append(("DaVinci Resolve", dv, "instalado" if dv else "no encuentro DaVinci Resolve Studio"))
    pl = os.path.exists(rutas.PLANTILLAS_DRP)
    res.append(("Plantillas", pl, "listas" if pl else "falta %s" % os.path.basename(rutas.PLANTILLAS_DRP)))
    try:
        os.makedirs(rutas.DIR_LUT_MCP, exist_ok=True)
        lut = os.access(rutas.DIR_LUT_MCP, os.W_OK)
    except Exception:
        lut = False
    res.append(("Color y ruido", lut, "carpeta de LUT lista" if lut else "sin permiso en la carpeta de LUT"))
    try:
        import numpy  # noqa: F401
        lib = True
    except Exception:
        lib = False
    res.append(("Ritmo de la musica", lib, "listo" if lib else "falta numpy"))
    return res


def _resumen(items):
    res = {}
    for it in items:
        if it.get("descartar") or not it.get("momento"):
            continue
        r = res.setdefault(it["momento"], {"fotos": 0, "videos": 0, "dron": 0, "min": 0.0})
        r["fotos" if it["tipo"] == "foto" else "videos"] += 1
        r["dron"] += it["tipo"] == "dron"
        r["min"] += it.get("dur", 0) / 60.0 if it["tipo"] != "foto" else 0
    return res


def resumen_material():
    """Fotos/videos por momento segun el ultimo analisis guardado (sin volver a analizar)."""
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            return _resumen(json.load(f).get("items", []))
    except Exception:
        return {}


def _dvr():
    api = os.environ.get("RESOLVE_SCRIPT_API") or rutas.SCRIPT_API
    lib = os.environ.get("RESOLVE_SCRIPT_LIB") or rutas.SCRIPT_LIB
    os.environ["RESOLVE_SCRIPT_API"], os.environ["RESOLVE_SCRIPT_LIB"] = api, lib
    if rutas.CONGELADO:
        # Desde el .exe: fusionscript busca python3.dll en PYTHON3HOME y sus DLL en la carpeta de Resolve
        os.environ.setdefault("PYTHON3HOME", rutas.PROGRAMA)
        if rutas.ES_WIN and os.path.isdir(os.path.dirname(lib)):
            try:
                os.add_dll_directory(os.path.dirname(lib))
            except Exception:
                pass
    mods = os.path.join(api, "Modules")
    if not os.path.exists(lib) or not os.path.isdir(mods):
        raise RuntimeError("No encuentro DaVinci Resolve Studio en esta computadora. Instálalo (la versión Studio: la "
                           "gratuita no deja que otros programas la controlen), ábrelo una vez y vuelve a pulsar ▶.")
    if mods not in sys.path:
        sys.path.append(mods)
    try:
        import DaVinciResolveScript
    except ImportError as ex:
        raise RuntimeError("DaVinci Resolve está instalado pero no se pudo cargar su conexión (%s). Reinstala DaVinci "
                           "Resolve Studio o actualízalo." % ex)
    return DaVinciResolveScript


def _sin_titulo(nombre):
    n = (nombre or "").strip().lower()
    return not n or n.startswith(("untitled project", "proyecto sin t", "sin titulo", "sin título"))


def resolve_abierto():
    """True si el proceso de DaVinci Resolve esta corriendo (sin tocar su API: nunca se cuelga)."""
    try:
        if rutas.ES_WIN:
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH"], capture_output=True,
                               text=True, timeout=5, creationflags=rutas.SIN_VENTANA)
            return "resolve.exe" in r.stdout.lower()
        r = subprocess.run(["pgrep", "-x", "Resolve"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def estado_davinci():
    """(abierto, proyecto). Sin usar la API de Resolve ni el candado, para no frenar nunca al boton Play:
    el nombre del proyecto se lee del titulo de la ventana en Windows."""
    if not resolve_abierto():
        return False, ""
    proyecto = ""
    for t in _titulos_resolve(todos=True):
        if t.startswith("DaVinci Resolve") and " - " in t:
            proyecto = t.split(" - ", 1)[1].strip()
    return True, proyecto


def dialogos_resolve(exe="resolve.exe"):
    """Titulos de ventanas de Resolve que no son la principal (p. ej. 'Crear proyecto', 'Organizador de
    proyectos'). Con un cuadro asi abierto, la API se bloquea o no responde."""
    return _titulos_resolve(False, exe)


def _titulos_resolve(todos=False, exe="resolve.exe"):
    """Titulos de las ventanas visibles de Resolve (Windows). todos=False: sin la ventana principal."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    titulos = []

    def es_resolve(pid):
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(520)
            n = wintypes.DWORD(520)
            return bool(k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))) and \
                buf.value.lower().endswith("\\" + exe)
        finally:
            k32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, buf, 256)
            if buf.value and es_resolve(pid.value):
                titulos.append(buf.value)
        return True
    try:
        u32.EnumWindows(cada, 0)
    except Exception:
        return []
    return titulos if todos else [t for t in titulos if not t.startswith("DaVinci Resolve")]


ORGANIZADOR = ("organizador de proyectos", "project manager")   # se cierra solo al abrir el proyecto


def _bloqueos(incluir_organizador):
    return [t for t in dialogos_resolve()
            if incluir_organizador or not t.lower().startswith(ORGANIZADOR)]


CUADROS_NUESTROS = ("crear proyecto", "create project", "guardar proyecto", "save project")


def _cerrar_cuadros(titulos):
    """Cierra (= Cancelar) ventanas de Resolve con esos titulos. Solo Windows."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    hechas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(h, _):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, buf, 256)
        if u32.IsWindowVisible(h) and buf.value.lower().startswith(titulos):
            u32.PostMessageW(h, 0x0010, 0, 0)          # WM_CLOSE
            hechas.append(buf.value)
        return True
    u32.EnumWindows(cada, 0)
    return len(hechas)


class _Vigilante:
    """Mientras se abre el proyecto: si Resolve saca un cuadro que bloquea la API ("Crear proyecto"...),
    lo cancela para que la llamada no se quede esperando para siempre."""
    def __init__(self, log):
        self.log, self.fin = log, threading.Event()

    def __enter__(self):
        def vigilar():
            while not self.fin.wait(2.0):
                if _cerrar_cuadros(CUADROS_NUESTROS):
                    self.log("AVISO: DaVinci abrio un cuadro que bloqueaba la conexion; se cancelo solo.")
        threading.Thread(target=vigilar, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.fin.set()


def conectar_resolve(log):
    with _Vigilante(log):
        return _conectar_resolve(log)


def _conectar_resolve(log):
    abiertos = _bloqueos(False)
    if abiertos:
        raise RuntimeError("DaVinci tiene abierto: %s. Cierralo y vuelve a intentar."
                           % ", ".join("«%s»" % t for t in abiertos))
    dvr = _dvr()
    r = dvr.scriptapp("Resolve")
    if r is None and rutas.abrir_resolve():
        log("Abriendo DaVinci Resolve...")
        for _ in range(60):
            time.sleep(3)
            r = dvr.scriptapp("Resolve")
            if r is not None and r.GetProjectManager() is not None:
                break
        time.sleep(5)                     # que termine de arrancar antes de pedirle el proyecto
    if r is None or r.GetProjectManager() is None:       # a veces scriptapp devuelve un objeto "hueco"
        raise RuntimeError("No pude conectar con DaVinci Resolve. Abrelo y revisa Preferencias > Sistema > "
                           "General > Scripting externo = Local.")
    pm = r.GetProjectManager()
    actual = pm.GetCurrentProject()
    nombres = [PROYECTO] + PROYECTOS_ANTERIORES
    if actual is None or actual.GetName() not in nombres:
        log("Abriendo el proyecto %s..." % PROYECTO)
        # Solo se guarda un proyecto con nombre de verdad. Guardar el "Untitled Project" que Resolve abre al
        # arrancar hace salir el cuadro "Crear proyecto" y la API se queda esperando para siempre.
        if actual is not None and not _sin_titulo(actual.GetName()):
            pm.SaveProject()
        bases = [d.get("DbName") for d in (pm.GetDatabaseList() or [])]
        if BASE_DATOS in bases:
            pm.SetCurrentDatabase({"DbType": "Disk", "DbName": BASE_DATOS})
        pm.GotoRootFolder()
        if not any(pm.LoadProject(n) for n in nombres):
            if not os.path.exists(rutas.PLANTILLAS_DRP):
                raise RuntimeError("No encontre el proyecto '%s' en DaVinci ni las plantillas en %s."
                                   % (PROYECTO, rutas.PLANTILLAS_DRP))
            log("Primera vez en esta computadora: instalando las plantillas en DaVinci...")
            if not (pm.ImportProject(rutas.PLANTILLAS_DRP, PROYECTO) and pm.LoadProject(PROYECTO)):
                raise RuntimeError("DaVinci no pudo importar las plantillas (%s)." % rutas.PLANTILLAS_DRP)
        time.sleep(2)
    abiertos = _bloqueos(True)
    if abiertos:
        raise RuntimeError("DaVinci sigue con %s abierto. Cierralo y vuelve a intentar."
                           % ", ".join("«%s»" % t for t in abiertos))
    return r


def reenlazar(project, log=print):
    """Vuelve a enlazar los clips del media pool cuyo archivo ya no esta en esa ruta (carpetas movidas o
    proyecto abierto en otra computadora / Mac). Los busca por nombre en 1 MATERIAL y PROGRAMA/recursos."""
    import re
    mp = project.GetMediaPool()
    perdidos = []

    def recorrer(f):
        for c in f.GetClipList() or []:
            r = c.GetClipProperty("File Path") or ""
            if r and not os.path.exists(r):
                perdidos.append((c, re.split(r"[\\/]", r)[-1]))
        for s in f.GetSubFolderList() or []:
            recorrer(s)
    recorrer(mp.GetRootFolder())
    if not perdidos:
        return 0
    hay = {}
    for raiz in (rutas.MATERIAL, rutas.RECURSOS, rutas.AUDIO):
        for d, _, fs in os.walk(raiz):
            for x in fs:
                hay.setdefault(x.lower(), d)
    por_carpeta = {}
    for c, nombre in perdidos:
        if nombre.lower() in hay:
            por_carpeta.setdefault(hay[nombre.lower()], []).append((c, nombre))
    n = 0
    for d, grupo in por_carpeta.items():
        if mp.RelinkClips([c for c, _ in grupo], d):
            n += len(grupo)
            continue
        for c, nombre in grupo:                       # uno por uno si la carpeta completa no se pudo
            try:
                n += bool(c.ReplaceClip(os.path.join(d, nombre)))
            except Exception:
                pass
    log("Archivos reenlazados en DaVinci: %d%s" % (n, (" (faltan %d que no estan en las carpetas)"
                                                         % (len(perdidos) - n)) if n < len(perdidos) else ""))
    return n


def instalar_fuentes(log=print):
    """Instala para el usuario (sin administrador) las fuentes de los titulos que falten:
    Windows: %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts + registro HKCU. Mac: ~/Library/Fonts."""
    import shutil
    origen = {}                                  # nombre -> carpeta (las del programa y la con licencia guardada aparte)
    for d in rutas.carpetas_fuentes():
        for f in os.listdir(d):
            if f.lower().endswith((".ttf", ".otf")):
                origen.setdefault(f, d)
    if not origen:
        return 0
    archivos = sorted(origen)
    n = 0
    if rutas.ES_MAC:
        destino = os.path.expanduser("~/Library/Fonts")
        os.makedirs(destino, exist_ok=True)
        for f in archivos:
            if not os.path.exists(os.path.join(destino, f)):
                shutil.copy2(os.path.join(origen[f], f), os.path.join(destino, f))
                n += 1
    elif rutas.ES_WIN:
        import winreg
        sistema = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        destino = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
        os.makedirs(destino, exist_ok=True)
        clave = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
        try:
            for f in archivos:
                if os.path.exists(os.path.join(sistema, f)) or os.path.exists(os.path.join(destino, f)):
                    continue
                shutil.copy2(os.path.join(origen[f], f), os.path.join(destino, f))
                nombre = os.path.splitext(f)[0].replace("-", " ")
                winreg.SetValueEx(clave, "%s (%s)" % (nombre, "OpenType" if f.lower().endswith(".otf") else "TrueType"),
                                  0, winreg.REG_SZ, os.path.join(destino, f))
                n += 1
        finally:
            winreg.CloseKey(clave)
        if n:
            try:
                import ctypes
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)   # WM_FONTCHANGE
            except Exception:
                pass
    if n:
        log("Instale %d fuentes de los titulos. Si DaVinci estaba abierto, cierralo y vuelve a pulsar Play." % n)
    return n


def abrir_timeline(nombre):
    with CANDADO:
        r = _dvr().scriptapp("Resolve")
        p = r.GetProjectManager().GetCurrentProject() if r else None
        if p is None:
            return False
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName() == nombre:
                r.OpenPage("edit")
                return bool(p.SetCurrentTimeline(t))
    return False


def cargar_perfiles():
    """{clave: perfil} de perfiles_evento.json (boda, xv, bautizo, graduacion, cumpleanos)."""
    try:
        with open(rutas.perfiles(), encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except Exception:
        return {"xv": {"nombre": "XV años", "momentos": {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia",
                                                        "FIESTA": "Fiesta"}}}


def aplicar_ruido(log, intensidad):
    """Cambia la intensidad de la reduccion de ruido en TODAS las timelines de eventos (no en las plantillas)."""
    import ruido
    if ruido.drx_activo(intensidad):                 # el ruido lo quita DaVinci con el ajuste guardado por la persona
        log("El ruido lo quita DaVinci con tu ajuste guardado: el cambio se aplica al volver a armar.")
        return {"tipo": "ruido", "clips": 0, "timelines": 0}
    with CANDADO:
        ruido.escribir(intensidad, os.path.join(rutas.DATOS, "dctl"))
        r = conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        if p.IsRenderingInProgress():
            log("AVISO: hay un render en curso; aplica la intensidad cuando termine.")
            return None
        p.RefreshLUTList()
        n_tl = n = 0
        clips = []                                   # (item, ruta del video): primero se juntan, luego se mide lo que falte
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName().startswith(("TRAILER XV", "CC ")):
                continue
            n_tl += 1
            for tr in range(1, t.GetTrackCount("video") + 1):
                for it in t.GetItemListInTrack("video", tr) or []:
                    if ruido.es_video(it):
                        clips.append((it, it.GetMediaPoolItem().GetClipProperty("File Path") or ""))
        medidas = {}
        if int(intensidad) > 0:                      # cada toma con el nivel que pide SU ruido (el mismo proceso para todas)
            try:
                import ruido_tomas
                medidas = ruido_tomas.medir_varios(sorted({(ruta, None) for _, ruta in clips if ruta}), log)
            except Exception as ex:
                log("Aviso: no pude medir el ruido de los videos (%s); van con el nivel normal." % ex)
        cuenta = {}
        for it, ruta in clips:
            medida = medidas.get(os.path.normcase(ruta))
            if ruido.aplicar_a_item(it, intensidad, medida):
                n += 1
                nv = ruido.nivel_para(medida, intensidad)
                cuenta[nv] = cuenta.get(nv, 0) + 1
        r.GetProjectManager().SaveProject()
        log("Reduccion de ruido %d (%s) aplicada a %d clips en %d timelines: %s." % (
            int(intensidad), ruido.nivel(intensidad), n, n_tl,
            ", ".join("%d %s" % (cuenta[k], ruido.NOMBRES[k]) for k in sorted(cuenta)) or "sin clips"))
        return {"tipo": "ruido", "clips": n, "timelines": n_tl}


def estado_ruido_davinci():
    """El ajuste de ruido de DaVinci guardado: {"hay", "fecha", "clip", "linea", "herramientas", "de_ruido"}."""
    import ruido
    return ruido.estado_davinci()


def capturar_ruido_davinci(log):
    """Guarda el grado del clip que DaVinci tiene bajo el cursor: ahi dejo la persona el ruido a su gusto (pagina
    Color). Al armar se aplica a todas las tomas. Devuelve lo mismo que estado_ruido_davinci()."""
    import ruido
    with CANDADO:
        if not resolve_abierto():
            raise RuntimeError("Abre DaVinci Resolve en el clip donde dejaste el ruido a tu gusto.")
        r = conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        if p is not None and p.IsRenderingInProgress():
            raise RuntimeError("Hay un render en curso: guarda el ajuste cuando termine.")
        return ruido.capturar_de_resolve(r, log)


def quitar_ruido_davinci():
    import ruido
    ruido.quitar_davinci()
    return ruido.estado_davinci()


def armar(log, evento="", solo=None, seco=False, nombre_xv="", fecha_lugar="", frase="", tipo_evento="xv",
          ruido=None, igualar=True):
    """Analiza el material y lo arma en las plantillas. Devuelve el reporte."""
    with CANDADO:
        t0 = time.time()
        log("== Analizando material ==")
        esperar_copias(log)
        analisis = am.analizar(BASE, log=log)
        if not analisis.get("items"):
            log("No hay material para armar.")
            return None
        usables = [i for i in analisis["items"] if i["tipo"] != "foto" and not i.get("descartar")
                   and i.get("dur", 0) - sum(b - a for a, b in i.get("oscuros") or []) > 3]
        if not usables:                       # todos dañados, en negro o de menos de 3 s: el trailer saldria en negro
            raise RuntimeError("No hay videos que se puedan usar (dañados, en negro o muy cortos). Revisa 1 MATERIAL/VIDEOS: "
                               + "; ".join(a for a in analisis.get("avisos", [])[:2]))
        if sum(1 for i in analisis["items"] if i["tipo"] == "foto" and not i.get("descartar")) < MINIMOS["foto"]:
            log("Aviso: hay menos de %d fotos que se puedan leer: la intro repetira fotos." % MINIMOS["foto"])
        resumen = _resumen(analisis["items"])
        try:                                  # el plan se ve ya, antes de abrir DaVinci (y aunque DaVinci falle)
            log("== Plan previo ==")
            previo = plan_previo(analisis, log, solo=solo, tipo_evento=tipo_evento, evento=evento)
            guardar_plan(previo)
        except Exception as ex:
            log("Aviso: no pude calcular el plan previo (%s)" % ex)
        log("== Conectando con DaVinci Resolve ==")
        instalar_fuentes(log)
        resolve = conectar_resolve(log)
        reenlazar(resolve.GetProjectManager().GetCurrentProject(), log)
        log("== %s ==" % ("Plan (prueba en seco)" if seco else "Armando timelines"))
        ruta = rutas.codigo("build_trailers.py")
        g = {"__name__": "build_trailers", "resolve": resolve, "BASE": BASE, "ANALISIS": analisis,
             "EVENTO": evento or None, "SOLO": solo or None, "REHACER": True, "DRY_RUN": seco,
             "NOMBRE_XV": nombre_xv, "FECHA_LUGAR": fecha_lugar, "FRASE": frase, "TIPO_EVENTO": tipo_evento,
             "RUIDO": ruido, "IGUALAR": bool(igualar),
             "print": lambda *a, **k: log(" ".join(str(x) for x in a))}
        with open(ruta, encoding="utf-8") as f:
            exec(compile(f.read(), ruta, "exec"), g)
        rep = g.get("result") or {}
        rep["material"] = resumen
        rep["seco"] = seco
        if not seco:
            est = leer_estado()
            est.update({"huella": analisis["huella"], "evento": rep.get("evento"),
                        "armado": time.strftime("%Y-%m-%d %H:%M"),
                        "timelines": [v["timeline"] for v in rep.get("versiones", [])],
                        "resumen_versiones": rep.get("versiones", [])})
            guardar_estado(est)
        log("Listo en %.0f s." % (time.time() - t0))
        return rep


def armar_todo(log, avance=None, render=True, **op):
    """El boton Play: analiza, arma las versiones en DaVinci, renderiza, masteriza el audio y mide la imagen.
    avance(pct, texto). Devuelve {"evento", "videos": [(nombre, ok, ruta)], "carpeta"}."""
    def paso(pct, texto):
        if avance:
            avance(pct, texto)
    with SinDormir():                        # una suspension a media render deja el trabajo colgado
        paso(3, "Revisando el material")
        rep = armar(log, **op)
        if not rep or not rep.get("versiones"):
            raise RuntimeError("No se armo ninguna version (revisa que haya fotos y videos en 1 MATERIAL).")
        evento = rep.get("evento")
        salida = {"evento": evento, "videos": [], "carpeta": os.path.join(rutas.TERMINADOS, evento or "")}
        if not render:
            paso(100, "Armado en DaVinci")
            return salida
        libre, necesita = espacio_para_render(op.get("solo"))
        if libre < necesita:
            raise RuntimeError("No hay espacio para renderizar: quedan %.1f GB libres y hacen falta unos %.1f GB. "
                               "Las timelines ya quedaron armadas en DaVinci." % (libre, necesita))
        paso(45, "Renderizando")
        import renderizar
        salida["videos"] = renderizar.renderizar(
            log, evento, lambda pct, texto: paso(45 + int(pct * 0.5), texto))
        paso(100, "Listo")
        return salida
