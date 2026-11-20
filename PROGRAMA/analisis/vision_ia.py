# -*- coding: utf-8 -*-
"""
vision_ia.py - Lo que VE una IA local en cada toma (1.5.7), para clasificar bien el evento y armar mejor.

La persona (2026-11-16): «mejora el análisis: si es iglesia, identifícalo; maquillaje es una mujer maquillándola o tomas del
vestido o traje del novio; después de eso ya sería iglesia con familia o en grupos»; «mejora las IAs locales para que
reconozca todo eso»; «busca en internet el mejor modelo y úsalo». El análisis de antes repartía los momentos por hora y
color y SIEMPRE ponía tres: en la boda del 7 de noviembre (sin tomas de maquillaje y con el reloj de la cámara mal) puso
la ceremonia como MAQUILLAJE y el primer baile como IGLESIA.

Modelo: el mejor modelo de vision que haya en Ollama (local, sin internet). Preferido Qwen3-VL 8B (2026: el más
recomendado para correr en la PC; ~4 s por toma en una RTX 5070 Ti, 3 cuadros por video); si no, otro con vision
(Ollama dice cuales «ven»: capabilities = vision). Sin Ollama o sin modelo de vision, no hace nada: el análisis sigue por
hora y color como siempre. Se puede forzar con TRAILER_VISION_MODELO.

describir(tipo, ruta, dur) -> {"v", "modelo", "momento": MAQUILLAJE|IGLESIA|FIESTA|OTRO, "escena", "etiquetas", "util"}
Lo guarda analizar_material en el cache de cada archivo («ia»): no se vuelve a mirar (tampoco al renombrarlo).
"""
import os
import json
import time
import base64
import shutil
import subprocess
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import rutas

