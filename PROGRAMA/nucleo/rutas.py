# -*- coding: utf-8 -*-
"""
rutas.py - Todas las carpetas del programa y las rutas de DaVinci Resolve, en Windows y en Mac.

Desde el codigo (carpeta del proyecto):
  TRAILER XV AUTOMATICO/
    1 MATERIAL/  FOTOS · VIDEOS · DRON             <- aqui se sube el material del evento
    2 VIDEOS TERMINADOS/<EVENTO>/                  <- aqui salen los videos listos
    PROGRAMA/                                      <- codigo, recursos y datos (datos/)

Instalado (.exe / .app): el programa vive en su carpeta de instalacion (recursos de solo lectura en
sys._MEIPASS), los datos en %LOCALAPPDATA%\\TrailerAutomatico (Mac: ~/Library/Application Support/...) y la
carpeta de trabajo (1 MATERIAL, 2 VIDEOS TERMINADOS) la elige la persona; por defecto la del Escritorio.
"""
import os
import sys
import json
import subprocess

ES_MAC = sys.platform == "darwin"
ES_WIN = os.name == "nt"
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
    if os.environ.get("TRAILER_BASE"):
        return os.path.abspath(os.environ["TRAILER_BASE"])
    if not CONGELADO:
        return os.path.dirname(PROGRAMA)
    elegida = leer_config().get("carpeta_trabajo")
    if elegida:
        return elegida
    for nombre in ("TRAILER XV AUTOMATICO", "Trailer automatico"):
        d = os.path.join(_escritorio(), nombre)
        if os.path.isdir(d):
            return d
    return os.path.join(_escritorio(), "Trailer automatico")


BASE = _base()
MATERIAL = os.path.join(BASE, "1 MATERIAL")
CARPETAS = {"foto": os.path.join(MATERIAL, "FOTOS"),
            "video": os.path.join(MATERIAL, "VIDEOS"),
            "dron": os.path.join(MATERIAL, "DRON")}
TERMINADOS = os.path.join(BASE, "2 VIDEOS TERMINADOS")
EDITABLE = "PLANTILLA EDITABLE (DaVinci)"      # dentro de 2 VIDEOS TERMINADOS/<EVENTO>: la linea de cada version (.drt)

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


def crear_carpetas():
    for d in list(CARPETAS.values()) + [TERMINADOS, ANALISIS, RESPALDOS]:
        os.makedirs(d, exist_ok=True)


def migrar_datos():
    """Primera vez instalado: trae los analisis ya hechos desde BASE/PROGRAMA/datos (version de codigo), asi no
    vuelve a analizar todo el material."""
    viejo = os.path.join(BASE, "PROGRAMA", "datos")
    if not CONGELADO or not os.path.isdir(viejo) or os.path.exists(os.path.join(ANALISIS, "material.json")):
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


def abrir_resolve():
    if ES_MAC:
        subprocess.Popen(["open", "-a", RESOLVE_APP if os.path.exists(RESOLVE_APP) else "DaVinci Resolve"])
    elif os.path.exists(RESOLVE_APP):
        subprocess.Popen([RESOLVE_APP], cwd=os.path.dirname(RESOLVE_APP))
    else:
        return False
    return True
