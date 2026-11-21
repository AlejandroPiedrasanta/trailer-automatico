# -*- coding: utf-8 -*-
"""
escenas_ia.py - Lo que DaVinci Resolve Studio sabe de cada toma, para que el armado "entienda" las escenas.

Usa las IA de Resolve que SI devuelven datos al script (probado en Resolve Studio 21.2):
  - Clasificacion de audio (MediaPoolItem.PerformAudioClassification): deja el metadato Category / Subcategory
    (dialogo, musica, efecto...).
  - Transcripcion (TranscribeAudio + GetTranscription): frases y palabras con su tiempo, en espanol.
Con eso encuentra los momentos clave: VOTOS ("si, acepto", "te prometo"), DECLARACION ("los declaro marido y mujer",
"puede besar a la novia"), AMOR ("te amo"), XV ("mis quince"), BRINDIS ("salud") y DISCURSOS. Los marca en el media
pool (marcador lavanda con la frase) y los entrega al armado: voz sobre la musica y camara lenta en esos instantes.

IntelliSearch NO devuelve nada al script (solo sirve para buscar a mano en Resolve): va al final (indexar.py).
OJO: la transcripcion y la clasificacion solo funcionan con la pagina MEDIOS abierta (en Entrega devuelven False);
este modulo la abre y al terminar vuelve a la pagina que estaba.
Cache: datos/analisis/escenas.json (clave nombre|tamano): no se transcribe dos veces.
"""
import os
import re
import json
import time
import unicodedata

import rutas

CACHE = os.path.join(rutas.ANALISIS, "escenas.json")
VERSION = 4               # 2: votos mal oidos ("en la salud...") y sin discursos repetitivos; 3: pasajes de habla;
#                           4: quien habla en cada pasaje (la transcripcion de Resolve 21 trae el hablante)
# Las PERSONAS que reconoce Resolve Studio (IntelliSearch con caras): al analizar un clip o una foto deja en su
# metadato «People» las caras que aparecen ("Rostro 3, Rostro 6"...), las mismas de un archivo a otro. Con eso se
# sabe quien es la persona festejada (la cara que sale en mas fotos), que tomas no tienen a nadie de frente (el piso,
# espaldas, detalles) y en cuales sale ella. Cache: datos/analisis/personas.json (clave nombre|tamano).
PERSONAS = os.path.join(rutas.ANALISIS, "personas.json")
PROTAS_POR_TIPO = {"boda": 2}       # cuantas personas son "la protagonista" (en una boda, los dos)
PROTA_MINIMO = 0.08                 # debe salir al menos en esta parte de lo analizado para contar como protagonista
COLOR_MARCADOR = "Lavender"

# lo que el modelo "oye" en musica o ruido (alucinaciones tipicas de los transcriptores): se descarta
ALUCINACIONES = ("suscrib", "gracias por ver", "subtitul", "amara.org", "www", ".com", "dale like", "like y",
                 "comparte", "proximo video", "nos vemos en", "musica", "aplausos", "risas", "gracias por su atencion",
                 "hasta la proxima", "canal", "transcripcion", "♪")
