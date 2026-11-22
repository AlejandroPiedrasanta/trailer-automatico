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


FUNDIDO_S = 0.4          # (1.8.7) cerca de un corte se ven dos imagenes a la vez (el fundido): no se pregunta
CERCA_INSTANTE_S = 2.0   # un cuadro del video final cuenta como ya visto si la IA vio bien su toma a menos de esto
CONFIRMAR_S = 1.2        # (1.8.7) cada aviso se confirma con otro cuadro de la MISMA toma a esta distancia
AL_REVES_FUERZA, AL_REVES_VENTAJA = 6.0, 3.0   # (1.8.7) caras giradas claras antes de preguntarle a la IA de vista


def tramos_vistos(tl, desde_frame=None):
    """[(ini_s, fin_s, pista, ya_visto, origen)] de cada clip de material de la linea, en segundos del video final.
    ya_visto: no se pregunta en todo el clip (aerea, foto o vertical con relleno: son asi a proposito).
    origen: (seg_ini, seg_fin, [(segundo, bueno)]) la parte de la toma que usa el clip (GetSourceStartTime / EndTime:
    vale tambien en camara lenta y conformado) y lo que la IA vio en ella al analizar (vision_ia.instantes, cada 3 s).
    (19-nov) La revision final no vuelve a preguntar lo que la IA ya vio bien: es la misma imagen con color y estabilizador.
    (1.8.7) Antes se decidia por clip entero (todos sus instantes buenos), y casi ningun clip pasaba: ahora cuadro por
    cuadro (_visto)."""
    import persona_delante as pdl
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            items = {os.path.normcase(i["ruta"]): i for i in json.load(f).get("items") or [] if i.get("ruta")}
    except Exception:
        return []
    fps = float(tl.GetSetting("timelineFrameRate") or 24)
    desde = tl.GetStartFrame() if desde_frame is None else desde_frame
    try:
        horizontal = float(tl.GetSetting("timelineResolutionWidth") or 16) >= float(
            tl.GetSetting("timelineResolutionHeight") or 9)
    except Exception:
        horizontal = True
    pistas = range(1, tl.GetTrackCount("video") + 1)
    encendida = {}
    for v in pistas:
        try:
            encendida[v] = bool(tl.GetIsTrackEnabled("video", v))
        except Exception:
            encendida[v] = True
    # (1.8.7, MEDIDO) GetIsTrackEnabled da False en TODAS las pistas de una linea que no es la activa (el de 30 min con el
    # de 15 abierto): la revision no salteaba nada del de 30 y marcaba sus aereas. Solo se cree si alguna dice que si.
    if not any(encendida.values()):
        encendida = {v: True for v in pistas}
    out = []
    for v in pistas:
        if not encendida[v]:                       # (revision) una pista apagada no es lo que se ve
            continue
        for it in tl.GetItemListInTrack("video", v) or []:
            if not pdl._es_material(it):
                continue
            ok, origen = False, None
            try:
                m = it.GetMediaPoolItem()
                d = items.get(os.path.normcase(m.GetClipProperty("File Path") or ""))
                inst = [(float(x[0]), x[2] is True) for x in ((d or {}).get("ia") or {}).get("instantes") or []
                        if len(x) > 2]
                # (1.8.7, visto en NUESTRA BODA: 13 marcas rojas por video y casi todas falsas) lo que es asi a proposito
                # no se pregunta: las aereas («no se ve ninguna cara»), las fotos (los anillos de cerca: «gente sin
                # cabeza») y los videos verticales en la linea horizontal (sus lados difuminados: «algo pegado al lente»)
                if d and (d.get("tipo") in ("dron", "foto") or (horizontal and not d.get("horizontal", True))):
                    ok = True
                elif inst:
                    try:
                        s0, s1 = float(it.GetSourceStartTime()), float(it.GetSourceEndTime())
                    except Exception:
                        s0 = s1 = None
                    if s0 is not None and s1 > s0:
                        origen = (s0, s1, inst)
                    else:                          # sin la parte de la toma: como antes, todo el clip bien o nada
                        fps_m = float(m.GetClipProperty("FPS") or fps) or fps
                        los = (it.GetLeftOffset() / fps_m, it.GetLeftOffset() / fps)
                        dur = (it.GetEnd() - it.GetStart()) / fps
                        rango = [x for x in inst if min(los) - 1.5 <= x[0] <= max(los) + 2 * dur + 1.5]
                        ok = bool(rango) and all(b for _, b in rango)
            except Exception:
                ok = False
            out.append(((it.GetStart() - desde) / fps, (it.GetEnd() - desde) / fps, v, ok, origen))
    return out


