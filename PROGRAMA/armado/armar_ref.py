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
import re
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
DESTELLO_CALIDO_OPACIDAD = 90.0        # (1.9.6) la luz calida de «denis y iris» se ve como en la referencia
LENTO_PARTE = 0.25                     # como mucho 1 de cada 4 planos, los mas firmes
_POR_RUTA = {}                         # (1.9.3) {ruta: clip} del media pool, uno por armado (rutas._armado_id)


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


def _medir_vertical(elegidas, info, lentos, analisis, tipo_evento, log):
    """(1.9.1, la persona: «si escojo plantillas, igual armas con lo de video en horizontal adaptado a vertical para
    llenar las plantillas; pule más eso») La franja 9:16 de cada toma HORIZONTAL (vertical.py: la festejada al centro,
    sin cortar caras): (modulo, [camino o None por hueco]). Los lentos, fijos (Speed Warp + un comp que se mueve no se
    probo); los demas siguen a la persona si el hueco es largo."""
    vacio = [None] * len(elegidas)
    if not info.get("vertical", True):
        return None, vacio
    try:
        import vertical as vt
    except Exception as ex:
        log("  plantilla: sin encuadre vertical (%s)" % ex)
        return None, vacio
    from concurrent.futures import ThreadPoolExecutor
    if any(e[0].get("tipo") == "video" and e[0].get("horizontal", True) for e in elegidas):
        vt.preparar(log=log)                      # la IA de vista en la GPU (si cabe) y su presupuesto de tiempo
    ps = vt.protas(analisis.get("items") or [], tipo_evento)

    def medir(k):
        it, ini, h = elegidas[k][0], elegidas[k][1], info["planos"][k]
        if it.get("tipo") != "video" or not it.get("horizontal", True) or not it.get("ruta") or _de_cabeza(it):
            return None
        hueco_s = float(h["fin"]) - float(h["ini"])
        if k in lentos:                           # lo que se ve en camara lenta: la mitad del centro (ver armar)
            ini_s, dur_s = ini + hueco_s * (1 - LENTO_VEL) / 2.0, hueco_s * LENTO_VEL
        else:
            ini_s, dur_s = ini, hueco_s
        fr = vt.franja(float(it.get("ancho") or 1920), float(it.get("alto") or 1080), 1080, 1920)
        try:
            return vt.camino(vt.medir(it, ini_s, dur_s, ps, tipo_evento), fr, hueco_s, mover=k not in lentos)
        except Exception:
            return None
    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        cams = list(ex.map(medir, range(len(elegidas))))
    vt.guardar()
    horiz = [c for (it, _i, _d), c in zip(elegidas, cams) if it.get("tipo") == "video" and it.get("horizontal", True)]
    if horiz:
        log("  plantilla: %d tomas horizontales en 9:16 (%.0f s): %s." % (len(horiz), time.time() - t0,
                                                                          vt.resumen(horiz)))
    return vt, cams


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
            # (1.9.3, medido: Faster tarda la mitad y no se ve diferencia; build_trailers.SPEED_WARP_MEJOR)
            mejor = os.environ.get("TRAILER_SPEED_WARP", "").lower() == "better"
            x.SetProperty("MotionEstimation", resolve.MOTION_EST_SPEED_WARP_BETTER if mejor else
                          getattr(resolve, "MOTION_EST_SPEED_WARP_FASTER", resolve.MOTION_EST_SPEED_WARP_BETTER))
        except Exception:
            pass
    return ok


FRANJAS = (0.50, 0.30, 0.70, 0.22, 0.78)   # donde puede ir el titulo (desde arriba), en orden de preferencia
MEDIA_FRANJA = 0.08                         # medio alto del titulo (fraccion del alto)


