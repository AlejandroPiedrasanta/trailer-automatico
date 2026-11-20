# -*- coding: utf-8 -*-
"""
persona_delante.py - El TITULO DETRAS DE LA PERSONA (lo que se hace a mano con la Mascara Magica), automatico y local.

(17-nov, la persona: «aplica Magic Mask para transiciones o captions») Como:
  1. Del tramo del titulo con el nombre se saca un video SIN textos ni overlays (se apagan esas pistas un momento y se
     renderiza solo ese tramo con los ajustes de entrega de siempre): es exactamente lo que se ve debajo del texto, ya
     con su color, su zoom y su estabilizado.
  2. recorte.py (modelo RVM, en el procesador) deja de ese video solo a la gente, con transparencia.
  3. Ese recorte va en una pista nueva, «PERSONA», ENCIMA del titulo: la persona tapa el texto y el texto queda detras.
Como el recorte sale de la misma imagen que tiene debajo, no hay diferencia de color ni de encuadre.

Solo se pone si en el centro del cuadro (donde va el texto) hay persona de verdad: entre el 4 % y el 70 %.
Estado «texto_detras» (Ajustes) o TRAILER_TEXTO_DETRAS=1. Si algo falla, el titulo queda como siempre.

    python PROGRAMA/armado/persona_delante.py        prueba: lo aplica a la linea abierta en DaVinci
"""
import os
import sys
import time

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nucleo"))
import rutas

PISTA = "PERSONA"
TITULOS = ("TEXTO NOMBRE",)                     # los titulos que van detras de la persona
EXT_MATERIAL = (".mp4", ".mov", ".mts", ".m4v", ".avi", ".mxf", ".jpg", ".jpeg")
MIN_CENTRO, MAX_CENTRO = 0.04, 0.70


def activo():
    if os.environ.get("TRAILER_TEXTO_DETRAS") is not None:
        return os.environ["TRAILER_TEXTO_DETRAS"] == "1"
    try:
        import motor
        return motor.leer_estado().get("texto_detras", True) is not False
    except Exception:
        return True


def carpeta():
    return os.path.join(rutas.BASE, "RECORTES")


def _es_vertical(it):
    """¿El clip es un video grabado en vertical? (nombre renombrado «VIDEO VERTICAL ...» o resolucion alto > ancho)"""
    try:
        m = it.GetMediaPoolItem()
        if m is None:
            return False
        if "VERTICAL" in (m.GetName() or "").upper():
            return True
        w, h = [int(x) for x in (m.GetClipProperty("Resolution") or "0x0").lower().split("x")[:2]]
        return h > w > 0
    except Exception:
        return False


def _es_material(it):
    try:
        m = it.GetMediaPoolItem()
        r = (m.GetClipProperty("File Path") or "") if m else ""
    except Exception:
        r = ""
    return bool(r) and r.lower().endswith(EXT_MATERIAL) and \
        not os.path.normcase(r).startswith(os.path.normcase(rutas.RECURSOS)) and \
        not os.path.normcase(r).startswith(os.path.normcase(carpeta()))


def _encender(resolve, tl, v, si):
    """Enciende o apaga una pista de video y COMPRUEBA que quedo asi. (17-nov, medido) En la pagina Entrega
    SetTrackEnable devuelve True y no hace nada: tras un render DaVinci queda ahi y las pistas de TEXTOS y LUZ se
    quedaban apagadas. Solo funciona en Edicion."""
    for _ in range(4):
        try:
            if resolve.GetCurrentPage() != "edit":
                resolve.OpenPage("edit")
                time.sleep(0.8)
            tl.SetTrackEnable("video", v, bool(si))
            time.sleep(0.2)
            if bool(tl.GetIsTrackEnabled("video", v)) == bool(si):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _render_tramo(project, tl, a, b, nombre, log):
    """Renderiza los cuadros [a, b) de la linea (absolutos) a RECORTES/<nombre>.*; devuelve la ruta o None."""
    d = carpeta()
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.startswith(nombre + "."):
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
    project.SetRenderSettings({"SelectAllFrames": False, "MarkIn": a, "MarkOut": b - 1, "TargetDir": d,
                               "CustomName": nombre})
    job = project.AddRenderJob()
    if not job:
        return None
    try:
        if not project.StartRendering([job], False):
            return None
        t0 = time.time()
        while project.IsRenderingInProgress() and time.time() - t0 < 600:
            time.sleep(0.5)
        if project.IsRenderingInProgress():
            project.StopRendering()
            return None
    finally:
        try:
            project.DeleteRenderJob(job)
        except Exception:
            pass
    return next((os.path.join(d, f) for f in os.listdir(d) if f.startswith(nombre + ".")), None)


