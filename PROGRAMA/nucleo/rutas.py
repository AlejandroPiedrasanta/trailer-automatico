# -*- coding: utf-8 -*-
"""
rutas.py - Todas las carpetas del programa y las rutas de DaVinci Resolve, en Windows y en Mac.

Desde el codigo (carpeta del proyecto; la persona, 2026-11-16: «en la carpeta solo dejame 2 carpetas, una del programa y
otra del instalador»):
  TRAILER XV AUTOMATICO/
    PROGRAMA/                                      <- codigo, recursos y datos; el trabajo POR DENTRO, como instalado:
      datos/trabajo/1 MATERIAL/  FOTOS · VIDEOS · DRON · ANTERIORES
    3 INSTALADORES/                                <- Windows (.exe + .dat) y Mac (.dmg)
  Lo terminado sale en el Escritorio, igual que instalado: «EVENTO TERMINADO - <evento>».

Instalado (.exe / .app), desde la 1.5.7 (la persona, 2026-11-16: «el usuario no debe tener nada a la vista, solo la carpeta
que se crea cuando termina el video»): el programa vive en su carpeta de instalacion (recursos de solo lectura en
sys._MEIPASS); los datos Y el trabajo (1 MATERIAL) van POR DENTRO, en %LOCALAPPDATA%\\TrailerAutomatico (Mac:
~/Library/Application Support/TrailerAutomatico), en «trabajo/». A la vista solo queda, en el Escritorio, una carpeta por
evento terminado: «EVENTO TERMINADO - <evento>» con «VIDEO TERMINADO» (VIDEO FINAL 1 MIN.mov...) y «PLANTILLAS DE LOS
VIDEOS» (un proyecto de DaVinci por video, .drp, por si hay que corregir algo). pasar_adentro() mueve lo de antes.
"""
import os
import sys
import json
import subprocess

ES_MAC = sys.platform == "darwin"
ES_WIN = os.name == "nt"

import threading  # noqa: E402
PARAR = threading.Event()          # (1.6.0) «Cancelar» en la ventana: el trabajo se detiene en el paso que va


class Detenido(BaseException):
    """Se lanza al cancelar. BaseException: ningun «except Exception» del armado lo traga."""


def revisar_parada():
    if PARAR.is_set():
        raise Detenido()
CONGELADO = bool(getattr(sys, "frozen", False))
NOMBRE_APP = "TrailerAutomatico"

if CONGELADO:
    PROGRAMA = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if ES_WIN:
        DATOS = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), NOMBRE_APP)
    elif ES_MAC:
        DATOS = os.path.expanduser("~/Library/Application Support/" + NOMBRE_APP)
    else:
        DATOS = os.path.expanduser("~/." + NOMBRE_APP.lower())
else:
    PROGRAMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # PROGRAMA/nucleo/rutas.py
    DATOS = os.path.join(PROGRAMA, "datos")
# Pruebas (arrastrar una carpeta de mentira sin tocar el material ni los datos de verdad): TRAILER_DATOS y TRAILER_BASE
if os.environ.get("TRAILER_DATOS"):
    DATOS = os.path.abspath(os.environ["TRAILER_DATOS"])
CONFIG = os.path.join(DATOS, "config.json")

# El codigo va ordenado en carpetas (en el .exe / .app todo queda junto en _MEIPASS). Importar rutas pone las carpetas en
# sys.path, asi los modulos se importan igual que siempre: `import motor`, `import analizar_material`...
GRUPOS = ("nucleo", "analisis", "armado", "entrega", "interfaz", "herramientas")
CONFIG_PROG = PROGRAMA if CONGELADO else os.path.join(PROGRAMA, "config")       # version, perfiles, requisitos, LEEME
if not CONGELADO:
    for _g in GRUPOS:
        _d = os.path.join(PROGRAMA, _g)
        if os.path.isdir(_d) and _d not in sys.path:
            sys.path.append(_d)


def codigo(nombre):
    """Ruta de un .py del programa: en su carpeta (codigo) o junto a todo lo demas (instalado)."""
    if not CONGELADO:
        for g in GRUPOS:
            p = os.path.join(PROGRAMA, g, nombre)
            if os.path.exists(p):
                return p
    return os.path.join(PROGRAMA, nombre)


