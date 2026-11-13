# -*- coding: utf-8 -*-
"""
actualizar_fondo.py - Actualizaciones con el programa CERRADO (como CineCaptions 5.87): avisa, descarga, comprueba e instala sola.

Quien lo corre (los dos con `TrailerAutomatico --tarea actualizar_fondo`):
  Windows  la tarea programada del USUARIO «Trailer automatico Actualizaciones» (cada 4 h, al iniciar sesion y, si la PC
           estaba apagada, en cuanto se pueda). La crea el instalador (tareas.instalar) y el programa al abrirse
           (asegurar_programada); la quita el desinstalador. Instala en silencio (/silencioso /noabrir): sin administrador.
  Mac      el servicio del sistema ETIQUETA_MAC (/Library/LaunchDaemons, lo pone el .pkg), de root: al encender, cada 4 h y al
           momento cuando el programa deja un pedido en PEDIDOS (QueueDirectories). Instala el .pkg sin pedir contrasena.

Que hace: lee el version.json FIRMADO (actualizaciones.comprobar). Si hay una version nueva y el programa NO esta abierto, avisa con
una notificacion, la baja (SHA-256 del manifiesto firmado) y la instala. Con el programa abierto no toca nada: el programa la baja
y la instala al cerrarlo (o con «Instalar ahora»). Un fallo no se reintenta antes de REINTENTO_S. Registro: carpeta_estado()/fondo.log.
Seguridad del servicio de root (Mac): solo instala lo que dice el manifiesto firmado; de un pedido solo usa «reabrir», el PID que
espera (nunca lo mata) y un .dmg que COPIA a su carpeta y comprueba con el SHA-256 firmado antes de usarlo.
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess

import rutas
import actualizaciones as act

NOMBRE_TAREA = "Trailer automatico Actualizaciones"
ETIQUETA_MAC = "com.cinemaproductions.trailerautomatico.actualizar"
APP_MAC = "/Applications/TrailerAutomatico.app"
BIN_MAC = APP_MAC + "/Contents/MacOS/TrailerAutomatico"
COMPARTIDO_MAC = "/Users/Shared/TrailerAutomatico"
SIN_ABRIR_MAC = COMPARTIDO_MAC + "/.sin_abrir"      # el postinstall no abre la app ni cierra el Instalador (lo hace este servicio)
CADA_H = 4
REINTENTO_S = 6 * 3600
ESPERA_CIERRE_S = 90
SIN_VENTANA = 0x08000000 if rutas.ES_WIN else 0


# ------------------------------------------------------------------ estado y registro
def carpeta_estado():
    d = "/Library/Application Support/TrailerAutomatico/actualizar" if (rutas.ES_MAC and _es_root()) \
        else os.path.join(rutas.DATOS, "actualizacion")
    os.makedirs(d, exist_ok=True)
    return d


def _es_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _log(texto):
    try:
        with open(os.path.join(carpeta_estado(), "fondo.log"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), texto))
    except Exception:
        pass


def _estado():
    try:
        with open(os.path.join(carpeta_estado(), "fondo.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_estado(d):
    ruta = os.path.join(carpeta_estado(), "fondo.json")
    with open(ruta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(ruta + ".tmp", ruta)


# ------------------------------------------------------------------ el programa abierto y el usuario de la Mac
def programa_abierto():
    """True si la ventana del programa esta abierta (no cuenta esta tarea ni otras --tarea)."""
    if rutas.ES_WIN:
        try:
            from PySide6.QtCore import QLockFile
            c = QLockFile(os.path.join(rutas.DATOS, "programa.lock"))
            c.setStaleLockTime(0)
            if c.tryLock(0):
                c.unlock()
                return False
            return True
        except Exception:
            return False
    try:
        r = subprocess.run(["pgrep", "-f", BIN_MAC], capture_output=True, text=True, timeout=15)
        for pid in r.stdout.split():
            if int(pid) == os.getpid():
                continue
            a = subprocess.run(["ps", "-o", "args=", "-p", pid], capture_output=True, text=True, timeout=15).stdout
            if a.strip() and "--tarea" not in a:
                return True
    except Exception:
        pass
    return False


def instalando():
    """True si hay una instalacion del programa en marcha (el Instalador de macOS / installer, o el instalador de Windows):
    no se instala otra encima (paso de verdad: el servicio arrancaba al cargarse dentro del postinstall)."""
    try:
        if rutas.ES_MAC:
            for nombre in ("installer", "Installer"):
                if subprocess.run(["pgrep", "-x", nombre], capture_output=True, timeout=10).returncode == 0:
                    return True
            return False
        if rutas.ES_WIN:
            r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace",
                               timeout=30, creationflags=SIN_VENTANA)
            return any(n.startswith(('"instalar trailer', '"actualizar_trailer', '"desinstalar'))
                       for n in r.stdout.lower().splitlines())
    except Exception:
        pass
    return False


def usuario_mac():
    """(nombre, uid) de quien esta frente a la Mac, o None."""
    try:
        nombre = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True, timeout=10).stdout.strip()
        if nombre and nombre != "root":
            return nombre, int(subprocess.run(["id", "-u", nombre], capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:
        pass
    return None


def _como_usuario(orden):
    u = usuario_mac()
    if _es_root() and u:
        orden = ["/bin/launchctl", "asuser", str(u[1]), "/usr/bin/sudo", "-u", u[0]] + orden
    return subprocess.run(orden, capture_output=True, timeout=60)


def notificar(texto, titulo="Tráiler automático"):
    try:
        if rutas.ES_MAC:
            _como_usuario(["/usr/bin/osascript", "-e", 'display notification %s with title %s'
                           % (json.dumps(texto), json.dumps(titulo))])
        elif rutas.ES_WIN:
            ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing;"
                  "$n = New-Object System.Windows.Forms.NotifyIcon;"
                  "try { $n.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon(%s) } catch { $n.Icon = [System.Drawing.SystemIcons]::Information };"
                  "$n.Visible = $true; $n.ShowBalloonTip(9000, %s, %s, 'Info'); Start-Sleep -Seconds 10; $n.Dispose()"
                  % (_ps(sys.executable), _ps(titulo), _ps(texto)))
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             creationflags=SIN_VENTANA, close_fds=True)
    except Exception as ex:
        _log("no se pudo avisar: %s" % ex)


def _ps(t):
    return "'" + str(t).replace("'", "''") + "'"


# ------------------------------------------------------------------ instalar
def _instalar_windows(ruta):
    """Lanza el instalador en silencio y vuelve: el instalador cierra esta tarea (se llama igual) y reemplaza el programa."""
    subprocess.Popen([ruta, "/silencioso", "/noabrir"], cwd=os.path.dirname(ruta), close_fds=True,
                     creationflags=0x00000008 | 0x00000200 | SIN_VENTANA)


def _instalar_mac(dmg, reabrir=False):
    """De root: monta el .dmg, instala su .pkg sin contrasena y lo expulsa. True si quedo instalado."""
    montaje = tempfile.mkdtemp(prefix="trailer_dmg_")
    os.makedirs(COMPARTIDO_MAC, exist_ok=True)
    open(SIN_ABRIR_MAC, "w").close()
    try:
        r = subprocess.run(["hdiutil", "attach", dmg, "-nobrowse", "-noverify", "-readonly", "-mountpoint", montaje],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError("no se pudo abrir el .dmg: %s" % r.stderr[-200:])
        pkgs = [f for f in os.listdir(montaje) if f.endswith(".pkg")]
        if not pkgs:
            raise RuntimeError("el .dmg no trae el instalador .pkg")
        r = subprocess.run(["/usr/sbin/installer", "-pkg", os.path.join(montaje, pkgs[0]), "-target", "/"],
                           capture_output=True, text=True, timeout=1800)
        _log("installer: %s" % (r.stdout + r.stderr).strip()[-300:])
        if r.returncode != 0:
            raise RuntimeError("el instalador fallo")
    finally:
        subprocess.run(["hdiutil", "detach", montaje, "-force", "-quiet"], capture_output=True, timeout=120)
        try:
            os.rmdir(montaje)
        except OSError:
            pass
        try:
            os.remove(SIN_ABRIR_MAC)
        except OSError:
            pass
    if reabrir:
        _como_usuario(["/usr/bin/open", APP_MAC])
    return True


# ------------------------------------------------------------------ pedidos del programa (Mac)
def _tomar_pedidos():
    d = act.PEDIDOS_MAC
    out = []
    try:
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if f.endswith(".json"):
                try:
                    with open(p, encoding="utf-8") as h:
                        out.append(json.load(h))
                except Exception:
                    pass
            try:
                os.remove(p)                           # la carpeta debe quedar vacia (si no, launchd lo vuelve a lanzar)
            except OSError:
                pass
    except OSError:
        pass
    return out


def _esperar_cierre(pid, tope_s=ESPERA_CIERRE_S):
    fin = time.time() + tope_s
    while pid and time.time() < fin:
        try:
            os.kill(int(pid), 0)
        except (OSError, ValueError):
            return True
        time.sleep(1)
    return False


# ------------------------------------------------------------------ todo junto
def correr():
    _log("== revisando (version instalada %s)" % rutas.version())
    try:
        if rutas.ES_MAC:
            return _correr_mac()
        if rutas.ES_WIN:
            return _correr_windows()
    except Exception as ex:
        _log("ERROR: %s" % ex)
        e = _estado()
        e["fallo"] = time.time()
        _guardar_estado(e)
        return 1
    return 0


def _puede_reintentar(e):
    return time.time() - float(e.get("fallo") or 0) >= REINTENTO_S


def _correr_windows():
    e = _estado()
    if not _puede_reintentar(e):
        _log("fallo reciente: se reintenta mas tarde")
        return 0
    if programa_abierto():
        _log("el programa esta abierto: el se encarga")
        return 0
    if instalando():
        _log("hay una instalacion en marcha: se revisa la proxima vez")
        return 0
    r = act.comprobar()
    if r["estado"] != "nueva":
        _log("%s %s" % (r["estado"], r.get("mensaje", r.get("version", ""))))
        return 0
    if e.get("avisada") != r["version"]:
        notificar("Hay una versión nueva (%s): se descarga e instala sola." % r["version"])
        e["avisada"] = r["version"]
        _guardar_estado(e)
    ruta = act.descargar(r["archivo"])
    if programa_abierto():                              # lo abrieron mientras bajaba: se instala al cerrarlo
        _log("bajada %s; el programa se abrio: la instala el al cerrar" % r["version"])
        return 0
    _log("instalando %s" % r["version"])
    notificar("Instalando Tráiler automático %s…" % r["version"])
    _instalar_windows(ruta)
    return 0


def _correr_mac():
    if not _es_root():
        _log("en la Mac lo corre el servicio del sistema (root)")
        return 0
    pedidos = _tomar_pedidos()
    e = _estado()
    if pedidos:                                          # el programa pidio instalar una version ya bajada
        p = pedidos[-1]
        _esperar_cierre(p.get("pid"))
        r = act.comprobar()
        if r["estado"] != "nueva":
            _log("pedido sin version nueva: %s" % r.get("mensaje", r["estado"]))
            return 0
        destino = os.path.join(carpeta_estado(), act.nombre_de(r["archivo"]))
        dmg = str(p.get("dmg") or "")
        if os.path.isfile(dmg) and not os.path.islink(dmg):
            shutil.copy2(dmg, destino)                   # se copia a la carpeta de root y se comprueba ahi
        if not (os.path.exists(destino) and act.sha256_de(destino) == r["archivo"]["sha256"]):
            destino = act.descargar(r["archivo"], carpeta=carpeta_estado())
        _log("instalando %s (pedido del programa)" % r["version"])
        _instalar_mac(destino, reabrir=bool(p.get("reabrir")))
        return 0
    if not _puede_reintentar(e):
        return 0
    if programa_abierto():
        _log("el programa esta abierto: el se encarga")
        return 0
    if instalando():                                     # p. ej. el servicio arranca dentro del postinstall
        _log("hay una instalacion en marcha: se revisa la proxima vez")
        return 0
    r = act.comprobar()
    if r["estado"] != "nueva":
        _log("%s %s" % (r["estado"], r.get("mensaje", r.get("version", ""))))
        return 0
    notificar("Hay una versión nueva (%s): se descarga e instala sola." % r["version"])
    dmg = act.descargar(r["archivo"], carpeta=carpeta_estado())
    if programa_abierto():
        _log("bajada %s; el programa se abrio: se instala al cerrarlo" % r["version"])
        return 0
    _instalar_mac(dmg, reabrir=False)
    notificar("Tráiler automático se actualizó a %s." % r["version"])
    _log("instalada %s" % r["version"])
    return 0


# ------------------------------------------------------------------ la tarea programada de Windows
def _xml_tarea(exe, usuario):
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 1800))   # no justo al instalar
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Busca e instala las versiones nuevas de Tráiler automático (CINEMA PRODUCTIONS).</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>%(u)s</UserId><Delay>PT10M</Delay></LogonTrigger>
    <TimeTrigger><Repetition><Interval>PT%(h)dH</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>%(i)s</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>%(u)s</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author"><Exec><Command>%(e)s</Command><Arguments>--tarea actualizar_fondo</Arguments><WorkingDirectory>%(d)s</WorkingDirectory></Exec></Actions>
</Task>
""" % {"u": _xml(usuario), "h": CADA_H, "i": inicio, "e": _xml(exe), "d": _xml(os.path.dirname(exe))}


