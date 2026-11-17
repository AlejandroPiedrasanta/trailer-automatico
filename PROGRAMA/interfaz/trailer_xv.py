# -*- coding: utf-8 -*-
"""
trailer_xv.py - "Un clic y listo": trailer automatico de CINEMA PRODUCTIONS (Windows y Mac, Qt6 / PySide6, local).

El boton del centro (▶) hace todo:
  1. revisa que 1 MATERIAL tenga fotos y videos (si falta algo, lo pide),
  2. analiza y clasifica el material (maquillaje, iglesia, fiesta),
  3. lo arma en las plantillas elegidas abajo (1, 3, 15 y/o 30 min) en DaVinci Resolve,
  4. renderiza, deja el audio a -14 LUFS, mide la imagen y abre «EVENTO TERMINADO - <evento>» (VIDEO TERMINADO y
   PLANTILLAS DE LOS VIDEOS). El material y el trabajo van por dentro del programa (1.5.7).
Se pueden arrastrar fotos, videos o carpetas a la ventana: se copian solos a FOTOS, VIDEOS o DRON.

Uso:  doble clic en "ARMAR TRAILERS" (.bat en Windows, .command en Mac)
      python trailer_xv.py --todo        (sin ventana: arma y renderiza)
      python trailer_xv.py --una-vez     (sin ventana: solo arma en DaVinci)
      python trailer_xv.py --seco        (solo el plan, no toca DaVinci)
"""
import os
import re
import sys
import math
import time
_T_ARRANQUE = time.perf_counter()        # para medir cuanto tarda en abrir (ver _tiempo)
import random
import traceback

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # PROGRAMA (el codigo va en carpetas)
sys.path.insert(0, os.path.join(SKILL_DIR, "nucleo"))      # rutas pone en sys.path las demas carpetas
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


def _fecha_bonita(iso):
    """'2026-11-07' -> 'sábado 7 de noviembre'."""
    import datetime
    try:
        f = datetime.date.fromisoformat(str(iso))
    except (ValueError, TypeError):
        return str(iso or "otra fecha")
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre")
    return "%s %d de %s" % (dias[f.weekday()], f.day, meses[f.month - 1])


def versiones_guardadas(est):
    """(horizontales, verticales): las versiones elegidas en Inicio para cada formato. Sin elegir nunca, todas las
    horizontales y ninguna vertical; siempre queda al menos una."""
    h = est.get("versiones")
    h = list(motor.VERSIONES) if h is None else [x for x in motor.VERSIONES if x in h]
    v = [x for x in motor.VERSIONES if x in (est.get("versiones_vertical") or [])]
    return (h or ([] if v else list(motor.VERSIONES))), v


def opciones_guardadas():
    est = motor.leer_estado()
    h, _ = versiones_guardadas(est)
    return dict(evento=est.get("evento_manual", ""), nombre_xv=est.get("nombre_xv", ""),
                fecha_lugar=est.get("fecha_lugar", ""), frase=est.get("frase", ""),
                tipo_evento=est.get("tipo_evento", "xv"), ruido=est.get("ruido"),
                igualar=est.get("igualar", True), voz=est.get("voz"), verticales=est.get("usar_verticales", True),
                solo=h if 0 < len(h) < len(motor.VERSIONES) else None)


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
        h, vert = versiones_guardadas(motor.leer_estado())
        res = motor.armar_todo(log, vertical=vert, horizontal=bool(h), **op)
        log("Videos en: %s" % res["carpeta"])
    else:
        motor.armar(log, seco="--seco" in args, **op)


# ================================================================== ventana
def _tiempo(que):
    """Con TRAILER_TIEMPOS=1 anota en el registro cuanto lleva el arranque (para medir que tarda en abrir)."""
    if os.environ.get("TRAILER_TIEMPOS"):
        registro.info("arranque %-22s %.2f s" % (que, time.perf_counter() - _T_ARRANQUE))


def _portada_nativa():
    """Windows: la portada (recursos/portada.bmp) en una ventanita del sistema, ANTES de cargar Qt. Qt tarda mas de
    un segundo en poder mostrar su primera ventana (arma la lista de fuentes de la PC); esto se ve a las decimas del
    doble clic. Devuelve el identificador de la ventanita (para quitarla con _quitar_portada) o None."""
    if not rutas.ES_WIN:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        try:                                    # misma nitidez que tendra Qt (por monitor); si ya estaba puesta, da igual
            u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                 wintypes.UINT]
        mapa = u.LoadImageW(None, os.path.join(rutas.RECURSOS, "portada.bmp"), 0, 0, 0, 0x0010)   # LR_LOADFROMFILE
        if not mapa:
            return None

        class BITMAP(ctypes.Structure):
            _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                        ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                        ("bmBits", ctypes.c_void_p)]
        bm = BITMAP()
        g.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
        g.GetObjectW(mapa, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                      wintypes.HINSTANCE, wintypes.LPVOID]
        # WS_EX_TOOLWINDOW | WS_EX_TOPMOST ; WS_POPUP | WS_VISIBLE | SS_BITMAP
        v = u.CreateWindowExW(0x00000080 | 0x00000008, "STATIC", None, 0x80000000 | 0x10000000 | 0x0000000E,
                              (u.GetSystemMetrics(0) - w) // 2, (u.GetSystemMetrics(1) - h) // 2, w, h,
                              None, None, None, None)
        if not v:
            return None
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.SendMessageW(v, 0x0172, 0, mapa)       # STM_SETIMAGE, IMAGE_BITMAP
        u.UpdateWindow.argtypes = [wintypes.HWND]
        u.UpdateWindow(v)
        return v
    except Exception:
        return None


def _traer_la_abierta():
    """El programa ya esta abierto y se le dio doble clic otra vez: en vez de un cuadro «ya esta abierto», se trae
    al frente la ventana que hay (Windows; en la Mac lo hace el sistema solo). True si la encontro."""
    if not rutas.ES_WIN:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        yo, halladas = os.getpid(), []

        def ver(h, _):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value != yo and u.IsWindowVisible(h):
                t = ctypes.create_unicode_buffer(120)
                u.GetWindowTextW(h, t, 120)
                if t.value == TITULO_APP:
                    halladas.append(h)
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(ver), 0)
        if not halladas:
            return False
        if u.IsIconic(halladas[0]):
            u.ShowWindow(halladas[0], 9)                   # SW_RESTORE
        u.SetForegroundWindow(halladas[0])
        return True
    except Exception:
        return False


def _quitar_portada(v):
    if v:
        try:
            import ctypes
            from ctypes import wintypes
            ctypes.windll.user32.DestroyWindow.argtypes = [wintypes.HWND]
            ctypes.windll.user32.DestroyWindow(v)
        except Exception:
            pass