def _escritorio():
    for d in (os.path.join(os.path.expanduser("~"), "Desktop"), os.path.join(os.path.expanduser("~"), "Escritorio"),
              os.path.join(os.environ.get("OneDrive", ""), "Desktop") if os.environ.get("OneDrive") else ""):
        if d and os.path.isdir(d):
            return d
    return os.path.expanduser("~")


def leer_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_config(d):
    os.makedirs(DATOS, exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG)


def _base():
    """La carpeta de trabajo (1 MATERIAL): POR DENTRO (datos/trabajo), nada a la vista. Desde el codigo tambien (16-nov:
    la carpeta del proyecto solo tiene PROGRAMA y 3 INSTALADORES): PROGRAMA/datos/trabajo."""
    if os.environ.get("TRAILER_BASE"):
        return os.path.abspath(os.environ["TRAILER_BASE"])
    return os.path.join(DATOS, "trabajo")


def _salida():
    """Donde quedan los eventos terminados (lo unico a la vista): el Escritorio, o la carpeta elegida en Ajustes. Igual
    desde el codigo (antes salian en la carpeta del proyecto)."""
    if os.environ.get("TRAILER_SALIDA"):
        return os.path.abspath(os.environ["TRAILER_SALIDA"])
    if os.environ.get("TRAILER_BASE"):
        return BASE
    elegida = leer_config().get("carpeta_terminados")
    if elegida and os.path.isdir(elegida):
        return elegida
    return _escritorio()


BASE = _base()
MATERIAL = os.path.join(BASE, "1 MATERIAL")
CARPETAS = {"foto": os.path.join(MATERIAL, "FOTOS"),
            "video": os.path.join(MATERIAL, "VIDEOS"),
            "dron": os.path.join(MATERIAL, "DRON")}
SALIDA = _salida()

# (19-nov, la persona: «deja en Ajustes si activo o no los proxies; si los activo, la ruta es en Videos: crea la carpeta y
# pon ahi todos los proxies de cualquier evento, plantilla o lo que sea») una sola carpeta para todos, a la vista
NOMBRE_PROXIES = "PROXIES TRAILER AUTOMATICO"
PROXIES_VIEJOS = os.path.join(BASE, "PROXIES")      # donde iban antes (por dentro): se mudan a la de Videos


def carpeta_videos():
    """La carpeta Videos del usuario (Windows: la de verdad, aunque este en otro disco u OneDrive; Mac: Peliculas)."""
    if ES_MAC:
        return os.path.join(os.path.expanduser("~"), "Movies")
    if ES_WIN:
        try:
            import ctypes
            from ctypes import wintypes
            import uuid
            guid = uuid.UUID("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}")          # FOLDERID_Videos

            class GUID(ctypes.Structure):
                _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                            ("d4", ctypes.c_ubyte * 8)]
            g = GUID(guid.fields[0], guid.fields[1], guid.fields[2],
                     (ctypes.c_ubyte * 8).from_buffer_copy(guid.bytes[8:]))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                ruta = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                if ruta and os.path.isdir(ruta):
                    return ruta
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Videos")


def proxies_activos():
    """Ajustes > Video > «Proxies para editar» (encendido de fabrica)."""
    return leer_config().get("proxies_activos", True) is not False


def carpeta_proxies():
    """Videos/PROXIES TRAILER AUTOMATICO: los proxies de todos los eventos y plantillas."""
    return os.path.join(carpeta_videos(), NOMBRE_PROXIES)


def _tam(ruta, tam):
    if tam is not None:
        return int(tam)
    try:
        return os.path.getsize(ruta)
    except OSError:
        return 0


def ruta_proxy(original, tam=None):
    """El proxy de un video: <nombre>_<huella>_proxy.mov en carpeta_proxies(). (19-nov) La huella es el NOMBRE del
    archivo y su tamaño, no su carpeta: si la persona mueve el evento (D:\\XV -> D:\\TERMIANDO\\XV) su proxy sigue sirviendo."""
    import hashlib
    nombre = os.path.basename(original)
    h = hashlib.sha1(("%s|%d" % (nombre.lower(), _tam(original, tam))).encode("utf-8")).hexdigest()[:12]
    return os.path.join(carpeta_proxies(), "%s_%s_proxy.mov" % (os.path.splitext(nombre)[0][:60], h))


