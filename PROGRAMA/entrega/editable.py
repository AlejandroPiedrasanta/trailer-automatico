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
import re
import threading
import time
import hashlib
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import rutas

ALTO_PROXY = 540
PARALELO = 4                 # (18-nov) con la tarjeta leyendo y comprimiendo, 4 a la vez
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
    """(19-nov) Videos/PROXIES TRAILER AUTOMATICO (rutas.carpeta_proxies): todos los eventos y plantillas juntos."""
    return rutas.carpeta_proxies()


def mudar_proxies(log=print):
    """Los proxies que estaban por dentro (rutas.PROXIES_VIEJOS) pasan a la carpeta de Videos. Los proyectos de
    DaVinci los vuelven a encontrar al abrirse (enlazar_proxies) o al armar (proxies_y_cache). Devuelve cuantos."""
    import shutil
    viejo, nuevo = rutas.PROXIES_VIEJOS, carpeta_proxies()
    if not os.path.isdir(viejo) or os.path.normcase(os.path.abspath(viejo)) == os.path.normcase(os.path.abspath(nuevo)):
        return 0
    os.makedirs(nuevo, exist_ok=True)
    n = 0
    for f in os.listdir(viejo):
        a, b = os.path.join(viejo, f), os.path.join(nuevo, f)
        if not os.path.isfile(a) or f.endswith(".tmp.mov"):
            continue
        try:
            if os.path.exists(b):
                os.remove(a)                         # ya estaba alla (el mismo video): sobra la copia de dentro
            else:
                shutil.move(a, b)                    # otro disco: copia y borra
            n += 1
        except OSError as ex:
            log("Aviso: no se pudo mudar el proxy %s (%s)" % (f, ex))
    try:
        if not os.listdir(viejo):
            os.rmdir(viejo)
    except OSError:
        pass
    if n:
        log("Proxies mudados a %s: %d." % (nuevo, n))
    return n


def enlazar_proxies(project, log=print):
    """Solo enlaza los proxies que YA estan hechos (en la carpeta de Videos) a los clips que no los tienen o los tienen
    en otra ruta (los mudados). No hace ninguno: es rapido (al abrir un proyecto de video). Devuelve cuantos."""
    if not rutas.proxies_activos():
        return 0
    n = 0
    for c in _clips(project.GetMediaPool().GetRootFolder()):
        try:
            r = c.GetClipProperty("File Path") or ""
            if not r or not r.lower().endswith(EXT_VIDEO) or not os.path.exists(r) or _sin_proxy(r):
                continue
            p = ruta_proxy(r)
            actual = c.GetClipProperty("Proxy Media Path") or ""
            if not os.path.exists(p) and actual:     # el que ya tenia (mudado a la carpeta nueva), con el nombre de ahora
                movido = os.path.join(carpeta_proxies(), os.path.basename(actual))
                if os.path.exists(movido):
                    try:
                        os.replace(movido, p)
                    except OSError:
                        p = movido
            if not os.path.exists(p):                # hecho cuando el video estaba en otra carpeta
                p = proxy_huerfano(r) or p
            if os.path.exists(p) and os.path.normcase(actual) != os.path.normcase(p):
                if _retiempo(p, _fps_davinci(c.GetClipProperty("FPS")))[0]:   # antes de enlazar (DaVinci recuerda
                    arreglar_proxy(p, r, c.GetClipProperty("Start TC"), c.GetClipProperty("FPS"))   # el rechazo)
                ok = c.LinkProxyMedia(p)
                if not ok and arreglar_proxy(p, r, c.GetClipProperty("Start TC"), c.GetClipProperty("FPS")):
                    c.UnlinkProxyMedia()                # (DaVinci recuerda el rechazo en la sesion)
                    ok = c.LinkProxyMedia(p)
                if ok:
                    n += 1
        except Exception:
            pass
    if n:
        log("Proxies enlazados desde %s: %d clips." % (carpeta_proxies(), n))
    return n


def ruta_proxy(original):
    """El proxy de un archivo (rutas.ruta_proxy: nombre + tamaño, en Videos). Si solo esta con el nombre de antes del
    19-nov (la huella llevaba la ruta), se le pone el de ahora."""
    p = rutas.ruta_proxy(original)
    if not os.path.exists(p):
        v = rutas.ruta_proxy_vieja(original)
        if v != p and os.path.exists(v):
            try:
                os.replace(v, p)
            except OSError:
                return v
    return p


