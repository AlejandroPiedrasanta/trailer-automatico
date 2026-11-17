# -*- coding: utf-8 -*-
"""
prueba_arrastre.py - Prueba de punta a punta de «suelta la carpeta y listo», en el programa de verdad (desde el codigo o
instalado, en Windows y en Mac):

  crear_material(carpeta)   un evento de mentira con "de todo": fotos con EXIF de una camara, videos de camara y de celular
                            (hora en los metadatos o en el nombre), tomas de dron, un video vertical, uno en negro, uno
                            cortado, un repetido, un RAW, notas y basura de la Mac. Deja esperado.json con lo que debe salir.
  Guion(ventana, app, carpeta, salida)
                            suelta esa carpeta en la ventana (los mismos eventos de arrastre que manda el sistema), contesta
                            las hojas como una persona y comprueba cada paso: se ordena en FOTOS / VIDEOS / DRON, se organiza
                            por momentos, sale el plan y el armado empieza solo. Deja resultado.txt y capturas.

Como se corre (no toca tu material ni tus datos: todo va a carpetas aparte):
  TrailerAutomatico --tarea material_prueba <carpeta>
  TRAILER_BASE=<trabajo> TRAILER_DATOS=<datos> TRAILER_PRUEBA_ARRASTRE=<carpeta a soltar> TRAILER_PRUEBA_SALIDA=<resultados>
  TRAILER_PRUEBA_ESPERA=davinci  (por defecto: vale llegar a DaVinci o el aviso claro de que no esta)  |  armado
"""
import os
import sys
import json
import time
import random
import shutil
import datetime
import subprocess

import rutas

DIA = datetime.date(2026, 10, 17)
EVENTO = "Boda Ana y José (prueba)"
TONOS = {"MAQUILLAJE": (216, 206, 196), "IGLESIA": (150, 134, 118), "FIESTA": (62, 26, 84)}
HORAS = {"MAQUILLAJE": (11, 0, 100), "IGLESIA": (15, 0, 80), "FIESTA": (18, 40, 270)}      # hora, minuto, minutos que dura
FUENTES = ("testsrc2", "mandelbrot", "smptebars", "rgbtestsrc", "testsrc", "yuvtestsrc")


def _hora(momento, k, n):
    h, m, largo = HORAS[momento]
    return datetime.datetime.combine(DIA, datetime.time(h, m)) + datetime.timedelta(minutes=largo * (k + 0.5) / n)


def _fechar(ruta, dt):
    ts = dt.timestamp()
    os.utime(ruta, (ts, ts))


