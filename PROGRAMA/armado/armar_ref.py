# -*- coding: utf-8 -*-
"""
armar_ref.py - (18-nov) Arma un video del evento CON UNA PLANTILLA DE REFERENCIA (plantilla_ref.py): sus cortes, su
musica y su forma de cambiar de plano; las tomas, las del evento.

    linea = armar(resolve, project, info, evento, analisis, salida, log)

  1. LAS TOMAS: las elige el planificador de siempre (receta._planes, formato de la plantilla: reglas, caras, sin piso
     ni borrosas, en el orden del dia), de la version cuyo plan tenga al menos tantos planos como huecos; se reparten
     a lo largo del dia (de los preparativos a la fiesta). Cada hueco lleva SU duracion exacta.
  2. LA LINEA «<evento> - PLANTILLA N», del tamaño de la plantilla (vertical: 1080 x 1920) y a sus cuadros por segundo;
     las tomas en V1 (sin su sonido) y la musica de la plantilla en A1, entera. NADA de otra musica.
  3. COMO CAMBIA: «fundido» -> Cross Dissolve; «destello» -> el DESTELLO propio (overlays) centrado en el corte;
     «corte» -> seco. El final con logo de la plantilla lo ocupa la mejor foto (la del final de siempre).
  4. COLOR: la misma correccion por plano (DCTL) y el look suave del 1 min, en un grupo «PLANTILLA».
  5. RENDER en cola como las demas (VIDEO FINAL PLANTILLA N.mov): renderizar.py lo saca y lo masteriza a -14 LUFS.
"""
import os
import time

import rutas

PISTA_V, PISTA_A = 1, 1
FUNDIDO_F = 10                         # cuadros del Cross Dissolve
MARGEN_S = 0.4                         # material de sobra a cada lado de la toma (para el fundido)
DCTL_COLOR = "MCP/XV_CORRECCION_COLOR.dctl"
LOOK = "MCP/XV_1min_CINE_TEAL_ORANGE_REC709.cube"
GRUPO = "PLANTILLA"
# (19-nov, la persona: «agrégales al inicio el texto de los nombres... mejora la estabilidad... un poco de cámara lenta
# para algunas tomas, no todo tan rápido»)
TITULO_INI_S, TITULO_MAX_S, TITULO_PARTE = 0.3, 3.6, 0.22   # el titulo con los nombres al inicio (s, parte del video)
LENTO_VEL = 0.5                        # camara lenta al 50 % con Speed Warp
LENTO_MIN_S = 1.4                      # solo en huecos largos (en uno corto no se nota y se pierde el ritmo)
DESTELLO_OPACIDAD = 60.0               # % de los destellos blancos en las plantillas
LENTO_PARTE = 0.25                     # como mucho 1 de cada 4 planos, los mas firmes


def _clips(carpeta):
    out = list(carpeta.GetClipList() or [])
    for sub in carpeta.GetSubFolderList() or []:
        out += _clips(sub)
    return out


def _carpeta(mp, padre, nombre):
    return next((f for f in padre.GetSubFolderList() or [] if f.GetName() == nombre), None) or mp.AddSubFolder(padre, nombre)


PESO_MOMENTO = {"MAQUILLAJE": 0.25, "IGLESIA": 0.30, "FIESTA": 0.45}     # como la apertura de las versiones


# (1.8.7, la persona: «varía de tomas entre plantillas para que cada plantilla sea diferente entre la otra») lo que
# ya usaron las plantillas anteriores de este armado (motor.armar_plantillas_ref lo vacia al empezar)
_VARIEDAD = {"tomas": []}


def reiniciar_variedad():
    _VARIEDAD["tomas"] = []


