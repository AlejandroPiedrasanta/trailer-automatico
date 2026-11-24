# -*- coding: utf-8 -*-
"""
vista_registro.py - (23-nov) Lo que se ve al pulsar el icono del registro (junto a minimizar).

La persona (23-nov): «necesito un icono de registro a la par del icono minimizar que cuando le dé clic pueda ver el
registro de errores». Ese dia el armado acabo en «DaVinci se trabó en armado» y no sabia que habia pasado: la traza
estaba en registro.log, que no se ve desde la ventana.

Va dentro del popup de siempre, en compacto (piezas.preguntar(compacto=True): sin emblema, la cabecera es de aqui y la
lista se queda con el alto): Errores | Avisos | Todo. Las tarjetas van por dia («Hoy», «Ayer», «19 nov»), cada una
con su hora, lo que vio la persona (registro.corto: sin rutas kilometricas), que quiere decir (registro._EXPLICA) y
la traza plegada («Ver detalle» se abre creciendo; se crea al pedirla). Los seguidos iguales van en una sola con
«N veces · desde HH:MM» (registro.juntar). Lo nuevo desde la ultima vez que se miro lleva «Nuevo». «Copiar» de cada
tarjeta deja ESE error en el portapapeles; el de abajo, todo lo que se ve. «Abrir carpeta», la del registro.

Fluidez: el archivo se lee en un hilo (registro.entradas: ~10 ms con 2,5 MB); las tarjetas entran por tandas de
5 ms por cuadro; al cambiar de pestaña la pagina que se va se apaga en foto (_Fundido: una pintada de un pixmap,
sin efectos de opacidad). Abierto, mira cada 3 s la cuenta de errores (sin disco) y se vuelve a leer si hay uno nuevo.
"""
import math
import os
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import piezas
import qt_kit
import registro
import rutas

px = piezas.px
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MAX_TARJETAS = 80           # por pestaña, lo mas nuevo (mas y se nota al abrir)
TODO_LINEAS = 600           # «Todo»: las ultimas anotaciones del archivo
POR_TROZO = 8               # tarjetas (y cabeceras de dia) por trozo de la lista (_trozo)
POR_CUADRO = 2             # tarjetas por cuadro (medido: cada una son ~4 ms entre crearla, vestirla y colocarla)
TANDA_S = 0.005             # y nunca mas de esto creando (piezas.CUADRO_MS = 16 ms)
ROJO, AMBAR, TENUE, ORO, VERDE = "#FF6B60", "#F2B84B", "#9DB0B6", "#E2B04F", "#3BE3A0"
NOTAS = ("Lo más nuevo, arriba", "Lo más nuevo, arriba", "Lo más nuevo, abajo")


def dia(fecha):
    """«Hoy», «Ayer», «19 nov»."""
    if fecha == time.strftime("%Y-%m-%d"):
        return "Hoy"
    if fecha == time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400)):
        return "Ayer"
    try:
        return "%d %s" % (int(fecha[8:10]), MESES[int(fecha[5:7]) - 1])
    except (ValueError, IndexError):
        return fecha


def como_texto(x):
    """Un error o aviso, para pegarlo en un mensaje."""
    partes = ["[%s %s] %s%s" % (x["fecha"], x["hora"], x["titulo"],
                                 " (%d veces desde %s)" % (x["veces"], x["desde"][:5]) if x.get("veces", 1) > 1
                                 else "")]
    if x.get("explica"):
        partes.append("  " + x["explica"])
    if x.get("detalle"):
        partes.append(x["detalle"])
    return "\n".join(partes)


