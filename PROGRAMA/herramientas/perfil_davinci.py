# -*- coding: utf-8 -*-
"""
perfil_davinci.py - (23-nov, la persona: «mejora la respuesta entre DaVinci Resolve Studio, que sea más rápido»)
Cuánto tarda CADA llamada a la API de DaVinci en un armado real, y desde dónde se hace.

Hasta ahora lo lento de DaVinci se sacaba de los huecos del registro (segundos entre un mensaje y el siguiente) y de
medir a mano una llamada (SetClipColor 62 ms, ReplaceClip 0,13-0,28 s). Esto lo mide TODO: con TRAILER_PERFIL_DV=1,
motor._dvr() envuelve la conexión (instalar) y cada objeto que DaVinci devuelve sale envuelto; al terminar el programa
queda datos/perfil_davinci.txt: las llamadas ordenadas por tiempo total (cuántas, total, media, la más lenta) y, de las
más caras, desde qué función se hicieron. Apagado no toca nada (ni se importa).

    $env:TRAILER_PERFIL_DV='1'; $env:TRAILER_LIBERAR='0'; python -u PROGRAMA/interfaz/trailer_xv.py --todo
    python PROGRAMA/herramientas/perfil_davinci.py            (muestra el último informe)

OJO: es para medir, no para el uso diario: los objetos de DaVinci van envueltos (Remoto) y lo que el programa le pasa
de vuelta se desenvuelve; si algo compara por identidad («a is b») dos objetos de DaVinci, envuelto da False.
"""
import atexit
import os
import sys
import threading
import time

REMOTO = "PyRemoteObject"            # el tipo de todo lo que devuelve fusionscript
_AQUI = os.path.normcase(os.path.abspath(__file__))
_candado = threading.Lock()
_llamadas = {}                       # metodo -> [veces, total, maxima]
_desde = {}                          # (metodo, «archivo:funcion») -> [veces, total]
_inicio = time.time()


def _quien():
    f = sys._getframe(2)
    while f is not None and os.path.normcase(os.path.abspath(f.f_code.co_filename)) == _AQUI:
        f = f.f_back
    if f is None:
        return "?"
    return "%s:%s" % (os.path.basename(f.f_code.co_filename), f.f_code.co_name)


def _anotar(metodo, s, quien):
    with _candado:
        a = _llamadas.setdefault(metodo, [0, 0.0, 0.0])
        a[0] += 1
        a[1] += s
        a[2] = max(a[2], s)
        b = _desde.setdefault((metodo, quien), [0, 0.0])
        b[0] += 1
        b[1] += s


def _fuera(o):
    """Lo que el programa le pasa a DaVinci, sin envolver (tambien dentro de listas y diccionarios)."""
    if isinstance(o, (Remoto, _Metodo)):
        return object.__getattribute__(o, "_o")
    if isinstance(o, list):
        return [_fuera(x) for x in o]
    if isinstance(o, tuple):
        return tuple(_fuera(x) for x in o)
    if isinstance(o, dict):
        return {_fuera(k): _fuera(v) for k, v in o.items()}
    return o


def _dentro(o):
    """Lo que DaVinci devuelve, envuelto para medir lo que se le pida despues."""
    if type(o).__name__ == REMOTO:
        return Remoto(o)
    if isinstance(o, list):
        return [_dentro(x) for x in o]
    if isinstance(o, tuple):
        return tuple(_dentro(x) for x in o)
    if isinstance(o, dict):
        return {k: _dentro(v) for k, v in o.items()}
    return o


class _Metodo(object):
    """Un atributo de un objeto de DaVinci: casi siempre un metodo (se mide al llamarlo); en Fusion tambien una entrada
    de una herramienta (tool.Center[cuadro] = ...)."""
    __slots__ = ("_o", "_n")

    def __init__(self, real, nombre):
        object.__setattr__(self, "_o", real)
        object.__setattr__(self, "_n", nombre)

    def __call__(self, *a, **k):
        real, nombre = object.__getattribute__(self, "_o"), object.__getattribute__(self, "_n")
        quien = _quien()
        t0 = time.perf_counter()
        try:
            r = real(*_fuera(a), **_fuera(k))
        finally:
            _anotar(nombre, time.perf_counter() - t0, quien)
        return _dentro(r)

    def __getattr__(self, n):
        return _Metodo(getattr(object.__getattribute__(self, "_o"), n), object.__getattribute__(self, "_n") + "." + n)

    def __setattr__(self, n, v):
        setattr(object.__getattribute__(self, "_o"), n, _fuera(v))

    def __getitem__(self, i):
        return _dentro(object.__getattribute__(self, "_o")[_fuera(i)])

    def __setitem__(self, i, v):
        t0 = time.perf_counter()
        try:
            object.__getattribute__(self, "_o")[_fuera(i)] = _fuera(v)
        finally:
            _anotar(object.__getattribute__(self, "_n") + "[]=", time.perf_counter() - t0, _quien())

    def __bool__(self):
        return bool(object.__getattribute__(self, "_o"))

    def __repr__(self):
        return repr(object.__getattribute__(self, "_o"))

    __str__ = __repr__


