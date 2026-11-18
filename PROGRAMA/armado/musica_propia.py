# -*- coding: utf-8 -*-
"""
musica_propia.py - Musica ORIGINAL por estilo en lugar de las canciones de la plantilla.

(17-nov, la persona: «la musica no es acorde, crea musica adecuada para reutilizarla, hay cortes feos») Las plantillas XV
traen canciones de boda y una mezcla de DJ (con sus propios cambios adentro: de ahi los cortes feos) y todas tienen dueño.
Aqui cada cancion de la plantilla tiene un PAPEL (apertura, epica, romantica, fiesta) y se cambia, en el DUPLICADO del
evento (la plantilla no se toca), por pistas propias de recursos/musica/<ESTILO>/ con ese papel (sirven para XV y boda):

    01 INTRO.mp3            -> «apertura» (pista MUSICA INTRO). La apertura es la rampa de velocidad de las 8 fotos y
                               luego arranca el video: la intro va a 144 por minuto (una corchea = 5 cuadros = una
                               foto), con 8 golpes y un IMPACTO; se coloca para que el impacto caiga al terminar las fotos.
    02 ROMANTICA *.mp3      -> «romantica» (preparativos e iglesia)
    03 FIESTA *.mp3         -> «fiesta»
    04 EPICA *.mp3          -> «epica» (llegada, versiones de 3 min en adelante)

Estilos (carpetas): 1 CINE LATINO, 2 JUVENIL, 3 CLASICO, 4 EMOTIVO; se elige con el estado «musica_estilo» o
TRAILER_MUSICA_ESTILO (sin elegir, el primero). Las pistas de un estilo (Higgsfield / ElevenLabs Music, instrumentales)
van en el mismo tono, empiezan en el primer golpe y terminan en un acorde. Un tramo de la plantilla mas largo que una
pista se llena con varias SEGUIDAS: cada una suena hasta su final natural y la siguiente entra ahi (como un disco), sin
cortes a media cancion. Para un tramo corto se prefiere la pista mas corta que lo cubre (las «CORTA» entran de golpe).
Sin carpeta o con TRAILER_MUSICA=plantilla todo sigue como antes.
"""
import json
import os
import subprocess

import rutas

CARPETA = os.path.join(rutas.RECURSOS, "musica")
MIN_S = 5.0                      # tramos mas cortos (risers, golpes) no son canciones
COLA_MIN_S = 8.0                 # una pista no entra para sonar menos que esto: la anterior se corta antes
FOTOS_S = 40 / 24.0              # las 8 fotos de 5 cuadros de la apertura: ahi cae el impacto de la intro
# papel de cada cancion de plantilla, por una palabra de su nombre (lo demas: romantica)
PALABRAS = (("fiesta", ("MIX ", "FIESTA", "BAILABLE", "BAILE")), ("epica", ("FORZA", "EPIC", "EPICA")))
EXT = (".mp3", ".wav", ".m4a", ".flac")
_medidas = None


def activa():
    return os.environ.get("TRAILER_MUSICA", "").lower() != "plantilla" and bool(estilos())


def estilos():
    """Las carpetas de estilo, en orden («1 CINE LATINO», «2 JUVENIL»...)."""
    try:
        return sorted(n for n in os.listdir(CARPETA) if n[:1].isdigit() and os.path.isdir(os.path.join(CARPETA, n)))
    except OSError:
        return []


# (17-nov) sin elegir estilo en Ajustes («Auto»), el del tipo de evento
POR_TIPO = {"xv": "CINE LATINO", "boda": "EMOTIVO", "bautizo": "CLASICO", "graduacion": "JUVENIL", "cumpleanos": "JUVENIL"}


def estilo_elegido(tipo=None):
    """El estilo de Ajustes (estado «musica_estilo») o TRAILER_MUSICA_ESTILO; sin elegir («Auto»), el del tipo de
    evento (POR_TIPO); si no existe, el primero."""
    hay = estilos()
    quiero = os.environ.get("TRAILER_MUSICA_ESTILO", "")
    if not quiero:
        try:
            import motor
            quiero = motor.leer_estado().get("musica_estilo", "")
        except Exception:
            quiero = ""
    q = str(quiero).strip().upper()
    if q == "PLANTILLA":                                    # Ajustes > Sonido > Música > Plantilla
        return ""
    if q in ("", "AUTO"):
        if tipo is None:
            try:
                import motor
                tipo = motor.leer_estado().get("tipo_evento", "xv")
            except Exception:
                tipo = "xv"
        q = POR_TIPO.get(str(tipo or "xv").lower(), "")
    return next((n for n in hay if q and q in n.upper()), hay[0] if hay else "")