def _duracion(ruta):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                           capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def _timecode(ruta):
    """El codigo de tiempo del video (camaras Sony: «06:46:40:27» en su pista de datos), o ''."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream_tags=timecode:format_tags=timecode",
                            "-of", "default=nw=1:nk=1", ruta],
                           capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        return next((l.strip() for l in r.stdout.splitlines() if l.strip()), "")
    except Exception:
        return ""


def _tc_para(original, start_tc=None):
    """El codigo de tiempo que debe llevar el proxy: el que DaVinci lee del clip («Start TC») si se tiene; si no, el del
    archivo, y a 29,97 / 59,94 en «drop frame» («06:46:40;27»: asi lo lee DaVinci de las Sony)."""
    if start_tc and re.match(r"^\d\d:\d\d:\d\d[:;]\d\d$", start_tc) and start_tc != "00:00:00:00":
        return start_tc
    tc = _timecode(original)
    if not tc:
        return ""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                            "-of", "default=nw=1:nk=1", original],
                           capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        if r.stdout.strip() in ("30000/1001", "60000/1001"):
            tc = tc[:8] + ";" + tc[9:]
    except Exception:
        pass
    return tc


def _fps(ruta):
    """Cuadros por segundo (r_frame_rate) del archivo, o 0."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                            "-of", "default=nw=1:nk=1", ruta],
                           capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        a, b = (r.stdout.strip().split("/") + ["1"])[:2]
        return float(a) / float(b or 1)
    except Exception:
        return 0.0


def _fps_davinci(fps):
    """El FPS con que DaVinci lee el clip (propiedad «FPS») como numero, o None."""
    try:
        f = float(fps)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _retiempo(ruta, fps):
    """(19-nov, MEDIDO en la XV: 13 de 82 proxies rechazados) Los videos de celular van a cuadros por segundo VARIABLES
    (29,98 de media) y DaVinci los lee como 30, pero el proxy salia a 29,97 justos: mismos 464 cuadros y aun asi
    LinkProxyMedia da False. Con el FPS de DaVinci se pone el proxy a esa velocidad, un cuadro por cuadro (setpts), sin
    cambiar cuantos son. [] si ya coincide."""
    if not fps:
        return [], ""
    actual = _fps(ruta)
    if not actual or abs(actual - fps) < 0.005:
        return [], ""
    # (19-nov, revision) 29,97 es 30000/1001, no 2997/100: con el numero redondeado DaVinci lo seguiria rechazando
    v = next((q for n, q in ((23.976, "24000/1001"), (29.97, "30000/1001"), (59.94, "60000/1001"), (47.952, "48000/1001"))
              if abs(fps - n) < 0.01), None) or ("%.3f" % fps).rstrip("0").rstrip(".")
    return ["-r", v], "setpts=N/((%s)*TB)" % v


def _audio_proxy(proxy):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
                            "-of", "default=nw=1:nk=1", proxy],
                           capture_output=True, text=True, timeout=30, creationflags=rutas.SIN_VENTANA)
        return r.stdout.strip()
    except Exception:
        return ""


def arreglar_proxy(proxy, original, start_tc=None, fps=None):
    """(19-nov, MEDIDO en el XV: LinkProxyMedia daba False en 17 de 23 clips de la camara Sony) DaVinci solo acepta el
    proxy con el MISMO codigo de tiempo que el original («06:46:40;27», drop frame) y con el audio en PCM como el
    original (con AAC lo rechaza aunque el codigo de tiempo cuadre). Se arregla sin recomprimir el video (segundos).
    fps: el que DaVinci lee del clip; si el proxy va a otra velocidad (celular: 30 contra 29,97) se recomprime a esa
    (el proxy es chico: segundos). True si lo cambio."""
    tc = _tc_para(original, start_tc)
    audio = _audio_proxy(proxy)
    salida_r, filtro_r = _retiempo(proxy, _fps_davinci(fps))
    if not tc and audio in ("", "pcm_s16le") and not salida_r:   # (ffprobe no distingue «drop frame»: con codigo,
        return False                             # se rehace siempre; solo se llama cuando DaVinci ya lo rechazo)
    tmp = proxy + ".tc.mov"
    video = ["-c:v", "copy"]
    if salida_r:
        c, extra = _codificador()
        video = ["-vf", filtro_r, "-c:v", c] + extra + ["-pix_fmt", "yuv420p"] + salida_r
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", proxy, "-map", "0:v:0",
                            "-map", "0:a?"] + video + ["-c:a", "pcm_s16le"] + (["-timecode", tc] if tc else []) +
                           ["-movflags", "+faststart", tmp],
                           capture_output=True, text=True, timeout=600, creationflags=rutas.SIN_VENTANA)
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, proxy)
            _REHECHOS.add(proxy)
            return True
    except Exception:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def proxy_huerfano(original):
    """(19-nov) Un proxy hecho cuando el video estaba en otra carpeta (nombre de antes, con la ruta en la huella): uno
    con el mismo nombre de video y la misma duracion. Se le pone el nombre de ahora. Devuelve su ruta o None."""
    import glob
    p = rutas.ruta_proxy(original)
    base = os.path.splitext(os.path.basename(original))[0][:60]
    candidatos = [c for c in glob.glob(os.path.join(glob.escape(carpeta_proxies()), glob.escape(base) + "_*_proxy.mov"))
                  if os.path.normcase(c) != os.path.normcase(p) and not c.endswith(".tmp.mov")]
    if not candidatos:
        return None
    dur = _duracion(original)
    for c in candidatos[:6]:
        if dur > 0 and abs(_duracion(c) - dur) < 0.15:
            try:
                os.replace(c, p)
                return p
            except OSError:
                return c
    return None