def _cuadro_rgb(ruta, t, vertical, centro=0.5):
    """El cuadro de la toma en el segundo t, como se ve en la linea (9:16: la franja de `centro`, de 0 a 1 del ancho;
    1.9.1, vertical.py la corre a lo importante)."""
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
        x0 = max(0, min(w - nw, int(round(centro * w - nw / 2.0))))
        im = im.crop((x0, 0, x0 + nw, h))
    elif w / float(h) < prop - 0.01:
        nh = int(w / prop)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return np.asarray(im)


def _franja_sin_caras(elegidas, info, lentos, ini_s, fin_s, log, centros=None):
    """(19-nov, la persona: «siempre que no tape la cara el caption del intro») La altura (Fusion: 0 abajo, 1 arriba)
    donde el titulo no tapa ninguna cara de las tomas que hay debajo mientras se ve. None si no se pudo mirar.
    centros: la franja 9:16 de cada toma (1.9.1: las horizontales ya no se ven al centro)."""
    try:
        import caras
        if not caras.disponible():
            return None
    except Exception:
        return None
    vertical = bool(info.get("vertical", True))
    cajas, mirados, pedidos = [], 0, []
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
            pedidos.append((item["ruta"], src, vertical, (centros or {}).get(k, 0.5)))
    # (23-nov, MEDIDO: 4-8 s por plantilla sacando estos cuadros uno tras otro) ffmpeg a la vez; las caras, en orden
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        imagenes = list(ex.map(lambda p: _cuadro_rgb(*p), pedidos))
    for img in imagenes:
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
    vt, cams = _medir_vertical(elegidas, info, lentos, analisis, tipo_evento, log)     # (1.9.1) horizontal en 9:16
    a_mover = []                                  # (clip, camino, segundo de la toma, zoom del estabilizador, franja)
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
        # (23-nov, MEDIDO en DaVinci, scratch probar_ajustes.py) NO se gana mirando antes con GetSetting: poner un valor
        # que ya esta es gratis (0,00 s); lo que tarda es el cambio de verdad (useCustomSettings 0,3 s, ancho 0,2, alto
        # 0,5) y la llamada SIGUIENTE, sea cual sea, espera ~0,3 s a que la linea se asiente (probado: 16,7 s contra 14,3)
        tl.SetSetting(k, v)
    fps = float(tl.GetSetting("timelineFrameRate") or fps)
    try:                                          # (1.9.6) las franjas de cine de la referencia («denis y iris»)
        m = re.match(r"crop=(\d+):(\d+):(\d+):(\d+)", info.get("franjas") or "")
        if m and info.get("alto"):
            _w, h_c, _x, y_c = (int(v) for v in m.groups())
            k = alto / float(info["alto"])
            arriba, abajo = int(round(y_c * k)), int(round((info["alto"] - h_c - y_c) * k))
            # (MEDIDO) la API pide los BORDES de lo que se ve, no margenes: sin franjas da {Top 0, Bottom 1080,
            # Left 0, Right 1920}; {Bottom 118, Right 0} dejaba la imagen vacia y el video salia NEGRO entero
            if arriba + abajo >= 8 and tl.SetOutputBlanking({"Top": arriba, "Bottom": alto - abajo, "Left": 0,
                                                             "Right": ancho}):
                log("  plantilla: franjas de cine como la referencia (%d px arriba, %d abajo)." % (arriba, abajo))
    except Exception as ex:
        log("  plantilla: no se pudieron poner las franjas (%s)" % ex)
    st = tl.GetStartFrame()
    # los clips del evento que hacen falta (ya estan en el media pool; si no, se importan)
    # (1.9.3, MEDIDO: el pool entero en cada plantilla, 3 s de GetClipProperty al rearmar) un recorrido por armado
    marca = (project.GetName(), getattr(rutas, "_armado_id", None))
    if marca[1] and _POR_RUTA.get("marca") == marca:
        por_ruta = _POR_RUTA["clips"]
    else:
        por_ruta = {os.path.normcase(c.GetClipProperty("File Path") or ""): c for c in _clips(root)}
        _POR_RUTA.update(marca=marca, clips=por_ruta)
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
            zs = 1.0                              # lo que acerca el estabilizador (la franja se mide sin el)
            if lento and _poner_lento(resolve, x):
                n_lentos += 1
                if x.GetDuration() != largo_f:          # el hueco exacto: ni se come el siguiente ni deja negro
                    log("  plantilla: plano lento %d quedó de %d cuadros (hueco %d)." % (k + 1, x.GetDuration(), largo_f))
            elif est is not None and medidas[k]:
                a_estabilizar.append((x, medidas[k], ini))
                zs = float(medidas[k].get("zoom") or 1.0)
            cam = cams[k] if vt is not None else None
            if cam:                               # (1.9.1) la toma horizontal: la franja de lo importante
                fr = vt.franja(float(item.get("ancho") or 1920), float(item.get("alto") or 1080), ancho, alto)
                if "fija" in cam:
                    try:
                        x.SetProperty("Pan", vt.pan_para(cam["fija"], float(item.get("ancho") or 1920),
                                                         float(item.get("alto") or 1080), ancho, alto, 1.0, zs))
                    except Exception:
                        pass
                else:                             # se mueve: va en Fusion, detras del estabilizador (3b)
                    a_mover.append((x, cam, ini, zs, fr))
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
    n_mov = 0                                     # (1.9.1) la franja 9:16 que sigue a la persona, despues
    for x, cam, ini, zs, fr in a_mover:
        try:
            vel = est.velocidad(x) if est is not None else 1.0
            n_mov += bool(vt.aplicar_camino(x, cam, fps, ini, vel, zs, 1.0, fr, log))
        except Exception:
            pass
    if a_mover:
        log("  plantilla: %d de %d tomas siguen a la persona en el 9:16." % (n_mov, len(a_mover)))
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
                y = _franja_sin_caras(elegidas, info, lentos, TITULO_INI_S, TITULO_INI_S + d / fps, log,
                                      {k: vt.centro_medio(c) for k, c in enumerate(cams) if c} if vt else None)
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
            # (1.9.6) lo que dura el fundido en la referencia («trans», s); si no cabe en el material, el de siempre
            largo = int(round(float(hueco.get("trans") or 0) * fps)) or FUNDIDO_F
            hecho = False
            for dur_t in dict.fromkeys((largo, max(FUNDIDO_F, largo // 2), FUNDIDO_F)):
                for al in ("center", "right", "left"):
                    try:
                        if it.AddTransition({"type": "Cross Dissolve", "category": "simple", "position": "start",
                                             "alignment": al, "duration": dur_t}):
                            fundidos += 1
                            hecho = True
                            break
                    except Exception:
                        pass
                if hecho:
                    break
            if hueco.get("luz") and con_destellos:     # (1.9.6) la luz entra DURANTE el fundido, como la referencia
                cortes_destello.append(it.GetStart() - st)
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
            # (1.9.6) la referencia con luz en los fundidos («denis y iris»): luz calida que cruza, no la raya de lente
            calido = any(p.get("luz") for p in info.get("planos") or [])
            destellos = sum(1 for e, _s in overlays.poner(resolve, tl, mp, dir_ov, fps, tipo_evento, info.get("vertical", True),
                                           cortes_destello, log, calido=calido) if e == "DESTELLO")
            # (19-nov, la persona: «sin tanto brillo») los destellos de la plantilla, mas suaves que en las versiones
            for v in range(1, tl.GetTrackCount("video") + 1):
                if (tl.GetTrackName("video", v) or "").strip().upper() == overlays.PISTA:
                    for it_ in tl.GetItemListInTrack("video", v) or []:
                        try:
                            it_.SetProperty("Opacity", DESTELLO_CALIDO_OPACIDAD if calido else DESTELLO_OPACIDAD)
                        except Exception:
                            pass
        except Exception as ex:
            log("  plantilla: no se pudieron poner los destellos (%s)" % ex)
    # 5a) (19-nov, la persona: «aplica reducción de ruido y mejorar el color de la toma... sin saturación, reglas de
    # que no sature o exponga demasiado») lo mismo que las versiones: el ruido medido de cada toma con su nivel y el
    # CDL por plano de build_trailers.cdl_para (exposicion hacia la luz de su momento con topes, negros limpios,
    # balance con los grises; la saturacion SOLO baja, nunca pasa la de camara)
    n_ruido = n_color = n_bn = 0
    look_ref_lut, look_bn_lut, imgs = None, None, {}
    try:
        import ruido as rd
        import motor
        intensidad = motor.leer_estado().get("ruido")
        intensidad = int(intensidad) if intensidad is not None else rd.DEFECTO
        rd.escribir(intensidad, os.path.join(rutas.DATOS, "dctl"))
        project.RefreshLUTList()
        drx = rd.drx_activo(intensidad)
        medidas = {}
        if intensidad > 0:                       # (1.9.6) tambien con el de DaVinci: decide a que tomas va
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
        hueco_de = {id(it): h for it, h in puestos}
        for x, it_, a_s, d_s in con_toma:
            if it_.get("tipo") == "foto":
                continue
            try:
                # (1.9.6) la plantilla del tráiler: filtro «nítido» (mas nitidez y claridad, como las fotos del evento)
                if rd.aplicar(x, intensidad, medidas.get(os.path.normcase(it_.get("ruta") or "")), drx,
                              nitido=bool(info.get("color_ref"))) is not None:
                    n_ruido += 1
                cdl = cdls.get(id(x))
                if (hueco_de.get(id(x)) or {}).get("bn"):     # (1.9.6) en blanco y negro como la referencia
                    cdl = dict(cdl or {"NodeIndex": "1", "Slope": "1 1 1", "Offset": "0 0 0", "Power": "1 1 1"},
                               Saturation="0")
                    n_bn += 1
                if cdl and x.SetCDL(cdl):
                    n_color += 1
            except Exception:
                pass
        # (1.9.6, «pule más, no es igual al ejemplo») el COLOR de la referencia: una LUT que lleva la luz, el contraste
        # y el tono de estas tomas (con su CDL) a los de la referencia (look_ref), en el grupo de ESTA plantilla
        if info.get("color_ref"):
            try:
                import look_ref
                fotos = [look_ref.aplicar_cdl(imgs[(it_.get("ruta"), round(a_s + d_s / 2.0, 1))], cdls.get(id(x)) or {})
                         for x, it_, a_s, d_s in con_toma
                         if imgs.get((it_.get("ruta"), round(a_s + d_s / 2.0, 1))) is not None
                         and not (hueco_de.get(id(x)) or {}).get("bn")]
                ev = look_ref.estadisticas(fotos)
                # (1.9.6, la persona: «mejora el color COMO LA FOTO DEL EVENTO, con esa claridad y nitidez») el
                # objetivo son las FOTOS de este evento (editadas, claras y limpias); si no hay, el de la referencia
                meta, de_que = look_ref.de_fotos(analisis.get("items") or []), "las fotos del evento"
                if not meta:
                    meta, de_que = info["color_ref"], "la referencia"
                # (1.9.6, la persona: «mejora el blanco y negro») los planos en blanco y negro con SU LUT: neutra, con la
                # luz y el contraste de los de la referencia (antes: CDL sin color + la LUT de color = gris plano teñido)
                fotos_bn = [look_ref.aplicar_cdl(imgs[(it_.get("ruta"), round(a_s + d_s / 2.0, 1))], cdls.get(id(x)) or {})
                            for x, it_, a_s, d_s in con_toma
                            if imgs.get((it_.get("ruta"), round(a_s + d_s / 2.0, 1))) is not None
                            and (hueco_de.get(id(x)) or {}).get("bn")]
                ev_bn = look_ref.estadisticas(fotos_bn) if fotos_bn else None
                if ev_bn:
                    ref_bn = info["color_ref"].get("bn") or {"media": [40.0, 0, 0], "desv": [26.0, 0, 0]}
                    nombre_bn = "REF_%s_BN.cube" % re.sub(r"[^\w]+", "_", "%s %s" % (info.get("nombre"), evento)).strip("_")
                    look_ref.escribir_lut_bn(ev_bn, ref_bn, os.path.join(rutas.DIR_LUT_MCP, nombre_bn))
                    look_bn_lut = "MCP/" + nombre_bn
                    log("  plantilla: blanco y negro de cine (luz %.0f -> %.0f, contraste %.0f -> %.0f, neutro)." % (
                        ev_bn["media"][0], ref_bn["media"][0], ev_bn["desv"][0], ref_bn["desv"][0]))
                if ev:
                    nombre_lut = "REF_%s.cube" % re.sub(r"[^\w]+", "_", "%s %s" % (info.get("nombre"), evento)).strip("_")
                    look_ref.escribir_lut(ev, meta, os.path.join(rutas.DIR_LUT_MCP, nombre_lut))
                    project.RefreshLUTList()
                    look_ref_lut = "MCP/" + nombre_lut
                    log("  plantilla: color como %s (luz %.0f -> %.0f, contraste %.0f -> %.0f, tono %+.0f/%+.0f -> "
                        "%+.0f/%+.0f)." % (de_que, ev["media"][0], meta["media"][0], ev["desv"][0], meta["desv"][0],
                                           ev["media"][1], ev["media"][2], meta["media"][1], meta["media"][2]))
            except Exception as ex:
                log("  plantilla: sin el color de la referencia (%s)" % ex)
        if vigilados:
            log("  plantilla: color medido plano por plano, %d con la corrección suavizada." % len(vigilados))
    except Exception as ex:
        log("  plantilla: sin ruido ni color por toma (%s)" % ex)
    # 5) color: correccion por plano y look suave, en su grupo
    try:
        # (1.9.6) con el color de la referencia, un grupo PROPIO de esta plantilla y evento (el grupo «PLANTILLA» lo
        # comparten todas las lineas de plantilla del proyecto: cambiarle el look cambiaria las de Reels)
        nombre_g = GRUPO if not look_ref_lut else "%s %s - %s" % (GRUPO, info.get("nombre"), evento)
        grupo = next((g for g in project.GetColorGroupsList() or [] if g.GetName() == nombre_g), None) or \
            project.AddColorGroup(nombre_g)
        pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
        pre.SetLUT(1, DCTL_COLOR)
        post.SetLUT(1, look_ref_lut or LOOK)
        pre.SetNodeLabel(1, "1 BASE (TODAS LAS TOMAS)")         # (1.8.2) como las versiones: el orden de la cadena
        post.SetNodeLabel(1, "3 COLOR DE LA REFERENCIA" if look_ref_lut else "3 LOOK CINE TEAL ORANGE (SIN QUEMAR NI SATURAR)")
        if n_bn:
            log("  plantilla: %d planos en blanco y negro como la referencia." % n_bn)
        grupo_bn = None
        if look_bn_lut:                                  # (1.9.6) los de blanco y negro, en su grupo con su LUT
            nombre_bn = nombre_g + " BN"
            grupo_bn = next((g for g in project.GetColorGroupsList() or [] if g.GetName() == nombre_bn), None) or \
                project.AddColorGroup(nombre_bn)
            grupo_bn.GetPreClipNodeGraph().SetLUT(1, DCTL_COLOR)
            grupo_bn.GetPostClipNodeGraph().SetLUT(1, look_bn_lut)
            grupo_bn.GetPreClipNodeGraph().SetNodeLabel(1, "1 BASE (TODAS LAS TOMAS)")
            grupo_bn.GetPostClipNodeGraph().SetNodeLabel(1, "3 BLANCO Y NEGRO DE LA REFERENCIA")
        for it, h in puestos:
            it.AssignToColorGroup(grupo_bn if grupo_bn is not None and h.get("bn") else grupo)
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
