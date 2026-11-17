# -*- coding: utf-8 -*-
"""
crear_estructura.py - PASO 1 de 2. Deja listas las 4 timelines del TRAILER DE XV (sin videos):
  1 min, 3 min, 15 min y 30 min.
  - Duplica la plantilla (intro, titulos, efectos y SFX de la intro se conservan).
  - Renombra pistas, arma musica por actos y SFX por version, marcadores de cada acto,
    textos placeholder (Text+) y grupo de color con LUT (apagado, solo activar).
  - Deja V1 (VIDEOS) y V2 (FOTOS INTRO) vacias: las llena build_trailers.py (PASO 2).
  - La plantilla y las timelines originales NO se tocan.

Se ejecuta DENTRO de Resolve (MCP: run_script_unsafe) con las variables opcionales:
    SOLO = [0]            # indices de VERSIONES a construir (por defecto todas)
    REHACER = True        # borra y reconstruye si la timeline ya existe
                          # (OJO: se pierden los videos y fotos ya colocados; vuelve a correr el PASO 2)
"""

TEMPLATE = "TRAILER XV 4 - Dua Lipa"
INTRO_FIN_SEG = 15.0           # el audio de la intro (0 a 15 s) se conserva tal cual
FPS_DEF = 24

# Pistas: A2 y A3 musica (se alternan para cruzar), A5 chispa/riser, A6 campanas/gritos,
# A7 whoosh, A8 publico, A9 publico 2.
NOMBRES_V = ["VIDEOS", "FOTOS INTRO", "TEXTOS", "AJUSTE", "TITULOS", "EFECTOS", "EXTRA 1", "EXTRA 2"]
NOMBRES_A = ["VOZ NATURAL", "MUSICA 1", "MUSICA 2 (cruce)", "MUSICA INTRO", "SFX CHISPA",
             "SFX CAMPANAS Y GRITOS", "SFX WHOOSH", "SFX PUBLICO", "SFX PUBLICO 2", "EXTRA AUDIO 1", "EXTRA AUDIO 2"]

# claves de busqueda en el media pool
K = {"woosh": "50 overcrowed", "campanas": "campanas", "chispa": "chispa", "cbig": "cheer_big",
     "cflow": "cheer_flowers", "cshort": "cheer_short", "csic": "cheer_sicilian",
     "cpar": "cheer_couple", "aplauso": "2496 sfx", "grito": "grito",
     "forza": "forza", "perfect": "perfect (wedding", "nocrezcas": "no crezcas", "pacto": "un pacto",
     "yote": "yo te extra", "mix": "mix variado", "dua": "dua lipa"}

# (pista, clave, seg_origen, t_ini, t_fin, vol_dB, fade_in_s, fade_out_s)
# SFX: (clave, pista, t, largo_seg|None, vol_dB)
V30 = {
    "nombre": "TRAILER XV - 30s", "seg": 30, "lut": "XV_30s_FIESTA_VIBRANTE.cube", "grupo": "XV 30s - COLOR",
    "look": "LOOK FIESTA VIBRANTE",
    "actos": [(15, "ACTO 2 - FIESTA", "Blue")],
    "musica": [(2, "dua", 10, 14.0, 30.0, -6, 1.0, 2.0)],
    "sfx": [("woosh", 7, 14.3, 2.5, 0), ("cshort", 8, 18.0, None, -7), ("chispa", 5, 20.0, 6.0, 3),
            ("cbig", 9, 24.0, 4.0, -7), ("aplauso", 8, 26.5, 3.5, -7)],
}
V60 = {
    "nombre": "TRAILER XV - 1min", "seg": 60, "lut": "XV_1min_CINE_TEAL_ORANGE.cube", "grupo": "XV 1min - COLOR",
    "look": "LOOK CINE TEAL ORANGE",
    "actos": [(15, "ACTO 2 - ROMANTICA", "Pink"), (38, "ACTO 3 - FIESTA", "Blue")],
    "musica": [(2, "perfect", 30, 14.0, 39.0, -4, 1.0, 1.5), (3, "mix", 600, 37.0, 60.0, -6, 2.0, 2.0)],
    "sfx": [("woosh", 7, 14.3, 2.5, 0), ("campanas", 6, 17.0, 3.25, -6), ("woosh", 7, 37.3, 2.5, 0),
            ("chispa", 5, 40.0, 8.0, 3), ("cflow", 9, 42.0, None, -7), ("cshort", 8, 50.0, None, -7),
            ("cbig", 9, 52.5, 4.0, -7), ("aplauso", 8, 55.5, 4.5, -7), ("grito", 6, 57.0, 3.0, -12)],
}
V180 = {
    "nombre": "TRAILER XV - 3min", "seg": 180, "lut": "XV_3min_ROMANTICO_CALIDO.cube", "grupo": "XV 3min - COLOR",
    "look": "LOOK ROMANTICO CALIDO",
    "actos": [(15, "ACTO 2 - EPICA Y CEREMONIA", "Cyan"), (55, "ACTO 3 - ROMANTICA", "Pink"),
              (115, "ACTO 4 - FIESTA", "Blue")],
    "musica": [(2, "forza", 60, 14.0, 56.0, -4, 1.0, 2.0), (3, "yote", 0, 54.0, 117.0, -4, 2.0, 2.0),
               (2, "mix", 1500, 115.0, 180.0, -6, 2.0, 3.0)],
    "sfx": [("woosh", 7, 14.3, 2.5, 0), ("campanas", 6, 17.0, 3.25, -6), ("woosh", 7, 54.3, 2.5, 0),
            ("cflow", 9, 70.0, None, -7), ("woosh", 7, 114.3, 2.5, 0), ("cpar", 8, 118.0, None, -7),
            ("chispa", 5, 120.0, 8.0, 3), ("cbig", 9, 136.0, None, -7), ("cshort", 8, 148.0, None, -7),
            ("csic", 9, 152.0, None, -7), ("aplauso", 8, 168.0, None, -7), ("grito", 6, 170.0, 4.0, -12)],
}