def elegir_tomas(analisis, info, tipo_evento, log=print, con_g=False):
    """[(item, ini, dur_s)] una por hueco (sin el final con logo), en el orden del dia, y el plano final.
    (19-nov, visto en la Plantilla 3) Antes se tomaban planos de ~1 s del plan de 1 / 3 min y se ALARGABAN al hueco
    (hasta 3,8 s): el alargue se metia en lo que el planificador habia evitado (el piso, torcidas). Ahora el
    planificador elige, para CADA hueco, un tramo bueno de ESE largo (Planificador.zona con corte = su duracion)."""
    import importlib.util
    import random
    s = importlib.util.spec_from_file_location("receta", rutas.codigo("receta.py"))
    receta = importlib.util.module_from_spec(s)
    s.loader.exec_module(receta)
    g = receta._planes(analisis, tipo_evento, "vertical" if info.get("vertical", True) else "horizontal")
    fps = float(getattr(receta, "FPS", 24))
    items = g["decisiones"](list(analisis.get("items") or []))
    plan = g["Planificador"](items, fps)
    plan.usados = {}
    # (1.8.7) lo que ya salio en otra plantilla no esta libre (otra parte de la toma si) y su imagen cuenta como escena
    # ya vista: cada plantilla sale con tomas distintas
    por_ruta = {v["ruta"]: v for v in getattr(plan, "vids", [])}
    plan.otras_plantillas = {t[0] for t in _VARIEDAD["tomas"]}      # esos videos pesan menos en esta plantilla
    for ruta, a, b, h in _VARIEDAD["tomas"]:
        plan.usados.setdefault(ruta, []).append((a, b))
        if h is not None and ruta in por_ruta and hasattr(plan, "escenas"):
            plan.escenas.append((por_ruta[ruta], h))
    try:
        plan.poner_estorbo_duro(True)
    except Exception:
        pass
    huecos = list(info["planos"])
    zonas = [m for m in ("MAQUILLAJE", "IGLESIA", "FIESTA") if plan.capacidad_f(m, (1.0, 3.0)) > 0]
    if not zonas:
        raise RuntimeError("no hay tomas buenas para la plantilla")
    largo_total = sum(h["dur"] for h in huecos) or 1.0
    # (19-nov, visto: 4 tomas distintas en 9 huecos, el arco 3 veces seguidas) el peso de cada momento segun lo que
    # tiene de BUENO: la fiesta de la boda tenia 3 tomas buenas y se llevaba el 45 % de los huecos
    cap = {m: plan.capacidad_f(m, (1.0, 3.0)) / fps for m in zonas}
    peso = {m: PESO_MOMENTO[m] * min(1.0, cap[m] / (largo_total * PESO_MOMENTO[m] * 3.0)) for m in zonas}
    total_p = sum(peso.values()) or 1.0
    momento_de, acum = [], 0.0                       # a que momento del dia va cada hueco (en orden)
    for h in huecos:
        pos = (acum + h["dur"] / 2.0) / largo_total
        acum += h["dur"]
        limite, elegido = 0.0, zonas[-1]
        for m in zonas:
            limite += peso[m] / total_p
            if pos <= limite:
                elegido = m
                break
        momento_de.append(elegido)
    rng = random.Random(4242 + sum(ord(ch) for ch in str(info.get("nombre") or "")))    # (1.8.7) otra por plantilla
    # (19-nov, visto: 6 tomas distintas en 20 huecos) hueco por hueco el planificador no sabe que tomas ya puso: se le
    # pide la ZONA ENTERA de cada momento (su manera de variar), con planos al menos tan largos como el hueco mas largo,
    # y cada uno se RECORTA a su hueco desde el principio de su tramo bueno (nunca se alarga: no entra nada malo)
    elegidas_grupo = {}
    k = 0
    while k < len(huecos):
        j = k
        while j + 1 < len(huecos) and momento_de[j + 1] == momento_de[k]:
            j += 1
        grupo = list(range(k, j + 1))
        largo = max(float(huecos[i]["dur"]) for i in grupo)
        try:
            piezas, _r = plan.zona([momento_de[k]], int(round(len(grupo) * largo * 1.08 * fps)),
                                   (largo, largo * 1.15), rng, True)
        except Exception:
            piezas = []
        piezas = [p for p in piezas if p.get("tipo") != "foto" and p.get("dur_f", 0) >= int(largo * fps) - 1]
        for i, p in zip(grupo, piezas):
            elegidas_grupo[i] = (p.get("item") or {}, float(p.get("ini") or 0.0), float(huecos[i]["dur"]))
        k = j + 1
    elegidas = []
    for n_h, (h, m) in enumerate(zip(huecos, momento_de)):
        if n_h in elegidas_grupo:
            elegidas.append(elegidas_grupo[n_h])
            continue
        dur = float(h["dur"])
        piezas = []
        anterior = elegidas[-1][0].get("nombre") if elegidas else None
        for momentos in ([m], list(zonas)):          # su momento; si no alcanza (o repite la de antes), cualquiera
            try:
                piezas, reusos = plan.zona(momentos, int(round(dur * fps)), (dur, dur * 1.0001), rng, True)
            except Exception:
                piezas, reusos = [], 0
            piezas = [p for p in piezas if p.get("tipo") != "foto"]
            if piezas and not reusos and (piezas[0].get("item") or {}).get("nombre") != anterior:
                break
        if not piezas:                               # sin tramo bueno de ese largo: la anterior otra vez (nunca
            if elegidas:                             # un hueco vacio: las tomas se correrian de sus huecos)
                it0, ini0, _d = elegidas[-1]
                elegidas.append((it0, ini0, dur))
            continue
        p = piezas[0]
        elegidas.append((p.get("item") or {}, float(p.get("ini") or 0.0), dur))
    elegidas = _orden_a_mano(elegidas, huecos, info["nombre"], log)
    for it_e, ini_e, dur_e in elegidas:                 # (1.8.7) para que las siguientes plantillas usen otras
        if it_e.get("ruta"):
            try:
                h_e = plan.huella(it_e, ini_e + dur_e / 2.0) if it_e.get("vista") else None
            except Exception:
                h_e = None
            _VARIEDAD["tomas"].append((it_e["ruta"], ini_e, ini_e + dur_e, h_e))
    final = None
    for ver, _tpl, _intro, zz in sorted(g.get("PLANES") or [], key=lambda x: -x[0].get("seg", 0)):
        if zz and zz[-1][3]:                         # el final de siempre: la mejor foto de la persona (o su plano)
            final = zz[-1][3][-1]
            break
    log("  plantilla: %d huecos, %d con un tramo bueno de su largo (%d tomas distintas): %s." % (
        len(huecos), len(elegidas), len({e[0].get("nombre") for e in elegidas}),
        " · ".join("%s %d" % (m.lower(), momento_de.count(m)) for m in zonas)))
    if con_g:
        return elegidas, final, g
    return elegidas, final