def _foto(ruta, dt, tono, semilla, vertical=False, exif=True, corrido=0):
    from PIL import Image, ImageDraw
    w, h = (800, 1200) if vertical else (1200, 800)
    im = Image.new("RGB", (w, h), tono)
    d = ImageDraw.Draw(im)
    rnd = random.Random(semilla)
    for _ in range(46):                                    # formas con borde: nitidez y color medibles
        x, y, r = rnd.randrange(w) + corrido, rnd.randrange(h), rnd.randrange(18, 110)
        c = tuple(max(0, min(255, t + rnd.randrange(-70, 70))) for t in tono)
        (d.ellipse if rnd.random() < 0.6 else d.rectangle)((x - r, y - r, x + r, y + r), fill=c, outline=(20, 20, 20))
    if exif:
        ex = im.getexif()
        ex[0x010F], ex[0x0110] = "PRUEBA", "Camara 1"
        ex[306] = dt.strftime("%Y:%m:%d %H:%M:%S")
        try:
            ex.get_ifd(0x8769)[36867] = dt.strftime("%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
        im.save(ruta, quality=88, exif=ex)
    else:
        im.save(ruta)
    _fechar(ruta, dt)


def _video(ruta, dt, fuente, dur=6, tam="640x360", audio=True, meta=None):
    base = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", str(dur), "-i",          # -t: no todas las fuentes tienen «d=»
            ("color=c=black:s=%s:r=30" % tam) if fuente == "negro" else "%s=s=%s:r=30" % (fuente, tam)]
    if audio:
        base += ["-f", "lavfi", "-t", str(dur), "-i", "sine=f=%d" % (220 + 40 * (len(ruta) % 9))]
    cola = []
    for k, v in (meta or {}).items():
        cola += ["-metadata", "%s=%s" % (k, v)]
    if ruta.lower().endswith(".mov"):
        cola += ["-movflags", "use_metadata_tags"]
    ultimo = ""
    for codec in (["-c:v", "libx264", "-preset", "ultrafast"], ["-c:v", "mpeg4", "-q:v", "5"]):
        r = subprocess.run(base + codec + ["-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else [])
                           + cola + [ruta], capture_output=True, text=True, errors="replace", timeout=300,
                           creationflags=rutas.SIN_VENTANA)
        if r.returncode == 0 and os.path.getsize(ruta) > 1000:
            _fechar(ruta, dt + datetime.timedelta(seconds=dur))
            return
        ultimo = r.stderr[-300:]
    raise RuntimeError("ffmpeg no pudo crear %s: %s" % (os.path.basename(ruta), ultimo))


def crear_material(carpeta, log=print):
    """Crea <carpeta>/<EVENTO>/... y <carpeta>/esperado.json. Devuelve la carpeta que hay que soltar."""
    raiz = os.path.join(carpeta, EVENTO)
    if os.path.isdir(raiz):
        shutil.rmtree(raiz)
    sub = {n: os.path.join(raiz, n) for n in ("Fotos cámara", "Video cámara", "Celular", "DRON", "Drone tarde", "otros")}
    for d in list(sub.values()) + [os.path.join(sub["Fotos cámara"], "seleccion")]:
        os.makedirs(d)
    n = 0
    for mom in ("MAQUILLAJE", "IGLESIA", "FIESTA"):        # 24 fotos de camara con su hora en el EXIF
        for k in range(8):
            n += 1
            _foto(os.path.join(sub["Fotos cámara"], "IMG_%04d.JPG" % (1000 + n)), _hora(mom, k, 8), TONOS[mom], n)
    _foto(os.path.join(sub["Fotos cámara"], "IMG_1008b.JPG"), _hora("MAQUILLAJE", 7, 8) + datetime.timedelta(seconds=1),
          TONOS["MAQUILLAJE"], 8, corrido=3)                # rafaga: casi igual a la 1008
    _foto(os.path.join(sub["Fotos cámara"], "IMG_1030.JPG"), _hora("FIESTA", 3, 8), TONOS["FIESTA"], 30, vertical=True)
    _foto(os.path.join(sub["Fotos cámara"], "foto sin exif.png"), _hora("MAQUILLAJE", 5, 8), TONOS["MAQUILLAJE"], 31,
          exif=False)
    shutil.copy2(os.path.join(sub["Fotos cámara"], "IMG_1003.JPG"),
                 os.path.join(sub["Fotos cámara"], "seleccion", "IMG_1003 copia.JPG"))      # el MISMO archivo, otro nombre
    log("fotos listas")
    k = 0
    for mom in ("MAQUILLAJE", "IGLESIA", "FIESTA"):        # 9 videos de camara (hora en los metadatos)
        for j in range(3):
            k += 1
            dt = _hora(mom, j, 3)
            _video(os.path.join(sub["Video cámara"], "C%04d.MP4" % k), dt, FUENTES[k % len(FUENTES)],
                   meta={"creation_time": dt.strftime("%Y-%m-%dT%H:%M:%S")})
    for j, mom in enumerate(("MAQUILLAJE", "IGLESIA", "FIESTA", "FIESTA")):                  # 4 de iPhone
        dt = _hora(mom, j % 3, 3) + datetime.timedelta(minutes=7)
        _video(os.path.join(sub["Celular"], "IMG_%04d.MOV" % (7001 + j)), dt, FUENTES[(j + 2) % len(FUENTES)],
               meta={"com.apple.quicktime.creationdate": dt.strftime("%Y-%m-%dT%H:%M:%S") + "-0600",
                     "com.apple.quicktime.model": "iPhone 15"})
    _video(os.path.join(sub["Celular"], "VID_20261017_193000.mp4"), datetime.datetime.combine(DIA, datetime.time(19, 30)),
           "testsrc2", tam="360x640")                       # celular parado (vertical), hora en el nombre
    _video(os.path.join(sub["Celular"], "Vals 💃 de José.mp4"), datetime.datetime.combine(DIA, datetime.time(20, 15)),
           "mandelbrot")
    _video(os.path.join(sub["DRON"], "DJI_20261017153000_0001_D.MP4"), datetime.datetime.combine(DIA, datetime.time(15, 30)),
           "smptebars", audio=False)
    _video(os.path.join(sub["DRON"], "DJI_20261017190000_0002_D.MP4"), datetime.datetime.combine(DIA, datetime.time(19, 0)),
           "rgbtestsrc", audio=False)
    _video(os.path.join(sub["Drone tarde"], "toma aerea.mp4"), datetime.datetime.combine(DIA, datetime.time(17, 50)),
           "testsrc", audio=False)                          # dron por el nombre de la carpeta
    _video(os.path.join(sub["otros"], "todo_negro.mp4"), datetime.datetime.combine(DIA, datetime.time(16, 0)), "negro",
           audio=False)
    with open(os.path.join(sub["Video cámara"], "C0001.MP4"), "rb") as f:
        datos = f.read()
    with open(os.path.join(sub["otros"], "cortado.mp4"), "wb") as f:                          # copia interrumpida
        f.write(datos[:len(datos) // 3])
    open(os.path.join(sub["otros"], "vacio.mp4"), "wb").close()
    with open(os.path.join(sub["otros"], "DSC_0001.NEF"), "wb") as f:
        f.write(os.urandom(4000))
    with open(os.path.join(sub["otros"], "notas.txt"), "w", encoding="utf-8") as f:
        f.write("Entrada 4 pm, vals 8 pm")
    with open(os.path.join(sub["Fotos cámara"], "._IMG_1001.JPG"), "wb") as f:                # basura de la Mac
        f.write(b"\x00\x05\x16\x07" + b"\x00" * 300)
    with open(os.path.join(sub["Fotos cámara"], "Thumbs.db"), "wb") as f:
        f.write(b"x" * 200)
    # (1.5.7) la carpeta se usa donde esta: 27 JPG (con la copia repetida; la PNG no cuenta), 17 videos (con el cortado y el
    # negro; el vacio no), 3 de dron
    esperado = {"fecha": DIA.isoformat(), "foto": 27, "video": 17, "dron": 3, "ya_estaban": 1,
                "otros": {".nef": 1, ".txt": 1, "vacíos": 1}, "dañados": ["cortado.mp4"], "negro": "todo_negro.mp4",
                "vertical": "VID_20261017_193000.mp4"}
    with open(os.path.join(carpeta, "esperado.json"), "w", encoding="utf-8") as f:
        json.dump(esperado, f, ensure_ascii=False, indent=1)
    log("material de prueba en %s" % raiz)
    return raiz


class Guion:
    """Maneja la ventana de verdad como una persona: arrastra, suelta, contesta y mira que cada paso pase."""
    def __init__(self, ventana, app, carpeta, salida):
        from PySide6.QtCore import QTimer
        self.w, self.app, self.carpeta, self.salida = ventana, app, carpeta, salida
        self._archivos_antes = sum(len(fs) for _, _, fs in os.walk(carpeta))     # al final: no se borro nada
        os.makedirs(salida, exist_ok=True)
        self.lineas, self.mal = [], 0
        self.etapa, self.t0, self.t_etapa = "inicio", time.time(), time.time()
        try:
            with open(os.path.join(os.path.dirname(carpeta.rstrip("\\/")), "esperado.json"), encoding="utf-8") as f:
                self.esperado = json.load(f)
        except Exception:
            self.esperado = {}
        self.espera = os.environ.get("TRAILER_PRUEBA_ESPERA", "davinci")
        self.reloj = QTimer(ventana)
        self.reloj.timeout.connect(self._tic)
        QTimer.singleShot(3500, self._arrastrar)

    # ---- utilidades
    def ok(self, texto):
        self._linea("OK     " + texto)

    def falla(self, texto):
        self.mal = 1
        self._linea("FALLA  " + texto)

    def _linea(self, t):
        self.lineas.append(t)
        try:
            print(t, flush=True)
        except Exception:
            pass
        with open(os.path.join(self.salida, "resultado.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(self.lineas) + "\n")

    def foto(self, nombre):
        try:
            self.w.grab().save(os.path.join(self.salida, nombre + ".png"))
        except Exception:
            pass

    def _pasar(self, etapa):
        self.etapa, self.t_etapa = etapa, time.time()

    # ---- arrastrar y soltar (los mismos eventos que manda el sistema al arrastrar desde el Explorador o el Finder)
    def _arrastrar(self):
        from PySide6.QtCore import QMimeData, QUrl, Qt, QTimer
        from PySide6.QtGui import QDragEnterEvent
        from PySide6.QtWidgets import QApplication
        self.foto("1_inicio")
        os_ = "%s %s" % (sys.platform, "instalado" if rutas.CONGELADO else "codigo")
        self._linea("equipo: %s · version %s · carpeta de trabajo %s" % (os_, rutas.version(), rutas.BASE))
        self.ok("la ventana abrio")
        self.mime = QMimeData()
        self.mime.setUrls([QUrl.fromLocalFile(self.carpeta)])
        self.pos = self.w.rect().center()
        entra = QDragEnterEvent(self.pos, Qt.CopyAction, self.mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self.w, entra)
        if entra.isAccepted() and self.w.hoja.isVisible() and self.w.hoja.modo == "soltar":
            self.ok("al arrastrar la carpeta sobre la ventana aparece «Suelta aquí»")
        else:
            self.falla("la ventana no acepto el arrastre (aceptado=%s, hoja=%s)" % (entra.isAccepted(), self.w.hoja.modo))
        QTimer.singleShot(700, self._soltar)

    def _soltar(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication
        self.foto("2_arrastrando")
        suelta = QDropEvent(QPointF(self.pos), Qt.CopyAction, self.mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self.w, suelta)
        if self.w.flujo is not None:
            self.ok("al soltar empieza solo (mira lo que hay)")
        else:
            self.falla("al soltar no paso nada")
        self._pasar("copia")
        self.reloj.start(300)

    # ---- lo que va pasando
    def _tic(self):
        w = self.w
        if time.time() - self.t_etapa > float(os.environ.get("TRAILER_PRUEBA_TOPE", 600)):
            self.falla("tiempo agotado en la etapa «%s»" % self.etapa)
            return self._terminar()
        try:
            getattr(self, "_etapa_" + self.etapa)(w)
        except Exception:
            import traceback
            self.falla("error del guion en «%s»: %s" % (self.etapa, traceback.format_exc()[-400:]))
            self._terminar()

    def _etapa_copia(self, w):
        if w.flujo == "pregunta" and w.hoja.modo == "pregunta":      # habia material de otro evento
            self.foto("3_evento_nuevo")
            self.ok("pregunta si es un evento nuevo (habia material de otro dia)")
            w.hoja.botones[0].click()
            return
        if w.flujo == "copiando" and not getattr(self, "_vio_copia", False):
            self._vio_copia = True
            self.foto("3_copiando")
        if w.flujo in ("datos", "cuenta") or (w.flujo is None and w.copia is None and w.trabajo is None):
            self._revisar_copia(w)
            if w.flujo == "datos":
                self.foto("4_datos_del_evento")
                self.ok("pide el tipo de evento y los nombres")
                c, e = w._form
                c.setCurrentIndex(max(0, c.findData("boda")))
                e.setText("Ana & José")
                w.hoja.botones[0].click()
            elif w.flujo == "cuenta":
                self.foto("4_cuenta_atras")
                self.ok("cuenta atras para armar solo")
                w.hoja.botones[0].click()
            else:
                self.falla("despues de copiar no ofrecio armar: %s" % w.aviso_t.text())
                return self._terminar()
            self._pasar("armado")

    def _revisar_copia(self, w):
        """(1.5.7) La carpeta soltada se usa DONDE ESTA: nada se copia a 1 MATERIAL; solo cuentan las fotos JPG."""
        import analizar_material as am
        e = self.esperado
        lista = am.listar(rutas.BASE)
        hay = {t: sum(1 for x, _ in lista if x == t) for t in ("foto", "video", "dron")}
        if e and rutas.fuentes() and all(hay[t] == e[t] for t in ("foto", "video", "dron")):
            self.ok("tomado en su carpeta, sin copiar: %d fotos JPG, %d videos, %d dron" % (hay["foto"], hay["video"], hay["dron"]))
        else:
            self.falla("material distinto de lo esperado: %s (esperado %s, carpetas %s)" % (
                hay, {t: e.get(t) for t in hay}, rutas.fuentes()))
        copiados = [f for d in rutas.CARPETAS.values() if os.path.isdir(d) for f in os.listdir(d)]
        (self.ok if not copiados else self.falla)("no se copio nada a 1 MATERIAL" if not copiados
                                                  else "se copio a 1 MATERIAL: %s" % copiados[:5])
        nombres = [os.path.basename(r) for _, r in lista]
        if not any(n.lower().endswith((".png", ".nef")) for n in nombres):
            self.ok("solo fotos JPG: la PNG y el RAW no se toman en cuenta")
        else:
            self.falla("se tomo en cuenta una foto que no es JPG")
        if any("💃" in n for n in nombres) and any(t == "dron" and os.path.basename(r) == "toma aerea.mp4" for t, r in lista):
            self.ok("nombres con acentos y emoji, y el dron reconocido por su carpeta")
        else:
            self.falla("falta el video con emoji o el dron de la carpeta «Drone tarde»")

    def _etapa_armado(self, w):
        if w.trabajo is None and w._ultimo_fallo is None and not w.resultado:
            return
        self.ok("el armado empezo solo")
        self.foto("5_armando")
        self._pasar("analisis")

    def _etapa_analisis(self, w):
        ruta = os.path.join(rutas.ANALISIS, "material.json")
        plan = os.path.join(rutas.ANALISIS, "plan_previo.json")
        termino = w.trabajo is None
        if not os.path.exists(plan) and not termino:
            return
        try:
            with open(ruta, encoding="utf-8") as f:
                j = json.load(f)
        except Exception as ex:
            self.falla("no hay analisis del material (%s) · %s" % (ex, w._ultimo_fallo))
            return self._terminar()
        items = j.get("items") or []
        por = {}
        for i in items:
            por.setdefault(i.get("momento"), {"foto": 0, "video": 0, "dron": 0})[i["tipo"]] += 1
        bien = j.get("fecha") == self.esperado.get("fecha") and all(
            por.get(m, {}).get("foto", 0) >= 6 and por.get(m, {}).get("video", 0) + por.get(m, {}).get("dron", 0) >= 3
            for m in ("MAQUILLAJE", "IGLESIA", "FIESTA"))
        txt = " · ".join("%s %d fotos %d videos" % (m.lower(), por.get(m, {}).get("foto", 0),
                                                    por.get(m, {}).get("video", 0) + por.get(m, {}).get("dron", 0))
                         for m in ("MAQUILLAJE", "IGLESIA", "FIESTA"))
        (self.ok if bien else self.falla)("organizado por momentos (%s): %s" % (j.get("fecha"), txt))
        nombres = {i["nombre"]: i for i in items}
        # (1.5.7) los archivos se renombraron en su carpeta: «VIDEO HORIZONTAL 001 (CEREMONIA).MP4»...
        renombres = {}
        try:
            with open(os.path.join(rutas.ANALISIS, "nombres.json"), encoding="utf-8") as f:
                for vez in json.load(f):
                    for a, b in vez["cambios"]:
                        renombres[os.path.basename(a)] = os.path.basename(b)
        except Exception:
            pass
        for viejo, nuevo in renombres.items():
            if nuevo in nombres:
                nombres.setdefault(viejo, nombres[nuevo])
        import re
        bien_nombre = [n for n in renombres.values() if re.match(
            r"^(FOTO|DRON|VIDEO (VERTICAL|HORIZONTAL)) \d{3} \((MAQUILLAJE|CEREMONIA|FIESTA)\)\.\w+$", n)]
        if renombres and len(bien_nombre) == len(renombres):
            self.ok("renombrados en su carpeta con tipo y momento: %d (p. ej. «%s»)" % (len(renombres), sorted(bien_nombre)[0]))
        else:
            self.falla("renombrado: %d de %d con el nombre esperado" % (len(bien_nombre), len(renombres)))
        ahora = sum(len(fs) for _, _, fs in os.walk(self.carpeta))
        if ahora == getattr(self, "_archivos_antes", ahora):
            self.ok("no se borro ningun archivo de la carpeta del evento (%d)" % ahora)
        else:
            self.falla("la carpeta del evento tenia %d archivos y ahora %d" % (self._archivos_antes, ahora))
        avisos = " ".join(j.get("avisos") or [])
        if "cortado.mp4" not in nombres and "cortado.mp4" in avisos:
            self.ok("el video cortado se aparto con aviso")
        else:
            self.falla("el video cortado no se aparto (avisos: %s)" % avisos[:160])
        negro = nombres.get(self.esperado.get("negro"), {})
        if negro.get("oscuros"):
            self.ok("el video en negro quedo marcado para no usarse")
        else:
            self.falla("el video en negro no se detecto")
        if sum(1 for i in items if i["tipo"] == "dron") == self.esperado.get("dron"):
            self.ok("las %d tomas de dron reconocidas" % self.esperado.get("dron", 0))
        else:
            self.falla("tomas de dron: %d" % sum(1 for i in items if i["tipo"] == "dron"))
        try:
            with open(plan, encoding="utf-8") as f:
                p = json.load(f)
            v1 = next(v for v in p["versiones"] if rutas.etiqueta_de(v["timeline"]) == "1min")
            zonas = {n: z["videos"] for n, z in v1["zonas"].items()}
            if all(zonas.get(n, 0) > 0 for n in ("APERTURA", "MAQUILLAJE", "IGLESIA", "FIESTA")) and v1["fotos_intro"] == 8:
                self.ok("plan de las plantillas (%s): 8 fotos de intro y planos %s" % (
                    p.get("evento"), ", ".join("%s %d" % (n.lower(), c) for n, c in zonas.items())))
            else:
                self.falla("plan incompleto: %s" % zonas)
            if len(p["versiones"]) == 4:
                self.ok("plan de las 4 plantillas (1, 3, 15 y 30 min)")
        except Exception as ex:
            self.falla("no salio el plan de las plantillas (%s)" % ex)
        try:                                    # formato vertical (9:16): solo acepta videos grabados en vertical
            import motor
            vert = nombres.get(self.esperado.get("vertical")) or {}
            dicho = []
            rep = motor.plan_previo(j, lambda m: dicho.append(str(m)), formato="vertical")
            if vert and not vert.get("horizontal", True) and not (rep or {}).get("versiones") \
                    and "vertical" in " ".join(dicho).lower():
                self.ok("formato vertical: reconoce el video vertical y avisa que con ese solo no alcanza")
            else:
                self.falla("formato vertical: %s | %s" % (vert.get("horizontal"), " ".join(dicho)[:160]))
            for i in items:                     # y con todo el video en vertical, arma las mismas duraciones
                if i["tipo"] == "video":
                    i["horizontal"] = False
            rep = motor.plan_previo(j, lambda m: None, formato="vertical")
            lineas = [v["timeline"] for v in (rep or {}).get("versiones", [])]
            if lineas and all(rutas.etiqueta_de(t).startswith("VERTICAL ") for t in lineas):
                self.ok("formato vertical: con videos verticales planifica %s" % ", ".join(
                    rutas.etiqueta_de(t) for t in lineas))
            else:
                self.falla("formato vertical: no planifico (%s)" % lineas)
        except Exception as ex:
            self.falla("formato vertical: no se pudo probar (%s)" % ex)
        self._pasar("final")

    def _etapa_final(self, w):
        if w.trabajo is not None:
            if not getattr(self, "_vio_material", False) and time.time() - self.t_etapa > 2:
                self._vio_material = True
            return
        w._ir("Material")
        from PySide6.QtCore import QTimer
        self.reloj.stop()
        QTimer.singleShot(2500, self._cierre)

    def _cierre(self):
        w = self.w
        self.foto("6_material_organizado")
        if w.linea.items and len(w.linea.items) >= 40:
            self.ok("la pestaña Material muestra el dia organizado (%d archivos)" % len(w.linea.items))
        else:
            self.falla("la pestaña Material no muestra la organizacion (%d)" % len(w.linea.items or []))
        w._ir("Inicio")
        fallo = w._ultimo_fallo
        if fallo is None:
            self.ok("armado en DaVinci: %s" % (w.resultado or {}).get("evento"))
            incompleta = [x for x in w.registro.toPlainText().splitlines() if "se pidieron" in x]
            if incompleta:                          # p. ej. las fotos de la intro no entraron (secuencia de imagenes)
                self.falla("la linea quedo incompleta: %s" % incompleta[0][:200])
            elif self.espera == "armado":
                self.ok("todos los clips pedidos quedaron en la linea (las fotos de la intro incluidas)")
        elif "DaVinci" in fallo and self.espera != "armado":
            self.ok("sin DaVinci en este equipo, lo dice claro: «%s»" % fallo[:110])
        else:
            self.falla("el armado fallo: %s" % fallo[:300])
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self._terminar)

    def _terminar(self):
        self.reloj.stop()
        self.foto("7_final")
        self._linea("%s en %.0f s" % ("TODO BIEN" if not self.mal else "CON FALLAS", time.time() - self.t0))
        try:
            import registro
            registro.info("Prueba de arrastre: %s" % ("bien" if not self.mal else "con fallas"))
        except Exception:
            pass
        sys.stdout.flush()
        if os.name == "nt":                         # sin descargar las DLL (os._exit con hilos de Qt vivos da un fallo al salir)
            import ctypes
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = ctypes.c_void_p
            k.TerminateProcess(ctypes.c_void_p(k.GetCurrentProcess()), self.mal)
        os._exit(self.mal)
