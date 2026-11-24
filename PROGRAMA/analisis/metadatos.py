# -*- coding: utf-8 -*-
"""
metadatos.py - Los METADATOS VISIBLES de cada video analizado, DENTRO del archivo original (MP4 / MOV).

(18-nov, la persona: «no hay metadatos en los videos y deberían estar») El analisis ya viajaba con cada archivo en un
flujo oculto de NTFS («video.mp4:trailer», analizar_material._incrustar), pero eso no se ve en Windows ni en ningun
programa. Aqui se escribe lo que se entiende de la toma como etiquetas normales del contenedor (iTunes / QuickTime
«udta/meta/ilst»): titulo (que pasa), comentario (momento · escena · belleza · si sirve) y palabras clave. Se ven en
Propiedades > Detalles del Explorador, en DaVinci, VLC, MediaInfo o ffprobe.

COMO, para no arriesgar el original:
  - Solo se toca la CABECERA («moov»), que en los videos de camara, celular y dron va DESPUES de la imagen («mdat»):
    la imagen y el sonido no se mueven ni se reescriben (ni un byte), y los indices siguen valiendo.
  - Antes de escribir se guarda la cola original del archivo (desde «moov») en «.trailer/original/» de su carpeta:
    restaurar(ruta) lo deja exactamente como estaba.
  - Si la cabecera va ANTES de la imagen (videos exportados, «faststart») no se toca: devolveria False.
  - La fecha del archivo (la hora de la camara) se conserva.
El archivo crece unos cientos de bytes: quien lo llama (analizar_material) cambia su clave nombre|tamaño.

    python PROGRAMA/analisis/metadatos.py leer <video>
    python PROGRAMA/analisis/metadatos.py restaurar <video>
"""
import os
import struct
import sys