def id_toma(item, ini):
    """Como se reconoce una toma de la plantilla entre lo que se ve en Material y lo que se arma."""
    return "%s@%.1f" % ((item or {}).get("nombre", ""), float(ini or 0.0))


def _orden_a_mano(elegidas, huecos, clave, log=print):
    """(19-nov, la persona: «si son 10 tomas, 8 tomas, yo puedo mover las tomas que necesito») el orden que puso en
    «Qué entra al video» (estado orden_planos[nombre de la plantilla]). Cada HUECO conserva su duracion (son los cortes
    de la plantilla: nunca se agrega ni se quita uno); solo cambia que toma va en cada uno."""
    try:
        import motor
        orden = (motor.leer_estado().get("orden_planos") or {}).get(clave) or []
    except Exception:
        orden = []
    if not orden:
        return elegidas
    por_id = {}
    for e in elegidas:
        por_id.setdefault(id_toma(e[0], e[1]), []).append(e)
    nueva, usadas = [], set()
    for i in orden:
        if por_id.get(i):
            e = por_id[i].pop(0)
            nueva.append(e)
            usadas.add(id(e))
    nueva += [e for e in elegidas if id(e) not in usadas]
    out = []
    for (item, ini, _d), h in zip(nueva, huecos):
        dur = float(h["dur"])
        largo = float(item.get("dur") or 0.0)
        out.append((item, max(0.0, min(ini, largo - dur)) if largo > dur else ini, dur))
    log("  plantilla: en el orden que pusiste a mano.")
    return out


def plan_ventana(analisis, info, tipo_evento="xv"):
    """Para Material > «Qué entra al video»: los HUECOS de la plantilla (uno por corte) con la toma de cada uno y, al
    final, la foto que reemplaza al logo. [{"ruta","nombre","tipo","t","momento","id","dur"}]"""
    elegidas, final = elegir_tomas(analisis, info, tipo_evento, lambda *_a: None)
    planos = []
    for (item, ini, dur), h in zip(elegidas, info["planos"]):
        planos.append({"ruta": item.get("ruta"), "nombre": item.get("nombre"), "tipo": item.get("tipo"),
                       "t": round(float(h["ini"]), 1), "momento": item.get("momento") or "FIESTA",
                       "id": id_toma(item, ini), "dur": round(dur, 1)})
    if final is not None and float(info.get("final") or 0) > 0.5:
        it = final.get("item") or {}
        planos.append({"ruta": it.get("ruta"), "nombre": it.get("nombre"), "tipo": "foto",
                       "t": round(float(info["planos"][-1]["fin"]) if info["planos"] else 0, 1), "momento": "INTRO",
                       "id": "", "dur": round(float(info["final"]), 1)})
    return planos


def _elegir_tomas_antes(analisis, info, tipo_evento, log=print):
    """(la de antes: planos del plan alargados al hueco; se queda solo como referencia)"""
    import importlib.util
    s = importlib.util.spec_from_file_location("receta", rutas.codigo("receta.py"))
    receta = importlib.util.module_from_spec(s)
    s.loader.exec_module(receta)
    g = receta._planes(analisis, tipo_evento, "vertical" if info.get("vertical", True) else "horizontal")
    huecos = [p for p in info["planos"]]
    planes = []
    for ver, _tpl, _intro, zonas in g.get("PLANES") or []:
        # (visto en la boda) sin la APERTURA: es un resumen que mezcla momentos y la plantilla volvia al maquillaje
        # despues de la fiesta. Solo las zonas del dia, en su orden.
        piezas = [p for z, _a, _b, ps in zonas if z != "APERTURA" for p in ps if p.get("tipo") != "foto"]
        planes.append((ver.get("seg", 0), piezas))
    planes.sort(key=lambda x: x[0])
    piezas = next((ps for _s, ps in planes if len(ps) >= len(huecos)), planes[-1][1] if planes else [])
    if not piezas:
        raise RuntimeError("no hay tomas buenas para la plantilla")
    # repartidas a lo largo del dia: se toman a saltos parejos (sin repetir la misma toma seguida)
    n = len(huecos)
    paso = len(piezas) / float(n)
    elegidas, ultima = [], None
    for k in range(n):
        i = min(len(piezas) - 1, int(k * paso))
        p = piezas[i]
        if ultima is not None and (p.get("item") or {}).get("nombre") == ultima and i + 1 < len(piezas):
            p = piezas[i + 1]
        ultima = (p.get("item") or {}).get("nombre")
        item = p.get("item") or {}
        dur = float(huecos[k]["dur"])
        ini = float(p.get("ini") or 0.0)
        largo = float(item.get("dur") or 0.0)
        if largo > 0:
            # (visto) un fundido sin material de sobra a los lados pasaba por negro: MARGEN_S antes y despues
            ini = max(min(MARGEN_S, max(0.0, largo - dur) / 2.0), min(ini, largo - dur - MARGEN_S))
        elegidas.append((item, ini, dur))
    final = None
    for ver, _tpl, _intro, zonas in sorted(g.get("PLANES") or [], key=lambda x: -x[0].get("seg", 0)):
        if zonas and zonas[-1][3]:                   # el final de siempre: la mejor foto de la persona (o su plano)
            final = zonas[-1][3][-1]
            break
    log("  plantilla: %d huecos con %d tomas distintas (de un plan de %d planos)." % (
        n, len({e[0].get("nombre") for e in elegidas}), len(piezas)))
    return elegidas, final


