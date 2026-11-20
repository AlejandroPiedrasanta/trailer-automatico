# -*- coding: utf-8 -*-
"""
sfx.py - Efectos de sonido segun lo que se ve, no en posiciones fijas de la plantilla.

En la timeline del evento se quitan los SFX de publico, campanas y chispa de la plantilla (estaban a los
mismos segundos en todas las versiones: campanas a los 17 s aunque la iglesia empiece en el minuto 5,
aplausos con petalos dentro de la misa, publico sobre el maquillaje...) y se vuelven a poner por momento:

  IGLESIA .... campanas que entran 1 s antes del primer plano de la iglesia
               aplausos con petalos en la salida (ultimos segundos de la iglesia)
  FIESTA ..... entrada de la pareja al empezar, chispa fria a media fiesta y vitores repartidos,
               cada uno arrancando en un corte
  CIERRE ..... aplausos hasta el final
Todos con fundido de entrada y salida. El "grito invertido" (subida hacia el titulo y el cierre) se
conserva porque va con los marcadores de la plantilla. Los volumenes los ajusta despues mezcla.py.
"""

PISTAS = {"chispa": "SFX CHISPA", "campanas": "SFX CAMPANAS Y GRITOS", "publico": "SFX PUBLICO",
          "publico2": "SFX PUBLICO 2"}
CONSERVAR = ("GRITO",)                 # SFX de la plantilla que se quedan donde estan
PUBLICO_EN_INTRO = False               # True = deja los vitores de la plantilla sobre las fotos de la intro
FIN_INTRO_S = 15.0                     # s: hasta aqui llega el bloque de intro de la plantilla
VITORES = ["cheer_big", "cheer_short", "applause", "sicilian"]
CADA_VITOR_S = 25.0                    # s de fiesta por cada vitor (maximo MAX_VITORES)
MAX_VITORES = 10
# Los SFX PROPIOS del programa (recursos/sfx, los crea herramientas/hacer_sfx.py) van en su pista. Los de mas de 1 s
# los nivela mezcla.py (objetivo SFX); a los cortos se les pone aqui el volumen.
PISTA_MOMENTOS = "SFX MOMENTOS"
VOL_PASO, VOL_OBTURADOR = -7.0, -12.0
# el SFX de la rampa de cada tipo de intro, por el ritmo de sus fotos (los mismos de build_trailers.INTROS)
RAMPAS = {"XV_RAMPA": (5,) * 8, "XV_RAMPA_ACELERA": (9, 7, 6, 5, 4, 4, 3, 2), "XV_RAMPA_FRENA": (2, 3, 4, 4, 5, 6, 7, 9),
          "XV_RAMPA_LATIDO": (7, 3, 7, 3, 7, 3, 7, 3)}


def _pista(tl, nombre):
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if (tl.GetTrackName("audio", t) or "").strip().upper() == nombre:
            return t
    return None


def _frames(clip, fps):
    tc = (clip.GetClipProperty("Duration") or "").replace(";", ":").split(":")
    try:
        h, m, s, f = (int(x) for x in tc)
        return ((h * 60 + m) * 60 + s) * fps + f
    except Exception:
        return 10 * fps


def _sin_voz(ini, dur, evitar, S):
    """(1.8.0, auditoria) El SFX no tapa la voz original (pastor, brindis): si la voz empieza despues de 2 s del SFX,
    este se acorta hasta ahi; si ya esta hablando, no va. evitar: [(ini_f, fin_f)]. Devuelve la duracion (0 = no va)."""
    for a, b in evitar or ():
        if a < ini + dur and ini < b:
            if a - ini >= 2 * S:
                dur = int(a - ini - 0.3 * S)
            else:
                return 0
    return dur