def ruta_proxy_vieja(original, tam=None):
    """El nombre de antes del 19-nov (la huella llevaba la ruta entera): para pasarlos al de ahora."""
    import hashlib
    h = hashlib.sha1(("%s|%d" % (os.path.normcase(os.path.abspath(original)), _tam(original, tam))).encode("utf-8")
                     ).hexdigest()[:12]
    return os.path.join(carpeta_proxies(), "%s_%s_proxy.mov" % (os.path.splitext(os.path.basename(original))[0][:60], h))
TERMINADOS = SALIDA                                # el disco donde salen los videos (espacio para el render)
PREFIJO_TERMINADO = "EVENTO TERMINADO - "
VIDEOS_EVENTO = "VIDEO TERMINADO"
PLANTILLAS_EVENTO = "PLANTILLAS DE LOS VIDEOS"


def limpiar_nombre(texto, otro="evento"):
    """Un nombre que sirve de carpeta en Windows y en Mac."""
    import re
    return re.sub(r'[\\/:*?"<>|]+', " ", str(texto or "")).strip(" .") or otro


def carpeta_terminado(evento):
    """Escritorio/EVENTO TERMINADO - <evento>: lo unico que ve la persona."""
    return os.path.join(SALIDA, PREFIJO_TERMINADO + limpiar_nombre(evento))


def videos_terminados(evento):
    return os.path.join(carpeta_terminado(evento), VIDEOS_EVENTO)


def plantillas_evento(evento):
    """Un proyecto de DaVinci por video (.drp, solo esa linea), por si hay que corregir algo."""
    return os.path.join(carpeta_terminado(evento), PLANTILLAS_EVENTO)


def etiqueta_de(nombre_linea):
    """La version de una linea de DaVinci, en corto: «1min» o «VERTICAL 1min». Entiende los dos nombres: el de antes
    («BODA - 1min», «BODA - VERTICAL 1min») y el de la 1.5.7, igual al del video («BODA - VIDEO FINAL 1 MIN»)."""
    import re
    e = str(nombre_linea).split(" - ")[-1].strip()
    m = re.match(r"VIDEO FINAL (VERTICAL |HORIZONTAL )?(\d+) MIN$", e, re.I)
    if m:
        return ("VERTICAL " if (m.group(1) or "").upper().startswith("V") else "") + "%smin" % m.group(2)
    return e


def nombre_linea(evento, etiqueta):
    """(1.5.7) La linea en DaVinci se llama como su video: «BODA 7 NOVIEMBRE - VIDEO FINAL 1 MIN»."""
    return "%s - %s" % (evento, nombre_video(etiqueta))


def nombre_video(nombre_linea):
    """Como se llama el video (y su plantilla .drp), para reconocerlo rapido (la persona, 2026-11-16):
    «XV ANA 2026-11-08 - 15min» -> «VIDEO FINAL 15 MIN»; «... - VERTICAL 1min» -> «VIDEO FINAL VERTICAL 1 MIN».
    (19-nov, la persona: «tienes que explicarme si utilicé una plantilla o la edición, vertical u horizontal... solo
    renómbrala con la plantilla 1 y la fecha») «... - 1min» -> «VIDEO FINAL HORIZONTAL 1 MIN»; una de plantilla de
    Material, «BODA 2026-11-15 - PLANTILLA 1» -> «PLANTILLA 1 VERTICAL - 2026-11-15» (todas en la misma carpeta)."""
    import re
    import time as _t
    etiqueta = etiqueta_de(nombre_linea)
    e = etiqueta.upper()
    if e.startswith("PLANTILLA"):
        f = re.search(r"\d{4}-\d{2}-\d{2}", str(nombre_linea))
        n = re.match(r"PLANTILLA\s*(\d+)", e)
        base = ("PLANTILLA %s" % n.group(1)) if n else limpiar_nombre(e.replace(" HORIZONTAL", ""), "PLANTILLA")
        return "%s %s - %s" % (base, "HORIZONTAL" if "HORIZONTAL" in e else "VERTICAL",
                               f.group(0) if f else _t.strftime("%Y-%m-%d"))
    vertical = e.startswith("VERTICAL")
    m = re.search(r"(\d+)\s*min", etiqueta, re.I)
    tiempo = ("%s MIN" % m.group(1)) if m else limpiar_nombre(e, "VIDEO")
    return "VIDEO FINAL %s%s" % ("VERTICAL " if vertical else "HORIZONTAL ", tiempo)

