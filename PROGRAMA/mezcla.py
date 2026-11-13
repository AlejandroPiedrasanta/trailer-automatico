# -*- coding: utf-8 -*-
"""
mezcla.py - Mezcla de sonido medida: cada cancion y cada SFX de la timeline a su nivel.

Mide el volumen real (LUFS, EBU R128) del tramo exacto que suena de cada clip de audio y le pone la
ganancia que lo lleva al objetivo de su pista:
  MUSICA ............ -18 LUFS   (todas las canciones iguales: no hay saltos entre actos)
  SFX WHOOSH ........ -22        (presente en el corte)
  SFX CAMPANAS/GRITOS -23
  SFX CHISPA ........ -24
  SFX PUBLICO ....... -25        (ambiente bajo la musica)
Los trozos cortos (cortes ritmicos de la intro) usan la ganancia de su misma cancion. El masterizado del
render deja despues todo el video a -14 LUFS. Cache en PROGRAMA\\datos\\analisis\\volumen.json.
"""
import os
import re
import json
import subprocess

OBJETIVOS = [("MUSICA", -18.0), ("WHOOSH", -22.0), ("CAMPANAS", -23.0), ("GRITO", -23.0),
             ("CHISPA", -24.0), ("PUBLICO", -25.0), ("SFX", -24.0)]
GANANCIA = (-18.0, 12.0)        # dB maximos que se baja / sube un clip
MIN_SEG = 1.0                   # clips mas cortos usan la ganancia de su cancion
import rutas
SIN_VENTANA = rutas.SIN_VENTANA


def objetivo_de(pista):
    p = (pista or "").upper()
    return next((v for k, v in OBJETIVOS if k in p), None)


def medir_lufs(ruta, ini, dur):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", "%.3f" % max(0.0, ini), "-t", "%.3f" % dur,
                        "-i", ruta, "-vn", "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600, creationflags=SIN_VENTANA)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    v = float(i[-1]) if i else None
    return v if v is not None and v > -60 else None


def nivelar(tl, fps, base, log=print):
    """Ajusta AudioVolume de cada clip de audio de la timeline. Devuelve cuantos se ajustaron."""
    cache_ruta = os.path.join(rutas.ANALISIS, "volumen.json")
    try:
        with open(cache_ruta, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    largos, cortos = [], []
    for t in range(1, tl.GetTrackCount("audio") + 1):
        obj = objetivo_de(tl.GetTrackName("audio", t))
        if obj is None:
            continue
        tl.SetTrackLock("audio", t, False)
        for it in tl.GetItemListInTrack("audio", t) or []:
            mpi = it.GetMediaPoolItem()
            ruta = mpi.GetClipProperty("File Path") if mpi else ""
            if not ruta or not os.path.exists(ruta):
                continue
            dur = it.GetDuration() / float(fps)
            (largos if dur >= MIN_SEG else cortos).append((t, obj, it, ruta, it.GetLeftOffset() / float(fps), dur))
    ganancia_de = {}
    n = 0

    def poner(it, g):
        g = round(max(GANANCIA[0], min(GANANCIA[1], g)), 1)
        try:
            ok = it.SetProperties({"AudioVolume": g})
        except Exception:
            ok = False
        if not ok:
            try:
                ok = it.SetProperty("AudioVolume", g)
            except Exception:
                ok = False
        return bool(ok)

    for t, obj, it, ruta, ini, dur in largos:
        clave = "%s|%.2f|%.2f" % (ruta, ini, dur)
        if clave not in cache:
            cache[clave] = medir_lufs(ruta, ini, dur)
        medido = cache[clave]
        if medido is None:
            continue
        g = obj - medido
        ganancia_de.setdefault((t, ruta), g)
        n += poner(it, g)
    for t, obj, it, ruta, ini, dur in cortos:       # cortes ritmicos: misma ganancia que su cancion
        g = ganancia_de.get((t, ruta))
        if g is None:
            g = next((v for (pt, pr), v in ganancia_de.items() if pr == ruta), None)
        if g is not None:
            n += poner(it, g)
    os.makedirs(os.path.dirname(cache_ruta), exist_ok=True)
    with open(cache_ruta, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return n
