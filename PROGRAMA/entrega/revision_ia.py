# -*- coding: utf-8 -*-
"""
revision_ia.py - (1.5.7) Revisión final con la IA local: mira el VIDEO TERMINADO como lo vería la persona.

La persona (2026-11-16, «aplica todo»): «revisión final con IA: que mire cada corte del video final y avise o corrija si se
coló algo negro, borroso o la pantalla de una cámara». Tras el render, la IA local (vision_ia: Qwen3-VL en Ollama) mira un
cuadro cada pocos segundos del video final (como mucho CUADROS_MAX) y dice dónde se ve el piso, una cámara o su pantalla, algo
borroso o a oscuras. renderizar.py lo anota en el registro y pone un marcador ROJO «REVISAR (IA)» en ese punto de la línea
de DaVinci: se cambia ese plano a mano y se pulsa «Renderizar lo editado». Sin IA local no hace nada.
"""
import os
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import rutas

# (18-nov, medido en la boda: 270 cuadros de 4 videos en 253 s, 180 del de 15 min) las tomas ya pasaron por la IA
# cuadro por cuadro al analizar y lo negro / congelado lo mira masterizar.revisar_cortes: 100 bastan (15 min: uno cada 9 s)
CUADROS_MAX = 100
SIN_REVISAR_INICIO_S, SIN_REVISAR_FINAL_S = 3.0, 6.0    # la boda: marcaba 0:01 en todos (el fundido de la plantilla)
CUADROS_SIN_GPU = 30         # si el modelo no cabe en la GPU (DaVinci abierto), una muestra mas chica
PASO_MIN_S = 3.0
COLOR = "Red"
NOMBRE_MARCA = "REVISAR (IA)"
NOTA = ("La IA local ve aquí algo que no debería ir en el video (el piso, una cámara o su pantalla, borroso o a oscuras). "
        "Cambia este plano y pulsa «Renderizar lo editado» en el programa.")
COLOR_AUDIO = "Yellow"           # (1.5.9) lo que oye earshot en el audio final (oido.revisar_audio)
MARCA_AUDIO = "REVISAR (AUDIO)"
NOTA_AUDIO = ("El oído oye aquí un clic, un hueco de silencio o saturación en el audio. Escúchalo; si molesta, pon un "
              "fundido corto en el corte y pulsa «Renderizar lo editado» en el programa.")
COLOR_IMAGEN = "Purple"          # (1.6.0) cuadros negros o congelados en el video final (masterizar.revisar_cortes)
MARCA_IMAGEN = "REVISAR (IMAGEN)"
NOTA_IMAGEN = ("Aquí el video se queda en negro o congelado (un hueco en la línea o un clip sin su archivo). Llena el "
               "hueco o vuelve a enlazar el clip y pulsa «Renderizar lo editado» en el programa.")


def _duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", ruta],
                       capture_output=True, text=True, timeout=60, creationflags=rutas.SIN_VENTANA)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def tramos_vistos(tl, desde_frame=None):
    """[(ini_s, fin_s, pista, ya_visto)] de cada clip de material de la linea, en segundos del video final.
    (19-nov) ya_visto: la IA ya miro esa toma cuadro por cuadro al analizar (vision_ia.instantes) y TODOS sus cuadros
    en la parte que usa el clip (con margen: la camara lenta usa menos toma) salieron buenos. Ahi la revision final no
    vuelve a preguntar: es la misma imagen con color y estabilizador."""
    import persona_delante as pdl
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            items = {os.path.normcase(i["ruta"]): i for i in json.load(f).get("items") or [] if i.get("ruta")}
    except Exception:
        return []
    fps = float(tl.GetSetting("timelineFrameRate") or 24)
    desde = tl.GetStartFrame() if desde_frame is None else desde_frame
    out = []
    for v in range(1, tl.GetTrackCount("video") + 1):
        try:                                       # (revision) una pista apagada no es lo que se ve
            if not tl.GetIsTrackEnabled("video", v):
                continue
        except Exception:
            pass
        for it in tl.GetItemListInTrack("video", v) or []:
            if not pdl._es_material(it):
                continue
            ok = False
            try:
                m = it.GetMediaPoolItem()
                d = items.get(os.path.normcase(m.GetClipProperty("File Path") or ""))
                inst = [x for x in ((d or {}).get("ia") or {}).get("instantes") or [] if len(x) > 2]
                if inst:
                    fps_m = float(m.GetClipProperty("FPS") or fps) or fps
                    # (revision) GetLeftOffset: cuadros del clip o de la linea, segun el caso: se toma el rango que
                    # cubre las dos lecturas (mas cuadros que mirar = mas prudente)
                    los = (it.GetLeftOffset() / fps_m, it.GetLeftOffset() / fps)
                    dur = (it.GetEnd() - it.GetStart()) / fps
                    rango = [x for x in inst if min(los) - 1.5 <= x[0] <= max(los) + 2 * dur + 1.5]
                    ok = bool(rango) and all(x[2] is True for x in rango)
            except Exception:
                ok = False
            out.append(((it.GetStart() - desde) / fps, (it.GetEnd() - desde) / fps, v, ok))
    return out


