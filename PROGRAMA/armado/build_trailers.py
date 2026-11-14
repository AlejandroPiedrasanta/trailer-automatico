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
MARGEN = 1.0                  # s que se evitan al inicio y fin de cada video (arranque de camara, handles)
SEPARACION = 0.5              # s minimos entre dos planos del mismo video
PASO_CALIDAD = 0.5            # s por muestra de calidad (igual que analizar_material)
BRILLO_MIN_INTRO = 0.18
UMBRAL_LENTO = 0.55           # emocion media (0-1) para que un plano vaya en camara lenta
UMBRAL_LENTO_MIN = 0.30       # si no hay bastantes con UMBRAL_LENTO, se baja hasta aqui (los mas emotivos primero)
UMBRAL_TEMBLOR = 0.6          # temblor medio (px en 192 de ancho) para pasar el estabilizador de Resolve
LENTOS = {"1min": 3, "3min": 6, "15min": 12, "30min": 18}    # planos en camara lenta por version
LENTO_MIN_S = 1.5             # s en pantalla que debe durar un plano para ir en camara lenta (si no, no se aprecia)
LENTO_PARTE_ZONA = 0.45       # como mucho esta parte de las camaras lentas en un mismo momento (repartidas)
# El FINAL: desde un poco antes del marcador CIERRE hasta el ultimo cuadro va UNA sola imagen con la tarjeta final
# encima: la mejor foto del evento con zoom lento (Planificador.foto_final) o, si no hay foto que valga, el mejor
# plano de video en camara lenta (Planificador.heroe). Antes caia el plano que tocara (espaldas bailando).
FINAL_ANTES_S = 1.5           # s antes del marcador CIERRE en que entra el plano final
FINAL_VEL = 0.5               # velocidad del plano final (Speed Warp de Resolve inventa los cuadros que faltan)
UMBRAL_PLANO = 0.20           # puntaje minimo de un tramo para entrar; por debajo se rellena (dron, fotos) o se
#                               repite uno bueno, antes que meter una toma floja
VOCES = {"1min": 1, "3min": 2, "15min": 6, "30min": 14}      # pasajes de voz original (pastor, brindis, discursos)
# Voz original por version. En el video largo (30 min) va SIEMPRE; en el de 15 viene activada y en los cortos no
# (la persona lo cambia en Ajustes > Voz original: llega aqui como VOZ = {"1min": True, ...}).
VOZ_DEFECTO = {"1min": False, "3min": False, "15min": True, "30min": True}
VOZ_SIEMPRE = ("30min",)
VOZ_LARGO = {"1min": (3.0, 7.0), "3min": (4.0, 9.0), "15min": (6.0, 16.0), "30min": (8.0, 24.0)}   # s de cada pasaje
# ---- Tomas malas: medidas ABSOLUTAS del analizador ("vista" de cada medio segundo). No se comparan con el propio
# video: un video entero grabado por accidente (camara colgando, apuntando al piso) ya no puntua como uno bueno.
FOCO_MIN = 0.20               # enfoque respecto al tipico de ESA camara: por debajo esta desenfocada o movida
QUEMADO_MAX = 0.25            # parte de la imagen con las luces reventadas desde la que la toma no se usa
QUEMADO_SUAVE = 0.02          # desde aqui ya resta puntaje: se prefiere otra toma del mismo momento
BARRIDO_MAX = 8.0             # px por cuadro (192 de ancho, 10 c/s): la camara barre y no se ve nada
TEMBLOR_MAX = 5.0             # temblor que ni el estabilizador arregla
OSCURA_MAX = 0.07             # luz media con la que ya no se ve nada
TORCIDA = (25, 0.20, 0.16)    # giro minimo, pico minimo y eje maximo: camara ladeada o apuntando al piso
ENFOQUE_CAIDA = 0.40           # el enfoque cae a esta parte del de 2 s alrededor: desenfoque momentaneo o tiron
BORDE_MALO = 0.5              # s que se evitan a cada lado de un tramo malo (la camara aun se esta acomodando)
VIDEO_ACCIDENTAL = 0.15       # si sirve menos de esta parte del video, el video entero fue un accidente
PARECIDAS = 10                # bits de diferencia (de 64) con los que dos imagenes son el mismo encuadre
TOPE_MISMO_ENCUADRE = 0.22    # parte de los planos de una zona que puede venir del mismo video o encuadre
TOPE_DRON = 0.15              # parte de los planos de una zona que puede ser de dron
# ---- Relleno cuando no alcanzan las tomas buenas (mejor que repetir o meter una toma fea)
RELLENO_FOTOS = ("30min",)    # versiones que se rellenan con fotos del mismo momento
FOTO_RELLENO_S = (3.0, 4.5)   # s que dura cada foto de relleno
# 30 c/s en una linea de 24: Resolve tira 1 de cada 5 cuadros y el movimiento salta. Al 80 % se ven TODOS los
# cuadros (lento suave, sin saltos). Solo en los planos sin voz sincronizada.
CONFORMAR_30_A_24 = True
FUNDIDO_FOTO = 12             # cuadros del encadenado al entrar y salir de una foto de relleno
FUNDIDO_SALTO = 8             # cuadros del encadenado entre dos planos casi iguales (evita el salto)
# El mismo video usado varias veces en una zona (la camara fija de la ceremonia, el vals): se alterna el plano
# abierto con uno acercado, como si fueran dos camaras. Asi el corte entre dos trozos del mismo encuadre no se ve
# como un salto. Solo con fuente 4K (acercar no pierde nitidez en la linea de 1080).
ACERCAR = 1.28                # cuanto se acerca el plano alterno
ACERCAR_ANCHO_MIN = 3000      # ancho minimo de la fuente para acercar
# True = tambien entran los videos grabados en vertical (celular parado): llenan la pantalla recortados y el
# reencuadre inteligente de Resolve Studio (Smart Reframe) sigue a la persona. Lo decide Ajustes > Videos verticales.
USAR_VIDEOS_VERTICALES = bool(globals().get("VERTICALES", False))
# Igualacion automatica por plano (CDL en el nodo del clip): exposicion, negros, balance de blancos, saturacion
IGUALAR = globals().get("IGUALAR", True)
# Las tomas ya vienen en Rec.709 (color terminado de camara): la correccion por plano solo EMPAREJA, con poco margen.
FUERZA_EXPOSICION = 0.4           # 0 = no toca, 1 = iguala del todo a la luz tipica del momento
FUERZA_BLANCOS = 0.4              # cuanto corrige la dominante de color de los grises
LUZ_OBJETIVO = (0.30, 0.50)       # limites de la luz tipica de cada momento
PENDIENTE_LIMITES = (0.92, 1.12)  # cuanto puede oscurecer o aclarar una toma
NEGRO_LECHOSO = 0.08              # desde aqui el negro se considera lavado y se limpia (antes 0.05: tocaba de mas)
DESPLAZO_LIMITES = (-0.04, 0.02)  # cuanto baja unos negros lechosos
BLANCOS_LIMITES = (0.96, 1.04)    # cuanto mueve cada canal al quitar una dominante
SAT_OBJETIVO = 0.36               # respaldo; lo normal es la saturacion tipica del propio evento (objetivo_de_saturacion)
SAT_OBJETIVO_LIMITES = (0.28, 0.38)
SAT_LIMITES = (0.85, 1.00)        # cuanto puede bajar la saturacion de una toma (LED de fiesta); nunca sube
POTENCIA_MAX = 1.22               # cuanto puede bajar los medios (gamma) una toma sobreexpuesta, sin tocar el blanco
FUERZA_QUEMADA = 0.75             # fuerza de la exposicion cuando la toma viene con las luces reventadas de camara
FUENTE_TITULO, FUENTE_SUB = "Great Vibes", "Montserrat"
ESTILO_SUB = "Regular"            # peso del subtitulo (Light se pierde sobre vestidos blancos)
VELO_TITULO = 0.55                # oscuridad del velo suave detras de los titulos (0 = sin velo)
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
LOOK_REC709 = {"1min": "MCP/XV_1min_CINE_TEAL_ORANGE_REC709.cube", "3min": "MCP/XV_3min_ROMANTICO_CALIDO_REC709.cube",
               "15min": "MCP/XV_15min_FILM_KODAK_REC709.cube", "30min": "MCP/XV_30min_NATURAL_SUAVE_REC709.cube"}
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
    ruta = rutas.codigo(nombre + ".py")
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
        validos = [i for i in items if i["tipo"] != "foto" and not i.get("descartar")]
        horizontales = [i for i in validos if i.get("horizontal", True)]
        utiles_h = sum(max(0.0, i.get("dur", 0) - sum(b - a for a, b in i.get("oscuros") or [])) for i in horizontales)
        verticales = USAR_VIDEOS_VERTICALES or len(horizontales) < 3 or utiles_h < 45
        self.vids = validos if verticales else horizontales
        n_vert = len(validos) - len(horizontales)
        if n_vert and not verticales:
            print("%d video%s fuera del montaje (%s en el media pool)."
                  % (n_vert, " vertical queda" if n_vert == 1 else "s verticales quedan", "esta" if n_vert == 1 else "estan"))
        elif n_vert and not USAR_VIDEOS_VERTICALES:      # casi todo es de celular parado: mejor recortado que en negro
            print("Hay pocos videos horizontales: se usan tambien los %d verticales (llenando el cuadro)." % n_vert)
        self.fotos = self._sin_repetidas([i for i in items if i["tipo"] == "foto" and not i.get("descartar")
                                          and i.get("horizontal", True)])
        self.usados = {}
        self.fotos_usadas = set()
        self._pref = {}
        self._emo = {}
        self._vistas = {}
        self._firmas = {}
        self._refs = self._enfoque_tipico(self.vids)
        # videos grabados por accidente (camara colgando, desenfocada, apuntando al piso): no entran al montaje
        accidentes = [v for v in self.vids if (v.get("vista") or {}).get("nit") and self.parte_buena(v) < VIDEO_ACCIDENTAL]
        self.accidentales = []
        if accidentes and len(accidentes) < len(self.vids):
            self.accidentales = [v["nombre"] for v in accidentes]
            fuera = {v["ruta"] for v in accidentes}
            self.vids = [v for v in self.vids if v["ruta"] not in fuera]
            print("%d video%s fuera del montaje por accidental%s (desenfocado, movido o apuntando al piso): %s"
                  % (len(accidentes), "" if len(accidentes) == 1 else "s", "" if len(accidentes) == 1 else "es",
                     ", ".join(v["nombre"] for v in accidentes[:8]) + ("…" if len(accidentes) > 8 else "")))

    @staticmethod
    def _camara(v):
        return (v.get("camara") or "?", v.get("ancho"), v["tipo"] == "dron")

    def _enfoque_tipico(self, vids):
        """Enfoque tipico (mediana) de cada camara del evento: contra ESO se mide cada toma."""
        por = {}
        for v in vids:
            por.setdefault(self._camara(v), []).extend((v.get("vista") or {}).get("nit") or [])
        return {k: _mediana(x) for k, x in por.items() if x}

    def vista(self, v):
        """([(a, b)] tramos que NO se usan, [factor 0-1 de cada medio segundo]) por lo que se ve en la toma:
        desenfocada o movida, luces reventadas, camara barriendo, temblor fuerte, a oscuras o ladeada / al piso."""
        r = self._vistas.get(v["ruta"])
        if r is not None:
            return r
        vi = v.get("vista") or {}
        nit = vi.get("nit") or []
        ref = self._refs.get(self._camara(v)) or 0.0
        quem, pan = vi.get("quem") or [], vi.get("pan") or []
        giro, pico, eje = vi.get("giro") or [], vi.get("pico") or [], vi.get("eje") or []
        tem, col = v.get("temblor") or [], v.get("color") or []
        dron = v["tipo"] == "dron"
        malo, factor = [], []
        for i in range(len(nit)):
            foco = nit[i] / ref if ref > 0 else 1.0
            q = quem[i] if i < len(quem) else 0.0
            p = math.hypot(pan[i][0], pan[i][1]) if i < len(pan) else 0.0
            t = tem[i] if i < len(tem) else 0.0
            luz = col[i][0] if i < len(col) else 0.3
            torcida = (not dron and i < len(giro) and i < len(pico) and i < len(eje)
                       and giro[i] >= TORCIDA[0] and pico[i] >= TORCIDA[1] and eje[i] <= TORCIDA[2])
            # se va de foco un momento, alguien cruza pegado al lente o la camara da un tiron: el enfoque cae a
            # menos de la mitad de lo que tiene 2 s antes y despues
            cerca = max(nit[max(0, i - 4):i + 5])
            tiron = cerca > 0 and nit[i] < ENFOQUE_CAIDA * cerca and cerca >= 0.4 * ref
            m = (foco < FOCO_MIN or q >= QUEMADO_MAX or p > BARRIDO_MAX or t > TEMBLOR_MAX or luz < OSCURA_MAX
                 or torcida or tiron)
            malo.append(m)
            if m:
                factor.append(0.0)
            else:
                fq = 1.0 - 0.65 * _lim((q - QUEMADO_SUAVE) / (QUEMADO_MAX - QUEMADO_SUAVE), 0.0, 1.0)
                ff = _lim(foco / 0.6, 0.4, 1.0)
                fp = 1.0 - 0.4 * _lim((p - 3.0) / (BARRIDO_MAX - 3.0), 0.0, 1.0)
                factor.append(fq * ff * fp)
        tramos, i = [], 0
        while i < len(malo):
            if malo[i]:
                j = i
                while j + 1 < len(malo) and malo[j + 1]:
                    j += 1
                tramos.append((i * PASO_CALIDAD - BORDE_MALO, (j + 1) * PASO_CALIDAD + BORDE_MALO))
                i = j + 1
            else:
                i += 1
        r = (tramos, factor)
        self._vistas[v["ruta"]] = r
        return r

    def parte_buena(self, v):
        """Parte (0-1) del video que se puede usar."""
        _, factor = self.vista(v)
        return sum(1 for f in factor if f > 0.0) / float(len(factor)) if factor else 1.0

    def huella(self, v, t):
        """Huella de la imagen (64 bits) del video en el segundo t; None si no se midio."""
        hs = (v.get("vista") or {}).get("hash") or []
        if not hs:
            return None
        return int(hs[min(len(hs) - 1, max(0, int(t / PASO_CALIDAD)))], 16)

    def firma(self, v):
        """Tres huellas del video (al 25, 50 y 75 %): dos videos con la misma firma son el mismo encuadre (la camara
        en el tripode grabando varios archivos seguidos)."""
        f = self._firmas.get(v["ruta"])
        if f is None:
            f = [self.huella(v, v["dur"] * k) for k in (0.25, 0.5, 0.75)]
            self._firmas[v["ruta"]] = f
        return f

    def mismo_encuadre(self, a, b):
        if a is b:
            return True
        fa, fb = self.firma(a), self.firma(b)
        if None in fa or None in fb:
            return False
        return sum(1 for x in fa if min(bin(x ^ y).count("1") for y in fb) <= PARECIDAS + 3) >= 2

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

    def utiles(self, v, momentos=None, estricto=True):
        u = restar([(MARGEN, v["dur"] - MARGEN)], v.get("oscuros") or [])
        if estricto:                                # fuera lo que se ve mal (desenfocado, quemado, al piso...)
            u = restar(u, self.vista(v)[0])
        if momentos and v.get("tramos"):            # solo los tramos de ese momento
            u = restar(u, [(a, b) for a, b, m in v["tramos"] if m not in momentos])
        return u

    def libres(self, v, momentos=None):
        return restar(self.utiles(v, momentos), self.usados.get(v["ruta"], []))

    def _serie(self, v):
        """Puntaje de cada medio segundo: calidad (nitidez, luz, sin temblor) x lo que se ve (enfoque real, luces
        sin quemar, camara quieta) x emocion del audio (aplausos, gritos, brindis: sube sobre lo normal del video)."""
        cal = v.get("calidad") or []
        emo = self.emocion(v)
        _, factor = self.vista(v)
        return [c * (factor[i] if i < len(factor) else 1.0) * (0.85 + 0.35 * (emo[i] if i < len(emo) else 0.0))
                for i, c in enumerate(cal)]

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
                if p["tipo"] != "video" or p.get("sincro") or p.get("heroe"):
                    continue
                v = p["item"]
                l = p["dur_f"] / float(fps)
                e = self.media(self.emocion(v), p["ini"], l)
                # camara lenta donde pasa algo (aplausos, gritos, una frase clave) y la toma esta firme: lento sobre
                # una toma que tiembla o barre solo alarga el defecto
                firme = self.media(v.get("temblor") or [], p["ini"], l) <= 2.5
                if nombre in ("IGLESIA", "FIESTA", "APERTURA") and e >= UMBRAL_LENTO_MIN and l >= LENTO_MIN_S and firme:
                    cand.append((e, nombre, p))
        lentos, por_zona = sum(1 for _, _, _, ps in zonas for p in ps if p.get("heroe")), {}
        tope_zona = max(1, int(math.ceil(max_lentos * LENTO_PARTE_ZONA)))
        for umbral in (UMBRAL_LENTO, UMBRAL_LENTO_MIN):          # primero los claros; si faltan, los siguientes
            for e, nombre, p in sorted(cand, key=lambda t: -t[0]):
                if lentos >= max_lentos:
                    break
                if e < umbral or p.get("vel") or por_zona.get(nombre, 0) >= tope_zona:
                    continue
                vf = p["item"].get("fps") or 30
                p["vel"] = 0.4 if vf >= 48 else 0.5      # 60 fps: lento natural; 24-30 fps: Speed Warp inventa cuadros
                por_zona[nombre] = por_zona.get(nombre, 0) + 1
                lentos += 1
        for _, _, _, piezas in zonas:
            for p in piezas:
                if p["tipo"] == "foto" or p["tipo"] == "dron":
                    continue
                l = p["dur_f"] / float(fps) * p.get("vel", 1.0)
                if self.media(p["item"].get("temblor") or [], p["ini"], l) >= UMBRAL_TEMBLOR:
                    p["estabilizar"] = True
        return lentos, sum(1 for _, _, _, ps in zonas for p in ps if p.get("estabilizar"))

    def foto_final(self, dur_f):
        """La imagen del FINAL: la mejor foto del evento (las del fotografo son retratos cuidados de la persona
        festejada), de la ceremonia o la fiesta si hay, bien expuesta y sin quemar: la mas nitida. Va con zoom lento
        y la tarjeta final encima. Devuelve la pieza o None si no hay ninguna foto que valga."""
        cand = [f for f in self.fotos if f.get("nitidez") is not None and f.get("quemado", 0.0) < 0.08
                and 0.22 <= f.get("brillo", 0.5) <= 0.62]
        tarde = [f for f in cand if f.get("momento") in ("IGLESIA", "FIESTA")]
        cand = tarde or cand
        if not cand:
            return None
        f = max(cand, key=lambda x: x["nitidez"])
        self.fotos_usadas.add(f["ruta"])
        return {"tipo": "foto", "item": f, "dur_f": dur_f, "orden": _hora(f), "momento": f.get("momento"),
                "relleno": True, "final": True, "hash": int(f["dhash"], 16) if f.get("dhash") else None}

    def heroe(self, dur_f, vel=FINAL_VEL):
        """El plano del FINAL: el mejor tramo del evento para cerrar (emotivo, firme, sin quemar), que ira en camara
        lenta. De la ceremonia o la fiesta, no de dron. Devuelve la pieza o None."""
        l = dur_f / float(self.fps) * vel               # en lento se gasta menos toma de la que se ve
        mejor = None
        for v in self.vids:
            if v["tipo"] != "video" or not (v.get("vista") or {}).get("nit"):
                continue
            tem, pan = v.get("temblor") or [], (v.get("vista") or {}).get("pan") or []
            for a, b in self.utiles(v, ("IGLESIA", "FIESTA")):
                x = a
                while x + l <= b + 1e-6:
                    if self.momento_en(v, x + l / 2.0) not in ("IGLESIA", "FIESTA"):
                        x += 0.5
                        continue
                    emo = self.media(self.emocion(v), x, l)
                    quieto = 1.0 - 0.5 * _lim(self.media(tem, x, l) / 3.0, 0.0, 1.0)
                    i0 = int(x / PASO_CALIDAD)
                    barre = max([math.hypot(q[0], q[1]) for q in pan[i0:i0 + max(1, int(l / PASO_CALIDAD))]] or [0.0])
                    sc = self.puntaje(v, x, l) * (0.6 + 0.8 * emo) * quieto * (1.0 - 0.5 * _lim(barre / 6.0, 0.0, 1.0))
                    if mejor is None or sc > mejor[0]:
                        mejor = (sc, v, x)
                    x += 0.5
        if mejor is None:
            return None
        p = self._pieza(mejor[1], mejor[2], dur_f, marcar=False)
        p["vel"] = 0.4 if (mejor[1].get("fps") or 30) >= 48 else vel
        # colocar() centra la parte que se ve dentro de [ini, ini + largo en pantalla]: se corre el inicio para que lo
        # que se vea sea justo el tramo elegido
        p["ini"] = max(0.0, mejor[2] - dur_f / float(self.fps) * (1.0 - p["vel"]) / 2.0)
        p["heroe"] = True
        return p

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

    def zona(self, momentos, dur_f, corte, rng, dron_primero, con_fotos=False):
        """Planos de video (las mejores tomas libres) para llenar dur_f frames, en orden cronologico. Si las tomas
        buenas no alcanzan se rellena con dron y, con con_fotos, con fotos del momento (self.relleno dice cuantos)."""
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
        cand = [(v, ls) for v, ls in cand if ls]
        pesos, topes = [], []
        for v, ls in cand:
            largo = sum(b - a for a, b in ls)
            pesos.append(largo * (0.2 + self.puntaje(v, 0, v["dur"])))
            topes.append(int(largo // (lo + SEPARACION)))
        # variedad: los videos del mismo encuadre (la camara en el tripode, varios archivos seguidos) cuentan como uno
        # y todo el dron junto tiene su propio tope (es bonito, pero no es el evento)
        grupo = list(range(len(cand)))
        for i in range(len(cand)):
            if cand[i][0]["tipo"] == "dron":
                grupo[i] = "dron"
                continue
            for j in range(i):
                if grupo[j] != "dron" and self.mismo_encuadre(cand[i][0], cand[j][0]):
                    grupo[i] = grupo[j]
                    break
        varios = len(set(grupo)) >= 3
        tope_de = {g: (max(1, int(math.ceil(len(cortes) * TOPE_DRON))) if g == "dron" and varios else
                       max(2, int(math.ceil(len(cortes) * TOPE_MISMO_ENCUADRE))) if varios else len(cortes))
                   for g in set(grupo)}
        cuenta = [0] * len(cand)
        en_grupo = {}
        total = sum(pesos)
        if total > 0:
            ideal = [len(cortes) * p / total for p in pesos]
            orden = sorted(range(len(cand)), key=lambda i: -ideal[i])
            for i in orden:                         # primero la parte entera, sin pasar el tope de su encuadre
                n = min(int(ideal[i]), topes[i], tope_de[grupo[i]] - en_grupo.get(grupo[i], 0))
                if n > 0:
                    cuenta[i] = n
                    en_grupo[grupo[i]] = en_grupo.get(grupo[i], 0) + n
            orden = sorted(range(len(cand)), key=lambda i: ideal[i] - int(ideal[i]), reverse=True)
            falta = len(cortes) - sum(cuenta)
            while falta > 0:
                hubo = False
                for i in orden:
                    if falta > 0 and cuenta[i] < topes[i] and en_grupo.get(grupo[i], 0) < tope_de[grupo[i]]:
                        cuenta[i] += 1
                        en_grupo[grupo[i]] = en_grupo.get(grupo[i], 0) + 1
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
        self.relleno = {"dron": 0, "fotos": 0}
        if pendientes:                          # no alcanzan las tomas buenas: dron, fotos y, al final, repetir
            hay = sum(1 for p in piezas if p["tipo"] == "dron")
            pendientes = self._rellenar_dron(pendientes, piezas, max(0, int(len(cortes) * TOPE_DRON) - hay))
        if pendientes and con_fotos:            # primero las fotos de ese momento; si se acaban, las de los demas
            pendientes = self._rellenar_fotos(pendientes, piezas, filtro or momentos)
            if pendientes:
                pendientes = self._rellenar_fotos(pendientes, piezas, None)
        reusos = 0
        for d in pendientes:                    # ya no queda nada sin usar: se repite la mejor toma posible
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
        self.separar(piezas)
        return piezas, reusos

    def _rellenar_dron(self, largos, piezas, cupo):
        """Planos de dron que aun no se usaron (de cualquier momento) para lo que falta, hasta `cupo`. Devuelve los
        largos que siguen sin llenar."""
        faltan = []
        for lf in sorted(largos, reverse=True):
            l = lf / float(self.fps)
            puesto = None
            if cupo > 0:
                for v in sorted((d for d in self.vids if d["tipo"] == "dron"), key=lambda d: -self.puntaje(d, 0, d["dur"])):
                    ls = [x for x in self.libres(v) if x[1] - x[0] >= l]
                    if ls:
                        puesto, _ = self._colocar(v, ls, [lf])
                        if puesto:
                            break
            if puesto:
                piezas += puesto
                cupo -= 1
                self.relleno["dron"] += 1
            else:
                faltan.append(lf)
        return faltan

    def _rellenar_fotos(self, largos, piezas, momentos):
        """Fotos del mismo momento (nitidas, sin quemar, sin repetir) para lo que falta: cada hueco se llena con
        fotos de 3 a 4,5 s. Devuelve los largos que siguen sin llenar."""
        fps = self.fps
        lo, hi = (int(round(x * fps)) for x in FOTO_RELLENO_S)
        tramos = []
        for lf in largos:                       # un hueco largo son varias fotos
            k = max(1, int(math.ceil(lf / float(hi))))
            base = lf // k
            tramos.append([base + (1 if i < lf - base * k else 0) for i in range(k)])
        cand = [f for f in self.fotos if f["ruta"] not in self.fotos_usadas
                and (not momentos or f.get("momento") in momentos)
                and f.get("quemado", 0.0) < 0.12 and f.get("brillo", 0.5) >= BRILLO_MIN_INTRO]
        nit = sorted(f["nitidez"] for f in cand if f.get("nitidez") is not None)
        pedidas = sum(len(t) for t in tramos)
        if len(nit) > 2 * pedidas:               # sobran: fuera el 30 % menos nitido
            corte = nit[int(len(nit) * 0.3)]
            cand = [f for f in cand if f.get("nitidez") is None or f["nitidez"] >= corte]
        sel = espaciadas(cand, pedidas)
        faltan = []
        for t in tramos:
            if len(sel) < len(t) or min(t) < lo // 2:
                faltan.append(sum(t))
                continue
            for d in t:
                f = sel.pop(0)
                self.fotos_usadas.add(f["ruta"])
                piezas.append({"tipo": "foto", "item": f, "dur_f": d, "orden": _hora(f), "momento": f.get("momento"),
                               "relleno": True, "hash": int(f["dhash"], 16) if f.get("dhash") else None})
                self.relleno["fotos"] += 1
        return faltan

    @staticmethod
    def _parecidas(a, b):
        """Dos planos que se ven casi iguales (mismo video o mismo encuadre): juntos se ven como un salto."""
        if a["item"] is b["item"]:
            return True
        ha, hb = a.get("hash"), b.get("hash")
        return ha is not None and hb is not None and bin(ha ^ hb).count("1") <= PARECIDAS

    @classmethod
    def separar(cls, piezas, alcance=4):
        """Variedad: que no vayan dos planos seguidos del MISMO video ni del mismo encuadre (se ve como un salto). Se
        adelanta un plano cercano distinto (hasta `alcance` puestos), asi el orden sigue siendo casi cronologico.
        Devuelve cuantos pares quedaron pegados (cuando el momento tiene un solo video no hay con que separar)."""
        n = len(piezas)
        for i in range(1, n):
            if not cls._parecidas(piezas[i], piezas[i - 1]):
                continue
            for j in range(i + 1, min(n, i + 1 + alcance)):
                if not cls._parecidas(piezas[j], piezas[i - 1]):
                    piezas.insert(i, piezas.pop(j))
                    break
        return sum(1 for a, b in zip(piezas, piezas[1:]) if cls._parecidas(a, b))

    def _colocar(self, v, intervalos, largos):
        """Elige las mejores ventanas del video (calidad alta, repartidas) para cada largo pedido."""
        fps = self.fps
        libres = list(intervalos)
        res, falta, elegidos, vistas = [], [], [], []
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
                        h = self.huella(v, x + l / 2.0)          # otro plano del mismo video: que se vea distinto
                        if h is not None and any(bin(h ^ o).count("1") <= PARECIDAS for o in vistas):
                            sc -= 0.2
                    if mejor is None or sc > mejor[0]:
                        mejor = (sc, x)
                    x += 0.25
            if mejor is None or self.puntaje(v, mejor[1], l) < UMBRAL_PLANO:      # nada o solo tramos flojos
                falta.append(lf)
                continue
            s = mejor[1]
            res.append(self._pieza(v, s, lf))
            elegidos.append(s)
            if res[-1].get("hash") is not None:
                vistas.append(res[-1]["hash"])
            libres = [x for x in restar(libres, [(s - SEPARACION, s + l + SEPARACION)]) if x[1] - x[0] >= l * 0.5]
        return res, falta

    def _reusar(self, vids, lf, rng, momentos=None):
        l = lf / float(self.fps)
        sin_dron = [v for v in vids if v["tipo"] != "dron"]       # el dron ya tiene su tope: no se repite de relleno
        cand = [(v, u) for v in sin_dron for u in self.utiles(v, momentos) if u[1] - u[0] >= l] or \
               [(v, u) for v in vids for u in self.utiles(v, momentos) if u[1] - u[0] >= l] or \
               [(v, u) for v in self.vids for u in self.utiles(v) if u[1] - u[0] >= l] or \
               [(v, u) for v in self.vids for u in self.utiles(v, None, False) if u[1] - u[0] >= l]
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
        medio = ini + dur_f / (2.0 * self.fps)
        return {"tipo": v["tipo"], "item": v, "ini": ini, "dur_f": dur_f, "orden": _hora(v, ini),
                "momento": self.momento_en(v, medio), "hash": self.huella(v, medio)}


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


def objetivo_de_saturacion(items):
    """Saturacion tipica de los videos del evento: cada toma se acerca a ESA, no a un numero fijo, para emparejar sin
    cambiarle el color a todo el evento."""
    sats = [_mediana([s[2] for s in i["color"]]) for i in items if i["tipo"] != "foto" and i.get("color")]
    sats = [x for x in sats if x > 0.02]
    return _lim(_mediana(sats), *SAT_OBJETIVO_LIMITES) if sats else SAT_OBJETIVO


def cdl_para(pieza, objetivo, sat_objetivo=None):
    """CDL (slope / offset / saturacion) que empareja este plano con poco margen (son tomas Rec.709): exposicion hacia
    la luz tipica de su momento, negros limpios, balance de blancos con los grises y saturacion hacia la del evento."""
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
    quem = _mediana(((v.get("vista") or {}).get("quem") or [])[i0:i1] or [0.0])     # luces reventadas de camara
    fuerza = FUERZA_EXPOSICION + (FUERZA_QUEMADA - FUERZA_EXPOSICION) * _lim(quem / 0.10, 0.0, 1.0)
    meta = luz + fuerza * (objetivo - luz)
    potencia = 1.0
    if meta < luz and 0.05 < luz < 0.98:
        # sobreexpuesta: baja los medios con gamma y deja el blanco donde esta (bajar la pendiente volvia grises las
        # luces quemadas y la toma seguia viendose reventada)
        potencia = _lim(math.log(max(meta, 0.02)) / math.log(luz), 1.0, POTENCIA_MAX)
        s = 1.0
        o = _lim(0.03 - negro, *DESPLAZO_LIMITES) if negro > NEGRO_LECHOSO else 0.0
    else:
        if negro > NEGRO_LECHOSO:                      # negros lechosos: mapea negro->0.03 y luz->meta
            s = (meta - 0.03) / max(0.05, luz - negro)
        else:
            s = meta / max(0.02, luz)
        # si ya trae luces al tope no se aclara: se quemaria mas
        tope = 1.0 + (PENDIENTE_LIMITES[1] - 1.0) * max(0.0, 1.0 - quem / 0.03)
        s = _lim(s, PENDIENTE_LIMITES[0], tope)
        o = _lim(meta - luz * s, *DESPLAZO_LIMITES) if negro > NEGRO_LECHOSO else 0.0
    gan = [1.0, 1.0, 1.0]
    if len(grises) >= max(1, len(m) // 3):            # hay suficientes grises: corrige la dominante
        rgb = [sum(x[k] for x in grises) / len(grises) for k in (3, 4, 5)]
        prom = sum(rgb) / 3.0
        gan = [_lim(1 + FUERZA_BLANCOS * (prom / c - 1), *BLANCOS_LIMITES) for c in rgb]
        l = 0.2126 * gan[0] + 0.7152 * gan[1] + 0.0722 * gan[2]
        gan = [g / l for g in gan]
    # saturacion medida: la toma mas viva que lo tipico del evento (luces LED, flores) baja hacia eso (raiz =
    # correccion suave). NUNCA se sube: el color de camara ya viene terminado y la persona lo ve chillon.
    saturacion = _lim(((sat_objetivo or SAT_OBJETIVO) / sat) ** 0.5, *SAT_LIMITES) if sat > 0.02 else 1.0
    pend = [s * g for g in gan]
    return {"NodeIndex": "1", "Slope": "%.4f %.4f %.4f" % tuple(pend), "Offset": "%.4f %.4f %.4f" % (o, o, o),
            "Power": "%.4f %.4f %.4f" % (potencia, potencia, potencia), "Saturation": "%.3f" % saturacion}


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
                if p.get("relleno"):            # foto dentro del video: zoom lento para que no quede quieta
                    try:
                        r[0].SetProperty("DynamicZoomEnabled", True)
                        r[0].SetProperty("DynamicZoomEase", resolve.DYNAMIC_ZOOM_EASE_IN_AND_OUT)
                    except Exception:
                        pass
                puestos.append((p, r[0]))
        else:
            vf = p["item"]["fps"]
            vel = p.get("vel", 1.0)
            if p.get("sincro"):                  # se le ve hablar con su voz: a velocidad real
                vel = 1.0
                p.pop("vel", None)
            elif CONFORMAR_30_A_24 and vel >= 1.0 and fps == 24 and 28.0 <= float(vf or 0) <= 31.0:
                vel = p["vel"] = fps / float(vf)     # 30 c/s en 24: al 80 % se ven todos los cuadros, sin saltos
                p["conformado"] = True
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
    if ok and (p["item"].get("fps") or 30) < 48 and not p.get("conformado"):
        try:
            x.SetProperty("RetimeProcess", resolve.RETIME_OPTICAL_FLOW)
            x.SetProperty("MotionEstimation", resolve.MOTION_EST_SPEED_WARP_BETTER)
        except Exception:
            pass
    return ok


def marcar_acercados(zonas):
    """Pone p['zoom'] = ACERCAR en uno de cada dos planos que salen del MISMO video dentro de una zona (el 2.o, el
    4.o...). Los de dron, las fotos y los que van sincronizados con una voz no se tocan. Devuelve cuantos."""
    n = 0
    for nombre, _, _, piezas in zonas:
        veces = {}
        for p in piezas:
            it = p["item"]
            if p["tipo"] != "video" or p.get("sincro") or (it.get("ancho") or 0) < ACERCAR_ANCHO_MIN:
                continue
            k = veces.get(it["ruta"], 0)
            veces[it["ruta"]] = k + 1
            if k % 2 == 1:
                p["zoom"] = ACERCAR
                n += 1
    return n


def acercar(puestos):
    """Aplica el acercamiento marcado (despues de estabilizar, que puede tocar el encuadre)."""
    n = 0
    for p, x in puestos:
        z = p.get("zoom")
        if not z:
            continue
        try:
            n += bool(x.SetProperty("ZoomX", z) and x.SetProperty("ZoomY", z))
        except Exception:
            pass
    return n


def reencuadrar(project, puestos, limite_s=180.0):
    """Videos verticales en la linea horizontal: ya llenan la pantalla recortados (SCALE_FILL); el reencuadre
    inteligente de Resolve Studio (Smart Reframe) sigue a la persona para que el recorte no le corte la cabeza.
    Devuelve cuantos se reencuadraron."""
    t0, n = time.time(), 0
    for p, x in puestos:
        if p["tipo"] == "foto" or p["item"].get("horizontal", True) or time.time() - t0 > limite_s:
            continue
        try:
            if x.SmartReframe():
                fin = time.time() + 30.0
                while time.time() < fin:                 # trabaja en segundo plano: se espera a que termine
                    est = project.GetSmartReframeStatus() or {}
                    if str(est.get("JobStatus", "")).lower() not in ("running", "queued", "inprogress", "in progress"):
                        break
                    time.sleep(0.3)
                n += 1
        except Exception:
            pass
    return n


VELO_PLANTILLA = 0.30             # oscuridad del velo bajo los titulos propios de la plantilla (0 = sin velo)


def velos_plantilla(tl, mp, png, fps, intro_f=0):
    """Los titulos propios de la plantilla (la firma, el titulo grande, la frase de la intro) son de trazo fino y
    blancos: sobre un vestido claro o un cielo no se leen. No se pueden redisenar (son macros de titulos), asi que
    en la linea del evento se baja un poco la luz de la imagen MIENTRAS estan en pantalla: un velo oscuro en la
    pista TEXTOS, que queda por debajo de ellos y por encima del video. La plantilla no se toca.
    Devuelve cuantos velos puso."""
    if png is None or VELO_PLANTILLA <= 0:
        return 0
    st = tl.GetStartFrame()
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    ocupado = [(x.GetStart() - st, x.GetEnd() - st) for x in tl.GetItemListInTrack("video", pt) or []]
    tramos = []
    for t in range(pt + 1, tl.GetTrackCount("video") + 1):
        nombre_pista = (tl.GetTrackName("video", t) or "").upper()
        if "TITULO" not in nombre_pista and "TEXTO" not in nombre_pista:
            continue                                         # barras de cine, brillos, ajustes: no son textos
        for x in tl.GetItemListInTrack("video", t) or []:
            a, b = x.GetStart() - st, x.GetEnd() - st
            if x.GetMediaPoolItem() is not None or not x.GetClipEnabled() or a < intro_f or b - a < fps:
                continue
            tramos.append((a, b))
    tramos.sort()
    juntos = []
    for a, b in tramos:                                      # titulos seguidos: un solo velo
        if juntos and a - juntos[-1][1] <= fps:
            juntos[-1] = (juntos[-1][0], max(b, juntos[-1][1]))
        else:
            juntos.append((a, b))
    n = 0
    for a, b in juntos:
        a, b = max(0, a - int(0.25 * fps)), b + int(0.25 * fps)
        if any(x0 < b and a < x1 for x0, x1 in ocupado):
            continue
        r = mp.AppendToTimeline([{"mediaPoolItem": png, "startFrame": 0, "endFrame": b - a - 1, "trackIndex": pt,
                                  "recordFrame": st + a, "mediaType": 1}])
        it = r[0] if r else None
        if it is None:
            continue
        if it.GetDuration() != b - a:
            it.SetRightOffset(it.GetRightOffset() + it.GetDuration() - (b - a))
        try:
            it.SetName("VELO PLANTILLA")
        except Exception:
            pass
        comp = it.GetFusionCompByIndex(1) or it.AddFusionComp()
        if comp is None:
            continue
        comp.Lock()
        try:
            velo = comp.FindTool("Velo") or comp.AddTool("Background", -32768, -32768)
            velo.SetAttrs({"TOOLS_Name": "Velo"})
            velo.SetInput("UseFrameFormatSettings", 1)
            for k, v in (("TopLeftRed", 0.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0),
                         ("TopLeftAlpha", VELO_PLANTILLA)):
                velo.SetInput(k, v)
            comp.FindTool("MediaOut1").ConnectInput("Input", velo)
        finally:
            comp.Unlock()
        try:
            it.SetFades({"FadeIn": int(0.4 * fps), "FadeOut": int(0.4 * fps)})
        except Exception:
            pass
        ocupado.append((a, b))
        n += 1
    return n


def legibilidad_plantilla(tl):
    """Los textos PROPIOS de la plantilla (la firma, el titulo grande, la frase de la intro) son de trazo fino y se
    pierden sobre un vestido claro o un cielo. En la linea del evento (la plantilla no se toca) se les enciende un
    halo oscuro suave con los elementos de sombreado del propio Text+. Devuelve cuantos textos se tocaron."""
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
            for herr in (comp.GetToolList(False, "TextPlus") or {}).values():
                try:
                    if not isinstance(herr.GetInput("StyledText"), str) or not herr.GetInput("StyledText").strip():
                        continue
                    herr.SetInput("Enabled3", 1)             # elemento 3: halo oscuro centrado
                    herr.SetInput("ElementShape3", 0)
                    for k in ("Red3", "Green3", "Blue3"):
                        herr.SetInput(k, 0.0)
                    herr.SetInput("Opacity3", 0.7)
                    herr.SetInput("SoftnessX3", 7.0)
                    herr.SetInput("SoftnessY3", 7.0)
                    herr.SetInput("Offset3", {1: 0.0, 2: 0.0, 3: 0.0})
                    n += 1
                except Exception:
                    pass
    return n


def sfx_propios(mp, root):
    """Los efectos de sonido propios del programa (recursos/sfx/XV_*.wav) en el media pool (06 EFECTOS\\SFX PROPIOS):
    {"XV_GOLPE": MediaPoolItem, ...}. Los importa la primera vez."""
    carpeta = os.path.join(rutas.RECURSOS, "sfx")
    try:
        archivos = sorted(f for f in os.listdir(carpeta) if f.lower().endswith(".wav"))
    except OSError:
        return {}
    res, faltan = {}, []
    for f in archivos:
        clave = os.path.splitext(f)[0]
        c = buscar_clip(root, clave)
        if c is not None:
            res[clave] = c
        else:
            faltan.append(os.path.join(carpeta, f))
    if faltan:
        efe = carpeta_raiz(mp, root, "EFECTOS")
        dest = next((x for x in efe.GetSubFolderList() or [] if x.GetName() == "SFX PROPIOS"), None) or \
            mp.AddSubFolder(efe, "SFX PROPIOS")
        mp.SetCurrentFolder(dest)
        for c in mp.ImportMedia(faltan) or []:
            res[os.path.splitext(c.GetName() or "")[0]] = c
    return res


def estabilizar(puestos, limite_s=None):
    """Estabilizador de Resolve Studio en los planos que tiemblan (medido por el analizador). Primero los que mas
    tiemblan y los que van en camara lenta (ahi el temblor se ve el doble); el tope de tiempo crece con el numero
    de planos, para que en los videos largos no se quede ninguno sin pasar."""
    def cuanto(p):
        v = p["item"]
        t = v.get("temblor") or []
        i0 = int(p.get("ini", 0) / PASO_CALIDAD)
        tramo = t[i0:i0 + max(1, int(p["dur_f"] / 24.0 / PASO_CALIDAD))] or [0.0]
        return (2.0 if p.get("vel", 1.0) < 0.75 else 1.0) * sum(tramo) / len(tramo)
    orden = sorted(((p, x) for p, x in puestos if p.get("estabilizar")), key=lambda t: -cuanto(t[0]))
    limite_s = limite_s or max(120.0, 1.5 * len(orden))
    t0, n = time.time(), 0
    for p, x in orden:
        if time.time() - t0 > limite_s:
            break
        try:
            n += bool(x.Stabilize())
        except Exception:
            pass
    return n


TIPOS_VOZ = ("VOTOS", "DECLARACION")    # frases sueltas que tambien valen como voz (el "si, acepto" de una boda)
VOZ_PARTE_ZONA = 0.35         # como mucho esta parte de una zona lleva voz encima
VOZ_AISLAR = 70               # aislamiento de voz de Resolve Studio (0-100): quita musica y murmullo de fondo
VOZ_FUNDIDOS = (6, 12)        # cuadros de entrada y salida de cada voz
VOZ_GANANCIA = 4.0            # dB de salida del nivelador de dialogo (0-6)
MUSICA_BAJO_VOZ = -11.0       # dB que baja la musica debajo de la voz
RAMPA_VOZ = 14                # cuadros que tarda la musica en bajar y en volver a subir (sin escalon)
PISTA_MUSICA_BAJA = "MUSICA BAJA (voz)"
CRUCE_CANCIONES_S = 2.5       # s que se alarga la cancion que sale para cruzarse con la que entra
CRUCE_ENTRA_S = 2.5           # s de entrada de la cancion nueva
CRUCE_SALE_S = 4.0            # s de salida de la cancion que termina (mas largo: asi no hay "hueco" de volumen)
CRUCE_RETRASO_MAX = 60.0      # s que como mucho se retrasa una cancion que se acaba antes de que entre la siguiente.
#                               Es acumulado hacia atras: cada una termina donde entra la otra, y la primera (a la que
#                               le sobra musica) se alarga. La entrada de la cancion de la fiesta no se mueve.


def voz_activa(sufijo):
    """Si esta version lleva la voz original: siempre en el video largo; en las demas, lo que diga Ajustes (VOZ) o
    lo que viene por defecto (activada en el de 15 minutos)."""
    if sufijo in VOZ_SIEMPRE:
        return True
    elegido = globals().get("VOZ")
    if isinstance(elegido, dict) and sufijo in elegido:
        return bool(elegido[sufijo])
    return VOZ_DEFECTO.get(sufijo, False)


def _trozos(pasaje, lo, hi):
    """Parte un pasaje de habla en trozos de lo..hi segundos cortados en limites de oracion: [(ini, fin, palabras)].
    Una oracion mas larga que hi se corta a hi (con el fundido de salida no se nota)."""
    ors = pasaje.get("oraciones") or [[pasaje["ini"], pasaje["fin"], pasaje.get("palabras", 0)]]
    res, i = [], 0
    while i < len(ors):
        a, pal, j = ors[i][0], 0, i
        while j < len(ors) and ors[j][1] - a <= hi:
            pal += ors[j][2]
            j += 1
        if j == i:                               # una sola oracion ya pasa de hi
            res.append((a, a + hi, int(ors[i][2] * hi / max(0.1, ors[i][1] - a))))
            i += 1
            continue
        b = ors[j - 1][1]
        if b - a >= lo:
            res.append((a, b, pal))
        i = j
    if not res and pasaje["fin"] - pasaje["ini"] >= lo:
        res.append((pasaje["ini"], min(pasaje["fin"], pasaje["ini"] + hi), pasaje.get("palabras", 0)))
    return res


def elegir_voces(items, sufijo, zonas, fps, excluir=()):
    """La voz original que va sobre la musica: SOLO lo importante. Pasajes donde alguien habla de corrido (la palabra
    del pastor, un brindis, un discurso) en la ceremonia o en la fiesta, mas los votos de una boda. Nada de ruidos ni
    voces sueltas del publico. Devuelve [{item, ini, fin, zona, tipo, texto}] en orden."""
    n = VOCES.get(sufijo, 1)
    if n <= 0 or not voz_activa(sufijo):
        return []
    lo, hi = VOZ_LARGO.get(sufijo, (4.0, 9.0))
    de_zona = {z[0]: z for z in zonas}
    cand = []
    for it in items:
        if it["tipo"] != "video" or it.get("descartar") or it["nombre"] in excluir:
            continue
        for pa in it.get("pasajes") or []:
            mom = Planificador.momento_en(it, (pa["ini"] + pa["fin"]) / 2.0)
            if mom not in ("IGLESIA", "FIESTA") or mom not in de_zona:
                continue
            if mom == "FIESTA" and pa["tipo"] == "DISCURSO" and pa.get("claves", 0) < 2:
                continue                         # en la fiesta suena musica con letra: eso no es un discurso
            trozos = sorted(_trozos(pa, lo, hi), key=lambda t: -(t[2] / max(0.1, t[1] - t[0])))
            for k, (a, b, pal) in enumerate(trozos):
                ritmo = min(1.0, pal / max(0.1, b - a) / 2.5)          # habla clara y seguida
                cand.append((pa["puntaje"] * (0.6 + 0.4 * ritmo) * (0.85 ** k), it, pa, a, b, mom))
        if TIPO_EVENTO == "boda" and not it.get("pasajes") and it.get("momento") == "IGLESIA" and "IGLESIA" in de_zona:
            for fr in it.get("frases") or []:    # boda sin pasajes: los votos y "los declaro" (frases cortas)
                if fr["tipo"] in TIPOS_VOZ and 1.2 <= fr["fin"] - fr["ini"] <= 9.0:
                    cand.append((fr["puntaje"] * 0.9, it, fr, fr["ini"], fr["fin"], "IGLESIA"))
    cand.sort(key=lambda t: -t[0])
    elegidas, tiempo = [], {}
    for _, it, pa, a, b, mom in cand:
        if len(elegidas) >= n:
            break
        z = de_zona[mom]
        if tiempo.get(mom, 0.0) + (b - a) > VOZ_PARTE_ZONA * (z[2] - z[1]) / float(fps):
            continue
        if any(e["item"] is it and a < e["fin"] + 6.0 and b > e["ini"] - 6.0 for e in elegidas):
            continue                             # no dos trozos pegados del mismo momento
        elegidas.append({"item": it, "ini": a, "fin": b, "zona": mom, "tipo": pa["tipo"], "texto": pa["texto"]})
        tiempo[mom] = tiempo.get(mom, 0.0) + (b - a)
    elegidas.sort(key=lambda e: (ZONAS.index(e["zona"]), _hora(e["item"], e["ini"])))
    return elegidas


def ubicar_voces(voces, zonas, plan, fps):
    """A cada voz su lugar en la linea: repartidas a lo largo de su zona, en orden, entrando en un corte. Si se puede,
    el plano que empieza ahi pasa a ser el de quien habla, sincronizado con su voz (se le ve decirlo); despues la voz
    sigue sobre los demas planos. Pone v['pos'] (cuadros desde el inicio de la linea) y devuelve las que caben."""
    puestas = []
    for nombre, z0, z1, piezas in zonas:
        vs = [v for v in voces if v["zona"] == nombre]
        if not vs:
            continue
        inicios, pos = [], z0
        for p in piezas:
            inicios.append(pos)
            pos += p["dur_f"]
        libre = z0 + int(2.0 * fps)
        for k, v in enumerate(vs):
            largo = int(round((v["fin"] - v["ini"]) * fps))
            quiero = max(libre, z0 + int((k + 0.5) / len(vs) * (z1 - z0)) - largo // 2)
            cand = [(abs(x - quiero), j) for j, x in enumerate(inicios)
                    if libre <= x and x + largo <= z1 - int(2.0 * fps)]
            if not cand:
                continue
            j = min(cand)[1]
            v["pos"] = inicios[j]
            libre = v["pos"] + largo + int(3.0 * fps)
            puestas.append(v)
            p, c = piezas[j], v["item"]
            d = p["dur_f"] / float(fps)
            a = v["ini"]
            malos = plan.vista(c)[0] if plan is not None else []
            if a + d <= c["dur"] - 0.15 and not any(x < a + d and y > a for x, y in malos):
                p.update({"tipo": c["tipo"], "item": c, "ini": a, "sincro": True,
                          "momento": Planificador.momento_en(c, a + d / 2.0),
                          "hash": plan.huella(c, a + d / 2.0) if plan is not None else None})
                p.pop("vel", None)
                p.pop("relleno", None)
                v["sincro"] = True
    return puestas


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


def pulir_voz(x):
    """Voz limpia y pareja con la IA de Resolve Studio, clip por clip: aislamiento de voz (quita musica y murmullo)
    y nivelador de dialogo (sube lo bajo, baja lo fuerte). Devuelve True si se pudo aislar."""
    ok = False
    try:
        ok = bool(x.SetProperty("AudioVoiceIsolationEnabled", True)) and \
            bool(x.SetProperty("AudioVoiceIsolationAmount", VOZ_AISLAR))
    except Exception:
        pass
    try:
        if x.SetProperty("AudioDialogueLevelerEnabled", True):
            x.SetProperty("AudioDialogueLevelerMode", resolve.DIALOGUE_LEVELER_MODE_OPTIMIZE_MODERATE_LEVELS)
            x.SetProperty("AudioDialogueLevelerReduceLoudDialogue", True)
            x.SetProperty("AudioDialogueLevelerLiftSoftDialogue", True)
            x.SetProperty("AudioDialogueLevelerBackgroundReduction", True)
            x.SetProperty("AudioDialogueLevelerOutputGain", VOZ_GANANCIA)
    except Exception:
        pass
    return ok


def poner_voces(tl, mp, pool, voces, fps):
    """Pone cada voz ya ubicada (v['pos']) en la pista VOZ (solo el audio), con fundidos y pulida (aislamiento de voz
    y nivelador de dialogo). Devuelve [(inicio, fin, voz)] en frames de timeline (para bajar la musica debajo)."""
    voces = [v for v in voces if v.get("pos") is not None]
    if not voces:
        return []
    t = pista_voz(tl)
    if t is None:
        aviso("No se pudo crear la pista VOZ.")
        return []
    tl.SetTrackLock("audio", t, False)
    st = tl.GetStartFrame()
    tramos, aisladas = [], 0
    for v in voces:
        it = v["item"]
        c = pool.get(os.path.normcase(it["ruta"]))
        if c is None:
            continue
        vf = float(it.get("fps") or 30)
        s = int(round(v["ini"] * vf))
        e = s + int(round((v["fin"] - v["ini"]) * vf))
        r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": s, "endFrame": e, "mediaType": 2,
                                  "trackIndex": t, "recordFrame": st + v["pos"]}]) or []
        if not r:
            continue
        x = r[0]
        try:
            x.SetFades({"FadeIn": VOZ_FUNDIDOS[0], "FadeOut": VOZ_FUNDIDOS[1]})
        except Exception:
            pass
        aisladas += bool(pulir_voz(x))
        tramos.append((x.GetStart(), x.GetEnd(), v))
    if tramos and aisladas < len(tramos):        # sin aislamiento por clip: el de la pista entera
        try:
            tl.SetVoiceIsolationState(t, {"isEnabled": True, "amount": VOZ_AISLAR})
        except Exception:
            pass
    return tramos


def _pistas_musica(tl):
    return [t for t in range(1, tl.GetTrackCount("audio") + 1)
            if "MUSICA" in (tl.GetTrackName("audio", t) or "").upper()
            and "BAJA" not in (tl.GetTrackName("audio", t) or "").upper()]


def _niveles_db(ruta, ini_s, dur_s, paso=0.25):
    """Volumen (dB RMS) de cada `paso` segundos de un tramo de un archivo de audio. [] si no se puede leer."""
    import array
    import subprocess
    if dur_s <= 0 or not ruta or not os.path.exists(ruta):
        return []
    try:
        crudo = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-ss", "%.3f" % max(0.0, ini_s),
                                "-t", "%.3f" % dur_s, "-i", ruta, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
                               capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA).stdout
    except Exception:
        return []
    m = array.array("h")
    m.frombytes(crudo[:len(crudo) // 2 * 2])
    n = int(8000 * paso)
    res = []
    for i in range(0, len(m) - n + 1, n):
        s = 0
        for x in m[i:i + n]:
            s += x * x
        res.append(10.0 * math.log10(s / float(n) / 1073741824.0 + 1e-12))
    return res


def _final_de_cancion(x, fps, ventana=24.0, paso=0.25):
    """Segundos ANTES del final del clip en que la cancion deja de sonar de verdad (se acaba sola, se va apagando o
    el archivo trae silencio). 0 = suena hasta el corte. Mira los ultimos `ventana` segundos."""
    mpi = x.GetMediaPoolItem()
    ruta = mpi.GetClipProperty("File Path") if mpi else ""
    dur = x.GetDuration() / float(fps)
    v = min(ventana, dur)
    niv = _niveles_db(ruta, x.GetLeftOffset() / float(fps) + dur - v, v, paso)
    if len(niv) < 8:
        return 0.0
    ref = _mediana(niv[:len(niv) // 2])                  # lo normal de la cancion, antes del final
    ultimo = -1
    for i, d in enumerate(niv):
        if d >= ref - 10.0:
            ultimo = i
    return max(0.0, (len(niv) - 1 - ultimo) * paso)


def _entrada_de_cancion(x, fps, ventana=12.0, paso=0.25):
    """Segundos desde el inicio del clip hasta que la cancion se empieza a oir (silencio o entrada muy baja)."""
    mpi = x.GetMediaPoolItem()
    ruta = mpi.GetClipProperty("File Path") if mpi else ""
    v = min(ventana, x.GetDuration() / float(fps))
    niv = _niveles_db(ruta, x.GetLeftOffset() / float(fps), v, paso)
    if len(niv) < 8:
        return 0.0
    ref = _mediana(niv[len(niv) // 3:])
    for i, d in enumerate(niv):
        if d >= ref - 18.0:
            return i * paso
    return 0.0


def _mover_cancion(tl, mp, x, pista_n, d, fps):
    """Mueve una cancion `d` cuadros (positivo = mas tarde) sin cambiarle el punto donde empieza ni el largo. Resolve
    no mueve clips por script: se quita y se vuelve a poner. Devuelve el clip nuevo, o None si no se pudo mover."""
    mpi = x.GetMediaPoolItem()
    if mpi is None or not d:
        return None
    r0, r1 = x.GetStart(), x.GetEnd()
    try:
        s0 = x.GetSourceStartFrame()
        fades = x.GetFades() or {}
        vol = x.GetProperty("AudioVolume")
    except Exception:
        return None
    k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
    fin = s0 + int(round((r1 - r0) * k))                 # en audio el cuadro final no se incluye (probado)
    if not tl.DeleteClips([x], False):
        return None
    movido = True
    nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0, "endFrame": fin, "mediaType": 2,
                                  "trackIndex": pista_n, "recordFrame": r0 + d}]) or []
    if not nuevo:                                        # no se pudo: se deja donde estaba
        movido = False
        nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0, "endFrame": fin, "mediaType": 2,
                                      "trackIndex": pista_n, "recordFrame": r0}]) or []
    if not nuevo:
        return None
    y = nuevo[0]
    try:
        if vol is not None:
            y.SetProperty("AudioVolume", float(vol))
        y.SetFades({"FadeIn": int(fades.get("FadeIn", 0)), "FadeOut": int(fades.get("FadeOut", 0))})
    except Exception:
        pass
    return y if movido else None