class Remoto(object):
    """Un objeto de DaVinci (Resolve, Project, MediaPool, Timeline, clip, comp de Fusion...) que mide lo que se le pide."""
    __slots__ = ("_o",)

    def __init__(self, real):
        object.__setattr__(self, "_o", real)

    def __getattr__(self, n):
        return _Metodo(getattr(object.__getattribute__(self, "_o"), n), n)

    def __setattr__(self, n, v):
        t0 = time.perf_counter()
        try:
            setattr(object.__getattribute__(self, "_o"), n, _fuera(v))
        finally:
            _anotar(n + "=", time.perf_counter() - t0, _quien())

    def __getitem__(self, i):
        return _dentro(object.__getattribute__(self, "_o")[_fuera(i)])

    def __setitem__(self, i, v):
        object.__getattribute__(self, "_o")[_fuera(i)] = _fuera(v)

    def __eq__(self, otro):
        return object.__getattribute__(self, "_o") == _fuera(otro)

    def __ne__(self, otro):
        return not self.__eq__(otro)

    def __hash__(self):
        try:
            return hash(object.__getattribute__(self, "_o"))
        except TypeError:
            return id(object.__getattribute__(self, "_o"))

    def __bool__(self):
        return True

    def __repr__(self):
        return repr(object.__getattribute__(self, "_o"))

    __str__ = __repr__


def instalar(dvr):
    """Envuelve DaVinciResolveScript.scriptapp (una sola vez): lo llama motor._dvr() con TRAILER_PERFIL_DV=1."""
    if getattr(dvr, "_perfilado", False):
        return
    real = dvr.scriptapp

    def scriptapp(*a, **k):
        quien = _quien()
        t0 = time.perf_counter()
        try:
            r = real(*a, **k)
        finally:
            _anotar("scriptapp", time.perf_counter() - t0, quien)
        return _dentro(r)
    dvr.scriptapp = scriptapp
    dvr._perfilado = True
    atexit.register(informe)


def _archivo():
    try:
        import rutas
        return os.path.join(rutas.DATOS, "perfil_davinci.txt")
    except Exception:
        return os.path.join(os.path.dirname(_AQUI), "perfil_davinci.txt")


def texto(cuantas=40, con_origen=12):
    with _candado:
        llamadas = sorted(_llamadas.items(), key=lambda kv: -kv[1][1])
        desde = dict(_desde)
    total = sum(v[1] for _, v in llamadas)
    veces = sum(v[0] for _, v in llamadas)
    out = ["API de DaVinci: %d llamadas, %.1f s en total (de %.0f s que duro el programa)." % (
               veces, total, time.time() - _inicio), "",
           "%9s %8s %9s %9s  %s" % ("total s", "veces", "media ms", "max ms", "llamada")]
    for nombre, (n, s, mx) in llamadas[:cuantas]:
        out.append("%9.2f %8d %9.1f %9.0f  %s" % (s, n, 1000.0 * s / max(1, n), 1000.0 * mx, nombre))
    out += ["", "DESDE DONDE (las %d mas caras):" % con_origen]
    for nombre, (n, s, _mx) in llamadas[:con_origen]:
        out.append("  %s  (%.2f s)" % (nombre, s))
        suyas = sorted(((q, v) for (m, q), v in desde.items() if m == nombre), key=lambda x: -x[1][1])[:5]
        for q, (qn, qs) in suyas:
            out.append("    %8.2f s %7d x  %s" % (qs, qn, q))
    return "\n".join(out) + "\n"


def informe():
    """Deja el informe en datos/perfil_davinci.txt (al salir el programa) y devuelve la ruta."""
    if not _llamadas:
        return None
    ruta = _archivo()
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto())
    except OSError:
        return None
    return ruta


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(_AQUI), "..", "nucleo"))
    try:
        with open(_archivo(), encoding="utf-8") as f:
            print(f.read())
    except OSError:
        print("Aun no hay informe: arma con TRAILER_PERFIL_DV=1 (ver el encabezado de este archivo).")