CAPTURAS = os.path.join(BASE, "CAPTURAS")          # fotos de la intro sacadas del video cuando no hay JPG (por dentro)
ANALISIS = os.path.join(DATOS, "analisis")
RESPALDOS = os.path.join(DATOS, "respaldos")
CLASIFICACION = os.path.join(DATOS, "CLASIFICACION_EVENTO.json")
ESTADO = os.path.join(ANALISIS, "estado_programa.json")
REGISTRO = os.path.join(DATOS, "registro", "registro.log")

RECURSOS = os.path.join(PROGRAMA, "recursos")
PLANTILLAS_DRP = os.path.join(RECURSOS, "plantillas", "EVENTOS CINEMA - PLANTILLAS.drp")
FUENTES = os.path.join(RECURSOS, "fuentes")

# Musica, SFX y la fuente con licencia: los trae el instalador COMPLETO (el que se comparte a mano) y al instalar se guardan FUERA
# del programa, asi las actualizaciones publicas (que no los traen) no los borran. Windows: %LOCALAPPDATA%\TrailerAutomatico.
# Mac: /Users/Shared/TrailerAutomatico (la app de /Applications la reemplaza cada .pkg). En el codigo: recursos/ como siempre.
if CONGELADO and ES_MAC:
    PROTEGIDOS = "/Users/Shared/TrailerAutomatico"
elif CONGELADO:
    PROTEGIDOS = DATOS
else:
    PROTEGIDOS = RECURSOS
FUENTES_LICENCIA = ("FogtwoNo5.ttf",)


def _con_archivos(d):
    try:
        return any(not f.startswith(".") for f in os.listdir(d))
    except OSError:
        return False


AUDIO = os.path.join(PROTEGIDOS, "audio") if _con_archivos(os.path.join(PROTEGIDOS, "audio")) \
    else os.path.join(RECURSOS, "audio")          # musica y SFX de las plantillas (para reenlazar en otra compu)


def carpetas_fuentes():
    """Donde buscar las fuentes de los titulos: las del programa y las con licencia guardadas aparte."""
    return [d for d in (FUENTES, os.path.join(PROTEGIDOS, "fuentes")) if os.path.isdir(d)]


def guardar_protegidos(log=print):
    """Instalado: copia (Mac) o mueve (Windows) la musica y la fuente con licencia que trae el instalador completo a PROTEGIDOS.
    No pisa lo que ya hay. Devuelve cuantos archivos guardo."""
    if not CONGELADO:
        return 0
    import shutil
    n = 0
    for sub, solo in (("audio", None), ("fuentes", FUENTES_LICENCIA)):
        origen = os.path.join(RECURSOS, sub)
        if not os.path.isdir(origen):
            continue
        destino = os.path.join(PROTEGIDOS, sub)
        os.makedirs(destino, exist_ok=True)
        for f in os.listdir(origen):
            if solo and f not in solo:
                continue
            o, d = os.path.join(origen, f), os.path.join(destino, f)
            if os.path.isfile(o) and not (os.path.exists(d) and os.path.getsize(d) == os.path.getsize(o)):
                try:
                    shutil.copy2(o, d)
                    n += 1
                except OSError as ex:
                    log("No pude guardar %s: %s" % (f, ex))
    if n:
        log("Música, SFX y fuente guardadas aparte (%d archivos): las actualizaciones no las tocan." % n)
    return n
DCTL = os.path.join(PROGRAMA, "dctl")


def perfiles():
    """perfiles_evento.json: el de la persona (en datos) si lo edito, si no el que trae el programa."""
    propio = os.path.join(DATOS, "perfiles_evento.json")
    return propio if os.path.exists(propio) else os.path.join(CONFIG_PROG, "perfiles_evento.json")