def cruces_de_musica(tl, mp, fps):
    """Cambio de cancion que no se note. Midiendo el sonido de cada cancion, de la ULTIMA hacia la primera (la entrada
    de la cancion de la fiesta es la que mas importa que caiga en su sitio):
    - La que SALE se acaba antes de que entre la siguiente (termina, se va apagando, el archivo trae silencio o es mas
      corta que su sitio en la plantilla): quedaban huecos casi en silencio de varios segundos. Si le queda cancion,
      se alarga; si no, se RETRASA entera para que termine justo donde entra la otra. El retraso se acumula hacia
      atras hasta una cancion a la que si le sobra musica (la primera), que se alarga.
    - La que sale sigue sonando hasta el corte: en la plantilla se cruzan 2 s con dos fundidos iguales y en el medio
      el volumen hace un hueco. La que sale se alarga y se apaga despacio mientras la otra ya subio.
    Devuelve cuantos cambios arreglo."""
    clips = []
    for t in _pistas_musica(tl):
        if "INTRO" in (tl.GetTrackName("audio", t) or "").upper():
            continue
        tl.SetTrackLock("audio", t, False)
        for x in tl.GetItemListInTrack("audio", t) or []:
            if x.GetDuration() and x.GetDuration() > 8 * fps:
                clips.append([x, t])
    clips.sort(key=lambda c: c[0].GetStart())
    n = 0
    for i in range(len(clips) - 2, -1, -1):
        (a, ta), b = clips[i], clips[i + 1][0]
        cruce = a.GetEnd() - b.GetStart()
        if not -(CRUCE_RETRASO_MAX + 20) * fps <= cruce <= 6 * fps:      # ni se tocan ni estan cerca
            continue
        try:
            cola = _final_de_cancion(a, fps)                         # s finales en que la que sale ya no suena
            # cuadros que le faltan a la que sale para sonar hasta 1,5 s despues de entrar la otra
            entra = _entrada_de_cancion(b, fps) if cola > 0.75 or cruce < 0 else 0.0     # la otra puede entrar muy bajito
            hasta = b.GetStart() + int((1.5 + min(entra, 4.0)) * fps)
            falta = hasta - (a.GetEnd() - int(round(cola * fps)))
            if falta > int(0.5 * fps):
                if cola <= 0.75:                                     # le queda cancion: se alarga
                    extra = int(min(falta + int(CRUCE_SALE_S * fps * 0.5), max(0, a.GetRightOffset())))
                    if extra > 0 and a.SetRightOffset(a.GetRightOffset() - extra):
                        cola = _final_de_cancion(a, fps)
                        falta = hasta - (a.GetEnd() - int(round(cola * fps)))
                if falta > int(0.5 * fps):                           # se acabo: entera mas tarde
                    nuevo = _mover_cancion(tl, mp, a, ta, int(min(falta, CRUCE_RETRASO_MAX * fps)), fps)
                    if nuevo is not None:
                        a = clips[i][0] = nuevo
                fa, fb = a.GetFades() or {}, b.GetFades() or {}
                a.SetFades({"FadeIn": int(fa.get("FadeIn", 0)),
                            "FadeOut": int(min(CRUCE_SALE_S, max(2.0, cola + 1.0)) * fps)})
                b.SetFades({"FadeIn": int(min(CRUCE_ENTRA_S, 1.5) * fps), "FadeOut": int(fb.get("FadeOut", 0))})
                n += 1
                continue
            extra = int(min(CRUCE_CANCIONES_S * fps, max(0, a.GetRightOffset())))
            if cola <= 0.75 and extra > 0 and a.SetRightOffset(a.GetRightOffset() - extra):
                cruce = a.GetEnd() - b.GetStart()
            if cruce < fps:                      # ni asi se cruzan: se quedan como estaban
                continue
            fa, fb = a.GetFades() or {}, b.GetFades() or {}
            sale = int(min(CRUCE_SALE_S * fps, cruce, a.GetDuration() // 3))
            entra_f = int(min(CRUCE_ENTRA_S * fps, cruce, b.GetDuration() // 3))
            a.SetFades({"FadeIn": int(fa.get("FadeIn", 0)), "FadeOut": sale})
            b.SetFades({"FadeIn": entra_f, "FadeOut": int(fb.get("FadeOut", 0))})
            n += 1
        except Exception:
            pass
    return n


def bajar_musica(tl, mp, tramos, fps, db=MUSICA_BAJO_VOZ):
    """Baja la musica debajo de cada voz, SIN escalon. Resolve no deja poner keyframes de volumen por script, asi
    que el tramo bajo va en otra pista (PISTA_MUSICA_BAJA) con la misma cancion en el mismo punto: la de arriba se
    apaga en RAMPA_VOZ cuadros mientras la baja entra, y al terminar la voz al reves. Como son la misma senal en
    fase, la suma es una rampa de volumen. Si no se puede crear la pista, corta en la misma pista como antes."""
    if not tramos:
        return 0
    margen_a, margen_b = int(0.7 * fps), int(0.6 * fps)
    zonas = []
    for a, b, _ in sorted((t[0], t[1], 0) for t in tramos):
        a, b = a - margen_a, b + margen_b
        if zonas and a - zonas[-1][1] < int(2.0 * fps):          # dos voces casi seguidas: la musica no sube entre ellas
            zonas[-1] = (zonas[-1][0], max(b, zonas[-1][1]))
        else:
            zonas.append((a, b))
    baja = None
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if (tl.GetTrackName("audio", t) or "").strip().upper() == PISTA_MUSICA_BAJA.upper():
            baja = t
    if baja is None and tl.AddTrack("audio", "stereo"):
        baja = tl.GetTrackCount("audio")
        tl.SetTrackName("audio", baja, PISTA_MUSICA_BAJA)
    R = RAMPA_VOZ if baja else 2
    n = 0
    for t in _pistas_musica(tl):
        tl.SetTrackLock("audio", t, False)
        for x in list(tl.GetItemListInTrack("audio", t) or []):
            r0, r1 = x.GetStart(), x.GetEnd()
            tocan = [(max(a, r0), min(b, r1)) for a, b in zonas if a < r1 and b > r0]
            tocan = [(a, b) for a, b in tocan if b - a > 2 * R]
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
            # (pista, inicio, fin, volumen, fundido de entrada, fundido de salida)
            cortes, cur = [], r0
            for a, b in sorted(tocan):
                if a > cur:                      # tramo a volumen normal: se apaga R cuadros dentro del tramo bajo
                    cortes.append((t, cur if (cur == r0 or not baja) else cur - R, a + R if baja else a, vol,
                                   int(fades.get("FadeIn", 0)) if cur == r0 else R, R))
                cortes.append((baja or t, a, b, vol + db, R if a > r0 else int(fades.get("FadeIn", 0)),
                               R if b < r1 else int(fades.get("FadeOut", 0))))
                cur = b
            if cur < r1:
                cortes.append((t, cur - R if baja else cur, r1, vol, R, int(fades.get("FadeOut", 0))))
            if not tl.DeleteClips([x], False):
                continue
            for pista_n, a, b, v, fin_, fout in cortes:
                ini = s0 + int(round((a - r0) * k))
                fin = s0 + int(round((b - r0) * k))          # en audio el cuadro final no se incluye (probado)
                nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": ini, "endFrame": fin, "mediaType": 2,
                                              "trackIndex": pista_n, "recordFrame": a}]) or []
                if not nuevo:
                    continue
                y = nuevo[0]
                y.SetProperty("AudioVolume", v)
                try:
                    y.SetFades({"FadeIn": fin_, "FadeOut": fout})
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


def transiciones(tl, pv, zonas, ver, puestos=()):
    tr = ver["tr"]
    st = tl.GetStartFrame()
    items = sorted([x for x in tl.GetItemListInTrack("video", pv) or [] if x.GetMediaPoolItem() is not None],
                   key=lambda x: x.GetStart())          # sin transiciones (Resolve las lista como items)
    inicios = {st + z0: n for n, z0, _, _ in zonas}
    pieza_en = {}
    for p, x in puestos:
        try:
            pieza_en[x.GetStart()] = p
        except Exception:
            pass
    n_ok = 0
    for a, b in zip(items, items[1:]):
        if a.GetDuration() is None or b.GetDuration() is None:
            continue
        corte = b.GetStart()
        zona = None
        for n, z0, _, _ in zonas:
            if st + z0 <= corte:
                zona = n
        pa, pb = pieza_en.get(a.GetStart()), pieza_en.get(corte)
        if corte in inicios and inicios[corte] != "APERTURA":
            tipo, dur = "Dip To Color Dissolve", tr["zona"]
        elif tr["suave"] and zona in tr["suaves_en"]:
            tipo, dur = "Cross Dissolve", tr["suave"]
        elif pa and pb and (pa.get("relleno") or pb.get("relleno")):
            # una foto entre videos entra y sale fundida; la imagen final, mas despacio
            tipo, dur = "Cross Dissolve", (FUNDIDO_FOTO * 2 if pb.get("final") else FUNDIDO_FOTO)
        elif pa and pb and zona != "APERTURA" and Planificador._parecidas(pa, pb):
            tipo, dur = "Cross Dissolve", FUNDIDO_SALTO          # dos planos casi iguales: fundido corto, no salto
        else:
            continue
        dur = max(2, min(dur, a.GetDuration() // 2, b.GetDuration() // 2))
        n_ok += poner_transicion(b, tipo, dur, "start")
    if items:                                    # fundido a negro al final
        poner_transicion(items[-1], "Cross Dissolve", min(tr["final"], items[-1].GetDuration() - 2), "end", ("left",))
    return n_ok


def disenar_titulo(it, principal, secundario, frase=False, abajo=False):
    """Titulo con diseno: letra script grande con empuje lento + subtitulo en mayusculas espaciadas,
    halo oscuro y sombra para que se lea sobre cualquier toma. frase=True: frase en script mas pequena en
    el tercio inferior (sin subtitulo), para no tapar la accion. abajo=True: el titulo entero en el tercio
    inferior (la tarjeta final va sobre un retrato: en el centro le tapaba la cara)."""
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
            tam = 0.088 if len(principal) <= 26 else 0.076 if len(principal) <= 34 else 0.066
            y = 0.19
        else:
            tam = 0.15 if len(principal) <= 12 else 0.11 if len(principal) <= 24 else 0.085
            y = 0.545 if secundario else 0.5
            if abajo:
                tam *= 0.86
                y -= 0.275
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
        t2.SetInput("Size", 0.031)
        t2.SetInput("Center", {1: 0.5, 2: 0.405 - (0.26 if abajo else 0.0), 3: 0.0})
        try:                                                  # el subtitulo se va abriendo
            t2.AddModifier("CharacterSpacing", "BezierSpline")
            t2.SetInput("CharacterSpacing", 1.22, 0)
            t2.SetInput("CharacterSpacing", 1.42, d)
        except Exception:
            t2.SetInput("CharacterSpacing", 1.3)
        # Halo y sombra con los elementos de sombreado del propio Text+ (ligeros). NO usar la herramienta
        # Shadow de Fusion: con suavizado alto pide buffers de decenas de GB y tumba Resolve.
        for t, (halo_suave, sombra_suave, halo_op) in ((t1, (9.0, 2.0, 0.85)), (t2, (6.0, 1.0, 0.9))):
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
            forma.SetInput("Width", 1.15 if frase else 0.9)
            forma.SetInput("Height", 0.17 if frase else 0.27 if secundario else 0.2)
            forma.SetInput("SoftEdge", 0.16)
            forma.SetInput("Center", {1: 0.5, 2: 0.19 if frase else (0.47 if secundario else 0.5) - (0.265 if abajo else 0.0)})
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
        if disenar_titulo(it, p1, p2, abajo=n.startswith("TEXTO FINAL")):
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


def preparar_grupo(grupo, ver=None):
    """Grupo de color de la version: PRE-CLIP = correccion de color universal, POST-CLIP = LOOK.
    El look es el _REC709 (a media fuerza, ver herramientas/suavizar_looks.py): las tomas ya vienen en Rec.709 y el
    look entero les sube demasiado el contraste y la saturacion."""
    try:
        pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
        pre.SetLUT(1, DCTL_COLOR)
        pre.SetNodeLabel(1, "CORRECCION DE COLOR")
        pre.SetNodeEnabled(1, True)
        if ACTIVAR_LUT:
            look = LOOK_REC709.get((ver or {}).get("sufijo"))
            if look and os.path.exists(os.path.join(DIR_LUT, look.replace("/", os.sep))):
                if not post.SetLUT(1, look):
                    aviso("Grupo %s: no se pudo poner el look suave (%s); queda el look entero." % (grupo.GetName(), look))
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


def lotes_sin_secuencia(fotos, tam=100):
    """Resolve junta en UNA «secuencia de imagenes» las fotos con numeros seguidos (IMG_1001.JPG, IMG_1002.JPG...: los
    nombres que pone la camara) cuando entran en la misma llamada, y entonces ninguna sirve para la intro. Repartidas por
    la paridad de su ultimo numero nunca van dos seguidas juntas (con saltos de 2 las deja sueltas)."""
    pares = ([], [])
    for r in fotos:
        nums = re.findall(r"\d+", os.path.splitext(os.path.basename(r))[0])
        pares[int(nums[-1]) % 2 if nums else 0].append(r)
    return [lote[j:j + tam] for lote in pares for j in range(0, len(lote), tam)]


def importar_fotos(mp, dest, faltan):
    """Importa las fotos como fotos sueltas (ver lotes_sin_secuencia) y, si alguna no quedo (Resolve armo una secuencia
    de todos modos), la importa sola: de una en una nunca hace secuencia.
    OJO: aqui no se borra nada del media pool. mp.DeleteClips justo despues de importar cerro DaVinci (2026-11-13: al
    borrar cambia un instante a la pagina Medios y ahi se cayo); una secuencia vieja se queda, no estorba."""
    for lote in lotes_sin_secuencia(faltan):
        mp.SetCurrentFolder(dest)
        mp.ImportMedia(lote)
    hay = {os.path.normcase(c.GetClipProperty("File Path") or "") for c in dest.GetClipList() or []}
    for r in faltan:
        if os.path.normcase(r) not in hay:
            mp.SetCurrentFolder(dest)
            mp.ImportMedia([r])


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
                if top == "FOTOS":
                    importar_fotos(mp, dest, faltan)
                else:
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
    ritmo = _modulo("ritmo") if CORTAR_AL_RITMO and not globals().get("SIN_RESOLVE") else None   # el plan previo: sin musica

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
            plan.usados = {}                     # cada version elige de TODO el material: la larga no se queda con las sobras
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
                    piezas, reusos = plan.zona([nombre], z1 - z0, ver["corte"], rng, nombre != "MAQUILLAJE",
                                               ver["sufijo"] in RELLENO_FOTOS)
                    lo = ver["corte"][0]
                al_golpe += al_ritmo(piezas, z0, z1, golpes, fps, lo)
                zonas.append((nombre, z0, z1, piezas))
                info_z[nombre] = {"seg": round((z1 - z0) / float(fps), 1),
                                  "videos": sum(1 for p in piezas if p["tipo"] != "foto"),
                                  "dron": sum(1 for p in piezas if p["tipo"] == "dron"),
                                  "fotos": sum(1 for p in piezas if p["tipo"] == "foto"),
                                  "relleno_dron": plan.relleno["dron"], "reutilizados": reusos}
                if reusos:
                    aviso("%s %s: %d planos repiten video ya usado (falta material)." % (ver["sufijo"], nombre, reusos))
            try:                                 # el FINAL: un solo plano, el mejor, en camara lenta
                marcas = {(m.get("name") or "").strip().upper(): int(f) for f, m in (tpl.GetMarkers() or {}).items()}
                antes = FINAL_ANTES_S if ver["seg"] > 60 else 0.5       # en el de 1 minuto cada segundo cuenta
                c0 = marcas.get("CIERRE", total_f - 6 * fps) - int(antes * fps)
                if zonas and c0 > zonas[-1][1] + 2 * fps:
                    nombre_z, z0, z1, piezas = zonas[-1]
                    h = plan.foto_final(z1 - c0) or plan.heroe(z1 - c0)
                    if h is not None:
                        pos, quedan = z0, []
                        for p in piezas:
                            if pos >= c0:
                                break
                            if pos + p["dur_f"] > c0:    # el plano que cruza el final se acorta hasta ahi
                                if c0 - pos < int(0.8 * fps) and quedan:
                                    quedan[-1]["dur_f"] += c0 - pos
                                    pos = c0
                                    break
                                p["dur_f"] = c0 - pos
                            quedan.append(p)
                            pos += p["dur_f"]
                        if pos < c0 and quedan:
                            quedan[-1]["dur_f"] += c0 - pos
                        zonas[-1] = (nombre_z, z0, z1, quedan + [h])
            except Exception as ex:
                aviso("%s: no se pudo preparar el plano final (%s)" % (ver["sufijo"], ex))
            lentos, estab = plan.marcar_efectos(zonas, fps, LENTOS.get(ver["sufijo"], 2))
            planes.append((ver, tpl, intro, zonas))
            reporte["versiones"].append({"timeline": "%s - %s" % (evento, ver["sufijo"]), "zonas": info_z,
                                         "fotos_intro": len(intro), "cortes_al_ritmo": al_golpe,
                                         "camara_lenta": lentos, "estabilizar": estab})
            print("%s: %s | %d cortes al ritmo | %d en camara lenta | %d a estabilizar" % (ver["sufijo"], ", ".join(
                "%s %d" % (n, z["videos"]) for n, z in info_z.items()), al_golpe, lentos, estab))
        return plan, planes
    plan, planes = planificar()
    globals()["PLANES"] = planes                 # para las pruebas: el plan sin tocar Resolve
    if plan.accidentales:
        reporte["accidentales"] = plan.accidentales
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
    ruidos = {}                                  # ruta -> ruido medido (el mismo proceso para cualquier video)
    drx_ruido = rd.drx_activo(ruido_n)           # el ruido de DaVinci que la persona dejo guardado (o None)
    if drx_ruido:
        print("Ruido: se usa el ajuste de DaVinci guardado en todas las tomas.")
    try:
        rt = _modulo("ruido_tomas")
    except Exception as ex:
        rt = None
        aviso("No se pudo cargar el medidor de ruido (%s); todas las tomas van con el nivel normal." % ex)
    objetivos = objetivos_de_luz(items)
    sat_evento = objetivo_de_saturacion(items)
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
    try:
        propios = sfx_propios(mp, root)
    except Exception as ex:
        propios = {}
        aviso("No se pudieron cargar los efectos de sonido propios (%s)" % ex)
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

        voces_plan = []
        try:                                    # la voz original (pastor, brindis, discursos): donde va cada una
            voces_plan = ubicar_voces(elegir_voces(items, ver["sufijo"], zonas, fps, plan.accidentales),
                                      zonas, plan, fps)
        except Exception as ex:
            aviso("%s: no se pudo elegir la voz (%s)" % (nombre, ex))
        marcar_acercados(zonas)
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
        try:                                    # ruido de cada video de esta version (cada video se mide una sola vez)
            sin_medir = [(p["item"]["ruta"], p["item"].get("dur")) for p, _ in puestos
                         if p["tipo"] != "foto" and os.path.normcase(p["item"]["ruta"]) not in ruidos]
            if rt and sin_medir and ruido_n > 0 and not drx_ruido:
                ruidos.update(rt.medir_varios(sin_medir, print))
        except Exception as ex:
            aviso("No se pudo medir el ruido de los videos (%s); van con el nivel normal." % ex)
        niveles_ruido = {}
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
                    medida = ruidos.get(os.path.normcase(p["item"]["ruta"]))
                    nv = rd.aplicar(x, ruido_n, medida, drx_ruido)
                    if nv is not None:
                        niveles_ruido[nv] = niveles_ruido.get(nv, 0) + 1
                    if nv == "davinci" and not IGUALAR:  # el grado guardado trae el color del clip donde se capturo
                        x.SetCDL({"NodeIndex": "1", "Slope": "1.0 1.0 1.0", "Offset": "0.0 0.0 0.0",
                                  "Power": "1.0 1.0 1.0", "Saturation": "1.0"})
                    if IGUALAR:
                        cdl = cdl_para(p, objetivos.get((p.get("momento") or p["item"].get("momento")), 0.42), sat_evento)
                        if cdl and x.SetCDL(cdl):
                            info["igualados"] = info.get("igualados", 0) + 1
            except Exception:
                pass
        if grupo:
            preparar_grupo(grupo, ver)
        info["ruido"] = rd.resumen(niveles_ruido)
        info["camara_lenta"] = sum(1 for p, _ in puestos if p.get("lento_ok") and not p.get("conformado"))
        info["fotos_relleno"] = sum(1 for p, _ in puestos if p.get("relleno"))
        info["estabilizados"] = estabilizar(puestos)
        info["acercados"] = acercar(puestos)
        if USAR_VIDEOS_VERTICALES:
            info["reencuadrados"] = reencuadrar(project, puestos)
        info["transiciones"] = transiciones(tl, pv, zonas, ver, puestos)
        info["titulos"] = titulos(tl, ver, fps, fecha_txt, perfil, f.year)
        info["textos_plantilla"] = textos_plantilla(tl, perfil)
        try:
            info["textos_con_halo"] = legibilidad_plantilla(tl)
            info["velos_plantilla"] = velos_plantilla(tl, mp, png, fps, intro_f)
        except Exception as ex:
            aviso("%s: no se pudo dar contraste a los textos de la plantilla (%s)" % (nombre, ex))
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
        try:                                     # los momentos fuertes: subida y golpe a la fiesta, destellos, clics
            ini_fotos, pos_f = [], 0
            for p in intro:
                ini_fotos.append(pos_f)
                pos_f += p["dur_f"]
            info["momentos"] = _modulo("sfx").momentos(tl, mp, propios, fps, ini_fotos, print)
        except Exception as ex:
            aviso("%s: no se pudieron colocar los momentos (%s)" % (nombre, ex))
        voces = []
        try:                                     # la palabra del pastor, brindis y discursos sobre la musica
            voces = poner_voces(tl, mp, pool, voces_plan, fps)
            info["voces"] = ["%s %.0f s%s «%s»" % (v["tipo"], v["fin"] - v["ini"],
                                                  " (se le ve hablar)" if v.get("sincro") else "", v["texto"][:60])
                             for _, _, v in voces]
        except Exception as ex:
            aviso("%s: no se pudo poner la voz (%s)" % (nombre, ex))
        try:                                     # cruce entre canciones sin hueco de volumen
            info["cruces_musica"] = cruces_de_musica(tl, mp, fps)
        except Exception as ex:
            aviso("%s: no se pudieron suavizar los cruces de musica (%s)" % (nombre, ex))
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
        if info.get("ruido"):
            print("   ruido quitado segun cada toma: %s" % info["ruido"])
    pm.SaveProject()


main()
result = reporte