def _hoja():
    return """
    QWidget#vreg, QWidget#vreg_lista, QWidget#vreg_vacio {{ background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}
    QLabel#vreg_titulo {{ color: #FFFFFF; font-size: {f_titulo}px; font-weight: 800; }}
    QFrame#vregcaja {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.18);
                      border-radius: {r_seg}px; }}
    QPushButton#vregseg {{ font-size: {f_seg}px; font-weight: 500; color: #E3EBED; min-height: 0px;
                          padding: {p_v}px {p_h}px; border-radius: {r_b}px; border: 1px solid transparent;
                          background: transparent; }}
    QPushButton#vregseg:hover {{ background: rgba(255,255,255,0.05); }}
    QPushButton#vregseg:checked {{ background: #1FA971; color: #FFFFFF; border: 1px solid rgba(120,245,180,0.7); }}
    QFrame#vreg_card {{ background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.10);
                       border-radius: {r_card}px; }}
    QFrame#vreg_card[tipo="error"] {{ border-color: rgba(255,107,96,0.42); }}
    QLabel#vreg_dia {{ color: {oro}; font-size: {f_mini}px; font-weight: 700; padding: {p_dia}px 0px 0px {p_n}px; }}
    QLabel#vreg_hora {{ color: {tenue}; font-size: {f_chico}px; }}
    QLabel#vreg_nuevo {{ color: #FFFFFF; background: rgba(255,90,79,0.85); font-size: {f_mini}px; font-weight: 700;
                        padding: 0px {p_n}px; border-radius: {r_n}px; }}
    QLabel#vreg_veces {{ color: #E3EBED; background: rgba(255,255,255,0.08); font-size: {f_mini}px; font-weight: 600;
                        padding: 0px {p_n}px; border-radius: {r_n}px; }}
    QLabel#vreg_tit {{ color: #FFFFFF; font-size: {f_tit}px; font-weight: 600; }}
    QLabel#vreg_exp {{ color: #B9C6C9; font-size: {f_chico}px; }}
    QLabel#vreg_t {{ color: {tenue}; font-size: {f_chico}px; }}
    QLabel#vreg_vacio_t {{ color: #E3EBED; font-size: {f_tit}px; font-weight: 600; }}
    QPushButton#vreg_mas {{ background: transparent; border: none; color: {oro}; font-size: {f_chico}px;
                           font-weight: 600; padding: 0px; min-height: 0px; text-align: left; }}
    QPushButton#vreg_mas:hover {{ color: #F6D27A; }}
    QPushButton#vreg_mas[hecho="true"] {{ color: {verde}; }}
    QPlainTextEdit#vreg_det, QPlainTextEdit#vreg_todo {{ background: rgba(2,10,14,0.85); color: #C9D4D7;
                           border: 1px solid rgba(255,255,255,0.08); border-radius: {r_det}px; font-size: {f_det}px;
                           padding: {p_det}px; }}
    QPushButton#vreg_b {{ font-size: {f_b}px; font-weight: 600; color: #FFFFFF; min-height: {h_b}px; padding: 0px {p_b}px;
                         border-radius: {r_bb}px; background: rgba(255,255,255,0.04);
                         border: 1px solid rgba(217,177,92,0.75); }}
    QPushButton#vreg_b:hover {{ background: rgba(217,177,92,0.16); border-color: #F1CB7A; }}
    QPushButton#vreg_b:pressed {{ background: rgba(217,177,92,0.26); }}
    """.format(f_titulo=px(52), r_seg=px(30), f_seg=px(30), p_v=px(10), p_h=px(30), r_b=px(24), r_card=px(24),
               tenue=TENUE, oro=ORO, verde=VERDE, f_chico=px(26), f_mini=px(21), p_n=px(10), r_n=px(12), p_dia=px(8),
               f_tit=px(30), r_det=px(16), f_det=px(24), p_det=px(10), f_b=px(28), h_b=px(62), p_b=px(34),
               r_bb=px(31))


