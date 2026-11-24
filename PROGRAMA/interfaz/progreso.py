# -*- coding: utf-8 -*-
"""
progreso.py - (23-nov) Lo que lleva cada paso, lo que falta y lo que esta haciendo ahora (pantalla de trabajo).

La persona (23-nov): «mejora el proceso, ya que se mantiene el tiempo igual y no sé si está avanzando... que indique
el proceso de cada paso». VISTO en su registro (boda de 654 archivos sin analizar, 20:07-20:27): las personas, la IA y
el oido tardaron 15 min y en todo ese rato la barra se quedo en 11 % (solo contaba «  N/M  archivo»), «faltan X min»
casi no cambiaba (salia de ese 11 %) y la linea de lo que hacia estaba oculta mientras trabaja.

Sin Qt (se prueba repitiendo un registro real con sus horas): lee lo mismo que va al registro (linea) y el avance del
motor (avance), y estado(t) da:
  - cada paso: hecho / activo / pendiente, un detalle corto («40 de 57», «62 %»), su avance (0-1; -1 = sin cuenta),
    desde cuando corre (la ventana cuenta los segundos) o cuanto tardo;
  - el avance de todo (0-1) POR TIEMPO: cada paso pesa lo que se estima que tarda (motor.estimar_partes);
  - lo que falta: lo que le queda al paso de ahora, a la velocidad a la que de verdad va, mas lo estimado de los que
    vienen; la hora de fin se suaviza (no salta con cada linea);
  - «ahora»: lo que esta haciendo, en una linea.
"""
import math
import re
import time

MIN_EST = 20.0                # ningun paso que de verdad corre se estima en menos (los de 0 s: material ya analizado)
SUAVE_S = 20.0                # la hora de fin se acerca a la nueva en ~20 s (no salta de minuto en minuto)
EST_VERTICAL_SOLO = 150.0     # el vertical de 1 min que se agrega solo (23-nov, medido: 213 s con su analisis; 91 s eran
#                               «Terminando de reconocer a las personas»)
EST_PLANTILLA = 26.0          # cada plantilla de referencia (23-nov, medido: 4 en 104 s)
_CUENTA = re.compile(r"^\s*(\d+)/(\d+)\s+(\S.*)$")                                   # «  605/654  DSC_4998.MP4»
_PISTA = re.compile(r"^\s*(personas|IA revisión|IA|oído)\s+(\d+)/(\d+)\b\s*(.*)$")   # «  IA 10/57  X.MP4: ...»
_LISTA = re.compile(r"^(.*?) lista: \d+ (?:clips|planos)")                         # «... 1 MIN lista: 58 clips»
_RENDER = re.compile(r"^\s*(?:\d+ s\s+)?(.+?) (\w+) (\d+)%\s*$")                   # «  95 s  1min Rendering 45%»
_ESTADOS_RENDER = ("Rendering", "Complete", "Ready", "Queued", "Failed", "Cancelled")
_VIDEO = re.compile(r"\.(mp4|mov|mxf|m4v|avi|mts|m2ts|mkv|insv|lrv|3gp|webm)\b", re.I)
# «IA y oído»: tres pistas a la vez; lo que pesa cada una (medido 23-nov, boda de 654 archivos: 265 / 850 / 713 s)
PESO_PISTA = {"personas": 1.0, "vista": 2.5, "oido": 2.0}
_NOMBRE_PISTA = {"personas": "personas", "IA": "ia", "IA revisión": "revision", "oído": "oido"}