def _gris(video, t, extra=""):
    """Un cuadro de `video` en el segundo t, 480x270 en gris (numpy), o None."""
    import subprocess
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", video, "-frames:v", "1", "-vf",
                        extra + "scale=480:270,format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=120,
                       creationflags=rutas.SIN_VENTANA)
    return np.frombuffer(r.stdout, np.uint8).reshape(270, 480).astype(np.float32) if len(r.stdout) == 480 * 270 else None


def tapado(con_texto, sin_texto, persona, dur_s):
    """Que parte de las LETRAS queda tapada por la persona (0-1), mirando 3 cuadros: las letras son lo que cambia entre
    el tramo con texto y sin texto; la persona, el alfa del recorte. None si no se pudo medir."""
    partes = []
    for t in (dur_s * 0.35, dur_s * 0.5, dur_s * 0.65):
        a, b, p = _gris(con_texto, t), _gris(sin_texto, t), _gris(persona, t, "alphaextract,")
        if a is None or b is None or p is None:
            continue
        letras = (a - b) > 55.0                      # las letras son claras: mucho mas luz que sin ellas
        if letras.sum() < 150:                       # casi no hay letras en ese cuadro (el titulo esta entrando)
            continue
        partes.append(float((p[letras] > 128).mean()))
    return sum(partes) / len(partes) if partes else None


def tapado_previo(con_texto, sin_texto, dur_s):
    """Lo mismo que tapado() pero sin el recorte entero: el alfa de la gente sale de recorte.alfas en esos 3 cuadros.
    (19-nov) El tramo entero se recortaba (~5 cuadros/s) y luego casi siempre se descartaba: asi solo se recorta lo
    que se va a poner."""
    import numpy as np
    from PIL import Image
    import recorte
    ts = (dur_s * 0.35, dur_s * 0.5, dur_s * 0.65)
    alfa = recorte.alfas(sin_texto, ts)
    partes = []
    for t in ts:
        a, b, p = _gris(con_texto, t), _gris(sin_texto, t), alfa.get(t)
        if a is None or b is None or p is None:
            continue
        p = np.asarray(Image.fromarray((p * 255).astype(np.uint8)).resize((480, 270), Image.BILINEAR), np.float32)
        letras = (a - b) > 55.0
        if letras.sum() < 150:
            continue
        partes.append(float((p[letras] > 128).mean()))
    return sum(partes) / len(partes) if partes else None


MIN_TAPADO = 0.10                            # (17-nov) con casi todo tapado el nombre no se leia: asi no se pone
# visto con el 57 %: «Adriana Raquel» no se leia; (18-nov, boda) «Cindy & Dereck» con ~40 % tampoco: 30 %
MAX_TAPADO = float(os.environ.get("TRAILER_TEXTO_DETRAS_MAX", 0.30))