PATRONES = {
    # los votos se oyen mal a veces ("en la salud de la febrera" = "en la salud y en la enfermedad"): por eso
    # tambien cuentan los pedazos sueltos de la formula
    "VOTOS": [r"\b(si,? )?acepto\b", r"\bte (acepto|recibo|tomo) (a ti|como)\b", r"\b(te )?prometo\b",
              r"\ben la salud\b", r"\ben la (enfermedad|prosperidad|adversidad)\b", r"\btodos los dias de mi vida\b",
              r"\bhasta que la muerte\b", r"\bserte fiel\b", r"\bte sere fiel\b", r"\brespetarte\b"],
    "DECLARACION": [r"\blos declaro\b", r"\bmarido y mujer\b", r"\besposo y esposa\b", r"\bpuede besar\b",
                    r"\bbesar a la novia\b", r"\bya pueden\b.*\bbes"],
    "AMOR": [r"\bte amo\b", r"\bte quiero\b", r"\bpara siempre\b", r"\bel amor de mi vida\b"],
    "XV": [r"\bquince\b", r"\bmis xv\b", r"\bfeliz cumpleanos\b", r"\bprincesa\b", r"\bfelicidades\b"],
    "BRINDIS": [r"(?<!en la )\bsalud\b", r"\bbrindis\b", r"\bbrindemos\b", r"\blevantemos (las|nuestras) copas\b"],
}
PESO_TIPO = {"VOTOS": 1.0, "DECLARACION": 0.95, "AMOR": 0.85, "XV": 0.8, "BRINDIS": 0.7, "DISCURSO": 0.55}
EMOCION = ("gracias", "familia", "orgullos", "siempre", "corazon", "felices", "juntos", "amor", "vida", "dios",
           "bendicion", "hija", "hijo", "papa", "mama", "sueno", "nunca", "mejor", "hermos", "lindo", "feliz")
CLASES_DIALOGO = ("dialog", "dialogo", "speech", "voz", "habla")
# pasajes de habla de corrido (para la voz original de los videos largos)
FE = ("dios", "senor", "cristo", "jesus", "bendi", "oracion", "oremos", "amen", "biblia", "iglesia", "gloria",
      "espiritu", "pastor", "salmo", "proverbio", "evangelio")
PAUSA_PASAJE = 1.6          # s de silencio que aun es el mismo pasaje (respira, aplausos cortos)
PASAJE_MIN_S = 5.0          # s minimos hablando de corrido
PASAJE_MIN_PALABRAS = 12
PESO_PASAJE = {"BRINDIS": 1.0, "VOTOS": 1.0, "PASTOR": 0.9, "DISCURSO": 0.8}


