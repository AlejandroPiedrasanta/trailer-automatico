# -*- coding: utf-8 -*-
"""
barra_qml.py - (1.7, la persona 19-nov: «quédate con QML / Qt Quick por partes») piezas de la ventana hechas en QML
(PROGRAMA/interfaz/qml), metidas en la ventana de widgets con QQuickWidget. Las pinta la tarjeta grafica (Qt Quick):
animaciones a 60 por segundo sin repintar la ventana.

    BarraQML(padre)         la barra del Inicio (qml/BarraInicio.qml): señales nombre / plantillas / trailer
    disponible()            False si Qt Quick no carga (la ventana usa entonces los botones de widgets de siempre)
Los iconos son los mismos de la ventana (piezas.icono) por un proveedor de imagenes: image://icono/<tipo>/<RRGGBB>/<lado>.
"""
import os
import sys

from PySide6.QtCore import Qt, QUrl, QTimer

import rutas
import piezas

# en el .exe la carpeta qml va junto a todo (sys._MEIPASS/qml); desde el codigo, en interfaz/qml
CARPETA = os.path.join(rutas.PROGRAMA, "qml") if getattr(sys, "frozen", False) else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def disponible():
    if os.environ.get("TRAILER_QML") == "0":
        return False
    try:
        from PySide6.QtQuickWidgets import QQuickWidget  # noqa: F401
        return os.path.isfile(os.path.join(CARPETA, "BarraInicio.qml"))
    except Exception:
        return False


def _proveedor():
    from PySide6.QtQuick import QQuickImageProvider

    class Iconos(QQuickImageProvider):
        def __init__(self):
            super().__init__(QQuickImageProvider.Pixmap)

        def requestPixmap(self, ident, size, pedido):
            try:
                tipo, color, lado = (ident.split("/") + ["FFFFFF", "24"])[:3]
                return piezas.icono(tipo, "#" + color, float(lado))
            except Exception:
                from PySide6.QtGui import QPixmap
                return QPixmap()
    return Iconos()


_QUIETO = []


def movimiento_reducido():
    """(1.7.8) ¿La persona pidio menos movimiento? Windows: «Mostrar animaciones» apagado (Configuración >
    Accesibilidad > Efectos visuales; SPI_GETCLIENTAREAANIMATION, una llamada que no pesa). TRAILER_QUIETO=1/0 lo
    fuerza (pruebas). Con menos movimiento se paran los adornos que se repiten; lo que informa sigue."""
    if not _QUIETO:
        v = os.environ.get("TRAILER_QUIETO")
        if v is not None:
            _QUIETO.append(v == "1")
        elif sys.platform == "win32":
            try:
                import ctypes
                si = ctypes.c_int(1)
                ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(si), 0)
                _QUIETO.append(not bool(si.value))
            except Exception:
                _QUIETO.append(False)
        else:
            _QUIETO.append(False)
    return _QUIETO[0]


def _pieza_qml(archivo, padre, proveedores=None):
    from PySide6.QtQuickWidgets import QQuickWidget
    q = QQuickWidget(padre)
    q.rootContext().setContextProperty("quieto", movimiento_reducido())
    q.engine().addImageProvider("icono", _proveedor())
    for nombre, prov in (proveedores or {}).items():
        q.engine().addImageProvider(nombre, prov)
    q.setResizeMode(QQuickWidget.SizeRootObjectToView)
    q.setAttribute(Qt.WA_AlwaysStackOnTop, True)     # transparente sobre el cielo de la ventana
    q.setClearColor(Qt.transparent)
    q.setSource(QUrl.fromLocalFile(os.path.join(CARPETA, archivo)))
    if q.status() == QQuickWidget.Error:
        raise RuntimeError("; ".join(e.toString() for e in q.errors()))
    try:                                            # la misma letra que la ventana (el estilo: Segoe UI Variable)
        q.rootObject().setProperty("familia", padre.font().family())
    except Exception:
        pass
    return q