def _v1800():
    sfx = [("woosh", 7, 14.3, 2.5, 0), ("campanas", 6, 17.0, 3.25, -6), ("woosh", 7, 299.0, 2.5, 0),
           ("cflow", 9, 560.0, None, -7), ("cflow", 9, 800.0, None, -7), ("cflow", 9, 1065.0, None, -7),
           ("woosh", 7, 1423.5, 2.5, 0), ("cpar", 8, 1427.0, None, -7), ("chispa", 5, 1430.0, 8.0, 3)]
    ciclo = [("cbig", 9), ("cshort", 8), ("aplauso", 8), ("cflow", 9), ("csic", 9), ("cshort", 8)]
    t, i = 1445.0, 0
    while t < 1780.0:
        k, p = ciclo[i % len(ciclo)]
        sfx.append((k, p, t, None, -7 if k != "aplauso" else -9))
        t += 28.0
        i += 1
    sfx += [("aplauso", 8, 1789.0, None, -7), ("grito", 6, 1794.0, 5.0, -12)]
    return {
        "nombre": "TRAILER XV - 30min", "seg": 1800, "lut": "XV_30min_NATURAL_SUAVE.cube",
        "grupo": "XV 30min - COLOR", "look": "LOOK NATURAL SUAVE",
        "actos": [(15, "ACTO 2 - EPICA Y LLEGADA", "Cyan"), (300, "ACTO 3 - CEREMONIA Y ROMANTICA", "Pink"),
                  (1425, "ACTO 4 - FIESTA", "Blue")],
        "musica": [(2, "forza", 0, 14.0, 300.0, -4, 1.0, 2.0),
                   (3, "nocrezcas", 0, 298.0, 553.0, -4, 2.0, 2.0),
                   (2, "pacto", 0, 551.0, 795.0, -4, 2.0, 2.0),
                   (3, "yote", 0, 793.0, 1061.0, -4, 2.0, 2.0),
                   (2, "perfect", 0, 1059.0, 1425.0, -4, 2.0, 2.0),
                   (3, "mix", 2100, 1423.0, 1800.0, -6, 2.0, 3.0)],
        "sfx": sfx,
    }