def _medir(ruta):
    """(entrada_s, final_s, impacto_s): donde empieza y termina de sonar la pista (-40 dB) y, en sus primeros 6 s, el
    mayor salto de volumen (el impacto de una intro)."""
    import array
    crudo = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                           capture_output=True, timeout=300, creationflags=rutas.SIN_VENTANA).stdout
    m = array.array("h")
    m.frombytes(crudo[:len(crudo) // 2 * 2])
    n = 400                                                          # trozos de 50 ms
    e = [sum(x * x for x in m[i:i + n]) / float(n) for i in range(0, len(m) - n + 1, n)]
    suena = [i for i, v in enumerate(e) if v > 107374.0]             # -40 dB
    if not suena:
        return 0.0, len(m) / 8000.0, 0.0
    r = [v ** 0.5 for v in e]
    mejor, imp, cerca, imp_c = 0.0, 0.0, 0.0, 0.0
    for i in range(16, min(len(r) - 4, 120)):                        # de 0,8 a 6 s: 150 ms despues contra 300 ms antes
        salto = sum(r[i:i + 3]) / 3.0 - sum(r[i - 6:i]) / 6.0
        if salto > mejor:
            mejor, imp = salto, i * 0.05
        if 1.3 <= i * 0.05 <= 2.1 and salto > cerca:                 # el que ya cae donde terminan las fotos (1,67 s)
            cerca, imp_c = salto, i * 0.05
    # (medido: 3 de las 4 intros traen un impacto a 1,7 s y otro mayor a 3,35 s) si hay uno fuerte donde acaban las
    # fotos, ese: la intro empieza en su principio y suena hasta que entra la cancion siguiente (con el de 3,35 s
    # quedaba 1 s casi en silencio antes de la romantica)
    if cerca >= 0.6 * mejor:
        imp = imp_c
    # (17-nov, medido en el de 15 min: 2,5 s casi en silencio donde una fiesta acababa y entraba la otra) para
    # ENCADENAR no vale el -40 dB: la cola del acorde final y la subida inicial son muy bajas. Entrada fuerte: -32 dB;
    # final fuerte: -27 dB (ahi se apaga la que sale y entra la siguiente).
    fuerte_e = next((i for i, v in enumerate(e) if v > 677000.0), suena[0])          # -32 dB
    fuerte_f = next((i for i in range(len(e) - 1, -1, -1) if e[i] > 2142000.0), suena[-1])   # -27 dB
    return (max(0.0, suena[0] * 0.05 - 0.03), min(len(m) / 8000.0, (suena[-1] + 1) * 0.05), imp,
            max(0.0, fuerte_e * 0.05 - 0.03), min(len(m) / 8000.0, (fuerte_f + 1) * 0.05 + 0.4))


def medidas(ruta):
    """Las de _medir, guardadas por nombre y tamaño (datos/analisis/musica_propia.json)."""
    global _medidas
    cache = os.path.join(rutas.ANALISIS, "musica_propia.json")
    if _medidas is None:
        try:
            with open(cache, encoding="utf-8") as f:
                _medidas = json.load(f)
        except Exception:
            _medidas = {}
    k = "v3|%s|%d|%d" % (os.path.basename(os.path.dirname(ruta)) + "/" + os.path.basename(ruta), os.path.getsize(ruta),
                         int(os.path.getmtime(ruta)))
    if k not in _medidas:
        try:
            _medidas[k] = list(_medir(ruta))
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(_medidas, f)
        except Exception:
            return [0.0, 0.0, 0.0, 0.0, 0.0]
    return _medidas[k]


def catalogo(tipo=None):
    """{papel: [rutas]} de las pistas del estilo elegido (por una palabra del nombre del archivo)."""
    estilo = estilo_elegido(tipo) if os.environ.get("TRAILER_MUSICA", "").lower() != "plantilla" else ""
    cat = {}
    if not estilo:
        return cat
    d = os.path.join(CARPETA, estilo)
    for f in sorted(os.listdir(d)):
        if f.startswith(".") or os.path.splitext(f)[1].lower() not in EXT:
            continue
        for papel, palabra in (("apertura", "INTRO"), ("epica", "EPICA"), ("romantica", "ROMANTICA"),
                               ("fiesta", "FIESTA")):
            if palabra in f.upper():
                cat.setdefault(papel, []).append(os.path.join(d, f))
                break
    return cat


def papel_de(nombre_clip, nombre_pista):
    n = (nombre_clip or "").upper()
    if "INTRO" in (nombre_pista or "").upper():
        return "apertura"
    for papel, palabras in PALABRAS:
        if any(p in n for p in palabras):
            return papel
    return "romantica"


def _llenar(papel, lista, dur, fps, turno):
    """Los trozos [{ini (cuadros desde el inicio del tramo), dur, ruta, desde_s, natural}] que llenan un tramo de `dur`
    cuadros con las pistas de ese papel."""
    falta_s = dur / float(fps)
    util = {}
    for r in lista:
        ent, fin, imp, ent_f, fin_f = medidas(r)
        if papel == "apertura":                  # la intro suena entera, con su cola
            desde = max(ent, imp - FOTOS_S) if imp > FOTOS_S else ent
        else:                                    # las demas se encadenan por lo fuerte: sin colas ni subidas en silencio
            desde, fin = ent_f, (fin_f or fin)
        util[r] = (desde, max(0.0, fin - desde))
    if papel == "apertura":                                 # una sola; si termina un poco antes, suena hasta su final
        r = max(lista, key=lambda r: util[r][1])
        if util[r][1] < falta_s - 4.0:
            return []
        return [{"ini": 0, "dur": min(dur, int(util[r][1] * fps)), "ruta": r, "desde_s": util[r][0],
                 "natural": util[r][1] < falta_s}]
    buenas = [r for r in lista if util[r][1] >= COLA_MIN_S * 2]
    if not buenas:
        return []
    out, pos = [], 0
    while pos < dur:
        falta_s = (dur - pos) / float(fps)
        cubren = [r for r in buenas if util[r][1] >= falta_s + 0.3]
        # la menos usada hasta ahora (turno = usos por pista): si alguna cubre lo que falta, la mas corta de esas;
        # si no, la mas larga, que suena hasta su final natural y deja entrar a la siguiente
        if cubren:
            r = min(cubren, key=lambda r: (turno.get(r, 0), util[r][1]))
        else:
            r = min(buenas, key=lambda r: (turno.get(r, 0) + (1 if out and out[-1]["ruta"] == r else 0), -util[r][1]))
        turno[r] = turno.get(r, 0) + 1
        trozo = min(int(util[r][1] * fps), dur - pos)
        resto = dur - pos - trozo
        natural = trozo < dur - pos
        if 0 < resto < int(COLA_MIN_S * fps):               # la que sigue sonaria muy poco: esta se corta antes
            trozo -= int(COLA_MIN_S * fps) - resto
            natural = False
        out.append({"ini": pos, "dur": trozo, "ruta": r, "desde_s": util[r][0], "natural": natural})
        pos += trozo
    return out


def plan(tl, fps, tipo=None):
    """Que cancion de la linea se cambia por cuales: [{pista, ini (cuadros desde el inicio), dur, papel, intro, nombre,
    trozos}]. Los trozos seguidos de una misma cancion (la intro viene partida) cuentan como un solo tramo."""
    cat = catalogo(tipo)
    if not cat:
        return []
    st, todos, turno = tl.GetStartFrame(), [], {}
    for t in range(1, tl.GetTrackCount("audio") + 1):
        pista = (tl.GetTrackName("audio", t) or "").upper()
        if not pista.startswith("MUSICA") or "BAJA" in pista:
            continue
        grupos = []                                        # trozos pegados del mismo archivo -> un tramo
        for it in sorted(tl.GetItemListInTrack("audio", t) or [], key=lambda x: x.GetStart()):
            nombre = it.GetName() or ""
            if grupos and grupos[-1]["nombre"] == nombre and it.GetStart() - grupos[-1]["fin"] <= 1:
                grupos[-1]["fin"] = it.GetEnd()
            else:
                grupos.append({"nombre": nombre, "ini": it.GetStart(), "fin": it.GetEnd()})
        todos += [dict(g, pista=t, nombre_pista=pista) for g in grupos if g["fin"] - g["ini"] >= MIN_S * fps]
    out = []
    for g in sorted(todos, key=lambda g: g["ini"]):        # en el orden en que suenan: no repite la misma seguida
        dur = g["fin"] - g["ini"]
        papel = papel_de(g["nombre"], g["nombre_pista"])
        trozos = _llenar(papel, cat.get(papel) or [], dur, fps, turno) if cat.get(papel) else []
        if trozos:
            out.append({"pista": g["pista"], "ini": g["ini"] - st, "dur": dur, "papel": papel,
                        "intro": "INTRO" in g["nombre_pista"], "nombre": g["nombre"], "trozos": trozos})
    return out


def tramos_ritmo(tl, fps, tipo, de_plantilla):
    """Los tramos de musica para medir el ritmo (ruta, desde_s, inicio_s, dur_s): los de la plantilla, con las canciones
    que se cambian ya cambiadas. La apertura no cuenta (igual que la intro de la plantilla)."""
    cambios = [p for p in plan(tl, fps, tipo) if not p["intro"]]
    if not cambios:
        return de_plantilla
    out = []
    for ruta, src, ini, dur in de_plantilla:
        c = next((p for p in cambios if abs(p["ini"] / float(fps) - ini) < 0.5), None)
        if c is None:
            out.append((ruta, src, ini, dur))
            continue
        for z in c["trozos"]:
            out.append((z["ruta"], round(z["desde_s"], 3), round((c["ini"] + z["ini"]) / float(fps), 3),
                        round(z["dur"] / float(fps), 3)))
    return out


def aplicar(tl, mp, carpeta_mp, fps, tipo=None, log=print):
    """Cambia las canciones en la linea del evento (activa y asentada). Devuelve cuantas canciones de plantilla cambio."""
    cambios = plan(tl, fps, tipo)
    if not cambios:
        return 0
    st, hechos, items = tl.GetStartFrame(), 0, {}
    try:
        hay = {os.path.normcase(c.GetClipProperty("File Path") or ""): c for c in carpeta_mp.GetClipList() or []}
        faltan = [r for r in sorted({z["ruta"] for p in cambios for z in p["trozos"]}) if os.path.normcase(r) not in hay]
        if faltan:
            mp.SetCurrentFolder(carpeta_mp)
            for c in mp.ImportMedia(faltan) or []:
                hay[os.path.normcase(c.GetClipProperty("File Path") or "")] = c
        items = hay
    except Exception as ex:
        log("AVISO: no se pudo traer la musica propia (%s): queda la de la plantilla." % ex)
        return 0
    pistas = 0
    for p in cambios:
        if any(items.get(os.path.normcase(z["ruta"])) is None for z in p["trozos"]):
            continue
        try:
            tl.SetTrackLock("audio", p["pista"], False)
            viejos = [x for x in tl.GetItemListInTrack("audio", p["pista"]) or []
                      if x.GetStart() - st >= p["ini"] and x.GetEnd() - st <= p["ini"] + p["dur"]
                      and (x.GetName() or "") == p["nombre"]]
            if not viejos:
                continue
            fa = (viejos[0].GetFades() or {}).get("FadeIn", 0)
            fo = (viejos[-1].GetFades() or {}).get("FadeOut", 0)
            vol = viejos[0].GetProperty("AudioVolume")
            if not tl.DeleteClips(viejos, False):
                continue
            n = len(p["trozos"])
            for j, z in enumerate(p["trozos"]):
                mpi = items[os.path.normcase(z["ruta"])]
                k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
                s0 = int(round(z["desde_s"] * fps * k))
                nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0,
                                              "endFrame": s0 + int(round(z["dur"] * k)), "mediaType": 2,
                                              "trackIndex": p["pista"], "recordFrame": st + p["ini"] + z["ini"]}]) or []
                if not nuevo:
                    log("AVISO: no se pudo poner %s en la linea." % os.path.basename(z["ruta"]))
                    continue
                y = nuevo[0]
                if vol is not None:
                    y.SetProperty("AudioVolume", float(vol))
                # la intro y las pistas seguidas entran en su primer golpe; la que se corta antes de su final, se apaga
                # (medido en los 4 estilos: con el fundido de 1 s de la plantilla quedaba un hueco de -27 a -35 dB al
                # pasar de la intro a la romantica) la pista propia empieza en su primer golpe: entra casi de golpe
                entra = 0 if p["intro"] or j else min(int(fa), 6)
                if j and not p["trozos"][j - 1]["natural"]:
                    entra = int(fps * 0.5)
                sale = int(max(fo, fps)) if j == n - 1 else (int(fps * 0.4) if z["natural"] else int(fps * 1.5))
                y.SetFades({"FadeIn": entra, "FadeOut": sale})
                pistas += 1
            hechos += 1
        except Exception as ex:
            log("AVISO: musica propia, %s: %s" % (p["papel"], ex))
    if hechos:
        log("Música propia (%s): %d canciones de la plantilla cambiadas por %d pistas originales (%s)." % (
            estilo_elegido(tipo), hechos, pistas, ", ".join(sorted({p["papel"] for p in cambios}))))
    return hechos
