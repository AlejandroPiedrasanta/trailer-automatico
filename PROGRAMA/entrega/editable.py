# -*- coding: utf-8 -*-
"""
editable.py - (1.5.7) Al entregar los videos, el evento queda listo para editar a mano con fluidez:

La persona (2026-11-16): «cuando abro una plantilla ahí están todas las demás plantillas o líneas de tiempo, es muy
confuso: si abro la plantilla solo me tiene que dar esa línea de tiempo»; «cuando termine y me entregue los videos, haz los
videos en proxy para que pese menos y aplica los render caches, así cuando edite algo en alguna plantilla ya tiene los
videos en proxies y es fluida la reproducción».

1. PROXIES: DaVinci no los genera desde la API (solo los enlaza: MediaPoolItem.LinkProxyMedia). Se hacen con ffmpeg y la GPU
   (NVENC en NVIDIA, VideoToolbox en Mac; si no, x264 rapido): H.264 de 540 de alto, mismo fps y duracion, POR DENTRO
   (rutas.BASE/PROXIES, nada a la vista). Se enlazan a cada clip del evento.
2. CACHE: el proyecto usa los proxies cuando hay (perfProxyMediaMode = 1) y la cache de render en modo inteligente y
   automatica (perfRenderCacheMode = smart, perfAutoRenderCacheEnable = 1).
3. UN PROYECTO POR VIDEO: «EVENTO TERMINADO - <evento>/PLANTILLAS DE LOS VIDEOS/VIDEO FINAL 1 MIN.drp»: un proyecto de
   DaVinci con SOLO esa linea de tiempo y solo los clips que usa (con sus proxies y la cache). Se hace exportando el
   proyecto, importandolo con otro nombre en la carpeta <evento> de la base, borrando lo demas y exportandolo. Al abrir el
   .drp, DaVinci trae solo ese video para corregirlo.
"""
import os
import time
import hashlib
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import rutas

ALTO_PROXY = 540
PARALELO = 3
EXT_VIDEO = (".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi", ".mkv", ".m4v")


def _codificador():
    """El codificador H.264 por GPU que haya (NVENC / VideoToolbox / AMF / QSV), o x264."""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30,
                           creationflags=rutas.SIN_VENTANA)
        hay = r.stdout
    except Exception:
        hay = ""
    for c, extra in (("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "26", "-b:v", "0"]),
                     ("h264_videotoolbox", ["-b:v", "6M"]),
                     ("h264_amf", ["-quality", "speed", "-b:v", "6M"]),
                     ("h264_qsv", ["-preset", "veryfast", "-b:v", "6M"])):
        if c in hay:
            return c, extra
    return "libx264", ["-preset", "veryfast", "-crf", "24"]


def carpeta_proxies():
    return os.path.join(rutas.BASE, "PROXIES")


def ruta_proxy(original):
    """El proxy de un archivo: por dentro, con un nombre unico (ruta + tamano), extension .mov."""
    try:
        tam = os.path.getsize(original)
    except OSError:
        tam = 0
    h = hashlib.sha1(("%s|%d" % (os.path.normcase(os.path.abspath(original)), tam)).encode("utf-8")).hexdigest()[:12]
    base = os.path.splitext(os.path.basename(original))[0][:60]
    return os.path.join(carpeta_proxies(), "%s_%s_proxy.mov" % (base, h))


def hacer_proxy(original, log=print, codificador=None):
    """Hace el proxy (si no esta hecho). Devuelve su ruta o None."""
    destino = ruta_proxy(original)
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return destino
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    c, extra = codificador or _codificador()
    tmp = destino + ".tmp.mov"
    orden = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", original, "-map", "0:v:0", "-map", "0:a?",
             "-vf", "scale=-2:%d" % ALTO_PROXY, "-c:v", c] + extra + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                                                                       "-movflags", "+faststart", tmp]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=7200, creationflags=rutas.SIN_VENTANA)
        if r.returncode != 0 and c != "libx264":         # la GPU no pudo (formato raro): con el procesador
            orden[orden.index(c)] = "libx264"
            r = subprocess.run(orden, capture_output=True, text=True, timeout=7200, creationflags=rutas.SIN_VENTANA)
        if r.returncode != 0 or not os.path.exists(tmp):
            log("Aviso: no se pudo hacer el proxy de %s (%s)" % (os.path.basename(original), (r.stderr or "")[-120:]))
            return None
        os.replace(tmp, destino)
        return destino
    except Exception as ex:
        log("Aviso: no se pudo hacer el proxy de %s (%s)" % (os.path.basename(original), ex))
        return None


