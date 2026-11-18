# -*- coding: utf-8 -*-
"""
overlays.py - Los overlays propios (recursos/overlays, los crea herramientas/hacer_overlays.py) en la linea del evento:
luz sobre negro en una pista de arriba, en modo «Pantalla» (Screen).

(17-nov, la persona: «crea elementos, overlays o transiciones súper potentes, dependiendo si son bodas o XV años»)

    DESTELLO  en cada cambio de momento (preparativos -> iglesia -> fiesta): la banda de luz llena el cuadro justo en
              el corte. Va con el «paso de aire» (XV_PASO) que pone sfx.momentos en los capitulos.
    BRILLOS   sobre el titulo con el nombre y sobre la tarjeta final: polvo de luz que sube.

El color lo da el tipo de evento (boda: blanco calido; los demas: dorado con rosa) y el formato, la linea (H o V).
Con el estado «overlays» en False (o TRAILER_OVERLAYS=0) no se pone nada.
"""
import os

import rutas

CARPETA = os.path.join(rutas.RECURSOS, "overlays")
PISTA = "LUZ"
DESTELLO_F, BRILLOS_F = 30, 96            # cuadros de cada overlay (24 por segundo)


def activos():
    if os.environ.get("TRAILER_OVERLAYS", "") == "0" or not os.path.isdir(CARPETA):
        return False
    try:
        import motor
        return motor.leer_estado().get("overlays", True) is not False
    except Exception:
        return True


def _archivo(tipo, efecto, vertical):
    for t in (("BODA" if str(tipo).lower() == "boda" else "XV"), "XV"):
        r = os.path.join(CARPETA, "%s_%s_%s.mp4" % (t, efecto, "V" if vertical else "H"))
        if os.path.exists(r):
            return r
    return None


def poner(resolve, tl, mp, carpeta_mp, fps, tipo, vertical, cambios, log=print):
    """cambios: cuadros (desde el inicio de la linea) donde empieza cada momento nuevo (sin el primero).
    Devuelve [(efecto, segundo)] de lo que puso."""
    if not activos():
        return []
    rutas_ov = {e: _archivo(tipo, e, vertical) for e in ("DESTELLO", "BRILLOS")}
    hay = {os.path.normcase(c.GetClipProperty("File Path") or ""): c for c in carpeta_mp.GetClipList() or []}
    faltan = [r for r in rutas_ov.values() if r and os.path.normcase(r) not in hay]
    if faltan:
        mp.SetCurrentFolder(carpeta_mp)
        for c in mp.ImportMedia(faltan) or []:
            hay[os.path.normcase(c.GetClipProperty("File Path") or "")] = c
    clips = {e: hay.get(os.path.normcase(r)) for e, r in rutas_ov.items() if r}
    if not any(clips.values()):
        return []
    pista = next((t for t in range(1, tl.GetTrackCount("video") + 1)
                  if (tl.GetTrackName("video", t) or "").strip().upper() == PISTA), None)
    if pista is None:
        if not tl.AddTrack("video"):
            return []
        pista = tl.GetTrackCount("video")
        tl.SetTrackName("video", pista, PISTA)
    st, fin = tl.GetStartFrame(), tl.GetEndFrame()
    pedidos = []
    if clips.get("DESTELLO") is not None:
        pedidos += [("DESTELLO", int(c) - DESTELLO_F // 2, DESTELLO_F) for c in cambios]
    if clips.get("BRILLOS") is not None:
        for v in range(1, tl.GetTrackCount("video") + 1):
            for it in tl.GetItemListInTrack("video", v) or []:
                n = (it.GetName() or "").upper()
                if n.startswith("TEXTO NOMBRE") or n.startswith("TEXTO FINAL"):
                    pedidos.append(("BRILLOS", it.GetStart() - st, BRILLOS_F))
    puestos, ocupado = [], []
    for efecto, ini, largo in sorted(pedidos, key=lambda p: p[1]):
        ini = max(0, ini)
        largo = min(largo, fin - st - ini)
        if largo < 8 or any(ini < b and ini + largo > a for a, b in ocupado):      # no se enciman en la pista
            continue
        nuevo = mp.AppendToTimeline([{"mediaPoolItem": clips[efecto], "startFrame": 0, "endFrame": largo,
                                      "mediaType": 1, "trackIndex": pista, "recordFrame": st + ini}]) or []
        if not nuevo:
            continue
        try:
            nuevo[0].SetProperty("CompositeMode", resolve.COMPOSITE_SCREEN)
            if efecto == "BRILLOS":
                nuevo[0].SetProperty("Opacity", 85.0)
        except Exception:
            pass
        ocupado.append((ini, ini + largo))
        puestos.append((efecto, round(ini / float(fps), 1)))
    if puestos:
        log("Overlays de luz: %d destellos en los cambios de momento y %d brillos en los titulos." % (
            sum(1 for e, _ in puestos if e == "DESTELLO"), sum(1 for e, _ in puestos if e == "BRILLOS")))
    return puestos
