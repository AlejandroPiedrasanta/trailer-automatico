# -*- coding: utf-8 -*-
"""
build_trailers.py - Arma un evento en las 4 plantillas del TRAILER DE XV (DaVinci Resolve Studio 21).

Usa el analisis de analizar_material.py (fotos y videos por hora, clasificados en MAQUILLAJE / IGLESIA /
FIESTA, con la calidad de cada medio segundo de video). Por cada plantilla "TRAILER XV - 1min/3min/15min/30min":
  1. La duplica como "<EVENTO> - 1min", etc. La plantilla NO se toca.
  2. Intro (pista V2): 8 fotos de 5 frames, con los whoosh de la plantilla. Solo esas 8 fotos.
  3. Zonas en V1 segun los marcadores de la plantilla:
       APERTURA (fin de las fotos -> MAQUILLAJE): resumen con las mejores tomas de todo el evento
       MAQUILLAJE / IGLESIA / FIESTA: videos de ese momento en orden; IGLESIA y FIESTA abren con dron
     Elige las mejores tomas (nitidas, bien expuestas, sin temblor) y corta al ritmo de la musica.
  4. Acabado: transiciones (fundido a negro entre momentos, encadenados suaves en las versiones largas,
     fundido final), titulos con diseno (letra script + subtitulo, sombra, animacion y fundidos),
     whoosh en cada cambio de momento, LUT de color activado.
  5. Clasifica por colores: media pool en carpetas MAQUILLAJE / IGLESIA / FIESTA y cada clip con su
     color (morado / verde / rosa), tambien en la timeline.
  6. Sin audio original. Deja el render en cola en 2 VIDEOS TERMINADOS\\<EVENTO> (no lo inicia).

Se ejecuta dentro de Resolve: desde el programa (motor.py) o con el MCP (run_script_unsafe).
Variables opcionales antes de ejecutar: EVENTO, SOLO, REHACER, DRY_RUN, NOMBRE_XV, FRASE, FECHA_LUGAR.
"""
import os
import re
import math
import time
import bisect
import random
import datetime
import importlib.util

# ============================ CONFIGURACION ============================
import rutas                                     # carpetas del programa y de Resolve (Windows y Mac)
BASE = rutas.BASE
SKILL_DIR = rutas.PROGRAMA

# corte = (min, max) s por plano en las zonas; apertura = idem en el resumen inicial (mas rapido).
# tr = transiciones en frames: zona (fundido a negro entre momentos), suave (encadenado) en suaves_en,
#      final (fundido a negro al terminar).
VERSIONES = [
    {"plantilla": "TRAILER XV - 1min", "sufijo": "1min", "seg": 60, "corte": (1.0, 2.2), "apertura": (0.6, 1.2),
     "grupo": "XV 1min - COLOR", "tr": {"zona": 8, "suave": 0, "suaves_en": [], "final": 24}},
    {"plantilla": "TRAILER XV - 3min", "sufijo": "3min", "seg": 180, "corte": (1.8, 4.0), "apertura": (0.8, 1.6),
     "grupo": "XV 3min - COLOR", "tr": {"zona": 12, "suave": 10, "suaves_en": ["MAQUILLAJE"], "final": 36}},
    {"plantilla": "TRAILER XV - 15min", "sufijo": "15min", "seg": 900, "corte": (3.0, 7.0), "apertura": (1.2, 2.5),
     "grupo": "XV 15min - COLOR", "tr": {"zona": 20, "suave": 14, "suaves_en": ["MAQUILLAJE", "IGLESIA"], "final": 48}},
    {"plantilla": "TRAILER XV - 30min", "sufijo": "30min", "seg": 1800, "corte": (4.0, 9.0), "apertura": (1.5, 3.0),
     "grupo": "XV 30min - COLOR", "tr": {"zona": 24, "suave": 16, "suaves_en": ["MAQUILLAJE", "IGLESIA"], "final": 48}},
]
INTRO_CORTES = [5] * 8                  # 8 fotos de 5 frames (24 fps): las unicas fotos del video
ZONAS = ["MAQUILLAJE", "IGLESIA", "FIESTA"]
COLORES = {"MAQUILLAJE": "Purple", "IGLESIA": "Green", "FIESTA": "Pink", "DESCARTADOS": "Brown"}
PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS, PISTA_WHOOSH = "VIDEOS", "FOTOS INTRO", "TEXTOS", "SFX WHOOSH"
MARGEN = 0.75                 # s que se evitan al inicio y fin de cada video (arranque de camara, handles)
SEPARACION = 0.5              # s minimos entre dos planos del mismo video
PASO_CALIDAD = 0.5            # s por muestra de calidad (igual que analizar_material)
BRILLO_MIN_INTRO = 0.18
UMBRAL_LENTO = 0.55           # emocion media (0-1) para que un plano vaya en camara lenta
UMBRAL_TEMBLOR = 0.6          # temblor medio (px en 192 de ancho) para pasar el estabilizador de Resolve
LENTOS = {"1min": 2, "3min": 3, "15min": 6, "30min": 9}      # planos en camara lenta por version
VOCES = {"1min": 1, "3min": 2, "15min": 3, "30min": 4}       # frases (votos, brindis...) como voz sobre la musica
USAR_VIDEOS_VERTICALES = False    # True = tambien usa videos de celular grabados en vertical
# Igualacion automatica por plano (CDL en el nodo del clip): exposicion, negros, balance de blancos, saturacion
IGUALAR = globals().get("IGUALAR", True)
FUERZA_EXPOSICION = 0.75          # 0 = no toca, 1 = iguala del todo a la luz tipica del momento
FUERZA_BLANCOS = 0.6              # cuanto corrige la dominante de color de los grises
LUZ_OBJETIVO = (0.30, 0.50)       # limites de la luz tipica de cada momento
SAT_OBJETIVO = 0.36               # saturacion media medida a la que se lleva cada toma (antes del look)
SAT_LIMITES = (0.72, 1.25)        # cuanto puede bajar (LED de fiesta) o subir (tomas lavadas/log)
FUENTE_TITULO, FUENTE_SUB = "Great Vibes", "Montserrat"
ESTILO_SUB = "Regular"            # peso del subtitulo (Light se pierde sobre vestidos blancos)
VELO_TITULO = 0.42                # oscuridad del velo suave detras de los titulos (0 = sin velo)
ORDEN_ACTOS = ["FIESTA", "ROMANTICA", "CEREMONIA", "EPICA"]   # palabra del marcador ACTO -> frase del perfil
WHOOSH = "50 overcrowed"      # parte del nombre del whoosh en el media pool
CARPETAS_MOMENTO = {"MAQUILLAJE": "01 MAQUILLAJE", "IGLESIA": "02 IGLESIA", "FIESTA": "03 FIESTA",
                    "DESCARTADOS": "99 DESCARTADOS"}
# Color y ruido por separado (universal): ruido en el nodo de cada clip, correccion en el nodo PRE-CLIP del
# grupo de color de la version y el LOOK (LUT) en el nodo POST-CLIP. Cada uno se apaga por separado.
DCTL_RUIDO = "MCP/XV_REDUCCION_RUIDO.dctl"
DCTL_COLOR = "MCP/XV_CORRECCION_COLOR.dctl"
DIR_LUT = rutas.DIR_LUT
ACTIVAR_LUT = True
ACTIVAR_SIEMPRE = ["MULTITEXT"]   # titulos de la plantilla que se activan aunque esten apagados (firma)
CORTAR_AL_RITMO = True
ENCOLAR_RENDER = True

EVENTO = globals().get("EVENTO") or None
SOLO = globals().get("SOLO") or None
REHACER = globals().get("REHACER", True)
DRY_RUN = globals().get("DRY_RUN", False)
NOMBRE_XV = globals().get("NOMBRE_XV") or ""
FRASE = globals().get("FRASE") or ""
FECHA_LUGAR = globals().get("FECHA_LUGAR") or ""
TIPO_EVENTO = (globals().get("TIPO_EVENTO") or "xv").lower()   # xv, boda, bautizo, graduacion, cumpleanos
RUIDO = globals().get("RUIDO")          # intensidad de la reduccion de ruido 0-100 (None = la de ruido.DEFECTO)
# =======================================================================

try:
    resolve
except NameError:  # ejecucion fuera de Resolve
    import DaVinciResolveScript as _dvr
    resolve = _dvr.scriptapp("Resolve")

reporte = {"avisos": [], "versiones": []}


def aviso(msg):
    print("AVISO: " + msg)
    reporte["avisos"].append(msg)


