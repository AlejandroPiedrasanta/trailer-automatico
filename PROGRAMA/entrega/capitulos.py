# -*- coding: utf-8 -*-
"""
capitulos.py - (1.6.0) Los capítulos para YouTube de cada video (la persona eligió esta mejora): junto a cada video
terminado, un .txt con «00:00 Valeria · Mis XV años / 03:12 La ceremonia / ...» para pegar en la descripción.

  guardar_titulos(linea, intro, zonas)   lo llama build_trailers al armar (el titulo de cada momento, del perfil)
  escribir(tl, inicio, ruta_video, log)  lo llama renderizar.py tras el render: lee DONDE quedaron los textos
                                         «TEXTO CAPITULO <MOMENTO>» en la linea (asi vale tambien lo retocado a mano)

YouTube pide: el primero en 00:00, al menos 3 y cada uno de 10 s o mas. Si no alcanzan (el de 1 min), no hay archivo.
"""
import json
import os
import subprocess

import rutas

PREFIJO = "TEXTO CAPITULO "
MIN_S = 10.0


def _carpeta():
    return os.path.join(rutas.DATOS, "capitulos")


def _archivo(linea):
    return os.path.join(_carpeta(), "".join(c if c.isalnum() or c in " -_" else "_" for c in linea) + ".json")


def guardar_titulos(linea, intro, zonas):
    """intro: el titulo del principio («Valeria · Mis XV años»); zonas: {MOMENTO: titulo del capitulo}."""
    try:
        os.makedirs(_carpeta(), exist_ok=True)
        with open(_archivo(linea), "w", encoding="utf-8") as f:
            json.dump({"intro": intro, "zonas": zonas}, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _hora(s):
    s = int(round(s))
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60) if s >= 3600 else "%02d:%02d" % (s // 60, s % 60)


def _duracion(ruta):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                           creationflags=rutas.SIN_VENTANA)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def lista(tl, inicio):
    """[(segundo, titulo)] de los capitulos de la linea, contados desde `inicio` (el primer cuadro del render)."""
    try:
        with open(_archivo(tl.GetName()), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        info = {}
    zonas = info.get("zonas") or {}
    fps = float(tl.GetSetting("timelineFrameRate") or 24)
    caps = []
    for t in range(1, tl.GetTrackCount("video") + 1):
        for x in tl.GetItemListInTrack("video", t) or []:
            nombre = (x.GetName() or "").strip()
            if nombre.upper().startswith(PREFIJO) and x.GetClipEnabled():
                zona = nombre[len(PREFIJO):].strip().upper()
                caps.append(((x.GetStart() - inicio) / fps, zonas.get(zona) or zona.capitalize()))
    return [(0.0, info.get("intro") or "Inicio")] + sorted(c for c in caps if c[0] > 0)


def limpiar(caps, total):
    """Las reglas de YouTube: desde 00:00, cada uno de MIN_S o mas (tambien el ultimo, hasta el final)."""
    res = []
    for s, t in caps:
        if not res or s - res[-1][0] >= MIN_S:
            res.append((s, t))
    while total and len(res) > 1 and total - res[-1][0] < MIN_S:
        res.pop()
    return res


def escribir(tl, inicio, ruta_video, log=print):
    caps = limpiar(lista(tl, inicio), _duracion(ruta_video))
    destino = os.path.splitext(ruta_video)[0] + " - CAPITULOS YOUTUBE.txt"
    if len(caps) < 3:
        return None
    texto = ("Capítulos para YouTube (pégalos en la descripción del video):\n\n"
             + "\n".join("%s %s" % (_hora(s), t) for s, t in caps) + "\n")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)
    log("Capítulos para YouTube: %s (%d)" % (os.path.basename(destino), len(caps)))
    return destino