def _v900():
    sfx = [("woosh", 7, 14.3, 2.5, 0), ("campanas", 6, 17.0, 3.25, -6), ("woosh", 7, 149.3, 2.5, 0),
           ("cflow", 9, 280.0, None, -7), ("cflow", 9, 400.0, None, -7), ("cflow", 9, 530.0, None, -7),
           ("woosh", 7, 711.3, 2.5, 0), ("cpar", 8, 714.0, None, -7), ("chispa", 5, 716.0, 8.0, 3)]
    ciclo = [("cbig", 9), ("cshort", 8), ("aplauso", 8), ("cflow", 9), ("csic", 9), ("cshort", 8)]
    t, i = 725.0, 0
    while t < 880.0:
        k, p = ciclo[i % len(ciclo)]
        sfx.append((k, p, t, None, -7 if k != "aplauso" else -9))
        t += 25.0
        i += 1
    sfx += [("aplauso", 8, 889.0, None, -7), ("grito", 6, 894.0, 5.0, -12)]
    return {
        "nombre": "TRAILER XV - 15min", "seg": 900, "lut": "XV_15min_FILM_KODAK.cube",
        "grupo": "XV 15min - COLOR", "look": "LOOK FILM KODAK 2383",
        "actos": [(15, "ACTO 2 - EPICA Y LLEGADA", "Cyan"), (150, "ACTO 3 - CEREMONIA Y ROMANTICA", "Pink"),
                  (712, "ACTO 4 - FIESTA", "Blue")],
        "musica": [(2, "forza", 0, 14.0, 152.0, -4, 1.0, 2.0),
                   (3, "nocrezcas", 0, 150.0, 280.0, -4, 2.0, 2.0),
                   (2, "pacto", 0, 278.0, 402.0, -4, 2.0, 2.0),
                   (3, "yote", 0, 400.0, 530.0, -4, 2.0, 2.0),
                   (2, "perfect", 0, 528.0, 714.0, -4, 2.0, 2.0),
                   (3, "mix", 1000, 712.0, 900.0, -6, 2.0, 3.0)],
        "sfx": sfx,
    }


# V30 (30 s) queda disponible: agregala a la lista si se necesita esa version.
VERSIONES = [V60, V180, _v900(), _v1800()]
# ====================================================================

try:
    resolve
except NameError:
    import DaVinciResolveScript as _dvr
    resolve = _dvr.scriptapp("Resolve")
try:
    SOLO
except NameError:
    SOLO = list(range(len(VERSIONES)))
try:
    REHACER
except NameError:
    REHACER = False

project = resolve.GetProjectManager().GetCurrentProject()
mp = project.GetMediaPool() if project else None
root = mp.GetRootFolder() if mp else None
reporte = {}


def todas_las_timelines():
    return [project.GetTimelineByIndex(i) for i in range(1, project.GetTimelineCount() + 1)]


def hallar_timeline(nombre):
    for t in todas_las_timelines():
        if t.GetName() == nombre:
            return t
    return None


_cache = {}


def buscar_audio(clave):
    clave = clave.lower()
    if clave in _cache:
        return _cache[clave]
    hallados = []

    def rec(f):
        for c in f.GetClipList() or []:
            ruta = (c.GetClipProperty("File Path") or "").lower()
            if ruta.endswith((".mp3", ".wav", ".m4a", ".flac", ".aac")) and clave in c.GetName().lower():
                hallados.append(c)
        for s in f.GetSubFolderList() or []:
            rec(s)
    rec(root)
    _cache[clave] = hallados[0] if hallados else None
    return _cache[clave]


