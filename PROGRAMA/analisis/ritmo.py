# -*- coding: utf-8 -*-
"""
ritmo.py - Golpes (beats) de la musica de una plantilla, para que los cortes caigan al ritmo.

Lee las pistas de audio "MUSICA 1" y "MUSICA 2" de la timeline (no la de la intro), analiza cada tramo
de cancion con librosa y devuelve los frames (relativos al inicio de la timeline) donde cae cada golpe.
Guarda cache en PROGRAMA\\datos\\analisis\\ritmo.json.
"""
import os
import json

MIN_TRAMO = 5.0          # segundos: tramos mas cortos (risers, SFX) no se analizan


def tramos_musica(tl, fps):
    st = tl.GetStartFrame()
    tramos = []
    for t in range(1, tl.GetTrackCount("audio") + 1):
        nombre = (tl.GetTrackName("audio", t) or "").upper()
        if not nombre.startswith("MUSICA") or "INTRO" in nombre:
            continue
        for it in tl.GetItemListInTrack("audio", t) or []:
            mpi = it.GetMediaPoolItem()
            ruta = mpi.GetClipProperty("File Path") if mpi else ""
            dur = it.GetDuration() / float(fps)
            if ruta and os.path.exists(ruta) and dur >= MIN_TRAMO:
                tramos.append((ruta, round(it.GetLeftOffset() / float(fps), 3),
                               round((it.GetStart() - st) / float(fps), 3), round(dur, 3)))
    return tramos


def _golpes_numpy(ruta, src, dur):
    """Sin librosa (programa instalado): decodifica con ffmpeg y busca los golpes con el flujo espectral
    y el tempo por autocorrelacion. Menos fino que librosa, suficiente para cortar al ritmo."""
    import subprocess
    import numpy as np
    import rutas
    sr, hop, win = 11025, 256, 1024
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % src, "-t", "%.3f" % dur, "-i", ruta, "-ac", "1",
                        "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, timeout=600,
                       creationflags=rutas.SIN_VENTANA)
    y = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if len(y) < win * 4:
        return []
    n = 1 + (len(y) - win) // hop
    marcos = np.lib.stride_tricks.as_strided(y, (n, win), (y.strides[0] * hop, y.strides[0])) * np.hanning(win)
    esp = np.log1p(np.abs(np.fft.rfft(marcos, axis=1)) * 10)
    flujo = np.maximum(0, np.diff(esp, axis=0)).sum(axis=1)
    flujo = (flujo - flujo.mean()) / (flujo.std() + 1e-9)
    paso = hop / float(sr)
    flujo = np.convolve(flujo, np.hanning(5) / np.hanning(5).sum(), "same")
    # tempo: autocorrelacion con preferencia por ~120 bpm (como librosa)
    ac = np.correlate(flujo, flujo, "full")[len(flujo) - 1:]
    lags = np.arange(len(ac)) * paso
    bpm = np.where(lags > 0, 60.0 / np.maximum(lags, 1e-9), 0)
    peso = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1e-9) / 120.0) / 1.0) ** 2) * ((bpm >= 50) & (bpm <= 200))
    periodo = max(2, int(np.argmax(ac * peso)))
    # golpes: programacion dinamica de Ellis (2007), la misma idea que librosa.beat.beat_track
    n = len(flujo)
    puntaje = flujo.copy()
    previo = np.full(n, -1)
    ventana = np.arange(-2 * periodo, -periodo // 2 + 1)
    castigo = -100.0 * np.log(-ventana / float(periodo)) ** 2
    for i in range(n):
        idx = i + ventana
        ok = idx >= 0
        if ok.any():
            cand = puntaje[idx[ok]] + castigo[ok]
            j = int(np.argmax(cand))
            if cand[j] > 0:
                puntaje[i] += cand[j]
                previo[i] = idx[ok][j]
    i = int(np.argmax(puntaje[-2 * periodo:])) + n - 2 * periodo if n > 2 * periodo else int(np.argmax(puntaje))
    golpes = []
    while i >= 0:
        golpes.append(round((i + 1) * paso, 3))
        i = int(previo[i])
    return golpes[::-1]


def _bpm_propio(ruta):
    """El tempo con que se pidio una pista propia (recursos/musica/pistas.json: «<estilo>/<archivo>» -> bpm), o None."""
    import rutas
    raiz = os.path.join(rutas.RECURSOS, "musica")
    if not os.path.normcase(os.path.abspath(ruta)).startswith(os.path.normcase(raiz)):
        return None
    try:
        with open(os.path.join(raiz, "pistas.json"), encoding="utf-8") as f:
            tabla = json.load(f)
    except Exception:
        return None
    clave = "%s/%s" % (os.path.basename(os.path.dirname(ruta)), os.path.basename(ruta))
    return tabla.get(clave) or next((v for k, v in tabla.items() if k.endswith("*") and clave.startswith(k[:-1])), None)


def _golpes_rejilla(ruta, src, dur, bpm):
    """(17-nov, la persona: «en el de 1 minuto, al ritmo de la música») Golpes en REJILLA para las pistas propias, de las
    que se sabe el tempo: se afina el periodo (±5 %) y la fase doblando el flujo de ataques sobre el compas. El buscador
    general se equivocaba de tempo con el dembow (136 por minuto en una pista de 100) y los cortes caian fuera."""
    import subprocess
    import numpy as np
    import rutas
    sr, hop, win = 11025, 128, 1024
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % src, "-t", "%.3f" % dur, "-i", ruta, "-ac", "1",
                        "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, timeout=600,
                       creationflags=rutas.SIN_VENTANA)
    y = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if len(y) < win * 8:
        return []
    n = 1 + (len(y) - win) // hop
    marcos = np.lib.stride_tricks.as_strided(y, (n, win), (y.strides[0] * hop, y.strides[0])) * np.hanning(win)
    esp = np.log1p(np.abs(np.fft.rfft(marcos, axis=1)) * 10)
    flujo = np.maximum(0, np.diff(esp[:, :200], axis=0)).sum(axis=1)          # ataques, sobre todo graves y medios
    flujo = np.maximum(0, flujo - np.convolve(flujo, np.ones(43) / 43.0, "same"))
    paso = hop / float(sr)
    idx = np.arange(len(flujo))
    mejor = (0.0, 60.0 / bpm / paso, 0.0)
    for b in np.arange(bpm * 0.95, bpm * 1.05 + 1e-6, 0.05):
        p = 60.0 / b / paso                                                  # periodo en muestras del flujo
        dobl = np.bincount(((idx % p) / p * 48).astype(int) % 48, weights=flujo, minlength=48)
        dobl = dobl + 0.5 * (np.roll(dobl, 1) + np.roll(dobl, -1))
        k = int(np.argmax(dobl))
        if dobl[k] > mejor[0]:
            mejor = (float(dobl[k]), p, (k + 0.5) / 48.0 * p)
    _, p, fase = mejor
    return [round(float(t), 3) for t in (np.arange(fase, len(flujo), p) * paso + win / 2.0 / sr) if t < dur]