VERSION = 4                 # 4 (17-nov): «belleza» 1-10 de cada toma. 2: pregunta aparte por equipo de filmacion en primer plano (se colaba la camara)
#                             3: tiraba tomas buenas por una camara al fondo o en manos de un invitado: solo cuenta
#                                el equipo pegado al lente que TAPA la imagen (boda: de 20 fuera a solo las de la camara)
PARALELO = 4               # preguntas a la IA a la vez (las atiende juntas el servidor propio: servidor_rapido)
# (18-nov, la persona: «mejora los analizadores, que hagan más rápido y en paralelo las tomas») Sacar el cuadro con
# ffmpeg (0,55 s) se hacia EN FILA con la pregunta dentro de cada toma. Ahora los cuadros salen aparte (EXTRAER a la
# vez: 0,20 s por cuadro; medido, ffmpeg no frena a la IA) y la IA siempre tiene PARALELO preguntas esperando.
EXTRAER = max(3, min(8, (os.cpu_count() or 4) // 2))
TOMAS_A_LA_VEZ = PARALELO * 2      # tomas con sus cuadros ya pedidos (las cortas, de 1 cuadro, no dejan la GPU esperando)
_pozos, _candado_pozos = {}, threading.Lock()


def _pozo(nombre, n):
    with _candado_pozos:
        p = _pozos.get(nombre)
        if p is None:
            p = _pozos[nombre] = ThreadPoolExecutor(n, thread_name_prefix="ia_" + nombre)
        return p


def cuadros(ruta, tiempos, lado=448):
    """Los cuadros de esos segundos, saliendo ya (ffmpeg, EXTRAER a la vez): [futuro -> imagen en base64 o None]."""
    return [_pozo("ffmpeg", EXTRAER).submit(_cuadro, ruta, t, lado) for t in tiempos]


# contexto chico: 3 cuadros + la pregunta caben en ~5 mil tokens. Ollama cargaba el modelo con 64 mil (10 GB); con DaVinci
# usando la GPU no entraba y cada consulta tardaba mas de 2 min (16-nov). Con 8 mil: ~6 GB y unos segundos.
NUM_CTX = 8192
URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not URL.startswith("http"):
    URL = "http://" + URL
PREFERIDOS = ("qwen3-vl", "qwen2.5vl", "qwen2.5-vl", "gemma3", "llama3.2-vision", "minicpm-v", "llava")
ETIQUETAS = ("maquillaje", "peinado", "vestido", "traje", "zapatos", "anillos", "altar", "sacerdote", "bancas", "cortejo",
             "beso", "votos", "familia", "grupo", "baile", "primer_baile", "pastel", "brindis", "comida", "mesa", "dj",
             "exterior", "dron", "novia", "novio", "festejada", "niños", "detalle", "entrada", "risas", "lagrimas")
MOMENTO = {"PREPARATIVOS": "MAQUILLAJE", "MAQUILLAJE": "MAQUILLAJE", "IGLESIA": "IGLESIA", "CEREMONIA": "IGLESIA",
           "FIESTA": "FIESTA", "RECEPCION": "FIESTA", "OTRO": "OTRO"}
PROMPT = """Eres editor de videos de bodas, quinceañeras y bautizos. Las imágenes son cuadros de UNA misma toma del evento.
Responde SOLO un JSON con estas claves:
"momento": uno de
  "PREPARATIVOS" = antes de salir: maquillaje o peinado de la novia o la festejada, el vestido o el traje del novio (colgado o
                   poniéndoselo), zapatos, perfume, anillos o detalles en casa o en el hotel;
  "IGLESIA" = la ceremonia en iglesia o capilla: altar, sacerdote o pastor, bancas, cortejo, anillos, votos, beso, y la
              salida o las fotos con la familia o en grupos frente a la iglesia; también la fachada de la iglesia;
  "FIESTA" = el salón o la recepción: baile, mesas, comida, bebidas, pastel, brindis, DJ, luces de colores, juegos;
  "OTRO" = no se puede saber.
"escena": qué pasa, en 8 palabras o menos, en español.
"etiquetas": las palabras de esta lista que SE VEAN: %s.
"equipo": true SOLO si en la mayoría de los cuadros un equipo de filmación (cámara, flash, tripié, celular o
          micrófono) está pegado al lente y TAPA una buena parte de la imagen, o la imagen es la pantalla o el visor de
          una cámara. Cámaras, celulares o fotógrafos al fondo, en manos de los invitados o pequeños en la imagen NO
          cuentan: false.
"util": false SOLO si la toma no sirve para el video final: se ve sobre todo el piso o el techo, está muy borrosa o
        a oscuras, algo tapa casi toda la imagen, o no se ve a nadie ni nada del evento; si no, true. Ante la duda, true.
"belleza": un número del 1 al 10: qué tan BONITA es la toma para un video profesional (encuadre, luz, se ve bien a la
           persona, emoción, fondo limpio). 1-3 fea o descuidada; 4-6 normal; 7-8 bonita; 9-10 espectacular, de portada.
           Sé exigente: la mayoría de las tomas son 4-6.""" % \
    ", ".join(ETIQUETAS)

_estado = {"modelo": None, "probado": 0.0}
MODELO_RECOMENDADO = "qwen3-vl:8b-instruct"
DESCARGA_OLLAMA = "https://ollama.com/download"


# (1.8.0, auditoria) «cortacircuitos»: si Ollama no contesta CORTE_FALLOS veces seguidas (colgado, sin memoria de video),
# las preguntas de los proximos CORTE_S fallan al instante en vez de esperar 120 s cada una (con 448 tomas eran horas).
# Esos cuadros quedan como no mirados (instantes) y la toma se revisa otra vez la proxima vez.
CORTE_FALLOS, CORTE_S = 4, 90.0
_corte = {"seguidos": 0, "hasta": 0.0}
_corte_lock = threading.Lock()


class IACaida(OSError):
    pass


def _pedir(camino, cuerpo=None, timeout=5.0, base=None):
    if camino != "/api/chat":
        return _pedir_uno(camino, cuerpo, timeout, base)
    if time.time() < _corte["hasta"]:
        raise IACaida("la IA local no responde (pausa de %.0f s)" % CORTE_S)
    try:
        r = _pedir_uno(camino, cuerpo, timeout, base)
    except (OSError, TimeoutError):           # URLError, conexion rechazada, plazo vencido
        with _corte_lock:
            _corte["seguidos"] += 1
            if _corte["seguidos"] >= CORTE_FALLOS:
                _corte["seguidos"], _corte["hasta"] = 0, time.time() + CORTE_S
        raise
    with _corte_lock:
        _corte["seguidos"] = 0
    return r


def _pedir_uno(camino, cuerpo=None, timeout=5.0, base=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    propio = _propio["url"] if base is None else None
    req = urllib.request.Request((base or propio or URL) + camino, data=datos, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.URLError as ex:
        # el servidor propio se cayo (conexion rechazada): se sigue con el de siempre
        if propio and isinstance(getattr(ex, "reason", None), ConnectionError) and _propio["url"] == propio:
            _propio["url"] = None
            return _pedir_uno(camino, cuerpo, timeout)
        raise


def _exe_ollama():
    exe = shutil.which("ollama")
    for c in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
              "/Applications/Ollama.app/Contents/Resources/ollama", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"):
        if not exe and c and os.path.exists(c):
            exe = c
    return exe


# (18-nov, «mejora los analizadores, que hagan más rápido y en paralelo») MEDIDO con cuadros nuevos (Ollama guarda las
# imagenes repetidas y engaña): el Ollama de siempre atiende UNA pregunta a la vez (1,07 s por cuadro, mande 1 o 3 a la
# vez). Con OLLAMA_NUM_PARALLEL=4, 0,77 s (3 a la vez 0,92; 6 igual que 4) y 1,8 GB mas de memoria de video. Esa opcion
# solo se lee al encender el servidor, asi que el programa enciende el SUYO en otro puerto (mismos modelos; el del
# usuario no se toca ni se reinicia) y lo apaga al salir. Si no enciende o el modelo no cabe en la GPU, el de siempre.
PUERTO_PROPIO = int(os.environ.get("TRAILER_OLLAMA_PUERTO", "11439"))
_propio = {"url": None, "proc": None, "no": os.environ.get("TRAILER_OLLAMA_PROPIO") == "0", "probado": 0.0}


def _apagar_propio():
    p, _propio["proc"], _propio["url"] = _propio["proc"], None, None
    if p is not None:
        try:
            p.kill()
        except OSError:
            pass


_candado_propio = threading.Lock()


OPCIONES_SERVIDOR = {"OLLAMA_FLASH_ATTENTION": os.environ.get("TRAILER_OLLAMA_FA", "1"),
                     "OLLAMA_KV_CACHE_TYPE": os.environ.get("TRAILER_OLLAMA_KV", "q8_0")}


def servidor_rapido(nombre=None):
    """Deja las preguntas yendo al servidor propio (PARALELO a la vez de verdad). True si quedo; False: el de siempre.
    nombre: el modelo de vision (se descarga del servidor de siempre para que quepa en la GPU)."""
    if _propio["no"]:
        return False
    url = "http://127.0.0.1:%d" % PUERTO_PROPIO
    with _candado_propio:
        if _propio["url"]:
            return True
        if time.time() - _propio["probado"] < 120:
            return False
        _propio["probado"] = time.time()

        def vivo():
            try:
                _pedir("/api/version", timeout=1.0, base=url)
                return True
            except Exception:
                return False
        if not vivo():                           # (si quedo uno de una vez anterior, se aprovecha)
            exe = _exe_ollama()
            if not exe:
                return False
            try:
                _propio["proc"] = subprocess.Popen(
                    [exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                    creationflags=rutas.SIN_VENTANA,
                    env=dict(os.environ, OLLAMA_HOST="127.0.0.1:%d" % PUERTO_PROPIO, OLLAMA_NUM_PARALLEL=str(PARALELO),
                             OLLAMA_MAX_LOADED_MODELS="1", **OPCIONES_SERVIDOR))
            except OSError:
                return False
            import atexit
            atexit.register(_apagar_propio)
            for _ in range(30):
                time.sleep(0.5)
                if vivo():
                    break
            else:
                _apagar_propio()
                return False
        try:                                     # el modelo, fuera del servidor de siempre: no caben los dos en la GPU
            for m in _pedir("/api/ps", timeout=3.0, base=URL).get("models") or []:
                if nombre and (m.get("name") or m.get("model")) == nombre:
                    _pedir("/api/generate", {"model": nombre, "prompt": "", "keep_alive": 0}, timeout=60.0, base=URL)
        except Exception:
            pass
        _propio["url"] = url
        return True


def _arrancar_ollama():
    """Si Ollama esta instalado pero apagado, lo enciende (sin ventana) y espera un poco."""
    exe = _exe_ollama()
    if not exe:
        return False
    try:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         creationflags=rutas.SIN_VENTANA)
    except OSError:
        return False
    for _ in range(20):
        time.sleep(0.5)
        try:
            _pedir("/api/tags", timeout=1.0)
            return True
        except Exception:
            pass
    return False


def modelo(log=None):
    """El mejor modelo de vision instalado en Ollama, o None (sin Ollama o sin modelo que vea)."""
    if _estado["modelo"] or time.time() - _estado["probado"] < 60:
        return _estado["modelo"]
    _estado["probado"] = time.time()
    try:
        tags = _pedir("/api/tags", timeout=1.5)
    except Exception:
        if not _arrancar_ollama():
            return None
        try:
            tags = _pedir("/api/tags", timeout=3.0)
        except Exception:
            return None
    nombres = [m.get("name") or m.get("model") for m in tags.get("models") or []]
    forzado = os.environ.get("TRAILER_VISION_MODELO")
    if forzado:
        _estado["modelo"] = forzado if forzado in nombres else None
        return _estado["modelo"]
    ven = []
    for n in nombres:
        try:
            caps = _pedir("/api/show", {"model": n}, timeout=5.0).get("capabilities") or []
        except Exception:
            caps = []
        if "vision" in caps or any(p in n.lower() for p in PREFERIDOS):
            ven.append(n)

    import re

    def orden(n):
        bajo = n.lower()
        # (18-nov) con qwen3-vl:4b y :8b instalados ganaba el 4b por orden alfabetico, y el 4b deja pasar 15 de 40
        # cuadros malos (medido): a igual familia, el de MAS parametros primero
        tam = re.search(r":(\d+(?:\.\d+)?)b", bajo)
        return (next((k for k, p in enumerate(PREFERIDOS) if p in bajo), len(PREFERIDOS)), "instruct" not in bajo,
                -float(tam.group(1)) if tam else 0.0, n)
    ven.sort(key=orden)
    _estado["modelo"] = ven[0] if ven else None
    if log and _estado["modelo"]:
        log("IA local para ver las tomas: %s (Ollama)" % _estado["modelo"])
    return _estado["modelo"]


def _foto(ruta, lado=448):
    """La foto, derecha (EXIF) y chica, en JPEG base64. (Con ffmpeg y -ss, una foto sale vacia.)"""
    try:
        import io
        from PIL import Image, ImageOps
        with Image.open(ruta) as im0:
            im0.draft("RGB", (lado * 2, lado * 2))
            im = ImageOps.exif_transpose(im0).convert("RGB")
        im.thumbnail((lado, lado))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=85)
        return base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


PESADOS_GPU = (("Resolve.exe", "DaVinci Resolve"), ("PureRAW", "DxO PureRAW"), ("Photoshop.exe", "Photoshop"),
               ("Adobe Premiere Pro.exe", "Premiere"), ("AfterFX.exe", "After Effects"), ("Lightroom.exe", "Lightroom"),
               ("Topaz", "Topaz"), ("CineCaptions", "CineCaptions"))


def memoria_video():
    """(usados_GB, total_GB, [programas pesados abiertos]) o None si no hay nvidia-smi. (18-nov, medido) con la memoria
    de video llena (15,7 de 16,3 GB: DaVinci + DxO PureRAW + el modelo) la revision cuadro por cuadro iba a 3,1 s por
    cuadro con la GPU al 12 %, y en_gpu() decia que si (el modelo figura entero pero Windows lo intercambia)."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10, creationflags=rutas.SIN_VENTANA)
        usado, total = [float(x) / 1024.0 for x in r.stdout.strip().splitlines()[0].split(",")]
    except Exception:
        return None
    abiertos = []
    try:
        t = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                           creationflags=rutas.SIN_VENTANA).stdout.lower() if os.name == "nt" else ""
        abiertos = [nombre for clave, nombre in PESADOS_GPU if clave.lower() in t]
    except Exception:
        pass
    return usado, total, abiertos


def aviso_memoria(log, s_por_cuadro=None):
    """Si la memoria de video va llena (o la IA fue lenta), lo dice claro con los programas que la ocupan."""
    m = memoria_video()
    if not m:
        return
    usado, total, abiertos = m
    lento = s_por_cuadro is not None and s_por_cuadro > 1.5
    if usado / max(0.1, total) > 0.85 or lento:
        log("AVISO: la memoria de video va %s (%.1f de %.1f GB)%s: la IA local va varias veces más lenta%s. Para ir "
            "rápido, cierra %s antes de pulsar ▶." % (
                "llena" if usado / max(0.1, total) > 0.85 else "justa", usado, total,
                " con %s %s" % (" y ".join(abiertos), "abiertos" if len(abiertos) > 1 else "abierto") if abiertos else "",
                " (%.1f s por cuadro; con la GPU libre, 0,8)" % s_por_cuadro if lento else "",
                " y ".join(abiertos) if abiertos else "los programas que usen la tarjeta"))


def en_gpu(minimo=0.8):
    """¿El modelo cabe en la GPU? (cargado, con al menos `minimo` de su tamaño en la memoria de video). Con DaVinci
    abierto la GPU puede estar casi llena: el modelo queda en el procesador y cada consulta tarda 5-10 veces mas."""
    nombre = modelo()
    if not nombre:
        return False
    def parte():
        _pedir("/api/generate", {"model": nombre, "prompt": "", "keep_alive": "10m",    # que este cargado (sin imagen)
                                 "options": {"num_ctx": NUM_CTX}}, timeout=180.0)
        for m in _pedir("/api/ps", timeout=5.0).get("models") or []:
            if (m.get("name") or m.get("model")) == nombre and m.get("size"):
                return float(m.get("size_vram") or 0) / float(m["size"])
        return 0.0
    try:
        servidor_rapido(nombre)                  # (18-nov) varias preguntas a la vez de verdad, si se puede
        p = parte()
        if p < minimo:
            # (17-nov) el modelo se QUEDA como se cargo: si entro con DaVinci abierto (80 % en el procesador) sigue asi
            # aunque DaVinci ya este cerrado y la GPU libre (18 s por toma en vez de 3). Se descarga y se carga otra vez.
            _pedir("/api/generate", {"model": nombre, "prompt": "", "keep_alive": 0}, timeout=60.0)
            time.sleep(2.0)
            p = parte()
        if p < minimo and _propio["url"]:
            # con varias preguntas a la vez el modelo ocupa mas memoria de video: si asi no cabe, con el de siempre
            _pedir("/api/generate", {"model": nombre, "prompt": "", "keep_alive": 0}, timeout=60.0)
            _apagar_propio()
            _propio["no"] = True
            time.sleep(2.0)
            p = parte()
        return p >= minimo
    except Exception:
        pass
    return False


def _hay_ollama():
    if shutil.which("ollama"):
        return True
    return any(c and os.path.exists(c) for c in (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        "/Applications/Ollama.app", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"))


def estado():
    """(texto para Ajustes, accion: None | "modelo" | "ollama"). Para la ventana (en un hilo)."""
    _estado["probado"] = 0.0
    _estado["modelo"] = None
    m = modelo()
    if m:
        return ("Lista: %s (Ollama). Ve cada toma: iglesia, fiesta, preparativos, los momentos clave y lo que no sirve."
                % m, None)
    if _hay_ollama():
        return ("Ollama está instalado pero falta el modelo que ve las tomas (%s, unos 6 GB)." % MODELO_RECOMENDADO,
                "modelo")
    return ("No instalada: sin ella se clasifica por hora y color. Con Ollama y %s el programa ve cada toma y arma mejor."
            % MODELO_RECOMENDADO, "ollama")


def instalar_modelo(log=print):
    """Baja el modelo recomendado con Ollama (una sola vez). Devuelve True si quedo."""
    try:
        _pedir("/api/tags", timeout=2.0)
    except Exception:
        if not _arrancar_ollama():
            log("No pude encender Ollama para bajar el modelo.")
            return False
    req = urllib.request.Request(URL + "/api/pull", data=json.dumps({"model": MODELO_RECOMENDADO}).encode(),
                                 headers={"Content-Type": "application/json"})
    ultimo = ""
    try:
        with urllib.request.urlopen(req, timeout=7200) as r:
            for linea in r:
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                st = d.get("status") or ""
                if d.get("total") and d.get("completed"):
                    st += " %d%%" % (100 * d["completed"] // d["total"])
                if st and st != ultimo and (not st[-1:] == "%" or st.endswith("0%")):
                    log("Modelo de IA local: %s" % st)
                    ultimo = st
                if d.get("error"):
                    log("Modelo de IA local: %s" % d["error"])
                    return False
    except Exception as ex:
        log("No se pudo bajar el modelo de IA local: %s" % ex)
        return False
    _estado["probado"] = 0.0
    _estado["modelo"] = None
    return bool(modelo())


# (18-nov, MEDIDO con la boda: iPhone 4K HEVC, 66 cuadros, 6 a la vez) leer con la tarjeta: 0,24 -> 0,15 s por cuadro y
# deja el procesador al oido, que corre a la vez. Los cuadros salen derechos (252x448 en vertical, igual que antes: el
# cuadro baja a la memoria y ffmpeg lo gira). Si la tarjeta falla 3 veces seguidas, se vuelve al procesador.
_hw = {"fallos": 0}


def _cuadro(ruta, t, lado=448):
    base = ["-ss", "%.2f" % max(0.0, t), "-i", ruta, "-frames:v", "1",
            "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (lado, lado),
            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"]
    if _hw["fallos"] < 3:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "cuda"] + base,
                           capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
        if r.returncode == 0 and r.stdout:
            _hw["fallos"] = 0
            return base64.b64encode(r.stdout).decode()
        _hw["fallos"] += 1
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error"] + base,
                       capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
    return base64.b64encode(r.stdout).decode() if r.returncode == 0 and r.stdout else None


INSTANTES_V = 6               # 6 (17-nov): «sonrisa» y estorbo mas estricto (marcaba 328 de 1368; la mitad eran buenas). 2: equipo de filmacion; 3: solo el equipo que TAPA la imagen; 4: ver abajo; 5: tambien
#                               el «estorbo» (un hombro o una espalda pegados al lente, desenfocados, tapando un costado:
#                               la cara de la señora del microfono se veia y pasaba) y las etiquetas solo de momentos clave
# (4) La persona (16-nov), viendo el de 1 min: «hay tomas que no se ve nada, apuntan al techo... hay tomas que no apuntan a
# nada»; «la regla es simple: si sale un humano debe verse la cara, y si sale sin cabeza o algo raro, descartar». Con 3
# cuadros por toma no alcanzaba (una toma de 104 s grabada de cabeza contra el techo salio como «decoracion floral»): ahora
# TODAS las tomas, un cuadro cada 3 s, y a cada uno se le pregunta hacia donde apunta la camara, si esta de cabeza, si se
# ve la cara de alguien y si la persona sale sin cabeza (solo cuerpo, torso, ropa o de espaldas). Lo que falla queda fuera
# del montaje en ese tramo (build_trailers.vista) y, si falla la mayor parte de la toma, la toma entera.
INSTANTES_CADA_S = 3.0        # un cuadro cada tanto (un plano del armado dura 1-3 s)
INSTANTES_DESDE_S = 0.0       # todas las tomas (las cortas, al menos un cuadro)
INSTANTES_MAX = 200           # cuadros como mucho por toma (mas de 10 min: el paso crece)
APUNTA = ("personas", "detalle", "techo", "piso", "pared", "tapado", "equipo", "nada")
APUNTA_BIEN = ("personas", "detalle")
MOTIVOS = {"techo": "apunta al techo", "piso": "apunta al piso", "pared": "apunta a una pared", "tapado": "algo tapa",
           "equipo": "la camara tapa", "nada": "no se ve nada", "de_cabeza": "de cabeza o ladeada",
           "estorbo": "algo pegado al lente tapa un costado", "sin_cabeza": "gente sin cabeza",
           "sin_cara": "no se ve ninguna cara"}
# en cada cuadro solo interesan los momentos clave (para saber EN QUE SEGUNDO estan): la lista entera de etiquetas hacia
# la respuesta larga y lenta («vestido, traje, zapatos» en casi todos)
MOMENTOS_CLAVE = ("beso", "anillos", "votos", "primer_baile", "pastel", "brindis", "entrada", "lagrimas", "risas", "baile")
PROMPT_INSTANTE = (
    "Cuadro de un video de un evento (boda, quinceañera o bautizo). Mira hacia DÓNDE apunta la cámara y a la gente. "
    "Responde SOLO un JSON con:\n"
    "\"apunta\": \"personas\" si se ve a gente del evento, \"detalle\" si es un detalle bonito y claro SIN personas "
    "(anillos, flores, pastel, vestido colgado, mesa decorada, fachada, paisaje), \"techo\" si apunta al techo, lámparas, "
    "vigas o al cielo, \"piso\" si apunta al suelo, \"pared\" si es una pared o una esquina sin nada, \"tapado\" si un "
    "brazo, una espalda, una cabeza o un objeto pegado al lente tapa buena parte de la imagen, \"equipo\" si una cámara, "
    "flash o celular pegado al lente tapa la imagen o se ve la pantalla de una cámara, \"nada\" si no se entiende qué es;\n"
    "\"de_cabeza\": true si la imagen está de cabeza o muy ladeada (más de 30 grados);\n"
    "\"cara\": true si se ve con claridad la CARA de al menos una persona (de frente o de perfil, con la cabeza entera "
    "dentro del cuadro); false si no hay caras o solo se ven nucas, espaldas o caras tapadas o borrosas;\n"
    "\"sin_cabeza\": true si la persona principal sale SIN CABEZA (el cuadro le corta la cabeza) o solo se ve su "
    "cuerpo, torso, brazos, piernas o ropa de cerca, o se ve de espaldas; si no, false;\n"
    "\"estorbo\": true SOLO si algo PEGADO a la cámara (un hombro, una espalda, una cabeza, un brazo, ropa, una silla, "
    "un arreglo) sale BORROSO, desenfocado, y tapa una tercera parte o más de la imagen o a la persona principal; "
    "false si la imagen está limpia. Gente nítida que forma parte de la escena (invitados de pie, alguien que pasa, "
    "la maquillista trabajando, personas en primer plano bien enfocadas) NO es estorbo: false. Ante la duda, false;\n"
    "\"sonrie\": true si la persona principal se ve con claridad SONRIENDO o riendo; si no, false;\n"
    "\"etiquetas\": SOLO los momentos de esta lista que estén pasando en el cuadro (si ninguno, []): %s."
    % ", ".join(MOMENTOS_CLAVE))
# respuesta cerrada (Ollama: «structured outputs»): sin palabras inventadas y sin texto de mas (va mas rapido)
FORMATO_INSTANTE = {"type": "object", "properties": {
    "apunta": {"type": "string", "enum": list(APUNTA)}, "de_cabeza": {"type": "boolean"},
    "cara": {"type": "boolean"}, "sin_cabeza": {"type": "boolean"}, "estorbo": {"type": "boolean"},
    "sonrie": {"type": "boolean"},
    "etiquetas": {"type": "array", "items": {"type": "string", "enum": list(MOMENTOS_CLAVE)}}},
    "required": ["apunta", "de_cabeza", "cara", "sin_cabeza", "estorbo", "sonrie", "etiquetas"]}


def motivo_cuadro(d):
    """'' si el cuadro sirve; si no, la razon (una clave de MOTIVOS). La regla de la persona: si sale gente, se le tiene
    que ver la cara; sin cabeza, solo cuerpo, de espaldas o algo raro, fuera."""
    apunta = str(d.get("apunta") or "nada").strip().lower()
    if apunta not in APUNTA_BIEN:
        return apunta if apunta in APUNTA else "nada"
    if _si(d.get("de_cabeza")):
        return "de_cabeza"
    if _si(d.get("estorbo")):
        return "estorbo"
    if apunta == "personas":
        if _si(d.get("sin_cabeza")):
            return "sin_cabeza"
        if not _si(d.get("cara")):
            return "sin_cara"
    return ""


def _ver_cuadro(nombre, img):
    cuerpo = {"model": nombre, "stream": False, "format": FORMATO_INSTANTE, "keep_alive": "10m",
              "options": {"temperature": 0, "num_predict": 160, "num_ctx": NUM_CTX},
              "messages": [{"role": "user", "content": PROMPT_INSTANTE, "images": [img]}]}
    d = json.loads(_pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
    et = [e for e in (str(x).strip().lower().replace(" ", "_") for x in d.get("etiquetas") or []) if e in MOMENTOS_CLAVE]
    motivo = motivo_cuadro(d)
    if not motivo and _si(d.get("sonrie")) and _si(d.get("cara")):
        et.append("sonrisa")                     # (v6) el armado prefiere cortar donde la persona sonrie
    return et, motivo


SIN_MIRAR = "medidas"         # motivo de un cuadro que la IA no miro (sirve = None: ni bueno ni malo)
FALLO = "fallo"               # (1.8.0) la IA no contesto ese cuadro (sirve = None, igual que no mirado)
FALLOS_TOPE = 0.10            # mas de 1 de cada 10 cuadros sin respuesta: la toma no se guarda como revisada


def instantes(ruta, dur, log=None, fuera=None, limite=None, dron=False):
    """(1.5.7) Lo que pasa a lo largo de la toma: [[segundo, [etiquetas], sirve, motivo], ...] cada INSTANTES_CADA_S s
    (motivo: '' si sirve, si no una clave de MOTIVOS). Asi el armado sabe EN QUE SEGUNDO esta el beso, los anillos o el
    pastel, y en que tramos la camara apunta al techo, sale gente sin cabeza o no se ve ninguna cara.

    (18-nov) fuera = [(a, b)] tramos que las MEDIDAS ya dejan fuera del montaje (desenfocado, quemado, barrido, temblor,
    a oscuras: receta.tramos_fuera, las mismas cuentas del armado). Esos cuadros no se le preguntan a la IA (1 de cada
    5 en la XV del 8-nov): quedan como [segundo, [], None, "medidas"] para que el paso entre cuadros siga igual.
    limite: la parte mala desde la que la toma entera queda fuera (None: la toma ya esta fuera por las medidas, no importa).
    Los cuadros salen con ffmpeg aparte y la IA mira PARALELO a la vez, tambien dentro de una misma toma."""
    nombre = modelo(log)
    if not nombre or dur <= 0 or dur < INSTANTES_DESDE_S:
        return None
    paso = max(INSTANTES_CADA_S, dur / float(INSTANTES_MAX))
    tiempos, t = [], paso / 2.0
    while t < dur - 0.3:
        tiempos.append(t)
        t += paso
    tiempos = tiempos or [dur / 2.0]

    def ver(cuadro):
        rutas.revisar_parada()                    # «Cancelar»: lo que quedaba en fila no se pregunta
        img = cuadro.result()
        return _ver_cuadro(nombre, img) if img else None
    def pedir(t):
        return _pozo("modelo", PARALELO).submit(ver, cuadros(ruta, [t])[0])

    pedidos, fallos = [0], [0]

    def recoger(t, tarea):
        pedidos[0] += 1
        try:
            r = tarea.result()
        except rutas.Detenido:
            raise
        except Exception:
            r = None
        if not r:
            # (1.8.0, auditoria) antes el cuadro fallido DESAPARECIA y, si fallaban todos (Ollama caido), la toma
            # quedaba guardada como «revisada, nada malo» para siempre. Ahora queda como no mirado (sirve = None) y,
            # si fallan muchos, la toma no se guarda: se vuelve a mirar la proxima vez
            fallos[0] += 1
            return [round(t, 1), [], None, FALLO]
        return [round(t, 1), r[0], not r[1], r[1]]
    # un cuadro «vale» por medio paso a cada lado: se salta solo si TODO ese tramo ya esta fuera (con medio segundo de
    # margen se colaban 2 planos en 750 pegados a un cuadro que la IA habia marcado malo; asi, ninguno, y cuesta 40 s)
    margen = paso / 2.0
    tareas = [None if any(a <= max(0.0, t - margen) and min(dur, t + margen) <= b for a, b in fuera or ()) else pedir(t)
              for t in tiempos]
    out = [[round(t, 1), [], None, SIN_MIRAR] if tarea is None else recoger(t, tarea) for t, tarea in zip(tiempos, tareas)]
    # «si la mayor parte de la toma no sirve, la toma entera fuera» (parte_mala contra `limite`): si los cuadros saltados
    # pueden cambiar esa cuenta, tambien se miran (asi la regla da lo mismo que mirandolos todos)
    saltados = [k for k, x in enumerate(out) if x is not None and x[2] is None]
    n = sum(1 for x in out if x is not None)
    if limite and saltados and n >= 2:
        malos = sum(1 for x in out if x is not None and cuadro_malo(x, dron))
        if malos / float(n) < limite <= (malos + len(saltados)) / float(n):
            for k, tarea in [(k, pedir(tiempos[k])) for k in saltados]:
                out[k] = recoger(tiempos[k], tarea)
    if fallos[0] and fallos[0] > max(1, FALLOS_TOPE * pedidos[0]):
        if log:
            log("Aviso: la IA local no contestó en %d de %d cuadros de %s: la vuelvo a revisar la próxima vez." % (
                fallos[0], pedidos[0], os.path.basename(ruta)))
        return None
    return [x for x in out if x is not None]


def revisar_foto(ruta, log=None):
    """(16-nov) La misma revision para una foto (o una captura de video): [[0, etiquetas, sirve, motivo]] o None."""
    nombre = modelo(log)
    if not nombre:
        return None
    img = _foto(ruta)
    if not img:
        return None
    try:
        et, motivo = _ver_cuadro(nombre, img)
    except Exception:
        return None
    return [[0.0, et, not motivo, motivo]]


SOLO_CARAS = ("sin_cara", "sin_cabeza", "piso")   # el dron ve desde arriba: ni caras ni «apunta al piso» (la iglesia
#                                                   y el pueblo vistos desde el aire salian como «piso»)


# (16-nov) el «estorbo» es BLANDO: en la boda marco 339 de 1068 cuadros y, mirados al azar, la mitad eran tomas con
# algo de gente delante que si sirven (la salida de la iglesia entre invitados). No tira tomas ni tramos: el armado
# prefiere lo limpio (build_trailers.ia_tramos) y lo usa solo si no hay nada mejor de ese momento.
BLANDOS = ("estorbo",)


def cuadro_malo(x, dron=False):
    """El instante [t, etiquetas, sirve, motivo] no sirve (al dron no se le piden caras; el estorbo es blando)."""
    if len(x) < 3 or x[2] is not False:
        return False
    motivo = x[3] if len(x) > 3 else ""
    return not (motivo in BLANDOS or (dron and motivo in SOLO_CARAS))


def parte_mala(ia, dron=False):
    """(parte 0-1 de la toma que la IA vio que no sirve, motivo mas comun) segun sus instantes; (0, '') sin instantes."""
    # (18-nov) los cuadros saltados por las medidas (sirve = None) cuentan en el total y no como malos: si podian
    # cambiar el resultado contra el limite, instantes() ya los miro
    inst = [x for x in (ia or {}).get("instantes") or [] if len(x) >= 3]
    if not inst:
        return 0.0, ""
    malos = [x[3] if len(x) > 3 else "" for x in inst if cuadro_malo(x, dron)]
    if not malos:
        return 0.0, ""
    comun = max(set(malos), key=malos.count)
    return len(malos) / float(len(inst)), comun


def describir(tipo, ruta, dur=0.0, log=None):
    """Lo que la IA ve en esa toma (3 cuadros de un video, o la foto), o None si no se pudo."""
    nombre = modelo(log)
    if not nombre:
        return None
    if tipo == "foto":
        imgs = [_foto(ruta)]
    else:
        imgs = []
        for f in cuadros(ruta, [dur * (k + 1) / 4.0 for k in range(3)] if dur > 0 else [0.0]):    # los 3 a la vez
            try:
                imgs.append(f.result())
            except Exception:
                pass
    imgs = [x for x in imgs if x]
    if not imgs:
        return None
    cuerpo = {"model": nombre, "stream": False, "format": "json", "keep_alive": "10m",
              "options": {"temperature": 0, "num_predict": 200, "num_ctx": NUM_CTX},
              "messages": [{"role": "user", "content": PROMPT, "images": imgs}]}
    try:
        resp = _pedir("/api/chat", cuerpo, timeout=300.0)
        d = json.loads(resp["message"]["content"])
    except Exception as ex:
        if log and not isinstance(ex, IACaida):          # (en pausa no se repite el aviso por cada toma)
            log("Aviso: la IA local no pudo ver %s (%s)" % (os.path.basename(ruta), str(ex)[:80]))
        # (1.8.0) False = no contesto (caida, plazo): no cuenta como intento; None = contesto algo roto
        return False if isinstance(ex, (OSError, TimeoutError)) else None
    mom = MOMENTO.get(str(d.get("momento") or "").strip().upper(), "OTRO")
    etiquetas = [e for e in (str(x).strip().lower().replace(" ", "_") for x in d.get("etiquetas") or []) if e in ETIQUETAS]
    util = d.get("util")
    # (v3) solo cuenta el equipo que TAPA la imagen (la camara del camarografo en primer plano): esa toma no sirve
    equipo = _si(d.get("equipo"))
    try:                                         # (v4, 17-nov) que tan bonita es la toma: ordena lo bueno (lo_que_ve)
        belleza = max(1, min(10, int(round(float(d.get("belleza"))))))
    except (TypeError, ValueError):
        belleza = None
    return {"v": VERSION, "modelo": nombre, "momento": mom, "escena": str(d.get("escena") or "")[:80],
            "etiquetas": etiquetas, "equipo": equipo, "belleza": belleza,
            "util": not equipo and util is not False and str(util).lower() != "false"}


# (1.6.0) LA MIRADA: que la imagen final y las fotos de la intro no salgan con los ojos cerrados (la persona eligio esta
# mejora: «foto final sin ojos cerrados»). Solo para unas pocas fotos (las mejores candidatas, analizar_material.
# _miradas_con_ia), con la GPU libre, y queda en el cache («mirada»).
MIRADA_V = 1
PROMPT_MIRADA = (
    "Foto de un evento (boda, quinceañera o bautizo). Mira a la persona principal (la más grande o la del centro; si es "
    "una pareja, a los dos). Responde SOLO un JSON con:\n"
    "\"ojos\": \"abiertos\" si tiene los ojos abiertos, \"cerrados\" si los tiene cerrados o a medio cerrar (parpadeando o "
    "con los ojos entrecerrados), \"no_se_ve\" si no se le ve bien la cara;\n"
    "\"sonrie\": true si sonríe o se ve feliz; false si no;\n"
    "\"mira\": true si mira a la cámara; false si no.")
FORMATO_MIRADA = {"type": "object", "properties": {
    "ojos": {"type": "string", "enum": ["abiertos", "cerrados", "no_se_ve"]}, "sonrie": {"type": "boolean"},
    "mira": {"type": "boolean"}}, "required": ["ojos", "sonrie", "mira"]}


def mirada(ruta, log=None):
    """{"v", "ojos": abiertos|cerrados|no_se_ve, "sonrie", "mira"} de una foto, o None (sin IA local o si falla)."""
    nombre = modelo()
    img = _foto(ruta) if nombre else None
    if not img:
        return None
    cuerpo = {"model": nombre, "stream": False, "format": FORMATO_MIRADA, "keep_alive": "10m",
              "options": {"temperature": 0, "num_predict": 60, "num_ctx": NUM_CTX},
              "messages": [{"role": "user", "content": PROMPT_MIRADA, "images": [img]}]}
    try:
        d = json.loads(_pedir("/api/chat", cuerpo, timeout=120.0)["message"]["content"])
    except Exception as ex:
        if log:
            log("Aviso: la IA local no pudo ver la mirada en %s (%s)" % (os.path.basename(ruta), str(ex)[:80]))
        return None
    ojos = str(d.get("ojos") or "").strip().lower()
    return {"v": MIRADA_V, "ojos": ojos if ojos in ("abiertos", "cerrados", "no_se_ve") else "no_se_ve",
            "sonrie": _si(d.get("sonrie")), "mira": _si(d.get("mira"))}


def _si(x):
    return x is True or str(x).strip().lower() in ("true", "si", "sí", "yes", "1")