def cargar_perfil(tipo):
    """Perfil del tipo de evento (perfiles_evento.json): titulos, frases y nombres de los momentos."""
    import json
    try:
        with open(rutas.perfiles(), encoding="utf-8") as f:
            perfiles = json.load(f)
    except Exception as ex:
        aviso("No se pudo leer perfiles_evento.json (%s); se usan textos de XV." % ex)
        perfiles = {}
    perfil = perfiles.get(tipo) or perfiles.get("xv") or {}
    perfil.setdefault("prefijo", "XV")
    perfil.setdefault("titulo", "Mis XV años")
    perfil.setdefault("frase", "MIS XV AÑOS")
    perfil.setdefault("momentos", {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia", "FIESTA": "Fiesta"})
    perfil.setdefault("actos", {"FIESTA": ["¡A celebrar!", ""], "ROMANTICA": ["Un sueño hecho realidad", ""]})
    perfil.setdefault("plantilla", {})
    return perfil


def _modulo(nombre):
    ruta = os.path.join(SKILL_DIR, nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ utilidades
def restar(intervalos, quitar):
    res = [tuple(x) for x in intervalos]
    for qa, qb in quitar:
        nuevo = []
        for a, b in res:
            if qb <= a or qa >= b:
                nuevo.append((a, b))
            else:
                if qa > a:
                    nuevo.append((a, qa))
                if qb < b:
                    nuevo.append((qb, b))
        res = nuevo
    return [(a, b) for a, b in res if b - a > 0.05]


def espaciadas(lista, n, desfase=0.5):
    if n <= 0 or not lista:
        return []
    if n >= len(lista):
        return list(lista)
    paso = len(lista) / float(n)
    idx, vistos = [], set()
    for i in range(n):
        j = min(len(lista) - 1, int((i + desfase) * paso))
        while j in vistos and j + 1 < len(lista):
            j += 1
        vistos.add(j)
        idx.append(j)
    return [lista[j] for j in sorted(idx)]


def _hora(it, desplazamiento=0.0):
    return datetime.datetime.fromisoformat(it["hora"]) + datetime.timedelta(seconds=desplazamiento)


# ------------------------------------------------------------------ plan (sin tocar Resolve)
class Planificador:
    def __init__(self, items, fps):
        self.fps = fps
        # videos verticales (celular parado) no entran al montaje 16:9; quedan clasificados en el media pool
        self.vids = [i for i in items if i["tipo"] != "foto" and not i.get("descartar")
                     and (USAR_VIDEOS_VERTICALES or i.get("horizontal", True))]
        n_vert = sum(1 for i in items if i["tipo"] != "foto" and not i.get("horizontal", True))
        if n_vert and not USAR_VIDEOS_VERTICALES:
            print("%d videos verticales quedan fuera del montaje (estan en el media pool)." % n_vert)
        self.fotos = self._sin_repetidas([i for i in items if i["tipo"] == "foto" and not i.get("descartar")
                                          and i.get("horizontal", True)])
        self.usados = {}
        self.fotos_usadas = set()
        self._pref = {}
        self._emo = {}

    @staticmethod
    def _sin_repetidas(fotos):
        """Rafagas: de varias fotos casi iguales (huella dHash parecida, tomadas seguidas) queda la mas nitida."""
        fotos = sorted(fotos, key=lambda f: f["hora"])
        quedan = []
        for f in fotos:
            h = f.get("dhash")
            gemela = None
            if h:
                for j in range(len(quedan) - 1, max(-1, len(quedan) - 7), -1):
                    g = quedan[j]
                    if g.get("dhash") and bin(int(h, 16) ^ int(g["dhash"], 16)).count("1") <= 10:
                        gemela = j
                        break
            if gemela is None:
                quedan.append(f)
            elif f.get("nitidez", 0) > quedan[gemela].get("nitidez", 0):
                quedan[gemela] = f
        return quedan

    @staticmethod
    def momento_en(v, t):
        """Momento del video en el segundo t (los videos largos pueden pasar de IGLESIA a FIESTA)."""
        for a, b, m in v.get("tramos") or []:
            if a <= t < b:
                return m
        return v.get("momento")

    def utiles(self, v, momentos=None):
        u = restar([(MARGEN, v["dur"] - MARGEN)], v.get("oscuros") or [])
        if momentos and v.get("tramos"):            # solo los tramos de ese momento
            u = restar(u, [(a, b) for a, b, m in v["tramos"] if m not in momentos])
        return u

    def libres(self, v, momentos=None):
        return restar(self.utiles(v, momentos), self.usados.get(v["ruta"], []))

    def _serie(self, v):
        """Puntaje de cada medio segundo: calidad (nitidez, luz, sin temblor) x emocion del audio (aplausos,
        gritos, brindis: el audio sube sobre lo normal de ese video)."""
        cal = v.get("calidad") or []
        emo = self.emocion(v)
        return [c * (0.85 + 0.35 * (emo[i] if i < len(emo) else 0.0)) for i, c in enumerate(cal)]

    def emocion(self, v):
        """0-1 por medio segundo: el audio sube sobre lo normal del video (aplausos, gritos) y los momentos clave que
        entendio Resolve al escuchar (votos, "los declaro", el beso que viene despues, "te amo", brindis)."""
        cache = self._emo.get(v["ruta"])
        if cache is not None:
            return cache
        n = len(v.get("calidad") or []) or int(v.get("dur", 0) / PASO_CALIDAD)
        emo = [0.0] * n
        aud = v.get("audio") or []
        if len(aud) >= 6:
            normal = sorted(aud)[len(aud) // 2]
            crudo = [max(0.0, min(1.0, (x - normal - 4.0) / 10.0)) for x in aud]
            for i in range(min(n, len(crudo))):
                emo[i] = (crudo[max(0, i - 1)] + crudo[i] + crudo[min(len(crudo) - 1, i + 1)]) / 3.0
        for fr in v.get("frases") or []:
            fin = fr["fin"] + (8.0 if fr["tipo"] == "DECLARACION" else 2.0)    # tras "puede besar...": el beso
            for i in range(max(0, int((fr["ini"] - 1.0) / PASO_CALIDAD)), min(n, int(fin / PASO_CALIDAD) + 1)):
                emo[i] = max(emo[i], 0.6 + 0.4 * fr.get("puntaje", 0.5))
        self._emo[v["ruta"]] = emo
        return emo

    def media(self, serie, a, l):
        if not serie:
            return 0.0
        i0 = min(len(serie) - 1, max(0, int(a / PASO_CALIDAD)))
        i1 = min(len(serie), max(i0 + 1, int(math.ceil((a + l) / PASO_CALIDAD))))
        return sum(serie[i0:i1]) / float(i1 - i0)

    def marcar_efectos(self, zonas, fps, max_lentos):
        """Despues de cortar al ritmo: camara lenta (Speed Warp de Resolve) en los planos mas emotivos y estabilizador
        en los que tiemblan. Pone p['vel'] (0,4-0,5) y p['estabilizar']."""
        cand = []
        for nombre, _, _, piezas in zonas:
            for p in piezas:
                if p["tipo"] == "foto":
                    continue
                v = p["item"]
                l = p["dur_f"] / float(fps)
                e = self.media(self.emocion(v), p["ini"], l)
                if nombre in ("IGLESIA", "FIESTA", "APERTURA") and e >= UMBRAL_LENTO and l >= 1.0:
                    cand.append((e, p))
        lentos = 0
        for e, p in sorted(cand, key=lambda t: -t[0]):
            if lentos >= max_lentos:
                break
            vf = p["item"].get("fps") or 30
            p["vel"] = 0.4 if vf >= 48 else 0.5          # 60 fps: lento natural; 24-30 fps: Speed Warp inventa cuadros
            lentos += 1
        for _, _, _, piezas in zonas:
            for p in piezas:
                if p["tipo"] == "foto" or p["tipo"] == "dron":
                    continue
                l = p["dur_f"] / float(fps) * p.get("vel", 1.0)
                if self.media(p["item"].get("temblor") or [], p["ini"], l) >= UMBRAL_TEMBLOR:
                    p["estabilizar"] = True
        return lentos, sum(1 for _, _, _, ps in zonas for p in ps if p.get("estabilizar"))

    def puntaje(self, v, a, l):
        """Puntaje medio (0-1,2) del tramo [a, a+l] del video."""
        pref = self._pref.get(v["ruta"])
        if pref is None:
            pref = [0.0]
            for x in self._serie(v):
                pref.append(pref[-1] + x)
            self._pref[v["ruta"]] = pref
        n = len(pref) - 1
        if n < 1:
            return 0.5
        i0 = min(n - 1, max(0, int(a / PASO_CALIDAD)))
        i1 = min(n, max(i0 + 1, int(math.ceil((a + l) / PASO_CALIDAD))))
        return (pref[i1] - pref[i0]) / float(i1 - i0)

    def intro(self, k):
        n = len(INTRO_CORTES)
        cand = [f for f in self.fotos if f.get("brillo", 0.5) >= BRILLO_MIN_INTRO] or self.fotos
        nit = sorted(f["nitidez"] for f in cand if f.get("nitidez") is not None)
        if len(nit) > 3 * n:                        # fuera las movidas o desenfocadas (el 30 % menos nitido)
            corte = nit[int(len(nit) * 0.3)]
            cand = [f for f in cand if f.get("nitidez") is None or f["nitidez"] >= corte]
        libres = [f for f in cand if f["ruta"] not in self.fotos_usadas]
        sel = espaciadas(libres if len(libres) >= n else cand, n, 0.2 + 0.19 * k)
        for f in sel:
            self.fotos_usadas.add(f["ruta"])
        sel.sort(key=lambda f: f["hora"])
        return [{"tipo": "foto", "item": f, "dur_f": d} for f, d in zip(sel, INTRO_CORTES)]

    def zona(self, momentos, dur_f, corte, rng, dron_primero):
        """Planos de video (las mejores tomas libres) para llenar dur_f frames, en orden cronologico."""
        fps = self.fps
        lo, hi = corte
        vz = [v for v in self.vids if v.get("momento") in momentos
              or any(m in momentos for _, _, m in v.get("tramos") or [])]
        filtro = momentos
        if not vz:
            aviso("No hay videos de %s; se usa material de todo el evento." % "/".join(momentos))
            vz, filtro = self.vids, None
        cortes, rest = [], dur_f
        while rest > 0:
            c = int(round(rng.uniform(lo, hi) * fps))
            if rest - c < int(lo * fps * 0.6):
                c = rest
            c = min(c, rest)
            cortes.append(c)
            rest -= c
        cand = [(v, [x for x in self.libres(v, filtro) if x[1] - x[0] >= lo]) for v in vz]
        pesos, topes = [], []
        for v, ls in cand:
            largo = sum(b - a for a, b in ls)
            pesos.append(largo * (0.2 + self.puntaje(v, 0, v["dur"])))
            topes.append(int(largo // (lo + SEPARACION)))
        cuenta = [0] * len(cand)
        total = sum(pesos)
        if total > 0:
            ideal = [len(cortes) * p / total for p in pesos]
            cuenta = [min(int(x), t) for x, t in zip(ideal, topes)]
            orden = sorted(range(len(cand)), key=lambda i: ideal[i] - int(ideal[i]), reverse=True)
            falta = len(cortes) - sum(cuenta)
            while falta > 0:
                hubo = False
                for i in orden:
                    if falta > 0 and cuenta[i] < topes[i]:
                        cuenta[i] += 1
                        falta -= 1
                        hubo = True
                if not hubo:
                    break
        piezas, pendientes, cola = [], [], list(cortes)
        for (v, ls), n in zip(cand, cuenta):
            if n <= 0:
                continue
            largos = [cola.pop() for _ in range(min(n, len(cola)))]
            puestos, sobran = self._colocar(v, ls, largos)
            piezas += puestos
            pendientes += sobran
        pendientes += cola
        reusos = 0
        for d in pendientes:                    # ya no queda material sin usar: se repite la mejor toma posible
            p = self._reusar(vz, d, rng, filtro)
            if p:
                piezas.append(p)
                reusos += 1
        piezas.sort(key=lambda p: p["orden"])
        if dron_primero:
            dron = next((p for p in piezas if p["tipo"] == "dron"), None)
            if dron is not None:
                piezas.remove(dron)
                piezas.insert(0, dron)
        return piezas, reusos

    def _colocar(self, v, intervalos, largos):
        """Elige las mejores ventanas del video (calidad alta, repartidas) para cada largo pedido."""
        fps = self.fps
        libres = list(intervalos)
        res, falta, elegidos = [], [], []
        for lf in sorted(largos, reverse=True):
            l = lf / float(fps)
            mejor = None
            for a, b in libres:
                x = a
                while x + l <= b + 1e-6:
                    sc = self.puntaje(v, x, l)
                    if elegidos:
                        dist = min(abs(x - e) for e in elegidos)
                        sc -= 0.25 * max(0.0, 1.0 - dist / max(4.0 * l, 8.0))
                    if mejor is None or sc > mejor[0]:
                        mejor = (sc, x)
                    x += 0.25
            if mejor is None:
                falta.append(lf)
                continue
            s = mejor[1]
            res.append(self._pieza(v, s, lf))
            elegidos.append(s)
            libres = [x for x in restar(libres, [(s - SEPARACION, s + l + SEPARACION)]) if x[1] - x[0] >= l * 0.5]
        return res, falta

    def _reusar(self, vids, lf, rng, momentos=None):
        l = lf / float(self.fps)
        cand = [(v, u) for v in vids for u in self.utiles(v, momentos) if u[1] - u[0] >= l] or \
               [(v, u) for v in self.vids for u in self.utiles(v) if u[1] - u[0] >= l]
        if not cand:
            return None
        pruebas = []
        for _ in range(24):
            v, (a, b) = rng.choice(cand)
            x = rng.uniform(a, b - l)
            pruebas.append((self.puntaje(v, x, l), v, x))
        _, v, x = max(pruebas, key=lambda t: t[0])
        return self._pieza(v, x, lf, marcar=False)

    def _pieza(self, v, ini, dur_f, marcar=True):
        if marcar:
            self.usados.setdefault(v["ruta"], []).append((ini, ini + dur_f / float(self.fps)))
        return {"tipo": v["tipo"], "item": v, "ini": ini, "dur_f": dur_f, "orden": _hora(v, ini),
                "momento": self.momento_en(v, ini + dur_f / (2.0 * self.fps))}


def al_ritmo(piezas, z0, z1, golpes, fps, lo):
    """Mueve cada corte al golpe de musica mas cercano (sin acortar demasiado ningun plano)."""
    if not golpes or len(piezas) < 2:
        return 0
    bordes, pos = [], z0
    for p in piezas[:-1]:
        pos += p["dur_f"]
        bordes.append(pos)
    minimo = max(6, int(lo * fps * 0.55))
    nuevos, prev, movidos = [], z0, 0
    for i, b in enumerate(bordes):
        tol = min(int(0.5 * fps), piezas[i]["dur_f"] // 2, piezas[i + 1]["dur_f"] // 2)
        j = bisect.bisect_left(golpes, b)
        mejor = None
        for g in golpes[max(0, j - 2): j + 2]:
            if abs(g - b) <= tol and g - prev >= minimo and z1 - g >= minimo:
                if mejor is None or abs(g - b) < abs(mejor - b):
                    mejor = g
        nb = max(mejor if mejor is not None else b, prev + minimo)
        movidos += mejor is not None
        nuevos.append(nb)
        prev = nb
    pos = z0
    for p, nb in zip(piezas, nuevos + [z1]):
        d = max(1, nb - pos)
        if p["tipo"] != "foto":
            limite = p["item"]["dur"] - 0.15
            if p["ini"] + d / float(fps) > limite:
                p["ini"] = max(0.15, limite - d / float(fps))
        p["dur_f"] = d
        pos += d
    return movidos


def _lim(x, a, b):
    return max(a, min(b, x))


def _mediana(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def objetivos_de_luz(items):
    """Luz tipica de cada momento (mediana de los videos), para igualar las tomas entre si."""
    res = {}
    for mom in ZONAS:
        luces = [_mediana([s[0] for s in i["color"]]) for i in items
                 if i["tipo"] != "foto" and i.get("momento") == mom and i.get("color")]
        res[mom] = _lim(_mediana(luces) if luces else 0.42, *LUZ_OBJETIVO)
    return res


def cdl_para(pieza, objetivo):
    """CDL (slope / offset / saturacion) que iguala este plano: exposicion hacia la luz tipica de su momento,
    negros limpios, balance de blancos con los grises de la escena y algo de saturacion si esta lavado."""
    v = pieza["item"]
    col = v.get("color") or []
    if not col or pieza["tipo"] == "foto":
        return None
    i0 = max(0, int(pieza["ini"] / PASO_CALIDAD))
    i1 = min(len(col), max(i0 + 1, int(math.ceil((pieza["ini"] + pieza["dur_f"] / 24.0) / PASO_CALIDAD))))
    m = col[i0:i1] or col
    luz = _mediana([s[0] for s in m])
    negro = _mediana([s[1] for s in m])
    sat = _mediana([s[2] for s in m])
    grises = [s for s in m if s[6] >= 0.05 and min(s[3:6]) > 0.05]
    meta = luz + FUERZA_EXPOSICION * (objetivo - luz)
    if negro > 0.05:                                   # negros lechosos: mapea negro->0.03 y luz->meta
        s = (meta - 0.03) / max(0.05, luz - negro)
    else:
        s = meta / max(0.02, luz)
    s = _lim(s, 0.80, 1.35)
    o = _lim(meta - luz * s, -0.08, 0.04) if negro > 0.05 else 0.0
    gan = [1.0, 1.0, 1.0]
    if len(grises) >= max(1, len(m) // 3):            # hay suficientes grises: corrige la dominante
        rgb = [sum(x[k] for x in grises) / len(grises) for k in (3, 4, 5)]
        prom = sum(rgb) / 3.0
        gan = [_lim(1 + FUERZA_BLANCOS * (prom / c - 1), 0.90, 1.10) for c in rgb]
        l = 0.2126 * gan[0] + 0.7152 * gan[1] + 0.0722 * gan[2]
        gan = [g / l for g in gan]
    # saturacion medida: cada toma se lleva hacia SAT_OBJETIVO (raiz = correccion suave), asi ninguna queda
    # sobresaturada (luces LED) ni lavada (log, cielo nublado)
    saturacion = _lim((SAT_OBJETIVO / sat) ** 0.5, *SAT_LIMITES) if sat > 0.02 else 1.0
    pend = [s * g for g in gan]
    return {"NodeIndex": "1", "Slope": "%.4f %.4f %.4f" % tuple(pend), "Offset": "%.4f %.4f %.4f" % (o, o, o),
            "Power": "1.0 1.0 1.0", "Saturation": "%.3f" % saturacion}


AJUSTE_ACTO_S = 5.0     # s: si el cambio de cancion (marcador ACTO) esta asi de cerca, el momento empieza ahi
ACTO_DE_ZONA = {"IGLESIA": ("CEREMONIA", "ROMANTICA"), "FIESTA": ("FIESTA",)}


def zonas_de(marcadores, total_f, intro_f, fps=24):
    """[(nombre, inicio_f, fin_f)]: APERTURA (fin de fotos -> 1er marcador) y las zonas de los marcadores.
    Si el marcador ACTO de la cancion de ese momento esta a menos de AJUSTE_ACTO_S, la zona empieza en el ACTO:
    asi la imagen, la cancion y el texto del acto cambian juntos."""
    marcas, actos = {}, []
    for f, m in sorted(marcadores.items()):
        n = (m.get("name") or "").strip().upper()
        if n in ZONAS and n not in marcas:
            marcas[n] = int(f)
        elif n.startswith("ACTO"):
            actos.append((int(f), n))
    for z, claves in ACTO_DE_ZONA.items():
        if z in marcas:
            cerca = [(abs(f - marcas[z]), f) for f, n in actos if any(c in n for c in claves)
                     and abs(f - marcas[z]) <= AJUSTE_ACTO_S * fps]
            if cerca:
                marcas[z] = min(cerca)[1]
    if len(marcas) < len(ZONAS):
        faltan = [z for z in ZONAS if z not in marcas]
        defecto = {"MAQUILLAJE": 0.12, "IGLESIA": 0.35, "FIESTA": 0.62}
        for z in faltan:
            marcas[z] = int(total_f * defecto.get(z, 0.5))
        aviso("Faltan los marcadores %s en la plantilla; se usan posiciones por defecto." % ", ".join(faltan))
    orden = sorted(marcas.items(), key=lambda x: x[1])
    cortes = [("APERTURA", intro_f)] + [(n, max(intro_f, min(f, total_f))) for n, f in orden]
    zonas = []
    for i, (n, ini) in enumerate(cortes):
        fin = cortes[i + 1][1] if i + 1 < len(cortes) else total_f
        if fin > ini:
            zonas.append((n, ini, fin))
    return zonas


# ------------------------------------------------------------------ Resolve: colocar y acabar
def colocar(mp, secuencia, pool, fps):
    """Coloca [(pista, frame, pieza)] en orden. Devuelve [(pieza, timeline_item)].
    Las fotos se ponen de una en una y se recortan (Resolve les da duracion fija). Los videos van en
    lotes y se ajustan al frame exacto (mezclar 29.97 y 24 fps los deja 1 frame cortos)."""
    puestos, lote = [], []

    def ajustar(x, d):
        if x.GetDuration() != d:
            x.SetRightOffset(x.GetDuration() + x.GetRightOffset() - d)

    def vaciar():
        if lote:
            r = mp.AppendToTimeline([i for i, _ in lote]) or []
            for x, (_, p) in zip(r, lote):
                if p.get("vel", 1.0) < 1.0:
                    p["lento_ok"] = poner_lento(x, p)
                ajustar(x, p["dur_f"])
                puestos.append((p, x))
            del lote[:]

    for pista, pos, p in secuencia:
        c = pool.get(os.path.normcase(p["item"]["ruta"]))
        if c is None:
            continue
        d = p["dur_f"]
        if p["tipo"] == "foto":
            vaciar()
            r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": d - 1,
                                      "mediaType": 1, "trackIndex": pista, "recordFrame": pos}]) or []
            if r:
                ajustar(r[0], d)
                puestos.append((p, r[0]))
        else:
            vf = p["item"]["fps"]
            vel = p.get("vel", 1.0)
            # lento: Resolve conserva el largo en la timeline y usa menos fuente (desde el inicio); se centra la
            # parte que se ve en el medio de la ventana elegida
            s = int(round((p["ini"] + d / float(fps) * (1.0 - vel) / 2.0) * vf))
            n = max(1, int(math.ceil(d * vf / float(fps) - 1e-6)))
            lote.append(({"mediaPoolItem": c, "startFrame": s, "endFrame": s + n - 1,
                          "mediaType": 1, "trackIndex": pista, "recordFrame": pos}, p))
            if len(lote) >= 60:
                vaciar()
    vaciar()
    return puestos


def poner_lento(x, p):
    """Camara lenta de Resolve Studio: velocidad p['vel'] y, si el video es de 24-30 fps, Speed Warp (IA) para
    inventar los cuadros que faltan; con 60 fps alcanza con los cuadros reales."""
    try:
        ok = bool(x.SetSpeed({"Percentage": round(p["vel"] * 100.0, 2), "PitchCorrection": False,
                              "StretchKeyframesToFit": False, "RippleTimeline": False}))
    except Exception:
        ok = False
    if ok and (p["item"].get("fps") or 30) < 48:
        try:
            x.SetProperty("RetimeProcess", resolve.RETIME_OPTICAL_FLOW)
            x.SetProperty("MotionEstimation", resolve.MOTION_EST_SPEED_WARP_BETTER)
        except Exception:
            pass
    return ok


def estabilizar(puestos, limite_s=120.0):
    """Estabilizador de Resolve Studio en los planos que tiemblan (medido por el analizador). Con tope de tiempo."""
    t0, n = time.time(), 0
    for p, x in puestos:
        if not p.get("estabilizar") or time.time() - t0 > limite_s:
            continue
        try:
            n += bool(x.Stabilize())
        except Exception:
            pass
    return n


TIPOS_VOZ = ("VOTOS", "DECLARACION")    # la persona: "solo el audio de la iglesia, no metas audios random"


def elegir_voces(items, n, zonas):
    """Las n mejores frases de la IGLESIA (los votos y "los declaro marido y mujer") para ir como voz sobre la
    musica. Nada de otros momentos ni frases sueltas: si no hay votos claros, no hay voz."""
    if n <= 0:
        return []
    nombres = {z[0] for z in zonas}
    cand = sorted(((fr["puntaje"], fr, it) for it in items if it["tipo"] == "video" and not it.get("descartar")
                   and it.get("momento") == "IGLESIA"
                   for fr in it.get("frases") or [] if fr["tipo"] in TIPOS_VOZ and 1.2 <= fr["fin"] - fr["ini"] <= 9.0),
                  key=lambda t: -t[0])
    elegidas, tipos = [], set()
    for ronda in (0, 1):                               # primero tipos distintos; si faltan, repite tipo
        for _, fr, it in cand:
            if len(elegidas) >= n:
                break
            if any(e[1] is fr for e in elegidas) or (ronda == 0 and fr["tipo"] in tipos):
                continue
            zona = "IGLESIA" if fr["tipo"] in ("VOTOS", "DECLARACION", "AMOR") else "FIESTA"
            if zona not in nombres:
                zona = "APERTURA" if "APERTURA" in nombres else next(iter(nombres))
            elegidas.append((it, fr, zona))
            tipos.add(fr["tipo"])
    return elegidas


def pista_voz(tl):
    """La pista de voz de la plantilla ("VOZ NATURAL"); si no hay ninguna que empiece con VOZ, crea "VOZ"."""
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if (tl.GetTrackName("audio", t) or "").strip().upper().startswith("VOZ"):
            return t
    if not tl.AddTrack("audio", "stereo"):
        return None
    t = tl.GetTrackCount("audio")
    tl.SetTrackName("audio", t, "VOZ")
    return t


def poner_voces(tl, mp, pool, voces, zonas, fps):
    """Pone cada frase elegida en la pista VOZ (solo el audio), con fundidos cortos, aislamiento de voz de Resolve
    Studio y nivel medido. Devuelve [(inicio, fin)] en frames de timeline (para bajar la musica debajo)."""
    if not voces:
        return []
    t = pista_voz(tl)
    if t is None:
        aviso("No se pudo crear la pista VOZ.")
        return []
    tl.SetTrackLock("audio", t, False)
    st = tl.GetStartFrame()
    libre = {}
    tramos = []
    for it, fr, zona in voces:
        z = next((z for z in zonas if z[0] == zona), None)
        c = pool.get(os.path.normcase(it["ruta"]))
        if z is None or c is None:
            continue
        _, z0, z1, _ = z
        largo = int(round((fr["fin"] - fr["ini"]) * fps))
        pos = max(st + z0 + int(1.2 * fps), libre.get(zona, 0))
        if pos + largo > st + z1 - int(0.8 * fps):
            continue
        vf = float(it.get("fps") or 30)
        s = int(round(fr["ini"] * vf))
        e = s + int(round((fr["fin"] - fr["ini"]) * vf))
        r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": s, "endFrame": e, "mediaType": 2,
                                  "trackIndex": t, "recordFrame": pos}]) or []
        if not r:
            continue
        x = r[0]
        try:
            x.SetFades({"FadeIn": 3, "FadeOut": 8})
        except Exception:
            pass
        tramos.append((x.GetStart(), x.GetEnd(), fr))
        libre[zona] = x.GetEnd() + int(2.5 * fps)
    try:                                               # Voice Isolation: quita musica y murmullo de fondo
        tl.SetVoiceIsolationState(t, {"isEnabled": True, "amount": 75})
    except Exception:
        pass
    return tramos


def bajar_musica(tl, mp, tramos, fps, db=-9.0):
    """Baja la musica debajo de cada voz (Resolve no deja poner keyframes de volumen por script): parte el clip de
    musica en antes / debajo de la voz / despues, con la misma fuente y el tramo de en medio 9 dB mas bajo."""
    if not tramos:
        return 0
    margen_a, margen_b = int(0.25 * fps), int(0.5 * fps)
    zonas = [(a - margen_a, b + margen_b) for a, b, _ in tramos]
    n = 0
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if "MUSICA" not in (tl.GetTrackName("audio", t) or "").upper():
            continue
        tl.SetTrackLock("audio", t, False)
        for x in list(tl.GetItemListInTrack("audio", t) or []):
            r0, r1 = x.GetStart(), x.GetEnd()
            tocan = [(max(a, r0), min(b, r1)) for a, b in zonas if a < r1 and b > r0]
            if not tocan:
                continue
            try:
                vol = float(x.GetProperty("AudioVolume") or 0.0)
            except Exception:
                vol = 0.0
            if all(a <= r0 and b >= r1 for a, b in tocan):          # todo el clip queda bajo la voz
                n += bool(x.SetProperty("AudioVolume", vol + db))
                continue
            mpi = x.GetMediaPoolItem()
            if mpi is None:
                continue
            try:
                s0 = x.GetSourceStartFrame()
                fades = x.GetFades() or {}
            except Exception:
                continue
            k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
            cortes, cur = [], r0
            for a, b in sorted(tocan):
                if a > cur:
                    cortes.append((cur, a, vol))
                cortes.append((max(a, cur), b, vol + db))
                cur = b
            if cur < r1:
                cortes.append((cur, r1, vol))
            if not tl.DeleteClips([x], False):
                continue
            for j, (a, b, v) in enumerate(cortes):
                ini = s0 + int(round((a - r0) * k))
                fin = s0 + int(round((b - r0) * k))          # en audio el cuadro final no se incluye (probado)
                nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": ini, "endFrame": fin, "mediaType": 2,
                                              "trackIndex": t, "recordFrame": a}]) or []
                if not nuevo:
                    continue
                y = nuevo[0]
                y.SetProperty("AudioVolume", v)
                try:
                    y.SetFades({"FadeIn": fades.get("FadeIn", 0) if j == 0 else 2,
                                "FadeOut": fades.get("FadeOut", 0) if j == len(cortes) - 1 else 2})
                except Exception:
                    pass
            n += 1
    return n