def _medir_temblor(elegidas, info, log):
    """La correccion del estabilizador propio de cada toma en su hueco (en paralelo; lo medido queda guardado)."""
    try:
        import estabilizar as est
    except Exception as ex:
        log("  plantilla: sin estabilizador (%s)" % ex)
        return None, [None] * len(elegidas)
    from concurrent.futures import ThreadPoolExecutor

    def medir(par):
        (it, ini, _d), hueco = par
        if it.get("tipo") == "foto" or not it.get("ruta"):
            return None
        try:
            return est.calcular(it["ruta"], ini, float(hueco["fin"]) - float(hueco["ini"]), it.get("dur"))
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        medidas = list(ex.map(medir, zip(elegidas, info["planos"])))
    try:
        est.guardar()
    except Exception:
        pass
    return est, medidas


def _elegir_lentos(elegidas, info, medidas):
    """Los planos en camara lenta: huecos largos (no el primero), los de toma mas firme, 1 de cada 4 como mucho."""
    cand = [k for k, (_e, h) in enumerate(zip(elegidas, info["planos"]))
            if k > 0 and medidas[k] and float(h["fin"]) - float(h["ini"]) >= LENTO_MIN_S
            and (_e[0].get("tipo") != "foto")]
    cand.sort(key=lambda k: medidas[k].get("antes") or 0)
    return set(cand[:int(round(len(info["planos"]) * LENTO_PARTE))])


def _poner_lento(resolve, x):
    try:
        ok = bool(x.SetSpeed({"Percentage": round(LENTO_VEL * 100.0, 2), "PitchCorrection": False,
                              "StretchKeyframesToFit": False, "RippleTimeline": False}))
    except Exception:
        ok = False
    if ok:
        try:
            x.SetProperty("RetimeProcess", resolve.RETIME_OPTICAL_FLOW)
            x.SetProperty("MotionEstimation", resolve.MOTION_EST_SPEED_WARP_BETTER)
        except Exception:
            pass
    return ok


FRANJAS = (0.50, 0.30, 0.70, 0.22, 0.78)   # donde puede ir el titulo (desde arriba), en orden de preferencia
MEDIA_FRANJA = 0.08                         # medio alto del titulo (fraccion del alto)


def _cuadro_rgb(ruta, t, vertical):
    """El cuadro de la toma en el segundo t, como se ve en la linea (9:16 recortado al centro)."""
    import io
    import subprocess
    import numpy as np
    from PIL import Image
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % max(0.0, t), "-i", ruta,
                            "-frames:v", "1", "-vf", "scale=720:720:force_original_aspect_ratio=decrease",
                            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                           capture_output=True, timeout=60, creationflags=rutas.SIN_VENTANA)
        im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    prop = 9 / 16.0 if vertical else 16 / 9.0
    if w / float(h) > prop + 0.01:                   # mas ancho que la linea: se recorta a los lados
        nw = int(h * prop)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / float(h) < prop - 0.01:
        nh = int(w / prop)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return np.asarray(im)


def _franja_sin_caras(elegidas, info, lentos, ini_s, fin_s, log):
    """(19-nov, la persona: «siempre que no tape la cara el caption del intro») La altura (Fusion: 0 abajo, 1 arriba)
    donde el titulo no tapa ninguna cara de las tomas que hay debajo mientras se ve. None si no se pudo mirar."""
    try:
        import caras
        if not caras.disponible():
            return None
    except Exception:
        return None
    vertical = bool(info.get("vertical", True))
    cajas, mirados = [], 0
    for k, ((item, ini, _d), h) in enumerate(zip(elegidas, info["planos"])):
        h0, h1 = float(h["ini"]), float(h["fin"])
        a, b = max(h0, ini_s), min(h1, fin_s)
        if b <= a or item.get("tipo") == "foto" or not item.get("ruta"):
            continue
        for t in (a + (b - a) * x for x in (0.15, 0.5, 0.85)):
            if k in lentos:
                src = ini + (h1 - h0) * (1 - LENTO_VEL) / 2 + (t - h0) * LENTO_VEL
            else:
                src = ini + (t - h0)
            img = _cuadro_rgb(item["ruta"], src, vertical)
            if img is None:
                continue
            mirados += 1
            alto = float(img.shape[0])
            for c in caras.detectar(img):
                cajas.append((c[1] / alto, (c[1] + c[3]) / alto, c[3] / alto))
    if not mirados:
        return None

    def tapa(centro):
        f0, f1 = centro - MEDIA_FRANJA, centro + MEDIA_FRANJA
        return sum(max(0.0, min(f1, y1 + 0.03) - max(f0, y0 - 0.03)) * (1 + 4 * hh) for y0, y1, hh in cajas)
    mejor = min(FRANJAS, key=lambda c: (round(tapa(c), 3), FRANJAS.index(c)))
    log("  plantilla: título %s (%d caras en %d cuadros del inicio%s)." % (
        {0.5: "al centro", 0.3: "arriba", 0.22: "arriba", 0.7: "abajo", 0.78: "abajo"}[mejor], len(cajas), mirados,
        "" if tapa(mejor) == 0 else "; ninguna franja quedaba libre del todo, va donde menos tapa"))
    return 1.0 - mejor


