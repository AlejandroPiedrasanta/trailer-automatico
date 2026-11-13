# -*- coding: utf-8 -*-
"""
actualizaciones.py - Actualizaciones automaticas, como CineCaptions: lee un version.json FIRMADO publicado en el repositorio publico
de versiones (GitHub Releases de trailer-automatico-releases), baja el instalador que le toca a este equipo, comprueba su huella
SHA-256 y lo instala.

  {"estable": {"version": "1.4.0", "notas": "Lo nuevo", "fecha": "2026-11-13",
               "archivos": {"windows":    {"url": ".../Actualizar_Trailer_automatico_1.4.0.exe", "sha256": "...", "tam": 1},
                            "mac_arm64":  {"url": ".../Trailer_automatico_Mac_AppleSilicon_1.4.0.dmg", ...},
                            "mac_x86_64": {"url": ".../Trailer_automatico_Mac_Intel_1.4.0.dmg", ...}}},
   "firma": {"alg": "ed25519", "clave": "<id>", "valor": "<base64>"}}

Sin una firma valida de CLAVES_FIRMA no se ofrece nada (la huella de cada instalador va dentro de lo firmado). Los instaladores
publicos NO traen la musica, los SFX ni la fuente con licencia: se usa la que ya esta instalada (rutas.PROTEGIDOS).

  comprobar()   dice si hay una version mas nueva que la instalada, con el archivo de ESTE equipo
  descargar()   baja el instalador (con avance) y solo lo da por bueno si su SHA-256 coincide con el del manifiesto
  instalar()    Windows: el instalador de siempre (cierra el programa, reemplaza y, si se pide, lo vuelve a abrir)
                Mac: se lo pide al servicio del sistema (actualizar_fondo, de root), que instala el .pkg sin contrasena
Nada de esto corre en el hilo de la ventana.
"""
import os
import re
import sys
import ssl
import json
import time
import base64
import hashlib
import platform
import subprocess
import urllib.request

import rutas
import firma_ed25519

URL_MANIFIESTO = "https://github.com/AlejandroPiedrasanta/trailer-automatico-releases/releases/latest/download/version.json"
# claves PUBLICAS que pueden firmar el manifiesto (id -> hex). Las privadas NUNCA van al repositorio: ~/TrailerAutomatico_claves
CLAVES_FIRMA = {
    "be15d909": "e5ff9690acd6b4422fe1e0f80508d36a84c449ce543c6d1ea36f27db80470896",   # principal
    "c79bddb9": "6d69a94562f6b49e5b44ffd00b2b7d40cb9361b293e3b18952a6b51502438870",   # reserva
}
PEDIDOS_MAC = "/Users/Shared/TrailerAutomatico/pedidos"          # el servicio de root vigila esta carpeta
SERVICIO_MAC = "/Library/LaunchDaemons/com.cinemaproductions.trailerautomatico.actualizar.plist"
SIN_VENTANA = 0x08000000 if os.name == "nt" else 0


def _partes(v):
    return [int(x) for x in re.findall(r"\d+", str(v or "0"))[:4]] or [0]


def es_mas_nueva(remota, local):
    a, b = _partes(remota), _partes(local)
    n = max(len(a), len(b))
    return a + [0] * (n - len(a)) > b + [0] * (n - len(b))


def url_manifiesto():
    return (os.environ.get("TRAILER_URL_ACTUALIZACIONES") or rutas.leer_config().get("url_actualizaciones")
            or URL_MANIFIESTO).strip()


def clave_plataforma():
    if rutas.ES_WIN:
        return "windows"
    if rutas.ES_MAC:
        maq = platform.machine().lower()
        if maq == "x86_64":                                   # Rosetta: el proceso dice x86_64 en una Mac con chip Apple
            try:
                r = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True, timeout=5)
                if r.stdout.strip() == "1":
                    maq = "arm64"
            except Exception:
                pass
        return "mac_arm64" if maq in ("arm64", "aarch64") else "mac_x86_64"
    return "otro"


def _contexto_ssl():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _abrir(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "TrailerAutomatico/%s" % rutas.version()})
    if url.startswith("https://"):
        return urllib.request.urlopen(req, timeout=timeout, context=_contexto_ssl())
    return urllib.request.urlopen(req, timeout=timeout)