def pista(tl, tipo, nombre, defecto):
    for t in range(1, tl.GetTrackCount(tipo) + 1):
        if (tl.GetTrackName(tipo, t) or "").strip().upper() == nombre:
            return t
    return defecto


def poner_transicion(item, tipo, dur, posicion, alineaciones=("center", "right", "left")):
    for al in alineaciones:
        try:
            if item.AddTransition({"type": tipo, "category": "simple", "position": posicion,
                                   "alignment": al, "duration": int(dur)}):
                return True
        except Exception:
            pass
    return False


def transiciones(tl, pv, zonas, ver):
    tr = ver["tr"]
    st = tl.GetStartFrame()
    items = sorted([x for x in tl.GetItemListInTrack("video", pv) or [] if x.GetMediaPoolItem() is not None],
                   key=lambda x: x.GetStart())          # sin transiciones (Resolve las lista como items)
    inicios = {st + z0: n for n, z0, _, _ in zonas}
    n_ok = 0
    for a, b in zip(items, items[1:]):
        if a.GetDuration() is None or b.GetDuration() is None:
            continue
        corte = b.GetStart()
        zona = None
        for n, z0, _, _ in zonas:
            if st + z0 <= corte:
                zona = n
        if corte in inicios and inicios[corte] != "APERTURA":
            tipo, dur = "Dip To Color Dissolve", tr["zona"]
        elif tr["suave"] and zona in tr["suaves_en"]:
            tipo, dur = "Cross Dissolve", tr["suave"]
        else:
            continue
        dur = max(2, min(dur, a.GetDuration() // 2, b.GetDuration() // 2))
        n_ok += poner_transicion(b, tipo, dur, "start")
    if items:                                    # fundido a negro al final
        poner_transicion(items[-1], "Cross Dissolve", min(tr["final"], items[-1].GetDuration() - 2), "end", ("left",))
    return n_ok


def disenar_titulo(it, principal, secundario, frase=False):
    """Titulo con diseno: letra script grande con empuje lento + subtitulo en mayusculas espaciadas,
    halo oscuro y sombra para que se lea sobre cualquier toma. frase=True: frase en script mas pequena en
    el tercio inferior (sin subtitulo), para no tapar la accion."""
    comp = it.GetFusionCompByIndex(1)
    if comp is None:
        return False
    d = max(2, it.GetDuration())
    if frase:
        secundario = ""
    comp.Lock()
    try:
        t1 = comp.FindTool("Template")
        if t1 is None:
            return False
        if frase:
            tam = 0.072 if len(principal) <= 30 else 0.062
            y = 0.2
        else:
            tam = 0.15 if len(principal) <= 12 else 0.11 if len(principal) <= 24 else 0.085
            y = 0.545 if secundario else 0.5
        t1.SetInput("StyledText", principal)
        t1.SetInput("Font", FUENTE_TITULO)
        t1.SetInput("Style", "Regular")
        t1.SetInput("Center", {1: 0.5, 2: y, 3: 0.0})
        escritura = max(8, min(22, int(d * 0.35)))          # frames en que el nombre se escribe
        try:                                                  # empuje lento del nombre
            t1.AddModifier("Size", "BezierSpline")
            t1.SetInput("Size", tam, 0)
            t1.SetInput("Size", tam * 1.045, d)
        except Exception:
            t1.SetInput("Size", tam)
        try:                                                  # el nombre se escribe letra por letra
            t1.AddModifier("End", "BezierSpline")
            t1.SetInput("End", 0.0, 1)
            t1.SetInput("End", 1.0, escritura)
        except Exception:
            pass
        t2 = comp.FindTool("Subtitulo")
        if t2 is None:
            t2 = comp.AddTool("TextPlus", -32768, -32768)
            t2.SetAttrs({"TOOLS_Name": "Subtitulo"})
        t2.SetInput("StyledText", secundario.upper())
        t2.SetInput("Font", FUENTE_SUB)
        t2.SetInput("Style", ESTILO_SUB)
        t2.SetInput("Size", 0.028)
        t2.SetInput("Center", {1: 0.5, 2: 0.405, 3: 0.0})
        try:                                                  # el subtitulo se va abriendo
            t2.AddModifier("CharacterSpacing", "BezierSpline")
            t2.SetInput("CharacterSpacing", 1.22, 0)
            t2.SetInput("CharacterSpacing", 1.42, d)
        except Exception:
            t2.SetInput("CharacterSpacing", 1.3)
        # Halo y sombra con los elementos de sombreado del propio Text+ (ligeros). NO usar la herramienta
        # Shadow de Fusion: con suavizado alto pide buffers de decenas de GB y tumba Resolve.
        for t, (halo_suave, sombra_suave, halo_op) in ((t1, (10.0, 2.0, 0.65)), (t2, (7.0, 1.0, 0.8))):
            t.SetInput("Enabled3", 1)                       # elemento 3: "Black Shadow" -> halo centrado
            t.SetInput("ElementShape3", 0)
            t.SetInput("Red3", 0.0)
            t.SetInput("Green3", 0.0)
            t.SetInput("Blue3", 0.0)
            t.SetInput("Opacity3", halo_op)
            t.SetInput("SoftnessX3", halo_suave)
            t.SetInput("SoftnessY3", halo_suave)
            t.SetInput("Offset3", {1: 0.0, 2: 0.0, 3: 0.0})
            t.SetInput("Enabled5", 1)                       # elemento 5: sombra corta abajo a la derecha
            t.SetInput("ElementShape5", 0)
            t.SetInput("Red5", 0.0)
            t.SetInput("Green5", 0.0)
            t.SetInput("Blue5", 0.0)
            t.SetInput("Alpha5", 1.0)
            t.SetInput("Opacity5", 0.75)
            t.SetInput("SoftnessX5", sombra_suave)
            t.SetInput("SoftnessY5", sombra_suave)
            t.SetInput("Offset5", {1: 0.002, 2: -0.003, 3: 0.0})
            try:
                t.SetInput("PriorityBack5", t.GetInput("PriorityBack3"))
            except Exception:
                pass
        m = comp.FindTool("MezclaTitulo")
        if m is None:
            m = comp.AddTool("Merge", -32768, -32768)
            m.SetAttrs({"TOOLS_Name": "MezclaTitulo"})
        fondo = t1
        if VELO_TITULO > 0:                                   # velo eliptico suave: el texto se lee sobre blancos
            velo = comp.FindTool("Velo") or comp.AddTool("Background", -32768, -32768)
            velo.SetAttrs({"TOOLS_Name": "Velo"})
            velo.SetInput("UseFrameFormatSettings", 1)
            for k, v in (("TopLeftRed", 0.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0),
                         ("TopLeftAlpha", VELO_TITULO)):
                velo.SetInput(k, v)
            forma = comp.FindTool("VeloForma") or comp.AddTool("EllipseMask", -32768, -32768)
            forma.SetAttrs({"TOOLS_Name": "VeloForma"})
            forma.SetInput("Width", 1.0 if frase else 0.85)
            forma.SetInput("Height", 0.12 if frase else 0.24 if secundario else 0.18)
            forma.SetInput("SoftEdge", 0.16)
            forma.SetInput("Center", {1: 0.5, 2: 0.2 if frase else 0.47 if secundario else 0.5})
            velo.ConnectInput("EffectMask", forma)
            mv = comp.FindTool("MezclaVelo") or comp.AddTool("Merge", -32768, -32768)
            mv.SetAttrs({"TOOLS_Name": "MezclaVelo"})
            mv.ConnectInput("Background", velo)
            mv.ConnectInput("Foreground", t1)
            fondo = mv
        m.ConnectInput("Background", fondo)
        m.ConnectInput("Foreground", t2)
        try:                                                  # el subtitulo entra cuando el nombre ya casi esta
            m.AddModifier("Blend", "BezierSpline")
            m.SetInput("Blend", 0.0, int(escritura * 0.6))
            m.SetInput("Blend", 1.0, escritura + 10)
        except Exception:
            pass
        comp.FindTool("MediaOut1").ConnectInput("Input", m)
        for viejo in ("HaloTitulo", "SombraTitulo"):         # restos de versiones anteriores
            x = comp.FindTool(viejo)
            if x is not None:
                x.Delete()
    finally:
        comp.Unlock()
    return True


def titulos(tl, ver, fps, fecha_txt, perfil, anio):
    st = tl.GetStartFrame()
    total_f = int(ver["seg"] * fps)
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    actos = sorted((int(f), (m.get("name") or "").upper()) for f, m in (tl.GetMarkers() or {}).items()
                   if (m.get("name") or "").upper().startswith("ACTO"))

    def fmt(s):
        return (s or "").replace("{nombre}", NOMBRE_XV).replace("{fecha}", fecha_txt).replace("{anio}", str(anio))
    nombre = NOMBRE_XV or fmt(perfil["titulo"])
    frase = fmt(FRASE) or (fmt(perfil["frase"]) if NOMBRE_XV else "")
    n_ok = 0
    for it in tl.GetItemListInTrack("video", pt) or []:
        n = (it.GetName() or "").upper()
        rel = it.GetStart() - st
        if n.startswith("TEXTO NOMBRE"):
            p1, p2 = nombre, frase
        elif n.startswith("TEXTO FINAL"):
            p1, p2 = nombre, fmt(FECHA_LUGAR) or fecha_txt
            d = min(int(6 * fps), total_f - rel - int(0.5 * fps),        # tarjeta final de hasta 6 s
                    it.GetDuration() + max(0, it.GetRightOffset()))      # (lo que el titulo permita alargar)
            if d > it.GetDuration():
                it.SetRightOffset(it.GetDuration() + it.GetRightOffset() - d)
        elif n.startswith("TEXTO ACTO"):
            etiqueta = ([e for f, e in actos if f <= rel + fps] or [""])[-1]
            clave = next((k for k in ORDEN_ACTOS if k in etiqueta and k in perfil["actos"]), None)
            p1, p2 = [fmt(x) for x in perfil["actos"][clave]] if clave else ("", "")
            if not p1:
                continue
        else:
            continue
        if disenar_titulo(it, p1, p2):
            n_ok += 1
            poner_transicion(it, "Cross Dissolve", 12, "start", ("right",))
            poner_transicion(it, "Cross Dissolve", 12, "end", ("left",))
    return n_ok


# texto de la plantilla -> clave de "plantilla" en el perfil (el primero que coincida; los mas largos primero)
TEXTOS_FIJOS = [("MIS XV AÑOS", "titulo_largo"), ("MIS XV", "titulo"), ("UN SUEÑO QUE EMPIEZA", "frase1"),
                ("TE ELIJO", "intro")]


def textos_plantilla(tl, perfil):
    """Cambia los textos fijos de la plantilla (titulo grande 'MIS XV', frase de la intro) por los del
    tipo de evento. Solo en la timeline del evento: la plantilla no se toca."""
    reemplazos = perfil.get("plantilla") or {}
    if not reemplazos:
        return 0
    n = 0
    for t in range(1, tl.GetTrackCount("video") + 1):
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS):
            continue
        for it in tl.GetItemListInTrack("video", t) or []:
            try:
                comp = it.GetFusionCompByIndex(1)
            except Exception:
                comp = None
            if comp is None:
                continue
            for herr in (comp.GetToolList(False) or {}).values():
                for inp in (herr.GetInputList() or {}).values():
                    iid = (inp.GetAttrs() or {}).get("INPS_ID", "")
                    if not iid.endswith("StyledText"):
                        continue
                    actual = herr.GetInput(iid)
                    if not isinstance(actual, str):
                        continue
                    for clave_txt, clave in TEXTOS_FIJOS:
                        if clave_txt in actual.upper():
                            nuevo = reemplazos.get(clave)
                            if nuevo:
                                herr.SetInput(iid, nuevo.upper() if actual.isupper() else nuevo)
                                n += 1
                            break
    return n


# ------------------------------------------------------------------ textos nuevos (capitulos, frases, gracias)
TEXTO_PNG = os.path.join(rutas.RECURSOS, "TEXTO_TRANSPARENTE.png")
DUR_CAPITULO, DUR_FRASE, DUR_GRACIAS = 3.2, 4.0, 4.5      # s en pantalla
SEPARACION_TEXTOS = 2.0                                   # s minimos entre dos textos
CADA_FRASE = [(60, 18.0), (180, 40.0), (900, 90.0), (1e9, 120.0)]   # (hasta s de version, s de momento por frase)


def png_texto(mp, root):
    """Clip transparente 1920x1080 (06 EFECTOS\\GRAFICOS): base de los textos nuevos de la pista TEXTOS."""
    c = buscar_clip(root, "TEXTO_TRANSPARENTE")
    if c is not None:
        return c
    if not os.path.exists(TEXTO_PNG):
        import subprocess
        os.makedirs(os.path.dirname(TEXTO_PNG), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black@0.0:s=1920x1080,format=rgba",
                        "-frames:v", "1", TEXTO_PNG], creationflags=rutas.SIN_VENTANA)
    efe = carpeta_raiz(mp, root, "EFECTOS")
    gra = next((f for f in efe.GetSubFolderList() or [] if f.GetName() == "GRAFICOS"), None) or \
        mp.AddSubFolder(efe, "GRAFICOS")
    mp.SetCurrentFolder(gra)
    r = mp.ImportMedia([TEXTO_PNG]) if os.path.exists(TEXTO_PNG) else None
    return r[0] if r else None