def _normal(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def _tc_seg(tc, fps):
    """'HH:MM:SS:FF' (o ';FF') -> segundos."""
    m = re.match(r"(\d+):(\d+):(\d+)[:;.](\d+)", str(tc or ""))
    if not m:
        return None
    h, mi, s, f = map(int, m.groups())
    base = int(round(fps)) or 24
    return h * 3600 + mi * 60 + s + f / float(base)


def es_alucinacion(texto):
    n = _normal(texto)
    if not n or re.fullmatch(r"[\W_]+", n):
        return True
    if n.startswith(("[", "(")) and n.endswith(("]", ")")):
        return True
    return any(a in n for a in ALUCINACIONES)


def tipo_de(texto):
    n = _normal(texto)
    for tipo, pats in PATRONES.items():
        if any(re.search(p, n) for p in pats):
            return tipo
    palabras = re.findall(r"\w+", n)
    distintas = len(set(palabras)) / float(len(palabras) or 1)      # "¡que lindo! ¡que lindo!..." no es un discurso
    if len(palabras) >= 8 and distintas >= 0.7 and sum(1 for w in palabras if w.startswith(EMOCION)) >= 2:
        return "DISCURSO"
    return None


def _limpio(texto):
    """Sin los '(...)' que pone la transcripcion en las pausas y sin espacios dobles."""
    return re.sub(r"\s+", " ", re.sub(r"\(\s*\.\.\.\s*\)", " ", texto or "")).strip(" ,")


def frases_de(transcripcion, inicio_tc, fps, dur):
    """De la transcripcion de Resolve a [{ini, fin, texto, tipo, puntaje}] en segundos desde el inicio del clip.
    Recorta las frases largas a la parte importante con las palabras (8 s como mucho)."""
    out, previo = [], None
    for seg in (transcripcion or {}).get("segments") or []:
        texto = _limpio(seg.get("text"))
        if es_alucinacion(texto) or _normal(texto) == previo:
            continue
        previo = _normal(texto)
        a, b = _tc_seg(seg.get("start"), fps), _tc_seg(seg.get("end"), fps)
        if a is None or b is None:
            continue
        if inicio_tc and a >= inicio_tc - 1:            # tiempos en el codigo de tiempo de la camara
            a, b = a - inicio_tc, b - inicio_tc
        a, b = max(0.0, a), min(dur or b, b)
        if b - a < 0.6:
            continue
        tipo = tipo_de(texto)
        if tipo is None:
            continue
        palabras = []
        for w in seg.get("words") or []:
            wa, wb = _tc_seg(w.get("start"), fps), _tc_seg(w.get("end"), fps)
            if wa is not None and wb is not None:
                if inicio_tc and wa >= inicio_tc - 1:
                    wa, wb = wa - inicio_tc, wb - inicio_tc
                palabras.append((wa, wb, w.get("text") or ""))
        if b - a > 8.0 and palabras:                     # la frase larga: la ventana de 8 s con la parte clave
            claves = [k for k, (_, _, w) in enumerate(palabras) if tipo_de(w) == tipo] or [0]
            k0 = claves[0]
            a = palabras[max(0, k0 - 4)][0]
            b = min(a + 8.0, palabras[min(len(palabras) - 1, k0 + 10)][1])
            texto = " ".join(w for wa, wb, w in palabras if a - 0.01 <= wa and wb <= b + 0.01).strip() or texto
        dur_f = b - a
        ideal = 1.0 - min(1.0, abs(dur_f - 4.0) / 6.0) * 0.5
        out.append({"ini": round(a, 2), "fin": round(b, 2), "texto": texto[:160], "tipo": tipo,
                    "puntaje": round(PESO_TIPO[tipo] * ideal, 3)})
    return out


def pasajes_de(transcripcion, inicio_tc, fps, dur):
    """Los tramos donde alguien HABLA DE CORRIDO (la palabra del pastor, un brindis, un discurso), no frases sueltas ni
    voces del publico: oraciones seguidas (pausas de hasta PAUSA_PASAJE s) que juntas duran al menos PASAJE_MIN_S y
    traen PASAJE_MIN_PALABRAS palabras a ritmo de habla. Devuelve [{ini, fin, texto, tipo, puntaje, oraciones}] con
    `oraciones` = [[ini, fin, n_palabras]] para recortar el pasaje en limites de oracion (nunca a media palabra)."""
    oraciones, previo = [], None
    for seg in (transcripcion or {}).get("segments") or []:
        texto = _limpio(seg.get("text"))
        if es_alucinacion(texto) or _normal(texto) == previo:
            continue
        previo = _normal(texto)
        a, b = _tc_seg(seg.get("start"), fps), _tc_seg(seg.get("end"), fps)
        if a is None or b is None:
            continue
        if inicio_tc and a >= inicio_tc - 1:
            a, b = a - inicio_tc, b - inicio_tc
        a, b = max(0.0, a), min(dur or b, b)
        n = len(re.findall(r"\w+", _normal(texto)))
        if b - a < 0.4 or n < 1:
            continue
        oraciones.append((a, b, n, texto, str(seg.get("speaker") or "")))
    grupos = []
    for o in oraciones:
        if grupos and o[0] - grupos[-1][-1][1] <= PAUSA_PASAJE:
            grupos[-1].append(o)
        else:
            grupos.append([o])
    out = []
    for g in grupos:
        a, b = g[0][0], g[-1][1]
        texto = " ".join(o[3] for o in g)
        normal = _normal(texto)
        palabras = re.findall(r"\w+", normal)
        if b - a < PASAJE_MIN_S or len(palabras) < PASAJE_MIN_PALABRAS:
            continue
        ritmo = len(palabras) / (b - a)
        distintas = len(set(palabras)) / float(len(palabras))
        if not 1.0 <= ritmo <= 4.5 or distintas < 0.45:      # muy lento = palabras sueltas; muy repetido = un coro
            continue
        fe = sum(1 for w in palabras if w.startswith(FE))
        emo = sum(1 for w in palabras if w.startswith(EMOCION))
        if any(re.search(p, normal) for p in PATRONES["BRINDIS"]):
            tipo = "BRINDIS"
        elif any(re.search(p, normal) for p in PATRONES["VOTOS"] + PATRONES["DECLARACION"]):
            tipo = "VOTOS"
        elif fe >= 2:
            tipo = "PASTOR"
        else:
            tipo = "DISCURSO"
        puntaje = PESO_PASAJE[tipo] * min(1.0, (b - a) / 20.0) ** 0.5 * (0.6 + 0.4 * min(1.0, (fe + emo) / 6.0))
        # quien habla (lo dice la transcripcion de Resolve): el pasaje es de quien mas habla en el; "pureza" = que
        # parte del pasaje es suya. Un discurso es de una persona; muchas voces mezcladas es el publico.
        por_voz = {}
        for o in g:
            por_voz[o[4]] = por_voz.get(o[4], 0.0) + (o[1] - o[0])
        hablante = max(por_voz, key=lambda k: por_voz[k])
        pureza = por_voz[hablante] / max(0.1, sum(por_voz.values()))
        if hablante and pureza < 0.55:
            continue
        out.append({"ini": round(a, 2), "fin": round(b, 2), "texto": texto[:400], "tipo": tipo, "palabras": len(palabras),
                    "claves": fe + emo, "puntaje": round(puntaje, 3), "hablante": hablante, "pureza": round(pureza, 2),
                    # (1.8.7) con el texto de cada oracion: la IA editora (guion_voz) lee el trozo exacto que sonara
                    "oraciones": [[round(o[0], 2), round(o[1], 2), o[2], o[3][:200]] for o in g]})
    return out


def _clave(ruta):
    return "%s|%d" % (os.path.basename(ruta), os.path.getsize(ruta))


# (18-nov, la persona: «que ya venga incrustado... una carpeta dentro de mis fotos y videos, no tocar, y ahí vayan los
# datos necesarios») Lo que DaVinci tarda en sacar (personas: 21 min; voces: la transcripcion) viaja tambien con el
# material, en la carpeta oculta «.trailer» de cada carpeta del evento (junto a la ficha del analisis): con la cache
# del programa borrada, o en otra PC, se recupera de ahi y DaVinci no vuelve a analizar.
FICHA_DIR = ".trailer"


def _raices():
    try:
        return [r for r in rutas.fuentes() if os.path.isdir(r)]
    except Exception:
        return []


def _leer_viajero(nombre):
    """Lo guardado con el material (todas las carpetas del evento juntas): {clave nombre|tamaño: datos}."""
    out = {}
    arriba = []                                  # (18-nov) tambien en las carpetas de arriba: se pueden soltar subcarpetas
    for raiz in _raices():
        d = os.path.abspath(raiz)
        for _ in range(4):
            if d not in arriba:
                arriba.append(d)
            sup = os.path.dirname(d)
            if not sup or sup == d or len(sup) <= 3:
                break
            d = sup
    for raiz in arriba:
        try:
            with open(os.path.join(raiz, FICHA_DIR, nombre), encoding="utf-8") as f:
                j = json.load(f)
            if isinstance(j, dict) and j.get("version") == VERSION and isinstance(j.get("datos"), dict):
                out.update(j["datos"])
        except Exception:
            pass
    return out


def _guardar_viajero(nombre, datos):
    """Cada carpeta del evento se lleva lo de SUS archivos. Si el disco no deja escribir, el programa sigue con su cache."""
    for raiz in _raices():
        try:
            suyas = set()
            for r, dirs, fs in os.walk(raiz):
                dirs[:] = [d for d in dirs if not d.startswith((".", "$"))]
                for f in fs:
                    try:
                        suyas.add("%s|%d" % (f, os.path.getsize(os.path.join(r, f))))
                    except OSError:
                        pass
            mios = {k: v for k, v in datos.items() if k in suyas}
            if not mios:
                continue
            d = os.path.join(raiz, FICHA_DIR)
            os.makedirs(d, exist_ok=True)
            destino = os.path.join(d, nombre)
            with open(destino + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"version": VERSION, "datos": mios}, f, ensure_ascii=False)
            os.replace(destino + ".tmp", destino)
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(d, 2)      # oculta
        except Exception:
            pass


