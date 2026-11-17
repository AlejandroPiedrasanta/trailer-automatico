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
import urllib.request

import rutas

VERSION = 3                 # 2: pregunta aparte por equipo de filmacion en primer plano (se colaba la camara)
#                             3: tiraba tomas buenas por una camara al fondo o en manos de un invitado: solo cuenta
#                                el equipo pegado al lente que TAPA la imagen (boda: de 20 fuera a solo las de la camara)
PARALELO = 3               # tomas a la vez: ffmpeg saca los cuadros de las siguientes mientras la GPU mira una
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
        a oscuras, algo tapa casi toda la imagen, o no se ve a nadie ni nada del evento; si no, true. Ante la duda, true.""" % \
    ", ".join(ETIQUETAS)

_estado = {"modelo": None, "probado": 0.0}
MODELO_RECOMENDADO = "qwen3-vl:8b-instruct"
DESCARGA_OLLAMA = "https://ollama.com/download"


def _pedir(camino, cuerpo=None, timeout=5.0):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(URL + camino, data=datos, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _arrancar_ollama():
    """Si Ollama esta instalado pero apagado, lo enciende (sin ventana) y espera un poco."""
    exe = shutil.which("ollama")
    for c in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
              "/Applications/Ollama.app/Contents/Resources/ollama", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"):
        if not exe and c and os.path.exists(c):
            exe = c
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

    def orden(n):
        bajo = n.lower()
        return (next((k for k, p in enumerate(PREFERIDOS) if p in bajo), len(PREFERIDOS)), "instruct" not in bajo, n)
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


def en_gpu(minimo=0.8):
    """¿El modelo cabe en la GPU? (cargado, con al menos `minimo` de su tamaño en la memoria de video). Con DaVinci
    abierto la GPU puede estar casi llena: el modelo queda en el procesador y cada consulta tarda 5-10 veces mas."""
    nombre = modelo()
    if not nombre:
        return False
    try:                                         # que este cargado (una consulta minima, sin imagen)
        _pedir("/api/generate", {"model": nombre, "prompt": "", "keep_alive": "10m",
                                 "options": {"num_ctx": NUM_CTX}}, timeout=180.0)
        for m in _pedir("/api/ps", timeout=5.0).get("models") or []:
            if (m.get("name") or m.get("model")) == nombre and m.get("size"):
                return float(m.get("size_vram") or 0) / float(m["size"]) >= minimo
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


def _cuadro(ruta, t, lado=448):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % max(0.0, t), "-i", ruta,
                        "-frames:v", "1", "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (lado, lado),
                        "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"],
                       capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
    return base64.b64encode(r.stdout).decode() if r.returncode == 0 and r.stdout else None


INSTANTES_V = 5               # 2: equipo de filmacion; 3: solo el equipo que TAPA la imagen; 4: ver abajo; 5: tambien
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
    "\"estorbo\": true si algo MUY cerca de la cámara (un hombro, una espalda, una cabeza, un brazo, ropa, una silla, "
    "un arreglo) sale desenfocado y tapa un costado o una parte importante de la imagen (más o menos una cuarta parte o "
    "más); false si la imagen está limpia;\n"
    "\"etiquetas\": SOLO los momentos de esta lista que estén pasando en el cuadro (si ninguno, []): %s."
    % ", ".join(MOMENTOS_CLAVE))
# respuesta cerrada (Ollama: «structured outputs»): sin palabras inventadas y sin texto de mas (va mas rapido)
FORMATO_INSTANTE = {"type": "object", "properties": {
    "apunta": {"type": "string", "enum": list(APUNTA)}, "de_cabeza": {"type": "boolean"},
    "cara": {"type": "boolean"}, "sin_cabeza": {"type": "boolean"}, "estorbo": {"type": "boolean"},
    "etiquetas": {"type": "array", "items": {"type": "string", "enum": list(MOMENTOS_CLAVE)}}},
    "required": ["apunta", "de_cabeza", "cara", "sin_cabeza", "estorbo", "etiquetas"]}


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
    return et, motivo_cuadro(d)


def instantes(ruta, dur, log=None):
    """(1.5.7) Lo que pasa a lo largo de la toma: [[segundo, [etiquetas], sirve, motivo], ...] cada INSTANTES_CADA_S s
    (motivo: '' si sirve, si no una clave de MOTIVOS). Asi el armado sabe EN QUE SEGUNDO esta el beso, los anillos o el
    pastel, y en que tramos la camara apunta al techo, sale gente sin cabeza o no se ve ninguna cara."""
    nombre = modelo(log)
    if not nombre or dur <= 0 or dur < INSTANTES_DESDE_S:
        return None
    paso = max(INSTANTES_CADA_S, dur / float(INSTANTES_MAX))
    tiempos, t = [], paso / 2.0
    while t < dur - 0.3:
        tiempos.append(t)
        t += paso
    out = []
    for t in tiempos or [dur / 2.0]:
        img = _cuadro(ruta, t)
        if img:
            try:
                et, motivo = _ver_cuadro(nombre, img)
                out.append([round(t, 1), et, not motivo, motivo])
            except Exception:
                pass
    return out


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
        imgs = [_cuadro(ruta, dur * (k + 1) / 4.0) for k in range(3)] if dur > 0 else [_cuadro(ruta, 0.0)]
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
        if log:
            log("Aviso: la IA local no pudo ver %s (%s)" % (os.path.basename(ruta), str(ex)[:80]))
        return None
    mom = MOMENTO.get(str(d.get("momento") or "").strip().upper(), "OTRO")
    etiquetas = [e for e in (str(x).strip().lower().replace(" ", "_") for x in d.get("etiquetas") or []) if e in ETIQUETAS]
    util = d.get("util")
    # (v3) solo cuenta el equipo que TAPA la imagen (la camara del camarografo en primer plano): esa toma no sirve
    equipo = _si(d.get("equipo"))
    return {"v": VERSION, "modelo": nombre, "momento": mom, "escena": str(d.get("escena") or "")[:80],
            "etiquetas": etiquetas, "equipo": equipo,
            "util": not equipo and util is not False and str(util).lower() != "false"}


def _si(x):
    return x is True or str(x).strip().lower() in ("true", "si", "sí", "yes", "1")