class BarraQML:
    """La barra del Inicio. Se usa como un widget (self.widget) y avisa con sus señales (callbacks)."""

    def __init__(self, padre, al_nombre, al_plantillas, al_trailer):
        self.widget = _pieza_qml("BarraInicio.qml", padre)
        self.raiz = self.widget.rootObject()
        self.raiz.nombreClic.connect(al_nombre)
        self.raiz.plantillasClic.connect(al_plantillas)
        self.raiz.trailerClic.connect(al_trailer)
        self.reescalar()

    def reescalar(self):
        px = piezas.px
        self.raiz.setProperty("tam", px(36))
        self.raiz.setProperty("radio", px(40))
        self.raiz.setProperty("icono", px(46))
        self.widget.setFixedHeight(px(150))

    def poner_nombre(self, texto, ayuda=""):
        self.raiz.setProperty("nombre", texto)
        self.widget.setToolTip(ayuda)

    def poner_eleccion(self, plantillas, trailer):
        """(1.8.5) Lo que va a salir: plantillas = [nombres], trailer = texto («Horizontal y vertical») o "" si no."""
        n = len(plantillas)
        self.raiz.setProperty("plantillasOn", bool(n))
        self.raiz.setProperty("plantillasDetalle", "%d elegida%s" % (n, "" if n == 1 else "s") if n else "")
        self.raiz.setProperty("trailerOn", bool(trailer))
        self.raiz.setProperty("trailerDetalle", trailer or "")


# ---------------------------------------------------------------- (1.7) la pantalla de trabajo (qml/Trabajo.qml)
# Los adaptadores tienen la MISMA API que piezas.Pasos y piezas.Versiones (la ventana los usa igual): guardan el estado
# y se lo pasan al QML en cada cambio.
class PasosQML:
    def __init__(self, vista, pasos, estado=None):
        self._v = vista
        self.pasos = list(pasos)
        self.estado = dict(estado) if estado else {c: "pendiente" for c, _ in self.pasos}

    def _enviar(self):
        self._v.raiz.setProperty("pasos", [{"clave": c, "nombre": n, "estado": self.estado[c]} for c, n in self.pasos])

    def reiniciar(self):
        self.estado = {c: "pendiente" for c, _ in self.pasos}
        self._enviar()

    def poner(self, clave, estado):
        if clave not in self.estado:
            return
        if estado == "activo":                       # los de antes quedan hechos
            for c, _ in self.pasos:
                if c == clave:
                    break
                if self.estado[c] in ("pendiente", "activo"):
                    self.estado[c] = "hecho"
        self.estado[clave] = estado
        self._enviar()

    def activo(self):
        return next((c for c, _ in self.pasos if self.estado[c] == "activo"), None)


class _FilaQML:
    def __init__(self, padre, etiqueta):
        self._p = padre
        self.etiqueta = etiqueta
        self.estado, self.pct, self.texto, self.detalle = "cola", 0.0, "En cola", ""

    def poner(self, estado, texto, pct=None, detalle=""):
        self.estado, self.texto, self.detalle = estado, texto, detalle or ""
        if pct is not None:
            self.pct = max(0.0, min(1.0, pct))
        self._p._enviar()


class _BotonQML:
    """«Cancelar»: setEnabled / setText como un QPushButton."""

    def __init__(self, padre):
        self._p = padre
        self._activo, self._texto = True, "Cancelar"

    def setEnabled(self, si):
        self._activo = bool(si)
        self._p._v.raiz.setProperty("cancelarActivo", self._activo)

    def isEnabled(self):
        return self._activo

    def setText(self, t):
        self._texto = t
        self._p._v.raiz.setProperty("cancelarTexto", t)

    def text(self):
        return self._texto


class VersionesQML:
    def __init__(self, vista):
        self._v = vista
        self.filas = {}
        self.b_cancelar = _BotonQML(self)

    def _enviar(self):
        self._v.raiz.setProperty("versiones", [{"etq": e, "estado": f.estado, "texto": f.texto, "pct": f.pct,
                                                "detalle": f.detalle} for e, f in self.filas.items()])

    def poner_versiones(self, etiquetas):
        self.filas = {e: _FilaQML(self, e) for e in etiquetas}
        self.b_cancelar.setEnabled(True)
        self.b_cancelar.setText("Cancelar")
        self._enviar()

    def poner(self, etiqueta, estado, texto, pct=None, detalle=""):
        f = self.filas.get(etiqueta)
        if f is not None:
            f.poner(estado, texto, pct, detalle)

    def poner_eta(self, html):
        self._v.raiz.setProperty("eta", html or "")