def seguir_renombrado(hechos):
    """(18-nov) Al renombrar un video, su proxy (que lleva el nombre en la huella) quedaba huerfano y se volvia a hacer
    entero: 52 proxies, 11 min, con el programa parado en 97 %. Ahora el proxy se renombra con el. Devuelve cuantos."""
    n = 0
    for a, b in hechos:
        try:
            tam = os.path.getsize(b)
            nuevo = rutas.ruta_proxy(b, tam)
            for viejo in (rutas.ruta_proxy(a, tam), rutas.ruta_proxy_vieja(a, tam)):
                if os.path.exists(viejo) and not os.path.exists(nuevo):
                    os.replace(viejo, nuevo)
                    n += 1
                    break
        except OSError:
            pass
    return n


_REHECHOS = set()                   # proxies rehechos en esta sesion (hay que volver a enlazarlos aunque la ruta sea igual)


def _girado(ruta):
    """True si el video lleva rotacion de 90/270 (celular en vertical: 3840x2160 con rotation -90)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:stream_side_data=rotation:stream_tags=rotate", "-of", "json", ruta],
                           capture_output=True, text=True, timeout=60, creationflags=rutas.SIN_VENTANA)
        import json
        s = (json.loads(r.stdout).get("streams") or [{}])[0]
        rot = [d.get("rotation") for d in s.get("side_data_list") or [] if "rotation" in d]
        rot = rot[0] if rot else (s.get("tags") or {}).get("rotate", 0)
        return abs(int(float(rot or 0))) % 180 == 90, s.get("width") or 0, s.get("height") or 0
    except Exception:
        return False, 0, 0


_CANDADOS = {}
_CANDADO_LISTA = threading.Lock()


def hacer_proxy(original, log=print, codificador=None, start_tc=None, fps=None):
    """Hace el proxy (si no esta hecho). fps: el que DaVinci lee del clip (el proxy sale a ese). Devuelve su ruta o
    None. (19-nov, revision) Un candado por proxy: los adelantados durante el render y los de despues (o los de dos
    renders seguidos) nunca escriben el mismo .tmp.mov a la vez; el segundo espera y encuentra el proxy hecho."""
    with _CANDADO_LISTA:
        candado = _CANDADOS.setdefault(os.path.normcase(os.path.abspath(original)), threading.Lock())
    with candado:
        return _hacer_proxy(original, log, codificador, start_tc, fps)


def _hacer_proxy(original, log=print, codificador=None, start_tc=None, fps=None):
    destino = ruta_proxy(original)
    if not os.path.exists(destino):              # (19-nov) hecho cuando el video estaba en otra carpeta: no se rehace
        destino = proxy_huerfano(original) or destino
    girado, _, _ = _girado(original)
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        # (18-nov) los proxies hechos todo en la tarjeta de un video vertical de celular salian ACOSTADOS (960x540 sin
        # rotacion: con -hwaccel_output_format cuda ffmpeg no gira) y en DaVinci se veia la toma de lado
        if girado and _girado(destino)[1] > _girado(destino)[2] and not _girado(destino)[0]:
            log("Proxy acostado de %s: lo rehago derecho." % os.path.basename(original))
            try:
                os.remove(destino)
            except OSError:
                return destino
            _REHECHOS.add(destino)
        else:
            # (19-nov, MEDIDO) uno hecho antes a otra velocidad (celular: 29,97 contra los 30 de DaVinci) se arregla
            # ANTES de enlazarlo: DaVinci recuerda el rechazo de esa ruta en la sesion y ya no lo acepta arreglado
            if _retiempo(destino, _fps_davinci(fps))[0]:
                arreglar_proxy(destino, original, start_tc, fps)
            return destino
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    c, extra = codificador or _codificador()
    tmp = destino + ".tmp.mov"
    tc = _tc_para(original, start_tc)            # (19-nov) el mismo codigo de tiempo que el original (si no, no enlaza)
    con_tc = ["-timecode", tc] if tc else []
    salida_r, filtro_r = _retiempo(original, _fps_davinci(fps))   # (19-nov) celular: a la velocidad que lee DaVinci
    con_tc = salida_r + con_tc
    retiempo = ("," + filtro_r) if filtro_r else ""
    orden = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", original, "-map", "0:v:0", "-map", "0:a?",
             "-vf", "scale=-2:%d%s" % (ALTO_PROXY, retiempo), "-c:v", c] + extra + [
                 "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-movflags", "+faststart"] + con_tc + [tmp]
    try:
        # (18-nov, la persona: «necesito procesos más rápidos... bajar más los tiempos») Leer el 4K con el procesador
        # era lo lento (4 veces el tiempo real). Con la tarjeta NVIDIA todo el camino (leer, achicar y comprimir) va a
        # 12 veces; leyendo con la tarjeta y achicando con el procesador, a 7. Si no puede, sigue el camino de antes.
        rapidas = []
        if c == "h264_nvenc" and not girado:            # girado: la via toda en la tarjeta no gira (salia acostado)
            rapidas.append(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-hwaccel", "cuda",
                            "-hwaccel_output_format", "cuda", "-i", original, "-map", "0:v:0", "-map", "0:a?",
                            "-vf", "scale_cuda=-2:%d:format=nv12%s" % (ALTO_PROXY, retiempo), "-c:v", c] + extra +
                           ["-c:a", "pcm_s16le", "-movflags", "+faststart"] + con_tc + [tmp])
        if c != "libx264":
            rapidas.append(orden[:4] + ["-hwaccel", "auto"] + orden[4:])
        for rapida in rapidas:
            r = subprocess.run(rapida, capture_output=True, text=True, timeout=7200, creationflags=rutas.SIN_VENTANA)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, destino)
                return destino
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


def _sin_proxy(ruta):
    """(19-nov) Lo que NO lleva proxy: las luces del programa (XV_BRILLOS_H...) y los recortes con transparencia del
    texto detras (…_persona_0.mov). Venian tambien de OTRA instalacion (su carpeta recursos no es la de esta) y un
    proxy H.264 les quita la transparencia: editando con proxies la persona taparia el titulo con un cuadro entero."""
    # (revision) solo las carpetas DEL PROGRAMA: material en «D:\RECURSOS\XV ANA» si lleva proxy
    partes = [x.upper() for x in os.path.normpath(ruta).split(os.sep)]
    nombre = os.path.basename(ruta).upper()
    de_programa = "_INTERNAL" in partes or ("RECURSOS" in partes and "OVERLAYS" in partes) or \
        ("TRABAJO" in partes and "RECORTES" in partes)
    return de_programa or re.search(r"_PERSONA_\d+\.MOV$", nombre) is not None or \
        re.match(r"^(XV|BODA)_(DESTELLO|BRILLOS)_[HV]\.", nombre) is not None


def _clips(carpeta):
    out = list(carpeta.GetClipList() or [])
    for s in carpeta.GetSubFolderList() or []:
        out += _clips(s)
    return out


def proxies_y_cache(project, log=print):
    """Proxies de todos los videos del media pool que vienen del evento (o del material), enlazados, y la cache de
    render del proyecto. Devuelve cuantos proxies quedaron enlazados. (19-nov) Con «Proxies para editar» apagado en
    Ajustes, solo la cache (no se hace ni se enlaza ningun proxy)."""
    if not rutas.proxies_activos():
        log("Proxies apagados en Ajustes: solo la caché de render.")
        cache(project, log)
        return 0
    esperar_adelanto(log)                    # los que se hicieron mientras DaVinci renderizaba
    videos = _videos_para_proxy(project)
    return _hacer_y_enlazar(project, videos, log)


# (19-nov, MEDIDO: proxies 5,7 min DESPUES del render, con la tarjeta del render al 36 %) Se hacen MIENTRAS DaVinci
# renderiza: antes del render se apunta que videos van (con su codigo de tiempo y su FPS) y ffmpeg los hace en segundo
# plano, de a PARALELO_RENDER (menos que PARALELO: la tarjeta tambien comprime el render). Al terminar, proxies_y_cache
# espera a que acaben y solo enlaza.
PARALELO_RENDER = 2
_ADELANTO = {}


def adelantar(project, log=print):
    """Lanza en segundo plano los proxies que faltan de las lineas del proyecto. Llamar con DaVinci libre (lee el media
    pool); lo que hace despues es solo ffmpeg. No devuelve nada; proxies_y_cache espera."""
    if not rutas.proxies_activos() or os.environ.get("TRAILER_PROXIES_EN_RENDER") == "0":
        return
    esperar_adelanto(log)                    # (revision) el de un render anterior (Renderizar lo editado, video a video)
    try:
        videos = _videos_para_proxy(project)
        faltan = {}
        for o, cs in videos.items():
            if os.path.exists(ruta_proxy(o)):
                continue
            try:
                faltan[o] = (cs[0].GetClipProperty("Start TC") or None, cs[0].GetClipProperty("FPS") or None)
            except Exception:
                faltan[o] = (None, None)
    except Exception as ex:
        log("Aviso: los proxies se haran despues del render (%s)" % ex)
        return
    if not faltan:
        return
    cod = _codificador()
    ex = ThreadPoolExecutor(PARALELO_RENDER, thread_name_prefix="proxies")
    t0 = time.time()
    def uno(o, tc, fps):
        if rutas.PARAR.is_set():             # (revision) «Cancelar»: los que faltan no se empiezan
            return None
        return hacer_proxy(o, log, cod, tc, fps)
    futuros = [ex.submit(uno, o, tc, fps) for o, (tc, fps) in faltan.items()]
    ex.shutdown(wait=False, cancel_futures=False)
    _ADELANTO["trabajo"] = (futuros, t0)
    log("Proxies en segundo plano mientras se renderiza: %d videos." % len(faltan))


def esperar_adelanto(log=print):
    pend = _ADELANTO.pop("trabajo", None)
    if not pend:
        return
    futuros, t0 = pend
    hechos = 0
    for f in futuros:
        try:
            hechos += bool(f.result())
        except Exception:
            pass
    log("Proxies hechos durante el render: %d en %.0f s." % (hechos, time.time() - t0))


def _videos_para_proxy(project):
    """{ruta: [clips]} de los videos que llevan proxy: los que estan en alguna linea de evento (o ya lo tienen)."""
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
                and not os.path.normcase(r).startswith(os.path.normcase(rutas.RECURSOS)) and not _sin_proxy(r):
            videos.setdefault(r, []).append(c)
    # (17-nov) solo los videos que ESTAN en las lineas de los eventos (no las plantillas): en el XV del 8-nov eran 129
    # proxies (mas de 20 min) para 58 tomas usadas. Lo que no esta en ninguna linea se edita igual, sin proxy.
    try:
        usados = set()
        for i in range(1, project.GetTimelineCount() + 1):
            tl = project.GetTimelineByIndex(i)
            if tl is None or (tl.GetName() or "").upper().startswith("TRAILER "):
                continue
            for v in range(1, tl.GetTrackCount("video") + 1):
                for it in tl.GetItemListInTrack("video", v) or []:
                    m = it.GetMediaPoolItem()
                    r = (m.GetClipProperty("File Path") or "") if m else ""
                    if r:
                        usados.add(os.path.normcase(r))
        if usados:
            videos = {r: c for r, c in videos.items()
                      if os.path.normcase(r) in usados or os.path.exists(ruta_proxy(r))}
    except Exception:
        pass
    return videos


def _hacer_y_enlazar(project, videos, log):
    if videos:
        cod = _codificador()
        t0 = time.time()
        log("Haciendo proxies para editar con fluidez: %d videos (%s)..." % (len(videos), cod[0]))
        # el codigo de tiempo que DaVinci lee de cada clip (el proxy debe llevar el mismo, «drop frame» incluido)
        tcs, fpss = {}, {}
        for o, cs in videos.items():
            try:
                tcs[o] = cs[0].GetClipProperty("Start TC") or None
                fpss[o] = cs[0].GetClipProperty("FPS") or None
            except Exception:
                tcs[o] = None
        with ThreadPoolExecutor(PARALELO) as ex:
            hechos = dict(zip(videos, ex.map(lambda o: hacer_proxy(o, log, cod, tcs.get(o), fpss.get(o)), list(videos))))
        n = fallos = 0
        for original, clips in videos.items():
            p = hechos.get(original)
            if not p:
                continue
            for c in clips:
                try:
                    ok = (c.GetClipProperty("Proxy Media Path") or "") == p and p not in _REHECHOS
                    if not ok:
                        if p in _REHECHOS:              # mismo archivo, rehecho: DaVinci tiene el viejo en memoria
                            try:
                                c.UnlinkProxyMedia()
                            except Exception:
                                pass
                        ok = c.LinkProxyMedia(p)
                        # (19-nov, MEDIDO) LinkProxyMedia daba False en silencio (Sony: codigo de tiempo y audio PCM) y
                        # se contaban igual como enlazados: se arregla el proxy y se intenta otra vez
                        if not ok and arreglar_proxy(p, original, tcs.get(original), fpss.get(original)):
                            c.UnlinkProxyMedia()        # (DaVinci recuerda el rechazo en la sesion)
                            ok = c.LinkProxyMedia(p)
                    if ok:
                        n += 1
                    else:
                        fallos += 1
                except Exception:
                    fallos += 1
        log("Proxies listos en %.0f s: %d clips enlazados%s (en %s)." % (
            time.time() - t0, n, ", %d que DaVinci no aceptó" % fallos if fallos else "", carpeta_proxies()))
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
    for _ in range(4):                  # (18-nov, 2a vuelta de las plantillas) recien cerrado, DaVinci tarda en soltarlo
        if pm.DeleteProject(nombre) or nombre not in (pm.GetProjectListInCurrentFolder() or []):
            return True
        time.sleep(1.5)
    return False


LINEA_TIPOS = ("timeline", "compound", "línea de tiempo", "linea de tiempo", "clip compuesto", "compuesto")


def _es_linea(clip, lineas):
    """¿Es una linea (o un clip compuesto) del media pool? (18-nov) Con DaVinci en español el tipo sale «Línea de
    tiempo», no «Timeline»: se miraba solo en ingles y las lineas se borraban como clips sobrantes. Se mira el tipo en
    los dos idiomas Y el nombre de las lineas que quedan."""
    try:
        tipo = (clip.GetClipProperty("Type") or "").strip().lower()
        return tipo in LINEA_TIPOS or (clip.GetName() or "") in lineas
    except Exception:
        return True                     # en la duda, no se borra


def _recortar_base(pm, tmp, carpeta, lineas, log):
    """Una copia del proyecto con SOLO las lineas del evento y sus clips, exportada a otro .drp: cada plantilla por
    video se importa de esta (mucho mas chica) en vez del proyecto entero. Devuelve su ruta, o None."""
    import vigia_davinci
    nombre = "%s - BASE" % carpeta
    salida = tmp.replace(".drp", "_evento.drp")
    t0 = time.time()
    try:
        with vigia_davinci.vigilar("copia del evento", tope=180):
            _borrar_proyecto(pm, nombre)
            if not pm.ImportProject(tmp, nombre):
                return None
            p = pm.LoadProject(nombre)
            if p is None:
                return None
            mp = p.GetMediaPool()
            quedan, otras = [], []
            for i in range(1, p.GetTimelineCount() + 1):
                t = p.GetTimelineByIndex(i)
                (quedan if t.GetName() in lineas else otras).append(t)
            if otras:
                mp.DeleteTimelines(otras)
            usados = set()
            for t in quedan:
                usados |= _usados(t)
            sobran = [c for c in _clips(mp.GetRootFolder()) if c.GetUniqueId() not in usados
                      and not _es_linea(c, [t.GetName() for t in quedan])]
            for k in range(0, len(sobran), 200):
                mp.DeleteClips(sobran[k:k + 200])
            pm.SaveProject()
            ok = pm.ExportProject(nombre, salida, True)
            pm.CloseProject(p)
            _borrar_proyecto(pm, nombre)
        if ok:
            log("Copia solo con este evento: %d lineas, %d clips fuera, %.1f MB en %.0f s." % (
                len(quedan), len(sobran), os.path.getsize(salida) / 1e6, time.time() - t0))
            return salida
    except Exception as ex:
        log("Aviso: no se pudo hacer la copia chica del evento (%s): uso el proyecto entero." % ex)
    return None


def proyecto_por_video(resolve, evento, lineas, log=print, desde=None):
    """desde: (18-nov) en un reintento tras un cuelgue, las plantillas ya hechas desde ese momento no se rehacen."""
    if desde:
        destino0 = rutas.plantillas_evento(evento)
        hechas = [l for l in lineas if os.path.exists(os.path.join(destino0, rutas.nombre_video(l) + ".drp"))
                  and os.path.getmtime(os.path.join(destino0, rutas.nombre_video(l) + ".drp")) >= desde]
        if hechas:
            log("Ya hechas en el intento anterior: %s." % ", ".join(rutas.nombre_video(l) for l in hechas))
        lineas = [l for l in lineas if l not in hechas]
        if not lineas:
            return [os.path.join(destino0, rutas.nombre_video(l) + ".drp") for l in hechas]
    hechos = []
    try:
        hechos, lineas = _por_drt(resolve, evento, lineas, log)
    except Exception as ex:
        log("Aviso: plantillas por el camino rápido: %s; sigo por el de siempre." % ex)
    return hechos + (_proyecto_por_video(resolve, evento, lineas, log) if lineas else [])


def _por_drt(resolve, evento, lineas, log=print):
    """(18-nov, MEDIDO en la boda) El camino de siempre importaba el proyecto ENTERO (85 MB de project.xml) por cada
    video y luego le borraba casi todo: ~70 s por plantilla y un .drp de 41 MB. Aqui: la linea se exporta a .drt (0,3 s),
    se crea un proyecto vacio con los mismos ajustes, se importa la linea (1,7 s) y se exporta el .drp: ~6 s y 0,4 MB.
    Comparado con la linea original: las 21 pistas, clip por clip, y los marcadores, iguales; los cuadros (titulos,
    color, brillos), iguales. Devuelve ([.drp hechos], [lineas que fallaron: van por el camino de siempre])."""
    import vigia_davinci
    pm = resolve.GetProjectManager()
    actual = pm.GetCurrentProject()
    if actual is None or "untitled" in (actual.GetName() or "").lower():
        return [], lineas
    nombre_p = actual.GetName()
    destino = rutas.plantillas_evento(evento)
    os.makedirs(destino, exist_ok=True)
    carpeta = rutas.limpiar_nombre(evento)
    tmp = tempfile.mkdtemp(prefix="trailer_drt_")
    ajustes = actual.GetSetting() or {}
    drts = {}
    for i in range(1, actual.GetTimelineCount() + 1):
        t = actual.GetTimelineByIndex(i)
        if t.GetName() in lineas and t.GetName() not in drts:
            ruta = os.path.join(tmp, "%02d.drt" % len(drts))
            if t.Export(ruta, resolve.EXPORT_DRT) and os.path.exists(ruta):
                drts[t.GetName()] = ruta
    pm.SaveProject()
    hechos, fallan = [], [l for l in lineas if l not in drts]
    try:
        pm.GotoRootFolder()
        if carpeta not in (pm.GetFolderListInCurrentFolder() or []):
            pm.CreateFolder(carpeta)
        pm.OpenFolder(carpeta)
        for linea in [l for l in lineas if l in drts]:
            video = rutas.nombre_video(linea)
            nombre = "%s - %s" % (carpeta, video)
            t0 = time.time()
            try:
                with vigia_davinci.vigilar("plantilla de %s" % video, tope=120):
                    for viejo in [n for n in pm.GetProjectListInCurrentFolder() or [] if n.startswith(nombre + " (")]:
                        _borrar_proyecto(pm, viejo)
                    if not _borrar_proyecto(pm, nombre):
                        nombre = "%s (%s)" % (nombre, time.strftime("%H%M%S"))
                    p = pm.CreateProject(nombre)
                    if p is None:
                        fallan.append(linea)
                        continue
                    for k, v in ajustes.items():          # mismos ajustes (resolucion, cuadros, color...)
                        try:
                            if v not in (None, "") and p.GetSetting(k) != v:
                                p.SetSetting(k, v)
                        except Exception:
                            pass
                    mp = p.GetMediaPool()
                    nt = mp.ImportTimelineFromFile(drts[linea], {"timelineName": linea, "importSourceClips": True})
                    if nt is None:
                        pm.CloseProject(p)
                        _borrar_proyecto(pm, nombre)
                        fallan.append(linea)
                        continue
                    p.SetCurrentTimeline(nt)
                    if nt.GetName() != linea:         # (19-nov) DaVinci le pone el nombre del .drt («00»)
                        nt.SetName(linea)
                    try:
                        proxies_y_cache(p, lambda m: None)     # los proxies ya hechos y la cache de render
                    except Exception:
                        pass
                    pm.SaveProject()
                    drp = os.path.join(destino, video + ".drp")
                    if os.path.exists(drp):
                        os.remove(drp)
                    if pm.ExportProject(nombre, drp, True):
                        hechos.append(drp)
                        log("Plantilla de %s: %s en %.0f s (%.1f MB)." % (video, os.path.basename(drp), time.time() - t0,
                                                                       os.path.getsize(drp) / 1e6))
                    else:
                        fallan.append(linea)
                    pm.CloseProject(p)
            except Exception as ex:
                log("Aviso: la plantilla rápida de %s falló (%s): va por el camino de siempre." % (video, ex))
                fallan.append(linea)
    finally:
        pm.GotoRootFolder()
        pm.LoadProject(nombre_p)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return hechos, fallan


def _proyecto_por_video(resolve, evento, lineas, log=print):
    """Un proyecto de DaVinci por video, con SOLO esa linea y los clips que usa, exportado como .drp en
    EVENTO TERMINADO/PLANTILLAS DE LOS VIDEOS. lineas: [nombres de las lineas del evento]. Devuelve los .drp hechos."""
    pm = resolve.GetProjectManager()
    actual = pm.GetCurrentProject()
    if actual is None:
        return []
    nombre_p = actual.GetName()
    if "untitled" in (nombre_p or "").lower():          # guardar «Untitled Project» cuelga la API
        return []
    try:                                                # (18-nov) en otra base DaVinci se colgo al crear la carpeta
        import motor
        base = (pm.GetCurrentDatabase() or {}).get("DbName")
        bases = [d.get("DbName") for d in (pm.GetDatabaseList() or [])]
        if base and base != motor.BASE_DATOS and motor.BASE_DATOS in bases:   # (sin EVENTOS, la que haya vale)
            log("Aviso: DaVinci esta en la base «%s», no en «%s»: no hago los proyectos por video."
                % (base, motor.BASE_DATOS))
            return []
    except Exception:
        pass
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
        # (18-nov, probado) la copia chica NO sirvio: pesaba lo mismo (42,6 MB; lo pesado es project.xml, no los clips)
        # y las lineas se perdian por el camino. Apagada hasta revisar el filtro de tipo de clip.
        if False and len(lineas) >= 3:
            chico = _recortar_base(pm, tmp, carpeta, lineas, log)
            if chico:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                tmp = chico
        for linea in lineas:
            video = rutas.nombre_video(linea)
            nombre = "%s - %s" % (carpeta, video)
            log("Haciendo la plantilla de %s..." % video)      # (18-nov) si DaVinci se cuelga, se ve en cual
            import vigia_davinci
            t_uno = time.time()
            pasos, t_paso = [], [time.time()]

            def marca(que):                      # (18-nov) cada plantilla tardaba 57 s: cuanto se lleva cada paso
                pasos.append("%s %.0f" % (que, time.time() - t_paso[0]))
                t_paso[0] = time.time()
            try:
              with vigia_davinci.vigilar("plantilla de %s" % video, tope=180):   # una tarda ~1 min; 3 min = trabada
                for viejo in [n for n in pm.GetProjectListInCurrentFolder() or [] if n.startswith(nombre + " (")]:
                    _borrar_proyecto(pm, viejo)          # las que se hicieron con otro nombre la vez anterior
                if not _borrar_proyecto(pm, nombre):
                    # (18-nov) antes se saltaba y faltaba el .drp: se hace con otro nombre dentro de DaVinci (el
                    # archivo .drp se llama igual) y el viejo se borra la proxima vez
                    nombre = "%s (%s)" % (nombre, time.strftime("%H%M%S"))
                    log("Aviso: DaVinci no soltó el proyecto viejo de %s: lo hago como «%s»." % (video, nombre))
                marca("borrar")
                if not pm.ImportProject(tmp, nombre):
                    log("Aviso: no se pudo crear el proyecto de %s." % video)
                    continue
                marca("importar")
                p = pm.LoadProject(nombre)
                if p is None:
                    continue
                marca("cargar")
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
                marca("lineas")
                usados = _usados(queda)
                sobran = [c for c in _clips(mp.GetRootFolder()) if c.GetUniqueId() not in usados
                          and not _es_linea(c, [linea])]
                for k in range(0, len(sobran), 200):         # por tandas: DeleteClips con miles a la vez se traba
                    mp.DeleteClips(sobran[k:k + 200])
                marca("clips")
                cache(p, lambda m: None)
                pm.SaveProject()
                marca("guardar")
                drp = os.path.join(destino, video + ".drp")
                if os.path.exists(drp):
                    os.remove(drp)
                if pm.ExportProject(nombre, drp, True):
                    marca("exportar")
                    hechos.append(drp)
                    log("Plantilla de %s: %s (solo esa linea y sus %d clips) en %.0f s (%s)." % (
                        video, os.path.basename(drp), len(usados), time.time() - t_uno, ", ".join(pasos)))
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