def golpes(tl, fps, base, log=print, tramos=None):
    """Frames de la timeline (desde 0) donde cae un golpe de musica. tramos: los de otra musica (musica_propia) en
    lugar de los de la linea."""
    tramos = tramos_musica(tl, fps) if tramos is None else tramos
    if not tramos:
        return []
    import rutas
    cache_ruta = os.path.join(rutas.ANALISIS, "ritmo.json")
    cache = {}
    for ruta_c in (os.path.join(rutas.RECURSOS, "ritmo_plantillas.json"), cache_ruta):   # el que trae el programa + el propio
        try:
            with open(ruta_c, encoding="utf-8") as f:
                for k, v in json.load(f).items():                    # claves viejas con ruta completa -> nombre
                    partes = k.split("|")
                    cache["|".join([os.path.basename(partes[0].replace("\\", "/"))] + partes[1:])] = v
        except Exception:
            pass
    tiempos = []
    nuevos = False
    for ruta, src, ini, dur in tramos:
        clave = "%s|%s|%s" % (os.path.basename(ruta), src, dur)
        bpm = _bpm_propio(ruta)
        if bpm:                                 # pista propia: clave con su estilo y tamaño (se llaman igual en cada uno)
            clave = "rejilla|%s/%s|%d|%s|%s" % (os.path.basename(os.path.dirname(ruta)), os.path.basename(ruta),
                                                os.path.getsize(ruta), src, dur)
            if clave not in cache:
                try:
                    cache[clave] = _golpes_rejilla(ruta, src, dur, float(bpm))
                    nuevos = True
                    log("Ritmo: %d golpes en rejilla (%s por minuto) en %s" % (len(cache[clave]), bpm,
                                                                               os.path.basename(ruta)[:40]))
                except Exception as ex:
                    log("Aviso: no se pudo poner en rejilla el ritmo de %s (%s)" % (os.path.basename(ruta), ex))
                    cache[clave] = []
        if clave not in cache:
            try:
                try:
                    import librosa
                    y, sr = librosa.load(ruta, sr=22050, mono=True, offset=src, duration=dur)
                    _, b = librosa.beat.beat_track(y=y, sr=sr, units="time")
                    cache[clave] = [round(float(x), 3) for x in b]
                except ImportError:
                    cache[clave] = _golpes_numpy(ruta, src, dur)
                nuevos = True
                log("Ritmo: %d golpes en %s" % (len(cache[clave]), os.path.basename(ruta)[:40]))
            except Exception as ex:
                log("Aviso: no se pudo analizar el ritmo de %s (%s)" % (os.path.basename(ruta), ex))
                cache[clave] = []
        tiempos += [ini + x for x in cache[clave] if x < dur]
    if nuevos:
        os.makedirs(os.path.dirname(cache_ruta), exist_ok=True)
        with open(cache_ruta, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    frames = []
    for t in sorted(tiempos):
        fr = int(round(t * fps))
        if not frames or fr - frames[-1] >= int(0.15 * fps):
            frames.append(fr)
    return frames
