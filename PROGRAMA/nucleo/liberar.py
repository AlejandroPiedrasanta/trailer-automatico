# -*- coding: utf-8 -*-
"""
liberar.py - (18-nov) Al pulsar ▶, cierra solos los programas pesados que le quitan memoria y tarjeta al armado.

La persona (18-nov): «cuando arranca el programa cierra todos los procesos que consumen RAM o que pueden limitar el
rendimiento... automáticamente». MEDIDO ese dia: con DxO PureRAW, DaVinci y Chrome llenando la memoria de video (15,7 de
16,3 GB) la IA iba 4 veces mas lenta (3,1 s por cuadro en vez de 0,8).

Como, sin perder nada:
  - Solo una LISTA de programas pesados conocidos (PESADOS): editores de foto/video que no se usan aqui, navegadores y
    CineCaptions (abierto a mitad de un armado tumba a DaVinci). Nunca Windows, DaVinci, Ollama ni el propio programa.
  - Se cierran COMO SI SE PULSARA LA X (WM_CLOSE a sus ventanas): cada uno puede pedir guardar. Nunca a la fuerza: el que
    no se cierra en ESPERA_S se queda y se dice en el registro.
  - Estado «liberar_auto» (por defecto si). TRAILER_LIBERAR=0 lo apaga.
Solo Windows (en la Mac no hace nada).
"""
import os
import subprocess
import time

import rutas

# (nombre del .exe en minusculas o su comienzo, nombre para la persona)
PESADOS = (("pureraw", "DxO PureRAW"), ("photolab", "DxO PhotoLab"), ("photoshop.exe", "Photoshop"),
           ("adobe premiere pro.exe", "Premiere Pro"), ("afterfx.exe", "After Effects"),
           ("lightroom.exe", "Lightroom"), ("lightroomclassic", "Lightroom Classic"), ("topaz", "Topaz"),
           ("capture one", "Capture One"), ("cinecaptions", "CineCaptions"), ("obs64.exe", "OBS"),
           ("chrome.exe", "Chrome"), ("msedge.exe", "Edge"), ("firefox.exe", "Firefox"), ("brave.exe", "Brave"),
           ("opera.exe", "Opera"))
NUNCA = ("resolve.exe", "explorer.exe", "ollama", "llama-server", "trailerautomatico", "python", "msedgewebview2")
ESPERA_S = 10.0


def activo(clave="liberar_auto"):
    """Ajustes > Rendimiento: liberar_auto (pesados al armar), cerrar_google_claude (al abrir), prioridad_alta."""
    if os.name != "nt" or os.environ.get("TRAILER_LIBERAR") == "0":
        return False
    try:
        import motor
        return motor.leer_estado().get(clave, True) is not False
    except Exception:
        return True


def pesados():
    """{nombre para la persona: {"pids": [...], "mb": RAM total}} de los programas de PESADOS abiertos."""
    if os.name != "nt":
        return {}
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15,
                           creationflags=rutas.SIN_VENTANA)
    except Exception:
        return {}
    out = {}
    for l in r.stdout.splitlines():
        p = [x.strip('"') for x in l.split('","')]
        if len(p) < 5 or not p[1].isdigit():
            continue
        exe = p[0].lower()
        if any(exe.startswith(n) for n in NUNCA) or int(p[1]) == os.getpid():
            continue
        nombre = next((amigable for clave, amigable in PESADOS if exe.startswith(clave)), None)
        if not nombre:
            continue
        try:
            mb = int("".join(ch for ch in p[4] if ch.isdigit()) or 0) / 1024.0
        except ValueError:
            mb = 0.0
        d = out.setdefault(nombre, {"pids": [], "mb": 0.0})
        d["pids"].append(int(p[1]))
        d["mb"] += mb
    return out


def _ventanas(pids):
    """Ventanas principales visibles de esos procesos."""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    pids, hallada = set(pids), []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and u32.IsWindowVisible(hwnd) and not u32.GetWindow(hwnd, 4):
            hallada.append(hwnd)
        return True
    try:
        u32.EnumWindows(cada, 0)
    except Exception:
        pass
    return hallada


def cerrar(log=print, espera_s=ESPERA_S):
    """Cierra (con la X, nunca a la fuerza) los programas pesados abiertos. Devuelve (cerrados, siguen)."""
    if not activo():
        return [], []
    abiertos = pesados()
    if not abiertos:
        return [], []
    import ctypes
    u32 = ctypes.windll.user32
    total_mb = sum(d["mb"] for d in abiertos.values())
    log("Liberando memoria para armar: cierro %s (%.1f GB de RAM)..." % (
        ", ".join(sorted(abiertos)), total_mb / 1024.0))
    for d in abiertos.values():
        for h in _ventanas(d["pids"]):
            u32.PostMessageW(h, 0x0010, 0, 0)            # WM_CLOSE: como pulsar la X (puede pedir guardar)
    t0 = time.time()
    siguen = dict(abiertos)
    while siguen and time.time() - t0 < espera_s:
        time.sleep(1.0)
        ahora = pesados()
        siguen = {n: d for n, d in siguen.items() if n in ahora}
    cerrados = sorted(n for n in abiertos if n not in siguen)
    if cerrados:
        log("Cerrados para ir más rápido: %s." % ", ".join(cerrados))
    if siguen:
        log("AVISO: siguen abiertos %s (quizá piden guardar algo): ciérralos tú para que la IA vaya más rápida."
            % ", ".join(sorted(siguen)))
    return cerrados, sorted(siguen)