def construir(spec, issues):
    nombre = spec["nombre"]
    T = spec["seg"]
    existente = hallar_timeline(nombre)
    if existente:
        if not REHACER:
            issues.append("Ya existe %s; no se toca (usa REHACER = True para rehacerla)." % nombre)
            return None
        mp.DeleteTimelines([existente])
    tpl = hallar_timeline(TEMPLATE)
    if tpl is None:
        issues.append("No encuentro la plantilla %s" % TEMPLATE)
        return None
    sec = [f for f in root.GetSubFolderList() or [] if f.GetName().split(" ", 1)[-1] in ("PLANTILLAS", "SECUENCIAS")]
    mp.SetCurrentFolder(sec[0] if sec else root)
    tl = tpl.DuplicateTimeline(nombre)
    if not tl:
        issues.append("No se pudo duplicar la plantilla para %s" % nombre)
        return None
    project.SetCurrentTimeline(tl)
    try:
        fps = int(round(float(tl.GetSetting("timelineFrameRate"))))
    except Exception:
        fps = FPS_DEF
    st = tl.GetStartFrame()

    def F(t):
        return st + int(round(t * fps))

    # ---- pistas: desbloquear, activar y nombrar ----
    nv, na = tl.GetTrackCount("video"), tl.GetTrackCount("audio")
    for t in range(1, nv + 1):
        tl.SetTrackLock("video", t, False)
        tl.SetTrackEnable("video", t, True)
        if t <= len(NOMBRES_V):
            tl.SetTrackName("video", t, NOMBRES_V[t - 1])
    for t in range(1, na + 1):
        tl.SetTrackLock("audio", t, False)
        tl.SetTrackEnable("audio", t, True)
        if t <= len(NOMBRES_A):
            tl.SetTrackName("audio", t, NOMBRES_A[t - 1])

    # ---- limpiar: video 1-3 y todo el audio posterior a la intro ----
    for t in (1, 2, 3):
        its = tl.GetItemListInTrack("video", t) or []
        if its:
            tl.DeleteClips(its, False)
    limite = F(INTRO_FIN_SEG)
    ultimo_intro = None
    for t in range(1, na + 1):
        borrar = []
        for it in tl.GetItemListInTrack("audio", t) or []:
            if it.GetEnd() > limite:
                borrar.append(it)
            elif t == 4 and (ultimo_intro is None or it.GetEnd() > ultimo_intro.GetEnd()):
                ultimo_intro = it
        if borrar:
            tl.DeleteClips(borrar, False)
    if ultimo_intro is not None:
        ultimo_intro.SetFades({"FadeOut": fps})     # cierra la musica de la intro con 1 s de fade

    # ---- textos placeholder (Text+) en la pista TEXTOS ----
    # IMPORTANTE: InsertFusionTitleIntoTimeline es una edicion tipo "insertar" y desplaza todas las
    # pistas desbloqueadas; por eso se bloquea todo menos V1 mientras se inserta, y se hace ANTES del audio.
    textos = []
    for k, (t0, etiqueta, _c) in enumerate(spec["actos"]):
        textos.append((t0 + 1.0, "TEXTO NOMBRE XV" if k == 0 else "TEXTO " + etiqueta.split(" - ")[0]))
    textos.append((max(T - 7.0, 16.0), "TEXTO FINAL - FECHA Y LUGAR"))
    n_txt = 0
    for (t, etiqueta) in textos:
        try:
            for tr in range(1, nv + 1):
                tl.SetTrackLock("video", tr, tr != 1)
            for tr in range(1, na + 1):
                tl.SetTrackLock("audio", tr, True)
            tl.SetCurrentTimecode(_tc(st, t, fps))
            it = tl.InsertFusionTitleIntoTimeline("Text+")
            tl.SetTrackLock("video", 3, False)
            if not it:
                issues.append("%s: no se pudo insertar el texto %s" % (nombre, etiqueta))
                continue
            it.SetPosition({"trackIndex": 3, "startFrame": F(t)})
            exceso = int(it.GetDuration()) - int(3.0 * fps)
            if exceso > 0:
                it.SetRightOffset(exceso)
            it.SetName(etiqueta)
            try:
                comp = it.GetFusionCompByIndex(1)
                herr = comp.FindTool("Template") if comp else None
                if herr:
                    herr.SetInput("StyledText", etiqueta)
            except Exception:
                pass
            n_txt += 1
        except Exception as ex:
            issues.append("%s: texto %s fallo (%s)" % (nombre, etiqueta, str(ex)[:60]))
        finally:
            for tr in range(1, nv + 1):
                tl.SetTrackLock("video", tr, False)
            for tr in range(1, na + 1):
                tl.SetTrackLock("audio", tr, False)

    # ---- musica por actos ----
    n_mus = 0
    for (pista, clave, src, a, b, vol, fi, fo) in spec["musica"]:
        clip = buscar_audio(K[clave])
        if clip is None:
            issues.append("%s: falta la cancion '%s' en el media pool" % (nombre, clave))
            continue
        b = min(b, T)
        tramo_f = int((b - a) * fps)
        largo_f = _frames(clip.GetClipProperty("Duration"), fps)
        ini_f = int(src * fps)
        if ini_f + tramo_f > largo_f:     # la cancion no alcanza desde ese punto: se adelanta el inicio
            ini_f = max(0, largo_f - tramo_f)
        fin_f = min(largo_f, ini_f + tramo_f) - 1
        if fin_f - ini_f + 1 < tramo_f:
            issues.append("%s: '%s' dura menos que el tramo %s-%s s; queda un hueco de musica" % (nombre, clave, a, b))
        r = mp.AppendToTimeline([{"mediaPoolItem": clip, "startFrame": ini_f, "endFrame": fin_f,
                                  "mediaType": 2, "trackIndex": pista, "recordFrame": F(a)}])
        if r:
            r[0].SetProperties({"AudioVolume": float(vol)})
            r[0].SetFades({"FadeIn": int(fi * fps), "FadeOut": int(fo * fps)})
            n_mus += 1
        else:
            issues.append("%s: no se pudo colocar %s (%s-%s s)" % (nombre, clave, a, b))

    # ---- SFX ----
    n_sfx = 0
    for (clave, pista, t, largo, vol) in spec["sfx"]:
        if t >= T:
            continue
        clip = buscar_audio(K[clave])
        if clip is None:
            issues.append("%s: falta el SFX '%s'" % (nombre, clave))
            continue
        total_f = _frames(clip.GetClipProperty("Duration"), fps)
        dur_f = total_f if largo is None else min(total_f, int(largo * fps))
        dur_f = min(dur_f, int((T - t) * fps))
        if dur_f < 2:
            continue
        r = mp.AppendToTimeline([{"mediaPoolItem": clip, "startFrame": 0, "endFrame": dur_f - 1,
                                  "mediaType": 2, "trackIndex": pista, "recordFrame": F(t)}])
        if r:
            r[0].SetProperties({"AudioVolume": float(vol)})
            r[0].SetFades({"FadeOut": min(dur_f // 3, int(0.5 * fps))})
            n_sfx += 1
        else:
            issues.append("%s: no se pudo colocar el SFX %s en %s s" % (nombre, clave, t))

    # ---- marcadores de actos ----
    n_mar = 0
    marcas = [(0, "INTRO", "Yellow", "FOTOS en V2 (0 a 5 s) y titulos/efectos de la plantilla.", int(5 * fps)),
              (int(5.6 * fps), "FIN INTRO", "Yellow", "Aqui termina la intro; empieza el montaje de VIDEOS en V1.", 1)]
    for (t0, etiqueta, color) in [(a, b, c) for (a, b, c) in spec["actos"]]:
        marcas.append((int(t0 * fps), etiqueta, color, "Videos de este acto en V1 (musica y SFX ya colocados).", 1))
    marcas.append((int((T - 6) * fps), "CIERRE", "Red", "Ultimos segundos: plano final y texto de cierre.", int(6 * fps) - 1))
    for (f, etiqueta, color, nota, dur) in marcas:
        if tl.AddMarker(f, color, etiqueta, nota, dur):
            n_mar += 1

    tl.SetMarkInOut(st, st + int(T * fps) - 1, "all")
    reporte_v = {"timeline": nombre, "musica": n_mus, "sfx": n_sfx, "textos": n_txt, "marcadores": n_mar}
    return reporte_v


def _frames(tc, fps):
    """Convierte la propiedad Duration (HH:MM:SS:FF) en frames."""
    try:
        h, m, s, f = [int(x) for x in str(tc).replace(";", ":").split(":")]
        return ((h * 60 + m) * 60 + s) * fps + f
    except Exception:
        return 10 ** 6


def _tc(st, t, fps):
    total = int(round(t * fps))
    base = int(st)
    f = base + total
    hh = f // (3600 * fps)
    mm = (f // (60 * fps)) % 60
    ss = (f // fps) % 60
    ff = f % fps
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)


def color_grupo(spec, issues):
    grupo = None
    for g in project.GetColorGroupsList() or []:
        if g.GetName() == spec["grupo"]:
            grupo = g
    if grupo is None:
        grupo = project.AddColorGroup(spec["grupo"])
    if grupo is None:
        issues.append("No se pudo crear el grupo de color %s" % spec["grupo"])
        return False
    resolve.OpenPage("color")
    pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
    ok = True
    if pre and pre.GetNumNodes() >= 1:
        pre.SetNodeLabel(1, "BASE - correccion previa")
        pre.SetNodeEnabled(1, False)
    if post and post.GetNumNodes() >= 1:
        ok = post.SetLUT(1, "MCP/" + spec["lut"])
        post.SetNodeLabel(1, spec["look"])
        post.SetNodeEnabled(1, False)
    else:
        ok = False
    resolve.OpenPage("edit")
    if not ok:
        issues.append("%s: no se pudo aplicar el LUT al grupo %s" % (spec["nombre"], spec["grupo"]))
    return ok


def main():
    if project is None:
        reporte["error"] = "No hay proyecto abierto"
        return
    for idx in SOLO:
        spec = VERSIONES[idx]
        issues = []
        r = construir(spec, issues)
        if r is not None:
            r["color_grupo"] = color_grupo(spec, issues)
        reporte[spec["nombre"]] = {"resumen": r, "avisos": issues}
    resolve.OpenPage("edit")


main()
result = reporte