def _mover_titulo(it, y):
    comp = it.GetFusionCompByIndex(1)
    if comp is None:
        return
    for nombre in ("Template", "VeloForma"):
        tool = comp.FindTool(nombre)
        if tool is not None:
            try:
                tool.SetInput("Center", {1: 0.5, 2: y, 3: 0.0})
            except Exception:
                pass


def _textos(g, tipo_evento, nombre_xv, frase, analisis):
    """(nombre, subtitulo) del titulo del inicio, como el TEXTO NOMBRE de las versiones."""
    try:
        perfil = g["cargar_perfil"](tipo_evento)
    except Exception:
        perfil = {}
    anio = str(analisis.get("fecha") or "")[:4]

    def fmt(s):
        return (s or "").replace("{nombre}", nombre_xv).replace("{fecha}", "").replace("{anio}", anio).strip(" ·-")
    nombre = nombre_xv or fmt(perfil.get("titulo"))
    sub = fmt(frase) or (fmt(perfil.get("frase")) if nombre_xv else "")
    return nombre, sub


def _de_cabeza(item):
    """(1.8.7) La toma se ve de cabeza en DaVinci (la misma regla que build_trailers.de_cabeza: la orientacion medida de
    lo que se ve; sin medida, la rotacion de 180 del archivo). Antes las plantillas no la giraban."""
    g = (item or {}).get("girar")
    if g is not None:
        return g == 180
    try:
        return abs(int(float((item or {}).get("rotacion") or 0))) % 360 == 180
    except (TypeError, ValueError):
        return False


def _centrar_aereo(x, item, t, ancho, alto):
    """(1.8.7) Una toma de dron horizontal en la plantilla 9:16 llena la altura y solo se ve su franja del centro (un
    tercio del ancho): con la iglesia a un lado se veia el cielo o los techos (la persona, 20-nov: «hay tomas aéreas que
    no apuntan a nada... centra al objeto que se está grabando»). La IA local de vista (encuadre.sujeto_aereo) ubica lo
    importante y la imagen se corre para dejarlo al centro, sin descubrir bordes. True si la movio."""
    try:
        import encuadre
        s = encuadre.sujeto_aereo(item["ruta"], t)
        if not s:
            return False
        w, h = float(item.get("ancho") or 16), float(item.get("alto") or 9)
        img_w = alto * max(w, h) / min(w, h)              # Fill: la altura de la linea manda, el ancho sobra
        holgura = max(0.0, (img_w - ancho) / 2.0)
        pan = max(-holgura, min(holgura, (0.5 - s[0]) * img_w))   # DaVinci: Pan = posicion X (derecha +)
        if abs(pan) < 0.03 * ancho:                       # ya estaba al centro
            return False
        return bool(x.SetProperty("Pan", round(pan, 1)))
    except Exception:
        return False