def aplicar(resolve, project, tl, mp, carpeta_mp, log=print):
    """Pone a la persona delante de los titulos de TITULOS en la linea `tl` (activa). Devuelve cuantos."""
    import recorte
    if not recorte.disponible():
        return 0
    st = tl.GetStartFrame()
    titulos, n_v = [], tl.GetTrackCount("video")
    for v in range(1, n_v + 1):
        for it in tl.GetItemListInTrack("video", v) or []:
            if (it.GetName() or "").upper().startswith(TITULOS):
                titulos.append((it.GetStart(), it.GetEnd()))
    if not titulos:
        return 0
    hechos = 0
    limpio = "".join(c if c.isalnum() else "_" for c in tl.GetName())[:60]
    try:
        horizontal = int(tl.GetSetting("timelineResolutionWidth") or 16) >= int(tl.GetSetting("timelineResolutionHeight") or 9)
    except Exception:
        horizontal = True
    for k, (a, b) in enumerate(sorted(set(titulos))):
        medio = (a + b) // 2
        # (18-nov, boda) en el horizontal una toma VERTICAL va entera al centro con fondo desenfocado: el recorte agarra
        # tambien las siluetas borrosas de los lados y tapa las letras a trozos. Ahi el titulo queda normal.
        bajo = [it for v in range(1, n_v + 1) for it in tl.GetItemListInTrack("video", v) or []
                if it.GetStart() <= medio < it.GetEnd() and _es_material(it)]
        if horizontal and any(_es_vertical(it) for it in bajo):
            log("  texto detrás: debajo hay una toma vertical con fondo desenfocado; el título queda normal.")
            continue
        apagadas = []
        pista_p = next((t for t in range(1, n_v + 1)
                        if (tl.GetTrackName("video", t) or "").strip().upper() == PISTA), None)
        if pista_p is not None:                              # de una pasada anterior: fuera, para medir limpio
            viejos = [it for it in tl.GetItemListInTrack("video", pista_p) or [] if it.GetStart() < b and it.GetEnd() > a]
            if viejos:
                tl.DeleteClips(viejos, False)
        con_texto = _render_tramo(project, tl, a, b, "%s_contexto_%d" % (limpio, k), log)
        try:
            for v in range(1, n_v + 1):                      # solo queda encendido el material del evento
                if not tl.GetIsTrackEnabled("video", v):
                    continue
                encima = [it for it in tl.GetItemListInTrack("video", v) or [] if it.GetStart() < b and it.GetEnd() > a]
                if (tl.GetTrackName("video", v) or "").strip().upper() == PISTA or \
                        not any(_es_material(it) for it in encima if it.GetStart() <= medio < it.GetEnd()):
                    if encima or (tl.GetTrackName("video", v) or "").strip().upper() == PISTA:
                        if _encender(resolve, tl, v, False):
                            apagadas.append(v)
            crudo = _render_tramo(project, tl, a, b, "%s_sintexto_%d" % (limpio, k), log) if apagadas else None
        finally:
            for v in apagadas:
                if not _encender(resolve, tl, v, True):
                    log("AVISO: la pista %d (%s) quedó apagada en DaVinci: enciéndela a mano." % (
                        v, tl.GetTrackName("video", v)))
        if not crudo:
            log("  texto detrás: DaVinci no pudo sacar el tramo del título.")
            continue
        salida = os.path.join(carpeta(), "%s_persona_%d.mov" % (limpio, k))
        try:                                                 # (19-nov) se mide ANTES y solo se recorta si se pone
            fps_l = float(tl.GetSetting("timelineFrameRate") or 24)
        except Exception:
            fps_l = 24.0
        try:
            parte = tapado_previo(con_texto, crudo, (b - a) / fps_l) if con_texto else None
        except Exception as e:
            log("  texto detrás: no se pudo medir (%s)." % e)
            parte = None
        r = recorte.recortar(crudo, salida, 0.0, None, log) \
            if parte is not None and MIN_TAPADO <= parte <= MAX_TAPADO else None
        for sobra in (crudo, con_texto):
            try:
                os.remove(sobra)
            except (OSError, TypeError):
                pass
        if not r or parte is None or not (MIN_TAPADO <= parte <= MAX_TAPADO):
            log("  texto detrás: %s; el título queda normal." % (
                "no se pudo medir" if parte is None else
                "no se pudo recortar a la persona" if MIN_TAPADO <= parte <= MAX_TAPADO else
                "la persona taparía el %.0f %% de las letras (solo se pone entre el %d y el %d %%)"
                % (100 * parte, 100 * MIN_TAPADO, 100 * MAX_TAPADO)))
            try:
                os.remove(salida)
            except OSError:
                pass
            continue
        mp.SetCurrentFolder(carpeta_mp)
        clips = mp.ImportMedia([salida]) or []
        if not clips:
            continue
        pista = next((t for t in range(1, tl.GetTrackCount("video") + 1)
                      if (tl.GetTrackName("video", t) or "").strip().upper() == PISTA), None)
        if pista is None:
            if not tl.AddTrack("video"):
                continue
            pista = tl.GetTrackCount("video")
            tl.SetTrackName("video", pista, PISTA)
        for viejo in [it for it in tl.GetItemListInTrack("video", pista) or [] if it.GetStart() < b and it.GetEnd() > a]:
            tl.DeleteClips([viejo], False)
        nuevo = mp.AppendToTimeline([{"mediaPoolItem": clips[0], "startFrame": 0, "endFrame": b - a, "mediaType": 1,
                                      "trackIndex": pista, "recordFrame": a}]) or []
        if nuevo:
            hechos += 1
            log("Texto detrás de la persona en %.1f s (%d cuadros recortados, %.0f %% del centro es persona)."
                % ((a - st) / float(r["fps"] or 24), r["cuadros"], 100 * r["centro"]))
    return hechos


if __name__ == "__main__":
    import motor
    r = motor._dvr().scriptapp("Resolve")
    p = r.GetProjectManager().GetCurrentProject()
    mp = p.GetMediaPool()
    tl = p.GetCurrentTimeline()
    print("linea:", tl.GetName())
    raiz = mp.GetRootFolder()
    efe = next((f for f in raiz.GetSubFolderList() or [] if "EFECTOS" in f.GetName()), raiz)
    dest = next((f for f in efe.GetSubFolderList() or [] if f.GetName() == "RECORTES"), None) or mp.AddSubFolder(efe, "RECORTES")
    print("hechos:", aplicar(r, p, tl, mp, dest))