def _clips(carpeta):
    out = list(carpeta.GetClipList() or [])
    for s in carpeta.GetSubFolderList() or []:
        out += _clips(s)
    return out


def proxies_y_cache(project, log=print):
    """Proxies de todos los videos del media pool que vienen del evento (o del material), enlazados, y la cache de
    render del proyecto. Devuelve cuantos proxies quedaron enlazados."""
    mp = project.GetMediaPool()
    videos = {}
    for c in _clips(mp.GetRootFolder()):
        try:
            r = c.GetClipProperty("File Path") or ""
            tipo = (c.GetClipProperty("Type") or "").lower()
        except Exception:
            continue
        # (16-nov) «Video + Audio» tambien es video: con «"audio" not in tipo» solo pasaba 1 de 73 (el dron sin sonido)
        if r and os.path.exists(r) and r.lower().endswith(EXT_VIDEO) and tipo.strip() != "audio" \
                and not os.path.normcase(r).startswith(os.path.normcase(rutas.RECURSOS)):
            videos.setdefault(r, []).append(c)
    if videos:
        cod = _codificador()
        t0 = time.time()
        log("Haciendo proxies para editar con fluidez: %d videos (%s)..." % (len(videos), cod[0]))
        with ThreadPoolExecutor(PARALELO) as ex:
            hechos = dict(zip(videos, ex.map(lambda o: hacer_proxy(o, log, cod), list(videos))))
        n = 0
        for original, clips in videos.items():
            p = hechos.get(original)
            if not p:
                continue
            for c in clips:
                try:
                    if (c.GetClipProperty("Proxy Media Path") or "") != p:
                        c.LinkProxyMedia(p)
                    n += 1
                except Exception:
                    pass
        log("Proxies listos en %.0f s: %d clips enlazados (por dentro, en %s)." % (time.time() - t0, n, carpeta_proxies()))
    else:
        n = 0
    cache(project, log)
    return n


def recordar_cache(project):
    """(17-nov) Anota donde guarda DaVinci la cache de render de este proyecto (<perfCacheClipsLocation>/<id>), para
    que «Borrar caché» de Ajustes la pueda borrar aunque DaVinci este cerrado (limpieza.py). En la boda: 18 GB."""
    try:
        loc = project.GetSetting("perfCacheClipsLocation") or ""
        uid = project.GetUniqueId() or ""
    except Exception:
        return
    if not loc or not uid:
        return
    c = rutas.leer_config()
    d = c.get("cache_davinci") or {}
    ids = set(d.get(loc) or [])
    if uid in ids:
        return
    ids.add(uid)
    d[loc] = sorted(ids)
    c["cache_davinci"] = d
    try:
        rutas.guardar_config(c)
    except Exception:
        pass


def cache(project, log=print):
    """Usar los proxies cuando hay + cache de render inteligente y automatica."""
    recordar_cache(project)
    hechos = []
    for k, v in (("perfProxyMediaMode", "1"), ("perfRenderCacheMode", "smart"), ("perfAutoRenderCacheEnable", "1"),
                 ("perfAutoRenderCacheAfterTime", "5"), ("perfAutoRenderCacheTransition", "1"),
                 ("perfAutoRenderCacheComposite", "1"), ("perfAutoRenderCacheFuEffect", "1")):
        try:
            if project.SetSetting(k, v):
                hechos.append(k)
        except Exception:
            pass
    log("Proyecto listo para editar: proxies cuando hay y cache de render automatica (%d ajustes)." % len(hechos))
    return len(hechos)


def _usados(tl):
    """Los media pool items que usa la linea (video y audio, todas las pistas)."""
    ids = set()
    for tipo in ("video", "audio"):
        for t in range(1, (tl.GetTrackCount(tipo) or 0) + 1):
            for x in tl.GetItemListInTrack(tipo, t) or []:
                try:
                    m = x.GetMediaPoolItem()
                    if m is not None:
                        ids.add(m.GetUniqueId())
                except Exception:
                    pass
    return ids


