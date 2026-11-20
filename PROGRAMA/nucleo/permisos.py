# -*- coding: utf-8 -*-
"""
permisos.py - (1.8.2, la persona: «necesito un popup que salga con todos los permisos para controlar la PC y leer todo
el disco y todo para que el programa opere con total libertad; si ya tiene todos los permisos ya no sale el popup»)

Revisa lo que el sistema tiene que dejar hacer al programa y, si la persona lo pide, lo da:

  Windows  DaVinci con «Scripting externo = Local» (sin eso no se le puede controlar), el «Acceso controlado a
           carpetas» de Windows Defender (si esta activo bloquea que el programa y ffmpeg escriban en el Escritorio y
           en Videos), escribir en las carpetas del programa, leer todos los discos y las rutas largas.
  Mac      Acceso total al disco, Accesibilidad (controlar la Mac), Automatizacion (controlar otras apps), Grabacion
           de pantalla (leer las ventanas de DaVinci) y el mismo scripting de DaVinci.

Lo que pide administrador va en UNA sola ventana de Windows (UAC); lo de la Mac abre su panel de Privacidad (macOS no
deja darlo desde un programa: la persona activa el interruptor). Nada se da sin que la persona pulse «Dar permisos».

  revisar() -> [{"id", "nombre", "para", "ok": True/False/None}]   (None = no se pudo saber: no se pide)
  dar(faltan) -> [mensajes]
"""
import os
import re
import sys
import glob
import shutil
import subprocess

import rutas

SIN_VENTANA = getattr(rutas, "SIN_VENTANA", 0)


# ------------------------------------------------------------------ DaVinci: scripting externo
def _prefs_davinci():
    if rutas.ES_WIN:
        d = os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design", "DaVinci Resolve", "Preferences")
    else:
        d = os.path.expanduser("~/Library/Preferences/Blackmagic Design/DaVinci Resolve")
    return [p for p in (os.path.join(d, "config.dat"), os.path.join(d, ".config.data")) if os.path.exists(p)]


def _scripting():
    """True si DaVinci deja que otros programas lo controlen (Local o Red), None si DaVinci nunca se abrio."""
    modos = []
    for p in _prefs_davinci():
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                modos += [int(m) for m in re.findall(r"System\.Scripting\.Mode\s*=\s*(\d+)", f.read())]
        except OSError:
            pass
    return (max(modos) >= 1) if modos else None


def _davinci_abierto():
    try:
        import motor
        return bool(motor.estado_davinci()[0])
    except Exception:
        return False


def _dar_scripting():
    if _davinci_abierto():
        return ("DaVinci está abierto: ciérralo y pulsa otra vez «Dar permisos» (o en DaVinci: Preferencias > Sistema > "
                "General > Scripting externo = Local).")
    hechos = 0
    for p in _prefs_davinci():
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                texto = f.read()
            nuevo = re.sub(r"(System\.Scripting\.Mode\s*=\s*)0", r"\g<1>1", texto)
            if nuevo != texto:
                shutil.copy2(p, p + ".antes_trailer")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(nuevo)
                hechos += 1
        except OSError:
            pass
    return "DaVinci ya deja que el programa lo controle (Scripting externo = Local)." if hechos else None


# ------------------------------------------------------------------ Windows
def _reg(raiz, clave, valor):
    try:
        import winreg
        with winreg.OpenKey(raiz, clave) as k:
            return winreg.QueryValueEx(k, valor)[0]
    except OSError:
        return None


def _reg_nombres(raiz, clave):
    try:
        import winreg
        out, i = [], 0
        with winreg.OpenKey(raiz, clave) as k:
            while True:
                try:
                    out.append(winreg.EnumValue(k, i)[0])
                except OSError:
                    return out
                i += 1
    except OSError:
        return None


CFA = r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard\Controlled Folder Access"


def _programas():
    """Los .exe que escriben en el Escritorio / Videos: el programa (o Python) y ffmpeg / ffprobe."""
    p = [sys.executable] + [shutil.which(x) for x in ("ffmpeg", "ffprobe")]
    return [os.path.abspath(x) for x in p if x]