def leer_cache():
    viajero = _leer_viajero("voces.json")
    try:
        with open(CACHE, encoding="utf-8") as f:
            j = json.load(f)
        return dict(viajero, **(j.get("clips", {}) if j.get("version") == VERSION else {}))
    except Exception:
        return viajero


def _guardar_cache(clips):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "clips": clips}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)
    _guardar_viajero("voces.json", clips)


def _esperar_transcripcion(project, clip, limite):
    fin = time.time() + limite
    while time.time() < fin:
        tr = clip.GetTranscription() or {}
        if tr.get("segments"):
            return tr
        st = (project.GetTranscribeAudioStatus() or {}).get("JobStatus", "")
        if st in ("Complete", "Completed", "Failed", "Cancelled", "Error"):
            return clip.GetTranscription() or {}
        time.sleep(1.0)
    return clip.GetTranscription() or {}


def entender(resolve, project, pares, log=print, transcribir=True):
    """pares: [(MediaPoolItem, item del analisis)] de los videos con audio. Devuelve {clave: {categoria, frases}}
    y deja las frases clave como marcadores en el media pool. Lo ya hecho sale de la cache."""
    cache = leer_cache()
    pendientes = []
    for c, it in pares:
        try:
            k = _clave(it["ruta"])
        except OSError:
            continue
        if k not in cache:
            pendientes.append((k, c, it))
    if pendientes:
        pagina = None
        try:
            pagina = resolve.GetCurrentPage()
            if pagina != "media":
                resolve.OpenPage("media")         # en Entrega la transcripcion devuelve False
                time.sleep(1.0)
        except Exception:
            pass
        log("Escuchando %d videos con la IA de DaVinci (clasificación y transcripción)…" % len(pendientes))
        t0 = time.time()
        try:
            for n, (k, c, it) in enumerate(pendientes, 1):
                datos = {"categoria": "", "subcategoria": "", "frases": [], "pasajes": []}
                try:
                    meta = c.GetMetadata() or {}
                    if not meta.get("Category") and c.PerformAudioClassification():
                        meta = c.GetMetadata() or {}
                    datos["categoria"] = meta.get("Category", "") or ""
                    datos["subcategoria"] = meta.get("Subcategory", "") or ""
                except Exception:
                    pass
                cat = _normal(datos["categoria"])
                vale = transcribir and (any(x in cat for x in CLASES_DIALOGO) or it.get("momento") == "IGLESIA"
                                        or not cat or it.get("momento") == "FIESTA" and "music" not in cat)
                if vale:
                    try:
                        tr = c.GetTranscription() or {}
                        if not tr.get("segments") and c.TranscribeAudio():
                            tr = _esperar_transcripcion(project, c, max(30.0, it.get("dur", 30) * 1.5))
                        fps = float(c.GetClipProperty("FPS") or it.get("fps") or 30)
                        ini_tc = _tc_seg(c.GetClipProperty("Start TC"), fps) or 0.0
                        datos["frases"] = frases_de(tr, ini_tc, fps, it.get("dur", 0))
                        datos["pasajes"] = pasajes_de(tr, ini_tc, fps, it.get("dur", 0))
                    except Exception as ex:
                        log("  %s: no se pudo transcribir (%s)" % (it["nombre"], ex))
                cache[k] = datos
                if datos["pasajes"]:
                    log("  %s: %s" % (it["nombre"], " | ".join("%s %.0f s «%s»" % (f["tipo"], f["fin"] - f["ini"],
                                                                                 f["texto"][:40])
                                                               for f in datos["pasajes"][:2])))
                elif datos["frases"]:
                    log("  %s: %s" % (it["nombre"], " | ".join("%s «%s»" % (f["tipo"], f["texto"][:50])
                                                               for f in datos["frases"][:2])))
                if n % 10 == 0:
                    _guardar_cache(cache)
                    log("  %d/%d escuchados (%.0f s)" % (n, len(pendientes), time.time() - t0))
        finally:
            _guardar_cache(cache)
            try:
                if pagina and pagina != "media":
                    resolve.OpenPage(pagina)
            except Exception:
                pass
    # marcadores lavanda con la frase (para verlos en Resolve), sin repetir
    puestos = 0
    for c, it in pares:
        try:
            datos = cache.get(_clave(it["ruta"])) or {}
        except OSError:
            continue
        if not datos.get("frases"):
            continue
        try:
            fps = float(c.GetClipProperty("FPS") or it.get("fps") or 30)
            for f, m in (c.GetMarkers() or {}).items():          # los «VOZ» de antes se rehacen (reglas nuevas)
                if str(m.get("name", "")).startswith("VOZ ·"):
                    c.DeleteMarkerAtFrame(int(f))
            ya = {int(f) for f in (c.GetMarkers() or {})}
            for fr in datos["frases"]:
                cuadro = int(round(fr["ini"] * fps))
                if cuadro in ya:
                    continue
                if c.AddMarker(cuadro, COLOR_MARCADOR, "VOZ · %s" % fr["tipo"], fr["texto"],
                               max(1, int(round((fr["fin"] - fr["ini"]) * fps)))):
                    puestos += 1
        except Exception:
            pass
    if puestos:
        log("  %d frases clave marcadas en el media pool (marcadores lavanda «VOZ»)." % puestos)
    return cache