def _visto(tramos, t):
    """¿Hace falta NO preguntar por el segundo t? Si: en el fundido de un corte (dos imagenes a la vez: la IA veia «algo
    pegado al lente»), en lo que es asi a proposito (aereas, fotos, verticales con relleno) o si la IA ya vio bien ESE
    momento de la toma al analizar (a menos de CERCA_INSTANTE_S)."""
    cerca = [x for x in tramos if x[0] - FUNDIDO_S <= t < x[1] + FUNDIDO_S]
    if not cerca:
        return False
    arriba = max(cerca, key=lambda x: x[2])
    if not (arriba[0] + FUNDIDO_S <= t < arriba[1] - FUNDIDO_S):
        return True
    if arriba[3]:
        return True
    origen = arriba[4] if len(arriba) > 4 else None
    if not origen:
        return False
    s0, s1, inst = origen
    seg = s0 + (t - arriba[0]) * (s1 - s0) / max(1e-6, arriba[1] - arriba[0])
    vistos = [b for x, b in inst if abs(x - seg) <= CERCA_INSTANTE_S]
    return bool(vistos) and all(vistos)


def _otro_cuadro(tramos, t):
    """Un segundo de la MISMA toma a CONFIRMAR_S de t (despues o, si no cabe, antes), lejos de los cortes; None si no hay
    o si no se sabe donde empieza y acaba la toma."""
    cerca = [x for x in tramos or [] if x[0] <= t < x[1]]
    if not cerca:
        return None
    ini, fin = max(cerca, key=lambda x: x[2])[:2]
    for t2 in (t + CONFIRMAR_S, t - CONFIRMAR_S):
        if ini + FUNDIDO_S <= t2 < fin - FUNDIDO_S:
            return round(t2, 1)
    return None


def _al_reves(ruta, t):
    """(1.8.7) ¿El cuadro t del video TERMINADO se ve girado (de cabeza o de lado)? Las caras (YuNet) se ven derechas
    claramente mejor en otra rotacion y la IA de vista lo confirma (orientacion.py)."""
    try:
        import numpy as np
        import orientacion as ori
        img = ori._cuadro(ruta, t)
        if img is None:
            return False
        f = [ori._fuerza(np.ascontiguousarray(np.rot90(img, q))) for q in range(4)]
        q = max(range(4), key=lambda i: f[i])
        if q == 0 or f[q] < AL_REVES_FUERZA or f[q] < AL_REVES_VENTAJA * max(f[0], 0.5):
            return False
        return ori._por_ia(img) == q * 90
    except Exception:
        return False


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
    pedidos, cuantos, saltados, todos = [], {}, 0, []
    for ruta in rutas_:
        dur = _duracion(ruta)
        paso = max(PASO_MIN_S, dur / float(maximo))
        t = max(SIN_REVISAR_INICIO_S, paso / 2.0)          # la entrada (fundido desde negro) y la tarjeta final no
        n = 0
        tramos = (vistos or {}).get(ruta) or []
        while dur > 1 and t < dur - SIN_REVISAR_FINAL_S:
            todos.append((ruta, round(t, 1)))
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
    # (1.8.7, MEDIDO en NUESTRA BODA) segunda mirada: cada aviso se confirma con otro cuadro de la misma toma (una cabeza
    # delante del lente sigue ahi 1 s despues; «gente sin cabeza» en el baile, de noche y de lejos, no se repetia)
    otra = {(r, t): _otro_cuadro((vistos or {}).get(r), t) for r in rutas_ for t, _ in malos[r]}
    pedir = [(r, t2) for (r, _t), t2 in otra.items() if t2 is not None]
    if pedir:
        segunda = set()
        with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
            for ruta, t2, motivo in ex.map(uno, pedir):
                if motivo:
                    segunda.add((ruta, t2))
        antes = sum(len(v) for v in malos.values())
        for r in rutas_:
            malos[r] = [(t, x) for t, x in malos[r] if otra.get((r, t)) is None or (r, otra[(r, t)]) in segunda]
        quitados = antes - sum(len(v) for v in malos.values())
        if quitados:
            log("Revision con IA: %d avisos no se repitieron en la segunda mirada (quitados)." % quitados)
    # (1.8.7, la persona: «verifica que no haya tomas al revés, que la IA reconozca eso») en TODOS los cuadros (tambien
    # los ya vistos al analizar: lo girado lo hace DaVinci, no la toma), caras en las 4 rotaciones y, si parece girado,
    # la IA de vista lo confirma
    with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
        for ruta, t, girado in ex.map(lambda par: par + (_al_reves(*par),), todos):
            if girado and not any(abs(t - x) < 0.5 for x, _ in malos[ruta]):
                malos[ruta].append((t, "al_reves"))
    for r in rutas_:
        malos[r].sort()
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
