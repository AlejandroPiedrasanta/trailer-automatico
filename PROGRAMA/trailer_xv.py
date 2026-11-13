# -*- coding: utf-8 -*-
"""
trailer_xv.py - "Un clic y listo": trailer automatico de CINEMA PRODUCTIONS (Windows y Mac, Qt6 / PySide6, local).

El boton del centro (▶) hace todo:
  1. revisa que 1 MATERIAL tenga fotos y videos (si falta algo, lo pide),
  2. analiza y clasifica el material (maquillaje, iglesia, fiesta),
  3. lo arma en las plantillas elegidas abajo (1, 3, 15 y/o 30 min) en DaVinci Resolve,
  4. renderiza, deja el audio a -14 LUFS, mide la imagen y abre 2 VIDEOS TERMINADOS.
Se pueden arrastrar fotos, videos o carpetas a la ventana: se copian solos a FOTOS, VIDEOS o DRON.

Uso:  doble clic en "ARMAR TRAILERS" (.bat en Windows, .command en Mac)
      python trailer_xv.py --todo        (sin ventana: arma y renderiza)
      python trailer_xv.py --una-vez     (sin ventana: solo arma en DaVinci)
      python trailer_xv.py --seco        (solo el plan, no toca DaVinci)
"""
import os
import sys
import math
import time
import random
import traceback

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
import rutas  # noqa: E402
import registro  # noqa: E402
import motor  # noqa: E402

TITULO_APP = "Tráiler automático"
TIPOS = [("xv", "XV años"), ("boda", "Boda"), ("bautizo", "Bautizo"), ("graduacion", "Graduación"),
         ("cumpleanos", "Cumpleaños")]
VERSION_TEXTO = {"1min": "1 min", "3min": "3 min", "15min": "15 min", "30min": "30 min"}
# Las fases del boton GO (las claves son las de la escena de CineCaptions: cada una enciende una pieza del astrolabio)
PASOS_GO = [("timeline", "Revisar material"), ("voz", "Abrir DaVinci"), ("ia", "Plan y ritmo"),
            ("diseno", "Armar versiones"), ("sfx", "Renderizar"), ("resolve", "Audio final")]
PESO_GO = [("timeline", 0.04), ("voz", 0.08), ("ia", 0.05), ("diseno", 0.27), ("sfx", 0.51), ("resolve", 0.05)]


def opciones_guardadas():
    est = motor.leer_estado()
    return dict(evento=est.get("evento_manual", ""), nombre_xv=est.get("nombre_xv", ""),
                fecha_lugar=est.get("fecha_lugar", ""), frase=est.get("frase", ""),
                tipo_evento=est.get("tipo_evento", "xv"), ruido=est.get("ruido"),
                igualar=est.get("igualar", True), solo=est.get("versiones") or None)


# ================================================================== sin ventana
def cli(args):
    def log(m):
        print(time.strftime("%H:%M:%S  ") + str(m), flush=True)
        registro.info(m)
    rutas.crear_carpetas()
    m = motor.revisar_material()
    if not m["ok"] and "--seco" not in args:
        log("Falta material: %s" % ", ".join("%d en %s" % (n, motor.NOMBRE_CARPETA[t]) for t, n in m["faltan"]))
        sys.exit(2)
    op = opciones_guardadas()
    if "--todo" in args:
        res = motor.armar_todo(log, **op)
        log("Videos en: %s" % res["carpeta"])
    else:
        motor.armar(log, seco="--seco" in args, **op)