def version():
    try:
        with open(os.path.join(CONFIG_PROG, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "dev"


# ---------------------------------------------------------------- DaVinci Resolve segun el sistema
if ES_MAC:
    SCRIPT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
    SCRIPT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    DIR_LUT = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
    RESOLVE_APP = "/Applications/DaVinci Resolve/DaVinci Resolve.app"
    for _d in ("/opt/homebrew/bin", "/usr/local/bin"):          # Finder no pasa el PATH de Homebrew
        if os.path.isdir(_d) and _d not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
elif ES_WIN:
    SCRIPT_API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
    SCRIPT_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
    DIR_LUT = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT"
    RESOLVE_APP = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"
else:
    SCRIPT_API = "/opt/resolve/Developer/Scripting"
    SCRIPT_LIB = "/opt/resolve/libs/Fusion/fusionscript.so"
    DIR_LUT = "/opt/resolve/LUT"
    RESOLVE_APP = "/opt/resolve/bin/resolve"
DIR_LUT_MCP = os.path.join(DIR_LUT, "MCP")

# ffmpeg que trae el programa instalado (si no, el del sistema)
_ff = os.path.join(PROGRAMA, "ffmpeg")
if os.path.isfile(os.path.join(_ff, "ffmpeg.exe" if ES_WIN else "ffmpeg")):
    os.environ["PATH"] = _ff + os.pathsep + os.environ.get("PATH", "")

SIN_VENTANA = 0x08000000 if ES_WIN else 0          # que ffmpeg no abra ventanas negras en Windows


def fuentes():
    """(1.5.7) Donde esta el material del evento: las carpetas soltadas, DONDE ESTAN (no se copian; sus archivos se
    renombran en su sitio) y las capturas de la intro. Las carpetas viven en el estado («carpetas»)."""
    try:
        with open(ESTADO, encoding="utf-8") as f:
            carpetas = json.load(f).get("carpetas") or []
    except Exception:
        carpetas = []
    out = [c for c in carpetas if isinstance(c, str) and os.path.isdir(c)]
    if os.path.isdir(CAPTURAS):
        out.append(CAPTURAS)
    return out


def crear_carpetas():
    for d in list(CARPETAS.values()) + [ANALISIS, RESPALDOS]:
        os.makedirs(d, exist_ok=True)


def _bases_viejas():
    """Las carpetas de trabajo A LA VISTA de antes de la 1.5.7: la elegida en Ajustes y la del Escritorio."""
    out = []
    for d in [leer_config().get("carpeta_trabajo")] + [os.path.join(_escritorio(), n)
                                                        for n in ("TRAILER XV AUTOMATICO", "Trailer automatico")]:
        if d and os.path.isdir(d) and os.path.abspath(d) != os.path.abspath(BASE) and d not in out:
            out.append(d)
    return out


def _quitar_vacias(d):
    """Borra las carpetas que quedaron vacias (de abajo arriba); la basura del sistema no cuenta."""
    if not os.path.isdir(d):
        return
    for raiz, carpetas, archivos in os.walk(d, topdown=False):
        for f in archivos:
            if f in (".DS_Store", "desktop.ini", "Thumbs.db") or f.startswith("._"):
                try:
                    os.remove(os.path.join(raiz, f))
                except OSError:
                    pass
        try:
            os.rmdir(raiz)
        except OSError:
            pass


def _mover_dentro(origen, destino):
    """Mueve el contenido de origen a destino sin pisar nada (mismo nombre -> «x (2).ext»). Devuelve cuantos movio."""
    if not os.path.isdir(origen):
        return 0
    import shutil
    n = 0
    os.makedirs(destino, exist_ok=True)
    for nombre in os.listdir(origen):
        if nombre in (".DS_Store", "desktop.ini", "Thumbs.db"):
            continue
        o, d = os.path.join(origen, nombre), os.path.join(destino, nombre)
        if os.path.exists(d):
            if os.path.isdir(o) and os.path.isdir(d):
                n += _mover_dentro(o, d)
                continue
            base, ext = os.path.splitext(nombre)
            k = 2
            while os.path.exists(d):
                d = os.path.join(destino, "%s (%d)%s" % (base, k, ext))
                k += 1
        try:
            shutil.move(o, d)
            n += 1
        except OSError:
            pass
    _quitar_vacias(origen)
    return n


def pasar_adentro(log=print):
    """(1.5.7) Instalado: lo que habia A LA VISTA en la carpeta de trabajo de antes pasa a su sitio: el material
    (1 MATERIAL) adentro del programa; los videos (2 VIDEOS TERMINADOS/<evento>) y las plantillas (3 PLANTILLAS
    EDITABLES/<evento>) a «EVENTO TERMINADO - <evento>» en el Escritorio. La carpeta vieja se quita si queda vacia. La del
    proyecto (la que tiene PROGRAMA/, para programar) nunca se toca. Lo llama tareas.instalar. Devuelve cuantos movio."""
    if not CONGELADO or os.environ.get("TRAILER_BASE"):
        return 0
    n = 0
    for vieja in _bases_viejas():
        if os.path.isdir(os.path.join(vieja, "PROGRAMA")):
            log("No toco %s: es la carpeta del proyecto." % vieja)
            continue
        n += _mover_dentro(os.path.join(vieja, "1 MATERIAL"), MATERIAL)
        for sub, destino in (("2 VIDEOS TERMINADOS", videos_terminados), ("3 PLANTILLAS EDITABLES", plantillas_evento)):
            d = os.path.join(vieja, sub)
            if not os.path.isdir(d):
                continue
            for ev in os.listdir(d):
                o = os.path.join(d, ev)
                if os.path.isdir(o):
                    n += _mover_dentro(o, destino(ev))
            sueltos = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and f not in ("LEEME.txt", "desktop.ini")
                       and not f.startswith(".")]
            if sueltos:                          # videos sueltos, sin carpeta de evento
                tmp = os.path.join(d, "_sueltos")
                os.makedirs(tmp, exist_ok=True)
                for f in sueltos:
                    os.replace(os.path.join(d, f), os.path.join(tmp, f))
                n += _mover_dentro(tmp, destino("anteriores"))
            try:
                os.remove(os.path.join(d, "LEEME.txt"))
            except OSError:
                pass
        try:
            os.remove(os.path.join(vieja, "LEEME.txt"))
        except OSError:
            pass
        _quitar_vacias(vieja)
        log("%s: %s" % (vieja, "quitada (todo quedo en su sitio)" if not os.path.isdir(vieja) else "quedan cosas que no son del programa"))
    c = leer_config()
    if c.pop("carpeta_trabajo", None) is not None:
        guardar_config(c)
    return n


def migrar_datos():
    """Primera vez instalado: trae los analisis ya hechos desde <carpeta del proyecto>/PROGRAMA/datos (version de codigo),
    asi no vuelve a analizar todo el material."""
    viejo = next((os.path.join(b, "PROGRAMA", "datos") for b in [BASE] + (_bases_viejas() if CONGELADO else [])
                  if os.path.isdir(os.path.join(b, "PROGRAMA", "datos"))), "")
    if not CONGELADO or not viejo or os.path.exists(os.path.join(ANALISIS, "material.json")):
        return 0
    import shutil
    n = 0
    for sub in ("analisis",):
        o = os.path.join(viejo, sub)
        if os.path.isdir(o):
            os.makedirs(os.path.join(DATOS, sub), exist_ok=True)
            for f in os.listdir(o):
                if f.endswith(".json"):
                    shutil.copy2(os.path.join(o, f), os.path.join(DATOS, sub, f))
                    n += 1
    if os.path.exists(os.path.join(viejo, "CLASIFICACION_EVENTO.json")) and not os.path.exists(CLASIFICACION):
        shutil.copy2(os.path.join(viejo, "CLASIFICACION_EVENTO.json"), CLASIFICACION)
        n += 1
    return n


def abrir(ruta):
    """Abre una carpeta o archivo con el programa del sistema (Explorador / Finder)."""
    if not os.path.splitext(ruta)[1]:
        os.makedirs(ruta, exist_ok=True)
    if ES_WIN:
        os.startfile(ruta)
    elif ES_MAC:
        subprocess.Popen(["open", ruta])
    else:
        subprocess.Popen(["xdg-open", ruta])


def entorno_limpio():
    """El entorno sin lo nuestro: DaVinci abierto con PYTHON3HOME/PYTHONHOME del .exe hace que su Python de Fusion
    no arranque ('No module named encodings') y se cae a los 10 s (18-nov, 3 veces seguidas)."""
    env = {k: v for k, v in os.environ.items()
           if not (k.upper().startswith("PYTHON") or k.upper().startswith("_PYI") or k.upper().startswith("_MEIPASS")
                   or k.upper() in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "TCL_LIBRARY", "TK_LIBRARY", "SSL_CERT_FILE"))}
    base = getattr(sys, "_MEIPASS", None)
    if base and "PATH" in env:
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep)
                                      if p and not os.path.normcase(p).startswith(os.path.normcase(base)))
    return env


def abrir_resolve():
    if ES_MAC:
        subprocess.Popen(["open", "-a", RESOLVE_APP if os.path.exists(RESOLVE_APP) else "DaVinci Resolve"],
                         env=entorno_limpio())
    elif os.path.exists(RESOLVE_APP):
        subprocess.Popen([RESOLVE_APP], cwd=os.path.dirname(RESOLVE_APP), env=entorno_limpio())
    else:
        return False
    return True
