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

CUADROS_MAX = 180
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


def revisar(ruta, log=print):
    """[segundos] del video final donde la IA local ve algo que no deberia ir; None si no hay IA local."""
    try:
        import vision_ia
    except Exception:
        return None
    modelo = vision_ia.modelo(log)
    if not modelo:
        return None
    dur = _duracion(ruta)
    if dur <= 1:
        return []
    maximo = CUADROS_MAX if vision_ia.en_gpu() else CUADROS_SIN_GPU     # DaVinci llenando la GPU: una muestra
    paso = max(PASO_MIN_S, dur / float(maximo))
    tiempos = []
    t = max(SIN_REVISAR_INICIO_S, paso / 2.0)              # la entrada (fundido desde negro) y la tarjeta final no
    while t < dur - SIN_REVISAR_FINAL_S:
        tiempos.append(round(t, 1))
        t += paso

    def uno(t):                         # (16-nov) la misma regla que al analizar: techo, de cabeza, gente sin cara...
        img = vision_ia._cuadro(ruta, t, 448)
        if not img:
            return t, ""
        try:
            return t, vision_ia._ver_cuadro(modelo, img)[1]
        except Exception:
            return t, ""
    with ThreadPoolExecutor(vision_ia.PARALELO) as ex:
        malos = [(t, motivo) for t, motivo in ex.map(uno, tiempos) if motivo]
    if malos:
        log("REVISAR (IA) %s: %s" % (os.path.basename(ruta), ", ".join(
            "%d:%02d %s" % (t // 60, t % 60, vision_ia.MOTIVOS.get(m, m)) for t, m in malos[:12])
            + (" …" if len(malos) > 12 else "")))
        malos = [t for t, _ in malos]
    else:
        log("Revision con IA de %s: nada fuera de lugar (%d cuadros)." % (os.path.basename(ruta), len(tiempos)))
    return malos


def marcar(timeline, segundos, desde_frame=0, color=COLOR, nombre=NOMBRE_MARCA, nota=NOTA):
    """Marcadores rojos «REVISAR (IA)» en la linea, en esos segundos del video (desde_frame: donde empezo el render).
    (1.5.9) Con color/nombre/nota, los amarillos del audio."""
    fps = float(timeline.GetSetting("timelineFrameRate") or 24)
    n = 0
    for s in segundos or []:
        try:
            n += bool(timeline.AddMarker(int(desde_frame + s * fps), color, nombre, nota, 1, ""))
        except Exception:
            pass
    return n
