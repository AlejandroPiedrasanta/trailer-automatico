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


def sonorizar(tl, mp, buscar, zonas, fps, cortes, log=print):
    """zonas: [(nombre, inicio_f, fin_f)] relativos al inicio de la timeline; cortes: inicios de plano.
    buscar(clave) -> MediaPoolItem. Devuelve cuantos SFX se colocaron."""
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
        dur = int(min(dur, _frames(c, fps), total - ini))
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