def sonorizar(tl, mp, buscar, zonas, fps, cortes, log=print, evitar=()):
    """zonas: [(nombre, inicio_f, fin_f)] relativos al inicio de la timeline; cortes: inicios de plano.
    buscar(clave) -> MediaPoolItem. evitar: tramos de voz original [(ini_f, fin_f)]. Devuelve los SFX colocados."""
    st = tl.GetStartFrame()
    S = fps
    total = max(z1 for _, _, z1 in zonas)
    pistas = {k: _pista(tl, v) for k, v in PISTAS.items()}
    # 1) fuera los SFX de posicion fija (menos el grito invertido)
    ocupado = {}
    for k, t in pistas.items():
        if not t:
            continue
        tl.SetTrackLock("audio", t, False)
        quitar = []
        for it in tl.GetItemListInTrack("audio", t) or []:
            nombre = (it.GetName() or "").upper()
            ini = it.GetStart() - st
            if any(c in nombre for c in CONSERVAR) or (PUBLICO_EN_INTRO and ini < FIN_INTRO_S * S):
                ocupado.setdefault(t, []).append((ini, it.GetEnd() - st))
            else:
                quitar.append(it)
        if quitar:
            tl.DeleteClips(quitar, False)
    cache = {}

    def clip(clave):
        if clave not in cache:
            cache[clave] = buscar(clave)
        return cache[clave]

    def al_corte(f, margen=1.5):
        cerca = [c for c in cortes if abs(c - f) <= margen * S]
        return min(cerca, key=lambda c: abs(c - f)) if cerca else int(f)

    puestos = []

    def poner(clave, pista_k, ini, dur, fi, fo, alterna=None):
        c = clip(clave)
        if c is None:
            return False
        ini = max(0, int(ini))
        dur = _sin_voz(ini, int(min(dur, _frames(c, fps), total - ini)), evitar, S)
        if dur < S:
            return False
        for pk in (pista_k, alterna):
            t = pistas.get(pk) if pk else None
            if not t:
                continue
            if any(a < ini + dur and ini < b for a, b in ocupado.get(t, [])):
                continue
            r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": dur - 1, "mediaType": 2,
                                      "trackIndex": t, "recordFrame": st + ini}])
            if not r:
                continue
            it = r[0]
            try:
                it.SetFades({"FadeIn": int(min(fi, dur / 3)), "FadeOut": int(min(fo, dur / 2))})
            except Exception:
                pass
            ocupado.setdefault(t, []).append((ini, ini + dur))
            puestos.append((clave, round(ini / float(S), 1)))
            return True
        return False

    z = {n: (a, b) for n, a, b in zonas}
    marcas = {(m.get("name") or "").strip().upper(): int(f) for f, m in (tl.GetMarkers() or {}).items()}
    cierre = marcas.get("CIERRE", total - 6 * S)
    if "IGLESIA" in z:
        i0, i1 = z["IGLESIA"]
        poner("campanas", "campanas", i0 - 1 * S, min(9 * S, i1 - i0), 0.3 * S, 2.5 * S, "publico2")
        if i1 - i0 >= 15 * S:                                     # salida de la iglesia
            poner("cheer_flowers", "publico2", min(i1, cierre) - 5 * S, 6 * S, 0.5 * S, 1.5 * S, "publico")
    if "FIESTA" in z:
        f0, f1 = z["FIESTA"]
        f1 = min(f1, cierre)
        largo = f1 - f0
        if largo > 4 * S:
            poner("coupleentrance", "publico", f0, min(12 * S, largo * 0.5), 0.2 * S, 2 * S, "publico2")
        if largo >= 12 * S:
            poner("chispa", "chispa", al_corte(f0 + 0.45 * largo), min(7 * S, 0.4 * largo), 0.5 * S, 2 * S)
        n = min(MAX_VITORES, max(1, int(largo / (CADA_VITOR_S * S))))
        for k in range(n):
            t = al_corte(f0 + (k + 1) * largo / (n + 1.0))
            poner(VITORES[k % len(VITORES)], "publico2" if k % 2 == 0 else "publico", t, 6 * S,
                  0.4 * S, 1.5 * S, "publico" if k % 2 == 0 else "publico2")
    poner("applause", "publico", cierre - 2 * S, total - cierre + 2 * S, 0.5 * S, 2.5 * S, "publico2")
    return puestos


