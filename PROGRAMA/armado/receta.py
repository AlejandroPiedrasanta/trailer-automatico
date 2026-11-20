# -*- coding: utf-8 -*-
"""
receta.py - La RECETA de cada toma, para los metadatos: en que plantilla y en que minuto iria, que correccion de color
le toca y cuanta reduccion de ruido.

(18-nov, la persona: «si necesitas más metadatos, como sugerir: estas tomas podrían ir en las plantillas tal y tal en el
minuto y segundo tal, o corrección de color tal y tal, y aplicar reducción de ruido») Sale del mismo plan y de las
mismas cuentas que usa el armado, pero SIN DaVinci (como el plan previo): las cuatro duraciones en horizontal y en
vertical, la correccion por toma (cdl_para) y el nivel de ruido medido (ruido_tomas -> ruido.nivel_para).

    calcular(analisis, tipo_evento) -> {ruta en minusculas: {"usos": texto, "color": texto, "ruido": texto}}

Los minutos son los del PLAN: en el armado los cortes se ajustan al golpe de la musica, asi que pueden moverse medio
segundo. Sirve para saber de un vistazo (en Windows o en DaVinci) donde entra cada toma y con que ajuste.
"""
import json
import os

import rutas

FPS = 24.0


def _t(seg):
    return "%d:%02d" % (int(seg) // 60, int(seg) % 60)


def _planes(analisis, tipo, formato, solo_definir=False):
    import motor
    with open(os.path.join(rutas.RECURSOS, "plantillas_marcadores.json"), encoding="utf-8") as f:
        plantillas = json.load(f)
    ruta = rutas.codigo("build_trailers.py")
    g = {"__name__": "build_trailers", "resolve": motor._ResolveFalso(plantillas), "BASE": rutas.BASE,
         "ANALISIS": analisis, "EVENTO": None, "SOLO": None, "REHACER": True, "DRY_RUN": True, "SIN_RESOLVE": True,
         "TIPO_EVENTO": tipo, "VERTICALES": True, "FORMATO": formato, "print": lambda *a, **k: None,
         "SOLO_DEFINIR": solo_definir}
    with open(ruta, encoding="utf-8") as f:
        exec(compile(f.read(), ruta, "exec"), g)
    return g


def _cruce(a, b):
    """Lo que esta en los dos juegos de tramos [(ini, fin)]."""
    out = []
    for a0, a1 in a:
        for b0, b1 in b:
            if max(a0, b0) < min(a1, b1):
                out.append((max(a0, b0), min(a1, b1)))
    return sorted(out)


def tramos_fuera(videos, tipo_evento="xv"):
    """({ruta: [(ini, fin)]}, {rutas grabadas por accidente}) los tramos de cada toma que las MEDIDAS ya dejan fuera del
    montaje: desenfocado, luces reventadas, barrido, temblor fuerte, a oscuras o torcido (Planificador.vista, las mismas
    cuentas del armado, sin lo que vio la IA), y las tomas que el armado ya deja fuera enteras (Planificador.accidentales).
    En un video vertical, solo lo que queda fuera en los DOS formatos (cada uno mide contra sus camaras).

    (18-nov, «mejora los analizadores, que hagan más rápido») La revision cuadro por cuadro de la IA no pregunta por esos
    tramos: en la XV del 8-nov eran 30 de 69 min de video. videos: entradas del cache del analisis
    (con «vista», «temblor», «color», «camara»)."""
    limpios = []
    for d in videos:
        if d.get("tipo") == "foto" or not d.get("ruta"):
            continue
        c = dict(d)
        c.pop("descartar", None)
        if c.get("ia"):
            c["ia"] = {k: v for k, v in c["ia"].items() if k != "instantes"}
        limpios.append(c)
    if not limpios:
        return {}, set()
    formatos = ("horizontal", "vertical") if any(not c.get("horizontal", True) for c in limpios) else ("horizontal",)
    plan = {f: _planes({"items": limpios, "fecha": None}, tipo_evento, f, True)["Planificador"](limpios, FPS)
            for f in formatos}
    out, accidentales = {}, set()
    for c in limpios:
        tramos = plan["horizontal"].vista(c)[0]
        accidental = c["nombre"] in plan["horizontal"].accidentales
        if not c.get("horizontal", True):
            tramos = _cruce(tramos, plan["vertical"].vista(c)[0])
            accidental = accidental and c["nombre"] in plan["vertical"].accidentales
        out[c["ruta"]] = [(round(a, 2), round(b, 2)) for a, b in tramos]
        if accidental:                           # grabada por accidente: el armado ya la deja fuera entera
            accidentales.add(c["ruta"])
    return out, accidentales


def _color(g, item, objetivos, sat_evento):
    if not item.get("color") or item.get("tipo") == "foto":
        return ""
    try:
        cdl = g["cdl_para"]({"item": item, "tipo": item.get("tipo"), "ini": 0.0,
                             "dur_f": int(float(item.get("dur") or 1.0) * FPS), "momento": item.get("momento")},
                            objetivos.get(item.get("momento"), 0.42), sat_evento)
    except Exception:
        return ""
    if not cdl:
        return ""
    pend = [float(x) for x in cdl["Slope"].split()]
    media = sum(pend) / 3.0
    pot, des, sat = float(cdl["Power"].split()[0]), float(cdl["Offset"].split()[0]), float(cdl["Saturation"])
    partes = ["exposición %+d %%" % round((media - 1.0) * 100)]
    if abs(pot - 1.0) >= 0.01:
        partes.append("medios (gamma) %.2f" % pot)
    if abs(des) >= 0.003:
        partes.append("negros %+.3f" % des)
    bal = [round((p / media - 1.0) * 100) for p in pend]
    if any(bal):
        partes.append("balance R %+d %% G %+d %% B %+d %%" % tuple(bal))
    partes.append("saturación %d %%" % round(sat * 100))
    neutro = abs(media - 1.0) < 0.02 and abs(pot - 1.0) < 0.01 and not any(bal) and sat >= 0.99
    return "casi no necesita (ya está bien)" if neutro else ", ".join(partes)


def _ruido(item, medidas, intensidad):
    if item.get("tipo") == "foto":
        return ""
    try:
        import ruido
        import ruido_tomas
        m = medidas.get(ruido_tomas._clave(item["ruta"]))
        if not isinstance(m, dict):
            return ""
        n = ruido.nivel_para(m, intensidad)
        nombre = {0: "apagada", 1: "muy poca", 2: "poca", 3: "media", 4: "alta", 5: "muy alta"}.get(n, "")
        return "nivel %d de 5 (%s)" % (n, nombre)
    except Exception:
        return ""


MOTIVOS_FUERA = {"sin_cara": "No se ve la cara", "sin_cabeza": "Gente sin cabeza", "piso": "Apunta al piso",
                 "techo": "Apunta al techo", "tapado": "Algo la tapa", "pared": "Apunta a la pared",
                 "de_cabeza": "De cabeza", "equipo": "La cámara tapa", "nada": "No se entiende"}
MOMENTO_CORTO = 8             # con menos tomas buenas que esto, los videos largos repiten planos de ese momento


def plan_ventana(analisis, tipo_evento="xv"):
    """(18-nov, la persona eligio la propuesta A: «Qué entra al video») Para Material: el plan de CADA version, plano
    por plano, y las tomas que quedan fuera con su motivo en pocas palabras. Sin DaVinci (el mismo plan previo).

        {"versiones": [(clave, texto)], "planos": {clave: [{"ruta", "nombre", "tipo", "t", "momento"}]},
         "fuera": [{"ruta", "nombre", "tipo", "motivo", "a_mano"}], "a_mano_si": [nombres], "videos": n,
         "cortos": [(momento, tomas buenas)]}"""
    out = {"versiones": [], "planos": {}, "fuera": [], "a_mano_si": [], "videos": 0, "cortos": []}
    g0 = None
    for formato in ("horizontal", "vertical"):
        try:
            g = _planes(analisis, tipo_evento, formato)
        except Exception:
            continue
        g0 = g0 or g
        for ver, _tpl, intro, zonas in g.get("PLANES") or []:
            suf = str(ver.get("sufijo", ""))
            clave = ("V " if formato == "vertical" else "") + suf
            planos, t = [], 0.0
            ide = g.get("id_plano") or (lambda p: "")
            for p in intro or []:
                planos.append((p["item"], t, "INTRO", ide(p), p.get("dur_f", 0) / FPS))
                t += p.get("dur_f", 0) / FPS
            for _zona, z0, _z1, piezas in zonas:
                t = z0 / FPS
                for p in piezas:
                    planos.append((p["item"], t, p["item"].get("momento") or "FIESTA", ide(p), p.get("dur_f", 0) / FPS))
                    t += p.get("dur_f", 0) / FPS
            out["versiones"].append((clave, ("Vertical " if formato == "vertical" else "") + suf.replace("min", " min")))
            out["planos"][clave] = [{"ruta": i.get("ruta"), "nombre": i.get("nombre"), "tipo": i.get("tipo"),
                                     "t": round(t0, 1), "momento": mom, "id": ide_, "dur": round(dur, 1)}
                                    for i, t0, mom, ide_, dur in planos]
    if g0 is None:
        return out
    items = g0["decisiones"](analisis.get("items") or [])
    plan = g0["Planificador"](items, FPS)
    try:
        import vision_ia
    except Exception:
        vision_ia = None
    vids = [i for i in items if i.get("tipo") != "foto"]
    out["videos"] = len(vids)
    buenas, lista_buenas = {}, []
    for i in vids:
        accidental = i.get("nombre") in plan.accidentales
        if i.get("a_mano") == "si":
            out["a_mano_si"].append(i.get("nombre"))
        if not (i.get("descartar") or accidental):
            buenas[i.get("momento")] = buenas.get(i.get("momento"), 0) + 1
            lista_buenas.append({"ruta": i.get("ruta"), "nombre": i.get("nombre"), "tipo": i.get("tipo"),
                                 "momento": i.get("momento") or "FIESTA", "horizontal": i.get("horizontal", True),
                                 "motivo": "Buena, sin usar"})
            continue
        motivo = "No sirve"
        if i.get("a_mano") == "no":
            motivo = "La quitaste tú"
        elif accidental:
            motivo = "Desenfocada o movida"
        elif vision_ia is not None:
            _parte, m = vision_ia.parte_mala(i.get("ia"), i.get("tipo") == "dron")
            motivo = MOTIVOS_FUERA.get(m, motivo)
        out["fuera"].append({"ruta": i.get("ruta"), "nombre": i.get("nombre"), "tipo": i.get("tipo"), "motivo": motivo,
                             "a_mano": i.get("a_mano")})
    out["cortos"] = [(m, buenas.get(m, 0)) for m in ("MAQUILLAJE", "IGLESIA", "FIESTA") if buenas.get(m, 0) < MOMENTO_CORTO]
    try:                                     # (18-nov) las versiones con orden puesto a mano
        import motor
        out["a_mano_orden"] = {k: bool(v) for k, v in (motor.leer_estado().get("orden_planos") or {}).items()}
    except Exception:
        out["a_mano_orden"] = {}
    try:                                     # (19-nov) las plantillas elegidas en Material: sus huecos, uno por corte
        import motor
        import plantilla_ref
        import armar_ref
        elegidas = motor.leer_estado().get("plantillas_ref") or []
        for info in plantilla_ref.lista():
            if info["nombre"] in elegidas:
                out["planos"][info["nombre"]] = armar_ref.plan_ventana(analisis, info, tipo_evento)
                out["versiones"].append((info["nombre"], info["nombre"].title()))
    except Exception as ex:
        out["error_plantillas"] = str(ex)
    # (19-nov, la persona: «si solo hay 10 o 20 escenas que las ponga, y abajo las que posiblemente sí y abajo las
    # descartadas») por version: las tomas buenas que no entraron (en lo vertical, solo las grabadas en vertical)
    verticales = {c for c, _t in out["versiones"] if c.startswith("V ")}
    try:
        verticales |= {p["nombre"] for p in plantilla_ref.lista() if p.get("vertical", True)}
    except Exception:
        pass
    out["posibles"] = {}
    for clave, _t in out["versiones"]:
        usadas = {x.get("ruta") for x in out["planos"].get(clave) or []}
        out["posibles"][clave] = [b for b in lista_buenas if b["ruta"] not in usadas
                                  and (clave not in verticales or not b["horizontal"])]
    return out


def calcular(analisis, tipo_evento="xv"):
    try:
        import motor
        intensidad = motor.leer_estado().get("ruido")
        intensidad = 60 if intensidad is None else intensidad
    except Exception:
        intensidad = 60
    usos, g0 = {}, None
    for formato in ("horizontal", "vertical"):
        try:
            g = _planes(analisis, tipo_evento, formato)
        except Exception:
            continue
        g0 = g0 or g
        for ver, _tpl, intro, zonas in g.get("PLANES") or []:
            nombre = ("VERTICAL " if formato == "vertical" else "") + str(ver.get("sufijo", "")).upper().replace("MIN", " MIN")
            pos = 0
            for p in intro or []:
                usos.setdefault(os.path.normcase(p["item"]["ruta"]), {}).setdefault(nombre, []).append((pos / FPS, None))
                pos += p.get("dur_f", 0)
            for _zona, z0, _z1, piezas in zonas:
                pos = z0
                for p in piezas:
                    usos.setdefault(os.path.normcase(p["item"]["ruta"]), {}).setdefault(nombre, []).append(
                        (pos / FPS, p.get("ini")))
                    pos += p.get("dur_f", 0)
    out = {}
    try:
        import ruido_tomas
        medidas = ruido_tomas.leer_cache()
    except Exception:
        medidas = {}
    items = analisis.get("items") or []
    objetivos, sat_evento = {}, None
    if g0 is not None:
        try:
            objetivos, sat_evento = g0["objetivos_de_luz"](items), g0["objetivo_de_saturacion"](items)
        except Exception:
            pass
    for it in items:
        k = os.path.normcase(it.get("ruta") or "")
        u = usos.get(k) or {}
        partes = []
        for nombre in sorted(u, key=lambda n: (n.startswith("VERTICAL"), int("".join(c for c in n if c.isdigit()) or 0))):
            veces = sorted(u[nombre])
            texto = ", ".join(_t(t) for t, _ in veces[:3]) + ("…" if len(veces) > 3 else "")
            desde = veces[0][1]
            partes.append("%s en %s%s" % (nombre, texto, " (desde %s de la toma)" % _t(desde) if desde else ""))
        out[k] = {"usos": " · ".join(partes) if partes else ("no entra en ninguna plantilla" if g0 is not None else ""),
                  "color": _color(g0, it, objetivos, sat_evento) if g0 is not None else "",
                  "ruido": _ruido(it, medidas, intensidad)}
    return out