class TrabajoQML:
    """La pantalla de trabajo: self.widget (QQuickWidget), self.pasos y self.versiones (adaptadores)."""

    def __init__(self, padre, pasos, al_cancelar, previo_pasos=None, previo_versiones=None):
        self.widget = _pieza_qml("Trabajo.qml", padre)
        self.raiz = self.widget.rootObject()
        self.raiz.cancelarClic.connect(al_cancelar)
        self.pasos = PasosQML(self, pasos, getattr(previo_pasos, "estado", None))
        self.versiones = VersionesQML(self)
        if previo_versiones is not None and previo_versiones.filas:     # lo que ya mostraba la de widgets
            self.versiones.poner_versiones(list(previo_versiones.filas))
            for e, f in previo_versiones.filas.items():
                self.versiones.filas[e].poner(f.estado, f.texto, f.pct, f.detalle)
        self.raiz.implicitHeightChanged.connect(self._alto)
        self.reescalar()
        self.pasos._enviar()
        self.versiones._enviar()

    def entrar(self):
        self.raiz.entrar()
        QTimer.singleShot(0, self._alto)

    def _alto(self):
        # (medido: si cambia de alto mientras esta escondido, QQuickWidget sigue pintando en el lienzo de antes y
        # todo sale estirado) ya a la vista, se le cambia el alto de nuevo para que rehaga su lienzo
        h = int(self.raiz.property("implicitHeight")) + 2
        q = self.widget
        if q.isVisible() and q.height() == h:
            q.setFixedHeight(h + 1)
        q.setFixedHeight(h)
        if not q.isVisible():
            self._pendiente = True
        elif getattr(self, "_pendiente", False):
            self._pendiente = False
            QTimer.singleShot(0, self._alto)

    def reescalar(self):
        self.raiz.setProperty("escala", piezas.ESCALA)
        self._alto()


# ---------------------------------------------------------------- (1.7, parte 3) los popups (qml/Popup.qml)
class _Fondo:
    """La foto borrosa de la ventana que va detras del popup (image://fondo/<n>)."""

    def __init__(self):
        from PySide6.QtQuick import QQuickImageProvider

        class Prov(QQuickImageProvider):
            def __init__(self, dueno):
                super().__init__(QQuickImageProvider.Pixmap)
                self.dueno = dueno

            def requestPixmap(self, ident, size, pedido):
                from PySide6.QtGui import QPixmap
                return self.dueno.pm if self.dueno.pm is not None else QPixmap()
        self.pm = None
        self.prov = Prov(self)


class _BotonPrueba:
    """Para las pruebas (piezas.preguntar deja ventana.popup_abierto): pop.botones[i].click() responde."""

    def __init__(self, popup, i):
        self.popup, self.i = popup, i

    def click(self):
        self.popup.raiz.cerrar(self.i)


