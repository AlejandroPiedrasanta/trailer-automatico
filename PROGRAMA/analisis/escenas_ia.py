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
VERSION = 2               # 2: votos mal oidos ("en la salud...") y sin discursos repetitivos
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


def _clave(ruta):
    return "%s|%d" % (os.path.basename(ruta), os.path.getsize(ruta))


def leer_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            j = json.load(f)
        return j.get("clips", {}) if j.get("version") == VERSION else {}
    except Exception:
        return {}


def _guardar_cache(clips):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "clips": clips}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)


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
                datos = {"categoria": "", "subcategoria": "", "frases": []}
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
                    except Exception as ex:
                        log("  %s: no se pudo transcribir (%s)" % (it["nombre"], ex))
                cache[k] = datos
                if datos["frases"]:
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


def aplicar(items, cache=None):
    """Pega lo que entendio Resolve a los items del analisis: it['frases'], it['categoria_audio']."""
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
            it["categoria_audio"] = d.get("categoria", "")
            n += len(it["frases"])
    return n