class _Fundido(QWidget):
    """(animacion de cambio de pestaña) La pagina que se va, en foto, apagandose sobre la que llega: una pintada de
    un pixmap por cuadro (nada de QGraphicsOpacityEffect: repinta la lista entera)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pm, self._a = None, 0.0
        self._anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=150,
                                       easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._paso)
        self._anim.finished.connect(self._fin)
        self.hide()

    def lanzar(self, pm, sitio):
        self._anim.stop()
        self._pm, self._a = pm, 1.0
        self.setGeometry(sitio)
        self.show()
        self.raise_()
        self._anim.start()

    def _paso(self, v):
        self._a = float(v)
        self.update()

    def _fin(self):
        self._pm = None
        self.hide()

    def paintEvent(self, _):
        if self._pm is None:
            return
        p = QPainter(self)
        p.setOpacity(self._a)
        p.drawPixmap(0, 0, self._pm)


class VistaRegistro(QWidget):
    """El contenido del popup del registro. visto = «fecha hora» de la ultima vez que se miro (lo de despues: Nuevo)."""

    def __init__(self, ventana, pestana=0, visto=""):
        super().__init__()
        self.setObjectName("vreg")
        self.setStyleSheet(_hoja())
        self.visto = visto or ""
        self.datos = None                            # (errores, avisos, todo)
        self.llenas = set()
        self._cola = []
        self._sueltas = []                           # tarjetas recien puestas, aun sin su alto fijo (_fijar)
        self._abierto = [None, None]                 # la columna del trozo que se esta llenando en cada lista
        self._dia = [None, None]                     # el ultimo dia con cabecera en cada lista
        self._leyendo = False
        self._n = registro.errores()
        self._goteo = QTimer(self, interval=piezas.CUADRO_MS)
        self._goteo.timeout.connect(self._gotear)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(px(18))
        # --- cabecera: icono, «Registro» y como va
        cab = QHBoxLayout()
        cab.setSpacing(px(18))
        ic = QLabel()
        ic.setPixmap(piezas.icono("registro", ORO, px(52)))
        cab.addWidget(ic)
        cab.addWidget(QLabel("Registro", objectName="vreg_titulo"))
        cab.addStretch(1)
        self.l_estado = QLabel("Leyendo el registro…", objectName="vreg_t")
        cab.addWidget(self.l_estado)
        v.addLayout(cab)
        # --- pestañas
        arriba = QHBoxLayout()
        self.seg = piezas.Segmentado(["Errores", "Avisos", "Todo"], pestana, nombre="vregseg", caja="vregcaja")
        self.seg.cambio.connect(self._ver)
        arriba.addWidget(self.seg)
        arriba.addStretch(1)
        self.l_nota = QLabel(NOTAS[pestana], objectName="vreg_t")
        arriba.addWidget(self.l_nota)
        v.addLayout(arriba)
        # --- las tres paginas
        self.pila = QStackedWidget()
        # (fijo: el popup hace la foto de su entrada con este tamaño y no salta al llegar las tarjetas)
        self.pila.setFixedSize(px(1060), max(px(300), min(px(820), ventana.height() - px(600))))
        self.listas, self.areas = [], []
        for _ in range(2):
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            caja = QWidget(objectName="vreg_lista")
            lv = QVBoxLayout(caja)
            lv.setContentsMargins(0, 0, px(14), 0)
            lv.setSpacing(px(14))
            lv.addStretch(1)
            sa.setWidget(caja)
            self.pila.addWidget(sa)
            self.listas.append(lv)
            self.areas.append(sa)
        self.todo = QPlainTextEdit(objectName="vreg_todo")
        self.todo.setReadOnly(True)
        self.pila.addWidget(self.todo)
        v.addWidget(self.pila)
        self._fundido = _Fundido(self)
        # --- abajo
        abajo = QHBoxLayout()
        abajo.setSpacing(px(20))
        self.b_copiar = QPushButton("Copiar todo", objectName="vreg_b")
        self.b_copiar.setToolTip("Copia lo que se ve en esta pestaña (para pegarlo en un mensaje)")
        self.b_carpeta = QPushButton("Abrir carpeta", objectName="vreg_b")
        self.b_carpeta.setToolTip("La carpeta donde está registro.log")
        for b, icono in ((self.b_copiar, "copiar"), (self.b_carpeta, "carpeta")):
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(piezas.qicono(icono, "#F2F6F7", px(30)))
            b.setIconSize(QSize(px(30), px(30)))
            abajo.addWidget(b)
        self.b_copiar.clicked.connect(self._copiar)
        self.b_carpeta.clicked.connect(lambda: rutas.abrir(os.path.dirname(rutas.REGISTRO)))
        abajo.addStretch(1)
        v.addLayout(abajo)
        self.pila.setCurrentIndex(pestana)
        self._vigia = QTimer(self, interval=3000)    # ¿un error nuevo con esto abierto? (la cuenta, sin disco)
        self._vigia.timeout.connect(self._hay_nuevo)
        self._vigia.start()
        self._pedir()

    # ---------------------------------------------------------------- leer (en un hilo)
    def _pedir(self):
        if self._leyendo:
            return
        self._leyendo = True
        self._n = registro.errores()
        qt_kit.correr_en_hilo(self, self._leer, self._leido)

    @staticmethod
    def _leer():
        ent = registro.entradas()
        lista = registro.juntar(registro.errores_y_avisos(ent))
        todo = []
        for e in ent[-TODO_LINEAS:]:
            todo.append("%s %s  %-7s %s" % (e["fecha"][5:], e["hora"], e["nivel"], e["texto"].strip()))
            todo.extend("        " + l for l in e["resto"])
        return ([x for x in lista if x["tipo"] == "error"], [x for x in lista if x["tipo"] == "aviso"],
                "\n".join(todo))

    def _leido(self, res, error):
        self._leyendo = False
        if error is not None or res is None:
            self.l_estado.setText("No pude leer el registro: %s" % (error or "vacío"))
            return
        if self.datos is not None:                   # se volvio a leer (llego un error con esto abierto)
            self._vaciar()
        self.datos = res
        errores, avisos, _ = res
        for i, (nombre, lista) in enumerate((("Errores", errores), ("Avisos", avisos))):
            self.seg.botones[i].setText("%s · %d" % (nombre, len(lista)) if lista else nombre)
        nuevos = sum(1 for x in errores if self._es_nuevo(x))
        self.l_estado.setText(("%d error%s nuevo%s" % (nuevos, "" if nuevos == 1 else "es", "" if nuevos == 1 else "s"))
                              if nuevos else "Leído a las %s" % time.strftime("%H:%M"))
        self.l_estado.setStyleSheet("color: %s; font-weight: 600;" % ROJO if nuevos else "")
        self._llenar(self.seg.actual())

    def _hay_nuevo(self):
        if registro.errores() != self._n and self.isVisible():
            self._pedir()

    def _es_nuevo(self, x):
        return bool(self.visto) and "%s %s" % (x["fecha"], x["hora"]) > self.visto

    def _vaciar(self):
        self._goteo.stop()
        self._cola, self._sueltas = [], []
        self.llenas.clear()
        self._dia, self._abierto = [None, None], [None, None]
        for lv in self.listas:
            while lv.count() > 1:                    # (queda el muelle del final)
                w = lv.takeAt(0).widget()
                if w is not None:
                    w.hide()
                    w.deleteLater()

    # ---------------------------------------------------------------- mostrar
    def _ver(self, i):
        """Cambio de pestaña: la pagina que se va se apaga en foto sobre la que llega."""
        i = max(0, i)
        if i != self.pila.currentIndex() and self.isVisible():
            self._fundido.lanzar(self.pila.currentWidget().grab(), self.pila.geometry())
        self.pila.setCurrentIndex(i)
        self.l_nota.setText(NOTAS[i])
        self._llenar(i)

    def _llenar(self, i):
        if self.datos is None or i in self.llenas:
            return
        self.llenas.add(i)
        if i == 2:
            self.todo.setPlainText(self.datos[2])
            self.todo.verticalScrollBar().setValue(self.todo.verticalScrollBar().maximum())
            return
        lista = self.datos[i][:MAX_TARJETAS]
        if not lista:
            self.listas[i].insertWidget(0, self._vacio(i))
            return
        self._cola.extend((i, x) for x in lista)
        if len(self.datos[i]) > MAX_TARJETAS:        # lo que no cabe aqui sigue en «Todo» y en el archivo
            self._cola.append((i, len(self.datos[i]) - MAX_TARJETAS))
        self._goteo.start()

    def _vacio(self, i):
        w = QWidget(objectName="vreg_vacio")
        w.setMinimumHeight(self.pila.height() - px(40))
        l = QVBoxLayout(w)
        l.setSpacing(px(14))
        l.addStretch(1)
        ic = QLabel()
        ic.setPixmap(piezas.icono("check", VERDE, px(84)))
        l.addWidget(ic, 0, Qt.AlignHCenter)
        l.addWidget(QLabel("Sin errores guardados" if i == 0 else "Sin avisos guardados", objectName="vreg_vacio_t"),
                    0, Qt.AlignHCenter)
        l.addWidget(QLabel("Si algo falla, aquí queda qué pasó y a qué hora.", objectName="vreg_t"), 0,
                    Qt.AlignHCenter)
        l.addStretch(1)
        return w

    def _gotear(self):
        """(animacion de entrada) una tanda de tarjetas por cuadro (5 ms): se ven llegar y la ventana no se traba."""
        t0, n = time.perf_counter(), 0
        self._fijar()
        while self._cola:
            i, x = self._cola.pop(0)
            lv = self._trozo(i)
            if isinstance(x, int):                   # el final: cuantos mas viejos quedaron fuera
                fin = QLabel("… y %d más antiguos: están en «Abrir carpeta» (registro.log)" % x, objectName="vreg_t")
                fin.setAlignment(Qt.AlignHCenter)
                lv.insertWidget(lv.count() - 1, fin)
                continue
            if x["fecha"] != self._dia[i]:
                self._dia[i] = x["fecha"]
                lv.insertWidget(lv.count() - 1, QLabel(dia(x["fecha"]).upper(), objectName="vreg_dia"))
            f = self._tarjeta(x)
            lv.insertWidget(lv.count() - 1, f)
            f.ensurePolished()                       # (medido) lo caro es vestirla con la hoja: aqui, dentro de la
            self._sueltas.append(f)                  # tanda, y no todas juntas al pintar
            n += 1
            if n >= POR_CUADRO or time.perf_counter() - t0 > TANDA_S:
                return
        if not self._sueltas:
            self._goteo.stop()

    def _trozo(self, i):
        """Donde va la tarjeta que sigue: las listas van en trozos de POR_TROZO (cada uno, una caja con su columna).
        (medido: en UNA columna cada tarjeta nueva hacia recolocar todas las de antes, ~0,3 ms por tarjeta: 25-30 ms
        con 80; asi solo se recoloca el trozo abierto)"""
        lv = self._abierto[i]
        if lv is None or lv.count() - 1 >= POR_TROZO:
            caja = QWidget(objectName="vreg_lista")
            lv = QVBoxLayout(caja)
            lv.setContentsMargins(0, 0, 0, 0)
            lv.setSpacing(px(14))
            lv.addStretch(1)
            fuera = self.listas[i]
            fuera.insertWidget(fuera.count() - 1, caja)
            self._abierto[i] = lv
        return lv

    def _fijar(self):
        """(medido: cada tanda volvia a medir el alto de TODAS las tarjetas, con su texto partido en renglones:
        16-29 ms con 80) La tarjeta ya colocada se queda con su alto; «Ver detalle» se lo devuelve (_detalle)."""
        quedan = []
        for f in self._sueltas:
            if f.isVisible() and f.height() > 0 and f.height() == f.heightForWidth(f.width()):
                f.setFixedHeight(f.height())
            elif len(quedan) < 400:                  # (en una pestaña que no se ve: cuando se vea)
                quedan.append(f)
        self._sueltas = quedan

    def _tarjeta(self, x):
        f = QFrame(objectName="vreg_card")
        f.setProperty("tipo", x["tipo"])
        f.det = None                                 # la traza se crea al pedirla (un QPlainTextEdit pesa)
        l = QVBoxLayout(f)
        l.setContentsMargins(px(26), px(16), px(26), px(18))
        l.setSpacing(px(6))
        cab = QHBoxLayout()
        cab.setSpacing(px(12))
        punto = QLabel()
        punto.setPixmap(piezas.icono("punto", ROJO if x["tipo"] == "error" else AMBAR, px(18)))
        cab.addWidget(punto)
        cab.addWidget(QLabel(x["hora"][:5], objectName="vreg_hora"))
        if self._es_nuevo(x):
            cab.addWidget(QLabel("Nuevo", objectName="vreg_nuevo"))
        if x.get("veces", 1) > 1:
            cab.addWidget(QLabel("%d veces · desde %s" % (x["veces"], x["desde"][:5]), objectName="vreg_veces"))
        cab.addStretch(1)
        version = x.get("sesion", "").split("·")[-1].strip()
        if version:
            cab.addWidget(QLabel("versión %s" % version, objectName="vreg_hora"))
        l.addLayout(cab)
        # (medido: 80 titulos «seleccionables» = un documento de texto cada uno y huecos de 50-78 ms al llenar la
        # lista; sin eso, 12-23. Para llevarse el texto esta «Copiar»)
        t = QLabel(x["titulo"], objectName="vreg_tit")
        t.setWordWrap(True)
        t.setTextFormat(Qt.PlainText)
        l.addWidget(t)
        if x.get("explica"):
            e = QLabel(x["explica"], objectName="vreg_exp")
            e.setTextFormat(Qt.PlainText)
            e.setWordWrap(True)
            l.addWidget(e)
        pie = QHBoxLayout()
        pie.setSpacing(px(30))
        if x.get("detalle"):
            b = QPushButton("Ver detalle", objectName="vreg_mas", checkable=True)
            b.setCursor(Qt.PointingHandCursor)
            b.toggled.connect(lambda on, f=f, x=x, b=b: self._detalle(f, x, b, on))
            pie.addWidget(b)
        c = QPushButton("Copiar", objectName="vreg_mas")
        c.setCursor(Qt.PointingHandCursor)
        c.setToolTip("Copia este %s (para pegarlo en un mensaje)" % x["tipo"])
        c.clicked.connect(lambda _=False, x=x, c=c: self._copiar_uno(x, c))
        pie.addWidget(c)
        pie.addStretch(1)
        l.addLayout(pie)
        return f

    def _alto_detalle(self, d, texto):
        """Lo que mide la traza ya partida en renglones (hasta 360): el documento no lo sabe hasta que se pinta."""
        d.ensurePolished()
        fm = d.fontMetrics()
        ancho = max(px(200), self.pila.width() - px(14) - 2 * px(26) - 2 * px(10) - px(34))
        renglones = sum(max(1, int(math.ceil(fm.horizontalAdvance(r) * 1.12 / ancho))) for r in texto.split("\n"))
        return min(px(380), (renglones + 1) * fm.lineSpacing() + 2 * px(10) + px(16))

    def _detalle(self, f, x, b, abrir):
        """La traza crece (200 ms) o se pliega (160 ms)."""
        b.setText("Ocultar detalle" if abrir else "Ver detalle")
        d = f.det
        if d is None:
            if not abrir:
                return
            d = f.det = QPlainTextEdit(x["detalle"], objectName="vreg_det")
            d.setReadOnly(True)
            d.setMaximumHeight(0)
            if f in self._sueltas:
                self._sueltas.remove(f)
            f.setMinimumHeight(0)                    # (tenia el alto fijo: ahora crece con su traza)
            f.setMaximumHeight(16777215)
            f.layout().addWidget(d)
            d.alto = self._alto_detalle(d, x["detalle"])     # (ya dentro: con la letra de la hoja)
        if abrir:
            d.show()
        a = QPropertyAnimation(d, b"maximumHeight", d)
        a.setDuration(200 if abrir else 160)
        a.setStartValue(d.maximumHeight())
        a.setEndValue(d.alto if abrir else 0)
        a.setEasingCurve(QEasingCurve.OutCubic if abrir else QEasingCurve.InCubic)
        if abrir:                                    # al acabar de abrirse, que se vea entera (sin salirse por abajo)
            a.finished.connect(lambda f=f: self._a_la_vista(f))
        else:
            a.finished.connect(d.hide)
        a.start(a.DeletionPolicy.DeleteWhenStopped)

    def _a_la_vista(self, f):
        sa = self.pila.currentWidget()
        if isinstance(sa, QScrollArea):
            sa.ensureWidgetVisible(f, 0, px(14))

    # ---------------------------------------------------------------- copiar
    def texto(self):
        """Lo que se ve, como texto (para pegarlo en un mensaje)."""
        if self.datos is None:
            return ""
        i = max(0, self.seg.actual())
        if i == 2:
            return self.datos[2]
        return "\n".join(como_texto(x) for x in self.datos[i][:MAX_TARJETAS])

    def _copiar(self):
        QGuiApplication.clipboard().setText(self.texto())
        b = self.b_copiar
        b.setText("Copiado")
        b.setIcon(piezas.qicono("check", VERDE, px(30)))
        QTimer.singleShot(1800, b, lambda: (b.setText("Copiar todo"),
                                            b.setIcon(piezas.qicono("copiar", "#F2F6F7", px(30)))))

    def _copiar_uno(self, x, b):
        QGuiApplication.clipboard().setText(como_texto(x))
        self._hecho(b, True, "Copiado")
        QTimer.singleShot(1600, b, lambda: self._hecho(b, False, "Copiar"))

    @staticmethod
    def _hecho(b, si, texto):
        b.setText(texto)
        b.setProperty("hecho", bool(si))
        b.style().unpolish(b)
        b.style().polish(b)