def nuevo_texto(tl, mp, png, pt, ini, dur, nombre, p1, p2, frase, fps):
    st = tl.GetStartFrame()
    r = mp.AppendToTimeline([{"mediaPoolItem": png, "startFrame": 0, "endFrame": dur - 1, "trackIndex": pt,
                              "recordFrame": st + ini, "mediaType": 1}])
    it = r[0] if r else None
    if it is None:
        return False
    if it.GetDuration() != dur:              # las imagenes entran con duracion fija: se ajusta
        it.SetRightOffset(it.GetRightOffset() + it.GetDuration() - dur)
    try:
        it.SetName(nombre)
    except Exception:
        pass
    comp = it.GetFusionCompByIndex(1) or it.AddFusionComp()
    if comp is None:
        return False
    if comp.FindTool("Template") is None:
        t = comp.AddTool("TextPlus", -32768, -32768)
        t.SetAttrs({"TOOLS_Name": "Template"})
    ok = disenar_titulo(it, p1, p2, frase)
    try:
        it.SetFades({"FadeIn": int(0.5 * fps), "FadeOut": int(0.6 * fps)})
    except Exception:
        pass
    return ok


def textos_extra(tl, mp, png, zonas, fps, perfil, ver, cortes):
    """Capitulo al empezar cada momento, frases repartidas dentro de cada momento (mas en las versiones
    largas) y 'gracias' antes de la tarjeta final (3 min o mas). Nunca encima de otro texto."""
    if png is None:
        return 0
    st = tl.GetStartFrame()
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    ocupado = []
    for t in range(1, tl.GetTrackCount("video") + 1):     # textos y titulos que ya hay (V3, V5...)
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS):
            continue
        for x in tl.GetItemListInTrack("video", t) or []:
            if t == pt or x.GetMediaPoolItem() is None:
                ocupado.append((x.GetStart() - st, x.GetEnd() - st))
    m = int(SEPARACION_TEXTOS * fps)

    def libre(a, b):
        return all(b + m <= x0 or a >= x1 + m for x0, x1 in ocupado)

    def al_corte(f, margen=1.5):
        cerca = [c for c in cortes if abs(c - f) <= margen * fps]
        return min(cerca, key=lambda c: abs(c - f)) if cerca else int(f)
    n = 0
    caps = perfil.get("capitulos") or {}
    frases = perfil.get("frases") or {}
    cada = next(s for hasta, s in CADA_FRASE if ver["seg"] <= hasta)
    marcas = {(mk.get("name") or "").strip().upper(): int(f) for f, mk in (tl.GetMarkers() or {}).items()}
    cierre = marcas.get("CIERRE", int(ver["seg"] * fps) - 6 * fps)
    for nombre, z0, z1, _ in zonas:
        if nombre not in ZONAS:
            continue
        z1 = min(z1, cierre)
        d = int(DUR_CAPITULO * fps)
        a = z0 + int(0.4 * fps)
        if nombre in caps and a + d < z1 - fps and libre(a, a + d):
            p1, p2 = (caps[nombre] + [""])[:2]
            if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO CAPITULO " + nombre, p1, p2, False, fps):
                ocupado.append((a, a + d))
                n += 1
        lista = frases.get(nombre) or []
        cuantas = min(len(lista), int((z1 - z0) / float(cada * fps) + 0.5))
        d = int(DUR_FRASE * fps)
        k = 0
        for j in range(cuantas):
            centro = z0 + (j + 1) * (z1 - z0) / (cuantas + 1.0)
            for desv in sorted(range(-int((z1 - z0) / (2.0 * (cuantas + 1))), int((z1 - z0) / (2.0 * (cuantas + 1))) + 1,
                                     max(1, fps // 2)), key=abs):
                a = al_corte(centro + desv - d / 2)
                if z0 + fps <= a and a + d <= z1 - fps and libre(a, a + d):
                    if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO FRASE %s %d" % (nombre, k + 1), lista[k], "", True, fps):
                        ocupado.append((a, a + d))
                        n += 1
                        k += 1
                    break
    gracias = perfil.get("gracias")
    if gracias and ver["seg"] >= 180:
        d = int(DUR_GRACIAS * fps)
        final = [x.GetStart() - st for x in tl.GetItemListInTrack("video", pt) or []
                 if (x.GetName() or "").upper().startswith("TEXTO FINAL")]
        a = min(final + [cierre]) - m - d                # justo antes de la tarjeta final
        if libre(a, a + d):
            if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO GRACIAS", gracias, "", False, fps):
                n += 1
    return n


def whooshes(tl, mp, zonas, fps, clip):
    if clip is None:
        return 0
    st = tl.GetStartFrame()
    pa = pista(tl, "audio", PISTA_WHOOSH, 7)
    tl.SetTrackLock("audio", pa, False)
    ocupado = [(x.GetStart(), x.GetEnd()) for x in tl.GetItemListInTrack("audio", pa) or []]
    dur = int(2.5 * fps)
    n = 0
    for nombre, z0, _, _ in zonas:
        if nombre == "APERTURA":
            continue
        f = st + z0 - int(0.8 * fps)
        if any(a < f + dur and f < b for a, b in ocupado):
            continue
        if mp.AppendToTimeline([{"mediaPoolItem": clip, "startFrame": 0, "endFrame": dur - 1, "mediaType": 2,
                                 "trackIndex": pa, "recordFrame": f}]):
            ocupado.append((f, f + dur))
            n += 1
    return n


def buscar_clip(carpeta, clave):
    clave = clave.lower()
    for c in carpeta.GetClipList() or []:
        if clave in (c.GetName() or "").lower():
            return c
    for s in carpeta.GetSubFolderList() or []:
        r = buscar_clip(s, clave)
        if r:
            return r
    return None


def fuente(i):
    if i["tipo"] == "dron" or i.get("origen_hora") == "dji":
        return "DRON"
    return "CELULAR" if i.get("origen_hora") == "iphone" else "CAMARA"


def instalar_dctl(project):
    """Copia los DCTL de la skill a la carpeta de LUTs de Resolve si faltan."""
    import shutil
    origen = os.path.join(SKILL_DIR, "dctl")
    destino = os.path.join(DIR_LUT, "MCP")
    try:
        os.makedirs(destino, exist_ok=True)
        for f in os.listdir(origen):
            o, d = os.path.join(origen, f), os.path.join(destino, f)
            if not os.path.exists(d) or open(o, "rb").read() != open(d, "rb").read():
                shutil.copy2(o, destino)                     # copia los que faltan o cambiaron
        project.RefreshLUTList()
    except Exception as ex:
        aviso("No se pudieron instalar los DCTL de color/ruido (%s)" % ex)


def preparar_grupo(grupo):
    """Grupo de color de la version: PRE-CLIP = correccion de color universal, POST-CLIP = LOOK."""
    try:
        pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
        pre.SetLUT(1, DCTL_COLOR)
        pre.SetNodeLabel(1, "CORRECCION DE COLOR")
        pre.SetNodeEnabled(1, True)
        if ACTIVAR_LUT:
            post.SetNodeEnabled(1, True)
    except Exception as ex:
        aviso("Grupo %s: no se pudo preparar el color (%s)" % (grupo.GetName(), ex))


# Carpetas principales del media pool, numeradas para que salgan siempre en este orden.
CARPETAS_RAIZ = {"PLANTILLAS": "01 PLANTILLAS", "EVENTOS": "02 EVENTOS", "VIDEO": "03 VIDEO",
                 "FOTOS": "04 FOTOS", "MUSICA": "05 MUSICA", "EFECTOS": "06 EFECTOS"}
ALIAS_RAIZ = {"EVENTOS": ("SECUENCIAS",)}          # nombres de versiones anteriores


def carpeta_raiz(mp, root, clave, crear=True):
    """Carpeta principal por clave ('VIDEO', 'EVENTOS'...), con o sin numero delante."""
    nombres = (clave,) + ALIAS_RAIZ.get(clave, ())
    for f in root.GetSubFolderList() or []:
        if re.sub(r"^\d+\s+", "", f.GetName()) in nombres:
            return f
    return mp.AddSubFolder(root, CARPETAS_RAIZ.get(clave, clave)) if crear else None


def organizar_pool(mp, root, evento, items):
    """Media pool profesional: 04 FOTOS\\<EVENTO>\\01 MAQUILLAJE ... y 03 VIDEO\\<EVENTO>\\01 MAQUILLAJE\\CAMARA|
    CELULAR|DRON, cada clip con el color de su momento (morado / verde / rosa). Mueve lo ya importado y solo
    importa lo que falte. Devuelve {ruta: MediaPoolItem}."""
    def sub(padre, nombre, crear=True):
        if padre is root:
            return carpeta_raiz(mp, root, nombre, crear)
        for f in padre.GetSubFolderList() or []:
            if f.GetName() == nombre:
                return f
        return mp.AddSubFolder(padre, nombre) if crear else None

    existentes = {}

    def recorrer(f):
        for c in f.GetClipList() or []:
            r = c.GetClipProperty("File Path")
            if r:
                existentes.setdefault(os.path.normcase(r), (c, f))
        for s in f.GetSubFolderList() or []:
            recorrer(s)
    for top in ("FOTOS", "VIDEO", "DRON"):               # lo ya importado en este u otro evento se MUEVE
        f = sub(root, top, False)
        if f:
            ev = sub(f, evento, False)
            if ev:
                recorrer(ev)                              # primero el evento actual (prioridad)
            for otro in f.GetSubFolderList() or []:
                if otro.GetName() != evento:
                    recorrer(otro)
    pool = {}
    for top, tipos in (("FOTOS", ("foto",)), ("VIDEO", ("video", "dron"))):
        for mom in ZONAS + ["DESCARTADOS"]:
            sel = [i for i in items if i["tipo"] in tipos and
                   ("DESCARTADOS" if i.get("descartar") else i.get("momento")) == mom]
            if not sel:
                continue
            carpeta_mom = sub(sub(sub(root, top), evento), CARPETAS_MOMENTO[mom])
            por_destino = {}
            for i in sel:
                por_destino.setdefault(fuente(i) if top == "VIDEO" else "", []).append(i)
            for nombre_dest, grupo_sel in sorted(por_destino.items()):
                dest = sub(carpeta_mom, nombre_dest) if nombre_dest else carpeta_mom
                mover = [existentes[k][0] for k in (os.path.normcase(i["ruta"]) for i in grupo_sel)
                         if k in existentes and existentes[k][1].GetUniqueId() != dest.GetUniqueId()]
                if mover:
                    mp.MoveClips(mover, dest)
                faltan = [i["ruta"] for i in grupo_sel if os.path.normcase(i["ruta"]) not in existentes]
                mp.SetCurrentFolder(dest)
                for j in range(0, len(faltan), 100):
                    if not mp.ImportMedia(faltan[j:j + 100]):
                        mp.ImportMedia([{"FilePath": r} for r in faltan[j:j + 100]])
                color = COLORES.get(mom, "Brown")
                for c in dest.GetClipList() or []:
                    r = c.GetClipProperty("File Path")
                    if r:
                        pool[os.path.normcase(r)] = c
                        c.SetClipColor(color)

    def vaciar_viejas(f):                            # quita carpetas que quedaron vacias
        for s in f.GetSubFolderList() or []:
            vaciar_viejas(s)
        if not (f.GetClipList() or []) and not (f.GetSubFolderList() or []):
            mp.DeleteFolders([f])
    for top in ("FOTOS", "VIDEO", "DRON"):
        f = sub(root, top, False)
        for ev in (f.GetSubFolderList() or []) if f else []:
            vaciar_viejas(ev)
        if top == "DRON" and f and not (f.GetClipList() or []) and not (f.GetSubFolderList() or []):
            mp.DeleteFolders([f])
    return pool


# ------------------------------------------------------------------ todo junto
def main():
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        aviso("No hay proyecto abierto en Resolve.")
        return
    analisis = globals().get("ANALISIS") or _modulo("analizar_material").analizar(BASE, log=print)
    items = analisis.get("items") or []
    if not any(i["tipo"] == "foto" for i in items) or not any(i["tipo"] != "foto" for i in items):
        aviso("Faltan fotos o videos en las carpetas.")
        return
    perfil = cargar_perfil(TIPO_EVENTO)
    evento = EVENTO or "%s %s" % (perfil["prefijo"], analisis["fecha"])
    reporte["evento"] = evento
    reporte["tipo"] = TIPO_EVENTO
    f = datetime.date.fromisoformat(analisis["fecha"])
    fecha_txt = "%02d · %02d · %d" % (f.day, f.month, f.year)
    for i, z in enumerate(ZONAS, 1):                 # carpetas del media pool con los nombres del perfil
        CARPETAS_MOMENTO[z] = "%02d %s" % (i, perfil["momentos"].get(z, z).upper())

    tls = {}
    for i in range(1, project.GetTimelineCount() + 1):
        t = project.GetTimelineByIndex(i)
        tls[t.GetName()] = t
    pendientes = []
    for ver in VERSIONES:
        if SOLO and ver["sufijo"] not in SOLO:
            continue
        if ver["plantilla"] not in tls:
            aviso("No existe la plantilla '%s' en el proyecto." % ver["plantilla"])
        else:
            pendientes.append((ver, tls[ver["plantilla"]]))
    if not pendientes:
        return
    try:
        fps = int(round(float(pendientes[0][1].GetSetting("timelineFrameRate"))))
    except Exception:
        fps = 24
    intro_f = sum(INTRO_CORTES)
    ritmo = _modulo("ritmo") if CORTAR_AL_RITMO else None

    # ---------- plan (con lo que Resolve entendio de cada escena: votos, brindis, el beso...) ----------
    ia = _modulo("escenas_ia")
    ia.aplicar(items)                            # lo ya escuchado en otros armados (cache)

    def planificar():
        reporte["versiones"] = []
        plan = Planificador(items, fps)
        planes = []
        for k, (ver, tpl) in enumerate(pendientes):
            rng = random.Random(2000 + k)
            total_f = int(ver["seg"] * fps)
            golpes = []
            if ritmo:
                try:
                    golpes = ritmo.golpes(tpl, fps, BASE, log=print)
                except Exception as ex:
                    aviso("%s: no se pudo leer el ritmo (%s)" % (ver["sufijo"], ex))
            intro = plan.intro(k)
            zonas, info_z, al_golpe = [], {}, 0
            for nombre, z0, z1 in zonas_de(tpl.GetMarkers() or {}, total_f, intro_f, fps):
                if nombre == "APERTURA":
                    # el resumen inicial muestra los mejores momentos: en las versiones largas NO los reserva,
                    # porque luego se cuentan completos en su zona (en 1 y 3 min si, para no repetir planos)
                    reservados = {k: list(v) for k, v in plan.usados.items()}
                    piezas, reusos = plan.zona(ZONAS, z1 - z0, ver["apertura"], rng, True)
                    if ver["seg"] > 180:
                        plan.usados = reservados
                    lo = ver["apertura"][0]
                else:
                    piezas, reusos = plan.zona([nombre], z1 - z0, ver["corte"], rng, nombre != "MAQUILLAJE")
                    lo = ver["corte"][0]
                al_golpe += al_ritmo(piezas, z0, z1, golpes, fps, lo)
                zonas.append((nombre, z0, z1, piezas))
                info_z[nombre] = {"seg": round((z1 - z0) / float(fps), 1),
                                  "videos": len(piezas), "dron": sum(1 for p in piezas if p["tipo"] == "dron"),
                                  "fotos": 0, "reutilizados": reusos}
                if reusos:
                    aviso("%s %s: %d planos repiten video ya usado (falta material)." % (ver["sufijo"], nombre, reusos))
            lentos, estab = plan.marcar_efectos(zonas, fps, LENTOS.get(ver["sufijo"], 2))
            planes.append((ver, tpl, intro, zonas))
            reporte["versiones"].append({"timeline": "%s - %s" % (evento, ver["sufijo"]), "zonas": info_z,
                                         "fotos_intro": len(intro), "cortes_al_ritmo": al_golpe,
                                         "camara_lenta": lentos, "estabilizar": estab})
            print("%s: %s | %d cortes al ritmo | %d en camara lenta | %d a estabilizar" % (ver["sufijo"], ", ".join(
                "%s %d" % (n, z["videos"]) for n, z in info_z.items()), al_golpe, lentos, estab))
        return plan, planes
    plan, planes = planificar()
    if DRY_RUN:
        return

    # ---------- respaldo ----------
    try:
        pm.SaveProject()
        dir_r = rutas.RESPALDOS
        os.makedirs(dir_r, exist_ok=True)
        pm.ExportProject(project.GetName(), os.path.join(
            dir_r, "%s_%s.drp" % (project.GetName(), datetime.datetime.now().strftime("%Y-%m-%d_%H%M"))), False)
    except Exception as ex:
        aviso("No se pudo respaldar el proyecto (%s)" % ex)

    # ---------- media pool clasificado por colores ----------
    mp = project.GetMediaPool()
    root = mp.GetRootFolder()
    instalar_dctl(project)
    rd = _modulo("ruido")
    ruido_n = int(RUIDO) if RUIDO is not None else rd.DEFECTO
    try:                                        # DCTL de ruido con la intensidad elegida
        rd.escribir(ruido_n, os.path.join(rutas.DATOS, "dctl"))
        project.RefreshLUTList()
    except Exception as ex:
        aviso("No se pudo escribir la reduccion de ruido (%s)" % ex)
    reporte["ruido"] = ruido_n
    objetivos = objetivos_de_luz(items)
    reporte["luz_objetivo"] = {k: round(v, 3) for k, v in objetivos.items()}
    pool = organizar_pool(mp, root, evento, items)
    print("Media pool: %d archivos en carpetas MAQUILLAJE / IGLESIA / FIESTA con colores" % len(pool))
    try:                                         # la IA de Resolve escucha los videos: votos, brindis, discursos
        pares = [(pool[os.path.normcase(i["ruta"])], i) for i in items
                 if i["tipo"] == "video" and i.get("audio_pista", True) and not i.get("descartar")
                 and os.path.normcase(i["ruta"]) in pool]
        antes = ia.aplicar(items)
        cache_ia = ia.entender(resolve, project, pares, print)
        if ia.aplicar(items, cache_ia) != antes:
            plan, planes = planificar()          # con las frases nuevas el plan cambia
    except Exception as ex:
        aviso("No se pudo escuchar los videos con la IA de DaVinci (%s)" % ex)
    whoosh = buscar_clip(root, WHOOSH)
    png = png_texto(mp, root)
    grupos = {g.GetName(): g for g in project.GetColorGroupsList() or []}

    def carpeta_tl():                           # 02 EVENTOS\<EVENTO>: las timelines armadas
        padre = carpeta_raiz(mp, root, "EVENTOS")
        for x in padre.GetSubFolderList() or []:
            if x.GetName() == evento:
                return x
        return mp.AddSubFolder(padre, evento)
    dir_tl = carpeta_tl()
    salida = os.path.join(rutas.TERMINADOS, evento)

    for (ver, tpl, intro, zonas), info in zip(planes, reporte["versiones"]):
        nombre = info["timeline"]
        if nombre in tls:
            if not REHACER:
                aviso("%s ya existe; no se toca (REHACER = True para volver a armarla)." % nombre)
                continue
            project.SetCurrentTimeline(tpl)         # Resolve no borra la timeline abierta
            if not mp.DeleteTimelines([tls[nombre]]):
                aviso("No se pudo borrar la version anterior de %s; ciérrala en Resolve y vuelve a armar." % nombre)
                continue
            del tls[nombre]
        mp.SetCurrentFolder(dir_tl)
        tl = None
        for intento in range(4):                # justo despues de borrar, Resolve a veces tarda en liberar el nombre
            tl = tpl.DuplicateTimeline(nombre)
            if tl:
                break
            time.sleep(1.5)
            project.SetCurrentTimeline(tpl)
        if not tl:
            aviso("No se pudo duplicar %s (vuelve a pulsar Armar)" % ver["plantilla"])
            continue
        tls[nombre] = tl
        try:
            mp.MoveClips([tl.GetMediaPoolItem()], dir_tl)
        except Exception:
            pass
        project.SetCurrentTimeline(tl)
        time.sleep(1.0)            # Resolve solo cambia el estado de los clips de la timeline activa y ya asentada
        tl = project.GetCurrentTimeline() or tl
        for t in range(1, tl.GetTrackCount("video") + 1):
            for it in tl.GetItemListInTrack("video", t) or []:
                if (it.GetName() or "").strip().upper() in ACTIVAR_SIEMPRE and not it.GetClipEnabled():
                    tl.SetTrackLock("video", t, False)
                    it.SetClipEnabled(True)
        st = tl.GetStartFrame()
        pv, pf = pista(tl, "video", PISTA_VIDEOS, 1), pista(tl, "video", PISTA_FOTOS, 2)
        for t in (pv, pf):
            tl.SetTrackLock("video", t, False)
            viejos = tl.GetItemListInTrack("video", t) or []
            if viejos:
                tl.DeleteClips(viejos, False)

        secuencia, pos = [], st
        for p in intro:
            secuencia.append((pf, pos, p))
            pos += p["dur_f"]
        for _, z0, _, piezas in zonas:
            pos = st + z0
            for p in piezas:
                secuencia.append((pv, pos, p))
                pos += p["dur_f"]
        puestos = colocar(mp, secuencia, pool, fps)
        info["clips"] = len(puestos)
        if len(puestos) < len(secuencia):
            aviso("%s: se pidieron %d clips y se colocaron %d." % (nombre, len(secuencia), len(puestos)))

        grupo = grupos.get(ver["grupo"])
        for p, x in puestos:                    # llenar cuadro, color del momento, grupo, ruido e igualacion
            try:                                # fotos 3:2 o videos 4:3 llenan el 16:9 sin franjas negras
                if not x.SetProperties({"Scaling": resolve.SCALE_FILL}):
                    x.SetProperty("Scaling", resolve.SCALE_FILL)
            except Exception:
                pass
            try:
                x.SetClipColor(COLORES.get((p.get("momento") or p["item"].get("momento")), "Brown"))
                if grupo:
                    x.AssignToColorGroup(grupo)
                if p["tipo"] != "foto":
                    rd.aplicar_a_item(x, ruido_n)
                    if IGUALAR:
                        cdl = cdl_para(p, objetivos.get((p.get("momento") or p["item"].get("momento")), 0.42))
                        if cdl and x.SetCDL(cdl):
                            info["igualados"] = info.get("igualados", 0) + 1
            except Exception:
                pass
        if grupo:
            preparar_grupo(grupo)
        info["camara_lenta"] = sum(1 for p, _ in puestos if p.get("lento_ok"))
        info["estabilizados"] = estabilizar(puestos)
        info["transiciones"] = transiciones(tl, pv, zonas, ver)
        info["titulos"] = titulos(tl, ver, fps, fecha_txt, perfil, f.year)
        info["textos_plantilla"] = textos_plantilla(tl, perfil)
        cortes = sorted(x.GetStart() - st for _, x in puestos)
        try:                                     # capitulos, frases y gracias
            info["textos_nuevos"] = textos_extra(tl, mp, png, zonas, fps, perfil, ver, cortes)
        except Exception as ex:
            aviso("%s: no se pudieron poner los textos nuevos (%s)" % (nombre, ex))
        info["whoosh"] = whooshes(tl, mp, zonas, fps, whoosh)
        try:                                     # SFX segun el momento (campanas en la iglesia, vitores en la fiesta)
            info["sfx"] = _modulo("sfx").sonorizar(tl, mp, lambda k: buscar_clip(root, k),
                                                   [(n, a, b) for n, a, b, _ in zonas], fps, cortes, print)
        except Exception as ex:
            aviso("%s: no se pudieron colocar los SFX (%s)" % (nombre, ex))
        voces = []
        try:                                     # votos / "los declaro" / brindis como voz sobre la musica
            voces = poner_voces(tl, mp, pool, elegir_voces(items, VOCES.get(ver["sufijo"], 1), zonas), zonas, fps)
            info["voces"] = ["%s «%s»" % (fr["tipo"], fr["texto"][:60]) for _, _, fr in voces]
        except Exception as ex:
            aviso("%s: no se pudo poner la voz (%s)" % (nombre, ex))
        try:                                     # mezcla medida: canciones, SFX y voz a su nivel (LUFS)
            info["mezcla"] = _modulo("mezcla").nivelar(tl, fps, BASE, print)
        except Exception as ex:
            aviso("%s: no se pudo nivelar el sonido (%s)" % (nombre, ex))
        try:                                     # la musica baja debajo de cada voz
            info["musica_bajada"] = bajar_musica(tl, mp, voces, fps)
        except Exception as ex:
            aviso("%s: no se pudo bajar la musica bajo la voz (%s)" % (nombre, ex))

        total_f = int(ver["seg"] * fps)
        tl.SetMarkInOut(st, st + total_f - 1, "all")
        if ENCOLAR_RENDER:
            try:
                os.makedirs(salida, exist_ok=True)
                for job in project.GetRenderJobList() or []:
                    if job.get("TimelineName") == nombre:
                        project.DeleteRenderJob(job.get("JobId"))
                project.SetRenderSettings({"SelectAllFrames": False, "MarkIn": st, "MarkOut": st + total_f - 1,
                                           "TargetDir": salida, "CustomName": nombre})
                info["render_en_cola"] = bool(project.AddRenderJob())
            except Exception as ex:
                aviso("%s: no se pudo encolar el render (%s)" % (nombre, ex))
        print("%s lista: %d clips, %d igualados en color, %d transiciones, %d titulos + %d textos nuevos, %d whoosh, "
              "%d SFX por momento, %d sonidos nivelados, %d en camara lenta, %d estabilizados, %d voces" % (
                  nombre, len(puestos), info.get("igualados", 0), info["transiciones"], info["titulos"],
                  info.get("textos_nuevos", 0), info["whoosh"], len(info.get("sfx") or []), info.get("mezcla", 0),
                  info.get("camara_lenta", 0), info.get("estabilizados", 0), len(info.get("voces") or [])))
        for v in info.get("voces") or []:
            print("   voz: %s" % v)
    pm.SaveProject()


main()
result = reporte
