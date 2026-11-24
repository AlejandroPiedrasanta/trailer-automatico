# -*- coding: utf-8 -*-
"""
registro.py - Registro del programa en archivo (para encontrar bugs despues) y ganchos de errores.

  datos/registro/registro.log todo lo que hace el programa (rota a 1 MB, guarda 3)
  datos/registro/fallo_nativo.log si Python o Qt se caen del todo (faulthandler)
Cualquier excepcion no atrapada (en la ventana o en un hilo) queda en el registro con su traza.
"""
import os
import re
import sys
import logging
import threading
import traceback
from logging.handlers import RotatingFileHandler

import rutas

_log = logging.getLogger("trailer")
_fallo = None


def preparar():
    """Llamar una sola vez al arrancar."""
    global _fallo
    os.makedirs(os.path.dirname(rutas.REGISTRO), exist_ok=True)
    if sys.stdout is None:                 # .exe sin consola: print() no debe romper nada
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if not _log.handlers:
        h = RotatingFileHandler(rutas.REGISTRO, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
        _log.addHandler(h)
        _log.addHandler(_Contador(logging.ERROR))
        _log.setLevel(logging.INFO)
    try:
        import faulthandler
        _fallo = open(os.path.join(os.path.dirname(rutas.REGISTRO), "fallo_nativo.log"), "a", encoding="utf-8")
        faulthandler.enable(_fallo, all_threads=True)
    except Exception:
        pass

    def gancho(tipo, valor, tb):
        _log.error("Error no atrapado:\n%s", "".join(traceback.format_exception(tipo, valor, tb)))
    sys.excepthook = gancho

    def gancho_hilo(args):
        if args.exc_type is SystemExit:
            return
        _log.error("Error en el hilo %s:\n%s", getattr(args.thread, "name", "?"),
                   "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = gancho_hilo
    _log.info("=== Trailer automatico %s · %s · Python %s · %s", rutas.version(),
              "instalado" if rutas.CONGELADO else "codigo", sys.version.split()[0], sys.platform)
    _log.info("Carpeta de trabajo: %s | datos: %s", rutas.BASE, rutas.DATOS)


def info(msg):
    _log.info(str(msg))


def error(msg):
    _log.error(str(msg))


def aviso(msg, origen=""):
    """Compatibilidad con los modulos de la escena de Inicio (vienen de CineCaptions)."""
    _log.warning("%s%s" % (("[%s] " % origen) if origen else "", msg))


# ---------------------------------------------------------------- (23-nov) el icono del registro en la ventana
# La persona (23-nov): «necesito un icono de registro a la par del icono minimizar que cuando le dé clic pueda ver el
# registro de errores». La ventana pone un punto rojo en el icono cuando hay un error nuevo (errores(), sin leer el
# disco) y su popup (interfaz/vista_registro.py) lee el archivo en un hilo con entradas() y errores_y_avisos().
_ERRORES = {"n": 0}
_CABEZA = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  (\w+)\s?(.*)$")


class _Contador(logging.Handler):
    def emit(self, record):
        _ERRORES["n"] += 1


def errores():
    """Cuantos errores se anotaron desde que abrio el programa."""
    return _ERRORES["n"]


def archivos():
    """El registro y sus copias (rota a 1 MB), del mas nuevo al mas viejo."""
    base = rutas.REGISTRO
    return [p for p in [base] + ["%s.%d" % (base, i) for i in (1, 2, 3)] if os.path.isfile(p)]


def entradas(max_bytes=2_500_000):
    """Las anotaciones del registro, de la mas vieja a la mas nueva: {fecha, hora, nivel, texto, resto}. Las lineas
    sueltas (una traza) van en «resto» de la de arriba. Lee de lo mas nuevo hacia atras hasta max_bytes."""
    trozos, leido = [], 0
    for p in archivos():
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                tam = f.tell()
                desde = max(0, tam - (max_bytes - leido))
                f.seek(desde)
                datos = f.read()
        except OSError:
            continue
        if desde:                                   # la primera linea quedo cortada
            datos = datos.split(b"\n", 1)[-1]
        trozos.insert(0, datos.decode("utf-8", "replace"))
        leido += len(datos)
        if leido >= max_bytes:
            break
    out = []
    for linea in "\n".join(trozos).splitlines():
        a = _CABEZA.match(linea)
        if a:
            out.append({"fecha": a.group(1), "hora": a.group(2), "nivel": a.group(3), "texto": a.group(4),
                        "resto": []})
        elif out and linea.strip():
            out[-1]["resto"].append(linea)
    return out


# lo que suele salir y que quiere decir, en palabras de la persona
_EXPLICA = (("se trabó", "DaVinci dejó de responder y el programa lo cerró para no quedarse esperando."),
            ("se cerró solo", "DaVinci se cerró de golpe mientras trabajaba."),
            ("biblioteca de proyectos", "DaVinci no encontró la carpeta donde guarda sus proyectos."),
            ("No pude conectar con DaVinci", "Revisa que DaVinci esté abierto y con «Scripting externo = Local»."),
            ("'NoneType' object is not callable", "DaVinci se cerró o no respondía cuando el programa le habló."),
            ("WinError 32", "Otro programa tenía abierto un archivo."),
            ("WinError 5", "Windows no dejó escribir un archivo: otro programa (o el antivirus) lo tenía tomado."),
            ("PermissionError", "Windows no dejó tocar un archivo: otro programa lo tenía tomado."),
            ("FileNotFoundError", "Faltaba un archivo que el programa esperaba encontrar."),
            ("timed out", "Algo tardó demasiado en responder."),
            ("No space left", "Falta espacio en el disco."), ("Errno 28", "Falta espacio en el disco."),
            ("MemoryError", "Se acabó la memoria del equipo."))


def _causa(lineas):
    """La ultima linea de una traza («modulo.Error: texto») -> «texto» (o el nombre del error si no trae texto)."""
    for l in reversed(lineas):
        s = l.strip()
        if not s or l[:1].isspace() or s.startswith(("Traceback", "During handling", "The above exception")):
            continue
        tipo, _, msg = s.partition(": ")
        return msg.strip() or tipo.rsplit(".", 1)[-1]
    return ""


_RUTA = re.compile(r"""(['"«])(?:[A-Za-z]:|/)[^'"»]*?[\\/]+([^\\/'"»]+)(['"»])""")


def corto(texto, largo=240):
    """Un titulo que se lee: «\\\\» -> «\\», las rutas entre comillas quedan en «…\\archivo» y, si aun asi es largo,
    se corta con «…» (lo entero sigue en el detalle)."""
    t = _RUTA.sub(lambda m: "%s…\\%s%s" % (m.group(1), m.group(2), m.group(3)), texto.replace("\\\\", "\\"))
    return t if len(t) <= largo else t[:largo].rstrip() + "…"


def juntar(lista):
    """Los seguidos iguales (mismo dia, tipo y titulo: el vigia repite su aviso cada rato) quedan en UNO con «veces»
    y «desde» (la hora del primero). lista = lo de errores_y_avisos (de lo mas nuevo a lo mas viejo)."""
    out = []
    for x in lista:
        p = out[-1] if out else None
        if p and (p["tipo"], p["fecha"], p["titulo"]) == (x["tipo"], x["fecha"], x["titulo"]):
            p["veces"] += 1
            p["desde"] = x["hora"]
            if not p["detalle"]:
                p["detalle"] = x["detalle"]
            continue
        out.append(dict(x, veces=1, desde=x["hora"]))
    return out


def errores_y_avisos(lista=None):
    """[{tipo: error|aviso, fecha, hora, titulo, explica, detalle, sesion}] de lo mas nuevo a lo mas viejo. Error =
    ERROR (con su traza en «detalle») o «No se pudo terminar» (que se junta con la traza de ese mismo momento);
    aviso = WARNING o lo que empieza por AVISO / Aviso / VIGIA. sesion = «23 nov 20:07 · 1.9.3» (cuando se abrio)."""
    lista = entradas() if lista is None else lista
    out, sesion = [], ""
    for e in lista:
        texto = e["texto"].strip()
        if texto.startswith("=== Trailer automatico"):
            version = texto.split("·")[0].replace("=== Trailer automatico", "").strip()
            sesion = "%s %s · %s" % (e["fecha"], e["hora"][:5], version)
            continue
        tipo = None
        if e["nivel"] == "ERROR" or texto.startswith("No se pudo terminar"):
            tipo = "error"
        elif e["nivel"] == "WARNING" or texto.startswith(("AVISO", "Aviso", "VIGIA")):
            tipo = "aviso"
        if tipo is None:
            continue
        detalle = "\n".join(e["resto"])
        titulo = texto
        if e["resto"] and ("Traceback" in texto or texto.endswith(":")):     # «Armado: Traceback (most recent...»
            contexto = re.sub(r":?\s*Traceback.*$", "", texto).rstrip(": ")
            causa = _causa(e["resto"])
            titulo = ("%s: %s" % (contexto, causa)) if contexto and causa else (causa or texto)
        previo = out[-1] if out else None
        if texto.startswith("No se pudo terminar") and previo and previo["tipo"] == "error" and \
                previo["fecha"] == e["fecha"] and previo["hora"][:5] == e["hora"][:5] and previo["detalle"]:
            previo["titulo"] = corto(texto)            # lo que vio la persona, con la traza de ese mismo error
            previo["explica"] = next((x for k, x in _EXPLICA if k in texto or k in previo["detalle"]), "")
            continue
        if corto(titulo) != titulo and not detalle:    # lo que se acorto no se pierde: entero, en el detalle
            detalle = titulo
        titulo = corto(titulo)
        out.append({"tipo": tipo, "fecha": e["fecha"], "hora": e["hora"], "titulo": titulo, "detalle": detalle,
                    "explica": next((x for k, x in _EXPLICA if k in texto or k in detalle), ""),
                    "sesion": sesion})
    out.reverse()
    return out