def app():
    _tiempo("app()")
    nativa = None if os.environ.get("TRAILER_PRUEBA_ARRASTRE") else _portada_nativa()
    _tiempo("portada nativa")
    from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QPointF, QRectF, QSize, QFileSystemWatcher, QVariantAnimation,
                                QEasingCurve, QEvent, QLockFile)
    from PySide6.QtGui import (QColor, QIcon, QPainter, QPixmap, QPolygonF, QPen, QBrush, QFont, QPainterPath,
                               QRadialGradient, QLinearGradient, QConicalGradient)
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                                   QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                                   QPushButton, QSizeGrip, QSlider, QStackedWidget, QVBoxLayout, QWidget, QScrollArea, QSizePolicy,
                                   QButtonGroup)
    import qt_kit
    _tiempo("PySide6 importado")

    ORO, ORO_CLARO, ORO_OSCURO = QColor("#C9A267"), QColor("#EBCB8F"), QColor("#6E4C24")
    ESMERALDA, ESMERALDA_CLARO, ESMERALDA_OSCURO = QColor("#22C47E"), QColor("#7CF2C0"), QColor("#06301F")
    TEXTO, TENUE, AMBAR, ROJO = "#EAF2F0", "#8FA3A8", "#F2B84B", "#F07A6A"
    # ---- fuentes (medido el 2026-11-16 en una PC con 628 familias; todo esto era «tiempo de carga» al abrir)
    #  1. La primera vez que Qt mide un texto arma la lista de fuentes de la PC: 0,2 s.
    #  2. Si un estilo pide una LISTA de familias («Cascadia Mono», «Consolas», ...) o un texto trae un simbolo que su
    #     fuente no tiene (✓ ☰ ✕ ▶ ⤓ ⚠ ✎, emojis), Qt prepara ademas TODAS las fuentes de reserva: otros 0,4 s. Lo
    #     disparaba el panel de registro (oculto) por su lista, y los simbolos de la barra y las pastillas.
    # Por eso: el estilo lleva UNA familia (la primera de la lista que existe, que es lo que la lista elegia); al abrir
    # no se pinta ningun simbolo de esos (iconos dibujados y equivalentes que la fuente si trae: ≡ × ► ↓); y las dos
    # cosas se preparan en un hilo que llama a Qt directamente, sin el candado de Python (calentar_fuentes).
    FAMILIAS_UI = ("Segoe UI Variable Display", "Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial")
    FAMILIAS_MONO = ("Cascadia Mono", "Consolas", "Menlo", "Courier New")

    def primera_que_hay(familias):
        """La primera familia instalada, entre comillas para el estilo (lo mismo que resolveria la lista entera)."""
        from PySide6.QtGui import QFontDatabase
        for f in familias:
            try:
                if QFontDatabase.hasFamily(f):
                    return '"%s"' % f
            except Exception:
                break
        return ", ".join('"%s"' % f for f in familias)

    def calentar_fuentes():
        """Windows: devuelve preparar(caracter), que mide un caracter llamando a Qt directamente (ctypes) y por eso
        puede correr en otro hilo SIN parar la ventana (medido: el hilo de la ventana sigue a toda velocidad; con
        QFontMetrics desde Python se quedaba parado igual). «I» arma la lista de fuentes de la PC; «✓» prepara las
        de reserva. None si no se puede (otro sistema u otra version de Qt): entonces se hace solo, al primer uso."""
        if not rutas.ES_WIN:
            return None
        try:
            import ctypes
            import shiboken6
            from PySide6.QtGui import QFontMetrics
            try:
                gui = ctypes.CDLL("Qt6Gui.dll")
            except OSError:
                import PySide6
                gui = ctypes.CDLL(os.path.join(os.path.dirname(PySide6.__file__), "Qt6Gui.dll"))
            medir = getattr(gui, "?horizontalAdvance@QFontMetrics@@QEBAHVQChar@@@Z")   # int (QChar) const, x64
            medir.restype = ctypes.c_int
            medir.argtypes = [ctypes.c_void_p, ctypes.c_ushort]
            f = QFont()
            f.setPixelSize(14)
            fm = QFontMetrics(f)
            puntero = shiboken6.getCppPointer(fm)[0]

            def preparar(caracter, _vivo=fm):                 # _vivo: el objeto de Qt no se libera mientras se use
                try:
                    medir(puntero, ord(caracter))
                except Exception:
                    pass
            return preparar
        except Exception:
            return None

    def icono_trazo(tipo, color, lado=14):
        """Iconos de trazo dibujados (palomita, lapiz): nitidos a cualquier escala y sin pedir ninguna fuente."""
        k = 4                                                  # se dibuja a 4x y Qt lo reduce segun la pantalla
        pm = QPixmap(lado * k, lado * k)
        pm.setDevicePixelRatio(k)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), lado * 0.13, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        s = float(lado)
        camino = QPainterPath()
        if tipo == "palomita":
            camino.moveTo(s * 0.16, s * 0.54)
            camino.lineTo(s * 0.40, s * 0.77)
            camino.lineTo(s * 0.86, s * 0.25)
        elif tipo == "lapiz":
            camino.moveTo(s * 0.14, s * 0.86)                  # punta
            camino.lineTo(s * 0.20, s * 0.62)
            camino.lineTo(s * 0.66, s * 0.16)                  # cuerpo
            camino.lineTo(s * 0.84, s * 0.34)
            camino.lineTo(s * 0.38, s * 0.80)
            camino.closeSubpath()
            camino.moveTo(s * 0.55, s * 0.27)                  # la virola
            camino.lineTo(s * 0.73, s * 0.45)
        p.drawPath(camino)
        p.end()
        return QIcon(pm)

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
                        border-radius: 12px; font-size: 24px; padding: 0 0 3px 0; }
    QPushButton#icono:hover, QPushButton#icono:checked { background: rgba(34,196,126,0.18); }
    QFrame#ventanita { background: rgba(14, 30, 38, 0.82); border: 1px solid rgba(255,255,255,0.06);
                       border-radius: 18px; }
    QPushButton#ctrl { background: transparent; border: 1px solid transparent; border-radius: 10px; font-size: 14px;
                       color: %(m)s; padding: 0; }
    QPushButton#ctrl:hover { background: rgba(255,255,255,0.08); color: %(t)s; }
    QPushButton#cerrar:hover { background: #C42B1C; color: white; }
    QPushButton#cerrar { background: transparent; border: 1px solid transparent; border-radius: 10px; color: %(m)s;
                         padding: 0 0 2px 0; font-size: 21px; }
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
                     border-radius: 14px; padding: 8px; font-family: %(mono)s;
                     font-size: 12px; color: #B8C7CB; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 4px; min-height: 24px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar:horizontal { background: transparent; height: 8px; }
    QScrollBar::handle:horizontal { background: rgba(255,255,255,0.15); border-radius: 4px; min-width: 24px; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QAbstractScrollArea::corner { background: transparent; border: none; }
    QToolTip { background: #0E1E26; color: %(t)s; border: 1px solid rgba(255,255,255,0.12); padding: 6px 8px; }
    QFrame#hoja { background: rgba(12, 26, 34, 0.97); border: 1px solid rgba(34,196,126,0.55); border-radius: 22px; }
    QFrame#hoja[modo="soltar"] { border: 2px dashed rgba(34,196,126,0.95); background: rgba(8, 32, 27, 0.94); }
    QLabel#hoja_titulo { font-size: 24px; font-weight: 800; }
    QLabel#hoja_texto { color: #B8C7CB; font-size: 15px; }
    QLabel#hoja_icono { color: #22C47E; font-size: 44px; font-weight: 800; }
    QMessageBox, QDialog { background: #0E1E26; }
    QMessageBox QPushButton, QDialog QPushButton { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.16);
                                                   border-radius: 10px; padding: 8px 16px; font-weight: 600; min-width: 84px; }
    QMessageBox QPushButton:hover, QDialog QPushButton:hover { background: rgba(255,255,255,0.13); }
    QMessageBox QPushButton:default, QDialog QPushButton:default { background: #22C47E; color: #04150D; border-color: #22C47E; }
    """          # se completa al aplicarlo: %(t)s %(m)s y las familias %(f)s %(mono)s (ver estilo_completo)

    def estilo_completo():
        return QSS % {"t": TEXTO, "m": TENUE, "f": primera_que_hay(FAMILIAS_UI), "mono": primera_que_hay(FAMILIAS_MONO)}

    # ------------------------------------------------------------------ trabajos en segundo plano
    class Trabajo(QThread):
        linea = Signal(str)
        avance = Signal(int, str)
        fin = Signal(object)
        fallo = Signal(str)

        def __init__(self, op, funcion=None):
            super().__init__()
            self.op = op
            self.funcion = funcion                     # None = armar todo; o motor.renderizar_editado

        def run(self):
            try:
                res = (self.funcion or motor.armar_todo)(lambda m: self.linea.emit(str(m)),
                                                         lambda p, t: self.avance.emit(int(p), str(t)), **self.op)
                self.fin.emit(res)
            except Exception as ex:
                registro.error("Armado: %s" % traceback.format_exc())      # la traza, al registro (no a la persona)
                self.linea.emit("No se pudo terminar: %s" % ex)
                self.fallo.emit(str(ex))

    class Copia(QThread):
        """Copia ordenada a 1 MATERIAL. Si es un evento nuevo, antes guarda aparte el material del anterior."""
        avance = Signal(float, str, int, int)            # fraccion (por bytes), archivo, i, n
        fin = Signal(object)

        def __init__(self, archivos, tipo=None, examen=None, anterior=None):
            super().__init__()
            self.archivos, self.tipo, self.examen, self.anterior = archivos, tipo, examen, anterior
            self.cancelar = False

        def run(self):
            try:
                res = {}
                carpetas = [a for a in self.archivos if os.path.isdir(a)]
                if self.tipo is None and carpetas and len(carpetas) == len(self.archivos):
                    # (1.5.7, la persona: «si te arrastran la carpeta, es la ruta donde está: simplemente renombras») la
                    # carpeta se usa DONDE ESTA, sin copiar; sus archivos se renombran en su sitio al armar
                    for k, c in enumerate(carpetas):
                        motor.usar_carpeta(c, self.anterior if k == 0 else None)
                        self.avance.emit((k + 1) / float(len(carpetas)), os.path.basename(c), k + 1, len(carpetas))
                    ex = self.examen or {}
                    res.update({"copiados": dict(ex.get("cuenta") or {}), "ya_estaban": 0, "otros": ex.get("otros") or {},
                                "bytes": 0, "en_su_sitio": True,
                                "archivado": (None, 1) if self.anterior is not None else None})
                    self.fin.emit(res)
                    return
                if self.anterior is not None:
                    res["archivado"] = motor.archivar_material(self.anterior)
                ultimo = [0.0, 0]

                def paso(hechos, total, nombre, i, n):   # sin inundar la ventana de avisos
                    f = hechos / float(total or 1)
                    if i != ultimo[1] or f - ultimo[0] >= 0.004:
                        ultimo[0], ultimo[1] = f, i
                        self.avance.emit(f, nombre, i, n)
                res.update(motor.copiar_material(self.archivos, paso, self.tipo, lambda: self.cancelar, self.examen))
                self.fin.emit(res)
            except motor.Cancelado:
                self.fin.emit({"error": "copia cancelada", "cancelada": True})
            except Exception as ex:
                registro.error("Copia de material: %s" % traceback.format_exc())
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

    # ------------------------------------------------------------------ interruptor (en vez de casilla)
    class Interruptor(QCheckBox):
        """Pista redonda con perilla que se desliza: se entiende de un vistazo si esta encendido."""
        def __init__(self, texto):
            super().__init__(texto)
            self.setCursor(Qt.PointingHandCursor)
            self._x = 0.0
            self._anim = QVariantAnimation(self)
            self._anim.setDuration(170)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.valueChanged.connect(self._mover)
            self.toggled.connect(self._cambio)

        def _mover(self, v):
            self._x = float(v)
            self.update()

        def _cambio(self, on):
            if not self.isVisible():
                self._x = 1.0 if on else 0.0
                return
            self._anim.stop()
            self._anim.setStartValue(self._x)
            self._anim.setEndValue(1.0 if on else 0.0)
            self._anim.start()

        def sizeHint(self):
            from PySide6.QtCore import QSize
            return QSize(60 + self.fontMetrics().horizontalAdvance(self.text()), 32)

        def hitButton(self, pos):
            return self.rect().contains(pos)

        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            h, w = 24.0, 44.0
            y = (self.height() - h) / 2
            apagado, encendido = QColor(255, 255, 255, 38), QColor("#22C47E")
            t = self._x
            mezcla = QColor(int(apagado.red() + (encendido.red() - apagado.red()) * t),
                            int(apagado.green() + (encendido.green() - apagado.green()) * t),
                            int(apagado.blue() + (encendido.blue() - apagado.blue()) * t),
                            int(apagado.alpha() + (255 - apagado.alpha()) * t))
            p.setPen(QPen(QColor(255, 255, 255, 50), 1) if t < 0.5 else Qt.NoPen)
            p.setBrush(mezcla)
            p.drawRoundedRect(QRectF(1, y, w, h), h / 2, h / 2)
            r = h - 6
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFFFFF") if self.isEnabled() else QColor("#8FA3A8"))
            p.drawEllipse(QRectF(4 + t * (w - 6 - r), y + 3, r, r))
            p.setPen(QColor(TEXTO if self.isEnabled() else TENUE))
            p.drawText(QRectF(w + 14, 0, self.width() - w - 14, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                       self.text())

    # ------------------------------------------------------------------ hoja sobre la ventana
    class Hoja(QWidget):
        """Fondo oscurecido + tarjeta al centro, sobre toda la ventana: «suelta aqui», preguntas, datos del evento y la
        cuenta atras. Sin cuadros de dialogo del sistema."""
        def __init__(self, padre):
            super().__init__(padre)
            self.modo = None
            self.botones = []
            fuera = QVBoxLayout(self)
            fuera.setContentsMargins(24, 24, 24, 24)
            fuera.addStretch(1)
            fila = QHBoxLayout()
            fila.addStretch(1)
            self.tarjeta = QFrame(objectName="hoja")
            self.tarjeta.setMinimumWidth(380)
            self.tarjeta.setMaximumWidth(640)
            fila.addWidget(self.tarjeta, 10)
            fila.addStretch(1)
            fuera.addLayout(fila)
            fuera.addStretch(1)
            v = QVBoxLayout(self.tarjeta)
            v.setContentsMargins(32, 26, 32, 24)
            v.setSpacing(12)
            self.icono = QLabel("", objectName="hoja_icono")
            self.icono.setAlignment(Qt.AlignCenter)
            self.titulo = QLabel("", objectName="hoja_titulo")
            self.titulo.setAlignment(Qt.AlignCenter)
            self.titulo.setWordWrap(True)
            self.texto = QLabel("", objectName="hoja_texto")
            self.texto.setAlignment(Qt.AlignCenter)
            self.texto.setWordWrap(True)
            self.zona = QVBoxLayout()
            self.fila_b = QHBoxLayout()
            self.fila_b.setSpacing(10)
            for x in (self.icono, self.titulo, self.texto):
                v.addWidget(x)
            v.addLayout(self.zona)
            v.addSpacing(6)
            v.addLayout(self.fila_b)
            self.hide()

        def mostrar(self, modo, titulo, texto="", botones=(), contenido=None, icono=""):
            self.modo = modo
            self.icono.setText(icono)
            self.icono.setVisible(bool(icono))
            self.titulo.setText(titulo)
            self.texto.setText(texto)
            self.texto.setVisible(bool(texto))
            for lay in (self.zona, self.fila_b):
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w is not None:
                        w.setParent(None)
                        w.deleteLater()
            if contenido is not None:
                self.zona.addWidget(contenido)
            self.botones = []
            if botones:
                self.fila_b.addStretch(1)
                for txt, accion, primario in botones:
                    b = QPushButton(txt, objectName="boton" if primario else "borde")
                    b.setCursor(Qt.PointingHandCursor)
                    b.clicked.connect(accion)
                    self.fila_b.addWidget(b)
                    self.botones.append(b)
                self.fila_b.addStretch(1)
            repulir(self.tarjeta, modo=modo)
            self.setGeometry(self.parentWidget().rect())
            self.show()
            self.raise_()

        def ocultar(self, modo=None):
            if modo is None or self.modo == modo:
                self.modo = None
                self.hide()

        def paintEvent(self, _):
            QPainter(self).fillRect(self.rect(), QColor(3, 9, 13, 190))

        def mousePressEvent(self, e):
            e.accept()                            # lo de abajo no recibe clics mientras la hoja esta abierta

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
            self._fondo = None                  # (ancho, alto, escala, QPixmap): degradados y constelaciones, ya pintados
            reloj = QTimer(self)
            reloj.timeout.connect(self._tic)
            reloj.start(70)

        def _tic(self):
            self.t += 0.07
            if self.isVisible() and not self.window().isMinimized():      # minimizada no se pinta nada
                self.update()

        def pausar(self, si):                   # bajo la escena de Inicio no hace falta animarlo
            r = self.findChild(QTimer)
            if r is not None:
                r.stop() if si else r.start(70)

        def resizeEvent(self, e):
            super().resizeEvent(e)
            if getattr(self, "al_cambiar", None):
                self.al_cambiar()

        def _pintar_fondo(self, w, h, escala):
            """Lo que no cambia (dos degradados a toda la ventana y las constelaciones), pintado una sola vez por
            tamano: rellenar esos degradados en cada latido costaba varios ms y arrastraba a todo lo de encima."""
            pm = QPixmap(max(1, int(w * escala)), max(1, int(h * escala)))
            pm.setDevicePixelRatio(escala)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            todo = QRectF(0, 0, w, h)
            g = QRadialGradient(QPointF(w * 0.5, h * 0.45), max(w, h) * 0.75)
            g.setColorAt(0.0, QColor("#12303A"))
            g.setColorAt(0.45, QColor("#0B1C26"))
            g.setColorAt(1.0, QColor("#050C13"))
            p.fillRect(todo, g)
            neb = QRadialGradient(QPointF(w * 0.82, h * 0.30), w * 0.35)
            neb.setColorAt(0.0, QColor(40, 90, 110, 40))
            neb.setColorAt(1.0, QColor(40, 90, 110, 0))
            p.fillRect(todo, neb)
            p.setPen(QPen(QColor(150, 190, 200, 45), 1))
            for linea in self.constelaciones:
                pts = [QPointF(x * w, y * h) for x, y in linea]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
                p.setBrush(QColor(200, 230, 235, 150))
                for q in pts:
                    p.drawEllipse(q, 1.8, 1.8)
            p.end()
            return pm

        def paintEvent(self, _):
            w, h, escala = self.width(), self.height(), self.devicePixelRatioF()
            if self._fondo is None or self._fondo[:3] != (w, h, escala):
                self._fondo = (w, h, escala, self._pintar_fondo(w, h, escala))
            p = QPainter(self)
            p.drawPixmap(0, 0, self._fondo[3])
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            for x, y, r, fase, vel in self.estrellas:
                a = 70 + 110 * (0.5 + 0.5 * math.sin(self.t * vel + fase))
                p.setBrush(QColor(220, 240, 245, int(a)))
                p.drawEllipse(QPointF(x * w, y * h), r * 0.6, r * 0.6)

    def icono_app():
        """El icono del programa (icono_app.py) en varios tamanos: la barra de tareas elige el que le toca."""
        hecho = os.path.join(rutas.RECURSOS, "icono.ico")       # lo deja hacer_portada.py; dibujarlo aqui costaba 0,12 s
        if os.path.exists(hecho):
            ico = QIcon(hecho)
            if not ico.isNull():
                return ico
        import icono_app as ic
        ico = QIcon()
        for t in (16, 24, 32, 48, 64, 128, 256):
            ico.addPixmap(QPixmap.fromImage(ic.dibujar(t)))
        return ico

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
            _tiempo("  icono")
            self.setAcceptDrops(True)
            self.setMinimumSize(880, 580)                 # cabe en una laptop de 1366 x 768 al 125 %
            self.resize(1240, 860)
            self.trabajo = self.copia = self.cheq = None
            self.flujo = None                    # soltar una carpeta: None | mirando | pregunta | copiando | datos | cuenta
            self._ultimo_fallo = None
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
            self.b_log = QPushButton("≡", objectName="icono", checkable=True)       # ≡ si esta en la fuente; ☰ no
            self.b_log.setFixedSize(44, 44)
            self.b_log.setToolTip("Ver lo que va haciendo")
            barra.addWidget(self.b_log)
            barra.addSpacing(10)
            ctrls = QFrame(objectName="ventanita")
            hc = QHBoxLayout(ctrls)
            hc.setContentsMargins(6, 4, 6, 4)
            for txt, nombre, acc in (("—", "ctrl", self.showMinimized), ("□", "ctrl", self._maximizar),
                                     ("×", "cerrar", self.close)):          # × si esta en la fuente; ✕ no
                b = QPushButton(txt, objectName=nombre)
                b.setFixedSize(38, 30)
                b.clicked.connect(acc)
                hc.addWidget(b)
            barra.addWidget(ctrls)
            raiz.addLayout(barra)
            _tiempo("  barra")

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
            self.b_actualizar = QPushButton("Instalar ahora", objectName="boton")      # aparece con una version nueva lista
            self.b_actualizar.setCursor(Qt.PointingHandCursor)
            self.b_actualizar.clicked.connect(self._instalar_ahora)
            self.b_actualizar.hide()
            ha.addWidget(self.b_actualizar)
            ha.addWidget(self.aviso_h)
            raiz.addWidget(self.aviso)
            self.actualizacion = None            # {"version", "ruta"} cuando ya se bajo una version nueva
            self._instalando = False

            # --- paginas + registro
            medio = self._medio = QHBoxLayout()
            self.paginas = QStackedWidget()
            medio.addWidget(self.paginas, 1)
            self.registro = QPlainTextEdit(readOnly=True)
            self.registro.setFixedWidth(400)
            self.registro.hide()
            medio.addWidget(self.registro)
            raiz.addLayout(medio, 1)
            self.paginas.addWidget(self._pagina_inicio())
            _tiempo("  pagina Inicio")
            for pag in (self._pagina_material(), self._pagina_textos(), self._pagina_ajustes()):
                sa = QScrollArea()                       # en una pantalla chica se desplazan en vez de agrandar la ventana
                sa.setWidgetResizable(True)
                sa.setFrameShape(QFrame.NoFrame)
                sa.setStyleSheet("QScrollArea { background: transparent; border: none; }")
                sa.viewport().setAutoFillBackground(False)
                sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                sa.setWidget(pag)
                pag.setAutoFillBackground(False)        # setWidget lo enciende: el cielo debe verse detras
                self.paginas.addWidget(sa)
            self.grupo_tabs.idClicked.connect(self.paginas.setCurrentIndex)
            _tiempo("  demas paginas")
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
            self.b_log.toggled.connect(self._ancho_registro)
            self.paginas.currentChanged.connect(self._ancho_registro)
            self.hoja = Hoja(self.cielo)             # «suelta aqui», preguntas y cuenta atras, sobre toda la ventana
            _tiempo("  escena")

            pie = QHBoxLayout()
            pie.addStretch(1)
            pie.addWidget(QSizeGrip(self))
            raiz.addLayout(pie)

            # --- vigilancia de carpetas y chequeo
            self.vigia = QFileSystemWatcher([d for d in rutas.CARPETAS.values() if os.path.isdir(d)], self)
            self.espera = QTimer(self, singleShot=True, interval=800)
            self.espera.timeout.connect(self._revisar_material_fondo)
            self.vigia.directoryChanged.connect(lambda _: self.espera.start())
            self.t_dv = QTimer(self)
            self.t_dv.timeout.connect(self._ver_davinci)
            self.t_dv.start(10000)
            QApplication.instance().installEventFilter(self)       # bordes para cambiar el tamano
            for b in self.tabs.values():                           # que no se corte el texto en una ventana angosta
                b.setMinimumWidth(b.sizeHint().width())            # (al final: mide texto, y las fuentes ya cargaron)
            self._chips_editable(bool(self.est.get("evento") and self.est.get("timelines")))
            _tiempo("  final")
            QTimer.singleShot(300, self._arranque)

        # ============================================================== paginas
        def _pagina_inicio(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            import boton_go
            # el astrolabio va en un hueco que toma el espacio libre y NO esta en el layout: asi su tamano fijo no impide
            # achicar la ventana (en una laptop de 768 px de alto no cabia); _centrar_boton lo pone en medio
            self.hueco_boton = QWidget()
            self.hueco_boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.hueco_boton.setMinimumHeight(200)
            self.boton = boton_go.BotonGo(lado=380)
            self.boton.setParent(self.hueco_boton)
            self.boton.clicked.connect(lambda *_: self._play())
            v.addWidget(self.hueco_boton, 1)
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
            # la linea de cada evento queda editable en DaVinci: retocar y volver a sacar el video sin rearmar
            self.chip_editar = QPushButton("Editar en DaVinci", objectName="chip")
            self.chip_editar.setCursor(Qt.PointingHandCursor)
            self.chip_editar.setToolTip("Abre DaVinci en la página Edición con la línea de este evento: retoca lo que "
                                        "no te guste (cortes, textos, color, música).")
            self.chip_editar.clicked.connect(self._editar_en_davinci)
            fila_c.addWidget(self.chip_editar)
            self.chip_render = QPushButton("Renderizar lo editado", objectName="chip")
            self.chip_render.setCursor(Qt.PointingHandCursor)
            self.chip_render.setToolTip("Saca de nuevo los videos con lo que cambiaste a mano en DaVinci, con el audio "
                                        "a -14 LUFS, SIN volver a armar (▶ sí arma desde cero).")
            self.chip_render.clicked.connect(self._renderizar_editado)
            fila_c.addWidget(self.chip_render)
            self.chip_editar.hide()                 # se muestran al final de __init__: aqui aun no tienen ventana y
            self.chip_render.hide()                 # mostrarlos crearia una ventanita suelta (0,15 s y un parpadeo)
            self.chip_cancelar = QPushButton("Cancelar la copia", objectName="chip")
            self.chip_cancelar.setCursor(Qt.PointingHandCursor)
            self.chip_cancelar.clicked.connect(self._cancelar_copia)
            self.chip_cancelar.hide()
            fila_c.addWidget(self.chip_cancelar)
            fila_c.addStretch(1)
            v.addLayout(fila_c)
            v.addSpacing(6)
            # formatos: que versiones se arman en horizontal (16:9) y cuales en vertical (9:16, solo videos verticales)
            eleg_h, eleg_v = versiones_guardadas(self.est)
            self._palomita = icono_trazo("palomita", "#B9FFE0", 13)       # dibujada: «✓» no esta en la fuente
            self.pills, self.pills_v, self.etqs_formato, self.bs_todas = {}, {}, [], []
            for etq, ayuda, pills, elegidas in (
                    ("HORIZONTAL", "16:9 · usa los videos horizontales y también los verticales", self.pills, eleg_h),
                    ("VERTICAL", "9:16 para celular · solo usa los videos grabados en vertical", self.pills_v, eleg_v)):
                fila_p = QHBoxLayout()
                fila_p.addStretch(1)
                l = QLabel(etq, objectName="etq")
                l.setFixedWidth(104)
                l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                l.setToolTip(ayuda)
                fila_p.addWidget(l)
                fila_p.addSpacing(6)
                for ver in motor.VERSIONES:
                    b = QPushButton((" " if ver in elegidas else "") + VERSION_TEXTO[ver], objectName="pill", checkable=True)
                    b.setIconSize(QSize(13, 13))
                    b.setIcon(self._palomita if ver in elegidas else QIcon())
                    b.setCursor(Qt.PointingHandCursor)
                    b.setMinimumWidth(106)        # con o sin ✓ miden igual: las dos filas quedan alineadas
                    b.setChecked(ver in elegidas)
                    b.setToolTip(ayuda)
                    b.toggled.connect(self._cambio_plantillas)
                    pills[ver] = b
                    fila_p.addWidget(b)
                todas = QPushButton("Todas", objectName="pill")
                todas.setCursor(Qt.PointingHandCursor)
                todas.setToolTip(ayuda)
                todas.clicked.connect(lambda _=False, ps=pills: [x.setChecked(True) for x in ps.values()])
                fila_p.addWidget(todas)
                fila_p.addStretch(1)
                v.addLayout(fila_p)
                v.addSpacing(5)
                self.etqs_formato.append(l)
                self.bs_todas.append(todas)
            v.addSpacing(3)
            self._pintar_evento()
            return w

        def _tarjeta_carpeta(self, tipo, titulo, ayuda):
            t = QFrame(objectName="carpeta")
            t.setToolTip(ayuda)
            g = QGridLayout(t)
            g.setContentsMargins(20, 14, 16, 14)
            g.setHorizontalSpacing(12)
            g.setVerticalSpacing(2)
            g.addWidget(QLabel(titulo, objectName="etq"), 0, 0)
            n = QLabel("0", objectName="grande")
            g.addWidget(n, 1, 0)
            e = QLabel("", objectName="estado_c")
            g.addWidget(e, 2, 0)
            col = QVBoxLayout()
            col.setSpacing(6)
            b1 = QPushButton("Agregar…", objectName="boton")
            b1.clicked.connect(lambda: self._agregar(tipo))
            b2 = QPushButton("Abrir", objectName="borde")
            b2.clicked.connect(lambda: rutas.abrir(rutas.CARPETAS[tipo]))
            for b in (b1, b2):
                b.setCursor(Qt.PointingHandCursor)
                col.addWidget(b)
            g.addLayout(col, 0, 1, 3, 1, Qt.AlignRight | Qt.AlignVCenter)
            g.setColumnStretch(0, 1)
            self.tarjetas[tipo] = (t, n, e)
            return t

        def _pagina_material(self):
            import linea_dia
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(26, 14, 26, 6)
            v.setSpacing(12)
            cab = QHBoxLayout()
            tit = QLabel("Material del evento", objectName="titulo")
            tit.setStyleSheet("font-size: 30px;")
            cab.addWidget(tit)
            cab.addStretch(1)
            self.l_copia = QLabel("↓  Arrastra fotos, videos o carpetas a la ventana: se ordenan solos")
            self.l_copia.setWordWrap(True)
            self.l_copia.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.l_copia.setStyleSheet("color:%s;" % TENUE)
            cab.addWidget(self.l_copia)
            v.addLayout(cab)
            fila = QHBoxLayout()
            fila.setSpacing(14)
            self.tarjetas = {}
            fila.addWidget(self._tarjeta_carpeta("foto", "FOTOS", "Se usan 8 para los destellos de la intro: "
                                                 "pon al menos 8 (mejor muchas: el programa elige las más nítidas "
                                                 "y no repite fotos de una ráfaga)."))
            fila.addWidget(self._tarjeta_carpeta("video", "VIDEOS", "Videos de cámara y celular de todo el evento: "
                                                 "maquillaje, iglesia y fiesta."))
            fila.addWidget(self._tarjeta_carpeta("dron", "DRON", "Tomas aéreas (opcional). Abren el tráiler "
                                                 "y las versiones largas."))
            v.addLayout(fila)
            # --- como quedo organizado (el analisis)
            org = QFrame(objectName="vidrio")
            go = QVBoxLayout(org)
            go.setContentsMargins(22, 16, 22, 14)
            go.setSpacing(10)
            fila_t = QHBoxLayout()
            t2 = QLabel("Cómo quedó organizado")
            t2.setStyleSheet("font-size: 18px; font-weight: 800;")
            fila_t.addWidget(t2)
            self.l_org = QLabel("")
            self.l_org.setStyleSheet("color:%s;" % TENUE)
            fila_t.addWidget(self.l_org, 1)
            self.b_analizar = QPushButton("Analizar ahora", objectName="boton")
            self.b_analizar.setCursor(Qt.PointingHandCursor)
            self.b_analizar.setToolTip("Revisa hora, nitidez, luz, color y audio de cada archivo y los ordena por "
                                       "momento. Lo ya analizado no se repite: después ▶ va directo.")
            self.b_analizar.clicked.connect(self._analizar_ahora)
            fila_t.addWidget(self.b_analizar)
            go.addLayout(fila_t)
            self.linea = linea_dia.LineaDia()
            self.linea.limites_cambiados.connect(self._limites_cambiados)
            self.linea.cuentas_vivas.connect(self._pintar_cuentas)
            go.addWidget(self.linea, 1)
            fila_m = QHBoxLayout()
            fila_m.setSpacing(10)
            self.l_momentos = {}
            for mom in linea_dia.MOMENTOS:
                l = QLabel("")
                l.setStyleSheet("background: rgba(4,14,20,0.6); border: 1px solid %s; border-radius: 10px; "
                                "padding: 8px 12px;" % linea_dia.COLOR[mom].name())
                l.setTextFormat(Qt.RichText)
                fila_m.addWidget(l, 1)
                self.l_momentos[mom] = l
            go.addLayout(fila_m)
            self.l_avisos = QLabel("")
            self.l_avisos.setWordWrap(True)
            self.l_avisos.setTextFormat(Qt.RichText)
            self.l_avisos.setStyleSheet("color:%s;" % AMBAR)
            go.addWidget(self.l_avisos)
            ayuda = QLabel("¿Algo cayó en el momento equivocado? Arrastra las etiquetas <b>Iglesia</b> y <b>Fiesta</b> "
                           "a la hora en que empezó cada una. Lo hueco se ordenó por lo que se ve (su cámara no tenía "
                           "buena hora).")
            ayuda.setWordWrap(True)
            ayuda.setStyleSheet("color:%s; font-size: 12px;" % TENUE)
            go.addWidget(ayuda)
            v.addWidget(org, 1)
            self.analisis = None
            return w

        # ============================================================== organizacion (analisis del material)
        def _cargar_organizacion(self):
            """Pinta el ultimo analisis guardado y dice si sigue al dia con lo que hay en 1 MATERIAL."""
            import analizar_material as am

            def leer():
                ult = am.leer_ultimo()
                return ult, bool(ult.get("items")) and ult.get("huella") == am.huella(rutas.BASE), am.no_compatibles()
            qt_kit.correr_en_hilo(self, leer, lambda r, e: self._pintar_organizacion(*r) if r else None)

        def _pintar_organizacion(self, res, al_dia, raros=()):
            import linea_dia
            items = res.get("items") or []
            self.linea.poner(items, res.get("fecha"), res.get("momentos"))
            self.linea.editable = bool(items) and self.trabajo is None and self.analisis is None
            nota_raros = ""
            if raros:
                nota_raros = "%d archivo%s no se usa%s (formato no compatible o vacío): %s" % (
                    len(raros), "s" if len(raros) > 1 else "", "n" if len(raros) > 1 else "",
                    ", ".join("%s/%s" % c for c in raros[:3]) + ("…" if len(raros) > 3 else ""))
            if not items:
                self.l_org.setText("  ·  todavía sin analizar: pulsa «Analizar ahora» o ►")
                self.b_analizar.setText("Analizar ahora")
                for l in self.l_momentos.values():
                    l.setText("")
                self.l_avisos.setText("⚠  " + nota_raros if nota_raros else "")
                return
            try:
                import datetime as _dt
                f = _dt.date.fromisoformat(res["fecha"])
                dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
                meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                         "octubre", "noviembre", "diciembre")
                fecha = "%s %d de %s de %d" % (dias[f.weekday()], f.day, meses[f.month - 1], f.year)
            except Exception:
                fecha = res.get("fecha") or ""
            camaras = res.get("camaras") or []
            self.l_org.setText("  ·  %s  ·  %d archivos  ·  %d cámara%s%s" % (
                fecha, len(items), len(camaras), "" if len(camaras) == 1 else "s",
                "" if al_dia else "  ·  hay material nuevo: pulsa «Analizar ahora»"))
            self.b_analizar.setText("Analizar ahora" if not al_dia else "Volver a analizar")
            self._pintar_cuentas(self.linea.cuentas())
            av = list(res.get("avisos") or [])
            if nota_raros:
                av.append(nota_raros)
            vert = sum(1 for i in items if i["tipo"] != "foto" and not i.get("horizontal", True))
            if vert:                     # ya no quedan fuera: entran al horizontal y son los del formato vertical
                varios = vert > 1
                if self.ch_vert.isChecked():
                    av.append("%d video%s vertical%s (celular parado): entra%s entero%s al video horizontal, con los "
                              "lados desenfocados, y %s del formato VERTICAL." % (
                                  vert, "s" if varios else "", "es" if varios else "", "n" if varios else "",
                                  "s" if varios else "", "son los" if varios else "es el"))
                else:
                    av.append("%d video%s vertical%s (celular parado): fuera del video horizontal (lo apagaste en "
                              "Ajustes); %s del formato VERTICAL." % (
                                  vert, "s" if varios else "", "es" if varios else "", "son los" if varios else "es el"))
            for mom in linea_dia.MOMENTOS:
                if not any(i["tipo"] != "foto" and i.get("momento") == mom and not i.get("descartar") for i in items):
                    av.append("%s no tiene videos: esa parte se llena con material de todo el evento." %
                              linea_dia.NOMBRE[mom])
            self.l_avisos.setText("<br>".join("⚠  " + a.replace("&", "&amp;").replace("<", "&lt;") for a in av[:6]))

        def _pintar_cuentas(self, cuentas):
            import linea_dia
            for mom, l in self.l_momentos.items():
                fotos, vids, mins = cuentas.get(mom, (0, 0, 0.0))
                l.setText("<span style='color:%s; font-weight:800;'>●  %s</span><br>"
                          "<span style='color:#EAF2F0;'>%d fotos · %d videos · %.0f min</span>" % (
                              linea_dia.COLOR[mom].name(), linea_dia.NOMBRE[mom], fotos, vids, mins))

        def _analizar_ahora(self):
            if self.trabajo is not None or self.analisis is not None:
                return
            if self.copia is not None:
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            import analizar_material as am
            self.analisis = True
            self.linea.editable = False
            self.b_analizar.setEnabled(False)
            self.b_analizar.setText("Analizando…")
            self._avisar("Analizando el material (la primera vez tarda unos minutos; después ▶ va directo)…")
            ultima = {"t": ""}

            def log(m):
                ultima["t"] = str(m)
                registro.info(m)

            def correr():
                if not motor.CANDADO.acquire(timeout=1):
                    raise RuntimeError("ya hay un trabajo en marcha")
                try:
                    return am.analizar(rutas.BASE, log=log)
                finally:
                    motor.CANDADO.release()
            self.t_analisis = QTimer(self)
            self.t_analisis.timeout.connect(lambda: self.l_org.setText("  ·  " + ultima["t"][:90]) if ultima["t"] else None)
            self.t_analisis.start(400)
            qt_kit.correr_en_hilo(self, correr, self._fin_analisis)

        def _fin_analisis(self, res, error):
            self.t_analisis.stop()
            self.analisis = None
            self.b_analizar.setEnabled(True)
            if error is not None:
                self._avisar("No se pudo analizar: %s" % error, "error")
                self._cargar_organizacion()
                return
            self._avisar("Material analizado y ordenado por momento.")
            self._cargar_organizacion()

        def _limites_cambiados(self, limites):
            import analizar_material as am
            self.linea.editable = False

            def correr():
                am.guardar_momentos(limites)
                return am.reclasificar(rutas.BASE, log=registro.info)

            def listo(res, error):
                if error is not None:
                    self._avisar("No pude guardar los límites: %s" % error, "error")
                else:
                    self._avisar("Listo: Iglesia empieza a las %s y Fiesta a las %s. Se usa en el próximo ▶." % (
                        limites.get("IGLESIA", "?"), limites.get("FIESTA", "?")))
                self._cargar_organizacion()
            qt_kit.correr_en_hilo(self, correr, listo)

        def _pagina_textos(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(26, 20, 26, 10)
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

        def _pintar_ruido_dv(self, info=None):
            info = info if info is not None else motor.estado_ruido_davinci()
            if info.get("hay"):
                vio = ", ".join(info.get("de_ruido") or [])
                self.l_ruido_dv.setText("Guardado el %s del clip «%s»%s. Se aplica a todas las tomas al armar." % (
                    info.get("fecha", "?"), info.get("clip", "?"),
                    " (%s)" % vio if vio else " (ojo: en ese clip no vi reducción de ruido)"))
            else:
                self.l_ruido_dv.setText("Sin guardar: las tomas usan el filtro del programa. Para usar el de DaVinci, "
                                        "déjalo a tu gusto en un clip (página Color) y guárdalo aquí.")
            self.b_ruido_quitar.setVisible(bool(info.get("hay")))

        def _guardar_ruido_dv(self):
            if self.trabajo is not None:
                self._avisar("Espera a que termine el trabajo en curso para guardar el ruido de DaVinci.", "warn")
                return
            self.b_ruido_dv.setEnabled(False)
            self.l_ruido_dv.setText("Leyendo el clip que DaVinci tiene bajo el cursor…")

            def listo(info, error):
                self.b_ruido_dv.setEnabled(True)
                if error is not None:
                    registro.error("Ruido de DaVinci: %s" % error)
                    self._pintar_ruido_dv()
                    self._avisar("No se pudo guardar el ruido de DaVinci: %s" % error, "error")
                    return
                self._pintar_ruido_dv(info)
                if info.get("de_ruido"):
                    self._avisar("Ruido de DaVinci guardado. Vuelve a armar para que se aplique a todas las tomas.", "ok")
                else:
                    self._avisar("Guardé el clip, pero no vi reducción de ruido en él. Revisa que el cursor de DaVinci "
                                 "esté sobre el clip correcto y vuelve a guardar.", "warn")
            qt_kit.correr_en_hilo(self, lambda: motor.capturar_ruido_davinci(registro.info), listo)

        def _quitar_ruido_dv(self):
            self._pintar_ruido_dv(motor.quitar_ruido_davinci())
            self._avisar("Ruido de DaVinci quitado: las tomas vuelven a usar el filtro del programa al armar.", "info")

        def _pagina_ajustes(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(26, 20, 26, 10)
            tit = QLabel("Ajustes", objectName="titulo")
            tit.setStyleSheet("font-size: 30px;")
            v.addWidget(tit)
            caja = QFrame(objectName="vidrio")
            g = QGridLayout(caja)
            g.setContentsMargins(26, 24, 26, 24)
            g.setVerticalSpacing(16)
            self.ch_render = Interruptor("Renderizar al terminar (si no, solo arma las timelines en DaVinci)")
            self.ch_render.setChecked(self.est.get("renderizar", True))
            self.ch_igualar = Interruptor("Igualar luz y balance de blancos de cada toma")
            self.ch_igualar.setChecked(self.est.get("igualar", True))
            self.ch_auto = Interruptor("Al soltar una carpeta, ordenarla y armar el tráiler solo")
            self.ch_auto.setChecked(self.est.get("auto_armar", True))
            g.addWidget(self.ch_render, 0, 0, 1, 3)
            g.addWidget(self.ch_igualar, 1, 0, 1, 3)
            g.addWidget(self.ch_auto, 4, 0, 1, 3)
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
            # el ruido propio de DaVinci: la persona lo deja a su gusto en un clip y aqui se guarda para todas las tomas
            l_dv = QLabel("Ruido de DaVinci")
            l_dv.setStyleSheet("color:%s; font-weight:600;" % TENUE)
            self.l_ruido_dv = QLabel("")
            self.l_ruido_dv.setWordWrap(True)
            self.l_ruido_dv.setStyleSheet("color:%s;" % TENUE)
            self.b_ruido_dv = QPushButton("Guardar el del clip actual", objectName="borde")
            self.b_ruido_dv.setToolTip("En DaVinci, página Color: deja la reducción de ruido a tu gusto en un clip, "
                                       "deja el cursor sobre él y pulsa aquí. Al armar se aplica a todas las tomas.")
            self.b_ruido_dv.setCursor(Qt.PointingHandCursor)
            self.b_ruido_dv.clicked.connect(self._guardar_ruido_dv)
            self.b_ruido_quitar = QPushButton("Quitar", objectName="borde")
            self.b_ruido_quitar.setCursor(Qt.PointingHandCursor)
            self.b_ruido_quitar.clicked.connect(self._quitar_ruido_dv)
            fila_dv = QHBoxLayout()
            fila_dv.setSpacing(10)
            fila_dv.addWidget(self.l_ruido_dv, 1)
            fila_dv.addWidget(self.b_ruido_dv)
            fila_dv.addWidget(self.b_ruido_quitar)
            g.addWidget(l_dv, 3, 0)
            g.addLayout(fila_dv, 3, 1, 1, 2)
            self._pintar_ruido_dv()
            # la voz original (la palabra del pastor, brindis, discursos) sobre la musica: en que versiones va
            l_voz = QLabel("Voz original")
            l_voz.setStyleSheet("color:%s; font-weight:600;" % TENUE)
            l_voz.setToolTip("Lo que se dice en el evento (la palabra del pastor, el brindis, los discursos) suena sobre "
                             "la música. Solo entra cuando alguien habla de corrido: nada de ruidos ni voces sueltas.")
            guardada = self.est.get("voz") if isinstance(self.est.get("voz"), dict) else {}
            self.ch_voz = {}
            fila_voz = QHBoxLayout()
            fila_voz.setSpacing(18)
            for clave, texto in (("1min", "1 min"), ("3min", "3 min"), ("15min", "15 min")):
                ch = Interruptor(texto)
                ch.setChecked(bool(guardada.get(clave, motor.VOZ_DEFECTO[clave])))
                self.ch_voz[clave] = ch
                fila_voz.addWidget(ch)
            nota_voz = QLabel("En el de 30 min va siempre")
            nota_voz.setStyleSheet("color:%s;" % TENUE)
            fila_voz.addWidget(nota_voz)
            fila_voz.addStretch(1)
            g.addWidget(l_voz, 5, 0)
            g.addLayout(fila_voz, 5, 1, 1, 2)
            self.ch_vert = Interruptor("En el formato horizontal, usar también los videos verticales (de celular)")
            self.ch_vert.setChecked(bool(self.est.get("usar_verticales", True)))
            self.ch_vert.setToolTip("Encendido (lo normal), el video horizontal acepta videos horizontales y verticales: "
                                    "los verticales entran recortados para llenar la pantalla y DaVinci reencuadra "
                                    "siguiendo a la persona. Apagado, quedan fuera del horizontal (siguen en el media "
                                    "pool). El formato vertical de Inicio usa siempre solo los verticales.")
            g.addWidget(self.ch_vert, 6, 0, 1, 3)
            g.setColumnStretch(1, 1)
            v.addWidget(caja)
            fila = QHBoxLayout()
            for txt, acc in (("Clasificación del evento", self._clasificacion),
                             ("Abrir DaVinci Resolve", rutas.abrir_resolve),
                             ("Videos terminados", self._abrir_terminado),
                             ("Nombres originales", self._restaurar_nombres),
                             ("Carpeta del programa", lambda: rutas.abrir(rutas.PROGRAMA))):
                b = QPushButton(txt, objectName="borde")
                b.clicked.connect(acc)
                fila.addWidget(b)
            fila.addStretch(1)
            v.addLayout(fila)
            caja2 = QFrame(objectName="vidrio")
            g2 = QGridLayout(caja2)
            g2.setContentsMargins(26, 18, 26, 18)
            l2 = QLabel("Eventos terminados")             # (1.5.7) el trabajo va por dentro; a la vista, solo esto
            l2.setStyleSheet("color:%s; font-weight:600;" % TENUE)
            self.l_base = QLabel(rutas.SALIDA)
            self.l_base.setWordWrap(True)
            g2.addWidget(l2, 0, 0)
            g2.addWidget(self.l_base, 0, 1)
            if rutas.CONGELADO:
                b_base = QPushButton("Cambiar…", objectName="borde")
                b_base.clicked.connect(self._cambiar_base)
                g2.addWidget(b_base, 0, 2)
            g2.setColumnStretch(1, 1)
            v.addWidget(caja2)
            caja3 = QFrame(objectName="vidrio")                 # actualizaciones (como CineCaptions)
            g3 = QHBoxLayout(caja3)
            g3.setContentsMargins(26, 14, 26, 14)
            l3 = QLabel("Versión %s" % rutas.version())
            l3.setStyleSheet("font-weight:700;")
            g3.addWidget(l3)
            self.l_act = QLabel("Se actualiza sola: busca versiones nuevas al abrir y cada %d horas, aunque esté cerrado."
                                % 4)
            self.l_act.setStyleSheet("color:%s;" % TENUE)
            self.l_act.setWordWrap(True)
            g3.addWidget(self.l_act, 1)
            self.b_buscar = QPushButton("Buscar actualizaciones", objectName="borde")
            self.b_buscar.setCursor(Qt.PointingHandCursor)
            self.b_buscar.clicked.connect(lambda: self._buscar_actualizacion(manual=True))
            g3.addWidget(self.b_buscar)
            v.addWidget(caja3)
            caja4 = QFrame(objectName="vidrio")                 # (1.5.7) la IA local que ve cada toma
            g4 = QHBoxLayout(caja4)
            g4.setContentsMargins(26, 14, 26, 14)
            l4 = QLabel("IA local")
            l4.setStyleSheet("font-weight:700;")
            g4.addWidget(l4)
            self.l_ia = QLabel("Revisando…")
            self.l_ia.setStyleSheet("color:%s;" % TENUE)
            self.l_ia.setWordWrap(True)
            g4.addWidget(self.l_ia, 1)
            self.b_ia = QPushButton("Instalar", objectName="borde")
            self.b_ia.setCursor(Qt.PointingHandCursor)
            self.b_ia.hide()
            self.b_ia.clicked.connect(self._instalar_ia)
            g4.addWidget(self.b_ia)
            v.addWidget(caja4)
            QTimer.singleShot(1500, self._revisar_ia)
            pie = QLabel("Versión %s  ·  registro: %s" % (rutas.version(), rutas.REGISTRO))
            pie.setStyleSheet("color:%s; font-size:12px;" % TENUE)
            pie.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(pie)
            v.addStretch(1)
            return w

        # ============================================================== IA local (1.5.7)
        def _revisar_ia(self):
            """En un hilo: ¿hay IA local que vea las tomas? (Ollama con un modelo de vision)."""
            import vision_ia
            qt_kit.correr_en_hilo(self, vision_ia.estado, self._pintar_ia, baja=True)

        def _pintar_ia(self, r, error):
            if error is not None or not r:
                self.l_ia.setText("No se pudo revisar la IA local.")
                return
            texto, accion = r
            self.l_ia.setText(texto)
            self.b_ia.setVisible(accion is not None)
            self.b_ia.setEnabled(True)
            self.b_ia.setText({"modelo": "Instalar el modelo", "ollama": "Descargar Ollama"}.get(accion, "Instalar"))
            self._accion_ia = accion

        def _instalar_ia(self):
            import vision_ia
            if getattr(self, "_accion_ia", None) == "ollama":
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl(vision_ia.DESCARGA_OLLAMA))
                self.l_ia.setText("Instala Ollama (se abrió su página), abre el programa otra vez y pulsa «Instalar el modelo».")
                return
            r = QMessageBox.question(self, TITULO_APP, "¿Bajar el modelo de IA local %s (unos 6 GB)?\n\nCon él el programa ve "
                                     "cada toma (iglesia, fiesta, preparativos, los momentos clave) y arma mejor. Se baja "
                                     "una sola vez; luego todo es local, sin internet." % vision_ia.MODELO_RECOMENDADO)
            if r != QMessageBox.Yes:
                return
            self.b_ia.setEnabled(False)
            self.l_ia.setText("Bajando el modelo… (puede tardar varios minutos)")
            qt_kit.correr_en_hilo(self, lambda: vision_ia.instalar_modelo(registro.info),
                                  lambda r, e: self._revisar_ia())

        # ============================================================== actualizaciones
        def _buscar_actualizacion(self, manual=False):
            """En un hilo: lee el version.json firmado; si hay una version nueva la baja sola y queda lista para instalar
            al cerrar (o con «Instalar ahora»). Instalado nada mas: en el codigo solo avisa."""
            import actualizaciones as act
            if getattr(self, "_buscando", False) or self.actualizacion:
                if manual and self.actualizacion:
                    self._avisar("La versión %s ya está lista: se instala al cerrar (o pulsa «Instalar ahora»)."
                                 % self.actualizacion["version"])
                return
            self._buscando = True
            if manual:
                self.b_buscar.setEnabled(False)
                self.l_act.setText("Buscando…")
            avance = {"t": ""}

            def trabajo():
                r = act.comprobar()
                if r["estado"] == "nueva" and rutas.CONGELADO:
                    def prog(h, t):
                        avance["t"] = "Bajando la versión %s… %d %%" % (r["version"], 100 * h // t) if t else \
                            "Bajando la versión %s… %.0f MB" % (r["version"], h / 1e6)
                    r["ruta"] = act.descargar(r["archivo"], prog)
                return r
            self.t_bajar = QTimer(self)
            self.t_bajar.timeout.connect(lambda: self.l_act.setText(avance["t"]) if avance["t"] else None)
            self.t_bajar.start(500)

            def listo(r, error):
                self._buscando = False
                self.t_bajar.stop()
                self.b_buscar.setEnabled(True)
                if error is not None:
                    self.l_act.setText("No se pudo buscar ni bajar la versión nueva: %s" % str(error)[:120])
                    if manual:
                        self._avisar("Actualizaciones: %s" % str(error)[:140], "warn")
                    return
                if r["estado"] == "al_dia":
                    self.l_act.setText("Al día: tienes la última versión (%s)." % rutas.version())
                    if manual:
                        self._avisar("Tienes la última versión (%s)." % rutas.version())
                elif r["estado"] == "error":
                    self.l_act.setText("Actualizaciones: %s" % r.get("mensaje", ""))
                    if manual:
                        self._avisar("Actualizaciones: %s" % r.get("mensaje", ""), "warn")
                elif r.get("ruta"):
                    self.actualizacion = {"version": r["version"], "ruta": r["ruta"]}
                    self.l_act.setText("Versión %s lista: se instala sola al cerrar el programa. %s"
                                       % (r["version"], (r.get("notas") or "").split("\n")[0][:160]))
                    self._avisar("Hay una versión nueva (%s) lista: se instala al cerrar el programa." % r["version"])
                    self.b_actualizar.show()
                else:
                    self.l_act.setText("Hay una versión nueva (%s) (en el código no se instala)." % r["version"])
            qt_kit.correr_en_hilo(self, trabajo, listo)

        def _lanzar_instalacion(self, reabrir):
            import actualizaciones as act
            import threading
            hecho = {}

            def lanzar():
                try:
                    hecho["modo"] = act.instalar(self.actualizacion["ruta"], reabrir=reabrir)
                except Exception as ex:
                    hecho["error"] = str(ex)
            h = threading.Thread(target=lanzar, daemon=True)
            h.start()
            h.join(8)
            if "error" in hecho:
                registro.error("No se pudo lanzar la actualizacion: %s" % hecho["error"])
            else:
                registro.info("Actualizacion %s lanzada (%s)" % (self.actualizacion["version"], hecho.get("modo")))
            return "error" not in hecho

        def _instalar_ahora(self):
            if not self.actualizacion:
                return
            if self.trabajo is not None:
                self._avisar("Espera a que termine el armado: luego pulsa «Instalar ahora» (o se instala al cerrar).", "warn")
                return
            self._instalando = True
            self._avisar("Instalando la versión %s: el programa se cierra y se vuelve a abrir solo…"
                         % self.actualizacion["version"])
            if self._lanzar_instalacion(reabrir=True):
                # Windows: esta ventana la cierra el instalador cuando YA esta en pantalla (es su primer paso). Antes
                # se cerraba a los 0,6 s y quedaban varios segundos sin nada a la vista mientras Windows revisaba el
                # instalador recien bajado. Si no aparece, se cierra igual al cabo de un rato.
                QTimer.singleShot(90000 if rutas.ES_WIN else 600, self.close)
            else:
                self._instalando = False
                self._avisar("No se pudo empezar la instalación: se intenta al cerrar.", "error")

        def _cambiar_base(self):
            """Dónde se crean las carpetas «EVENTO TERMINADO - <evento>» (por defecto, el Escritorio). El material y el
            trabajo van siempre por dentro del programa (1.5.7)."""
            d = QFileDialog.getExistingDirectory(self, "Dónde quedan los eventos terminados", rutas.SALIDA)
            if d:
                c = rutas.leer_config()
                c["carpeta_terminados"] = d
                rutas.guardar_config(c)
                QMessageBox.information(self, TITULO_APP, "Listo. Cierra y vuelve a abrir el programa para usar:\n%s" % d)

        def _restaurar_nombres(self):
            """(1.5.7) Deshace el renombrado del material del evento (vuelven los nombres que traian los archivos)."""
            if self.trabajo is not None or self.copia is not None:
                self._avisar("Espera a que termine lo que está haciendo.", "warn")
                return
            r = QMessageBox.question(self, TITULO_APP,
                                     "¿Devolver a los archivos del evento los nombres que traían?\n\n"
                                     "No se borra ni se mueve nada; DaVinci los vuelve a encontrar. Mientras sea este "
                                     "evento, el programa ya no los renombrará.")
            if r != QMessageBox.Yes:
                return
            qt_kit.correr_en_hilo(self, lambda: motor.restaurar_nombres(registro.info),
                                  lambda n, error: self._avisar(
                                      "No se pudieron restaurar los nombres: %s" % error if error is not None
                                      else "Nombres originales restaurados: %d archivos." % (n or 0),
                                      "error" if error is not None else "ok"))

        def _abrir_terminado(self):
            """La carpeta EVENTO TERMINADO del último evento (o donde se crean, si todavía no hay ninguna)."""
            evento = (self.resultado or {}).get("evento") or motor.leer_estado().get("evento")
            carpeta = rutas.carpeta_terminado(evento) if evento else ""
            rutas.abrir(carpeta if carpeta and os.path.isdir(carpeta) else rutas.SALIDA)

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
            self.chip_evento.setText(("%s%s" % (tipo, ("  ·  " + nombre) if nombre else "  ·  escribe los nombres"))
                                     .replace("&", "&&"))
            if self.chip_evento.icon().isNull():                      # el lapiz, dibujado («✎» no esta en la fuente)
                self.chip_evento.setIconSize(QSize(14, 14))
                self.chip_evento.setIcon(icono_trazo("lapiz", "#EBCB8F", 14))

        def _cambio_plantillas(self, _=None):
            if not any(b.isChecked() for b in self._pastillas()):
                quien = self.sender()                             # siempre al menos una, de un formato u otro
                (quien if quien in self._pastillas() else self.pills[motor.VERSIONES[0]]).setChecked(True)
            for pills in (self.pills, self.pills_v):
                for v, b in pills.items():
                    b.setIcon(self._palomita if b.isChecked() else QIcon())
                    b.setText((" " if b.isChecked() else "") + VERSION_TEXTO[v])     # un respiro entre palomita y texto
            self._sub_material()

        def _pastillas(self, con_todas=False, con_etiquetas=False):
            """Las pastillas de los dos formatos (y, si se piden, sus botones «Todas» y sus etiquetas)."""
            return list(self.pills.values()) + list(self.pills_v.values()) + (self.bs_todas if con_todas else []) + \
                (self.etqs_formato if con_etiquetas else [])

        def _estimar(self, examen=None):
            """Segundos que tardara todo, con lo que hay (o lo que se acaba de soltar) y las versiones elegidas."""
            try:
                cuenta = (examen or {}).get("cuenta") or self.material.get("cuenta") or {}
                n = int(cuenta.get("video", 0)) + int(cuenta.get("dron", 0))
                gb = float((examen or {}).get("bytes") or 0) / 1e9 or n * 0.4
                vert = self._versiones_v() or (["1min"] if n else [])
                return motor.estimar_segundos(n, gb, self._versiones(), vert, getattr(self, "_con_render", True))
            except Exception:
                return None

        def _versiones(self):
            """Versiones elegidas del formato horizontal."""
            return [v for v, b in self.pills.items() if b.isChecked()]

        def _versiones_v(self):
            """Versiones elegidas del formato vertical (9:16, solo videos verticales)."""
            return [v for v, b in self.pills_v.items() if b.isChecked()]

        def _texto_versiones(self):
            h = ", ".join(VERSION_TEXTO[v] for v in self._versiones())
            vv = ", ".join(VERSION_TEXTO[v] for v in self._versiones_v())
            return h + (((" · " if h else "") + "vertical " + vv) if vv else "")

        def _sub_material(self):
            if self.trabajo is not None or self.flujo is not None:
                return
            m = self.material
            c = m["cuenta"]
            vers = self._texto_versiones()
            if m["ok"]:
                self._sub("● %d fotos · %d videos · %d dron  ·  armará %s" % (c["foto"], c["video"], c["dron"], vers), "ok")
            else:
                self._sub("● Falta material: %s  ·  pulsa ► y te digo qué agregar" % ", ".join(
                    "%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in m["faltan"]))

        def _revisar_material_fondo(self):
            """Lo mismo, pero contando los archivos en otro hilo: recorrer 1 MATERIAL frenaba la ventana unos 60 ms
            cada vez que cambiaba la carpeta y justo al abrir."""
            def listo(res, error):
                if error is not None:
                    self._avisar("No pude revisar 1 MATERIAL: %s" % error, "error")
                elif res:
                    self._revisar_material(res)
            qt_kit.correr_en_hilo(self, motor.revisar_material, listo)

        def _revisar_material(self, hecho=None):
            try:
                self.material = hecho or motor.revisar_material()
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
            if self.analisis is None and self.trabajo is None:
                self._cargar_organizacion()

        def _arranque(self):
            rutas.crear_carpetas()
            self._revisar_material_fondo()
            self._avisar("Chequeo de arranque…")
            self.cheq = Chequeo()
            self.cheq.fin.connect(self._fin_chequeo)
            self.cheq.start()
            self._ver_davinci()
            if os.environ.get("TRAILER_PRUEBA_ARRASTRE"):                # en la prueba: sin internet ni tareas del sistema
                return
            QTimer.singleShot(4000, self._buscar_actualizacion)          # actualizaciones: al abrir y cada 4 h
            self.t_act = QTimer(self)
            self.t_act.timeout.connect(self._buscar_actualizacion)
            self.t_act.start(4 * 3600 * 1000)
            if rutas.CONGELADO and rutas.ES_WIN:                          # la tarea programada (con el programa cerrado)
                import actualizar_fondo
                qt_kit.correr_en_hilo(self, actualizar_fondo.asegurar_programada,
                                      lambda r, e: registro.info("Tarea de actualizaciones: %s" % (e or r)))
            elif rutas.CONGELADO and rutas.ES_MAC:                        # Mac: se arrastra a Aplicaciones, sin instalador
                import tareas                                             # lo que hacia el .pkg lo hace el programa al abrirse
                qt_kit.correr_en_hilo(self, tareas.primer_arranque, self._fin_primer_arranque)

        def _fin_primer_arranque(self, r, e):
            import actualizar_fondo
            registro.info("Primer arranque (Mac): %s" % (e or r))
            if actualizar_fondo.app_de_paso():                            # abierta desde el disco, sin arrastrarla
                QTimer.singleShot(6000, lambda: self._avisar(
                    "Arrastra Tráiler automático a Aplicaciones y ábrelo desde ahí: así se actualiza solo.", "warn"))

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
                self._recibir(archivos, tipo)

        # ---- soltar una carpeta: se mira, se pregunta lo justo, se copia ordenada y se arma el trailer solo
        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls() and self.trabajo is None and self.flujo is None and self.copia is None:
                e.acceptProposedAction()
                self.hoja.mostrar("soltar", "Suelta aquí la carpeta del evento",
                                  "La ordeno en fotos, videos y dron, la organizo por momentos\ny armo el tráiler.",
                                  icono="↓")

        def dragLeaveEvent(self, e):
            self.hoja.ocultar("soltar")

        def dropEvent(self, e):
            self.hoja.ocultar("soltar")
            archivos = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if archivos:
                e.acceptProposedAction()
                self._recibir(archivos)

        def _recibir(self, archivos, tipo=None):
            """Lo soltado (o elegido con «Agregar…», con su tipo): primero se mira sin copiar nada."""
            if self.trabajo is not None or self.copia is not None or self.flujo is not None:
                self._avisar("Espera a que termine lo que está haciendo y vuelve a soltar el material.", "warn")
                return
            self.flujo = "mirando"
            self._soltado = (archivos, tipo)
            self._ir("Inicio")
            self.titulo.setText("Mirando lo que soltaste…")
            self._sub("Contando fotos, videos y tomas de dron…")
            qt_kit.correr_en_hilo(self, lambda: (motor.examinar_origen(archivos, tipo), motor.evento_actual(),
                                                 motor.es_evento_nuevo()), self._recibido)

        def _recibido(self, r, error):
            archivos, tipo = self._soltado
            if error is not None or not r:
                self._fin_flujo("No pude leer lo que soltaste: %s" % error, "error")
                return
            examen, (ev_nombre, ev_fecha), terminado = r
            self._examen_soltado = examen
            c = examen["cuenta"]
            otros = motor.texto_otros(examen["otros"])
            if not sum(c.values()):
                self._fin_flujo("Ahí no encontré fotos ni videos que sirvan%s." % ((" (" + otros + ")") if otros else ""),
                                "warn")
                return
            # (1.5.7, la persona: «se vuelva a arrastrar otra carpeta, solo la unes al análisis») sin preguntar: se une al
            # evento que hay; si ese ya está terminado (con su EVENTO TERMINADO), lo soltado empieza uno nuevo y el
            # material del anterior se guarda por dentro (no se borra nada)
            self._copiar(archivos, tipo, examen, (ev_nombre or terminado) if tipo is None and terminado else None)

        def _copiar(self, archivos, tipo, examen, anterior):
            self.hoja.ocultar()
            self.flujo = "copiando"
            self._evento_nuevo = anterior is not None or not any(self.material["cuenta"].values())
            self._tipo_copia = tipo
            c = examen["cuenta"]
            self.titulo.setText("Tomando el material…")
            self._sub("%d fotos · %d videos · %d dron  ·  %.1f GB" % (c["foto"], c["video"], c["dron"], examen["bytes"] / 1e9), "ok")
            self.boton.poner_estado("trabajando", centro="Copiando")
            self.boton.poner_progreso(0.0)
            self.chip_evento.hide()
            self.chip_cancelar.show()
            self.copia = Copia(archivos, tipo, examen, anterior)
            # _fin_copia suelta self.copia cuando el hilo AUN no acaba de salir de run(): si Qt destruye un QThread que
            # sigue corriendo, cierra el programa sin avisar (paso 1 vez de 4 en la prueba). Aqui queda vivo hasta el final.
            self._hilos_vivos = [h for h in getattr(self, "_hilos_vivos", []) if h.isRunning()] + [self.copia]
            self.copia.avance.connect(self._avance_copia)
            self.copia.fin.connect(self._fin_copia)
            self.copia.start()

        def _avance_copia(self, f, nombre, i, n):
            self.boton.poner_progreso(min(0.99, f))
            self._sub("%d %%  ·  %d de %d  ·  %s" % (int(f * 100), i, n, nombre[:44]), "ok")

        def _cancelar_copia(self):
            if self.copia is not None:
                self.copia.cancelar = True
                self._sub("Cancelando la copia…")

        def _fin_copia(self, res):
            self.copia = None
            self.chip_cancelar.hide()
            self.chip_evento.show()
            self.boton.poner_estado("listo")
            self.titulo.setText("Material ordenado")
            if "error" in res:
                self._revisar_material()
                self._fin_flujo("Copia cancelada: lo ya copiado queda guardado." if res.get("cancelada")
                                else "No se pudo copiar: %s" % res["error"], "warn" if res.get("cancelada") else "error")
                return
            c = res["copiados"]
            partes = ["%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in c.items() if n]
            resumen = ("En su carpeta: " if res.get("en_su_sitio") else "Ordenado: ") + (
                " · ".join(partes) if partes else "nada nuevo")
            seg = self._estimar(getattr(self, "_examen_soltado", None))      # (1.5.7) en cuanto tiempo estara listo
            if seg:
                resumen += "  ·  estará listo en " + motor.texto_tiempo(seg)
            if res["ya_estaban"]:
                resumen += "  ·  %d ya estaban" % res["ya_estaban"]
            otros = motor.texto_otros(res["otros"])
            if otros:
                resumen += "\nNo se usan: " + otros
            if res.get("archivado") and res["archivado"][1]:
                resumen += "\nEvento nuevo: el anterior ya estaba terminado (su material queda guardado por dentro)."
            if self._evento_nuevo and self._tipo_copia is None:      # los textos del evento anterior no valen
                for w in (self.e_nombre, self.e_frase, self.e_fecha):
                    w.setText("")
            self._revisar_material()
            self.l_copia.setText(resumen.split("\n")[0])
            if not self.material["ok"]:
                self._fin_flujo(resumen.split("\n")[0] + "  ·  todavía falta: " + ", ".join(
                    "%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in self.material["faltan"]), "warn")
            elif self._tipo_copia is not None or not self.ch_auto.isChecked():
                self._fin_flujo(resumen.split("\n")[0] + "  ·  pulsa ▶ para armar.")
            elif self._evento_nuevo or not self.e_nombre.text().strip():
                self._pedir_datos(resumen)
            else:
                self._cuenta_atras(resumen)

        def _pedir_datos(self, resumen):
            """Evento nuevo: tipo y nombres para los titulos, y a armar."""
            self.flujo = "datos"
            w = QWidget()
            g = QGridLayout(w)
            g.setContentsMargins(0, 6, 0, 0)
            g.setHorizontalSpacing(12)
            g.setVerticalSpacing(10)
            c = QComboBox()
            for clave, texto in TIPOS:
                c.addItem(texto, clave)
            c.setCurrentIndex(self.c_tipo.currentIndex())
            e = QLineEdit(self.e_nombre.text())
            e.setPlaceholderText("Ej.: Valeria  ·  K & R")
            for i, (etq, wid) in enumerate((("Tipo de evento", c), ("Nombres", e))):
                l = QLabel(etq)
                l.setStyleSheet("color:%s; font-weight:600;" % TENUE)
                g.addWidget(l, i, 0)
                g.addWidget(wid, i, 1)
            g.setColumnStretch(1, 1)

            def armar():
                self.c_tipo.setCurrentIndex(c.currentIndex())
                self.e_nombre.setText(e.text().strip())
                self._armar_flujo()
            e.returnPressed.connect(armar)
            self._form = (c, e)
            self.hoja.mostrar("datos", "¿De quién es el evento?", resumen,
                              [("Armar el tráiler", armar, True),
                               ("Solo ordenar", lambda: self._fin_flujo("Material ordenado. Pulsa ▶ cuando quieras armar."),
                                False)], contenido=w, icono="✓")
            e.setFocus()

        def _cuenta_atras(self, resumen):
            """Mismo evento con material nuevo: arma solo en unos segundos, salvo que se cancele."""
            self.flujo = "cuenta"
            self._quedan = 6

            def tic():
                if self.flujo != "cuenta":
                    self.t_cuenta.stop()
                    return
                self._quedan -= 1
                if self._quedan <= 0:
                    self.t_cuenta.stop()
                    self._armar_flujo()
                else:
                    self.hoja.texto.setText("%s\n\nEmpiezo a armar el tráiler en %d…" % (resumen, self._quedan))
            self.hoja.mostrar("cuenta", "Material ordenado", "%s\n\nEmpiezo a armar el tráiler en 5…" % resumen,
                              [("Armar ya", self._armar_flujo, True),
                               ("Ahora no", lambda: self._fin_flujo("Material ordenado. Pulsa ▶ cuando quieras armar."),
                                False)], icono="✓")
            self.t_cuenta = QTimer(self)
            self.t_cuenta.timeout.connect(tic)
            self.t_cuenta.start(1000)

        def _armar_flujo(self):
            self.hoja.ocultar()
            self.flujo = None
            self.titulo.setText("Un clic y listo")
            self._play(auto=True)

        def _fin_flujo(self, texto, tipo="info"):
            self.hoja.ocultar()
            self.flujo = None
            self.titulo.setText("Un clic y listo")
            self._avisar(texto, tipo)
            self._sub_material()

        # ============================================================== play
        def _guardar(self):
            versiones, verticales = self._versiones(), self._versiones_v()
            if not versiones and not verticales:
                versiones = list(motor.VERSIONES)
            d = motor.leer_estado()
            d.update({"tipo_evento": self.c_tipo.currentData(), "nombre_xv": self.e_nombre.text().strip(),
                      "frase": self.e_frase.text().strip(), "fecha_lugar": self.e_fecha.text().strip(),
                      "versiones": versiones, "versiones_vertical": verticales, "ruido": self.s_ruido.value(),
                      "igualar": self.ch_igualar.isChecked(), "renderizar": self.ch_render.isChecked(),
                      "auto_armar": self.ch_auto.isChecked(),
                      "voz": {k: ch.isChecked() for k, ch in self.ch_voz.items()},
                      "usar_verticales": self.ch_vert.isChecked()})
            motor.guardar_estado(d)
            return dict(evento=d.get("evento_manual", ""), nombre_xv=d["nombre_xv"], fecha_lugar=d["fecha_lugar"],
                        frase=d["frase"], tipo_evento=d["tipo_evento"], ruido=d["ruido"], igualar=d["igualar"],
                        voz=d["voz"], verticales=d["usar_verticales"],
                        solo=versiones if 0 < len(versiones) < len(motor.VERSIONES) else None,
                        horizontal=bool(versiones), vertical=verticales, render=d["renderizar"])

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

        def _chips_editable(self, ver=None):
            """«Editar en DaVinci» y «Renderizar lo editado» se ven cuando hay un evento armado (y no se esta trabajando)."""
            if ver is None:
                est = motor.leer_estado()
                ver = bool(est.get("evento") and est.get("timelines")) and self.trabajo is None
            self.chip_editar.setVisible(bool(ver))
            self.chip_render.setVisible(bool(ver))

        def _ya_armado(self):
            """El evento que hay en 1 MATERIAL ya esta armado en DaVinci con este mismo material: su nombre, o ''."""
            try:
                est = motor.leer_estado()
                if est.get("evento") and est.get("timelines") and est.get("huella") == motor.huella():
                    return est["evento"]
            except Exception:
                pass
            return ""

        def _preguntar_ya_armado(self, evento):
            """▶ vuelve a armar desde cero y reemplaza las lineas: si la persona las retoco a mano, lo perderia.
            Devuelve "editado", "armar" o None (cancelar)."""
            caja = QMessageBox(self)
            caja.setWindowTitle(TITULO_APP)
            caja.setIcon(QMessageBox.Question)
            caja.setText("«%s» ya está armado en DaVinci.\n\n"
                         "•  Renderizar lo editado: saca los videos con lo que hayas cambiado a mano en DaVinci.\n"
                         "•  Volver a armar: lo arma de nuevo desde cero y reemplaza esas líneas "
                         "(se pierden los cambios hechos a mano)." % evento)
            b_ed = caja.addButton("Renderizar lo editado", QMessageBox.AcceptRole)
            b_ar = caja.addButton("Volver a armar", QMessageBox.DestructiveRole)
            caja.addButton("Cancelar", QMessageBox.RejectRole)
            caja.setDefaultButton(b_ed)
            caja.exec()
            return "editado" if caja.clickedButton() is b_ed else "armar" if caja.clickedButton() is b_ar else None

        def _editar_en_davinci(self):
            if self.trabajo is not None:
                self._avisar("Espera a que termine: después podrás retocarlo en DaVinci.", "warn")
                return
            self._avisar("Abriendo DaVinci en la línea del evento…")

            def listo(nombre, error):
                if error is not None:
                    self._avisar("No pude abrirlo en DaVinci: %s" % error, "warn")
                else:
                    self._avisar("DaVinci quedó en Edición con «%s». Retoca lo que quieras y pulsa "
                                 "«Renderizar lo editado»." % nombre)
            qt_kit.correr_en_hilo(self, lambda: motor.abrir_editable(registro.info), listo)

        def _renderizar_editado(self):
            """Saca de nuevo los videos con las lineas tal como estan en DaVinci (sin volver a armar)."""
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            if self.copia is not None:
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            evento = motor.leer_estado().get("evento")
            if not evento:
                self._avisar("Todavía no hay ningún evento armado: pulsa ▶ primero.", "warn")
                return
            self._arrancar({"evento": evento}, True, "Renderizando lo editado de %s (sin volver a armar)…" % evento,
                           motor.renderizar_editado)
            self._marcar("sfx", "activo")                 # el armado no corre: directo al render

        def _play(self, auto=False):
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            if self.copia is not None:
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            self._revisar_material()
            if not self.material["ok"]:
                self._avisar("Falta material: suelta la carpeta del evento y vuelve a pulsar ▶.", "warn")
                self._pedir_material()
                return
            if not auto:                                  # ya armado con este material: ¿lo editado o desde cero?
                armado = self._ya_armado()
                if armado:
                    que = self._preguntar_ya_armado(armado)
                    if que is None:
                        return
                    if que == "editado":
                        self._renderizar_editado()
                        return
            op = self._guardar()
            if op.get("render", True):
                try:
                    libre, necesita = motor.espacio_para_render(self._versiones() + self._versiones_v())
                except Exception:
                    libre, necesita = 1e9, 0.0
                if libre < necesita:
                    caja = QMessageBox(self)
                    caja.setWindowTitle(TITULO_APP)
                    caja.setIcon(QMessageBox.Warning)
                    caja.setText("Quedan %.1f GB libres en el disco donde quedan los videos y el render necesita unos "
                                 "%.1f GB.\n\nLibera espacio, o arma solo en DaVinci y renderiza después." % (libre, necesita))
                    b_sin = caja.addButton("Armar sin renderizar", QMessageBox.AcceptRole)
                    caja.addButton("Cancelar", QMessageBox.RejectRole)
                    caja.exec()
                    if caja.clickedButton() is not b_sin:
                        self._avisar("Sin espacio para renderizar: libera espacio y vuelve a pulsar ▶.", "warn")
                        return
                    op["render"] = False
            self._arrancar(op, bool(op.get("render", True)), "Armando %s…" % self._texto_versiones())
            if self.analisis is not None:
                self._avisar("Termino de analizar el material y sigo solo…")

        def _arrancar(self, op, con_render, texto, funcion=None):
            """Pone la ventana a trabajar y lanza el hilo: armar todo (funcion=None) o renderizar lo editado."""
            self.registro.clear()
            self.chip_videos.hide()
            self._chips_editable(False)
            self._con_render = con_render
            self.pasos_go = {k: "pendiente" for k, _ in PASOS_GO}
            self._prog = 0.0
            self.boton.poner_estado("trabajando", centro="Preparando")
            self.boton.poner_progreso(0.0)
            self.escena.empezar()
            self._marcar("timeline", "activo")
            self.chip_evento.hide()
            for b in self._pastillas(True, True):
                b.hide()
            self.reserva.setFixedHeight(len(PASOS_GO) * 34 + 14)
            self._acomodar()
            self.titulo.setText("Trabajando…")
            self._sub("Empezando…")
            self._avisar(texto)
            for b in self._pastillas(True):
                b.setEnabled(False)
            try:                                         # si IntelliSearch esta trabajando, cede el paso
                import indexar
                indexar.PARAR.set()
            except Exception:
                pass
            self.linea.editable = False
            self._t_trabajo = time.time()
            self._eta_previo = self._estimar()
            self.trabajo = Trabajo(op, funcion)
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
                  ("Escuchando", 21, "La IA de DaVinci escucha votos y brindis", "ia"),
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
            self._poner_eta(f)

        def _poner_eta(self, f):
            """(1.5.7, la persona: «que me diga en cuánto tiempo va a estar listo») Lo que falta: al principio, lo
            calculado por el material; a medida que avanza, cada vez mas lo que de verdad va tardando."""
            t0 = getattr(self, "_t_trabajo", None)
            if t0 is None or self.trabajo is None:
                return
            pasado = time.time() - t0
            previo = getattr(self, "_eta_previo", None)
            resto_previo = max(0.0, previo - pasado) if previo else None
            resto_real = pasado * (1.0 - f) / f if f >= 0.06 else None
            if resto_real is None and resto_previo is None:
                return
            if resto_real is None:
                resto = resto_previo
            elif resto_previo is None:
                resto = resto_real
            else:
                w = min(1.0, max(0.0, (f - 0.06) / 0.5))            # cuanto mas avanza, mas manda lo real
                resto = (1 - w) * resto_previo + w * resto_real
            self.titulo.setText("Trabajando… listo en " + motor.texto_tiempo(resto))

        def _linea(self, m):
            self.registro.appendPlainText(m)
            registro.info(m)
            a = re.match(r"\s+(\d+)/(\d+)\s+(\S.*)$", m)         # avance del analisis: «  12/65  DSC_0012.MP4»
            if a and int(a.group(2)) > 0 and self._prog < 0.12:
                i, n = int(a.group(1)), int(a.group(2))
                self._poner_prog(0.03 + 0.08 * i / float(n))
                self._sub("Analizando %d de %d · %s" % (i, n, a.group(3)[:40]))
                return
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
                for b in self._pastillas(True, True):
                    b.show()
                self._acomodar()

        def _acomodar(self):
            """El tamano del astrolabio sigue al espacio libre (como en CineCaptions)."""
            if hasattr(self, "escena"):
                self.escena.setGeometry(self.cielo.rect())
            if hasattr(self, "hoja") and self.hoja.isVisible():
                self.hoja.setGeometry(self.cielo.rect())
            pag = self.paginas.widget(0)
            libre = self.hueco_boton.height() - 8
            self.boton.poner_lado(int(max(200, min(libre, pag.width() * 0.5))))
            self._centrar_boton()

        def _centrar_boton(self):
            h = self.hueco_boton
            self.boton.move(max(0, (h.width() - self.boton.width()) // 2), max(0, (h.height() - self.boton.height()) // 2))

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
                self._ancho_registro()
                QTimer.singleShot(0, self._acomodar)

        def _ancho_registro(self, *_):
            """El panel del registro se angosta para no cortar la pagina (ventana chica, pestaña Material). Si ni asi
            cabe, esa pagina se desplaza de lado en vez de quedar cortada."""
            pag = self.paginas.currentWidget()
            scroll = isinstance(pag, QScrollArea)
            libre = 400
            if self.b_log.isChecked():
                pide = pag.widget().minimumSizeHint().width() if scroll else 470
                libre = self._medio.geometry().width() - pide - max(0, self._medio.spacing())
                self.registro.setFixedWidth(max(260, min(400, libre)))
            if scroll:
                pag.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded if libre < 260 else Qt.ScrollBarAlwaysOff)

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
                self._sub("%d de %d videos en «%s»" % (len(ok), len(videos), os.path.basename(
                    rutas.carpeta_terminado(self.resultado.get("evento", "")))),
                          "ok" if len(ok) == len(videos) else "error")
                self._avisar("Terminado: %d videos con audio a -14 LUFS%s." % (
                    len(ok), " (con lo que editaste en DaVinci)" if self.resultado.get("editado") else ""))
                self.chip_videos.show()
                self._abrir_videos()
                QTimer.singleShot(4000, self._indexar_fondo)
            else:
                self._sub("Armado en DaVinci · %s" % self.resultado.get("evento", ""), "ok")
                self._avisar("Timelines armadas en DaVinci (sin render).")
            for a in (self.resultado.get("avisos") or [])[:3]:        # lo que el formato vertical no pudo armar
                self._avisar(a, "warn")
            if not self.resultado.get("editado"):
                self._avisar("La línea queda editable en DaVinci (02 EVENTOS › %s) y su copia en «%s». Si "
                             "retocas algo, pulsa «Renderizar lo editado»."
                             % (self.resultado.get("evento", ""), rutas.PLANTILLAS_EVENTO))
            self.chip_editar.show()
            self.chip_render.show()

        def _indexar_fondo(self):
            """Al final y sin esperar: IntelliSearch (Better, con rostros) para buscar en DaVinci por lo que se ve o por
            persona. Va de un video a la vez y cede el paso si se pulsa ▶ otra vez."""
            if self.trabajo is not None or getattr(self, "indexando", False):
                return
            import indexar
            self.indexando = True
            self._avisar("IntelliSearch: DaVinci está viendo cada video para que puedas buscar por contenido "
                         "(en segundo plano; puedes seguir trabajando).")

            def listo(res, error):
                self.indexando = False
                if self.trabajo is not None:
                    return
                if error is not None:
                    self._avisar("IntelliSearch no terminó: %s" % error, "warn")
                elif res and res.get("intellisearch"):
                    self._avisar("IntelliSearch listo: en DaVinci busca en el media pool por lo que se ve "
                                 "(«pastel», «anillos») o por persona.")
            qt_kit.correr_en_hilo(self, lambda: indexar.indexar(registro.info, intellisearch=True), listo)

        def _fallo(self, texto):
            activa = next((k for k, e in self.pasos_go.items() if e == "activo"), None)
            if activa:
                self.escena.paso(activa, "error")
            self._ultimo_fallo = texto
            self.escena.terminar(False, "ok")
            self.boton.poner_estado("error", centro="Error")
            self.titulo.setText("Un clic y listo")
            self._sub("No se pudo terminar: %s" % texto, "error")
            self._avisar("Error: %s" % texto, "error")
            self.b_log.setChecked(True)

        def _liberar(self):
            self.trabajo = None
            self._chips_editable()
            self._cargar_organizacion()
            for b in self._pastillas(True):
                b.setEnabled(True)
            QTimer.singleShot(6000, lambda: self.titulo.setText("Un clic y listo") if self.trabajo is None else None)

        def _abrir_videos(self):
            rutas.abrir((self.resultado or {}).get("carpeta") or rutas.SALIDA)

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
            if t == QEvent.Resize and (obj is getattr(self, "boton", None) or obj is getattr(self, "hueco_boton", None)):
                if obj is self.hueco_boton:
                    QTimer.singleShot(0, self._acomodar)
                else:
                    self._centrar_boton()               # el astrolabio crece o se achica con suavidad: siempre al medio
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
            if self.actualizacion and not self._instalando:      # la version nueva ya bajada se instala al cerrar
                self._instalando = True
                self._lanzar_instalacion(reabrir=False)
            e.accept()

    if rutas.ES_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CinemaProductions.Trailer")
        except Exception:
            pass
    _tiempo("clases definidas")
    qapp = QApplication(sys.argv)
    _tiempo("QApplication")
    import threading
    preparar_fuentes = calentar_fuentes()
    if preparar_fuentes:                                    # la lista de fuentes de la PC, ya, en su hilo
        threading.Thread(target=preparar_fuentes, args=("I",), name="fuentes", daemon=True).start()
    # Mientras esa lista se arma (0,2 s), aqui se hace lo que no necesita letras: cargar el codigo de la escena de
    # Inicio y de las paginas (0,1 s de puro Python). Despues el estilo ya pide fuentes y esperaria igual.
    try:
        import boton_go, escena_go, linea_dia  # noqa: F401
    except Exception:
        pass
    _tiempo("modulos de la escena")
    # Portada de Qt donde no hay nativa (Mac): mientras se construye la ventana completa (estilos, escena de Inicio).
    # En Windows ya esta puesta la nativa (_portada_nativa), que sale mucho antes: Qt tarda ~1 s en su primera ventana.
    portada = None
    try:
        if nativa:
            raise RuntimeError("ya hay portada nativa")
        from PySide6.QtWidgets import QSplashScreen
        import icono_app as ic
        ancho, alto = 440, 250
        pm = QPixmap(ancho, alto)
        pm.fill(QColor("#06131A"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, 0, alto)
        g.setColorAt(0.0, QColor("#0D2630"))
        g.setColorAt(1.0, QColor("#06131A"))
        p.fillRect(0, 0, ancho, alto, QBrush(g))
        p.setPen(QPen(QColor(201, 162, 103, 110), 1))
        p.drawRect(0, 0, ancho - 1, alto - 1)
        p.drawImage(QRectF(ancho / 2 - 52, 52, 104, 104), ic.dibujar(208))
        p.end()
        portada = QSplashScreen(pm)
        portada.show()
        qapp.processEvents()
    except Exception:
        portada = None
    _tiempo("portada visible")
    qapp.setApplicationName(TITULO_APP)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(estilo_completo())
    _tiempo("estilos")
    candado = QLockFile(os.path.join(rutas.DATOS, "programa.lock"))
    candado.setStaleLockTime(0)
    if not candado.tryLock(200):                           # una sola ventana abierta a la vez
        _quitar_portada(nativa)
        if portada is not None:
            portada.close()
        if not _traer_la_abierta():                        # ya esta abierto: esa ventana, al frente y sin cuadros
            QMessageBox.information(None, TITULO_APP, "El programa ya está abierto.")
        return 0
    if portada is not None:
        try:
            portada.showMessage("Abriendo %s…" % TITULO_APP, Qt.AlignHCenter | Qt.AlignBottom, QColor(TENUE))
            qapp.processEvents()
        except Exception:
            pass
    rutas.crear_carpetas()
    win = Ventana()
    _tiempo("ventana armada")
    win.show()
    _tiempo("ventana visible")
    qapp.processEvents()                                   # la ventana ya pintada: ahora si se quita la portada
    _quitar_portada(nativa)
    if portada is not None:
        portada.finish(win)
    _tiempo("primer cuadro pintado")
    if preparar_fuentes:                                    # con la ventana ya a la vista: las fuentes de reserva
        QTimer.singleShot(120, lambda: threading.Thread(target=preparar_fuentes, args=("✓",), name="fuentes de reserva",
                                                        daemon=True).start())
    if os.environ.get("TRAILER_PRUEBA_ARRASTRE"):          # prueba de punta a punta: suelta una carpeta y mira que arme
        import prueba_arrastre
        win._guion = prueba_arrastre.Guion(win, qapp, os.environ["TRAILER_PRUEBA_ARRASTRE"],
                                           os.environ.get("TRAILER_PRUEBA_SALIDA") or os.path.join(rutas.DATOS, "prueba"))
    return qapp.exec()


def main():
    args = sys.argv[1:]
    registro.preparar()
    _tiempo("main()")
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