# (18-nov, la persona: «le falta más SFX de emoción, alegría») Los SFX iban solo por zonas fijas (campanas, entrada,
# vitores cada 25 s): en el de 1 min, 5. La IA ya marca en cada toma los MOMENTOS CLAVE (beso, anillos, pastel...; en la
# boda 122 cuadros): cuando un plano del video cae en uno, su SFX de emocion entra en ese corte.
EMOCION = {"beso": ("cheer_big", "applause"), "pastel": ("cheer_big", "cheer_short"),
           "primer_baile": ("applause", "cheer_short"), "brindis": ("cheer_short", "applause"),
           "entrada": ("cheer_flowers", "cheer_short"), "anillos": ("XV_BRILLO",), "votos": ("XV_BRILLO",)}
EMOCION_CADA_S = (8.0, 14.0)           # separacion minima entre dos: video corto (<= 200 s) / largo
EMOCION_DUR_S = 4.0
EMOCION_MAX = 12


def emocion(tl, mp, buscar, puestos_plan, fps, propios=None, log=print, evitar=()):
    """puestos_plan: [(pieza del plan, clip de la linea)] (los mismos de ambiente.poner). Pone el SFX de cada momento
    clave que la IA vio EN ESE PLANO (it['ia']['instantes']: [t, [etiquetas], ...]), en el corte, sin pisar otros SFX
    ni la voz original (pasajes de voz de la toma). Devuelve [(sfx, segundo)]."""
    st = tl.GetStartFrame()
    S = fps
    total_s = (tl.GetEndFrame() - st) / float(S)
    cada = EMOCION_CADA_S[0] if total_s <= 200 else EMOCION_CADA_S[1]
    pistas = [p for p in (_pista(tl, PISTAS["publico2"]), _pista(tl, PISTAS["publico"])) if p]
    if not pistas:
        return []
    ocupado = {t: [(it.GetStart() - st, it.GetEnd() - st) for it in tl.GetItemListInTrack("audio", t) or []]
               for t in pistas}
    cand = []
    for p, it in puestos_plan:
        item = p.get("item") or {}
        if p.get("tipo") != "video" or it is None:
            continue
        ini = float(p.get("ini") or 0.0)
        dur = p.get("dur_f", 0) / float(S)
        if dur < 1.0:
            continue
        pasajes = [(float(x.get("ini", 0)), float(x.get("fin", 0))) if isinstance(x, dict) else tuple(x[:2])
                   for x in (item.get("pasajes") or [])]   # {'ini', 'fin', 'texto', 'tipo': 'DISCURSO'...}
        if any(a < ini + dur and ini < b for a, b in pasajes):
            continue                                       # alguien habla (votos, brindis con voz): no se tapa
        vistas = set()
        for x in ((item.get("ia") or {}).get("instantes") or []):
            if len(x) > 1 and ini - 0.5 <= float(x[0]) <= ini + dur + 0.5:
                vistas |= set(x[1] or [])
        claves = [k for k in EMOCION if k in vistas]
        if claves:
            cand.append((it.GetStart() - st, claves[0]))
    hechos, ultimo, usados = [], -1e9, {}
    for f, clave in sorted(cand):
        if len(hechos) >= EMOCION_MAX or (f - ultimo) / float(S) < cada:
            continue
        if f < FIN_INTRO_S * S:              # (visto) vitores a los 3 s, sobre «UN FILM DE»: en la intro no
            continue
        opciones = EMOCION[clave]
        n = usados.get(clave, 0)
        nombre = opciones[n % len(opciones)]
        c = (propios or {}).get(nombre) if nombre.startswith("XV_") else buscar(nombre)
        if c is None:
            continue
        dur = _sin_voz(f, int(min(EMOCION_DUR_S * S, _frames(c, fps), total_s * S - f)), evitar, S)
        if dur < S:
            continue
        for t in pistas:
            if any(a < f + dur and f < b for a, b in ocupado[t]):
                continue
            tl.SetTrackLock("audio", t, False)
            r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": dur - 1, "mediaType": 2,
                                      "trackIndex": t, "recordFrame": st + int(f)}])
            if not r:
                continue
            try:
                r[0].SetFades({"FadeIn": int(0.25 * S), "FadeOut": int(min(1.5 * S, dur / 2))})
                if nombre.startswith("XV_"):
                    r[0].SetProperty("AudioVolume", -6.0)
            except Exception:
                pass
            ocupado[t].append((f, f + dur))
            hechos.append((nombre, round(f / float(S), 1), clave))
            usados[clave] = n + 1
            ultimo = f
            break
    log("  SFX de emoción: %d planos con un momento clave, %d con su sonido%s." % (
        len(cand), len(hechos), (": " + ", ".join("%s %.0f s (%s)" % h for h in hechos[:6])) if hechos else ""))
    return [(h[0], h[1]) for h in hechos]