def _visto(tramos, t):
    """¿Lo que se ve en el segundo t (el clip de material de la pista mas alta) ya lo reviso la IA y estaba bien?"""
    cerca = [x for x in tramos if x[0] - 0.25 <= t < x[1] + 0.25]
    if not cerca:
        return False
    arriba = max(cerca, key=lambda x: x[2])
    return arriba[3] and arriba[0] + 0.25 <= t < arriba[1] - 0.25          # lejos de los cortes (fundidos)


def revisar(ruta, log=print):
    """[segundos] del video final donde la IA local ve algo que no deberia ir; None si no hay IA local."""
    return revisar_varios([ruta], log).get(ruta)


def revisar_varios(rutas_, log=print, vistos=None):
    """{ruta: [segundos]} de varios videos finales con UNA sola cola de preguntas a la IA (None si no hay IA local).
    vistos: {ruta: tramos_vistos(...)}; esos cuadros no se preguntan otra vez.
    (18-nov, medido en la boda: 4 videos uno tras otro = 34 + 160 + 15 + 50 s) Por separado, al final de cada video
    quedaban hilos ociosos y el de 1 min no llenaba las PARALELO preguntas a la vez del servidor propio."""
    try:
        import vision_ia
    except Exception:
        return {}
    modelo = vision_ia.modelo(log)
    if not modelo:
        return {}
    import time
    t0 = time.time()
    maximo = CUADROS_MAX if vision_ia.en_gpu() else CUADROS_SIN_GPU     # DaVinci llenando la GPU: una muestra
    pedidos, cuantos, saltados = [], {}, 0
    for ruta in rutas_:
        dur = _duracion(ruta)
        paso = max(PASO_MIN_S, dur / float(maximo))
        t = max(SIN_REVISAR_INICIO_S, paso / 2.0)          # la entrada (fundido desde negro) y la tarjeta final no
        n = 0
        tramos = (vistos or {}).get(ruta) or []
        while dur > 1 and t < dur - SIN_REVISAR_FINAL_S:
            if tramos and _visto(tramos, t):
                saltados += 1
            else:
                pedidos.append((ruta, round(t, 1)))
                n += 1
            t += paso
        cuantos[ruta] = n

    def uno(par):                       # (16-nov) la misma regla que al analizar: techo, de cabeza, gente sin cara...
        ruta, t = par
        img = vision_ia._cuadro(ruta, t, 448)
        if not img:
            return ruta, t, ""
        try:
            return ruta, t, vision_ia._ver_cuadro(modelo, img)[1]
        except Exception:
            return ruta, t, ""
    malos = {r: [] for r in rutas_}
    with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
        for ruta, t, motivo in ex.map(uno, pedidos):
            if motivo:
                malos[ruta].append((t, motivo))
    out = {}
    for ruta in rutas_:
        m = malos[ruta]
        if m:
            log("REVISAR (IA) %s: %s" % (os.path.basename(ruta), ", ".join(
                "%d:%02d %s" % (t // 60, t % 60, vision_ia.MOTIVOS.get(x, x)) for t, x in m[:12])
                + (" …" if len(m) > 12 else "")))
        else:
            log("Revision con IA de %s: nada fuera de lugar (%d cuadros)." % (os.path.basename(ruta), cuantos[ruta]))
        out[ruta] = [t for t, _ in m]
    s = time.time() - t0
    log("Revision con IA: %d cuadros de %d videos en %.0f s (%.2f s por cuadro, %d a la vez%s%s)." % (
        len(pedidos), len(rutas_), s, s / max(1, len(pedidos)), vision_ia.PARALELO,
        "" if maximo == CUADROS_MAX else ", modelo fuera de la GPU: muestra chica",
        ", %d ya vistos al analizar" % saltados if saltados else ""))
    return out


def marcar(timeline, segundos, desde_frame=0, color=COLOR, nombre=NOMBRE_MARCA, nota=NOTA):
    """Marcadores rojos «REVISAR (IA)» en la linea, en esos segundos del video (desde_frame: donde empezo el render).
    (1.5.9) Con color/nombre/nota, los amarillos del audio."""
    fps = float(timeline.GetSetting("timelineFrameRate") or 24)
    try:                                 # (19-nov) los de un render anterior se quitan: si no, se duplicaban
        for f, m in (timeline.GetMarkers() or {}).items():
            if m.get("name") == nombre:
                timeline.DeleteMarkerAtFrame(f)
    except Exception:
        pass
    n = 0
    for s in segundos or []:
        try:
            n += bool(timeline.AddMarker(int(desde_frame + s * fps), color, nombre, nota, 1, ""))
        except Exception:
            pass
    return n