def armar(resolve, project, info, evento, analisis, salida, tipo_evento="xv", log=print, nombre_archivo=None,
          nombre_xv="", frase="", con_texto=True, con_destellos=True, con_fundidos=True):
    """Arma la linea de la plantilla y deja su render en cola. Devuelve el nombre de la linea."""
    t0 = time.time()
    mp = project.GetMediaPool()
    root = mp.GetRootFolder()
    nombre = "%s - %s%s" % (evento, info["nombre"], "" if info.get("vertical", True) else " HORIZONTAL")
    fps = float(info.get("fps") or 30.0)
    ancho, alto = (1080, 1920) if info.get("vertical", True) else (1920, 1080)
    elegidas, final, g = elegir_tomas(analisis, info, tipo_evento, log, con_g=True)
    t_med = time.time()
    est, medidas = _medir_temblor(elegidas, info, log)
    lentos = _elegir_lentos(elegidas, info, medidas)
    log("  plantilla: temblor medido en %d tomas (%.0f s); %d en cámara lenta." % (
        sum(1 for m in medidas if m), time.time() - t_med, len(lentos)))
    # la linea anterior de esta plantilla (rearmar): fuera
    viejas = [project.GetTimelineByIndex(i) for i in range(1, project.GetTimelineCount() + 1)
              if project.GetTimelineByIndex(i).GetName() == nombre]
    if viejas:
        mp.DeleteTimelines(viejas)
    eventos = next((f for f in root.GetSubFolderList() or [] if "EVENTOS" in f.GetName()), root)
    mp.SetCurrentFolder(_carpeta(mp, eventos, evento))
    tl = mp.CreateEmptyTimeline(nombre)
    if tl is None:
        raise RuntimeError("DaVinci no creó la línea %s" % nombre)
    project.SetCurrentTimeline(tl)
    for k, v in (("useCustomSettings", "1"), ("timelineResolutionWidth", str(ancho)),
                 ("timelineResolutionHeight", str(alto)), ("timelineFrameRate", ("%g" % fps)),
                 ("timelineOutputResolutionWidth", str(ancho)), ("timelineOutputResolutionHeight", str(alto))):
        tl.SetSetting(k, v)
    fps = float(tl.GetSetting("timelineFrameRate") or fps)
    st = tl.GetStartFrame()
    # los clips del evento que hacen falta (ya estan en el media pool; si no, se importan)
    por_ruta = {os.path.normcase(c.GetClipProperty("File Path") or ""): c for c in _clips(root)}
    faltan = [it.get("ruta") for it, _a, _b in elegidas if it.get("ruta") and os.path.normcase(it["ruta"]) not in por_ruta]
    if faltan:
        mp.SetCurrentFolder(_carpeta(mp, root, "03 VIDEO"))
        for c in mp.ImportMedia(sorted(set(faltan))) or []:
            por_ruta[os.path.normcase(c.GetClipProperty("File Path") or "")] = c
    # 1) las tomas, cada una en su hueco
    puestos, pos_f, a_estabilizar, n_lentos, n_centradas = [], 0, [], 0, 0
    con_toma = []                                 # (clip, toma, segundo de origen, segundos de origen) para color y ruido
    for k, ((item, ini, dur), hueco) in enumerate(zip(elegidas, info["planos"])):
        c = por_ruta.get(os.path.normcase(item.get("ruta") or ""))
        largo_f = int(round(float(hueco["fin"]) * fps)) - pos_f
        if c is None or largo_f < 2:
            pos_f += max(0, largo_f)
            continue
        sfps = float(c.GetClipProperty("FPS") or fps)
        lento = k in lentos
        if lento:
            # (19-nov, probado) SetSpeed conserva el largo en la linea y usa menos fuente desde el inicio (con la
            # mitad de fuente quedaba medio hueco negro): se pone el hueco entero empezando donde se centra lo que se ve
            hueco_s = largo_f / fps
            a = int((ini + hueco_s * (1 - LENTO_VEL) / 2) * sfps)
            b = a + int(round(largo_f * sfps / fps))
        else:
            a = int(ini * sfps)
            # (18-nov, probado) endFrame NO entra: con «- 1» cada toma quedaba 1 cuadro corta y en cada corte habia un
            # cuadro negro (en los fundidos se veia oscuro)
            b = a + int(round(largo_f * sfps / fps))
        r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": a, "endFrame": b, "mediaType": 1,
                                  "trackIndex": PISTA_V, "recordFrame": st + pos_f}]) or []
        if r:
            x = r[0]
            puestos.append((x, hueco))
            try:                                  # (19-nov) el dron horizontal llena el 9:16 (sin franjas negras)
                if not x.SetProperties({"Scaling": resolve.SCALE_FILL}):
                    x.SetProperty("Scaling", resolve.SCALE_FILL)
            except Exception:
                pass
            if _de_cabeza(item):                  # (1.8.7) se ve de cabeza (orientacion medida): se gira
                try:
                    x.SetProperty("RotationAngle", 180.0)
                except Exception:
                    pass
            if alto > ancho and item.get("tipo") == "dron" and item.get("horizontal", True) and \
                    _centrar_aereo(x, item, (a + b) / (2.0 * sfps), ancho, alto):
                n_centradas += 1
            con_toma.append((x, item, a / sfps, (b - a) / sfps))
            if lento and _poner_lento(resolve, x):
                n_lentos += 1
                if x.GetDuration() != largo_f:          # el hueco exacto: ni se come el siguiente ni deja negro
                    log("  plantilla: plano lento %d quedó de %d cuadros (hueco %d)." % (k + 1, x.GetDuration(), largo_f))
            elif est is not None and medidas[k]:
                a_estabilizar.append((x, medidas[k], ini))
        pos_f += largo_f
    # 2) el final con logo: la foto / el plano del final de siempre
    final_f = int(round(float(info.get("dur") or 0) * fps)) - pos_f
    if final_f > fps and final is not None:
        c = por_ruta.get(os.path.normcase((final.get("item") or {}).get("ruta") or ""))
        if c is None and (final.get("item") or {}).get("ruta"):
            r_imp = mp.ImportMedia([final["item"]["ruta"]]) or []
            c = r_imp[0] if r_imp else None
        if c is not None:
            es_foto = (final.get("item") or {}).get("tipo") == "foto"
            if es_foto:
                # (visto) una foto en la linea dura lo que dice DaVinci (~1,5 s) aunque se pida mas: se pone seguida
                # hasta llenar el final (es la misma imagen: no se ve el corte)
                hecho, primero = 0, None
                while hecho < final_f:
                    r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": final_f - hecho,
                                              "mediaType": 1, "trackIndex": PISTA_V,
                                              "recordFrame": st + pos_f + hecho}]) or []
                    if not r or r[0].GetDuration() < 1:
                        break
                    primero = primero or r[0]
                    hecho += r[0].GetDuration()
                    puestos.append((r[0], {"entra": "fundido" if r[0] is primero else "corte"}))
            else:
                sfps = float(c.GetClipProperty("FPS") or fps)
                a = int(float(final.get("ini") or 0) * sfps)
                r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": a, "endFrame": a + int(final_f * sfps / fps),
                                          "mediaType": 1, "trackIndex": PISTA_V, "recordFrame": st + pos_f}]) or []
                if r:
                    puestos.append((r[0], {"entra": "fundido"}))
    # 3) la musica de la plantilla, entera
    musica = os.path.join(info["carpeta"], "musica.m4a")
    if not (os.path.exists(musica) and os.path.getsize(musica) >= 1000):      # (1.8.0) que no salga muda sin avisar
        log("Aviso: la plantilla «%s» no tiene su música: el video sale sin canción." % info.get("nombre", ""))
    elif os.path.exists(musica):
        mp.SetCurrentFolder(_carpeta(mp, _carpeta(mp, root, "05 MUSICA"), "PLANTILLAS"))
        m = mp.ImportMedia([musica]) or []
        if m:
            mf = int(round(float(info.get("dur") or 0) * fps))
            mp.AppendToTimeline([{"mediaPoolItem": m[0], "startFrame": 0, "endFrame": mf, "mediaType": 2,
                                  "trackIndex": PISTA_A, "recordFrame": st}])
    # 3b) estabilizador propio (ANTES del primer render del clip: DaVinci reusa lo ya renderizado)
    n_est = 0
    for x, c, ini in a_estabilizar:
        try:
            if est.aplicar(x, c, fps, ini, log=log):
                n_est += 1
        except Exception:
            pass
    # 3c) el titulo con los nombres al inicio (encima de todo; los brillos de overlays lo buscan por su nombre)
    titulo = ""
    try:
        p1, p2 = _textos(g, tipo_evento, nombre_xv, frase, analisis)
        if p1 and con_texto:
            tl.AddTrack("video")
            pt = tl.GetTrackCount("video")
            tl.SetTrackName("video", pt, "TEXTOS")
            png = g["png_texto"](mp, root, bool(info.get("vertical", True)))
            total_s = float(info.get("dur") or 0)
            d = int(min(TITULO_MAX_S, max(2.0, total_s * TITULO_PARTE)) * fps)
            if png is not None and g["nuevo_texto"](tl, mp, png, pt, int(TITULO_INI_S * fps), d, "TEXTO NOMBRE XV",
                                                      p1, "", False, fps):     # solo los nombres
                titulo = p1
                y = _franja_sin_caras(elegidas, info, lentos, TITULO_INI_S, TITULO_INI_S + d / fps, log)
                if y is not None and abs(y - 0.5) > 0.01:
                    for it_ in tl.GetItemListInTrack("video", pt) or []:
                        _mover_titulo(it_, y)
    except Exception as ex:
        log("  plantilla: sin título de nombres (%s)" % ex)
    # 4) como cambia de plano
    fundidos = destellos = 0
    cortes_destello = []
    for it, hueco in puestos[1:]:
        entra = hueco.get("entra")
        if entra == "fundido" and con_fundidos:   # (19-nov) apagado en Material: corte seco
            for al in ("center", "right", "left"):
                try:
                    if it.AddTransition({"type": "Cross Dissolve", "category": "simple", "position": "start",
                                         "alignment": al, "duration": FUNDIDO_F}):
                        fundidos += 1
                        break
                except Exception:
                    pass
        elif entra == "destello" and con_destellos:     # apagado en Material: corte seco
            cortes_destello.append(it.GetStart() - st)
    # (19-nov, la persona: «satura mucho en el inicio... solo un caption elegante, sin tanto brillo») el titulo va
    # SIN brillos y ningun destello lo tapa
    if titulo:
        fin_titulo = int((TITULO_INI_S + TITULO_MAX_S) * fps) + int(0.5 * fps)
        cortes_destello = [c for c in cortes_destello if c > fin_titulo]
        for it_ in tl.GetItemListInTrack("video", tl.GetTrackCount("video")) or []:
            if (it_.GetName() or "").upper().startswith("TEXTO NOMBRE"):
                it_.SetName("TEXTO PLANTILLA")          # overlays.poner busca «TEXTO NOMBRE» para los brillos
    if cortes_destello:
        try:
            import overlays
            efe = _carpeta(mp, root, "06 EFECTOS")
            dir_ov = _carpeta(mp, efe, "OVERLAYS")
            destellos = sum(1 for e, _s in overlays.poner(resolve, tl, mp, dir_ov, fps, tipo_evento, info.get("vertical", True),
                                           cortes_destello, log) if e == "DESTELLO")
            # (19-nov, la persona: «sin tanto brillo») los destellos de la plantilla, mas suaves que en las versiones
            for v in range(1, tl.GetTrackCount("video") + 1):
                if (tl.GetTrackName("video", v) or "").strip().upper() == overlays.PISTA:
                    for it_ in tl.GetItemListInTrack("video", v) or []:
                        try:
                            it_.SetProperty("Opacity", DESTELLO_OPACIDAD)
                        except Exception:
                            pass
        except Exception as ex:
            log("  plantilla: no se pudieron poner los destellos (%s)" % ex)
    # 5a) (19-nov, la persona: «aplica reducción de ruido y mejorar el color de la toma... sin saturación, reglas de
    # que no sature o exponga demasiado») lo mismo que las versiones: el ruido medido de cada toma con su nivel y el
    # CDL por plano de build_trailers.cdl_para (exposicion hacia la luz de su momento con topes, negros limpios,
    # balance con los grises; la saturacion SOLO baja, nunca pasa la de camara)
    n_ruido = n_color = 0
    try:
        import ruido as rd
        import motor
        intensidad = motor.leer_estado().get("ruido")
        intensidad = int(intensidad) if intensidad is not None else rd.DEFECTO
        rd.escribir(intensidad, os.path.join(rutas.DATOS, "dctl"))
        project.RefreshLUTList()
        drx = rd.drx_activo(intensidad)
        medidas = {}
        if intensidad > 0 and not drx:
            try:
                import ruido_tomas
                medidas = ruido_tomas.medir_varios(sorted({(it_.get("ruta"), None) for _x, it_, _a, _d in con_toma
                                                           if it_.get("ruta")}), log)
            except Exception as ex:
                log("  plantilla: ruido sin medir (%s); nivel normal." % ex)
        items = list(analisis.get("items") or [])
        objetivos = g["objetivos_de_luz"](items)
        sat_evento = g["objetivo_de_saturacion"](items)
        # (1.8.2) la MISMA revision de color que las versiones (color_guardia): cada plano medido con forma de onda y
        # vectorscopio antes de ponerle su CDL; si quema, aplasta negros, satura o tiñe, se suaviza
        cdls, vigilados = {}, {}
        for x, it_, a_s, d_s in con_toma:
            if it_.get("tipo") != "foto":
                c0 = g["cdl_para"]({"item": it_, "tipo": it_.get("tipo"), "ini": a_s, "dur_f": d_s * 24.0},
                                   objetivos.get(it_.get("momento"), 0.42), sat_evento)
                if c0:
                    cdls[id(x)] = c0
        try:
            import color_guardia
            imgs = color_guardia.cuadros([(it_.get("ruta"), round(a_s + d_s / 2.0, 1)) for x, it_, a_s, d_s in con_toma
                                          if id(x) in cdls])
            trabajos = {id(x): (cdls[id(x)], imgs.get((it_.get("ruta"), round(a_s + d_s / 2.0, 1))))
                        for x, it_, a_s, d_s in con_toma if id(x) in cdls}
            for k, (c, f, _t) in color_guardia.vigilar_varios(
                    {k: v for k, v in trabajos.items() if v[1] is not None},
                    os.path.join(rutas.PROGRAMA, "dctl", os.path.basename(LOOK))).items():
                cdls[k] = c
                if f:
                    vigilados[k] = f
        except Exception as ex:
            log("  plantilla: color sin medir (%s); va el calculado." % ex)
        for x, it_, a_s, d_s in con_toma:
            if it_.get("tipo") == "foto":
                continue
            try:
                if rd.aplicar(x, intensidad, medidas.get(os.path.normcase(it_.get("ruta") or "")), drx) is not None:
                    n_ruido += 1
                cdl = cdls.get(id(x))
                if cdl and x.SetCDL(cdl):
                    n_color += 1
            except Exception:
                pass
        if vigilados:
            log("  plantilla: color medido plano por plano, %d con la corrección suavizada." % len(vigilados))
    except Exception as ex:
        log("  plantilla: sin ruido ni color por toma (%s)" % ex)
    # 5) color: correccion por plano y look suave, en su grupo
    try:
        grupo = next((g for g in project.GetColorGroupsList() or [] if g.GetName() == GRUPO), None) or \
            project.AddColorGroup(GRUPO)
        pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
        pre.SetLUT(1, DCTL_COLOR)
        post.SetLUT(1, LOOK)
        pre.SetNodeLabel(1, "1 BASE (TODAS LAS TOMAS)")         # (1.8.2) como las versiones: el orden de la cadena
        post.SetNodeLabel(1, "3 LOOK CINE TEAL ORANGE (SIN QUEMAR NI SATURAR)")
        for it, _h in puestos:
            it.AssignToColorGroup(grupo)
    except Exception as ex:
        log("  plantilla: color sin grupo (%s)" % ex)
    # 6) render en cola, como las demas lineas
    total = int(round(float(info.get("dur") or 0) * fps))
    tl.SetMarkInOut(st, st + total - 1, "all")
    os.makedirs(salida, exist_ok=True)
    for job in project.GetRenderJobList() or []:
        if job.get("TimelineName") == nombre:
            project.DeleteRenderJob(job.get("JobId"))
    project.SetRenderSettings({"SelectAllFrames": False, "MarkIn": st, "MarkOut": st + total - 1, "TargetDir": salida,
                               "CustomName": nombre_archivo or rutas.nombre_video(nombre), "FormatWidth": ancho,
                               "FormatHeight": alto})
    en_cola = bool(project.AddRenderJob())
    if info.get("vertical", True):
        project.SetRenderSettings({"FormatWidth": 1920, "FormatHeight": 1080})     # Entrega vuelve a lo de siempre
    log("%s lista: %d planos con la musica de la plantilla, %d fundidos y %d destellos como ella, %d estabilizados, "
        "%d en cámara lenta, %d aéreas centradas, %d con color por toma, %d sin ruido, título «%s»%s (%.0f s)." % (
            nombre, len(puestos), fundidos, destellos, n_est, n_lentos, n_centradas, n_color, n_ruido, titulo or "—",
            "" if en_cola else "; NO quedo en la cola de render", time.time() - t0))
    return nombre
