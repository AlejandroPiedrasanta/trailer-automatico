# -*- coding: utf-8 -*-
"""
limpieza.py - (17-nov) «Borrar caché» de Ajustes: que despues de cada evento el programa no ocupe disco de mas.

La persona (2026-11-17): «en Ajustes agrega borrar caché; ahí va incluido todo, para que no ocupe espacio en el disco
después de cada proyecto».

Se borra SOLO lo que se vuelve a hacer solo si hace falta (medido en la boda del 7-nov):
  - la cache de render de DaVinci de nuestros proyectos (EVENTOS CINEMA y los proyectos por video): 18 GB.
    DaVinci la guarda en <perfCacheClipsLocation>/<id del proyecto>; editable.recordar_cache() anota donde, asi se
    borra aunque DaVinci este cerrado. Con DaVinci abierto NO se toca (podria estar usandola): se avisa.
  - los proxies del evento (trabajo/PROXIES): 670 MB. Sin ellos DaVinci reproduce los originales.
  - los respaldos del proyecto (datos/respaldos/*.drp): se deja el ultimo, por si acaso.
  - las actualizaciones ya instaladas (datos/actualizacion): nunca una pendiente de instalar.
  - los temporales del programa (%TEMP%/trailer_*).
NUNCA se borra: el material del evento, los videos terminados, las plantillas (.drp), las capturas de la intro (son
medios de la linea editable), los nombres originales, el analisis (pesa ~6 MB y ahorra ~30 min si se vuelve a armar),
la musica, los SFX ni los modelos de IA.
"""
import os
import re
import shutil
import tempfile

import rutas


def _tam(ruta):
    """(bytes, archivos) de un archivo o carpeta."""
    if os.path.isfile(ruta):
        try:
            return os.path.getsize(ruta), 1
        except OSError:
            return 0, 0
    tot = n = 0
    for dp, _, fn in os.walk(ruta):
        for f in fn:
            try:
                tot += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return tot, n


def _version(texto):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", texto or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _davinci():
    """Las carpetas de cache de render de DaVinci que anoto el programa: [ruta]."""
    out = []
    for loc, ids in (rutas.leer_config().get("cache_davinci") or {}).items():
        for uid in ids or []:
            p = os.path.join(loc, uid)
            if re.fullmatch(r"[0-9a-fA-F-]{36}", uid) and os.path.isdir(p):
                out.append(p)
    return out


def que_hay():
    """Lo que se puede borrar: [{"clave", "texto", "rutas", "bytes", "archivos"}] (solo lo que existe y pesa algo)."""
    items = []

    def agregar(clave, texto, rutas_):
        rutas_ = [r for r in rutas_ if os.path.exists(r)]
        b = n = 0
        for r in rutas_:
            x, y = _tam(r)
            b += x
            n += y
        if b > 0 or n > 0:
            items.append({"clave": clave, "texto": texto, "rutas": rutas_, "bytes": b, "archivos": n})

    agregar("davinci", "Caché de render de DaVinci", _davinci())
    agregar("proxies", "Proxies de los videos", [os.path.join(rutas.BASE, "PROXIES")])
    resp = sorted((os.path.join(rutas.RESPALDOS, f) for f in os.listdir(rutas.RESPALDOS)
                   if f.lower().endswith(".drp")), key=os.path.getmtime) if os.path.isdir(rutas.RESPALDOS) else []
    agregar("respaldos", "Respaldos viejos del proyecto (queda el último)", resp[:-1])
    act = os.path.join(rutas.DATOS, "actualizacion")
    actual = _version(rutas.version())
    viejas = []
    if os.path.isdir(act) and actual:
        for f in os.listdir(act):
            v = _version(f)
            if v and v <= actual and not f.lower().endswith((".json", ".log")):
                viejas.append(os.path.join(act, f))
    agregar("actualizaciones", "Actualizaciones ya instaladas", viejas)
    tmp = tempfile.gettempdir()
    try:
        temporales = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.lower().startswith("trailer_")]
    except OSError:
        temporales = []
    agregar("temporales", "Archivos temporales del programa", temporales)
    # (1.5.9) el audio que earshot decodifica cuando se usa a mano (el programa no lo deja: su ffmpeg va por tuberia);
    # su modelo (hf) no se toca: bajarlo otra vez es 1 GB
    home = os.environ.get("EARSHOT_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "earshot")
    agregar("earshot", "Audio decodificado de earshot (el oído)", [os.path.join(home, "decoded")])
    agregar("miniaturas", "Miniaturas de la ventana", [os.path.join(rutas.DATOS, "miniaturas")])   # (1.6.0)
    return items


def _borrar(ruta):
    """Borra un archivo o el CONTENIDO de una carpeta (la carpeta queda). Lo que este en uso se salta.
    Devuelve (bytes liberados, archivos que no se pudieron borrar)."""
    libres = fallas = 0
    if os.path.isfile(ruta):
        b, _ = _tam(ruta)
        try:
            os.remove(ruta)
            return b, 0
        except OSError:
            return 0, 1
    for dp, dn, fn in os.walk(ruta, topdown=False):
        for f in fn:
            p = os.path.join(dp, f)
            try:
                b = os.path.getsize(p)
                os.remove(p)
                libres += b
            except OSError:
                fallas += 1
        for d in dn:
            try:
                os.rmdir(os.path.join(dp, d))
            except OSError:
                pass
    return libres, fallas


def borrar(log=print, davinci_abierto=False, claves=None):
    """Borra lo de que_hay() (o solo esas claves). La cache de DaVinci, solo con DaVinci cerrado.
    Devuelve (bytes liberados, archivos que no se pudieron borrar, [claves saltadas])."""
    libres = fallas = 0
    saltadas = []
    for it in que_hay():
        if claves and it["clave"] not in claves:
            continue
        if it["clave"] == "davinci" and davinci_abierto:
            saltadas.append("davinci")
            continue
        b = f = 0
        for r in it["rutas"]:
            x, y = _borrar(r)
            b += x
            f += y
            if it["clave"] == "temporales" and os.path.isdir(r):
                shutil.rmtree(r, ignore_errors=True)
        libres += b
        fallas += f
        log("Borrar caché: %s, %s liberados%s." % (it["texto"], texto_tam(b),
                                                  " (%d archivos en uso quedaron)" % f if f else ""))
    return libres, fallas, saltadas


def texto_tam(b):
    if b >= 1e9:
        return "%.1f GB" % (b / 1e9)
    if b >= 1e6:
        return "%.0f MB" % (b / 1e6)
    return "%.0f KB" % (b / 1e3)