def _borrar_proyecto(pm, nombre):
    """Borra el proyecto de la carpeta actual de la base. DaVinci no deja borrar uno que este cargado, y deja en memoria
    los que se abrieron en la sesion (16-nov: al rehacer las plantillas, DeleteProject daba False): se abre, se cierra
    y se borra. True si ya no esta."""
    if nombre not in (pm.GetProjectListInCurrentFolder() or []):
        return True
    if pm.DeleteProject(nombre):
        return True
    p = pm.LoadProject(nombre)
    if p is not None:
        pm.CloseProject(p)
    return bool(pm.DeleteProject(nombre)) or nombre not in (pm.GetProjectListInCurrentFolder() or [])


def proyecto_por_video(resolve, evento, lineas, log=print):
    """Un proyecto de DaVinci por video, con SOLO esa linea y los clips que usa, exportado como .drp en
    EVENTO TERMINADO/PLANTILLAS DE LOS VIDEOS. lineas: [nombres de las lineas del evento]. Devuelve los .drp hechos."""
    pm = resolve.GetProjectManager()
    actual = pm.GetCurrentProject()
    if actual is None:
        return []
    nombre_p = actual.GetName()
    if "untitled" in (nombre_p or "").lower():          # guardar «Untitled Project» cuelga la API
        return []
    pm.SaveProject()
    destino = rutas.plantillas_evento(evento)
    os.makedirs(destino, exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), "trailer_proyecto_%d.drp" % os.getpid())
    if not pm.ExportProject(nombre_p, tmp, True):
        log("Aviso: no se pudo exportar el proyecto para hacer uno por video.")
        return []
    hechos = []
    carpeta = rutas.limpiar_nombre(evento)
    try:
        pm.GotoRootFolder()
        if carpeta not in (pm.GetFolderListInCurrentFolder() or []):
            pm.CreateFolder(carpeta)
        pm.OpenFolder(carpeta)
        for linea in lineas:
            video = rutas.nombre_video(linea)
            nombre = "%s - %s" % (carpeta, video)
            try:
                if not _borrar_proyecto(pm, nombre):
                    log("Aviso: no se pudo reemplazar el proyecto de %s (esta abierto en DaVinci)." % video)
                    continue
                if not pm.ImportProject(tmp, nombre):
                    log("Aviso: no se pudo crear el proyecto de %s." % video)
                    continue
                p = pm.LoadProject(nombre)
                if p is None:
                    continue
                mp = p.GetMediaPool()
                queda, otras = None, []
                for i in range(1, p.GetTimelineCount() + 1):
                    t = p.GetTimelineByIndex(i)
                    if t.GetName() == linea:
                        queda = t
                    else:
                        otras.append(t)
                if queda is None:
                    log("Aviso: %s no esta en la copia del proyecto." % linea)
                    pm.CloseProject(p)
                    pm.DeleteProject(nombre)
                    continue
                p.SetCurrentTimeline(queda)
                time.sleep(0.5)
                if otras:
                    mp.DeleteTimelines(otras)
                usados = _usados(queda)
                sobran = [c for c in _clips(mp.GetRootFolder()) if c.GetUniqueId() not in usados
                          and (c.GetClipProperty("Type") or "").lower() not in ("timeline", "compound")]
                for k in range(0, len(sobran), 200):         # por tandas: DeleteClips con miles a la vez se traba
                    mp.DeleteClips(sobran[k:k + 200])
                cache(p, lambda m: None)
                pm.SaveProject()
                drp = os.path.join(destino, video + ".drp")
                if os.path.exists(drp):
                    os.remove(drp)
                if pm.ExportProject(nombre, drp, True):
                    hechos.append(drp)
                    log("Plantilla de %s: %s (solo esa linea y sus %d clips)." % (video, os.path.basename(drp), len(usados)))
                pm.CloseProject(p)                       # que no quede cargado: si no, la proxima vez no se borra
            except Exception as ex:
                log("Aviso: no se pudo hacer el proyecto de %s (%s)" % (video, ex))
    finally:
        pm.GotoRootFolder()
        pm.LoadProject(nombre_p)
        try:
            os.remove(tmp)
        except OSError:
            pass
    return hechos