def bytes_firmados(datos):
    """Lo que se firma: el manifiesto sin «firma», en JSON canonico (claves ordenadas, sin espacios, solo ASCII)."""
    resto = {k: v for k, v in datos.items() if k != "firma"}
    return json.dumps(resto, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def firma_valida(datos):
    try:
        f = datos.get("firma") or {}
        publica = CLAVES_FIRMA.get(str(f.get("clave")))
        if f.get("alg") != "ed25519" or not publica:
            return False
        return firma_ed25519.verificar(bytes.fromhex(publica), bytes_firmados(datos),
                                       base64.b64decode(str(f.get("valor") or ""), validate=True))
    except Exception:
        return False


def leer_manifiesto(timeout=12):
    with _abrir(url_manifiesto(), timeout) as r:
        return json.loads(r.read(2_000_000).decode("utf-8"))


def comprobar(version_local=None, timeout=12):
    """{'estado': 'al_dia'|'nueva'|'error', 'version', 'notas', 'archivo': {url, sha256, tam}|None, 'mensaje'}"""
    local = version_local or rutas.version()
    try:
        datos = leer_manifiesto(timeout)
    except Exception as ex:
        return {"estado": "error", "mensaje": "sin conexión con las actualizaciones (%s)" % str(ex)[:120]}
    if not firma_valida(datos):
        return {"estado": "error", "mensaje": "la versión publicada no trae la firma de Cinema Productions: no se instala"}
    e = datos.get("estable") or {}
    remota = str(e.get("version") or "")
    archivo = (e.get("archivos") or {}).get(clave_plataforma())
    res = {"version": remota, "notas": e.get("notas", ""), "fecha": e.get("fecha", ""), "archivo": archivo}
    if not remota or not es_mas_nueva(remota, local):
        res["estado"] = "al_dia"
    elif not archivo or not archivo.get("url") or not re.fullmatch(r"[0-9a-f]{64}", str(archivo.get("sha256", ""))):
        res.update(estado="error", mensaje="la versión %s no trae instalador para este equipo" % remota)
    else:
        res["estado"] = "nueva"
    return res


def carpeta_descargas():
    d = os.path.join(rutas.DATOS, "actualizacion")
    os.makedirs(d, exist_ok=True)
    return d


def sha256_de(ruta, bloque=1 << 20):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(bloque), b""):
            h.update(b)
    return h.hexdigest()


def nombre_de(archivo):
    n = os.path.basename(urllib.request.url2pathname(archivo["url"].split("?")[0].split("/")[-1])) or "instalador"
    return re.sub(r"[^\w.\- ]", "_", n)


def descargar(archivo, progreso=None, cancelado=None, timeout=30, carpeta=None):
    """Baja el instalador y devuelve su ruta. progreso(bytes, total). Si ya estaba bajado y su huella cuadra, no lo baja otra vez."""
    destino = os.path.join(carpeta or carpeta_descargas(), nombre_de(archivo))
    esperado = str(archivo["sha256"]).lower()
    if os.path.exists(destino) and sha256_de(destino) == esperado:
        return destino
    parcial = destino + ".parte"
    total = int(archivo.get("tam") or 0)
    hechos = 0
    h = hashlib.sha256()
    with _abrir(archivo["url"], timeout) as r, open(parcial, "wb") as f:
        total = int(r.headers.get("Content-Length") or total or 0)
        while True:
            if cancelado and cancelado():
                raise RuntimeError("descarga cancelada")
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            h.update(b)
            hechos += len(b)
            if progreso:
                progreso(hechos, total)
    if h.hexdigest() != esperado:
        try:
            os.remove(parcial)
        except OSError:
            pass
        raise RuntimeError("el instalador bajado no coincide con su huella (se descarta)")
    os.replace(parcial, destino)
    for f in os.listdir(os.path.dirname(destino)):              # versiones viejas bajadas
        p = os.path.join(os.path.dirname(destino), f)
        if p != destino and os.path.isfile(p) and time.time() - os.path.getmtime(p) > 3600:
            try:
                os.remove(p)
            except OSError:
                pass
    return destino


def servicio_mac_instalado():
    return rutas.ES_MAC and os.path.exists(SERVICIO_MAC)


def instalar(ruta, reabrir=True):
    """Lanza la instalacion y vuelve enseguida: el programa debe cerrarse despues (el instalador lo cierra si sigue abierto)."""
    if rutas.ES_WIN:
        args = [ruta] if reabrir else [ruta, "/silencioso", "/noabrir"]
        subprocess.Popen(args, close_fds=True, cwd=os.path.dirname(ruta),
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        return "windows"
    if rutas.ES_MAC:
        if servicio_mac_instalado():
            os.makedirs(PEDIDOS_MAC, exist_ok=True)
            pedido = os.path.join(PEDIDOS_MAC, "pedido_%d.json" % int(time.time() * 1000))
            with open(pedido + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"dmg": ruta, "reabrir": bool(reabrir), "pid": os.getpid()}, f)
            os.replace(pedido + ".tmp", pedido)
            return "servicio"
        subprocess.Popen(["open", ruta])                           # sin servicio: se abre el .dmg y la persona instala
        return "dmg"
    raise RuntimeError("actualizar solo en Windows y Mac")