def _cfa():
    """True si el Acceso controlado a carpetas esta apagado o deja pasar al programa; None si no se puede leer."""
    import winreg
    activo = _reg(winreg.HKEY_LOCAL_MACHINE, CFA, "EnableControlledFolderAccess")
    if activo is None:                           # (sin administrador el registro no se lee) Defender lo dice igual
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-MpPreference -ErrorAction Stop).EnableControlledFolderAccess"],
                               capture_output=True, text=True, timeout=20, creationflags=SIN_VENTANA)
            activo = int(r.stdout.strip()) if r.stdout.strip().isdigit() else None
        except Exception:
            activo = None
    if activo is None:
        return None
    if int(activo) == 0:
        return True
    permitidos = _reg_nombres(winreg.HKEY_LOCAL_MACHINE, CFA + r"\AllowedApplications")
    if permitidos is None:                       # la lista solo la ve un administrador: decide la prueba de escribir
        return _escribir()[0]
    permitidos = {os.path.normcase(x) for x in permitidos}
    return all(os.path.normcase(x) in permitidos for x in _programas())


def _rutas_largas():
    import winreg
    v = _reg(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem", "LongPathsEnabled")
    return None if v is None else int(v) == 1


def _como_admin(ordenes):
    """Corre esas ordenes de PowerShell como administrador en UNA ventana de Windows (UAC) y espera. True si se acepto."""
    import base64
    script = "\n".join(ordenes)
    cod = base64.b64encode(script.encode("utf-16-le")).decode()
    externo = ("$p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
               "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','%s'; exit $p.ExitCode" % cod)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", externo], capture_output=True, text=True,
                           timeout=300, creationflags=SIN_VENTANA)
        return r.returncode == 0
    except Exception:
        return False


# ------------------------------------------------------------------ Mac
def _mac_disco():
    for p in ("~/Library/Safari", "~/Library/Mail", "/Library/Application Support/com.apple.TCC/TCC.db"):
        p = os.path.expanduser(p)
        if not os.path.exists(p):
            continue
        try:
            if os.path.isdir(p):
                os.listdir(p)
            else:
                open(p, "rb").close()
            return True
        except PermissionError:
            return False
        except OSError:
            continue
    return None


def _mac_lib(nombre):
    import ctypes
    import ctypes.util
    return ctypes.cdll.LoadLibrary(ctypes.util.find_library(nombre) or nombre)


def _mac_accesibilidad():
    try:
        f = _mac_lib("ApplicationServices").AXIsProcessTrusted
        f.restype = __import__("ctypes").c_bool
        return bool(f())
    except Exception:
        return None


def _mac_pantalla():
    try:
        f = _mac_lib("CoreGraphics").CGPreflightScreenCaptureAccess
        f.restype = __import__("ctypes").c_bool
        return bool(f())
    except Exception:
        return None


def _mac_automatizacion():
    try:
        r = subprocess.run(["/usr/bin/osascript", "-e", 'tell application "System Events" to return name of first '
                            'application process'], capture_output=True, text=True, timeout=8)
    except Exception:
        return None
    if r.returncode == 0:
        return True
    return False if "-1743" in (r.stderr or "") or "not allowed" in (r.stderr or "").lower() else None


def _mac_abrir(panel):
    subprocess.run(["/usr/bin/open", "x-apple.systempreferences:com.apple.preference.security?%s" % panel],
                   capture_output=True, timeout=15)


# ------------------------------------------------------------------ comunes
def _carpetas():
    out = [rutas.DATOS, rutas.DIR_LUT_MCP]
    for f in ("carpeta_proxies", "_escritorio"):          # los proxies (Videos) y EVENTO TERMINADO (Escritorio)
        try:
            v = getattr(rutas, f)
            out.append(v() if callable(v) else v)
        except Exception:
            pass
    return [x for x in out if x]


def _escribir():
    """True si puede crear archivos en todas sus carpetas (y la lista de las que fallan)."""
    malas = []
    for d in _carpetas():
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, ".prueba_permiso_trailer")
            with open(p, "w") as f:
                f.write("ok")
            os.remove(p)
        except OSError:
            malas.append(d)
    return not malas, malas


