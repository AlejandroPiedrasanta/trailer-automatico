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


def activo():
    if os.name != "nt" or os.environ.get("TRAILER_LIBERAR") == "0":
        return False
    try:
        import motor
        return motor.leer_estado().get("liberar_auto", True) is not False
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


if __name__ == "__main__":                       # python liberar.py: que cerraria (sin cerrar nada)
    for n, d in sorted(pesados().items()):
        print("%-20s %d procesos  %.0f MB" % (n, len(d["pids"]), d["mb"]))