# ---- (23-nov) AL ABRIR: Google y Claude fuera del todo, y prioridad alta -------------------------------------------
# La persona (23-nov): «que cuando arranque cierre absolutamente todos los procesos Google - Claude... mejor que los
# cierre, y se dé la prioridad». Aqui SI a la fuerza: Chrome deja procesos de fondo y Claude se va a la bandeja con la X.
# Primero la X (Chrome guarda su sesion) y a los 2 s se termina lo que quede. Mismo interruptor: liberar_auto.
FUERA_AL_ABRIR = (("chrome", "Chrome"), ("google", "Google"), ("claude", "Claude"))
MOTORES = ("resolve.exe", "fuscript", "ollama", "llama-server", "ffmpeg")      # reciben prioridad alta
ALTA = 0x00000080                                # HIGH_PRIORITY_CLASS (nunca REALTIME: congela el equipo)


def _procesos():
    """[(pid, padre, exe en minusculas)] de todo lo abierto (Toolhelp: 2 ms, sin lanzar tasklist)."""
    import ctypes
    from ctypes import wintypes

    class Entrada(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entrada)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    foto = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not foto or foto == wintypes.HANDLE(-1).value:
        return []
    out, e = [], Entrada()
    e.dwSize = ctypes.sizeof(Entrada)
    try:
        sigue = k32.Process32FirstW(foto, ctypes.byref(e))
        while sigue:
            out.append((int(e.th32ProcessID), int(e.th32ParentProcessID), e.szExeFile.lower()))
            sigue = k32.Process32NextW(foto, ctypes.byref(e))
    finally:
        k32.CloseHandle(foto)
    return out


def _abrir(pid, permiso):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return k32, k32.OpenProcess(permiso, False, pid)


def _mis_padres(procs):
    """El programa y quien lo abrio (si se abrio desde Claude o Chrome, matarlos lo cerraria a el)."""
    padre = {p: pp for p, pp, _ in procs}
    yo, vistos = os.getpid(), set()
    while yo and yo not in vistos:
        vistos.add(yo)
        yo = padre.get(yo)
    return vistos


def de_google_y_claude():
    """{nombre: [pids]} de los procesos de Google y Claude abiertos (sin los que abrieron este programa)."""
    if os.name != "nt":
        return {}
    procs = _procesos()
    mios, out = _mis_padres(procs), {}
    for pid, _, exe in procs:
        nombre = next((n for clave, n in FUERA_AL_ABRIR if exe.startswith(clave)), None)
        if nombre and pid not in mios:
            out.setdefault(nombre, []).append(pid)
    return out


def cerrar_google_y_claude(log=print, espera_s=2.0):
    """Cierra TODOS los procesos de Google y Claude: la X primero y, lo que quede, terminado. Devuelve cuantos."""
    if not activo("cerrar_google_claude"):
        return 0
    abiertos = de_google_y_claude()
    if not abiertos:
        return 0
    import ctypes
    u32 = ctypes.windll.user32
    todos = [p for l in abiertos.values() for p in l]
    for h in _ventanas(todos):
        u32.PostMessageW(h, 0x0010, 0, 0)
    t0 = time.time()
    while time.time() - t0 < espera_s and de_google_y_claude():
        time.sleep(0.25)
    quedan, no = de_google_y_claude(), 0
    for l in quedan.values():
        for pid in l:
            k32, h = _abrir(pid, 0x0001)                 # PROCESS_TERMINATE
            if not h:
                no += 1                                  # de otro usuario o del sistema (servicio de Google)
                continue
            k32.TerminateProcess(h, 1)
            k32.CloseHandle(h)
    log("Cerrados para ir más rápido: %s (%d procesos%s)." % (
        ", ".join(sorted(abiertos)), len(todos) - no, "; %d del sistema siguen" % no if no else ""))
    return len(todos) - no


def prioridad(log=None):
    """Prioridad ALTA para el programa y sus motores (DaVinci, Ollama, ffmpeg) que ya esten abiertos."""
    if os.name != "nt" or os.environ.get("TRAILER_PRIORIDAD") == "0":
        return []
    try:
        import motor
        if motor.leer_estado().get("prioridad_alta", True) is False:
            return []
    except Exception:
        pass
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    hechos = ["el programa"] if k32.SetPriorityClass(k32.GetCurrentProcess(), ALTA) else []
    for pid, _, exe in _procesos():
        if pid != os.getpid() and any(exe.startswith(m) for m in MOTORES):
            k, h = _abrir(pid, 0x0200)                   # PROCESS_SET_INFORMATION
            if h:
                if k.SetPriorityClass(h, ALTA) and exe not in hechos:
                    hechos.append(exe)
                k.CloseHandle(h)
    if log and hechos:
        log("Prioridad alta: %s." % ", ".join(hechos))
    return hechos


def al_abrir(log=print):
    """Al abrir el programa y al empezar a armar (en un hilo, nunca en el de la ventana)."""
    n = 0
    try:
        n = cerrar_google_y_claude(log)
    except Exception as ex:
        log("Aviso: no se pudo cerrar Google/Claude (%s)" % ex)
    try:
        prioridad(log)
    except Exception as ex:
        log("Aviso: no se pudo subir la prioridad (%s)" % ex)
    return n


if __name__ == "__main__":                       # python liberar.py: que cerraria (sin cerrar nada)
    for n, d in sorted(pesados().items()):
        print("%-20s %d procesos  %.0f MB" % (n, len(d["pids"]), d["mb"]))
    for n, l in sorted(de_google_y_claude().items()):
        print("%-20s %d procesos  (al abrir, a la fuerza)" % (n, len(l)))