def leer_personas():
    viajero = _leer_viajero("personas.json")     # (18-nov) lo que viaja con el material; lo del programa manda
    try:
        with open(PERSONAS, encoding="utf-8") as f:
            j = json.load(f)
        return dict(viajero, **j) if isinstance(j, dict) else viajero
    except Exception:
        return viajero


def _guardar_personas(cache):
    os.makedirs(os.path.dirname(PERSONAS), exist_ok=True)
    with open(PERSONAS + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(PERSONAS + ".tmp", PERSONAS)
    _guardar_viajero("personas.json", cache)


HECHOS_INTELLISEARCH = os.path.join(rutas.ANALISIS, "intellisearch.json")   # lo que ya analizo indexar.py en segundo plano
VIDEOS_LIMITE_S = 600.0             # s que como mucho se dedican a reconocer VIDEOS en un armado (el resto, despues)


def _pantalla_despierta(si):
    """Mientras DaVinci analiza, que no se apague la pantalla ni se suspenda la PC. Con la pantalla apagada Resolve
    entra en su «modo de suspension» y el analisis se queda parado (visto el 2026-11-14: el respaldo automatico del
    proyecto se atasco al 7 % detras del cuadro de IntelliSearch y hubo que cerrar DaVinci). Devuelve lo que haya
    que cerrar despues (el proceso caffeinate en la Mac)."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | (0x00000002 if si else 0))
        elif si and os.uname().sysname == "Darwin":
            import subprocess
            return subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())])
    except Exception:
        pass
    return None


def _con_limite(fn, limite_s):
    """fn() en un hilo aparte, esperando como mucho limite_s: TimeoutError si DaVinci no contesta."""
    import threading
    res = {}

    def correr():
        try:
            res["v"] = fn()
        except Exception as ex:
            res["e"] = ex
    h = threading.Thread(target=correr, daemon=True)
    h.start()
    h.join(limite_s)
    if h.is_alive():
        raise TimeoutError("DaVinci no contesto en %.0f s" % limite_s)
    if "e" in res:
        raise res["e"]
    return res.get("v")


def _por_carpeta(raiz, pendientes):
    """[(Folder, [pendientes de esa carpeta])]: las fotos primero y luego los videos, las carpetas mas cortas antes.
    La llamada analiza la carpeta entera (lo que ya estaba hecho no importa); un pendiente solo va archivo por archivo."""
    de = {}                                      # id del clip -> su carpeta

    def andar(f):
        for c in f.GetClipList() or []:
            de[c.GetUniqueId()] = f
        for s in f.GetSubFolderList() or []:
            andar(s)
    andar(raiz)
    grupos = {}
    for p in pendientes:
        f = de.get(p[3].GetUniqueId())
        if f is not None:
            grupos.setdefault((p[0], f.GetUniqueId()), (f, []))[1].append(p)
    lotes = [v for _, v in sorted(grupos.items(), key=lambda kv: (kv[0][0], sum(g[1] for g in kv[1][1])))]
    return [l for l in lotes if len(l[1]) > 1]


def reconocer(pares, log=print, limite_s=VIDEOS_LIMITE_S, renderizando=None, raiz=None):
    """pares: [(MediaPoolItem, item del analisis)] de fotos y videos. Pasa por IntelliSearch con caras (modo rapido)
    lo que aun no se analizo y lee las personas de cada uno.
    - Primero las fotos (0,7 s cada una): son las que dicen quien es la persona festejada.
    - Luego los videos, los CORTOS primero y durante limite_s como mucho: en los cortos es donde se esconden las
      tomas accidentales, y se clasifican muchos por minuto. Un video largo (la ceremonia entera) tarda minutos y casi
      seguro trae a la festejada: si no da tiempo, queda sin dato (neutro) y lo analiza despues indexar.py.
    - Lo que ya analizo indexar.py en segundo plano no se repite: solo se lee.
    Se guarda cada poco: si se corta, sigue donde iba. Devuelve la cache {clave: [caras]}."""
    cache = leer_personas()
    try:
        with open(HECHOS_INTELLISEARCH, encoding="utf-8") as f:
            hechos = set(json.load(f))
    except Exception:
        hechos = set()

    def personas_de(c):
        return [x.strip() for x in str(c.GetMetadata("People") or "").split(",") if x.strip()]
    pendientes = []
    for c, it in pares:
        try:
            k = _clave(it["ruta"])
        except OSError:
            continue
        if k in cache:
            continue
        try:
            ya = personas_de(c)
        except Exception:
            ya = []
        if ya or k in hechos:                    # ya lo analizo alguien: solo se lee
            cache[k] = ya
            continue
        pendientes.append((0 if it["tipo"] == "foto" else 1, float(it.get("dur") or 0), k, c, it))
    if not pendientes:
        _guardar_personas(cache)
        return cache
    pendientes.sort(key=lambda t: t[:3])
    n_fotos = sum(1 for p in pendientes if p[0] == 0)
    log("Reconociendo a las personas con la IA de DaVinci: %d fotos y %d videos (solo la primera vez)…"
        % (n_fotos, len(pendientes) - n_fotos))
    t0, t_videos, hechos_n = time.time(), None, 0
    despierta = _pantalla_despierta(True)
    # (1.6.1, 17-nov) POR CARPETA: cada llamada a AnalyzeForIntellisearch cuesta ~11 s fijos (XV 8-nov: 12 s por foto,
    # 420 archivos = 80 min). Folder.AnalyzeForIntellisearch hace la carpeta entera de una vez: 0,83 s por foto (medido).
    # Lo que no quede resuelto por carpeta sigue despues archivo por archivo, como antes.
    try:
        lotes = _por_carpeta(raiz, pendientes) if raiz is not None else []
    except Exception as ex:
        log("  (por carpeta no se pudo: %s; sigo archivo por archivo)" % ex)
        lotes = []
    trabado = False
    try:
        for carpeta, grupo in lotes:
            es_video = grupo[0][0]
            if es_video and t_videos is None:
                t_videos = time.time()
            if (renderizando and renderizando()) or (es_video and time.time() - t_videos > limite_s):
                break
            dur = sum(g[1] for g in grupo)
            try:
                if not _con_limite(lambda: carpeta.AnalyzeForIntellisearch(True, False), 120.0 + 3.0 * len(grupo) + 0.6 * dur):
                    continue                     # DaVinci dijo que no: esos van despues uno por uno
            except TimeoutError:
                log("  DaVinci se quedó trabado reconociendo la carpeta %s: sigo sin las caras de lo que falta (cierra la "
                    "ventana «Analizar para IntelliSearch» de DaVinci si quedó abierta)." % carpeta.GetName())
                trabado = True
                break
            except Exception as ex:
                log("  carpeta %s: no se pudo reconocer (%s)" % (carpeta.GetName(), ex))
                continue
            for _, _, k, c, it in grupo:
                try:
                    cache[k] = personas_de(c)
                    hechos_n += 1
                except Exception:
                    pass
            _guardar_personas(cache)
            log("  %d/%d reconocidos (%.0f s)" % (hechos_n, len(pendientes), time.time() - t0))
        pendientes = [] if trabado else [p for p in pendientes if p[2] not in cache]
        for n, (es_video, _, k, c, it) in enumerate(pendientes, 1):
            if es_video and t_videos is None:
                t_videos = time.time()
            if renderizando and renderizando():
                break
            if es_video and time.time() - t_videos > limite_s:
                log("  %d videos largos se reconocen después, en segundo plano." % (len(pendientes) - n + 1))
                break
            try:
                # (1.5.7) con limite: el 2026-11-16 DaVinci se trabo en «Indice de archivos - Inicializando...» con 3
                # videos y el armado espero para siempre (ni su «Cancelar» respondia). Si no termina, se sigue sin las
                # caras de lo que falta (quedan neutras) y se avisa.
                if not _con_limite(lambda: c.AnalyzeForIntellisearch(True, False),
                                   90.0 + 0.6 * float(it.get("dur") or 0)):
                    continue
                cache[k] = personas_de(c)
                hechos_n += 1
            except TimeoutError:
                log("  DaVinci se quedó trabado reconociendo %s: sigo sin las caras de lo que falta (cierra la ventana "
                    "«Analizar para IntelliSearch» de DaVinci si quedó abierta)." % it["nombre"])
                break
            except Exception as ex:
                log("  %s: no se pudo reconocer (%s)" % (it["nombre"], ex))
            if n % 25 == 0:
                _guardar_personas(cache)
                log("  %d/%d reconocidos (%.0f s)" % (n, len(pendientes), time.time() - t0))
    finally:
        _guardar_personas(cache)                 # (en Windows el pedido de pantalla lo suelta motor.SinDormir al terminar)
        if despierta is not None:
            try:
                despierta.terminate()
            except Exception:
                pass
    log("  personas reconocidas en %d archivos (%.0f s)." % (hechos_n, time.time() - t0))
    return cache


def aplicar_personas(items, cache=None, tipo="xv"):
    """Pega las personas a los items: it['caras'] = [...] (None si aun no se analizo) e it['prota'] (sale la persona
    festejada). La protagonista es la cara que sale en mas fotos y videos (en una boda, las dos primeras).
    Devuelve (protagonistas, huella): la huella cambia cuando cambia lo que se sabe (para volver a planificar)."""
    cache = leer_personas() if cache is None else cache
    cuenta, analizados = {}, 0
    for it in items:
        try:
            caras = cache.get(_clave(it["ruta"]))
        except OSError:
            caras = None
        it["caras"] = caras
        if caras is None:
            continue
        analizados += 1
        for c in set(caras):
            cuenta[c] = cuenta.get(c, 0) + 1
    orden = sorted(cuenta, key=lambda c: -cuenta[c])
    protas = [c for c in orden[:PROTAS_POR_TIPO.get(tipo, 1)] if cuenta[c] >= max(3, PROTA_MINIMO * analizados)]
    for it in items:
        it["prota"] = None if it.get("caras") is None else any(c in protas for c in it["caras"])
    return protas, (analizados, tuple(protas))


def aplicar(items, cache=None):
    """Pega lo que entendio Resolve a los items del analisis: it['frases'], it['pasajes'], it['categoria_audio']."""
    cache = leer_cache() if cache is None else cache
    n = 0
    for it in items:
        if it["tipo"] == "foto":
            continue
        try:
            d = cache.get(_clave(it["ruta"]))
        except OSError:
            d = None
        if d:
            it["frases"] = d.get("frases") or []
            it["pasajes"] = d.get("pasajes") or []
            it["categoria_audio"] = d.get("categoria", "")
            n += len(it["frases"]) + 1000 * len(it["pasajes"])
    return n