def momentos(tl, mp, propios, fps, fotos_intro=(), log=print):
    """Los momentos fuertes, con los SFX propios del programa (propios: {"XV_GOLPE": MediaPoolItem, ...}):
      - entrada de la FIESTA (marcador ACTO ... FIESTA): subida de aire que termina en seco y golpe grave en el cambio;
      - titulo con el nombre y tarjeta final: destellos;
      - cada capitulo y la entrada de la imagen final: paso de aire corto;
      - fotos de la intro: un clic de camara por foto (rafaga).
    fotos_intro: cuadros (desde el inicio de la linea) en que empieza cada foto de la intro.
    Devuelve [(sonido, segundo)]."""
    if not propios:
        return []
    st = tl.GetStartFrame()
    S = fps
    t = _pista(tl, PISTA_MOMENTOS)
    if not t:
        if not tl.AddTrack("audio", "stereo"):
            return []
        t = tl.GetTrackCount("audio")
        tl.SetTrackName("audio", t, PISTA_MOMENTOS)
    tl.SetTrackLock("audio", t, False)
    viejos = tl.GetItemListInTrack("audio", t) or []
    if viejos:
        tl.DeleteClips(viejos, False)
    ocupado, puestos = [], []

    def poner(nombre, ini, vol=None, fi=0, fo=0):
        c = propios.get(nombre)
        ini = int(ini)
        if c is None or ini < 0:
            return False
        dur = max(2, _frames(c, fps))
        if any(a < ini + dur and ini < b for a, b in ocupado):
            return False
        r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": dur - 1, "mediaType": 2,
                                  "trackIndex": t, "recordFrame": st + ini}])
        if not r:
            return False
        try:
            if vol is not None:
                r[0].SetProperty("AudioVolume", vol)
            if fi or fo:
                r[0].SetFades({"FadeIn": int(fi), "FadeOut": int(fo)})
        except Exception:
            pass
        ocupado.append((ini, ini + dur))
        puestos.append((nombre, round(ini / float(S), 1)))
        return True

    marcas = sorted((int(f), (m.get("name") or "").strip().upper()) for f, m in (tl.GetMarkers() or {}).items())
    fiesta = next((f for f, n in marcas if n.startswith("ACTO") and "FIESTA" in n), None)
    if fiesta is not None and fiesta > 5 * S:
        sub = propios.get("XV_SUBIDA")
        largo = _frames(sub, fps) if sub is not None else 0
        poner("XV_SUBIDA", fiesta - largo)
        poner("XV_GOLPE", fiesta)
    textos = []
    for v in range(1, tl.GetTrackCount("video") + 1):
        for it in tl.GetItemListInTrack("video", v) or []:
            n = (it.GetName() or "").upper()
            if n.startswith("TEXTO "):
                textos.append((it.GetStart() - st, n))
    for ini, n in sorted(textos):
        if n.startswith("TEXTO NOMBRE") or n.startswith("TEXTO FINAL"):
            poner("XV_BRILLO", ini + int(0.15 * S), fo=0.5 * S)
        elif n.startswith("TEXTO CAPITULO"):
            poner("XV_PASO", ini - int(0.2 * S), VOL_PASO)
    for f in fotos_intro:
        poner("XV_OBTURADOR", f, VOL_OBTURADOR)
    if fotos_intro:                             # (17-nov) rampa de velocidad de las fotos: aire que late con cada foto
        fs = sorted(fotos_intro)                # e impacto al arrancar el video; una rampa por tipo de intro (Ajustes)
        pasos = [b - a for a, b in zip(fs, fs[1:])]
        nombre = next((n for n, c in RAMPAS.items() if list(c[:len(pasos)]) == pasos and n in propios), "XV_RAMPA")
        poner(nombre, fs[0])
    return puestos
