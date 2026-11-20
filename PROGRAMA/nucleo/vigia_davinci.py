# -*- coding: utf-8 -*-
"""
vigia_davinci.py - (18-nov) Que DaVinci nunca se quede trabado sin que nadie haga nada.

La persona (18-nov): «pon vigilantes; si se congela y no responde entre 10-15 segundos, reintentarlo... si pasa un
minuto, obviamente se trabó». Ese dia DaVinci se colgo 10 minutos haciendo los .drp por video (ventana «no responde»,
casi sin procesador) y el programa esperaba para siempre: una llamada de la API bloqueada no tiene tiempo limite.

UN PROCESO APARTE (probado congelando DaVinci a proposito): una llamada de la API bloqueada NO suelta el GIL, asi que
un hilo vigia dentro del programa se congela con ella y no hace nada. El vigia es otro proceso (el mismo .py, o el .exe
con --vigia) que sigue vivo aunque el programa este parado:
  - El programa anota en DATOS/vigia/secciones.json lo que esta haciendo con DaVinci (`with vigilar("que", tope=s):`).
  - El vigia lo lee cada segundo y mira DaVinci:
      CONGELADO: la ventana principal no contesta un mensaje vacio en 2 s (como Windows dice «no responde») Y casi
                 no usa procesador, durante CONGELADO_S seguidos. Los primeros ARRANQUE_S del proceso no cuentan (al
                 abrir, la ventana tampoco contesta ~20 s: daba falso positivo).
      TRABADO:   la seccion lleva mas de su tope (None = sin tope: render, IntelliSearch, que tardan de verdad).
  - Si pasa: lo escribe en el registro, CIERRA DaVinci (la llamada bloqueada se suelta) y anota la seccion en
    matadas.json. Al soltarse, vigilar() lanza Trabado y `reintentar(fn, ...)` vuelve a conectar y repite.
  - Ocupado de verdad (ventana lenta pero procesador trabajando) NO se toca.
  - Se cierra solo cuando el programa ya no esta.
Mac: no hay forma de preguntar a la ventana; solo cuenta el tope.
"""
import contextlib
import json
import os
import subprocess
import sys
import threading
import time

import rutas

CONGELADO_S = float(os.environ.get("TRAILER_CONGELADO_S", 15))
TOPE_S = 60.0
CPU_QUIETO = 0.25        # menos de un cuarto de nucleo de media = no esta haciendo nada (el cuelgue del 18-nov: 0,16)
ARRANQUE_S = 60.0        # DaVinci contesta a los 15-37 s de abrir (medido 4 veces el 18-nov)
MIRAR_S = 1.0

CARPETA = os.path.join(rutas.DATOS, "vigia")
SECCIONES = os.path.join(CARPETA, "secciones.json")
MATADAS = os.path.join(CARPETA, "matadas.json")


class Trabado(RuntimeError):
    """DaVinci se congelo o una llamada paso su tope: el vigia cerro DaVinci y hay que reintentar."""


_vivo = {"secciones": {}, "proc": None, "n": 0}
_candado = threading.Lock()


# --- archivos compartidos -----------------------------------------------------------------------------------------
def _leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def _escribir(ruta, datos):
    os.makedirs(CARPETA, exist_ok=True)
    tmp = ruta + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    for _ in range(5):
        try:
            os.replace(tmp, ruta)
            return
        except OSError:
            time.sleep(0.05)


def _registrar(msg):
    """Al registro del programa, directo (el programa puede estar parado en la llamada que se trabo)."""
    try:
        ruta = os.path.join(rutas.DATOS, "registro", "registro.log")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("%s  INFO    %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


# --- DaVinci: proceso, ventana, procesador -------------------------------------------------------------------------
def _pids():
    """PIDs de Resolve.exe (Windows) / DaVinci Resolve (Mac)."""
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=10, creationflags=rutas.SIN_VENTANA)
            out = []
            for l in r.stdout.splitlines():
                p = l.strip().strip('"').split('","')
                if len(p) > 1 and p[0].lower() == "resolve.exe" and p[1].isdigit():
                    out.append(int(p[1]))
            return out
        r = subprocess.run(["pgrep", "-f", "DaVinci Resolve.app/Contents/MacOS/Resolve"], capture_output=True,
                           text=True, timeout=10)
        return [int(x) for x in r.stdout.split() if x.isdigit()]
    except Exception:
        return []