MARCA = "Tráiler automático"
RESPALDO = os.path.join(".trailer", "original")
CLAVES = {"titulo": b"\xa9nam", "comentario": b"\xa9cmt", "descripcion": b"desc", "etiquetas": b"keyw"}
EXT = (".mp4", ".mov", ".m4v")


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def _t(seg):
    return "%d:%02d" % (int(seg) // 60, int(seg) % 60)


def _estrellas(item, sirve, ref=None):
    """(24-nov) De 1 a 5 estrellas, para ordenar y buscar en el Explorador de Windows. Con la «belleza» de la IA (1-10):
    la mitad, hacia arriba. Sin ella (las fotos de un evento grande no pasan por la IA): 3, +1 si sale la persona
    festejada, +1 / -1 por su nitidez contra la tipica del evento, -1 si tiene luces quemadas; ojos cerrados, a lo
    sumo 2. Lo que no sirve: 1."""
    if not sirve:
        return 1
    b = (item.get("ia") or {}).get("belleza")
    if isinstance(b, (int, float)) and b > 0:
        return max(1, min(5, int((min(10, b) + 1) // 2)))
    e = 3
    if item.get("prota"):
        e += 1
    nit, tipica = item.get("nitidez"), (ref or {}).get("nitidez")
    if isinstance(nit, (int, float)) and tipica:
        e += 1 if nit >= 1.3 * tipica else -1 if nit < 0.55 * tipica else 0
    if isinstance(item.get("quemado"), (int, float)) and item["quemado"] >= 0.10:
        e -= 1
    if (item.get("mirada") or {}).get("ojos_cerrados"):
        e = min(e, 2)
    return max(1, min(5, e))


def _imagen(item, ref=None):
    """(texto, etiquetas) de como se ve: exposicion, luces quemadas, contraste, color, enfoque y estabilidad.
    Los limites salen de lo medido en eventos reales (XV 8-nov: luz mediana 0,41; nitidez 26; temblor 0,85).
    ref: {"nit": la nitidez tipica de SU camara} (24-nov, boda de JUTIAPA: la GoPro gran angular mide 14,6 y sus tomas
    buenas salian como «enfoque suave o desenfocado»: el enfoque se nombra contra lo suyo, como en el armado)."""
    partes, et = [], []
    color = item.get("color") or []
    if color and not isinstance(color[0], (list, tuple)):          # en una foto es una sola medida, no una serie
        color = [color]
    color = [c for c in color if isinstance(c, (list, tuple)) and len(c) >= 7]
    vista = {k: (v if isinstance(v, list) else [v]) for k, v in (item.get("vista") or {}).items()
             if isinstance(v, (list, int, float))}
    if isinstance(item.get("temblor"), (int, float)):
        item = dict(item, temblor=[item["temblor"]])
    if isinstance(item.get("quemado"), (int, float)) and "quem" not in vista:      # fotos: una sola medida
        vista["quem"] = [item["quemado"]]
    luz = _med([c[0] for c in color if c])
    if luz is not None:
        nombre = ("muy oscura (subexpuesta)" if luz < 0.20 else "algo oscura" if luz < 0.30 else
                  "correcta" if luz <= 0.58 else "clara" if luz <= 0.68 else "muy clara (sobreexpuesta)")
        negro = _med([c[1] for c in color if c]) or 0.0
        quem = _med(vista.get("quem") or []) or 0.0
        partes.append("exposición %s (luz media %d %%, negros %d %%, luces quemadas %d %%)"
                      % (nombre, round(luz * 100), round(negro * 100), round(quem * 100)))
        et.append("exposición " + nombre.split(" (")[0])
        if quem >= 0.10:
            et.append("luces quemadas")
        sat = _med([c[2] for c in color if c]) or 0.0
        gr = [(c[3], c[5]) for c in color if c and c[6] > 0.02]
        calido = _med([r - b for r, b in gr]) if gr else None
        tono = "" if calido is None else (", tono cálido" if calido > 0.03 else ", tono frío" if calido < -0.03 else ", tono neutro")
        partes.append("color: saturación %d %%%s" % (round(sat * 100), tono))
    con = _med(vista.get("con") or [])
    if con is not None:
        partes.append("contraste %s" % ("bajo" if con < 0.19 else "alto" if con > 0.31 else "medio"))
    nit = _med(vista.get("nit") or [])
    if nit is not None:
        tipica = (ref or {}).get("nit")
        if tipica:
            nombre = "nítido" if nit >= 1.3 * tipica else "normal" if nit >= 0.6 * tipica else "suave o desenfocado"
        else:
            nombre = "nítido" if nit >= 35 else "normal" if nit >= 15 else "suave o desenfocado"
        partes.append("enfoque %s (nitidez %d)" % (nombre, round(nit)))
        et.append("enfoque " + nombre)
    tem = _med(item.get("temblor") or [])
    if tem is not None:
        nombre = "muy estable (trípode)" if tem < 0.45 else "estable" if tem < 1.2 else "algo movida" if tem < 2.5 else "muy movida"
        partes.append("cámara %s (temblor %.1f)" % (nombre, tem))
        et.append("cámara " + nombre.split(" (")[0])
    if nit is None and isinstance(item.get("nitidez"), (int, float)):               # la escala de las fotos es otra
        partes.append("nitidez de la foto %s" % (("%.0f" % item["nitidez"]) if item["nitidez"] >= 10 else ("%.2f" % item["nitidez"])))
    oscuros = item.get("oscuros") or []
    if oscuros:
        partes.append("%d tramos en negro" % len(oscuros))
    return "; ".join(partes), et


def _sonido(item, voz):
    """(texto, etiquetas) de lo que se oye: nivel, aplausos / vitores / risas del oido (con su minuto), musica del lugar
    y si hay VOZ UTIL (pasajes de alguien hablando de corrido, de escenas_ia: pastor, brindis, discursos)."""
    if item.get("audio_pista") is False:
        return "sin pista de sonido", ["sin sonido"]
    partes, et = [], []
    nivel = _med(item.get("audio") or [])
    if nivel is not None:
        pico = max(item.get("audio") or [nivel])
        partes.append("nivel %s (%d dB, picos %d dB)" % ("bajo" if nivel < -38 else "fuerte" if nivel > -24 else "medio",
                                                         round(nivel), round(pico)))
    oido = item.get("oido") or {}
    paso = float(oido.get("paso") or 4.0)
    emocion = []
    for g, nombre, minimo in (("aplausos", "aplausos", 0.45), ("vitores", "gritos y vítores", 0.4), ("risas", "risas", 0.35),
                              ("llanto", "llanto", 0.35), ("campanas", "campanas", 0.4)):
        serie = oido.get(g) or []
        if serie and max(serie) >= minimo:
            emocion.append("%s en %s" % (nombre, _t(serie.index(max(serie)) * paso)))
            et.append(nombre)
    if emocion:
        partes.append("sonido útil: " + ", ".join(emocion))
    elif oido:
        partes.append("sin aplausos, gritos ni risas claros")
    if (oido.get("musica") or [0])and max(oido.get("musica") or [0]) >= 0.6:
        partes.append("suena música del lugar")
        et.append("música del lugar")
    pasajes = (voz or {}).get("pasajes") or []
    if pasajes:
        total = sum(float(p.get("fin", 0)) - float(p.get("ini", 0)) for p in pasajes)
        p0 = max(pasajes, key=lambda p: float(p.get("fin", 0)) - float(p.get("ini", 0)))
        texto = " ".join(str(p0.get("texto") or "").split())[:110]
        tipo = str(p0.get("tipo") or "").strip().lower()
        partes.append("VOZ ÚTIL: %d pasaje%s, %d s en total%s; el más largo en %s–%s: «%s%s»" % (
            len(pasajes), "" if len(pasajes) == 1 else "s", round(total), " (%s)" % tipo if tipo else "",
            _t(float(p0.get("ini", 0))), _t(float(p0.get("fin", 0))), texto, "…" if len(texto) >= 110 else ""))
        et.append("voz útil")
    elif (oido.get("habla") or [0]) and max(oido.get("habla") or [0]) >= 0.7:
        partes.append("se oye hablar, pero sin un pasaje de voz útil")
    else:
        partes.append("sin voz útil")
    return "; ".join(partes), et


def campos_de(item, voz=None, caras=None, receta=None, ref=None):
    """Lo que se escribe de una toma analizada (item del analisis): titulo, comentario, descripcion y etiquetas.
    voz: lo que DaVinci entendio al escucharla (escenas_ia: «pasajes»); caras: las personas reconocidas (personas.json).
    (18-nov, la persona: «mejora más los metadatos: nivel de exposición, si hay sonido o voz útil, más metadatos
    útiles aunque crezca el triple») El comentario va por partes: CONTENIDO | IMAGEN | SONIDO | PERSONAS | TÉCNICO."""
    ia = item.get("ia") or {}
    momento = str(item.get("momento") or "").strip()
    escena = str(ia.get("escena") or "").strip()
    etiquetas = [str(e) for e in ia.get("etiquetas") or []]
    inst = [x for x in ia.get("instantes") or [] if len(x) > 2]
    clave = {}
    for x in inst:
        for e in x[1] or []:
            clave.setdefault(str(e), []).append(x[0])
    cont = [p for p in (momento, escena) if p]
    if etiquetas:
        cont.append("se ve: " + ", ".join(etiquetas))
    if clave:
        cont.append("momentos: " + ", ".join("%s (%s)" % (k, ", ".join(_t(t) for t in ts[:3]) + ("…" if len(ts) > 3 else ""))
                                             for k, ts in sorted(clave.items())))
    if ia.get("belleza"):
        cont.append("belleza %s de 10" % ia["belleza"])
    malos = [x for x in inst if x[2] is False]
    if inst and malos:
        motivos = {}
        for x in malos:
            motivos[x[3] if len(x) > 3 else "?"] = motivos.get(x[3] if len(x) > 3 else "?", 0) + 1
        try:
            import vision_ia
            nombres = vision_ia.MOTIVOS
        except Exception:
            nombres = {}
        m = max(motivos, key=motivos.get)
        cont.append("%d %% de la toma no sirve (%s)" % (round(100.0 * len(malos) / len(inst)), nombres.get(m, m)))
    sirve = not (ia.get("util") is False or item.get("descartar"))
    por = str(item.get("por_descarte") or "").replace("ia: ", "")    # (1.9.3) por que quedo fuera, si se sabe
    cont.append("SIRVE" if sirve else ("NO SIRVE (%s)" % por if por else "NO SIRVE"))
    imagen, et_i = _imagen(item, ref)
    sonido, et_s = ("", []) if item.get("tipo") == "foto" else _sonido(item, voz)
    caras = caras if caras is not None else item.get("caras")
    personas = []
    if caras is not None:
        personas.append("%d persona%s reconocida%s" % (len(caras), "" if len(caras) == 1 else "s", "" if len(caras) == 1 else "s")
                        if caras else "nadie reconocido de frente")
    if item.get("prota"):
        personas.append("sale la persona festejada")
    tec = []
    if item.get("ancho") and item.get("alto"):
        tec.append("%dx%d %s" % (item["ancho"], item["alto"], "horizontal" if item.get("horizontal", True) else "vertical"))
    if item.get("fps"):
        tec.append(("%.2f" % float(item["fps"])).rstrip("0").rstrip(".") + " c/s")
    if item.get("dur"):
        tec.append("dura " + _t(float(item["dur"])))
    if item.get("camara"):
        tec.append("cámara " + str(item["camara"]))
    if item.get("hora"):
        tec.append("grabado " + str(item["hora"]).replace("T", " ")[:16] +
                   (" (reloj corregido)" if item.get("reloj") == "corregido" else ""))
    if item.get("nombre_original") and item.get("nombre_original") != item.get("nombre"):
        tec.append("nombre original " + str(item["nombre_original"]))
    # (18-nov, la persona: «sugerir: estas tomas podrían ir en las plantillas tal en el minuto tal, corrección de color
    # tal y reducción de ruido») la receta del armado (armado/receta.py): donde entra y con que ajuste
    receta = receta or {}
    ajustes = [x for x in (("color " + receta["color"]) if receta.get("color") else "",
                           ("reducción de ruido " + receta["ruido"]) if receta.get("ruido") else "") if x]
    grupos = [("ANALIZADO", "sí (no hace falta volver a analizarlo)"), ("CONTENIDO", " · ".join(cont)),
              ("PLANTILLAS", receta.get("usos") or ""), ("AJUSTES SUGERIDOS", "; ".join(ajustes)), ("IMAGEN", imagen),
              ("SONIDO", sonido), ("PERSONAS", "; ".join(personas)), ("TÉCNICO", ", ".join(tec))]
    comentario = " | ".join("%s: %s" % (n, t) for n, t in grupos if t) + " | " + MARCA
    todas = ([momento] if momento else []) + etiquetas + sorted(clave) + et_i + et_s + \
        (["festejada"] if item.get("prota") else []) + (["sirve"] if sirve else ["no sirve"])
    titulo = escena
    if not titulo:
        # (1.9.3) sin lo que ve la IA (con mas de 200 fotos no las mira: MAX_FOTOS_IA) el titulo decia solo
        # «MAQUILLAJE»: ahora el momento, que es y a quien se ve, con lo que el analisis si sabe
        que = {"foto": "foto", "dron": "toma aérea"}.get(item.get("tipo"), "toma")
        if item.get("prota"):
            que += " de la festejada"
        elif caras:
            que += " con %d persona%s" % (len(caras), "" if len(caras) == 1 else "s")
        titulo = "%s · %s" % (momento.capitalize(), que) if momento else que.capitalize()
    return {"titulo": titulo, "comentario": comentario, "descripcion": momento,
            "etiquetas": "; ".join(dict.fromkeys(todas)), "estrellas": str(_estrellas(item, sirve, ref))}


def _atomos(b, ini, fin):
    """[(tipo, inicio, tamaño, cabecera)] de los atomos de b[ini:fin]."""
    out, pos = [], ini
    while pos + 8 <= fin:
        n, t = struct.unpack(">I4s", b[pos:pos + 8])
        cab = 8
        if n == 1:
            n, cab = struct.unpack(">Q", b[pos + 8:pos + 16])[0], 16
        elif n == 0:
            n = fin - pos
        if n < cab or pos + n > fin:
            raise ValueError("atomo roto en %d" % pos)
        out.append((t, pos, n, cab))
        pos += n
    return out


def _atomo(tipo, cuerpo):
    return struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo


def _dato(clave, texto):
    return _atomo(clave, _atomo(b"data", struct.pack(">II", 1, 0) + texto.encode("utf-8")))


def _arriba(ruta):
    """Los atomos de primer nivel: [(tipo, inicio, tamaño)], sin leer el archivo entero."""
    out, pos, fin = [], 0, os.path.getsize(ruta)
    with open(ruta, "rb") as f:
        while pos + 8 <= fin:
            f.seek(pos)
            h = f.read(16)
            n, t = struct.unpack(">I4s", h[:8])
            if n == 1:
                n = struct.unpack(">Q", h[8:16])[0]
            elif n == 0:
                n = fin - pos
            if n < 8 or pos + n > fin:
                raise ValueError("archivo con estructura rara")
            out.append((t, pos, n))
            pos += n
    return out


# ------------------------------------------------------------------ (24-nov) lo que el Explorador de Windows SI muestra
# La persona (24-nov): «mejora los metadatos a los archivos originales». Windows no lee «keyw» como Etiquetas ni sabe
# de «belleza 7 de 10»: en un MP4/MOV las Etiquetas y la Clasificacion (estrellas) de Propiedades > Detalles —y de las
# columnas, el orden y la busqueda del Explorador— salen del atomo «Xtra» de udta (WM/Category y WM/SharedUserRating).
# Cada entrada: largo(4) · largo del nombre(4) · nombre · cuantos valores(4) · [largo(4) · tipo(2) · dato]; tipo 8 =
# texto UTF-16LE acabado en cero, tipo 19 = entero de 64 bits. Lo nuestro se marca en una entrada propia (XTRA_MARCA):
# si la persona pone SUS estrellas o SUS etiquetas en el Explorador, no se le pisan.
XTRA_MARCA = "TrailerAutomatico"
XTRA_ESTRELLAS, XTRA_ETIQUETAS = "WM/SharedUserRating", "WM/Category"
PORCIENTO = {1: 1, 2: 25, 3: 50, 4: 75, 5: 99}          # como guarda Windows de 1 a 5 estrellas


def _xtra_entrada(nombre, valores):
    n = nombre.encode("ascii")
    cuerpo = struct.pack(">I", len(n)) + n + struct.pack(">I", len(valores))
    for tipo, dato in valores:
        cuerpo += struct.pack(">IH", 6 + len(dato), tipo) + dato
    return struct.pack(">I", 4 + len(cuerpo)) + cuerpo


def _xtra_texto(t):
    return (8, str(t).encode("utf-16-le") + b"\x00\x00")


def _xtra_leer(cuerpo):
    """{nombre: (entrada tal cual, [(tipo, dato)])} de un atomo Xtra, en su orden. ValueError si no se entiende."""
    out, pos = {}, 0
    while pos + 12 <= len(cuerpo):
        n, ln = struct.unpack(">II", cuerpo[pos:pos + 8])
        if n < 12 + ln or pos + n > len(cuerpo):
            raise ValueError("Xtra con estructura rara")
        nombre = cuerpo[pos + 8:pos + 8 + ln].decode("ascii", "replace")
        q = pos + 8 + ln
        cuantos = struct.unpack(">I", cuerpo[q:q + 4])[0]
        q += 4
        vals = []
        for _ in range(cuantos):
            lv, tipo = struct.unpack(">IH", cuerpo[q:q + 6])
            if lv < 6 or q + lv > pos + n:
                raise ValueError("Xtra con estructura rara")
            vals.append((tipo, cuerpo[q + 6:q + lv]))
            q += lv
        out[nombre] = (cuerpo[pos:pos + n], vals)
        pos += n
    if pos != len(cuerpo):
        raise ValueError("Xtra con estructura rara")
    return out


def _xtra_nuestro(entradas):
    """(estrellas que pusimos o None, True si las etiquetas son nuestras, estrellas de OTRO o None)."""
    marca = entradas.get(XTRA_MARCA)
    texto = marca[1][0][1].decode("utf-16-le", "replace").rstrip("\x00") if marca and marca[1] else ""
    a = dict(x.split("=", 1) for x in texto.split(";") if "=" in x)
    puse = int(a["estrellas"]) if a.get("estrellas", "").isdigit() else None
    hay = entradas.get(XTRA_ESTRELLAS)
    pct = struct.unpack("<Q", hay[1][0][1][:8])[0] if hay and hay[1] and len(hay[1][0][1]) >= 8 else None
    mias = puse is not None and pct == PORCIENTO.get(puse)
    return (puse if mias else None), a.get("etiquetas") == "1", (None if (pct is None or mias) else pct)


def _xtra_nuevo(viejo, campos):
    """El cuerpo del atomo Xtra con nuestras estrellas y etiquetas; lo de otros (y lo que puso la persona) se conserva.
    None = no se entiende el que hay: no se toca."""
    try:
        entradas = _xtra_leer(viejo) if viejo else {}
    except (ValueError, struct.error):
        return None
    puse, etq_mias, ajenas = _xtra_nuestro(entradas)
    est = int(campos["estrellas"]) if str(campos.get("estrellas") or "").isdigit() else None
    etq = [e.strip() for e in str(campos.get("etiquetas") or "").split(";") if e.strip()]
    nuevas = {k: v[0] for k, v in entradas.items() if k != XTRA_MARCA}
    marca = []
    if est in PORCIENTO and ajenas is None:                      # (sin estrellas de la persona)
        nuevas[XTRA_ESTRELLAS] = _xtra_entrada(XTRA_ESTRELLAS, [(19, struct.pack("<Q", PORCIENTO[est]))])
        marca.append("estrellas=%d" % est)
    elif puse is not None and ajenas is None:
        marca.append("estrellas=%d" % puse)
    if etq and (XTRA_ETIQUETAS not in entradas or etq_mias):     # (sin etiquetas de la persona)
        nuevas[XTRA_ETIQUETAS] = _xtra_entrada(XTRA_ETIQUETAS, [_xtra_texto(e) for e in etq])
        marca.append("etiquetas=1")
    elif etq_mias:
        marca.append("etiquetas=1")
    if marca:
        nuevas[XTRA_MARCA] = _xtra_entrada(XTRA_MARCA, [_xtra_texto(";".join(marca))])
    return b"".join(nuevas.values())


def _moov_nuevo(moov, campos):
    """La cabecera con nuestras etiquetas en udta/meta/ilst (lo que ya hubiera ahi de otros se conserva) y, para el
    Explorador de Windows, las Etiquetas y las estrellas en udta/Xtra."""
    nuestras = {CLAVES[k]: v for k, v in campos.items() if k in CLAVES and v}
    hijos = _atomos(moov, 8, len(moov))
    udta = next((h for h in hijos if h[0] == b"udta"), None)
    otros_udta, items_viejos, hdlr, xtra = b"", b"", None, None
    if udta is not None:
        for t, p, n, cab in _atomos(moov, udta[1] + udta[3], udta[1] + udta[2]):
            if t == b"Xtra" and xtra is None:
                xtra = moov[p + cab:p + n]
                continue
            if t != b"meta":
                otros_udta += moov[p:p + n]
                continue
            try:
                for t2, p2, n2, cab2 in _atomos(moov, p + cab + 4, p + n):
                    if t2 == b"hdlr":
                        hdlr = moov[p2:p2 + n2]
                    elif t2 == b"ilst":
                        for t3, p3, n3, _ in _atomos(moov, p2 + cab2, p2 + n2):
                            if t3 not in CLAVES.values():
                                items_viejos += moov[p3:p3 + n3]
            except ValueError:
                otros_udta += moov[p:p + n]          # un «meta» que no es de etiquetas: se deja tal cual
    hdlr = hdlr or _atomo(b"hdlr", struct.pack(">II4s4sIIH", 0, 0, b"mdir", b"appl", 0, 0, 0)[:25])
    ilst = _atomo(b"ilst", items_viejos + b"".join(_dato(k, v) for k, v in nuestras.items()))
    cuerpo_xtra = _xtra_nuevo(xtra or b"", campos)
    if cuerpo_xtra is None:                                    # un Xtra que no se entiende: queda como estaba
        cuerpo_xtra = xtra or b""
    udta_n = _atomo(b"udta", otros_udta + _atomo(b"meta", struct.pack(">I", 0) + hdlr + ilst)
                    + (_atomo(b"Xtra", cuerpo_xtra) if cuerpo_xtra else b""))
    cuerpo = b"".join(udta_n if h is udta else moov[h[1]:h[1] + h[2]] for h in hijos)
    if udta is None:
        cuerpo += udta_n
    return _atomo(b"moov", cuerpo)


def _carpeta_respaldo(ruta):
    return os.path.join(os.path.dirname(ruta), RESPALDO)


# ------------------------------------------------------------------ fotos JPG
# (18-nov, la persona: «y también en las fotos») En un JPG las etiquetas van en un paquete XMP (segmento APP1 propio),
# sin tocar la imagen (no se recomprime: los bytes de la foto quedan iguales) ni el EXIF de la camara. Si la foto ya
# trae XMP (las de DxO traen 17 KB) se le AGREGA un bloque nuestro, marcado, y lo demas queda como estaba.
EXT_FOTO = (".jpg", ".jpeg")
XMP_ID = b"http://ns.adobe.com/xap/1.0/\x00"
# nuestro bloque se reconoce por un atributo propio (con comentarios XML <!-- --> Windows dejaba de leer TODO el paquete,
# hasta las etiquetas que la foto ya traia)
ESPACIO = 'xmlns:trailer="https://cinemaproductions.gt/trailer/1.0/" trailer:v="1"'
BLOQUE_RE = r'<rdf:Description[^>]*trailer:v="1"[^>]*>.*?</rdf:Description>'


def _xml(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _jpg_cabecera(b):
    """([(marcador, inicio, largo)] de los segmentos antes de la imagen, posicion donde empieza la imagen)."""
    if b[:2] != b"\xff\xd8":
        raise ValueError("no es JPEG")
    pos, out = 2, []
    while pos + 4 <= len(b):
        if b[pos] != 0xFF:
            raise ValueError("JPEG con estructura rara")
        m = b[pos + 1]
        if m == 0xDA:
            return out, pos
        if m == 0x01 or 0xD0 <= m <= 0xD8:
            pos += 2
            continue
        n = struct.unpack(">H", b[pos + 2:pos + 4])[0]
        out.append((m, pos, n + 2))
        pos += n + 2
    raise ValueError("JPEG sin imagen")


RATING_RE = r'xmp:Rating(="|>)\s*(-?\d)'             # las estrellas de la foto: como atributo o como elemento


def _bloque_xmp(campos, con_palabras, estrellas=None, propias=True):
    """estrellas (1-5): las que ponemos (quedan anotadas en trailer:estrellas); propias = van en ESTE bloque (si la foto
    ya traia «xmp:Rating» en otro bloque, se cambia alli: _escribir_jpg)."""
    alt = '<rdf:Alt><rdf:li xml:lang="x-default">%s</rdf:li></rdf:Alt>'
    x = ['<rdf:Description rdf:about="" ' + ESPACIO + (' trailer:estrellas="%d"' % estrellas if estrellas else "")
         + ' xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:exif="http://ns.adobe.com/exif/1.0/" '
         'xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
         'xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/">']
    if estrellas:                                    # (24-nov) las estrellas de Propiedades > Detalles y del Explorador
        if propias:
            x.append("<xmp:Rating>%d</xmp:Rating>" % estrellas)
        x.append("<MicrosoftPhoto:Rating>%d</MicrosoftPhoto:Rating>" % PORCIENTO[estrellas])
    if campos.get("titulo"):
        x.append("<dc:title>" + alt % _xml(campos["titulo"]) + "</dc:title>")
        x.append("<photoshop:Headline>%s</photoshop:Headline>" % _xml(campos["titulo"]))
    if campos.get("comentario"):
        x.append("<dc:description>" + alt % _xml(campos["comentario"]) + "</dc:description>")
        x.append("<exif:UserComment>" + alt % _xml(campos["comentario"]) + "</exif:UserComment>")
    if campos.get("etiquetas") and con_palabras:
        x.append("<dc:subject><rdf:Bag>%s</rdf:Bag></dc:subject>" % "".join(
            "<rdf:li>%s</rdf:li>" % _xml(e.strip()) for e in campos["etiquetas"].split(";") if e.strip()))
    x.append("</rdf:Description>")
    return "".join(x)


def _leer_jpg(ruta):
    import re
    out = {}
    try:
        with open(ruta, "rb") as f:
            b = f.read(4 << 20)
        segs, _ = _jpg_cabecera(b)
        for m, p, n in segs:
            if m == 0xE1 and b[p + 4:p + 4 + len(XMP_ID)] == XMP_ID:
                t = b[p + 4 + len(XMP_ID):p + n].decode("utf-8", "replace")
                r0 = re.search(BLOQUE_RE, t, re.S)
                if not r0:
                    return out
                blo = r0.group(0)
                # (24-nov) nuestras estrellas, y si la foto lleva OTRAS (las puso la persona o su programa)
                mias = re.search(r'trailer:estrellas="(\d)"', blo)
                ajena = re.search(RATING_RE, re.sub(BLOQUE_RE, "", t, flags=re.S))
                extra = {}
                if mias and (ajena is None or ajena.group(2) == mias.group(1)):
                    extra["estrellas"] = mias.group(1)
                elif ajena is not None and ajena.group(2) not in ("0", "-"):
                    extra["estrellas_ajenas"] = "1"

                def uno(etq):
                    r = re.search(r"<%s>.*?<rdf:li[^>]*>(.*?)</rdf:li>" % etq, blo, re.S)
                    return r.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") if r else ""
                out = {"titulo": uno("dc:title"), "comentario": uno("dc:description")}
                pal = re.search(r"<dc:subject><rdf:Bag>(.*?)</rdf:Bag>", blo, re.S)
                if pal:
                    out["etiquetas"] = "; ".join(x.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                                                 for x in re.findall(r"<rdf:li>(.*?)</rdf:li>", pal.group(1)))
                return dict({k: v for k, v in out.items() if v}, **extra)
    except (ValueError, OSError):
        pass
    return out


def _escribir_jpg(ruta, campos):
    import re
    with open(ruta, "rb") as f:
        b = f.read()
    segs, sos = _jpg_cabecera(b)
    xmp = next(((p, n) for m, p, n in segs if m == 0xE1 and b[p + 4:p + 4 + len(XMP_ID)] == XMP_ID), None)
    est = int(campos["estrellas"]) if str(campos.get("estrellas") or "") in ("1", "2", "3", "4", "5") else None
    if xmp is not None:
        texto = b[xmp[0] + 4 + len(XMP_ID):xmp[0] + xmp[1]].decode("utf-8")
        viejo = re.search(BLOQUE_RE, texto, re.S)
        mias = re.search(r'trailer:estrellas="(\d)"', viejo.group(0)) if viejo else None
        texto = re.sub(BLOQUE_RE, "", texto, flags=re.S)
        if "</rdf:RDF>" not in texto:
            return None
        # (24-nov) las estrellas: la camara suele dejar «xmp:Rating="0"» (sin estrellas) en SU bloque: se cambia ahi
        # (dos «xmp:Rating» en un paquete no valen). Si lleva de 1 a 5 y no las pusimos nosotros, son de la persona:
        # no se tocan.
        ajena, propias = re.search(RATING_RE, texto), True
        if est and ajena is not None:
            if ajena.group(2) in ("0", "-") or (mias and ajena.group(2) == mias.group(1)):
                texto = texto[:ajena.start(2)] + str(est) + texto[ajena.end(2):]
                propias = False
            else:
                est = None
        bloque = _bloque_xmp(campos, "<dc:subject" not in texto, est, propias)   # las palabras que ya traiga, quedan
        texto = texto.replace("</rdf:RDF>", bloque + "</rdf:RDF>", 1)
        if len(texto.encode("utf-8")) > 65000:                       # sin el relleno en blanco del paquete
            texto = re.sub(r"[ \t\r\n]{3,}", "\n", texto)
        ini, fin = xmp[0], xmp[0] + xmp[1]
    else:
        texto = ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
                 '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">%s</rdf:RDF></x:xmpmeta>'
                 '<?xpacket end="w"?>' % _bloque_xmp(campos, True, est))
        tras = [s for s in segs if s[0] in (0xE0, 0xE1)]               # despues del JFIF y del EXIF
        ini = fin = (tras[-1][1] + tras[-1][2]) if tras else 2
    carga = XMP_ID + texto.encode("utf-8")
    if len(carga) + 2 > 65535:
        return None
    return b[:ini] + b"\xff\xe1" + struct.pack(">H", len(carga) + 2) + carga + b[fin:], b[:sos]


def _reemplazar_entero(ruta, datos, st):
    """Escribe el archivo nuevo al lado y lo cambia de golpe (si se corta la luz, queda el anterior entero)."""
    tmp = ruta + ".escribiendo"
    with open(tmp, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
    if os.name == "nt":                          # la fecha de creacion tambien, como estaba
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.CreateFileW.restype = wintypes.HANDLE
            h = k.CreateFileW(ruta, 0x0100, 7, None, 3, 0x02000000, None)      # FILE_WRITE_ATTRIBUTES, OPEN_EXISTING
            if h and h != wintypes.HANDLE(-1).value:
                t = int(getattr(st, "st_birthtime_ns", st.st_ctime_ns) // 100 + 116444736000000000)
                ft = wintypes.FILETIME(t & 0xFFFFFFFF, t >> 32)
                k.SetFileTime(wintypes.HANDLE(h), ctypes.byref(ft), None, None)
                k.CloseHandle(wintypes.HANDLE(h))
        except Exception:
            pass


def leer(ruta):
    """{"titulo", "comentario", "descripcion", "etiquetas"} que haya en el archivo (los que haya)."""
    if ruta.lower().endswith(EXT_FOTO):
        return _leer_jpg(ruta)
    out = {}
    try:
        arriba = _arriba(ruta)
        t, p, n = next(a for a in arriba if a[0] == b"moov")
        with open(ruta, "rb") as f:
            f.seek(p)
            moov = f.read(n)
        udta = next(h for h in _atomos(moov, 8, len(moov)) if h[0] == b"udta")
        try:                                                   # (24-nov) las estrellas que se ven en Windows
            x = next(h for h in _atomos(moov, udta[1] + udta[3], udta[1] + udta[2]) if h[0] == b"Xtra")
            puse, _, ajenas = _xtra_nuestro(_xtra_leer(moov[x[1] + x[3]:x[1] + x[2]]))
            if puse is not None:
                out["estrellas"] = str(puse)
            if ajenas is not None:
                out["estrellas_ajenas"] = "1"
        except StopIteration:
            pass
        except (ValueError, struct.error):                     # un Xtra que no se entiende no se toca: como si fuera
            out["estrellas_ajenas"] = "1"                      # de la persona (asi no se intenta en cada pasada)
        meta = next(h for h in _atomos(moov, udta[1] + udta[3], udta[1] + udta[2]) if h[0] == b"meta")
        ilst = next(h for h in _atomos(moov, meta[1] + meta[3] + 4, meta[1] + meta[2]) if h[0] == b"ilst")
        al_reves = {v: k for k, v in CLAVES.items()}
        for t3, p3, n3, cab3 in _atomos(moov, ilst[1] + ilst[3], ilst[1] + ilst[2]):
            if t3 in al_reves:
                d = next(h for h in _atomos(moov, p3 + cab3, p3 + n3) if h[0] == b"data")
                out[al_reves[t3]] = moov[d[1] + d[3] + 8:d[1] + d[2]].decode("utf-8", "replace")
    except (StopIteration, ValueError, OSError):
        pass
    return out


def al_dia(ruta, campos, ya=None):
    """True si el archivo YA lleva eso (no hay que escribirlo): titulo, comentario y, salvo que la persona haya puesto
    las suyas, las estrellas; en los videos tambien las etiquetas. Los espacios de mas no cuentan."""
    ya = leer(ruta) if ya is None else ya
    junto = lambda t: " ".join(str(t or "").split())
    claves = ["titulo", "comentario"] + ([] if ruta.lower().endswith(EXT_FOTO) else ["etiquetas"])
    if any(junto(ya.get(k)) != junto(campos.get(k)) for k in claves):
        return False
    return bool(ya.get("estrellas_ajenas")) or junto(ya.get("estrellas")) == junto(campos.get("estrellas"))


def escribir(ruta, campos):
    """Pone las etiquetas en el archivo. campos: {"titulo", "comentario", "descripcion", "etiquetas", "estrellas"}
    (textos; estrellas «1» a «5»). True si quedaron escritas (o ya estaban iguales); False si el archivo no es de los
    que se pueden tocar sin riesgo."""
    if ruta.lower().endswith(EXT_FOTO):
        campos = {k: " ".join(str(v).split()) for k, v in campos.items()
                  if k in ("titulo", "comentario", "etiquetas", "estrellas") and v}
        ya = _leer_jpg(ruta)
        if ya and al_dia(ruta, campos, ya):
            return True
        st = os.stat(ruta)
        r = _escribir_jpg(ruta, campos)
        if r is None:
            return False
        nuevo, cabecera = r
        _jpg_cabecera(nuevo)                                     # que lo nuevo se pueda leer antes de escribir
        d = _carpeta_respaldo(ruta)
        if not any(f.startswith(os.path.basename(ruta) + ".") for f in (os.listdir(d) if os.path.isdir(d) else [])):
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "%s.%d.cabecera" % (os.path.basename(ruta), st.st_size)), "wb") as f:
                f.write(cabecera)
        _reemplazar_entero(ruta, nuevo, st)
        return bool(_leer_jpg(ruta).get("comentario") == campos.get("comentario"))
    if not ruta.lower().endswith(EXT):
        return False
    campos = {k: str(v) for k, v in campos.items() if (k in CLAVES or k == "estrellas") and v}
    ya = leer(ruta)
    if al_dia(ruta, campos, ya) and ya.get("descripcion", "") == campos.get("descripcion", ""):
        return True
    arriba = _arriba(ruta)
    tipos = [a[0] for a in arriba]
    if b"moov" not in tipos or b"mdat" not in tipos:
        return False
    i_moov = tipos.index(b"moov")
    if any(t == b"mdat" for t in tipos[i_moov + 1:]):          # cabecera antes de la imagen: no se toca
        return False
    ini = arriba[i_moov][1]
    st = os.stat(ruta)
    with open(ruta, "rb") as f:
        f.seek(ini)
        cola = f.read()
    moov = cola[:arriba[i_moov][2]]
    nueva = _moov_nuevo(moov, campos) + cola[len(moov):]
    _atomos(nueva, 0, len(nueva))                              # que lo nuevo se pueda leer entero antes de escribir
    resp = os.path.join(_carpeta_respaldo(ruta), "%s.%d.cola" % (os.path.basename(ruta), st.st_size))
    if not any(f.startswith(os.path.basename(ruta) + ".") for f in
               (os.listdir(_carpeta_respaldo(ruta)) if os.path.isdir(_carpeta_respaldo(ruta)) else [])):
        os.makedirs(os.path.dirname(resp), exist_ok=True)       # la primera cola es la ORIGINAL: no se pisa nunca
        with open(resp, "wb") as f:
            f.write(struct.pack(">Q", ini) + cola)
    with open(ruta, "r+b") as f:
        f.seek(ini)
        f.write(nueva)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
    return al_dia(ruta, campos)


def restaurar(ruta):
    """Deja el archivo exactamente como antes de la primera escritura. True si habia que restaurar y se pudo."""
    d = _carpeta_respaldo(ruta)
    if ruta.lower().endswith(EXT_FOTO):
        try:
            resp = next(os.path.join(d, f) for f in os.listdir(d) if f.startswith(os.path.basename(ruta) + ".")
                        and f.endswith(".cabecera"))
        except (OSError, StopIteration):
            return False
        st = os.stat(ruta)
        with open(ruta, "rb") as f:
            b = f.read()
        with open(resp, "rb") as f:
            cabecera = f.read()
        _reemplazar_entero(ruta, cabecera + b[_jpg_cabecera(b)[1]:], st)
        return True
    try:
        resp = next(os.path.join(d, f) for f in os.listdir(d) if f.startswith(os.path.basename(ruta) + ".")
                    and f.endswith(".cola"))
    except (OSError, StopIteration):
        return False
    st = os.stat(ruta)
    with open(resp, "rb") as f:
        b = f.read()
    ini, cola = struct.unpack(">Q", b[:8])[0], b[8:]
    with open(ruta, "r+b") as f:
        f.seek(ini)
        f.write(cola)
        f.truncate()
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
    return True


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "leer":
        print(leer(sys.argv[2]))
    elif len(sys.argv) > 2 and sys.argv[1] == "restaurar":
        print(restaurar(sys.argv[2]))
    else:
        print(__doc__)