def _discos():
    """True si se pueden leer todos los discos conectados."""
    if not rutas.ES_WIN:
        return None
    import string
    import ctypes
    mascara = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letra in enumerate(string.ascii_uppercase):
        if mascara & (1 << i):
            raiz = letra + ":\\"
            if ctypes.windll.kernel32.GetDriveTypeW(raiz) not in (2, 3):      # extraible o fijo
                continue
            try:
                os.listdir(raiz)
            except PermissionError:
                return False
            except OSError:
                pass                                                         # lector sin disco
    return True


# ------------------------------------------------------------------ la lista
def revisar():
    """Los permisos del programa en este sistema, con su estado."""
    res = []

    def poner(ident, nombre, para, ok):
        res.append({"id": ident, "nombre": nombre, "para": para, "ok": ok})
    poner("scripting", "Controlar DaVinci Resolve", "armar, colorear y renderizar en DaVinci (Scripting externo = Local)",
          _scripting())
    ok_esc, _ = _escribir()
    poner("escribir", "Guardar en tus carpetas", "los videos terminados en el Escritorio, los proxies en Videos y los "
          "colores en DaVinci", ok_esc)
    if rutas.ES_WIN:
        poner("carpetas", "Carpetas protegidas de Windows", "que Windows Defender no bloquee al programa ni a ffmpeg al "
              "escribir en el Escritorio y en Videos", _cfa())
        poner("discos", "Leer todos los discos", "usar el material donde esté (D:, discos externos, memorias)", _discos())
        poner("rutas_largas", "Rutas largas", "carpetas de eventos con nombres largos o muy adentro", _rutas_largas())
    elif sys.platform == "darwin":
        poner("disco_mac", "Acceso total al disco", "leer el material en cualquier disco y guardar en Escritorio y "
              "Películas", _mac_disco())
        poner("accesibilidad", "Controlar la Mac (Accesibilidad)", "manejar ventanas y teclas de DaVinci",
              _mac_accesibilidad())
        poner("automatizacion", "Controlar otras apps (Automatización)", "avisos y abrir / cerrar DaVinci",
              _mac_automatizacion())
        poner("pantalla", "Ver las ventanas (Grabación de pantalla)", "saber qué tiene abierto DaVinci",
              _mac_pantalla())
    if os.environ.get("TRAILER_PERMISOS_PRUEBA"):          # para probar el popup en una PC que ya los tiene todos
        for p in res[:3]:
            p["ok"] = False
    return res


def faltan(lista=None):
    return [p for p in (lista if lista is not None else revisar()) if p["ok"] is False]


def dar(lista):
    """Da los permisos que faltan (los de administrador, todos en una sola ventana de Windows). Devuelve mensajes."""
    # (20-nov) en las pruebas los popups se contestan solos: NUNCA se cambia nada del sistema desde una prueba
    if os.environ.get("TRAILER_PERMISOS_PRUEBA") or os.environ.get("TRAILER_PRUEBA_ARRASTRE"):
        return ["(prueba: no se cambió nada del sistema)"]
    ids = {p["id"] for p in lista}
    msj = []
    if "scripting" in ids:
        m = _dar_scripting()
        if m:
            msj.append(m)
    if rutas.ES_WIN:
        ordenes = []
        if "carpetas" in ids or "escribir" in ids:
            ordenes += ["Add-MpPreference -ControlledFolderAccessAllowedApplications '%s'" % p.replace("'", "''")
                        for p in _programas()]
        if "rutas_largas" in ids:
            ordenes.append("New-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem' "
                           "-Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force | Out-Null")
        if ordenes:
            msj.append("Permisos de Windows dados." if _como_admin(ordenes) else
                       "Windows no dio los permisos (se canceló la ventana de administrador).")
    elif sys.platform == "darwin":
        if "automatizacion" in ids:
            _mac_automatizacion()                    # la primera vez macOS pregunta solo
            if _mac_automatizacion() is False:
                _mac_abrir("Privacy_Automation")
        if "pantalla" in ids:
            try:
                _mac_lib("CoreGraphics").CGRequestScreenCaptureAccess()
            except Exception:
                _mac_abrir("Privacy_ScreenCapture")
        if "accesibilidad" in ids:
            _mac_abrir("Privacy_Accessibility")
        if "disco_mac" in ids:
            _mac_abrir("Privacy_AllFiles")
        msj.append("Se abrió Privacidad y seguridad: activa «Tráiler automático» en cada lista y vuelve al programa.")
    return msj
