# -*- coding: utf-8 -*-
"""
oido.py - (1.5.9) El oido del programa: earshot (github.com/Leonxlnx/earshot) escucha el audio en la CPU, sin internet.

  - Analisis: cada toma en ventanas de 8 s cada 4 s con el clasificador de AudioSet (AST, 527 sonidos): aplausos,
    vitores, risas, llanto, habla, musica y campanas (0-1). Queda en el cache del analisis («oido») y el armado lo usa
    para encontrar los momentos emotivos (build_trailers.emocion). Nunca para descartar una toma.
  - Entrega: clics sueltos, saturacion digital y huecos de silencio en el audio de cada video final (el detector de
    clics de earshot, aqui con numpy: no necesita earshot), para marcarlos en la linea de DaVinci.

earshot vive en su propio Python (uv tool install): aqui solo se busca ese Python y se le da un script (AYUDANTE) que
carga el modelo una vez. El audio lo decodifica ffmpeg por tuberia, sin la cache de audio de earshot (guardaria GB).
Sin earshot no pasa nada: el programa sigue como antes. Calibrado con la boda del 7-nov: el aplauso real da 0,68;
«Crowd» da 0,3 en cualquier toma de la pista de baile (por eso no cuenta como vitores).
"""
import os
import json
import time
import shutil
import threading
import subprocess

import rutas