def duracion(s):
    """«40 s», «12 min», «1 h 05 min»."""
    s = max(0, int(round(s)))
    if s < 60:
        return "%d s" % s
    m = int(round(s / 60.0))
    return "%d min" % m if m < 60 else "%d h %02d min" % (m // 60, m % 60)


def falta(s):
    """«faltan 18 min», «falta 1 min», «falta 1 h 05 min»."""
    if s < 60:
        return "falta menos de 1 min"
    m = int(round(s / 60.0))
    if m >= 60:
        return "falta %d h %02d min" % (m // 60, m % 60)
    return "falta 1 min" if m == 1 else "faltan %d min" % m


def _num(texto, patron):
    a = re.search(patron, texto)
    return int(a.group(1)) if a else None


def _corto(m, largo=118):
    """Una linea del registro para la persona: sin «== ==», con «…» y sin espacios de sobra."""
    s = re.sub(r"\s+", " ", str(m)).strip()
    if s.startswith("== ") and s.endswith(" =="):
        s = s[3:-3]
    s = s.replace("...", "…")
    if len(s) > largo:
        s = s[:largo - 1].rstrip(" ,.;:·") + "…"
    return s


def _version(etq):
    """«1min» -> «1 min», «VERTICAL 1min» -> «vertical 1 min»."""
    s = re.sub(r"(\d+)min\b", r"\1 min", etq)
    return s.replace("VERTICAL", "vertical")


# (23-nov, la persona: «que el proceso que indica los tiempos sea más conciso y no se quede parado») Lo que dice el
# trabajo es para el registro (rutas, medidas, avisos largos: 77 letras de media y hasta 118 en la corrida del 23-nov).
# La persona ve UNA frase corta de lo que se hace ahora: (como empieza la linea, lo que se muestra). "" = no se muestra
# (queda lo de antes); {v} = la version que se arma; lo que no esta en la lista y es largo o tecnico tampoco se muestra.
AHORA_MAX = 64
_FRASES = (
    ("Material YA ANALIZADO", "Material ya analizado"), ("Recuperé el análisis", "Análisis recuperado del material"),
    ("== Analizando material", "Revisando fotos y videos"), ("Analizando ", "Revisando fotos y videos"),
    ("Reconociendo a las personas", "Reconociendo a las personas"),
    ("Terminando de reconocer", "Reconociendo a las personas"), ("Personas reconocidas", "Personas reconocidas"),
    ("El oído termina", "El oído termina de escuchar"), ("Clasificacion automatica", "Ordenando por momentos"),
    ("== Plan previo", "Planeando cada versión"), ("== Plan (", "Planeando cada versión"),
    ("== Conectando con DaVinci", "Conectando con DaVinci"), ("Abriendo DaVinci", "Abriendo DaVinci"),
    ("Esperando a DaVinci", "Abriendo DaVinci"), ("DaVinci contestó", "DaVinci listo"),
    ("Abriendo el proyecto", "Abriendo el proyecto"), ("Archivos reenlazados", "Material enlazado en DaVinci"),
    ("== Armando timelines", "Armando las versiones"), ("Media pool: ", "Ordenando el media pool"),
    ("Metadatos en DaVinci", "Ordenando el media pool"), ("Personas (IA de DaVinci)", "Personas reconocidas"),
    ("Escuchando ", "DaVinci escucha votos y brindis"), ("Ritmo: ", "Midiendo el ritmo de la música"),
    ("Música propia", "{v} · música"), ("color medido", "{v} · color plano por plano"),
    ("Estabilizados", "{v} · estabilizando"), ("Overlays de luz", "{v} · luces y destellos"),
    ("Ambiente real", "{v} · sonido"), ("SFX", "{v} · sonido"), ("texto detrás", "{v} · títulos"),
    ("ruido quitado", "{v} · limpiando el ruido"),
    ("== Formato vertical", "Armando el vertical"), ("== Plantillas", "Armando tus plantillas"),
    ("Renderizando ", "Renderizando"), ("== Renderizando", "Renderizando"), ("Memoria de video libre", "Renderizando"),
    ("== Masterizando", "Dejando el audio listo"), ("Audio masterizado", "Audio listo"),
    ("Imagen ", "Revisando la imagen"), ("Audio de ", "Revisando el audio"), ("Escuchando el audio", "Revisando el audio"),
    ("Revisando con IA", "La IA revisa los videos"), ("Revision con IA", "La IA revisó los videos"),
    ("Proxies", "Haciendo proxies para editar"), ("Haciendo proxies", "Haciendo proxies para editar"),
    ("Haciendo la plantilla", "Guardando las plantillas de DaVinci"), ("Videos en:", "Videos listos"),
    ("LISTO:", "Video terminado"), ("Listo en", ""),
)
_CALLADAS = ("Carpeta de trabajo", "Instalacion", "Metadatos escritos", "Midiendo", "Aviso", "AVISO", "VIGIA", "Zonas",
             "Lo que DaVinci", "Renombrados", "Prioridad", "Con el video que hay", "Hay ", "▶", "[preanalisis]",
             "MAQUILLAJE ", "IGLESIA ", "FIESTA ", "Formato vertical", "La IA local", "El oído escuchó", "plantilla:",
             "1min", "3min", "15min", "30min", "VERTICAL ", "Orden del media pool", "DaVinci quedó", "== Terminado")


def humano(m, v=""):
    """La frase corta que ve la persona por una linea del trabajo; None = esa linea no se muestra."""
    s = re.sub(r"\s+", " ", str(m)).strip()
    if not s:
        return None
    a = re.match(r"^(\d+)/(\d+) escuchados", s)
    if a:
        return "DaVinci escucha · %s de %s" % a.groups()
    a = re.search(r"VIDEO FINAL (HORIZONTAL|VERTICAL) (\d+) MIN(.*)$", s)
    if a:
        cual = ("vertical " if a.group(1) == "VERTICAL" else "") + "%s min" % a.group(2)
        resto = a.group(3)
        if " lista:" in resto:
            return _mayus("%s armado · %s clips" % (cual, (re.search(r"(\d+) clips", resto) or re.search(r"(\d+)", resto)
                                                         ).group(1)))
        if "Complete" in resto:
            return _mayus("%s renderizado" % cual)
        if "encuadre" in resto:
            return "Armando %s · encuadre" % cual
        return None if len(resto) > 30 else _mayus(cual)
    a = re.match(r"^plantilla: (\d+) huecos", s)
    if a:
        return ""                                    # (la cuenta la pone Progreso: «Plantilla 2 de 4»)
    a = re.match(r"^proxies (enlazados )?(\d+)/(\d+)", s)
    if a:
        return "%s proxies · %s de %s" % ("Enlazando" if a.group(1) else "Haciendo", a.group(2), a.group(3))
    for empieza, frase in _FRASES:
        if s.startswith(empieza):
            if not frase:
                return None
            return frase.replace("{v}", "Armando %s" % v if v else "Armando")
    if s.startswith(_CALLADAS) or ":\\" in s or str(m)[:1].isspace():
        return None
    s = s[3:-3] if s.startswith("== ") and s.endswith(" ==") else s
    s = s.replace("...", "…")
    return s if len(s) <= AHORA_MAX else None


def _mayus(s):
    return s[:1].upper() + s[1:]


class Progreso:
    def __init__(self, pasos, etapas, estimados=None, versiones=(), t=None, videos_nuevos=0):
        """pasos: [(clave, nombre)] de la fila; etapas: [(texto del registro, clave)] = el paso que empieza;
        estimados: {clave: segundos}; versiones: lo que se arma (cuenta «Armar», el render y el masterizado);
        videos_nuevos: los videos sin analizar (al analizar, una foto tarda 0,02 s y un video ~5 s: cuentan ellos)."""
        self.pasos = [c for c, _ in pasos]
        self.etapas = list(etapas)
        self.est = {c: float((estimados or {}).get(c) or 0.0) for c in self.pasos}
        self.n_vers = max(1, len(versiones))
        self.versiones = [str(v) for v in versiones]
        # «Armar»: cuantas cosas se arman en total (versiones + el vertical que se agrega solo + las plantillas de
        # referencia) y cuantas plantillas van. (23-nov, VISTO: «1 de 1 · 66 %» quieto 6,5 min y «faltan 2 min» todo
        # ese rato, porque el vertical automatico y 4 plantillas no contaban)
        self.n_arm = self.n_vers
        self.plantillas = (0, 0)      # (las que ya empezaron, las que son)
        self.vertical_solo = False
        self._hito = None             # cuando se armo lo ultimo (entre hito e hito el avance sigue andando)
        self.n_vid = max(0, int(videos_nuevos or 0))
        self.inicio = time.time() if t is None else float(t)
        self.estado_paso = {c: "pendiente" for c in self.pasos}
        self.desde, self.hasta = {}, {}
        self.cuenta = (0, 0)          # «Analizar»: archivos (n, total)
        self.vids = set()             # «Analizar»: videos ya contados
        self.pistas = {}              # «IA y oído»: pista -> {n, total, fin, t0, tn, paso}
        self.listas = set()           # «Armar»: versiones ya armadas
        self.davinci = False          # «Armar»: DaVinci ya contesto (antes: abriendolo)
        self.render = 0.0             # 0-1: lo mas alto entre el avance del motor y la cola de render de DaVinci
        self.partes = {}              # cola de render: version -> 0-1
        self.master = 0               # videos con el audio masterizado
        self.ahora = "Empezando…"
        self.f = 0.0
        self.terminado = None
        self._fin = self._t_fin = None
        self._activar(self.pasos[0], self.inicio)

    # ---------------------------------------------------------------- lo que llega
    def _activar(self, c, t):
        for k in self.pasos[:self.pasos.index(c)]:     # los de antes quedan hechos (como la fila de la ventana)
            if self.estado_paso[k] == "activo":
                self.hasta[k] = t
            if self.estado_paso[k] in ("pendiente", "activo"):
                self.estado_paso[k] = "hecho"
        self.estado_paso[c] = "activo"
        self.desde[c] = t

    def activo(self):
        return next((c for c in self.pasos if self.estado_paso[c] == "activo"), None)

    def _i_activo(self):
        c = self.activo()
        if c is not None:
            return self.pasos.index(c)
        return max([i for i, k in enumerate(self.pasos) if self.estado_paso[k] == "hecho"] or [-1])

    def linea(self, m, t=None):
        """Una linea de lo que va diciendo el trabajo (la misma que va al registro)."""
        t = time.time() if t is None else float(t)
        m = str(m)
        if self.terminado is not None or not m.strip():
            return
        if re.search(r": Complete\s", m):             # «… VIDEO FINAL … 3 MIN: Complete  C:\…»: la cola entera termino
            self.partes = {k: 1.0 for k in self.partes}
            self.render = 1.0
        for txt, c in self.etapas:                    # el paso que empieza (nunca hacia atras), como _paso_vista
            if txt in m:
                # (23-nov, VISTO: el audio de cada video se masteriza en cuanto ese video sale; con el primero la fila
                # pasaba a «Masterizar · 1 de 2» y ahi se quedaba 202 s mientras se renderizaba el siguiente)
                espera = c == "master" and m.startswith("Audio masterizado") and any(
                    v < 1.0 for v in self.partes.values())
                if c in self.estado_paso and self.pasos.index(c) > self._i_activo() and not espera:
                    self._activar(c, t)
                break
        self._contar(m, t)

    def avance(self, pct, texto, t=None):
        """El avance(pct, texto) del motor: 45-95 es el render."""
        if 45 <= pct <= 96:
            self.render = max(self.render, min(1.0, (pct - 45) / 50.0))
        self.linea(texto, t)

    def _pista(self, nombre, t, n=None, total=None, fin=False):
        p = self.pistas.get(nombre)
        if p is None:
            p = self.pistas[nombre] = {"n": 0, "total": 0, "fin": False, "t0": t, "tn": t, "paso": 0}
        if n is not None and n > p["n"]:
            p["paso"] = max(p["paso"], n - p["n"])  # cada cuanto avisa (personas de 100 en 100, la IA de 10 en 10)
            p["n"], p["tn"] = n, t
        if total:
            p["total"] = total
        if fin:
            p["fin"] = True

    def _texto_pistas(self):
        """«La IA revisa cada toma 40 de 57 · personas 600 de 654 · oído 30 de 48» (lo que aun corre)."""
        p, partes = self.pistas, []
        cuenta = lambda q: " %d de %d" % (q["n"], q["total"]) if q["total"] else ""
        if "revision" in p and not p["revision"]["fin"]:      # (23-nov) la cuenta va por cuadro (avanza parejo)
            partes.append("La IA revisa cuadro por cuadro" + (" ·" + cuenta(p["revision"]) if p["revision"]["total"]
                                                               else ""))
        elif "ia" in p and not p["ia"]["fin"]:
            partes.append("La IA mira cada toma" + cuenta(p["ia"]))
        for clave, nombre in (("personas", "personas"), ("oido", "oído")):
            if clave in p and not p[clave]["fin"]:
                partes.append(nombre + cuenta(p[clave]))
        return " · ".join(partes) if partes else None

    def _contar(self, m, t):
        a = _PISTA.match(m)
        if a:
            self._pista(_NOMBRE_PISTA[a.group(1)], t, int(a.group(2)), int(a.group(3)))
            self.ahora = self._texto_pistas() or self.ahora
            return
        a = _CUENTA.match(m)
        if a and "escuchados" not in m:
            n, total = int(a.group(1)), int(a.group(2))
            if total:
                self.cuenta = (n, total)
                archivo = a.group(3).strip()
                if _VIDEO.search(archivo):
                    self.vids.add(archivo)
                self.ahora = "Revisando fotos y videos · %d de %d" % (n, total)
            return
        # las pistas de «IA y oído» que empiezan o terminan
        pista = False
        for empieza, nombre, total in (("Reconociendo a las personas", "personas", None),
                                       ("Viendo cada toma con la IA", "ia", r"(\d+) archivos"),
                                       ("La IA local revisa cada toma", "revision", None),
                                       ("El oído (earshot) escucha", "oido", r"escucha (\d+) tomas")):
            if m.startswith(empieza):
                self._pista(nombre, t, 0, _num(m, total) if total else None)
                pista = True
        for termina, nombre in (("Personas reconocidas", "personas"), ("La IA local vio", "ia"),
                                ("La IA local revisó", "revision"), ("El oído escuchó", "oido")):
            if m.startswith(termina):
                self._pista(nombre, t, fin=True)
                pista = True
        if self.activo() == "ia" and (pista or self.pistas):     # mientras corren: lo que lleva cada una
            resumen = self._texto_pistas()
            if resumen:
                self.ahora = resumen
                return
        # la cola de render de DaVinci: «  95 s  1min Rendering 45% | 3min Ready 0%» (cada parte, su version)
        partes = []
        for x in m.split(" | "):
            r = _RENDER.match(x)
            if r and r.group(2) in _ESTADOS_RENDER:
                partes.append(r.groups())
        if partes:
            for etq, est, pct in partes:
                v = 1.0 if est == "Complete" else int(pct) / 100.0 if est == "Rendering" else 0.0
                self.partes[etq] = max(self.partes.get(etq, 0.0), v)
            self.render = max(self.render, sum(self.partes.values()) / float(max(len(self.partes), self.n_vers)))
            activa = next(((e, p) for e, s, p in partes if s == "Rendering"), None)
            if activa:
                self.ahora = "Renderizando %s · %s %%" % (_version(activa[0]), activa[1])
            return
        a = _LISTA.match(m)
        if a and a.group(1).strip() not in self.listas:
            self.listas.add(a.group(1).strip())
            self._hito = t
        if m.startswith(("DaVinci contestó", "Abriendo el proyecto", "Archivos reenlazados", "== Armando timelines")):
            if not self.davinci:
                self._hito = t
            self.davinci = True
        if "se arma tambien el VERTICAL" in m and not self.vertical_solo:      # el vertical que se agrega solo
            self.vertical_solo = True
            self.n_arm = max(self.n_arm, len(self.listas)) + 1
            self.est["armar"] = self.est.get("armar", 0.0) + EST_VERTICAL_SOLO
        if m.startswith("== Plantillas:"):                                     # «== Plantillas: A, B, C ==»
            n = len([x for x in m.strip("= ").partition(":")[2].split(",") if x.strip()])
            self.plantillas = (0, n)
            if len(self.listas) + n > self.n_arm:                              # (no venian en las versiones)
                self.est["armar"] = self.est.get("armar", 0.0) + EST_PLANTILLA * (len(self.listas) + n - self.n_arm)
                self.n_arm = len(self.listas) + n
            self._hito = t
        if re.match(r"^\s*plantilla: \d+ huecos", m) and self.plantillas[1]:
            self.plantillas = (min(self.plantillas[0] + 1, self.plantillas[1]), self.plantillas[1])
            self._hito = t
            self.ahora = "Armando tu plantilla %d de %d" % self.plantillas
            return
        if m.startswith("Audio masterizado"):
            self.master += 1
        try:
            h = humano(m, self._armando())
        except Exception:                             # una linea rara nunca tumba el avance: queda lo de antes
            h = None
        if h:
            self.ahora = h

    def _armados(self):
        """Cuantas cosas ya quedaron armadas (versiones + plantillas ya empezadas menos la que corre)."""
        return len(self.listas) + max(0, self.plantillas[0] - 1)

    def _armando(self):
        """«3 min», «vertical 1 min»: la version que se arma ahora (la que sigue a las ya listas)."""
        k = len(self.listas)
        if k < len(self.versiones) and re.search(r"\d+min", self.versiones[k]):
            return _version(self.versiones[k])
        return "el vertical" if self.vertical_solo and not self.plantillas[1] else ""

    def terminar(self, t=None):
        """Termino (bien o con error): el paso de ahora deja de contar segundos."""
        t = time.time() if t is None else float(t)
        if self.terminado is None:
            self.terminado = t
            c = self.activo()
            if c is not None:
                self.hasta[c] = t

    def tiempos(self):
        """{paso: segundos} lo que tardo de verdad cada paso que corrio y termino (para aprender: motor.guardar_tiempos)."""
        return {c: round(self.hasta[c] - self.desde[c], 1) for c in self.pasos
                if c in self.desde and c in self.hasta and self.hasta[c] > self.desde[c]}

    # ---------------------------------------------------------------- lo que se muestra
    def _f_tiempo(self, c, t):
        """Sin cuenta: por el tiempo estimado (90 % al llegar a lo estimado; despues sigue, cada vez mas lento)."""
        est = max(MIN_EST, self.est.get(c, 0.0))
        x = max(0.0, t - self.desde.get(c, t)) / est
        return 0.9 * x if x < 1 else 0.9 + 0.09 * (1.0 - math.exp(-(x - 1.0)))

    def _f_pistas(self, t):
        """«IA y oído»: lo que llevan las pistas, cada una por su peso. Entre dos avisos (la IA avisa cada 10 tomas: en
        la boda del 23-nov pasaron 5 min sin ninguno) sigue a la velocidad que lleva, sin pasar del aviso siguiente:
        el % no se queda quieto ni promete mas de lo que se ve."""
        p = self.pistas
        if not p:
            return None

        def fr(nombre):
            q = p[nombre]
            if q["fin"]:
                return 1.0
            tot = q["total"] or (p["ia"]["total"] if nombre == "revision" and "ia" in p else 0)  # las mismas tomas
            if not tot:
                return 0.0
            if q["n"] > 0 and q["tn"] - q["t0"] >= 1:
                ritmo = q["n"] / (q["tn"] - q["t0"])
            else:                                     # aun sin avisos: al ritmo de lo estimado para el paso
                ritmo = tot / max(MIN_EST, self.est.get("ia", 0.0))
            paso = max(1, q["paso"] or min(10, tot))
            # se acerca al aviso siguiente cada vez mas despacio (63 % de ese tramo en lo que deberia tardar, 95 % en
            # el triple): siempre se mueve y nunca pasa de lo que de verdad va a decir el aviso
            visto = q["n"] + paso * (1.0 - math.exp(-ritmo * max(0.0, t - q["tn"]) / paso))
            return min(1.0, visto / float(tot))
        partes = []
        if "personas" in p:
            partes.append(("personas", fr("personas")))
        if "ia" in p or "revision" in p:
            fi = fr("ia") if "ia" in p else 1.0
            partes.append(("vista", 0.33 * fi + (0.67 * fr("revision") if "revision" in p else 0.0)))
        if "oido" in p:
            partes.append(("oido", fr("oido")))
        return sum(PESO_PISTA[k] * v for k, v in partes) / sum(PESO_PISTA[k] for k, _ in partes)

    def _sub(self, c, t):
        """(avance 0-1 del paso, True si sale de una cuenta de verdad)."""
        if c == "analizar" and self.cuenta[1]:
            f = self.cuenta[0] / float(self.cuenta[1])
            if self.n_vid:                            # lo que tarda son los videos (una foto: 0,02 s; un video: ~5 s)
                f = 0.15 * f + 0.85 * min(1.0, len(self.vids) / float(self.n_vid))
            return f, True
        if c == "ia":
            f = self._f_pistas(t)
            if f is not None:
                return f, True
        if c == "armar" and (self.davinci or self.listas):
            # lo ya armado y, entre uno y otro, lo que va del que se arma (se acerca al siguiente sin llegar: el
            # avance nunca se queda quieto ni promete lo que aun no se ve)
            n = float(max(1, self.n_arm))
            cada = max(MIN_EST, 0.85 * max(MIN_EST, self.est.get("armar", 0.0)) / n)
            va = 0.9 * (1.0 - math.exp(-max(0.0, t - (self._hito or self.desde.get(c, t))) / cada))
            return 0.15 + 0.85 * min(n, self._armados() + va) / n, True
        if c == "render" and self.render > 0:
            return self.render, True
        if c == "master" and self.master:
            return min(1.0, self.master / float(self.n_vers)), True
        return self._f_tiempo(c, t), False

    def _resto(self, c, t):
        """Lo que le queda al paso de ahora: lo estimado y, en cuanto hay cuenta, a la velocidad real."""
        est = max(MIN_EST, self.est.get(c, 0.0))
        pasado = max(0.0, t - self.desde.get(c, t))
        sub, contado = self._sub(c, t)
        r_est = max(est - pasado, 0.12 * est)        # pasado lo estimado siempre queda algo (nunca «0 min» quieto)
        if contado and sub >= 0.03 and pasado >= 15:
            w = min(1.0, sub * 1.6)
            return (1.0 - w) * r_est + w * pasado * (1.0 - sub) / sub
        return r_est

    def _detalle(self, c, sub, contado):
        if c == "analizar":
            return "%d de %d" % self.cuenta if self.cuenta[1] else "Revisando"
        if c == "armar":
            k = self._armados()
            return "%d de %d" % (min(k, self.n_arm), self.n_arm) if k else ("Preparando" if self.davinci
                                                                             else "Abriendo DaVinci")
        if c == "master":
            return "%d de %d" % (min(self.master, self.n_vers), self.n_vers) if self.master else ""
        if c in ("ia", "render"):
            return "%d %%" % int(round(sub * 100)) if contado else "Empezando"
        return ""

    def _resumen(self, c):
        """Lo que hizo un paso ya hecho («654 archivos», «3 versiones»)."""
        plural = lambda n, uno, varios: "%d %s" % (n, uno if n == 1 else varios)
        if c == "analizar" and self.cuenta[1]:
            return plural(self.cuenta[1], "archivo", "archivos")
        if c == "ia" and self.pistas.get("ia", {}).get("total"):
            return plural(self.pistas["ia"]["total"], "toma", "tomas")
        if c == "armar" and self.listas:
            return plural(len(self.listas), "versión", "versiones") + (
                " y %s" % plural(self.plantillas[1], "plantilla", "plantillas") if self.plantillas[1] else "")
        if c == "render":
            n = sum(1 for v in self.partes.values() if v >= 1.0)
            return plural(n, "video", "videos") if n else ""
        if c == "master" and self.master:
            return plural(self.master, "video", "videos")
        return ""

    def estado(self, t=None):
        """{"pasos": {clave: {estado, detalle, tiempo, pct, desde}}, "f", "resto" (s o None), "ahora", "activo"}.
        desde = milisegundos de la epoca del paso que corre (la ventana cuenta), 0 si no corre."""
        t = time.time() if t is None else float(t)
        if self.terminado is not None:
            t = min(t, self.terminado)
        activo = self.activo()
        pasos, hecho, total = {}, 0.0, 0.0
        for c in self.pasos:
            e = self.estado_paso[c]
            est = max(MIN_EST, self.est[c]) if (e == "activo" or c in self.desde) else self.est[c]
            total += est
            d = {"estado": e, "detalle": "", "tiempo": "", "pct": -1.0, "desde": 0.0}
            if e == "activo":
                sub, contado = self._sub(c, t)
                hecho += est * min(1.0, sub)
                d["detalle"] = self._detalle(c, sub, contado)
                d["pct"] = round(min(1.0, sub), 3) if contado else -1.0
                if self.terminado is None:
                    d["desde"] = self.desde[c] * 1000.0
                else:
                    d["tiempo"] = duracion(self.terminado - self.desde[c])
            elif e == "hecho":
                hecho += est
                d["detalle"] = self._resumen(c)
                if c in self.desde and c in self.hasta:
                    d["tiempo"] = duracion(self.hasta[c] - self.desde[c])
            pasos[c] = d
        self.f = max(self.f, min(0.99, hecho / total) if total > 0 else 0.0)
        resto = None
        if activo is not None and self.terminado is None:
            r = self._resto(activo, t) + sum(self.est[c] for c in self.pasos[self.pasos.index(activo) + 1:])
            fin = t + r
            if self._fin is None:
                self._fin = fin
            else:                                    # se acerca a la nueva hora poco a poco (por tiempo, no por linea)
                a = 1.0 - math.exp(-max(0.0, t - self._t_fin) / SUAVE_S)
                self._fin += a * (fin - self._fin)
            self._t_fin = t
            resto = max(0.0, self._fin - t)
        return {"pasos": pasos, "f": self.f, "resto": resto, "ahora": self.ahora, "activo": activo,
                "pasado": t - self.inicio}