def abierto():
    return bool(_pids())


def _ventana_colgada(pid):
    """True si la ventana principal no contesta (Windows); None si no se puede saber. IsHungAppWindow da False si
    nadie le manda mensajes (probado): se le manda WM_NULL y se esperan 2 s, como hace Windows."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    hallada = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd) and not u32.GetWindow(hwnd, 4):   # 4 = GW_OWNER: la principal
            hallada.append(hwnd)
        return True
    try:
        u32.EnumWindows(cada, 0)
    except Exception:
        return None
    if not hallada:
        return None
    res = ctypes.c_size_t()
    return any(not u32.SendMessageTimeoutW(h, 0, 0, 0, 0x0002, 2000, ctypes.byref(res)) for h in hallada)


def _tiempos(pid):
    """(segundos de procesador, segundos de vida) del proceso (Windows), o (None, None)."""
    if os.name != "nt":
        return None, None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None, None
    try:
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None, None
        f = lambda x: x.dwHighDateTime << 32 | x.dwLowDateTime
        return (f(k) + f(u)) / 1e7, time.time() - (f(c) / 1e7 - 11644473600.0)
    finally:
        k32.CloseHandle(h)


def _vive(pid):
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259     # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cerrar(motivo=""):
    """Cierra DaVinci a la fuerza (la llamada bloqueada de la API se suelta). True si quedo cerrado."""
    _registrar("VIGIA: %s: cierro DaVinci para que no se quede trabado." % (motivo or "DaVinci no responde"))
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", "Resolve.exe", "/F"], capture_output=True, timeout=30,
                           creationflags=rutas.SIN_VENTANA)
        else:
            subprocess.run(["pkill", "-9", "-f", "DaVinci Resolve.app/Contents/MacOS/Resolve"], capture_output=True,
                           timeout=30)
    except Exception:
        pass
    for _ in range(20):
        if not abierto():
            return True
        time.sleep(0.5)
    return not abierto()


# --- el proceso vigia ---------------------------------------------------------------------------------------------
def principal(padre):
    """El bucle del proceso vigia (python vigia_davinci.py --vigia <pid> o TrailerAutomatico.exe --vigia <pid>)."""
    colgada_desde = cpu_antes = t_antes = None
    avisado = 0.0
    while _vive(padre):
        time.sleep(MIRAR_S)
        secs = (_leer(SECCIONES, {}) or {}).get("secciones") or {}
        if not secs:
            colgada_desde = None
            continue
        ahora = time.time()
        nombres = " / ".join(s[0] for s in secs.values())
        motivo = None
        for nombre, t0, tope in secs.values():
            if tope and ahora - t0 > tope:
                motivo = "«%s» lleva %.0f s sin terminar (tope %.0f s)" % (nombre, ahora - t0, tope)
                break
        pids = _pids()
        cpu, edad = _tiempos(pids[0]) if pids else (None, None)
        if not motivo and pids and not (edad is not None and edad < ARRANQUE_S):
            if _ventana_colgada(pids[0]):
                if colgada_desde is None:
                    colgada_desde, cpu_antes, t_antes = ahora, cpu, ahora
                elif ahora - colgada_desde >= CONGELADO_S:
                    quieto = cpu is None or cpu_antes is None or \
                        (cpu - cpu_antes) / max(0.1, ahora - t_antes) < CPU_QUIETO
                    if quieto:
                        motivo = "DaVinci no responde hace %.0f s y no está haciendo nada (%s)" % (
                            ahora - colgada_desde, nombres)
                    else:                                 # ocupado de verdad: se vuelve a medir desde aqui
                        if ahora - avisado > 60:
                            _registrar("VIGIA: DaVinci tarda en responder pero está trabajando (%s): espero." % nombres)
                            avisado = ahora
                        colgada_desde, cpu_antes, t_antes = ahora, cpu, ahora
            else:
                colgada_desde = None
        else:
            colgada_desde = None
        if motivo:
            matadas = _leer(MATADAS, {}) or {}
            for sid in secs:
                matadas[sid] = motivo
            _escribir(MATADAS, matadas)
            cerrar(motivo)
            colgada_desde = None


def _arrancar():
    """Enciende el proceso vigia si no esta (uno por programa)."""
    with _candado:
        p = _vivo["proc"]
        if p is not None and p.poll() is None:
            return
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--vigia", str(os.getpid())]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--vigia", str(os.getpid())]
        try:
            _vivo["proc"] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, creationflags=rutas.SIN_VENTANA,
                                             env=dict(os.environ, TRAILER_DATOS=rutas.DATOS))
        except OSError:
            _vivo["proc"] = None


def _guardar_secciones():
    _escribir(SECCIONES, {"padre": os.getpid(), "secciones": {str(k): v for k, v in _vivo["secciones"].items()}})


@contextlib.contextmanager
def vigilar(nombre, tope=TOPE_S, log=None):
    """Mientras dura el bloque, DaVinci se vigila desde fuera. Si se congelo o paso el tope, el vigia lo cierra y aqui
    sale Trabado (aunque la llamada bloqueada haya devuelto None o lanzado otro error al cerrarse DaVinci)."""
    _arrancar()
    al_entrar = set(_pids())
    with _candado:
        _vivo["n"] += 1
        sid = "%d.%d" % (os.getpid(), _vivo["n"])
        _vivo["secciones"][sid] = [nombre, time.time(), tope]
        _guardar_secciones()
    error = None
    try:
        yield
    except Exception as ex:                    # al cerrar DaVinci la llamada suele fallar: lo que cuenta es el vigia
        error = ex
    finally:
        with _candado:
            _vivo["secciones"].pop(sid, None)
            _guardar_secciones()
            matadas = _leer(MATADAS, {}) or {}
            motivo = matadas.pop(sid, None)
            if motivo:
                _escribir(MATADAS, matadas)
    if motivo:
        if log:
            log("VIGIA: %s: cerré DaVinci." % motivo)
        raise Trabado("DaVinci se trabó en «%s»" % nombre)
    if error is not None:
        # (18-nov, probado) DaVinci tambien se CAE solo (ntdll 0xc0000374 haciendo una plantilla): la API devuelve None y
        # sale «'NoneType' object is not callable». Si el DaVinci de antes ya no esta, es lo mismo: se reintenta
        if al_entrar and not (al_entrar & set(_pids())):
            if log:
                log("VIGIA: DaVinci se cerró solo durante «%s» (%s)." % (nombre, error))
            raise Trabado("DaVinci se cerró solo en «%s»" % nombre)
        raise error


def reintentar(fn, nombre, veces=3, log=print, tope=TOPE_S):
    """fn() dentro de vigilar(nombre); si DaVinci se traba, lo intenta otra vez (fn debe volver a conectar:
    motor.conectar_resolve abre DaVinci de nuevo). Devuelve lo que devuelva fn."""
    for k in range(1, veces + 1):
        try:
            with vigilar(nombre, tope, log):
                return fn()
        except Trabado as ex:
            if k == veces:
                raise
            log("VIGIA: %s. Intento %d de %d..." % (ex, k + 1, veces))
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--vigia":
        principal(int(sys.argv[2]))
        sys.exit(0)
    for p in _pids():                          # python vigia_davinci.py: como esta DaVinci ahora mismo
        a, edad = _tiempos(p)
        time.sleep(2)
        b, _ = _tiempos(p)
        print("Resolve %d: ventana colgada=%s, procesador %.2f nucleos, abierto hace %.0f s" % (
            p, _ventana_colgada(p), ((b or 0) - (a or 0)) / 2.0, edad or 0))
    if not _pids():
        print("DaVinci cerrado")