# ================================================================== ventana
def app():
    from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QPointF, QRectF, QFileSystemWatcher, QVariantAnimation,
                                QEasingCurve, QEvent, QLockFile)
    from PySide6.QtGui import (QColor, QIcon, QPainter, QPixmap, QPolygonF, QPen, QBrush, QFont, QPainterPath,
                               QRadialGradient, QLinearGradient, QConicalGradient)
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                                   QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                                   QPushButton, QSizeGrip, QSlider, QStackedWidget, QVBoxLayout, QWidget,
                                   QButtonGroup)

    ORO, ORO_CLARO, ORO_OSCURO = QColor("#C9A267"), QColor("#EBCB8F"), QColor("#6E4C24")
    ESMERALDA, ESMERALDA_CLARO, ESMERALDA_OSCURO = QColor("#22C47E"), QColor("#7CF2C0"), QColor("#06301F")
    TEXTO, TENUE, AMBAR, ROJO = "#EAF2F0", "#8FA3A8", "#F2B84B", "#F07A6A"
    FUENTE = '"Segoe UI Variable Display", "Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial"'

    QSS = """
    QWidget { color: %(t)s; font-family: %(f)s; font-size: 14px; }
    QLabel { background: transparent; }
    QFrame#nav { background: rgba(14, 30, 38, 0.82); border: 1px solid rgba(201, 162, 103, 0.28);
                 border-radius: 24px; }
    QPushButton#tab { background: transparent; border: 1px solid transparent; border-radius: 16px; padding: 8px 18px;
                      color: %(m)s; font-weight: 600; }
    QPushButton#tab:hover { color: %(t)s; background: rgba(255,255,255,0.05); }
    QPushButton#tab:checked { background: #22C47E; color: #04150D; }
    QPushButton#icono { background: rgba(14, 30, 38, 0.82); border: 1px solid rgba(34,196,126,0.45);
                        border-radius: 12px; font-size: 16px; padding: 0; }
    QPushButton#icono:hover, QPushButton#icono:checked { background: rgba(34,196,126,0.18); }
    QFrame#ventanita { background: rgba(14, 30, 38, 0.82); border: 1px solid rgba(255,255,255,0.06);
                       border-radius: 18px; }
    QPushButton#ctrl { background: transparent; border: 1px solid transparent; border-radius: 10px; font-size: 14px;
                       color: %(m)s; padding: 0; }
    QPushButton#ctrl:hover { background: rgba(255,255,255,0.08); color: %(t)s; }
    QPushButton#cerrar:hover { background: #C42B1C; color: white; }
    QPushButton#cerrar { background: transparent; border: 1px solid transparent; border-radius: 10px; color: %(m)s; padding: 0; }
    QFrame#aviso { border-radius: 10px; border: 1px solid rgba(34,196,126,0.40); background: rgba(10, 40, 30, 0.72); }
    QFrame#aviso[tipo="warn"] { border-color: rgba(242,184,75,0.55); background: rgba(48, 36, 10, 0.78); }
    QFrame#aviso[tipo="error"] { border-color: rgba(240,122,106,0.6); background: rgba(52, 18, 16, 0.78); }
    QLabel#aviso_i { background: #22C47E; color: #04150D; border-radius: 9px; font-weight: 800; font-size: 11px; }
    QLabel#aviso_i[tipo="warn"] { background: #F2B84B; }
    QLabel#aviso_i[tipo="error"] { background: #F07A6A; }
    QLabel#hora { color: %(m)s; }
    QLabel#titulo { font-size: 40px; font-weight: 800; letter-spacing: 0.5px; }
    QLabel#sub { color: #F2B84B; font-weight: 600; font-size: 15px; }
    QLabel#sub[tipo="ok"] { color: #7CF2C0; }
    QLabel#sub[tipo="error"] { color: #F07A6A; }
    QPushButton#pill { background: rgba(14, 30, 38, 0.80); border: 1px solid rgba(255,255,255,0.14);
                       border-radius: 16px; padding: 9px 20px; font-weight: 700; color: %(m)s; }
    QPushButton#pill:hover { color: %(t)s; border-color: #22C47E; }
    QPushButton#pill:checked { background: rgba(34,196,126,0.30); color: #B9FFE0; border-color: #22C47E; }
    QPushButton#pill:disabled { color: rgba(143,163,168,0.5); }
    QPushButton#chip { background: rgba(14, 30, 38, 0.80); border: 1px solid rgba(201,162,103,0.45);
                       border-radius: 14px; padding: 7px 16px; color: #EBCB8F; font-weight: 600; }
    QPushButton#chip:hover { background: rgba(201,162,103,0.15); }
    QFrame#vidrio { background: rgba(12, 26, 34, 0.80); border: 1px solid rgba(201,162,103,0.25);
                    border-radius: 18px; }
    QFrame#carpeta { background: rgba(12, 26, 34, 0.80); border: 1px solid rgba(34,196,126,0.35);
                     border-radius: 18px; }
    QFrame#carpeta[estado="falta"] { border-color: rgba(242,184,75,0.75); }
    QFrame#soltar { border: 2px dashed rgba(34,196,126,0.45); border-radius: 18px; background: rgba(8, 24, 28, 0.55); }
    QLabel#grande { font-size: 34px; font-weight: 800; }
    QLabel#etq { color: %(m)s; font-weight: 600; letter-spacing: 1px; font-size: 12px; }
    QLabel#estado_c { color: #7CF2C0; font-weight: 600; }
    QLabel#estado_c[estado="falta"] { color: #F2B84B; }
    QPushButton#boton { background: #22C47E; color: #04150D; border: 1px solid #22C47E; border-radius: 10px; padding: 9px 16px;
                        font-weight: 700; }
    QPushButton#boton:hover { background: #45E3A0; }
    QPushButton#borde { background: transparent; border: 1px solid rgba(255,255,255,0.14); border-radius: 10px;
                        padding: 9px 16px; font-weight: 600; }
    QPushButton#borde:hover { background: rgba(255,255,255,0.06); }
    QLineEdit, QComboBox { background: rgba(4, 14, 20, 0.85); border: 1px solid rgba(255,255,255,0.12);
                           border-radius: 10px; padding: 10px 12px; font-weight: 600; }
    QLineEdit:focus, QComboBox:focus { border-color: #22C47E; }
    QComboBox::drop-down { border: none; width: 26px; }
    QComboBox QAbstractItemView { background: #0E1E26; border: 1px solid rgba(255,255,255,0.12); outline: none;
                                  selection-background-color: rgba(34,196,126,0.25); selection-color: %(t)s; }
    QCheckBox { spacing: 10px; }
    QCheckBox::indicator { width: 20px; height: 20px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);
                           background: rgba(4,14,20,0.85); }
    QCheckBox::indicator:checked { background: #22C47E; border-color: #22C47E; }
    QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.10); border-radius: 3px; }
    QSlider::sub-page:horizontal { background: #22C47E; border-radius: 3px; }
    QSlider::handle:horizontal { background: white; border: 2px solid #22C47E; width: 14px; margin: -6px 0;
                                 border-radius: 9px; }
    QPlainTextEdit { background: rgba(4, 12, 18, 0.88); border: 1px solid rgba(255,255,255,0.08);
                     border-radius: 14px; padding: 8px; font-family: "Cascadia Mono", "Consolas", "Menlo", monospace;
                     font-size: 12px; color: #B8C7CB; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 4px; min-height: 24px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QToolTip { background: #0E1E26; color: %(t)s; border: 1px solid rgba(255,255,255,0.12); padding: 6px 8px; }
    """ % {"t": TEXTO, "m": TENUE, "f": FUENTE}

    # ------------------------------------------------------------------ trabajos en segundo plano
    class Trabajo(QThread):
        linea = Signal(str)
        avance = Signal(int, str)
        fin = Signal(object)
        fallo = Signal(str)

        def __init__(self, op):
            super().__init__()
            self.op = op

        def run(self):
            try:
                res = motor.armar_todo(lambda m: self.linea.emit(str(m)),
                                       lambda p, t: self.avance.emit(int(p), str(t)), **self.op)
                self.fin.emit(res)
            except Exception as ex:
                self.linea.emit(traceback.format_exc())
                self.fallo.emit(str(ex))

    class Copia(QThread):
        avance = Signal(int, int, str)
        fin = Signal(object)

        def __init__(self, archivos, tipo=None):
            super().__init__()
            self.archivos, self.tipo = archivos, tipo

        def run(self):
            try:
                self.fin.emit(motor.copiar_material(self.archivos, lambda i, n, f: self.avance.emit(i, n, f),
                                                    self.tipo))
            except Exception as ex:
                self.fin.emit({"error": str(ex)})

    class Chequeo(QThread):
        fin = Signal(object)

        def run(self):
            try:
                self.fin.emit(motor.chequeo())
            except Exception as ex:
                self.fin.emit([("Chequeo", False, str(ex))])

    class EstadoDV(QThread):                     # pregunta a DaVinci sin congelar la ventana
        fin = Signal(object)

        def run(self):
            try:
                self.fin.emit(motor.estado_davinci())
            except Exception:
                self.fin.emit((False, ""))

    # ------------------------------------------------------------------ fondo: cielo con estrellas
    class Cielo(QWidget):
        def __init__(self):
            super().__init__()
            rnd = random.Random(7)
            self.estrellas = [(rnd.random(), rnd.random(), rnd.choice((0.6, 0.8, 1.0, 1.0, 1.4, 1.8)),
                               rnd.random() * 6.28, 0.6 + rnd.random() * 1.6) for _ in range(260)]
            self.constelaciones = [[(0.06, 0.20), (0.15, 0.13), (0.22, 0.16), (0.30, 0.10)],
                                   [(0.07, 0.62), (0.12, 0.70), (0.20, 0.66), (0.24, 0.80), (0.14, 0.86)],
                                   [(0.78, 0.66), (0.84, 0.60), (0.91, 0.64), (0.88, 0.76), (0.95, 0.80)],
                                   [(0.80, 0.18), (0.86, 0.12), (0.93, 0.22)]]
            self.t = 0.0
            reloj = QTimer(self)
            reloj.timeout.connect(self._tic)
            reloj.start(70)

        def _tic(self):
            self.t += 0.07
            self.update()

        def pausar(self, si):                   # bajo la escena de Inicio no hace falta animarlo
            r = self.findChild(QTimer)
            if r is not None:
                r.stop() if si else r.start(70)

        def resizeEvent(self, e):
            super().resizeEvent(e)
            if getattr(self, "al_cambiar", None):
                self.al_cambiar()

        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            g = QRadialGradient(QPointF(w * 0.5, h * 0.45), max(w, h) * 0.75)
            g.setColorAt(0.0, QColor("#12303A"))
            g.setColorAt(0.45, QColor("#0B1C26"))
            g.setColorAt(1.0, QColor("#050C13"))
            p.fillRect(self.rect(), g)
            neb = QRadialGradient(QPointF(w * 0.82, h * 0.30), w * 0.35)
            neb.setColorAt(0.0, QColor(40, 90, 110, 40))
            neb.setColorAt(1.0, QColor(40, 90, 110, 0))
            p.fillRect(self.rect(), neb)
            p.setPen(QPen(QColor(150, 190, 200, 45), 1))
            for linea in self.constelaciones:
                pts = [QPointF(x * w, y * h) for x, y in linea]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
                p.setBrush(QColor(200, 230, 235, 150))
                for q in pts:
                    p.drawEllipse(q, 1.8, 1.8)
            p.setPen(Qt.NoPen)
            for x, y, r, fase, vel in self.estrellas:
                a = 70 + 110 * (0.5 + 0.5 * math.sin(self.t * vel + fase))
                p.setBrush(QColor(220, 240, 245, int(a)))
                p.drawEllipse(QPointF(x * w, y * h), r * 0.6, r * 0.6)

    def icono_app():
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(ORO)
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 60, 60)
        p.setBrush(QColor("#0E7A4E"))
        p.drawEllipse(10, 10, 44, 44)
        p.setBrush(QColor("#E9FFF5"))
        p.drawPolygon(QPolygonF([QPointF(26, 20), QPointF(45, 32), QPointF(26, 44)]))
        p.end()
        return QIcon(pm)

    def repulir(w, **props):
        for k, v in props.items():
            w.setProperty(k, v)
        w.style().unpolish(w)
        w.style().polish(w)

    # ------------------------------------------------------------------ ventana
    class Ventana(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            self.setWindowTitle(TITULO_APP)
            self.setWindowIcon(icono_app())
            self.setAcceptDrops(True)
            self.setMinimumSize(980, 720)
            self.resize(1240, 860)
            self.trabajo = self.copia = self.cheq = None
            self.resultado = None
            self.material = {"ok": False, "cuenta": {"foto": 0, "video": 0, "dron": 0}, "faltan": []}
            self.est = motor.leer_estado()

            fondo = QVBoxLayout(self)
            fondo.setContentsMargins(0, 0, 0, 0)
            self.cielo = Cielo()
            fondo.addWidget(self.cielo)
            raiz = QVBoxLayout(self.cielo)
            raiz.setContentsMargins(22, 18, 22, 14)
            raiz.setSpacing(12)

            # --- barra superior
            barra = QHBoxLayout()
            marca = QLabel("<span style='font-size:26px; font-weight:900; letter-spacing:1px; color:#FFFFFF;'>"
                           "CINEMA</span><span style='font-size:15px; font-weight:800; color:#EAF2F0;'>"
                           " PRODUCTIONS</span>")
            barra.addWidget(marca)
            barra.addStretch(1)
            nav = QFrame(objectName="nav")
            hn = QHBoxLayout(nav)
            hn.setContentsMargins(6, 6, 6, 6)
            hn.setSpacing(2)
            self.grupo_tabs = QButtonGroup(self)
            self.tabs = {}
            for i, txt in enumerate(("Inicio", "Material", "Textos", "Ajustes")):
                b = QPushButton(txt, objectName="tab", checkable=True)
                b.setCursor(Qt.PointingHandCursor)
                self.grupo_tabs.addButton(b, i)
                self.tabs[txt] = b
                hn.addWidget(b)
            self.tabs["Inicio"].setChecked(True)
            self.punto = QLabel("●")
            self.punto.setStyleSheet("color:%s; font-size:16px; padding: 0 10px;" % TENUE)
            self.punto.setToolTip("DaVinci Resolve")
            hn.addWidget(self.punto)
            barra.addWidget(nav)
            barra.addStretch(1)
            self.b_log = QPushButton("☰", objectName="icono", checkable=True)
            self.b_log.setFixedSize(44, 44)
            self.b_log.setToolTip("Ver lo que va haciendo")
            barra.addWidget(self.b_log)
            barra.addSpacing(10)
            ctrls = QFrame(objectName="ventanita")
            hc = QHBoxLayout(ctrls)
            hc.setContentsMargins(6, 4, 6, 4)
            for txt, nombre, acc in (("—", "ctrl", self.showMinimized), ("□", "ctrl", self._maximizar),
                                     ("✕", "cerrar", self.close)):
                b = QPushButton(txt, objectName=nombre)
                b.setFixedSize(38, 30)
                b.clicked.connect(acc)
                hc.addWidget(b)
            barra.addWidget(ctrls)
            raiz.addLayout(barra)

            # --- aviso
            self.aviso = QFrame(objectName="aviso")
            ha = QHBoxLayout(self.aviso)
            ha.setContentsMargins(12, 8, 14, 8)
            self.aviso_i = QLabel("i", objectName="aviso_i")
            self.aviso_i.setFixedSize(18, 18)
            self.aviso_i.setAlignment(Qt.AlignCenter)
            self.aviso_t = QLabel("Revisando…")
            self.aviso_h = QLabel(time.strftime("%H:%M:%S"), objectName="hora")
            ha.addWidget(self.aviso_i)
            ha.addWidget(self.aviso_t, 1)
            ha.addWidget(self.aviso_h)
            raiz.addWidget(self.aviso)

            # --- paginas + registro
            medio = QHBoxLayout()
            self.paginas = QStackedWidget()
            medio.addWidget(self.paginas, 1)
            self.registro = QPlainTextEdit(readOnly=True)
            self.registro.setFixedWidth(400)
            self.registro.hide()
            medio.addWidget(self.registro)
            raiz.addLayout(medio, 1)
            self.paginas.addWidget(self._pagina_inicio())
            self.paginas.addWidget(self._pagina_material())
            self.paginas.addWidget(self._pagina_textos())
            self.paginas.addWidget(self._pagina_ajustes())
            self.grupo_tabs.idClicked.connect(self.paginas.setCurrentIndex)
            import escena_go                         # la escena de Inicio de CineCaptions (esfera de particulas)
            self.escena = escena_go.EscenaGo(self.cielo)
            self.escena.lower()
            self.escena.poner_pasos(PASOS_GO)
            self.escena.proveedor = self._geo_escena
            self.escena.datos_barra = self._datos_barra
            self.escena.etiquetas_ocultas.connect(self._quitar_reserva)
            self.boton.seguir_a(self.escena)
            self.cielo.al_cambiar = self._acomodar
            self.paginas.currentChanged.connect(self._pagina)
            QTimer.singleShot(0, lambda: self._pagina(self.paginas.currentIndex()))
            self.b_log.toggled.connect(self.registro.setVisible)

            pie = QHBoxLayout()
            pie.addStretch(1)
            pie.addWidget(QSizeGrip(self))
            raiz.addLayout(pie)

            # --- vigilancia de carpetas y chequeo
            self.vigia = QFileSystemWatcher([d for d in rutas.CARPETAS.values() if os.path.isdir(d)], self)
            self.espera = QTimer(self, singleShot=True, interval=800)
            self.espera.timeout.connect(self._revisar_material)
            self.vigia.directoryChanged.connect(lambda _: self.espera.start())
            self.t_dv = QTimer(self)
            self.t_dv.timeout.connect(self._ver_davinci)
            self.t_dv.start(10000)
            QApplication.instance().installEventFilter(self)       # bordes para cambiar el tamano
            QTimer.singleShot(300, self._arranque)

        # ============================================================== paginas
        def _pagina_inicio(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            import boton_go
            self.boton = boton_go.BotonGo(lado=380)
            self.boton.clicked.connect(self._play)
            v.addStretch(1)
            fila_b = QHBoxLayout()
            fila_b.addStretch(1)
            fila_b.addWidget(self.boton)
            fila_b.addStretch(1)
            v.addLayout(fila_b)
            self.titulo = QLabel("Un clic y listo", objectName="titulo")
            self.titulo.setAlignment(Qt.AlignCenter)
            v.addWidget(self.titulo)
            linea = QFrame()
            linea.setFixedSize(120, 2)
            linea.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 transparent, "
                                "stop:0.5 #22C47E, stop:1 transparent);")
            fila_l = QHBoxLayout()
            fila_l.addStretch(1)
            fila_l.addWidget(linea)
            fila_l.addStretch(1)
            v.addLayout(fila_l)
            self.sub = QLabel("", objectName="sub")
            self.sub.setAlignment(Qt.AlignCenter)
            self.sub.setWordWrap(True)
            v.addWidget(self.sub)
            self.reserva = QWidget()                 # aqui la escena dibuja la lista de pasos mientras trabaja
            self.reserva.setFixedHeight(0)
            v.addWidget(self.reserva)
            v.addSpacing(8)
            # chip del evento + abrir videos
            fila_c = QHBoxLayout()
            fila_c.addStretch(1)
            self.chip_evento = QPushButton("", objectName="chip")
            self.chip_evento.setCursor(Qt.PointingHandCursor)
            self.chip_evento.clicked.connect(lambda: self._ir("Textos"))
            fila_c.addWidget(self.chip_evento)
            self.chip_videos = QPushButton("Abrir videos terminados", objectName="chip")
            self.chip_videos.setCursor(Qt.PointingHandCursor)
            self.chip_videos.clicked.connect(self._abrir_videos)
            self.chip_videos.hide()
            fila_c.addWidget(self.chip_videos)
            fila_c.addStretch(1)
            v.addLayout(fila_c)
            v.addSpacing(6)
            # plantillas: cuales se arman
            fila_p = QHBoxLayout()
            fila_p.addStretch(1)
            self.etq_plantillas = QLabel("PLANTILLAS", objectName="etq")
            fila_p.addWidget(self.etq_plantillas)
            fila_p.addSpacing(6)
            elegidas = self.est.get("versiones") or list(motor.VERSIONES)
            self.pills = {}
            for ver in motor.VERSIONES:
                b = QPushButton(VERSION_TEXTO[ver], objectName="pill", checkable=True)
                b.setCursor(Qt.PointingHandCursor)
                b.setChecked(ver in elegidas)
                b.toggled.connect(self._cambio_plantillas)
                self.pills[ver] = b
                b.setText(("✓  " if b.isChecked() else "") + VERSION_TEXTO[ver])
                fila_p.addWidget(b)
            self.b_todas = QPushButton("Todas", objectName="pill")
            self.b_todas.setCursor(Qt.PointingHandCursor)
            self.b_todas.clicked.connect(lambda: [b.setChecked(True) for b in self.pills.values()])
            fila_p.addWidget(self.b_todas)
            fila_p.addStretch(1)
            v.addLayout(fila_p)
            v.addSpacing(8)
            self._pintar_evento()
            return w

        def _tarjeta_carpeta(self, tipo, titulo, ayuda):
            t = QFrame(objectName="carpeta")
            g = QVBoxLayout(t)
            g.setContentsMargins(22, 20, 22, 20)
            g.setSpacing(8)
            g.addWidget(QLabel(titulo, objectName="etq"))
            n = QLabel("0", objectName="grande")
            g.addWidget(n)
            e = QLabel("", objectName="estado_c")
            e.setWordWrap(True)
            g.addWidget(e)
            a = QLabel(ayuda)
            a.setStyleSheet("color:%s;" % TENUE)
            a.setWordWrap(True)
            g.addWidget(a)
            g.addStretch(1)
            fila = QHBoxLayout()
            b1 = QPushButton("Agregar…", objectName="boton")
            b1.clicked.connect(lambda: self._agregar(tipo))
            b2 = QPushButton("Abrir carpeta", objectName="borde")
            b2.clicked.connect(lambda: rutas.abrir(rutas.CARPETAS[tipo]))
            fila.addWidget(b1)
            fila.addWidget(b2)
            fila.addStretch(1)
            g.addLayout(fila)
            self.tarjetas[tipo] = (t, n, e)
            return t

        def _pagina_material(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(40, 20, 40, 10)
            v.setSpacing(16)
            tit = QLabel("Material del evento", objectName="titulo")
            tit.setStyleSheet("font-size: 30px;")
            v.addWidget(tit)
            exp = QLabel("Arrastra fotos, videos o carpetas a esta ventana: se copian solos a la carpeta correcta "
                         "(los archivos DJI van a DRON). También puedes usar «Agregar…».")
            exp.setStyleSheet("color:%s;" % TENUE)
            exp.setWordWrap(True)
            v.addWidget(exp)
            fila = QHBoxLayout()
            fila.setSpacing(16)
            self.tarjetas = {}
            fila.addWidget(self._tarjeta_carpeta("foto", "FOTOS", "Se usan 8 para los destellos de la intro: "
                                                 "pon al menos 8 (mejor muchas, el programa elige las mejores)."))
            fila.addWidget(self._tarjeta_carpeta("video", "VIDEOS", "Videos de cámara y celular de todo el evento: "
                                                 "maquillaje, iglesia y fiesta."))
            fila.addWidget(self._tarjeta_carpeta("dron", "DRON", "Tomas aéreas (opcional). Abren el tráiler "
                                                 "y las versiones largas."))
            v.addLayout(fila)
            zona = QFrame(objectName="soltar")
            zv = QVBoxLayout(zona)
            z1 = QLabel("⤓")
            z1.setAlignment(Qt.AlignCenter)
            z1.setStyleSheet("font-size: 44px; color: #22C47E;")
            z2 = QLabel("Suelta aquí tus fotos, videos o carpetas completas")
            z2.setAlignment(Qt.AlignCenter)
            z2.setStyleSheet("font-size: 18px; font-weight: 700;")
            self.l_copia = QLabel("Se ordenan solos en FOTOS, VIDEOS y DRON")
            self.l_copia.setAlignment(Qt.AlignCenter)
            self.l_copia.setStyleSheet("color:%s;" % TENUE)
            zv.addStretch(1)
            for x in (z1, z2, self.l_copia):
                zv.addWidget(x)
            zv.addStretch(1)
            v.addWidget(zona, 1)
            return w

        def _pagina_textos(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(40, 20, 40, 10)
            tit = QLabel("Textos del video", objectName="titulo")
            tit.setStyleSheet("font-size: 30px;")
            v.addWidget(tit)
            caja = QFrame(objectName="vidrio")
            g = QGridLayout(caja)
            g.setContentsMargins(26, 24, 26, 24)
            g.setHorizontalSpacing(16)
            g.setVerticalSpacing(14)
            self.c_tipo = QComboBox()
            for clave, texto in TIPOS:
                self.c_tipo.addItem(texto, clave)
            self.c_tipo.setCurrentIndex(next((k for k, (c, _) in enumerate(TIPOS)
                                              if c == self.est.get("tipo_evento", "xv")), 0))
            self.e_nombre = QLineEdit(self.est.get("nombre_xv", ""))
            self.e_nombre.setPlaceholderText("Ej.: Valeria  ·  K & R")
            self.e_frase = QLineEdit(self.est.get("frase", ""))
            self.e_frase.setPlaceholderText("Vacío = la del tipo de evento (ej. «Nuestra historia de amor»)")
            self.e_fecha = QLineEdit(self.est.get("fecha_lugar", ""))
            self.e_fecha.setPlaceholderText("Vacío = la fecha del material (ej. «07 · 11 · 2026»)")
            for i, (etq, wid) in enumerate((("Tipo de evento", self.c_tipo), ("Nombres", self.e_nombre),
                                            ("Frase bajo el nombre", self.e_frase),
                                            ("Tarjeta final", self.e_fecha))):
                l = QLabel(etq)
                l.setStyleSheet("color:%s; font-weight:600;" % TENUE)
                g.addWidget(l, i, 0)
                g.addWidget(wid, i, 1)
            g.setColumnStretch(1, 1)
            v.addWidget(caja)
            nota = QLabel("Los capítulos, frases y el «gracias» cambian solos según el tipo de evento.")
            nota.setStyleSheet("color:%s;" % TENUE)
            v.addWidget(nota)
            v.addStretch(1)
            for wid in (self.e_nombre, self.e_frase, self.e_fecha):
                wid.textChanged.connect(self._pintar_evento)
            self.c_tipo.currentIndexChanged.connect(self._pintar_evento)
            return w

        def _pagina_ajustes(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(40, 20, 40, 10)
            tit = QLabel("Ajustes", objectName="titulo")
            tit.setStyleSheet("font-size: 30px;")
            v.addWidget(tit)
            caja = QFrame(objectName="vidrio")
            g = QGridLayout(caja)
            g.setContentsMargins(26, 24, 26, 24)
            g.setVerticalSpacing(16)
            self.ch_render = QCheckBox("Renderizar al terminar (si no, solo arma las timelines en DaVinci)")
            self.ch_render.setChecked(self.est.get("renderizar", True))
            self.ch_igualar = QCheckBox("Igualar luz y balance de blancos de cada toma")
            self.ch_igualar.setChecked(self.est.get("igualar", True))
            g.addWidget(self.ch_render, 0, 0, 1, 3)
            g.addWidget(self.ch_igualar, 1, 0, 1, 3)
            l = QLabel("Quitar ruido")
            l.setStyleSheet("color:%s; font-weight:600;" % TENUE)
            self.s_ruido = QSlider(Qt.Horizontal)
            self.s_ruido.setRange(0, 100)
            self.s_ruido.setValue(int(self.est.get("ruido") if self.est.get("ruido") is not None else 60))
            self.l_ruido = QLabel(str(self.s_ruido.value()))
            self.s_ruido.valueChanged.connect(lambda x: self.l_ruido.setText(str(x)))
            g.addWidget(l, 2, 0)
            g.addWidget(self.s_ruido, 2, 1)
            g.addWidget(self.l_ruido, 2, 2)
            g.setColumnStretch(1, 1)
            v.addWidget(caja)
            fila = QHBoxLayout()
            for txt, acc in (("Clasificación del evento", self._clasificacion),
                             ("Abrir DaVinci Resolve", rutas.abrir_resolve),
                             ("Videos terminados", lambda: rutas.abrir(rutas.TERMINADOS)),
                             ("Carpeta del programa", lambda: rutas.abrir(rutas.PROGRAMA))):
                b = QPushButton(txt, objectName="borde")
                b.clicked.connect(acc)
                fila.addWidget(b)
            fila.addStretch(1)
            v.addLayout(fila)
            caja2 = QFrame(objectName="vidrio")
            g2 = QGridLayout(caja2)
            g2.setContentsMargins(26, 18, 26, 18)
            l2 = QLabel("Carpeta de trabajo")
            l2.setStyleSheet("color:%s; font-weight:600;" % TENUE)
            self.l_base = QLabel(rutas.BASE)
            self.l_base.setWordWrap(True)
            g2.addWidget(l2, 0, 0)
            g2.addWidget(self.l_base, 0, 1)
            if rutas.CONGELADO:
                b_base = QPushButton("Cambiar…", objectName="borde")
                b_base.clicked.connect(self._cambiar_base)
                g2.addWidget(b_base, 0, 2)
            g2.setColumnStretch(1, 1)
            v.addWidget(caja2)
            pie = QLabel("Versión %s  ·  registro: %s" % (rutas.version(), rutas.REGISTRO))
            pie.setStyleSheet("color:%s; font-size:12px;" % TENUE)
            pie.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(pie)
            v.addStretch(1)
            return w

        def _cambiar_base(self):
            d = QFileDialog.getExistingDirectory(self, "Carpeta de trabajo (ahí van 1 MATERIAL y 2 VIDEOS TERMINADOS)",
                                                 rutas.BASE)
            if d:
                c = rutas.leer_config()
                c["carpeta_trabajo"] = d
                rutas.guardar_config(c)
                QMessageBox.information(self, TITULO_APP, "Listo. Cierra y vuelve a abrir el programa para usar:\n%s" % d)

        # ============================================================== estado
        def _ir(self, nombre):
            self.tabs[nombre].setChecked(True)
            self.paginas.setCurrentIndex(list(self.tabs).index(nombre))

        def _avisar(self, texto, tipo="info"):
            self.aviso_t.setText(texto)
            self.aviso_h.setText(time.strftime("%H:%M:%S"))
            repulir(self.aviso, tipo=tipo)
            repulir(self.aviso_i, tipo=tipo)
            self.aviso_i.setText("i" if tipo == "info" else "!")

        def _sub(self, texto, tipo=""):
            self.sub.setText(texto)
            repulir(self.sub, tipo=tipo)

        def _pintar_evento(self, *_):
            tipo = self.c_tipo.currentText() if hasattr(self, "c_tipo") else \
                dict(TIPOS).get(self.est.get("tipo_evento", "xv"), "XV años")
            nombre = self.e_nombre.text().strip() if hasattr(self, "e_nombre") else self.est.get("nombre_xv", "")
            self.chip_evento.setText(("✎  %s%s" % (tipo, ("  ·  " + nombre) if nombre else "  ·  escribe los nombres"))
                                     .replace("&", "&&"))

        def _cambio_plantillas(self, _=None):
            if not any(b.isChecked() for b in self.pills.values()):
                self.sender().setChecked(True)                    # siempre al menos una
            for v, b in self.pills.items():
                b.setText(("✓  " if b.isChecked() else "") + VERSION_TEXTO[v])
            self._sub_material()

        def _versiones(self):
            return [v for v, b in self.pills.items() if b.isChecked()]

        def _sub_material(self):
            if self.trabajo is not None:
                return
            m = self.material
            c = m["cuenta"]
            vers = ", ".join(VERSION_TEXTO[v] for v in self._versiones())
            if m["ok"]:
                self._sub("● %d fotos · %d videos · %d dron  ·  armará %s" % (c["foto"], c["video"], c["dron"], vers), "ok")
            else:
                self._sub("● Falta material: %s  ·  pulsa ▶ y te digo qué agregar" % ", ".join(
                    "%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in m["faltan"]))

        def _revisar_material(self):
            try:
                self.material = motor.revisar_material()
            except Exception as ex:
                self._avisar("No pude revisar 1 MATERIAL: %s" % ex, "error")
                return
            for tipo, (t, n, e) in self.tarjetas.items():
                cuantos = self.material["cuenta"][tipo]
                falta = dict(self.material["faltan"]).get(tipo)
                n.setText(str(cuantos))
                if falta:
                    e.setText("Faltan %d" % falta if cuantos else "Vacía: agrega %s" % (
                        "al menos 8 fotos" if tipo == "foto" else "videos"))
                else:
                    e.setText("Listo" if cuantos or tipo != "dron" else "Opcional")
                repulir(t, estado="falta" if falta else "ok")
                repulir(e, estado="falta" if falta else "ok")
            for d in rutas.CARPETAS.values():
                if os.path.isdir(d) and d not in self.vigia.directories():
                    self.vigia.addPath(d)
            self._sub_material()

        def _arranque(self):
            rutas.crear_carpetas()
            self._revisar_material()
            self._avisar("Chequeo de arranque…")
            self.cheq = Chequeo()
            self.cheq.fin.connect(self._fin_chequeo)
            self.cheq.start()
            self._ver_davinci()

        def _fin_chequeo(self, res):
            mal = [(n, d) for n, ok, d in res if not ok]
            if not mal:
                self._avisar("Chequeo de arranque: todo en orden (%d de %d)." % (len(res), len(res)))
            else:
                self._avisar("Chequeo de arranque: %d de %d en orden · %s" % (
                    len(res) - len(mal), len(res), " · ".join(d for _, d in mal)), "warn")

        def _ver_davinci(self):
            if self.trabajo is not None:
                self.punto.setStyleSheet("color:#22C47E; font-size:16px; padding: 0 10px;")
                return
            if getattr(self, "dv", None) is not None and self.dv.isRunning():
                return
            self.dv = EstadoDV()
            self.dv.fin.connect(self._pintar_davinci)
            self.dv.start()

        def _pintar_davinci(self, r):
            if r is None:
                return
            ok, proyecto = r
            self.punto.setStyleSheet("color:%s; font-size:16px; padding: 0 10px;" % ("#22C47E" if ok else AMBAR))
            self.punto.setToolTip("DaVinci Resolve abierto%s" % (" · " + proyecto if proyecto else "") if ok else
                                  "DaVinci Resolve cerrado: ▶ lo abre solo")

        # ============================================================== material: agregar / soltar
        def _agregar(self, tipo):
            filtros = {"foto": "Fotos (*.jpg *.jpeg *.png *.heic *.tif *.tiff *.webp)",
                       "video": "Videos (*.mp4 *.mov *.mkv *.avi *.mxf *.m4v *.mts)",
                       "dron": "Videos de dron (*.mp4 *.mov *.mkv *.m4v)"}
            archivos, _ = QFileDialog.getOpenFileNames(self, "Agregar a %s" % motor.NOMBRE_CARPETA[tipo],
                                                       os.path.expanduser("~"), filtros[tipo] + ";;Todo (*)")
            if archivos:
                self._copiar(archivos, tipo)

        def _copiar(self, archivos, tipo=None):
            if self.copia is not None:
                return
            self.copia = Copia(archivos, tipo)
            self.copia.avance.connect(lambda i, n, f: (self.l_copia.setText("Copiando %d de %d · %s" % (i, n, f)),
                                                       self._avisar("Copiando material %d de %d…" % (i, n))))
            self.copia.fin.connect(self._fin_copia)
            self.copia.start()

        def _fin_copia(self, res):
            self.copia = None
            if "error" in res:
                self._avisar("No se pudo copiar: %s" % res["error"], "error")
            else:
                hechos = ", ".join("%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in res.items() if n)
                self._avisar("Material agregado: %s." % (hechos or "nada nuevo (ya estaba)"))
                self.l_copia.setText("Listo: %s" % (hechos or "ya estaba todo"))
                self.l_copia.setStyleSheet("color:#7CF2C0; font-weight:600;")
            self._revisar_material()

        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls() and self.trabajo is None:
                e.acceptProposedAction()

        def dropEvent(self, e):
            archivos = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if archivos:
                self._ir("Material")
                self._copiar(archivos)

        # ============================================================== play
        def _guardar(self):
            versiones = self._versiones() or list(motor.VERSIONES)
            d = motor.leer_estado()
            d.update({"tipo_evento": self.c_tipo.currentData(), "nombre_xv": self.e_nombre.text().strip(),
                      "frase": self.e_frase.text().strip(), "fecha_lugar": self.e_fecha.text().strip(),
                      "versiones": versiones, "ruido": self.s_ruido.value(),
                      "igualar": self.ch_igualar.isChecked(), "renderizar": self.ch_render.isChecked()})
            motor.guardar_estado(d)
            return dict(evento=d.get("evento_manual", ""), nombre_xv=d["nombre_xv"], fecha_lugar=d["fecha_lugar"],
                        frase=d["frase"], tipo_evento=d["tipo_evento"], ruido=d["ruido"], igualar=d["igualar"],
                        solo=versiones if len(versiones) < len(motor.VERSIONES) else None, render=d["renderizar"])

        def _pedir_material(self):
            faltan = self.material["faltan"]
            texto = "Para armar el video falta:\n\n" + "\n".join(
                "•  %s: %s" % (motor.NOMBRE_CARPETA[t], "al menos %d fotos (faltan %d)" % (motor.MINIMOS[t], n)
                               if t == "foto" else "al menos %d video" % motor.MINIMOS[t]) for t, n in faltan) + \
                "\n\n¿Lo agregas ahora? También puedes arrastrar los archivos a la ventana."
            caja = QMessageBox(self)
            caja.setWindowTitle(TITULO_APP)
            caja.setIcon(QMessageBox.Warning)
            caja.setText(texto)
            b_ag = caja.addButton("Agregar…", QMessageBox.AcceptRole)
            b_ab = caja.addButton("Abrir carpeta", QMessageBox.ActionRole)
            caja.addButton("Ahora no", QMessageBox.RejectRole)
            caja.exec()
            tipo = faltan[0][0]
            self._ir("Material")
            if caja.clickedButton() is b_ag:
                self._agregar(tipo)
            elif caja.clickedButton() is b_ab:
                rutas.abrir(rutas.CARPETAS[tipo])

        def _play(self):
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            if self.copia is not None:
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            self._revisar_material()
            if not self.material["ok"]:
                self._avisar("Falta material en 1 MATERIAL: agrégalo y vuelve a pulsar ▶.", "warn")
                self._pedir_material()
                return
            op = self._guardar()
            self.registro.clear()
            self.chip_videos.hide()
            self._con_render = bool(op.get("render", True))
            self.pasos_go = {k: "pendiente" for k, _ in PASOS_GO}
            self._prog = 0.0
            self.boton.poner_estado("trabajando", centro="Preparando")
            self.boton.poner_progreso(0.0)
            self.escena.empezar()
            self._marcar("timeline", "activo")
            self.chip_evento.hide()
            for b in list(self.pills.values()) + [self.b_todas, self.etq_plantillas]:
                b.hide()
            self.reserva.setFixedHeight(len(PASOS_GO) * 34 + 14)
            self._acomodar()
            self.titulo.setText("Trabajando…")
            self._sub("Empezando…")
            self._avisar("Armando %s…" % ", ".join(VERSION_TEXTO[v] for v in self._versiones()))
            for b in list(self.pills.values()) + [self.b_todas]:
                b.setEnabled(False)
            self.trabajo = Trabajo(op)
            self.trabajo.linea.connect(self._linea)
            self.trabajo.avance.connect(self._avance)
            self.trabajo.fin.connect(self._fin)
            self.trabajo.fallo.connect(self._fallo)
            self.trabajo.finished.connect(self._liberar)
            self.trabajo.start()

        # (texto del registro, % , texto, fase que empieza)
        LINEAS = [("Analizando material", 3, "Revisando fotos y videos", "timeline"),
                  ("Analizando ", 5, "Analizando el material nuevo", "timeline"),
                  ("Conectando con DaVinci", 12, "Abriendo DaVinci Resolve", "voz"),
                  ("Armando timelines", 16, "Plan, ritmo y color", "ia"),
                  ("Media pool", 19, "Ordenando el media pool", "ia"),
                  ("1min lista", 24, "Versión de 1 min lista", "diseno"), ("3min lista", 30, "Versión de 3 min lista", "diseno"),
                  ("15min lista", 37, "Versión de 15 min lista", "diseno"), ("30min lista", 44, "Versión de 30 min lista", "diseno"),
                  ("Renderizando", 46, "Renderizando", "sfx"), ("Audio masterizado", 96, "Dejando el audio listo", "resolve")]

        def _marcar(self, clave, estado):
            """Una fase cambia: la escena lanza su cometa, el astrolabio enciende su pieza."""
            if self.pasos_go.get(clave) == estado or self.pasos_go.get(clave) == "hecho":
                return
            orden = [k for k, _ in PASOS_GO]
            if estado == "activo":                       # las anteriores quedan hechas (o saltadas)
                for k in orden[:orden.index(clave)]:
                    if self.pasos_go[k] in ("pendiente", "activo"):
                        self.pasos_go[k] = "hecho"
                        self.escena.paso(k, "hecho")
                self.boton.poner_estado("trabajando", centro=dict(PASOS_GO)[clave])
                self.boton.poner_fase(clave)
                self.escena.poner_fase(clave)
            self.pasos_go[clave] = estado
            self.escena.paso(clave, estado)

        def _poner_prog(self, f):
            f = max(self._prog, min(0.99, f))
            self._prog = f
            self.boton.poner_progreso(f)
            self.escena.progreso(f)

        def _linea(self, m):
            self.registro.appendPlainText(m)
            registro.info(m)
            for clave, pct, texto, fase in self.LINEAS:
                if clave in m:
                    if self.pasos_go.get(fase) != "hecho":
                        self._marcar(fase, "activo")
                    if pct / 100.0 >= self._prog:
                        self._poner_prog(pct / 100.0)
                        self._sub(texto + "…")
                    break

        def _avance(self, pct, texto):
            if pct >= 96:
                self._marcar("resolve", "activo")
            elif pct >= 46:
                self._marcar("sfx", "activo")
            self._poner_prog(pct / 100.0)
            self._sub(texto + "…")

        # ---- la escena: geometria y barra de abajo
        def _geo_escena(self):
            c = self.boton.mapTo(self.cielo, self.boton.rect().center())
            r = self.boton.width() * (0.62 if self.boton.estado == "trabajando" else 0.50)
            arriba = self.reserva.mapTo(self.cielo, self.reserva.rect().topLeft())
            cx = self.reserva.mapTo(self.cielo, self.reserva.rect().center()).x()
            if self.reserva.height() > 0:
                r = min(r, max(110.0, arriba.y() - c.y() - 22.0))
            return QPointF(c), float(r), QRectF(cx - 240, arriba.y(), 480, len(PASOS_GO) * 34)

        def _tramos(self):
            pesos = dict(PESO_GO)
            if not getattr(self, "_con_render", True):
                pesos["sfx"] = pesos["resolve"] = 0.0
            total = sum(pesos.values()) or 1.0
            out, x = [], 0.0
            for k, _ in PASOS_GO:
                w = pesos[k] / total
                out.append((k, x, x + w, getattr(self, "pasos_go", {}).get(k, "pendiente")))
                x += w
            return out

        def _datos_barra(self):
            b = self.boton
            if b.estado == "trabajando":
                prog = b._prog_visto
            elif b.estado in ("hecho", "error") and 0.0 <= b._cierre < 2.6:
                prog = 1.0 if b.estado == "hecho" else b._prog_visto
            else:
                return None
            izq = der = ""
            if b.estado == "trabajando":
                orden = [k for k, _ in PASOS_GO]
                activa = next((k for k in orden if self.pasos_go.get(k) == "activo"), None)
                if activa:
                    izq = "%d/%d · %s" % (orden.index(activa) + 1, len(orden), dict(PASOS_GO)[activa])
                der = "%d%%" % int(round(prog * 100))
            elif b.estado == "hecho":
                der = "100%"
            return {"prog": prog, "tramos": self._tramos(), "estado": b.estado, "cierre": b._cierre, "izq": izq, "der": der}

        def _quitar_reserva(self):
            if self.boton.estado != "trabajando":
                self.reserva.setFixedHeight(0)
                self.chip_evento.show()
                for b in list(self.pills.values()) + [self.b_todas, self.etq_plantillas]:
                    b.show()
                self._acomodar()

        def _acomodar(self):
            """El tamano del astrolabio sigue al espacio libre (como en CineCaptions)."""
            if hasattr(self, "escena"):
                self.escena.setGeometry(self.cielo.rect())
            pag = self.paginas.widget(0)
            libre = pag.height() - (self.reserva.height() + 150 if self.boton.estado == "trabajando" else 250)
            self.boton.poner_lado(int(max(240, min(libre, pag.width() * 0.5))))

        def _pagina(self, i):
            en_inicio = i == 0
            self.escena.setVisible(en_inicio)
            self.escena.activar(en_inicio)
            self.cielo.pausar(en_inicio)
            if en_inicio:
                self._acomodar()

        def resizeEvent(self, e):
            super().resizeEvent(e)
            if hasattr(self, "boton"):
                QTimer.singleShot(0, self._acomodar)

        def _fin(self, res):
            self.resultado = res or {}
            videos = self.resultado.get("videos") or []
            ok = [v for v in videos if v[1]]
            for k, _ in PASOS_GO:                      # lo que no corrio (sin render) queda saltado
                e = self.pasos_go.get(k)
                if e in ("pendiente", "activo"):
                    sin_render = not self._con_render and k in ("sfx", "resolve")
                    self._marcar(k, "saltado" if (sin_render and e == "pendiente") else "hecho")
            self.boton.poner_progreso(1.0)
            self.escena.progreso(1.0)
            bien = not videos or len(ok) == len(videos)

            def cerrar():
                self.escena.terminar(bien, "ok" if bien else "aviso")
                self.boton.poner_estado("hecho", centro="", tono="ok" if bien else "aviso")
            self.escena.explotar(cerrar)
            self.titulo.setText("¡Listo!")
            if videos:
                self._sub("%d de %d videos en 2 VIDEOS TERMINADOS · %s" % (len(ok), len(videos),
                                                                            self.resultado.get("evento", "")),
                          "ok" if len(ok) == len(videos) else "error")
                self._avisar("Terminado: %d videos con audio a -14 LUFS." % len(ok))
                self.chip_videos.show()
                self._abrir_videos()
            else:
                self._sub("Armado en DaVinci · %s" % self.resultado.get("evento", ""), "ok")
                self._avisar("Timelines armadas en DaVinci (sin render).")

        def _fallo(self, texto):
            activa = next((k for k, e in self.pasos_go.items() if e == "activo"), None)
            if activa:
                self.escena.paso(activa, "error")
            self.escena.terminar(False, "ok")
            self.boton.poner_estado("error", centro="Error")
            self.titulo.setText("Un clic y listo")
            self._sub("No se pudo terminar: %s" % texto, "error")
            self._avisar("Error: %s" % texto, "error")
            self.b_log.setChecked(True)

        def _liberar(self):
            self.trabajo = None
            for b in list(self.pills.values()) + [self.b_todas]:
                b.setEnabled(True)
            QTimer.singleShot(6000, lambda: self.titulo.setText("Un clic y listo") if self.trabajo is None else None)

        def _abrir_videos(self):
            rutas.abrir((self.resultado or {}).get("carpeta") or rutas.TERMINADOS)

        def _clasificacion(self):
            if os.path.exists(rutas.CLASIFICACION):
                rutas.abrir(rutas.CLASIFICACION)
            else:
                QMessageBox.information(self, TITULO_APP, "La clasificación se crea sola la primera vez que pulsas ▶.")

        # ============================================================== ventana sin marco
        BORDE = 7

        def _bordes(self, pos_global):
            if self.isMaximized():
                return Qt.Edges()
            g = self.frameGeometry()
            x, y = pos_global.x() - g.left(), pos_global.y() - g.top()
            b = Qt.Edges()
            if 0 <= x < self.BORDE:
                b |= Qt.LeftEdge
            elif g.width() - self.BORDE <= x <= g.width():
                b |= Qt.RightEdge
            if 0 <= y < self.BORDE:
                b |= Qt.TopEdge
            elif g.height() - self.BORDE <= y <= g.height():
                b |= Qt.BottomEdge
            return b

        def eventFilter(self, obj, ev):
            t = ev.type()
            if t in (QEvent.MouseMove, QEvent.MouseButtonPress) and isinstance(obj, QWidget) and obj.window() is self:
                b = self._bordes(ev.globalPosition().toPoint())
                if t == QEvent.MouseMove and not ev.buttons():
                    if b in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
                        self.setCursor(Qt.SizeFDiagCursor)
                    elif b in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
                        self.setCursor(Qt.SizeBDiagCursor)
                    elif b & (Qt.LeftEdge | Qt.RightEdge):
                        self.setCursor(Qt.SizeHorCursor)
                    elif b & (Qt.TopEdge | Qt.BottomEdge):
                        self.setCursor(Qt.SizeVerCursor)
                    else:
                        self.unsetCursor()
                elif t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton and b and self.windowHandle():
                    self.windowHandle().startSystemResize(b)
                    return True
            return super().eventFilter(obj, ev)

        def _maximizar(self):
            self.showNormal() if self.isMaximized() else self.showMaximized()

        def mousePressEvent(self, e):
            if e.button() == Qt.LeftButton and e.position().y() < 90 and self.windowHandle():
                self.windowHandle().startSystemMove()

        def mouseDoubleClickEvent(self, e):
            if e.position().y() < 90:
                self._maximizar()

        def closeEvent(self, e):
            if self.trabajo is not None and QMessageBox.question(
                    self, TITULO_APP, "Todavía está trabajando. ¿Cerrar de todos modos?") != QMessageBox.Yes:
                e.ignore()
                return
            try:
                self._guardar()
            except Exception:
                pass
            e.accept()

    if rutas.ES_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CinemaProductions.Trailer")
        except Exception:
            pass
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(TITULO_APP)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(QSS)
    candado = QLockFile(os.path.join(rutas.DATOS, "programa.lock"))
    candado.setStaleLockTime(0)
    if not candado.tryLock(200):                           # una sola ventana abierta a la vez
        QMessageBox.information(None, TITULO_APP, "El programa ya está abierto.")
        return 0
    rutas.crear_carpetas()
    win = Ventana()
    win.show()
    return qapp.exec()


def main():
    args = sys.argv[1:]
    registro.preparar()
    if "--tarea" in args:                                   # trabajos del instalador / autoprueba
        import tareas
        i = args.index("--tarea")
        sys.exit(tareas.correr(args[i + 1] if len(args) > i + 1 else "", args[i + 2] if len(args) > i + 2 else None))
    if rutas.CONGELADO:
        try:
            n = rutas.migrar_datos()
            if n:
                registro.info("Datos de la version anterior traidos: %d" % n)
        except Exception as ex:
            registro.error("No se pudieron traer los datos anteriores: %s" % ex)
    if any(a in args for a in ("--todo", "--una-vez", "--seco")):
        cli(args)
    else:
        sys.exit(app())


if __name__ == "__main__":
    main()
