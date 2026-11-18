# -*- coding: utf-8 -*-
"""
ambiente.py - Los GRITOS, APLAUSOS Y RISAS DE VERDAD del evento, bajo la musica.

(17-nov, la persona: «pule más los SFX con gritos, emociones») Los vitores de libreria suenan a libreria. El oido
(oido.py, earshot) ya sabe en que segundos de cada toma la gente aplaude, grita o rie: cuando un plano del video cae en
uno de esos momentos, su PROPIO sonido entra en la pista «EXTRA AUDIO 1», bajito y con fundidos, debajo de la musica.
Es la emocion real de esa fiesta, sincronizada con la imagen porque es el audio de ese mismo plano.

No entra en camara lenta (el sonido se deformaria) ni donde alguien habla de corrido (eso es la «voz original»).
Como mucho uno cada pocos segundos, los mas fuertes primero. Estado «ambiente» en False o TRAILER_AMBIENTE=0 lo apaga.
"""
import os

PISTA = "EXTRA AUDIO 1"
MINIMO = 0.45                   # cuanto tiene que oirse (0-1 del oido) para que entre
VOLUMEN_DB = -7.0
PESOS = {"vitores": 1.0, "aplausos": 1.0, "risas": 0.85}


def activo():
    if os.environ.get("TRAILER_AMBIENTE", "") == "0":
        return False
    try:
        import motor
        return motor.leer_estado().get("ambiente", True) is not False
    except Exception:
        return True


def fuerza(item, ini_s, dur_s):
    """(0-1, que se oye) en el tramo [ini_s, ini_s + dur_s] de la toma, segun el oido."""
    o = item.get("oido") or {}
    paso, ven = float(o.get("paso") or 4.0), float(o.get("ventana") or 8.0)
    mejor, que = 0.0, ""
    for g, peso in PESOS.items():
        serie = o.get(g) or []
        for k, v in enumerate(serie):
            if k * paso < ini_s + dur_s and k * paso + ven > ini_s and v * peso > mejor:
                mejor, que = v * peso, g
    habla = max([v for k, v in enumerate(o.get("habla") or []) if k * paso < ini_s + dur_s and k * paso + ven > ini_s]
                or [0.0])
    return (0.0, "") if habla > 0.8 and mejor < 0.7 else (mejor, que)


def poner(tl, mp, pool, puestos, fps, log=print):
    """puestos: [(pieza del plan, clip de la linea)]. Devuelve [(que, segundo)] de lo que puso."""
    if not activo():
        return []
    pista = next((t for t in range(1, tl.GetTrackCount("audio") + 1)
                  if (tl.GetTrackName("audio", t) or "").strip().upper() == PISTA), None)
    if pista is None:
        log("  ambiente real: la línea no tiene la pista «%s»; no se pone." % PISTA)
        return []
    st = tl.GetStartFrame()
    cand = []
    # (17-nov) en el armado del XV 8-nov no entro ninguno y no se supo por que (a mano, sobre la misma linea, entraron
    # 15): ahora siempre dice cuantos planos miro y cuantos tenian emocion
    vistos = sum(1 for p, it in puestos if p.get("tipo") == "video" and it is not None)
    con_oido = sum(1 for p, it in puestos if p.get("tipo") == "video" and (p.get("item") or {}).get("oido"))
    for p, it in puestos:
        item = p.get("item") or {}
        if p.get("tipo") != "video" or it is None:
            continue
        # camara lenta de verdad: fuera. (17-nov, por esto no entraba NINGUNO) Los videos de 30 c/s en una linea de 24
        # van «conformados» al 80 % y tambien traen «lento_ok»: esos SI cuentan (en 2 s de aplausos no se nota).
        if p.get("lento_ok") and not p.get("conformado"):
            continue
        if p.get("vel", 1.0) < 0.75:
            continue
        dur_s = p.get("dur_f", 0) / float(fps)
        f, que = fuerza(item, float(p.get("ini") or 0.0), dur_s)
        if f >= MINIMO and dur_s >= 0.8:
            cand.append((f, que, p, it))
    if not cand:
        log("  ambiente real: %d planos de video, %d con datos del oído, ninguno con aplausos, gritos o risas claros."
            % (vistos, con_oido))
        return []
    total_s = (tl.GetEndFrame() - st) / float(fps)
    tope = max(4, int(total_s / (8.0 if total_s <= 200 else 20.0)))
    tl.SetTrackLock("audio", pista, False)
    hechos, ocupado = [], []
    for f, que, p, it in sorted(cand, key=lambda c: -c[0]):
        if len(hechos) >= tope:
            break
        a, b = it.GetStart(), it.GetEnd()
        if any(a < y + int(1.5 * fps) and b > x - int(1.5 * fps) for x, y in ocupado):     # no dos pegados
            continue
        mpi = pool.get(os.path.normcase(p["item"].get("ruta") or ""))
        if mpi is None:
            continue
        try:
            k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
            s0 = int(round(float(p.get("ini") or 0.0) * fps * k))
            nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0, "endFrame": s0 + int(round((b - a) * k)),
                                          "mediaType": 2, "trackIndex": pista, "recordFrame": a}]) or []
            if not nuevo:
                continue
            nuevo[0].SetProperty("AudioVolume", VOLUMEN_DB)
            fund = int(min(8, (b - a) // 3))
            nuevo[0].SetFades({"FadeIn": fund, "FadeOut": fund})
        except Exception:
            continue
        ocupado.append((a, b))
        hechos.append((que, round((a - st) / float(fps), 1)))
    if not hechos:
        log("  ambiente real: %d planos con emoción, pero DaVinci no dejó poner ninguno en «%s»." % (len(cand), PISTA))
    if hechos:
        cuenta = {}
        for que, _ in hechos:
            cuenta[que] = cuenta.get(que, 0) + 1
        log("Ambiente real del evento bajo la música: %s." % ", ".join("%d de %s" % (n, q) for q, n in cuenta.items()))
    return sorted(hechos, key=lambda h: h[1])