VERSION = 1                     # sube si cambia lo que se escucha: las tomas se vuelven a escuchar solas
VENTANA_S = 8.0
PASO_S = 4.0
PISO_AFINAR = 0.05              # (los umbrales de «se oye» van de 0,2 a 0,3)
MIN_DUR_S = 2.0
SIN_RESPUESTA_S = 900           # earshot callado 15 min (la 1a vez baja su modelo, 1 GB): se sigue sin el
HILOS = max(2, min(8, (os.cpu_count() or 4) * 2 // 3))      # 12 hilos -> 8 (medido: 0,61 s por ventana; con 16, 0,80)
INSTALAR = 'uv tool install "earshot @ git+https://github.com/Leonxlnx/earshot"'
PAGINA = "https://github.com/Leonxlnx/earshot"

# grupos de sonidos de AudioSet: vale el maximo de sus etiquetas
GRUPOS = {
    "aplausos": ["Applause", "Clapping"],
    "vitores": ["Cheering", "Whoop", "Yell", "Shout", "Children shouting"],
    "risas": ["Laughter", "Giggle", "Chuckle, chortle", "Belly laugh", "Snicker"],
    "llanto": ["Crying, sobbing", "Whimper"],
    "habla": ["Speech", "Male speech, man speaking", "Female speech, woman speaking", "Conversation",
              "Narration, monologue"],
    "musica": ["Music", "Singing", "Wedding music", "Choir"],
    "campanas": ["Church bell", "Change ringing (campanology)"],
}
UMBRAL = {"aplausos": 0.3, "vitores": 0.25, "risas": 0.2, "llanto": 0.2, "campanas": 0.3}     # «se oye» desde aqui
NOMBRE = {"aplausos": "aplausos", "vitores": "vítores", "risas": "risas", "llanto": "llanto", "campanas": "campanas"}

AYUDANTE = r'''# -*- coding: utf-8 -*-
# Lo escribe y lo corre «Trailer automatico» (analisis/oido.py) con el Python de earshot. No se edita a mano.
import os, sys, json, threading, subprocess
import numpy as np

SIN_VENTANA = 0x08000000 if os.name == "nt" else 0


def decir(**k):
    sys.stdout.write(json.dumps(k) + "\n")
    sys.stdout.flush()


def vivo(pid):
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)            # SYNCHRONIZE
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) != 0          # 0 = ya termino
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def vigilar_padre(pid):
    # si el programa se cierra, aqui se termina tambien: no queda un proceso suelto. (No se lee la tuberia de entrada:
    # en Windows, con un hilo leyendola, cualquier subprocess que la herede se traba)
    import time
    while True:
        time.sleep(5)
        if not vivo(pid):
            os._exit(0)


def ffmpeg(t, ruta, sr, formato):
    return [t["ffmpeg"], "-hide_banner", "-nostats", "-loglevel", "error", "-nostdin", "-i", ruta, "-map", "0:a:0",
            "-vn", "-ac", "1", "-ar", str(sr), "-f", formato, "-"]


def escuchar(t):
    from earshot import audio
    from earshot.models import ast
    m = ast.get()
    grupos = {g: [m.index[l] for l in labs if l in m.index] for g, labs in t["grupos"].items()}
    decir(listo=True, faltan=[l for labs in t["grupos"].values() for l in labs if l not in m.index])
    sr, ven, paso = 16000, float(t["ventana"]), float(t["paso"])
    for ruta in t["tomas"]:
        try:
            r = subprocess.run(ffmpeg(t, ruta, sr, "s16le"), capture_output=True, stdin=subprocess.DEVNULL,
                               creationflags=SIN_VENTANA)
            x = np.frombuffer(r.stdout[:len(r.stdout) // 2 * 2], dtype=np.int16)
            dur = len(x) / float(sr)
            if dur < 0.5:
                decir(ruta=ruta, error="sin audio")
                continue
            inicios = np.arange(0.0, max(0.01, dur - ven / 2.0), paso)
            n = len(inicios)

            def medir(cuales):
                out = []
                for k in range(0, len(cuales), 32):
                    trozos = [audio.resample(x[int(a * sr):int((a + ven) * sr)].astype(np.float32) / 32768.0, sr,
                                             audio.SR) for a in inicios[cuales[k:k + 32]]]
                    out.append(np.asarray(m.probs(trozos, batch=8)))
                    decir(vivo=1)
                return np.concatenate(out)
            # primero una ventana si y otra no (sin solape: se oye todo el audio una vez); las de en medio solo donde
            # una vecina oyo algo de lo que interesa. Lo demas, el promedio de sus vecinas (su audio ya se escucho)
            pares, nones = list(range(0, n, 2)), list(range(1, n, 2))
            Pp = medir(pares)
            P = np.zeros((n, Pp.shape[1]), dtype=np.float32)
            P[pares] = Pp
            interes = sorted({i for g in t.get("afinar") or [] for i in grupos.get(g, [])})
            piso = float(t.get("piso") or 0.0)
            if interes and piso > 0:
                algo = P[:, interes].max(1) >= piso
                oir = [k for k in nones if algo[k - 1] or (k + 1 < n and algo[k + 1])]
            else:
                oir = nones
            if oir:
                P[oir] = medir(oir)
            for k in set(nones) - set(oir):
                P[k] = (P[k - 1] + P[k + 1]) / 2.0 if k + 1 < n else P[k - 1]
            decir(ruta=ruta, dur=round(dur, 2), series={
                g: [round(float(v), 2) for v in (P[:, idx].max(1) if idx else np.zeros(len(P)))]
                for g, idx in grupos.items()})
        except Exception as ex:
            decir(ruta=ruta, error=("%s: %s" % (ex.__class__.__name__, ex))[:200])


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        tarea = json.load(f)
    if tarea.get("padre"):
        threading.Thread(target=vigilar_padre, args=(int(tarea["padre"]),), daemon=True).start()
    escuchar(tarea)
    decir(fin=True)
'''


def python_earshot():
    """El Python de earshot (el de «uv tool install»), o None si no esta instalado."""
    propio = os.environ.get("TRAILER_EARSHOT_PY")
    if propio:
        return propio if os.path.isfile(propio) else None
    dirs = [os.environ.get("UV_TOOL_DIR")]
    if rutas.ES_WIN:
        dirs.append(os.path.join(os.environ.get("APPDATA", ""), "uv", "tools"))
    else:
        dirs.append(os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "uv", "tools"))
    for d in dirs:
        if d:
            py = os.path.join(d, "earshot", "Scripts", "python.exe") if rutas.ES_WIN else \
                os.path.join(d, "earshot", "bin", "python")
            if os.path.isfile(py):
                return py
    return None


def carpeta_cache():
    """Donde guarda earshot sus modelos (hf) y, si alguien lo usa a mano, audio decodificado (decoded)."""
    return os.environ.get("EARSHOT_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "earshot")


def estado():
    """(texto, listo) para Ajustes."""
    if not python_earshot():
        return ("No está instalado (es opcional): con él, el programa escucha aplausos, vítores y risas en cada toma "
                "para elegir mejor los momentos.", False)
    hf = os.path.join(carpeta_cache(), "hf")
    bajado = os.path.isdir(hf) and any("ast-finetuned-audioset" in n for n in os.listdir(hf))
    if not bajado:
        return ("Instalado. La primera vez baja su modelo de sonidos (1 GB); luego todo es local.", True)
    return ("Listo: escucha aplausos, vítores, risas y discursos en cada toma y revisa clics y huecos en el audio "
            "final.", True)


def _correr(trabajo, recibir, log, nombre):
    """Corre el AYUDANTE con el Python de earshot; recibir(dict) por cada linea. True si llego al final."""
    py = python_earshot()
    if not py:
        return False
    carpeta = os.path.join(rutas.DATOS, "oido")
    os.makedirs(carpeta, exist_ok=True)
    script = os.path.join(carpeta, "ayudante_earshot.py")
    try:
        with open(script, encoding="utf-8") as f:
            igual = f.read() == AYUDANTE
    except OSError:
        igual = False
    if not igual:
        with open(script, "w", encoding="utf-8", newline="\n") as f:
            f.write(AYUDANTE)
    trabajo = dict(trabajo, ffmpeg=shutil.which("ffmpeg") or "ffmpeg", padre=os.getpid())
    tarea = os.path.join(carpeta, "tarea_%s_%d.json" % (nombre, os.getpid()))
    with open(tarea, "w", encoding="utf-8") as f:
        json.dump(trabajo, f)
    ultimo, fin = [time.time()], [False]
    try:
        with open(os.path.join(carpeta, "earshot_%s.log" % nombre), "w", encoding="utf-8", errors="replace") as err:
            # -I: el Python de earshot no carga nada de la carpeta del script ni del entorno del programa
            p = subprocess.Popen([py, "-I", script, tarea], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err,
                                 text=True, encoding="utf-8", errors="replace", creationflags=rutas.SIN_VENTANA,
                                 env=dict(os.environ, EARSHOT_THREADS=str(HILOS)))
            parar = threading.Event()

            def vigia():
                while not parar.wait(10):
                    if time.time() - ultimo[0] > SIN_RESPUESTA_S:
                        log("El oído (earshot) no responde: se sigue sin él.")
                        p.kill()
                        return
            threading.Thread(target=vigia, daemon=True).start()
            for linea in p.stdout:
                ultimo[0] = time.time()
                if rutas.PARAR.is_set():              # (1.6.0) «Cancelar»: el oido se corta tambien
                    p.kill()
                    break
                try:
                    m = json.loads(linea)
                except ValueError:
                    continue
                if m.get("fin"):
                    fin[0] = True
                elif not m.get("vivo"):
                    recibir(m)
            parar.set()
            try:
                p.wait(30)
            except Exception:
                p.kill()
    except Exception as ex:
        log("Aviso: el oído (earshot) no pudo escuchar (%s)." % ex)
    finally:
        try:
            os.remove(tarea)
        except OSError:
            pass
    return fin[0]


def falta(d):
    """¿La toma (entrada del cache del analisis) esta por escuchar?"""
    return (d.get("tipo") != "foto" and d.get("audio_pista", True) is not False and not d.get("error")
            and d.get("dur", 0) >= MIN_DUR_S and (d.get("oido") or {}).get("v", 0) < VERSION)


def _oyo(d):
    """Lo que se oye en la toma: [grupo...] (los que pasan su umbral en alguna ventana)."""
    o = d.get("oido") or {}
    return [g for g in UMBRAL if max(o.get(g) or [0.0]) >= UMBRAL[g]]


def escuchar(tomas, log=print):
    """Escucha cada toma (entradas del cache del analisis, con «ruta» y «dur») y deja en cada una «oido»:
    {"v", "paso", "ventana", "aplausos": [0-1 por ventana], "vitores": [...], ...}. Devuelve cuantas escucho."""
    tomas = [d for d in tomas if falta(d)]
    if not tomas or not python_earshot():
        return 0
    por_ruta = {d["ruta"]: d for d in tomas}
    log("El oído (earshot) escucha %d tomas (%.0f min de audio): aplausos, vítores, risas, discursos, música..." % (
        len(tomas), sum(d.get("dur", 0.0) for d in tomas) / 60.0))
    t0, hechas, dicho = time.time(), [0], [time.time()]

    def recibir(m):
        if m.get("listo"):
            if m.get("faltan"):
                log("  oído: el modelo no trae %s" % ", ".join(m["faltan"]))
            return
        d = por_ruta.get(m.get("ruta"))
        if d is None:
            return
        if m.get("error"):
            # (1.8.0, auditoria) solo «sin audio» es para siempre; otro fallo (disco dormido, plazo) se vuelve a
            # escuchar la proxima vez y, si falla 2 veces, ya no se repite
            n_int = (d.get("oido") or {}).get("intentos", 0) + 1
            fijo = m["error"] == "sin audio" or n_int >= 2
            d["oido"] = dict({"error": m["error"], "intentos": n_int}, **({"v": VERSION} if fijo else {}))
        else:
            d["oido"] = dict({"v": VERSION, "paso": PASO_S, "ventana": VENTANA_S}, **m.get("series", {}))
        hechas[0] += 1
        # (23-nov, «que no se quede parado») cada 10 tomas eran ~2,5 min sin decir nada: tambien cada 6 s
        if hechas[0] % 10 == 0 or hechas[0] == len(tomas) or time.time() - dicho[0] >= 6.0:
            dicho[0] = time.time()
            log("  oído %d/%d  %s: %s" % (hechas[0], len(tomas), d.get("nombre", ""),
                                          ", ".join(NOMBRE[g] for g in _oyo(d)) or m.get("error") or "nada especial"))
    # (18-nov) «afinar»: las ventanas solapadas solo se escuchan donde una vecina oyo algo (PISO o mas) de lo que cuenta
    # en el armado. Simulado con lo ya escuchado (XV 8-nov, 922 ventanas): 39 % menos y ninguna deteccion perdida
    tarea = {"grupos": GRUPOS, "ventana": VENTANA_S, "paso": PASO_S, "afinar": list(UMBRAL), "piso": PISO_AFINAR,
             "tomas": [d["ruta"] for d in sorted(tomas, key=lambda d: -d.get("dur", 0.0))]}
    _correr(tarea, recibir, log, "escuchar")
    cuenta = {g: sum(1 for d in tomas if g in _oyo(d)) for g in UMBRAL}
    log("El oído escuchó %d de %d tomas en %.0f s: %s." % (
        hechas[0], len(tomas), time.time() - t0,
        ", ".join("%s en %d" % (NOMBRE[g], n) for g, n in cuenta.items() if n) or "nada especial"))
    return hechas[0]


def _mmss(s):
    s = int(round(s))
    return "%d:%02d" % (s // 60, s % 60)


def _clics(m, np):
    """Saltos en la forma de onda: el detector de clics de earshot (forge/polish.clicks, MIT) con todos los tiempos.
    Un cuadro de 1 ms cuya segunda derivada sube 18 dB sobre lo de alrededor, con la energia en 2 muestras."""
    def fdb(v, n):
        k = len(v) // n
        return 10 * np.log10((v[:k * n].reshape(k, n) ** 2).mean(1) + 1e-24)
    d2 = np.diff(m, 2)
    e, lvl = fdb(d2, 48), fdb(m, 48)
    k = min(len(e), len(lvl))
    if k < 24:
        return []
    e, lvl = e[:k], lvl[:k]
    W = np.lib.stride_tricks.sliding_window_view(np.pad(e, 12, mode="edge"), 25)
    pre, post = np.median(W[:, 2:10], 1), np.median(W[:, 15:23], 1)
    q = np.sort(d2[:k * 48].reshape(k, 48) ** 2, axis=1)
    imp = q[:, -2:].sum(1) / (q.sum(1) + 1e-30)
    hit = (e - np.maximum(pre, post) > 18) & (np.abs(post - pre) < 8) & (lvl > lvl.max() - 70) & (imp > 0.6)
    return [i / 1000.0 for i in np.nonzero(hit)[0]]


def _sueltos(tiempos, aire=0.25):
    """Solo los clics sueltos (como el de un corte sin fundido). Varios seguidos son la forma de onda de un sonido
    (boda 7-nov, 27:35 del de 30 min: un sintetizador en La 440 Hz daba 70 «clics» cada ~9 ms)."""
    t = sorted(tiempos)
    return [x for i, x in enumerate(t)
            if (i == 0 or x - t[i - 1] > aire) and (i == len(t) - 1 or t[i + 1] - x > aire)]


def revisar_audio(ruta, log=print):
    """(1.5.9) Clics sueltos, saturacion digital y huecos de silencio en el audio del video final. Se hace aqui con numpy
    (no necesita earshot). Devuelve los segundos a revisar (marcadores en la linea), [] si esta limpio, None si no se
    pudo."""
    try:
        import numpy as np
    except ImportError:
        return None
    nombre, sr, trozo = os.path.basename(ruta), 48000, 30
    try:
        p = subprocess.Popen([shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
                              "-nostdin", "-i", ruta, "-map", "0:a:0", "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le",
                              "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=rutas.SIN_VENTANA)
    except OSError as ex:
        log("Aviso: no se pudo revisar el audio de %s (%s)" % (nombre, ex))
        return None
    clics, huecos, saturados = [], [], 0
    t0, cola = 0.0, b""
    with p.stdout:
        while True:
            b = cola + p.stdout.read(sr * trozo * 8)
            if len(b) < 8:
                break
            cola = b[len(b) // 8 * 8:]
            par = np.frombuffer(b[:len(b) // 8 * 8], dtype=np.float32).reshape(-1, 2).astype(np.float64)
            # promedio de los canales (el «-ac 1» de ffmpeg suma cada uno x0,707: con la musica al tope pasa de 1)
            x = par.mean(1)
            if len(x) > sr // 10:
                clics += [t0 + t for t in _clics(x, np)]
                lleno = np.abs(par) >= 0.999                # saturacion digital: 3 muestras seguidas al tope
                saturados += int((lleno[:-2] & lleno[1:-1] & lleno[2:]).any(1).sum())
            k = len(x) // 480                               # silencio digital: cuadros de 10 ms bajo -70 dBFS
            if k:
                mudo = np.abs(x[:k * 480]).reshape(k, 480).max(1) < 3.2e-4
                cambios = np.nonzero(np.diff(np.r_[False, mudo, False].astype(np.int8)))[0]
                for a, z in zip(cambios[::2], cambios[1::2]):
                    ini, fin = t0 + a * 0.01, t0 + z * 0.01
                    if huecos and abs(huecos[-1][1] - ini) < 0.011:      # sigue del trozo anterior
                        huecos[-1][1] = fin
                    else:
                        huecos.append([ini, fin])
            t0 += len(x) / float(sr)
    p.wait()
    if t0 < 1.0:
        log("Aviso: no se pudo leer el audio de %s" % nombre)
        return None
    # los huecos al principio (antes de la musica) y en la cola del final no cuentan
    huecos = [(a, z - a) for a, z in huecos if z - a >= 0.5 and a > 1.5 and z < t0 - 3.0]
    clics = _sueltos(clics)
    partes = []
    if clics:
        partes.append("%d clic%s (%s)" % (len(clics), "s" if len(clics) > 1 else "",
                                         ", ".join(_mmss(t) for t in clics[:6])))
    if huecos:
        partes.append("%d hueco%s de silencio (%s)" % (len(huecos), "s" if len(huecos) > 1 else "",
                                                       ", ".join("%s, %.1f s" % (_mmss(a), d) for a, d in huecos[:4])))
    if saturados:
        partes.append("saturación digital en %d muestras" % saturados)
    log("Audio de %s: %s" % (nombre, "; ".join(partes) if partes else "sin clics, huecos ni saturación"))
    return sorted(set([round(float(t), 1) for t in clics] + [round(float(a), 1) for a, _ in huecos]))