def _xml(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def asegurar_programada(exe=None):
    """Windows, programa instalado: crea (o corrige) la tarea programada si falta o apunta a otro .exe. Corre en un hilo."""
    if not rutas.ES_WIN:
        return "solo Windows"
    exe = exe or sys.executable
    if not rutas.CONGELADO and exe == sys.executable:
        return "solo instalado"
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", NOMBRE_TAREA, "/XML"], capture_output=True, text=True,
                           errors="replace", timeout=90, creationflags=SIN_VENTANA)
        if r.returncode == 0 and exe.lower() in r.stdout.lower():
            return "ya estaba"
    except subprocess.TimeoutExpired:
        pass
    ultimo = None
    for intento in range(3):                 # Windows ARM (x64 emulado) o un antivirus revisando: schtasks puede tardar
        try:
            return _crear_tarea(exe)
        except Exception as ex:
            ultimo = ex
            time.sleep(4)
    raise RuntimeError("no se pudo programar la tarea: %s" % ultimo)


def _crear_tarea(exe):
    usuario = "%s\\%s" % (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")) if os.environ.get("USERDOMAIN") \
        else os.environ.get("USERNAME", "")
    fd, xml = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        with open(xml, "w", encoding="utf-16") as f:
            f.write(_xml_tarea(exe, usuario))
        r = subprocess.run(["schtasks", "/Create", "/TN", NOMBRE_TAREA, "/XML", xml, "/F"], capture_output=True, text=True,
                           errors="replace", timeout=90, creationflags=SIN_VENTANA)
    finally:
        try:
            os.remove(xml)
        except OSError:
            pass
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return "programada cada %d h" % CADA_H


def quitar_programada():
    if rutas.ES_WIN:
        subprocess.run(["schtasks", "/Delete", "/TN", NOMBRE_TAREA, "/F"], capture_output=True, timeout=30,
                       creationflags=SIN_VENTANA)