class PopupQML:
    """El popup de la ventana en QML. preguntar(...) -> (boton, resultado de la forma). Una sola a la vez: si ya hay
    uno abierto, abierto() es True y piezas.preguntar usa el de widgets."""

    def __init__(self, ventana):
        self.v = ventana
        self.fondo = _Fondo()
        self.widget = _pieza_qml("Popup.qml", ventana, {"fondo": self.fondo.prov})
        self.widget.setFocusPolicy(Qt.StrongFocus)
        self.widget.hide()
        self.raiz = self.widget.rootObject()
        self.raiz.respuesta.connect(self._respuesta)
        self._bucle, self._r, self._n = None, None, 0
        self.botones = []

    def abierto(self):
        return self._bucle is not None

    def _respuesta(self, i, js):
        import json
        try:
            self._r = (int(i), json.loads(js or "{}"))
        except Exception:
            self._r = (int(i), {})
        if self._bucle is not None:
            self._bucle.quit()

    def preguntar(self, titulo, texto="", botones=("Entendido",), tipo="info", primario=0, escape=None, forma="",
                  datos=None):
        from PySide6.QtCore import QEventLoop
        v = self.v
        botones = list(botones)
        escape = len(botones) - 1 if escape is None else escape
        try:                                        # lo de atras, borroso (achicar y agrandar: barato)
            foto = v.grab()
            chica = foto.scaled(max(1, foto.width() // 12), max(1, foto.height() // 12), Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation)
            self.fondo.pm = chica.scaled(foto.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        except Exception:
            self.fondo.pm = None
        tapados = piezas.tapar_quick(v)             # la barra y el trabajo (tambien QML) no se ven encima
        self._n += 1
        r = self.raiz
        r.setProperty("escala", piezas.ESCALA)
        r.setProperty("fondo", "image://fondo/%d" % self._n)
        r.setProperty("titulo", titulo or "")
        r.setProperty("texto", texto or "")
        r.setProperty("botones", botones)
        r.setProperty("tipo", tipo or "info")
        r.setProperty("primario", int(primario))
        r.setProperty("esc", int(escape))
        r.setProperty("datos", datos or {})
        r.setProperty("forma", forma or "")
        self.botones = [_BotonPrueba(self, i) for i in range(len(botones))]
        self.widget.setGeometry(v.rect())
        self.widget.show()
        self.widget.raise_()
        self.widget.setFocus()
        self._r = None
        r.abrir()
        self._bucle = QEventLoop()
        try:
            self._bucle.exec()
        finally:
            self._bucle = None
            self.widget.hide()
            piezas.destapar_quick(tapados)
        return self._r if self._r is not None else (escape, {})


# ---------------------------------------------------------------- (1.7, parte 4) las paginas (qml/Trailers, Plantillas, Ajustes)
class PaginaQML:
    """Una pagina hecha en QML. leer() da lo que muestra (dict, de los widgets de siempre, que siguen guardando el
    estado sin verse); cada 400 ms, si cambio y se ve, va al QML (propiedad d). El QML pide con accion(nombre, valor)
    y acciones[nombre](valor) lo hace. entrar() la hace aparecer (el fundido de paginas de Qt no le llega)."""

    def __init__(self, archivo, padre, leer, acciones, soltar=None):
        import json
        self._json = json
        self.widget = _pieza_qml(archivo, padre)
        self.raiz = self.widget.rootObject()
        self.leer, self.acciones = leer, acciones
        self.raiz.accion.connect(self._accion)
        if soltar is not None:
            self.raiz.soltado.connect(lambda urls: soltar([QUrl(u).toLocalFile() for u in urls]))
        self._ultimo = None
        self.raiz.implicitHeightChanged.connect(self._alto)
        self.t = QTimer(self.widget, interval=400)
        self.t.timeout.connect(self.sincronizar)
        self.t.start()
        self.reescalar()
        self.sincronizar(forzar=True)

    def _accion(self, nombre, valor):
        f = self.acciones.get(nombre)
        if f is None:
            return
        try:                                        # despues del clic: lo que abre popups no corre dentro de QML
            QTimer.singleShot(0, lambda: (f(valor), self.sincronizar(forzar=True)))
        except Exception:
            pass

    def sincronizar(self, forzar=False):
        # (1.8.4, auditoria) la pagina sabe si se ve: con el QQuickWidget escondido, para QML todo sigue «visible» y
        # sus animaciones infinitas (vinilo, puntos, brillos) corrian 60 veces por segundo en las 4 pestañas
        vis = self.widget.isVisible()
        try:
            if self.raiz.property("activa") is not None and bool(self.raiz.property("activa")) != vis:
                self.raiz.setProperty("activa", vis)
        except Exception:
            pass
        if not forzar and not vis:
            return
        try:
            d = self.leer()
            txt = self._json.dumps(d, sort_keys=True, ensure_ascii=False)
        except Exception:
            return
        if forzar or txt != self._ultimo:
            self._ultimo = txt
            self.raiz.setProperty("d", d)

    def entrar(self, dx=0):
        """dx: (1.7.8) +1 la pagina entra desde la derecha (pestaña de mas adelante), -1 desde la izquierda."""
        self.sincronizar(forzar=True)
        self.raiz.entrar(dx)
        QTimer.singleShot(0, self._alto)

    def _alto(self):
        h = max(1, int(self.raiz.property("implicitHeight")))
        q = self.widget
        if q.isVisible() and q.height() == h:      # (como TrabajoQML) que rehaga su lienzo si cambio escondido
            q.setFixedHeight(h + 1)
        q.setFixedHeight(h)

    def reescalar(self):
        self.raiz.setProperty("escala", piezas.ESCALA)
        self._alto()
