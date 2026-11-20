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
# (1.6.0, el diseño de Higgsfield) los pasos que ve la persona mientras trabaja, en una fila
PASOS_VISTA = [("analizar", "Analizar"), ("ia", "IA y oído"), ("armar", "Armar"), ("render", "Renderizar"),
               ("master", "Masterizar"), ("revisar", "Revisar")]
# texto del registro (o del avance) -> paso de la fila que empieza
ETAPAS_VISTA = [("Analizando", "analizar"), ("Revisando el material", "analizar"), ("Viendo cada toma con la IA", "ia"),
                ("La IA local revisa", "ia"), ("El oído (earshot) escucha", "ia"), ("Conectando con DaVinci", "armar"),
                ("Armando timelines", "armar"), ("Renderizando", "render"), ("Masterizando", "master"),
                ("Audio masterizado", "master"), ("Escuchando el audio", "revisar"), ("Revisando con IA", "revisar"),
                ("Proxies y plantillas", "revisar")]
TITULO_INICIO = "Un clic y <span style='color:#D9A441;'>listo</span>"
CANCELADO = "Cancelado"


def _cuantos(n, tipo):
    """«1 video», «442 fotos», «9 dron»."""
    nombre = {"foto": ("foto", "fotos"), "video": ("video", "videos"), "dron": ("dron", "dron")}.get(tipo, (tipo, tipo))
    return "%d %s" % (n, nombre[0] if n == 1 else nombre[1])


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
    # (1.8.2) sin versiones pero con plantillas de referencia elegidas: solo las plantillas
    return (h or ([] if v or est.get("plantillas_ref") else list(motor.VERSIONES))), v


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


PORTADA = False         # (1.6.0) el cuadro de arranque (nativo en Windows, de Qt en la Mac): quitado a pedido


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
    # (1.6.0) sin portada: la persona no quiere el cuadro de arranque («elimina eso», 17-nov); la ventana sale sola
    nativa = None
    _tiempo("sin portada")
    from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QPointF, QRectF, QSize, QFileSystemWatcher, QVariantAnimation,
                                QEasingCurve, QEvent, QLockFile)
    from PySide6.QtGui import (QColor, QIcon, QPainter, QPixmap, QPen, QBrush, QFont, QPainterPath,
                               QRadialGradient, QLinearGradient, QImageReader)
    from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                                   QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                                   QPushButton, QSizeGrip, QSlider, QStackedWidget, QVBoxLayout, QWidget, QScrollArea, QSizePolicy,
                                   QButtonGroup)
    import qt_kit
    import piezas                                  # (1.6.0) las piezas del diseño nuevo (Higgsfield, 17-nov)
    _tiempo("PySide6 importado")

    ESMERALDA = QColor("#22C47E")
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
    QLabel#sub { color: #EBCB8F; font-weight: 500; font-size: 15px; }
    QLabel#sub[tipo="ok"] { color: #7CF2C0; }
    QLabel#sub[tipo="error"] { color: #F07A6A; }
    QPushButton#pill { background: rgba(14, 30, 38, 0.80); border: 1px solid rgba(255,255,255,0.14);
                       border-radius: 12px; padding: 8px 16px; font-weight: 700; color: %(m)s; }
    QPushButton#pill:hover { color: %(t)s; border-color: #22C47E; }
    QPushButton#pill:checked { background: rgba(34,196,126,0.30); color: #B9FFE0; border-color: #22C47E; }
    QPushButton#pill:disabled { color: rgba(143,163,168,0.5); }
    QPushButton#chip { background: rgba(14, 30, 38, 0.80); border: 1px solid rgba(255,255,255,0.26);
                       border-radius: 9px; padding: 8px 18px; color: #F1F5F6; font-weight: 500; }
    QPushButton#chip:hover { background: rgba(255,255,255,0.08); }
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
    QFrame#hoja { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(16,52,48,248), stop:0.45 rgba(9,30,32,250),
                  stop:1 rgba(7,22,26,252)); border: 2px solid #D9B15C; border-radius: 30px; }
    QFrame#hoja[modo="soltar"] { border: 2px dashed rgba(34,196,126,0.95); background: rgba(8, 32, 27, 0.94); }
    QLabel#hoja_titulo { font-size: 24px; font-weight: 800; }
    QLabel#hoja_texto { color: #B8C7CB; font-size: 15px; }
    QLabel#hoja_icono { color: #22C47E; font-size: 44px; font-weight: 800; }
    QMessageBox, QDialog { background: #0E1E26; }
    QMessageBox QPushButton, QDialog QPushButton { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.16);
                                                   border-radius: 10px; padding: 8px 16px; font-weight: 600; min-width: 84px; }
    QMessageBox QPushButton:hover, QDialog QPushButton:hover { background: rgba(255,255,255,0.13); }
    QMessageBox QPushButton:default, QDialog QPushButton:default { background: #22C47E; color: #04150D; border-color: #22C47E; }
    QLabel#marca { font-size: 16px; font-weight: 800; letter-spacing: 1.5px; color: #FFFFFF; }
    QPushButton#estado { background: rgba(14, 30, 38, 0.82); border: 1px solid rgba(34,196,126,0.40); border-radius: 15px;
                         padding: 6px 14px 6px 10px; font-weight: 600; font-size: 13px; }
    QPushButton#estado:hover, QPushButton#estado:checked { background: rgba(34,196,126,0.16); }
    QPushButton#estado[tipo="warn"] { border-color: rgba(242,184,75,0.6); }
    QPushButton#estado[tipo="error"] { border-color: rgba(240,122,106,0.65); }
    QPushButton#estado[tipo="oro"] { border-color: rgba(217,164,65,0.6); }
    QFrame#dock { background: rgba(12, 26, 34, 0.86); border: 1px solid rgba(201,162,103,0.30); border-radius: 22px; }
    QPushButton#chip2 { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.13); border-radius: 12px;
                        padding: 8px 16px; font-weight: 600; }
    QPushButton#chip2:hover { border-color: rgba(34,196,126,0.6); }
    QPushButton#chip2[tipo="falta"] { border-color: rgba(242,184,75,0.75); color: #F2B84B; }
    QPushButton#chip2[tipo="oro"] { color: #EBCB8F; border-color: rgba(201,162,103,0.45); text-align: left; }
    QPushButton#chip2[tipo="ok"] { border-color: rgba(34,196,126,0.45); }
    QFrame#seg { background: rgba(4, 14, 20, 0.72); border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; }
    QPushButton#segb, QPushButton#segchico { background: transparent; border: 1px solid transparent; border-radius: 9px;
                                             padding: 7px 16px; color: %(m)s; font-weight: 600; }
    QPushButton#segchico { padding: 6px 10px; font-size: 12px; }
    QPushButton#segb:hover, QPushButton#segchico:hover { color: %(t)s; }
    QPushButton#segb:checked, QPushButton#segchico:checked { background: rgba(34,196,126,0.28); color: #B9FFE0;
                                                             border-color: rgba(34,196,126,0.75); }
    QPushButton#segb:disabled:checked { background: rgba(34,196,126,0.18); color: #8FD9B8; }
    QFrame#tarjeta { background: rgba(12, 26, 34, 0.84); border: 1px solid rgba(201,162,103,0.22); border-radius: 18px; }
    QLabel#tarjeta_t { font-size: 18px; font-weight: 700; }
    QFrame#stat { background: rgba(12, 26, 34, 0.84); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; }
    QFrame#stat[estado="falta"] { border-color: rgba(242,184,75,0.65); }
    QLabel#stat_n { font-size: 38px; font-weight: 800; }
    QLabel#titulo_pag { font-size: 28px; font-weight: 800; }
    QLabel#etq_campo { color: %(t)s; font-weight: 700; font-size: 14px; }
    QPushButton#link { background: transparent; border: none; color: #8FD9B8; font-weight: 600; padding: 4px 6px; }
    QPushButton#link:hover { color: #B9FFE0; }
    """          # se completa al aplicarlo: %(t)s %(m)s y las familias %(f)s %(mono)s (ver estilo_completo)

    def estilo_completo(s=None):
        if s is not None:
            piezas.ESCALA = s
        return QSS % {"t": TEXTO, "m": TENUE, "f": primera_que_hay(FAMILIAS_UI),
                      "mono": primera_que_hay(FAMILIAS_MONO)} + qss_diseno()

    def qss_diseno():
        """(1.6.0) El estilo de las maquetas de Higgsfield, con sus medidas (piezas.px: px de la maqueta de 2048 de
        ancho por la escala de la ventana). Va despues del estilo de siempre: lo que repite, manda."""
        p = piezas.px
        # (1.7.8, auditoria) el verde de la marca, vivo, con el texto de la pestaña activa OSCURO (blanco era ~2,3:1)
        # (1.7.8, la persona: «botones Liquid Glass») vidrio en QSS: luz arriba (degradado), filo mas brillante arriba
        # que abajo y la pestaña activa como una gota de vidrio verde (brillo arriba, verde profundo abajo)
        verde = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8CF5C6, stop:0.18 #4FE0A0, stop:0.55 #22C47E, "
                 "stop:1 #139A62)")
        vidrio = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.13), stop:0.45 rgba(14,30,36,0.80), "
                  "stop:1 rgba(10,22,28,0.84))")
        return """
    QLabel#marca {{ font-size: {a}px; font-weight: 600; letter-spacing: 1px; color: #FFFFFF; }}
    QFrame#nav {{ background: {vidrio}; border: 1px solid rgba(255, 255, 255, 0.22);
                 border-top-color: rgba(255, 255, 255, 0.55); border-bottom-color: rgba(255, 255, 255, 0.30);
                 border-radius: {nav_r}px; }}
    QPushButton#tab {{ font-size: {b}px; font-weight: 500; color: #DCE6E8; padding: {tab_v}px {tab_h}px;
                      border-radius: {tab_r}px; border: 1px solid transparent; }}
    QPushButton#tab:hover {{ background: rgba(255,255,255,0.08); color: #FFFFFF; border-color: rgba(255,255,255,0.14);
                            border-top-color: rgba(255,255,255,0.35); }}
    QPushButton#tab:checked {{ background: transparent; color: #FFFFFF; border: 1px solid transparent;
                              font-weight: 600; }}
    QPushButton#tab:checked[llego="true"] {{ color: #04150D; }}
    QPushButton#tab:checked:hover {{ background: transparent; border-color: transparent; }}
    QPushButton#estado {{ font-size: {c}px; font-weight: 500; padding: {e_v}px {e_h}px; border-radius: {e_r}px;
                         background: {vidrio}; border: 1px solid rgba(34, 196, 126, 0.75);
                         border-top-color: rgba(160, 255, 210, 0.95); }}
    QPushButton#estado[tipo="oro"] {{ border-color: rgba(226, 176, 79, 0.85); border-top-color: rgba(255, 228, 160, 0.95); }}
    QFrame#ventanita {{ background: transparent; border: none; }}
    QPushButton#ctrl, QPushButton#cerrar {{ background: transparent; border: none; border-radius: {ctl_r}px; }}
    QPushButton#ctrl:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#cerrar:hover {{ background: #C42B1C; }}
    QPushButton#logo {{ background: transparent; border: none; padding: 0; }}
    QLabel#sub {{ font-size: {d}px; }}
    QFrame#dock {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(24, 56, 60, 0.90),
                  stop:1 rgba(10, 28, 34, 0.90)); border: 1px solid rgba(140, 215, 200, 0.38);
                  border-radius: {dock_r}px; }}
    QPushButton#chip2 {{ font-size: {g}px; font-weight: 400; color: #F1F5F6; padding: {ch_v}px {ch_h}px;
                        border-radius: {ch_r}px; background: rgba(255,255,255,0.035);
                        border: 1px solid rgba(255,255,255,0.20); }}
    QPushButton#chip2:hover {{ border-color: rgba(120, 230, 180, 0.6); }}
    QPushButton#barra_c {{ font-size: {g}px; font-weight: 400; color: #F1F5F6; padding: {ch_v}px {ch_h}px;
                          padding-left: {ch_e}px; text-align: left; background: transparent; border: none;
                          border-right: 1px solid rgba(140, 215, 200, 0.30); border-radius: 0px; }}
    QPushButton#barra_c:hover {{ background: rgba(255,255,255,0.05); }}
    QPushButton#barra_c[centro="1"] {{ text-align: center; padding-left: {ch_h}px; }}
    QPushButton#barra_c[lado="izq"] {{ border-top-left-radius: {dock_r}px; border-bottom-left-radius: {dock_r}px; }}
    QPushButton#barra_trailer {{ font-size: {g}px; font-weight: 500; color: #FFFFFF; padding: {ch_v}px {ch_h}px;
                                background: {verde}; border: none; border-radius: 0px;
                                border-top-right-radius: {dock_r}px; border-bottom-right-radius: {dock_r}px; }}
    QPushButton#barra_trailer:hover {{ background: #26BE80; }}    QPushButton#chip2[tipo="falta"] {{ border-color: rgba(242,184,75,0.85); color: #F2B84B; }}
    QPushButton#chip2[tipo="oro"] {{ text-align: left; padding-left: {ch_e}px; color: #F1F5F6;
                                    border-color: rgba(255,255,255,0.20); }}
    QFrame#seg {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.20);
                 border-radius: {seg_r}px; }}
    QPushButton#segb {{ font-size: {g}px; font-weight: 400; color: #E3EBED; padding: {sb_v}px {sb_h}px;
                       border-radius: {sb_r}px; border: 1px solid transparent; background: transparent; }}
    QPushButton#segb:checked {{ background: {verde}; color: #FFFFFF; border: 1px solid rgba(120, 245, 180, 0.7); }}
    QPushButton#segb:disabled:checked {{ background: {verde}; color: #FFFFFF; }}
    QPushButton#pill {{ font-size: {g}px; font-weight: 400; color: #E3EBED; padding: {pl_v}px {pl_h}px;
                       border-radius: {pl_r}px; background: rgba(255,255,255,0.035);
                       border: 1px solid rgba(255,255,255,0.20); }}
    QPushButton#pill:hover {{ border-color: rgba(120, 230, 180, 0.7); color: #FFFFFF; }}
    QPushButton#pill:checked {{ background: {verde}; color: #FFFFFF; border: 1px solid #44D894; }}
    QLabel#eta {{ font-size: {g}px; font-weight: 400; color: #F1F5F6; }}
    QLabel#titulo_pag {{ font-size: {h1}px; font-weight: 700; }}
    QPushButton#boton_verde {{ font-size: {g}px; font-weight: 500; color: #FFFFFF; padding: {bv_v}px {bv_h}px;
                              border-radius: {bv_r}px; background: {verde}; border: 1px solid #44D894; }}
    QPushButton#boton_verde:hover {{ background: #2BD08C; }}
    QFrame#stat {{ background: rgba(14, 32, 40, 0.80); border: 1px solid rgba(160, 205, 210, 0.22);
                  border-radius: {st_r}px; }}
    QFrame#stat[estado="falta"] {{ border-color: rgba(242,184,75,0.75); }}
    QLabel#stat_t {{ font-size: {st_t}px; font-weight: 500; }}
    QLabel#stat_n {{ font-size: {st_n}px; font-weight: 700; }}
    QPushButton#chip_ok {{ font-size: {ok_f}px; font-weight: 400; color: #FFFFFF; padding: {ok_v}px {ok_h}px;
                          border-radius: {ok_r}px; background: rgba(16, 70, 48, 0.55); border: 1px solid #2FC27F;
                          text-align: left; }}
    QPushButton#chip_ok[tipo="falta"] {{ border-color: #F2B84B; color: #F2B84B; background: rgba(70, 52, 16, 0.5); }}
    QFrame#vidrio {{ background: rgba(14, 32, 40, 0.74); border: 1px solid rgba(160, 210, 210, 0.22);
                    border-radius: {vd_r}px; }}
    QLabel#titulo_card {{ font-size: {tc}px; font-weight: 700; }}
    QLabel#ayuda_t {{ font-size: {ay}px; color: #AFC0C4; }}
    QLabel#etq_campo {{ font-size: {ec}px; font-weight: 700; color: #FFFFFF; }}
    QLineEdit {{ font-size: {le}px; font-weight: 400; padding: {le_v}px {le_h}px; border-radius: {le_r}px;
                background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.20); }}
    QLineEdit:focus {{ border-color: #2FC27F; }}
    QPushButton#pill_tipo {{ font-size: {pt}px; font-weight: 400; color: #E3EBED; padding: {pt_v}px {pt_h}px;
                            border-radius: {pt_r}px; background: rgba(255,255,255,0.03);
                            border: 1px solid rgba(255,255,255,0.20); }}
    QPushButton#pill_tipo:hover, QPushButton#pill_vista:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#pill_tipo:checked {{ background: {verde}; color: #FFFFFF; border: 1px solid #44D894;
                                    font-weight: 600; }}
    QPushButton#pill_vista {{ font-size: {pv}px; font-weight: 500; color: #E3EBED; padding: {pv_v}px {pv_h}px;
                             border-radius: {pv_r}px; background: rgba(255,255,255,0.03);
                             border: 1px solid rgba(255,255,255,0.20); }}
    QPushButton#pill_vista:checked {{ background: {verde}; color: #FFFFFF; border: 1px solid #44D894;
                                     font-weight: 600; }}
    QLabel#nota_t {{ font-size: {nt}px; color: #9DB0B6; }}
    QFrame#tarjeta {{ background: rgba(13, 30, 38, 0.93); border: 1px solid rgba(160, 210, 210, 0.24);
                     border-radius: {tj_r}px; }}
    QLabel#tarjeta_t {{ font-size: {tj_t}px; font-weight: 700; }}
    QLabel#fila_aj {{ font-size: {fa}px; }}
    QLabel#sub_aj {{ font-size: {sa}px; }}
    QFrame#caja_estado {{ background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.14);
                         border-radius: {ce_r}px; }}
    QPushButton#borde {{ font-size: {fa}px; font-weight: 400; padding: {bo_v}px {bo_h}px; border-radius: {bo_r}px;
                        background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.26); }}
    QPushButton#borde:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#chip {{ font-size: {g}px; padding: {bo_v}px {bo_h}px; border-radius: {bo_r}px; }}
    QPushButton#cancelar {{ font-size: {cn}px; font-weight: 500; color: #FFFFFF; padding: {cn_v}px {cn_h}px;
                           border-radius: {cn_r}px; background: rgba(255,255,255,0.03);
                           border: 1px solid rgba(255,255,255,0.40); }}
    QPushButton#cancelar:hover {{ background: rgba(255,255,255,0.08); }}
    QLabel#eta_t {{ font-size: {g}px; color: #F1F5F6; }}
    QSlider::groove:horizontal {{ height: {sl_g}px; background: rgba(140, 160, 170, 0.35); border-radius: {sl_gr}px; }}
    QSlider::sub-page:horizontal {{ background: #22C47E; border-radius: {sl_gr}px; }}
    QSlider::handle:horizontal {{ background: #FFFFFF; border: {sl_b}px solid #22C47E; width: {sl_h}px;
                                 margin: -{sl_m}px 0; border-radius: {sl_hr}px; }}
    """.format(
            verde=verde, vidrio=vidrio, a=p(32), b=p(30), c=p(28), d=p(30), g=p(36), h1=p(56),
            nav_r=p(34), tab_v=p(12), tab_h=p(40), tab_r=p(30), e_v=p(12), e_h=p(26), e_r=p(28), ctl_r=p(10),
            # (18-nov, la persona: «botones con dos diseños») TODOS los botones de esquina con el mismo radio (14)
            dock_r=p(40), ch_v=p(22), ch_h=p(30), ch_r=p(14), ch_e=p(36), seg_r=p(16), sb_v=p(16), sb_h=p(26),
            sb_r=p(12), pl_v=p(16), pl_h=p(22), pl_r=p(14), bv_v=p(18), bv_h=p(46), bv_r=p(14), st_r=p(28),
            st_t=p(36), st_n=p(80), ok_f=p(34), ok_v=p(10), ok_h=p(30), ok_r=p(28), vd_r=p(30), tc=p(50), ay=p(28),
            ec=p(34), le=p(36), le_v=p(20), le_h=p(30), le_r=p(14), pt=p(25), pt_v=p(16), pt_h=p(18), pt_r=p(14),
            pv=p(28), pv_v=p(16), pv_h=p(50), pv_r=p(14), nt=p(26), tj_r=p(28), tj_t=p(44), fa=p(32), sa=p(36),
            ce_r=p(14), bo_v=p(16), bo_h=p(30), bo_r=p(14), cn=p(34), cn_v=p(14), cn_h=p(46), cn_r=p(14),
            sl_g=p(10), sl_gr=p(5), sl_b=p(4), sl_h=p(36), sl_m=p(13), sl_hr=p(18))

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
            import threading
            hilo = threading.current_thread()

            def log(m):
                # (1.6.0) «Cancelar»: el trabajo se corta en el siguiente mensaje de ESTE hilo (los demas hilos miran
                # rutas.PARAR al empezar cada archivo)
                if rutas.PARAR.is_set() and threading.current_thread() is hilo:
                    raise rutas.Detenido()
                self.linea.emit(str(m))
            try:
                res = (self.funcion or motor.armar_todo)(log, lambda p, t: self.avance.emit(int(p), str(t)), **self.op)
                self.fin.emit(res)
            except rutas.Detenido:
                self.linea.emit("Cancelado por la persona.")
                self.fallo.emit(CANCELADO)
            except Exception as ex:
                registro.error("Armado: %s" % traceback.format_exc())      # la traza, al registro (no a la persona)
                self.linea.emit("No se pudo terminar: %s" % ex)
                self.fallo.emit(str(ex))
            except BaseException as ex:          # (1.8.0, auditoria) un SystemExit dentro de build_trailers (exec) no
                registro.error("Armado: %s" % traceback.format_exc())     # emitia ni fin ni fallo
                self.fallo.emit("el armado se detuvo (%s)" % (ex.__class__.__name__,))

    class Preanalisis(QThread):
        """(1.8.2) El analisis en segundo plano en cuanto se suelta la carpeta (motor.preanalizar)."""
        linea = Signal(str)

        def run(self):
            try:
                motor.preanalizar(lambda m: self.linea.emit(str(m)))
            except rutas.Detenido:
                pass
            except Exception:
                registro.error("Preanalisis: %s" % traceback.format_exc())

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
            if not self.isVisible():                  # (1.7) la barra en QML no se ve encima de la hoja
                self._tapados = piezas.tapar_quick(self.window())
            self.show()
            self.raise_()

        def ocultar(self, modo=None):
            if modo is None or self.modo == modo:
                self.modo = None
                self.hide()
                piezas.destapar_quick(getattr(self, "_tapados", None))
                self._tapados = []

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
            self._peli = self._cuadro = None    # (1.6.0) el cielo que se mueve (recursos/animaciones/cielo.mp4)
            self._t_tam = QTimer(self, singleShot=True, interval=450)
            self._t_tam.timeout.connect(self._video)
            # (1.6.1, la persona: «no se ve fluido») el video del cielo llega a 8 cuadros por segundo: en vez de saltar
            # de uno a otro (se veia a tirones en toda la ventana), cada cuadro se FUNDE con el anterior a 30 por
            # segundo. Mismo video y mismo proceso de ffmpeg; solo dos copias por pintada.
            self._antes = None                  # el cuadro anterior (img, datos)
            self._t_cuadro, self._periodo = 0.0, 0.125
            self._reloj = QTimer(self)
            self._reloj.timeout.connect(self._tic)
            self._reloj.start(self.PASO_MS)

        PASO_MS = 50        # 20 por segundo: repintar TODA la ventana cuesta 8-12 ms (medido); las nebulosas van lentas
        # (18-nov, la persona: «las animaciones de fondo nada fluido y sin sentido», «va algo trabado y lagueado») El
        # video del cielo (nebulosas a 8 cuadros por segundo, fundidas) obligaba a repintar TODA la ventana 20 veces
        # por segundo, con todo lo de encima: eso frenaba botones, paginas y el astrolabio. Ahora el cielo es la imagen
        # quieta y solo titilan unas estrellas, repintando nada mas sus pocos pixeles. VIDEO = True lo trae de vuelta.
        VIDEO = False
        TITILAN = 26

        _nebulosa = None

        def poner_nebulosa(self):
            """(1.7.7, la persona eligio «Nebulosa esmeralda») El fondo vivo: qml/Nebulosa.qml (un shader en la tarjeta de
            video) DEBAJO de todo. No repinta la ventana de widgets (lo de encima no se vuelve a pintar): solo la tarjeta
            mezcla la imagen. Va un rato despues de abrir. Si Qt Quick o el shader fallan, queda la imagen quieta.
            TRAILER_NEBULOSA=0 la apaga."""
            if self._nebulosa is not None or os.environ.get("TRAILER_NEBULOSA") == "0":
                return
            try:
                from PySide6.QtQuickWidgets import QQuickWidget
                from PySide6.QtCore import QUrl
                import barra_qml
                q = QQuickWidget(self)
                q.setResizeMode(QQuickWidget.SizeRootObjectToView)
                q.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                q.setFocusPolicy(Qt.NoFocus)
                q.setSource(QUrl.fromLocalFile(os.path.join(barra_qml.CARPETA, "Nebulosa.qml")))
                if q.status() == QQuickWidget.Error or q.rootObject() is None:
                    raise RuntimeError("; ".join(e.toString() for e in q.errors()) or "sin raiz")
                q.setGeometry(self.rect())
                q.lower()
                q.show()
                self._nebulosa = q
                self.TITILAN = 0                    # las estrellas ya titilan en el shader
                self._cuadros_nebulosa = None
                self.update()
            except Exception as ex:
                registro.info("La nebulosa no cargó (queda el cielo quieto): %s" % ex)
                self._nebulosa = False

        def _ritmo_nebulosa(self, ver):
            """30 cuadros con la ventana en uso, 10 sin foco (ahi suele estar DaVinci usando la tarjeta), 0 minimizada."""
            if not self._nebulosa:
                return
            c = 0 if not ver else (30 if self.window().isActiveWindow() else 10)
            try:                                # (1.7.8) «menos movimiento» de Windows: el cielo quieto
                import barra_qml
                if barra_qml.movimiento_reducido():
                    c = 0
            except Exception:
                pass
            if c != getattr(self, "_cuadros_nebulosa", None):
                self._cuadros_nebulosa = c
                try:
                    self._nebulosa.rootObject().setProperty("cuadros", c)
                except Exception:
                    pass

        def _tic(self):
            self.t += self.PASO_MS / 1000.0
            ver = self.isVisible() and not self.window().isMinimized()      # minimizada no se pinta nada
            self._ritmo_nebulosa(ver)
            if self._nebulosa:                  # la nebulosa lo hace todo en la tarjeta: aqui no se repinta nada
                return
            if not self.VIDEO:
                if ver and self.window().isActiveWindow():
                    from PySide6.QtGui import QRegion
                    from PySide6.QtCore import QRect
                    w, h, zona = self.width(), self.height(), QRegion()
                    for x, y, _r, _f, _v in self.estrellas[:self.TITILAN]:
                        zona += QRect(int(x * w) - 4, int(y * h) - 4, 8, 8)
                    self.update(zona)
                return
            if self._peli is not None:
                self._peli.pausar(not ver)
                self._peli.lento(not self.window().isActiveWindow())
            # con la ventana en uso, el fundido (30 por segundo); sin foco, solo al llegar cada cuadro (poca CPU:
            # repintar toda la ventana cuesta ~9 ms y ahi suele estar DaVinci trabajando)
            if ver and (self._cuadro is None or self.window().isActiveWindow()):
                self.update()

        def showEvent(self, e):
            super().showEvent(e)
            if self.VIDEO and self._peli is None:          # un rato despues de abrir (regla de arranque)
                QTimer.singleShot(1500, self._video)

        def _video(self):
            """(1.6.0) El cielo de Higgsfield en movimiento (nebulosas que fluyen), a 1/3 de su velocidad (8 cuadros
            por segundo: calma y poca CPU) y del tamaño de la ventana: ffmpeg lo escala en su proceso y aqui solo se
            copia cada cuadro."""
            import animacion
            ruta = animacion.ruta("cielo.mp4")
            if not ruta:
                return
            if self._peli is None:
                self._peli = animacion.Pelicula(self._al_cuadro, None, self)
            esc = self.devicePixelRatioF()
            w, h = int(self.width() * esc) // 2 * 2, int(self.height() * esc) // 2 * 2
            if self._peli.ruta and self._peli.tam == (w, h):
                return
            self._peli.reproducir(ruta, w, h, fps=8, bucle=True)

        def _al_cuadro(self, img, datos):
            ahora = time.monotonic()
            if self._cuadro is not None and self._cuadro[0].size() == img.size():
                self._antes = self._cuadro
                if 0.03 < ahora - self._t_cuadro < 1.0:             # el ritmo real con que llegan (lento sin foco)
                    self._periodo = 0.7 * self._periodo + 0.3 * (ahora - self._t_cuadro)
            else:
                self._antes = None
            self._cuadro = (img, datos)
            self._t_cuadro = ahora
            if not self.window().isActiveWindow():
                self._antes = None              # sin foco: sin fundido, una pintada por cuadro
                self.update()

        def pausar(self, si):                   # bajo la escena de Inicio no hace falta animarlo
            # (antes buscaba «el primer QTimer» y era el del cambio de tamaño: el reloj del cielo no se tocaba)
            self._reloj.stop() if si else self._reloj.start(self.PASO_MS)

        def resizeEvent(self, e):
            super().resizeEvent(e)
            if self._nebulosa:
                self._nebulosa.setGeometry(self.rect())
            agarre = getattr(self.window(), "agarre", None)        # (1.7.9) siempre en la esquina de abajo
            if agarre is not None:
                agarre.move(self.width() - agarre.width(), self.height() - agarre.height())
                agarre.raise_()
            if getattr(self, "al_cambiar", None):
                self.al_cambiar()
            if self._peli is not None:
                self._t_tam.start()

        def _pintar_fondo(self, w, h, escala):
            """Lo que no cambia (dos degradados a toda la ventana y las constelaciones), pintado una sola vez por
            tamano: rellenar esos degradados en cada latido costaba varios ms y arrastraba a todo lo de encima."""
            pm = QPixmap(max(1, int(w * escala)), max(1, int(h * escala)))
            pm.setDevicePixelRatio(escala)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            todo = QRectF(0, 0, w, h)
            # (1.6.0) el cielo de la maqueta: la imagen de Higgsfield (estrellas y nebulosas verdes), sin constelaciones
            img = getattr(self, "_img_cielo", None)
            if img is None:
                from PySide6.QtGui import QImage
                ruta = os.path.join(rutas.RECURSOS, "cielo.jpg")
                self._img_cielo = img = QImage(ruta) if os.path.isfile(ruta) else QImage()
            if not img.isNull():
                esc = max(w / img.width(), h / img.height())
                tw, th = img.width() * esc, img.height() * esc
                p.drawImage(QRectF((w - tw) / 2, (h - th) / 2, tw, th), img)
            else:
                g = QRadialGradient(QPointF(w * 0.5, h * 0.45), max(w, h) * 0.75)
                g.setColorAt(0.0, QColor("#12303A"))
                g.setColorAt(0.45, QColor("#0B1C26"))
                g.setColorAt(1.0, QColor("#050C13"))
                p.fillRect(todo, g)
            p.end()
            return pm

        def paintEvent(self, _):
            w, h, escala = self.width(), self.height(), self.devicePixelRatioF()
            if self._fondo is None or self._fondo[:3] != (w, h, escala):
                self._fondo = (w, h, escala, self._pintar_fondo(w, h, escala))
            p = QPainter(self)
            if self._cuadro is not None:        # el cuadro del video (si aun es de otro tamaño, estirado)
                img = self._cuadro[0]
                justo = abs(img.width() - w * escala) < 3 and abs(img.height() - h * escala) < 3
                donde = QRectF(0, 0, img.width() / escala, img.height() / escala) if justo else QRectF(0, 0, w, h)
                u = min(1.0, (time.monotonic() - self._t_cuadro) / max(0.04, self._periodo))
                if self._antes is not None and u < 1.0:             # fundido del cuadro anterior al nuevo
                    p.drawImage(donde, self._antes[0])
                    p.setOpacity(u)
                    p.drawImage(donde, img)
                    p.setOpacity(1.0)
                else:
                    p.drawImage(donde, img)
            else:
                p.drawPixmap(0, 0, self._fondo[3])
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            for x, y, r, fase, vel in self.estrellas[:70 if self.VIDEO else self.TITILAN]:    # unas pocas titilan
                a = 30 + 170 * (0.5 + 0.5 * math.sin(self.t * vel + fase))
                p.setBrush(QColor(220, 240, 245, int(a)))
                p.drawEllipse(QPointF(int(x * w), int(y * h)), r * 0.9, r * 0.9)

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
            # (1.6.0, la persona: «primero pongo las carpetas y después, cuando yo decido, empieza») sala de espera:
            # soltar solo agrega la carpeta a la lista; arma al pulsar el boton. Lo soltado mientras mira otra, a la cola.
            self._cola_soltar = []
            self._falta_datos = False            # evento nuevo sin nombres: se piden al pulsar el boton
            self._ultimo_fallo = None
            self.resultado = None
            self.material = {"ok": False, "cuenta": {"foto": 0, "video": 0, "dron": 0}, "faltan": []}
            self.est = motor.leer_estado()
            self._carpetas = [c for c in (self.est.get("carpetas") or []) if isinstance(c, str)]
            # en espera: hay carpetas puestas y aun no se ha pulsado el boton (ni el evento esta ya terminado)
            self._en_espera = bool(self._carpetas) and (self.est.get("terminado") or "") != self.est.get("evento", "-")

            fondo = QVBoxLayout(self)
            fondo.setContentsMargins(0, 0, 0, 0)
            self.cielo = Cielo()
            fondo.addWidget(self.cielo)
            raiz = QVBoxLayout(self.cielo)
            raiz.setContentsMargins(22, 18, 22, 14)
            raiz.setSpacing(12)

            # --- barra superior (1.6.0: el icono, el nombre y una pastilla de estado en vez de la franja de avisos)
            barra = QHBoxLayout()
            barra.setSpacing(piezas.px(26))
            self.b_logo = QPushButton(objectName="logo")      # un clic: el menu con lo que no esta en el diseño
            self.b_logo.setIcon(icono_app())
            self.b_logo.setIconSize(QSize(piezas.px(72), piezas.px(72)))
            self.b_logo.setCursor(Qt.PointingHandCursor)
            self.b_logo.setToolTip("Más: carpetas, DaVinci, nombres originales…")
            self.b_logo.clicked.connect(self._menu_mas)
            barra.addWidget(self.b_logo)
            marca = QLabel("CINEMA PRODUCTIONS", objectName="marca")
            barra.addWidget(marca)
            barra.addStretch(1)
            nav = QFrame(objectName="nav")
            hn = QHBoxLayout(nav)
            hn.setContentsMargins(6, 6, 6, 6)
            hn.setSpacing(2)
            self.grupo_tabs = QButtonGroup(self)
            self.tabs = {}
            # el numero de cada pestaña es el de su pagina (self.paginas); el orden a la vista va aparte
            for i, txt in enumerate(("Inicio", "Material", "Textos", "Ajustes", "Tráilers", "Plantillas")):
                b = QPushButton(txt, objectName="tab", checkable=True)
                b.setCursor(Qt.PointingHandCursor)
                self.grupo_tabs.addButton(b, i)
                self.tabs[txt] = b
            # (19-nov, la persona: «la página de Textos elimínala» y «crea una página para plantillas y otra de
            # tráilers súper minimalista, solo de escoger el estilo; la de Material elimínala») Textos y Material sin
            # pestaña: sus piezas siguen por dentro (el armado lee los nombres; el material se suelta en la ventana)
            for txt in ("Inicio", "Tráilers", "Plantillas", "Ajustes", "Material", "Textos"):
                hn.addWidget(self.tabs[txt])
            self.tabs["Material"].hide()
            self.tabs["Textos"].hide()
            self.tabs["Inicio"].setChecked(True)
            # (1.7.9, revision de pulido) las 4 pestañas del MISMO ancho: separacion pareja y la gota no cambia de
            # tamaño al viajar
            self._igualar_tabs()
            QTimer.singleShot(0, self._igualar_tabs)          # ya con el estilo puesto
            # (1.7.8) la gota de vidrio verde de la pestaña activa: se desliza de una pestaña a otra
            self.gota_tabs = piezas.GotaPestanas(nav, self.grupo_tabs)
            self.punto = QLabel("●")
            self.punto.setStyleSheet("color:%s; font-size:16px; padding: 0 10px;" % TENUE)
            self.punto.setToolTip("DaVinci Resolve")
            hn.addWidget(self.punto)
            self.punto.hide()                        # (1.6.0) DaVinci va en la pastilla de estado
            barra.addWidget(nav)
            barra.addStretch(1)
            # la pastilla de estado: «Todo listo» / «Trabajando» / avisos; un clic muestra lo que va haciendo
            self.b_log = QPushButton("Revisando…", objectName="estado", checkable=True)
            self.b_log.setCursor(Qt.PointingHandCursor)
            self.b_log.setIconSize(QSize(piezas.px(24), piezas.px(24)))
            self.b_log.setIcon(piezas.qicono("punto", TENUE, piezas.px(24)))
            self.b_log.setToolTip("Ver lo que va haciendo")
            barra.addWidget(self.b_log)
            barra.addSpacing(6)
            ctrls = QFrame(objectName="ventanita")
            hc = QHBoxLayout(ctrls)
            hc.setContentsMargins(6, 4, 6, 4)
            for tipo, ayuda, acc in (("min", "Minimizar", self.showMinimized), ("max", "Maximizar", self._maximizar),
                                     ("x", "Cerrar", self.close)):         # (1.6.0) dibujados y sin caja (maqueta)
                b = piezas.BotonIcono(tipo, ayuda, rojo=tipo == "x")
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
            self.aviso.hide()                        # (1.6.0) solo aparece un rato con cada aviso (ver _avisar)
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
            for pag in (self._pagina_material(), self._pagina_textos(), self._pagina_ajustes(),
                        self._pagina_trailers(), self._pagina_plantillas()):
                sa = QScrollArea()                       # en una pantalla chica se desplazan en vez de agrandar la ventana
                sa.setWidgetResizable(True)
                sa.setFrameShape(QFrame.NoFrame)
                sa.setStyleSheet("QScrollArea { background: transparent; border: none; }")
                sa.viewport().setAutoFillBackground(False)
                sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                sa.setWidget(pag)
                pag.setAutoFillBackground(False)        # setWidget lo enciende: el cielo debe verse detras
                self.paginas.addWidget(sa)
            self.grupo_tabs.idClicked.connect(self._cambiar_pagina)
            import animacion
            self.fundido = animacion.Fundido(self.paginas)      # (1.6.0) la pagina de antes se desvanece
            _tiempo("  demas paginas")
            import escena_go                         # la escena de Inicio de CineCaptions (esfera de particulas)
            self.escena = escena_go.EscenaGo(self.cielo)
            self.escena.lower()
            self.escena.poner_pasos([])              # (1.6.0) los pasos van en self.pasos (fila de pasos del diseño)
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
            QTimer.singleShot(0, self._brillos)
            _tiempo("  escena")

            # (1.7.9, revision de pulido) el agarre para cambiar el tamaño, INVISIBLE en la esquina (sus puntitos se
            # veian en todas las paginas y su fila comia ~28 px abajo); los bordes de la ventana tambien la estiran
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            self.agarre = QSizeGrip(self.cielo)
            self.agarre.setFixedSize(18, 18)
            efecto = QGraphicsOpacityEffect(self.agarre)
            efecto.setOpacity(0.0)
            self.agarre.setGraphicsEffect(efecto)

            # --- vigilancia de carpetas y chequeo
            self.vigia = QFileSystemWatcher([d for d in rutas.CARPETAS.values() if os.path.isdir(d)], self)
            self.espera = QTimer(self, singleShot=True, interval=800)
            self.espera.timeout.connect(self._revisar_material_fondo)
            self.vigia.directoryChanged.connect(lambda _: self.espera.start())
            self.t_dv = QTimer(self)
            self.t_dv.timeout.connect(self._ver_davinci)
            self.t_dv.start(10000)
            QApplication.instance().installEventFilter(self)       # bordes para cambiar el tamano
            self._sin_recorte()                                    # (al final: mide texto, y las fuentes ya cargaron)
            self._chips_editable()
            self.t_eta = QTimer(self)                # «Listo a las 17:40» sigue al reloj
            self.t_eta.timeout.connect(self._sub_material)
            self.t_eta.start(60000)
            _tiempo("  final")
            QTimer.singleShot(300, self._arranque)
            QTimer.singleShot(700, self._barra_a_qml)    # (1.7) con la ventana ya a la vista
            QTimer.singleShot(1300, self.cielo.poner_nebulosa)    # (1.7.7) el fondo vivo, despues de la barra
            QTimer.singleShot(6000, self._mudar_proxies)  # (19-nov) los proxies de antes, a Videos

        # ============================================================== paginas
        def _pagina_inicio(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            # el astrolabio va en un hueco que toma el espacio libre y NO esta en el layout: asi su tamano fijo no impide
            # achicar la ventana (en una laptop de 768 px de alto no cabia); _centrar_boton lo pone en medio.
            # (1.6.0) Es la imagen del astrolabio de la maqueta (Higgsfield); trabajando, el de la ventana verde con el
            # avance real encima. Misma API que boton_go.BotonGo.
            self.hueco_boton = QWidget()
            self.hueco_boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.hueco_boton.setMinimumHeight(160)
            self.boton = piezas.Astrolabio(os.path.join(rutas.RECURSOS, "astrolabio_inicio.png"),
                                           os.path.join(rutas.RECURSOS, "astrolabio_trabajo.png"))
            self.boton.setParent(self.hueco_boton)
            self.boton.clicked.connect(lambda *_: self._play())
            v.addWidget(self.hueco_boton, 1)
            # (1.6.0) el titulo entre dos adornos dorados, como en el diseño
            fila_t = QHBoxLayout()
            fila_t.setSpacing(piezas.px(56))
            fila_t.addStretch(1)
            self.adornos = (piezas.Adorno("izq"), piezas.Adorno("der"))
            fila_t.addWidget(self.adornos[0], 0, Qt.AlignVCenter)
            self.titulo = piezas.Titulo(TITULO_INICIO, tam=100)    # blanco y «listo» en oro, como la maqueta
            fila_t.addWidget(self.titulo)
            fila_t.addWidget(self.adornos[1], 0, Qt.AlignVCenter)
            fila_t.addStretch(1)
            v.addLayout(fila_t)
            self.sub = QLabel("", objectName="sub")
            self.sub.setAlignment(Qt.AlignCenter)
            self.sub.setWordWrap(True)
            v.addWidget(self.sub)
            self.reserva = QWidget()                 # (1.6.0) ya no se usa: los pasos van en self.panel_trabajo
            self.reserva.setFixedHeight(0)
            v.addWidget(self.reserva)
            # (1.6.1) la sala de espera: las carpetas soltadas flotando y el boton «Empezar» (piezas.Sala)
            self.sala = piezas.Sala()
            self.sala.empezar.connect(lambda: self._play())
            self.sala.hide()
            v.addWidget(self.sala)
            v.addSpacing(4)
            # chips de lo ya hecho: abrir videos, editar en DaVinci, renderizar lo editado, cancelar la copia
            fila_c = QHBoxLayout()
            fila_c.setSpacing(14)                   # (18-nov) iban pegados y con letra chica
            fila_c.addStretch(1)
            self.chip_videos =QPushButton("Abrir videos terminados", objectName="chip")
            self.chip_videos.setCursor(Qt.PointingHandCursor)
            self.chip_videos.clicked.connect(self._abrir_videos)
            self.chip_videos.hide()
            fila_c.addWidget(self.chip_videos)
            # la linea de cada evento queda editable en DaVinci: retocar y volver a sacar el video sin rearmar
            self.chip_editar = QPushButton("Editar en DaVinci", objectName="chip")
            self.chip_editar.setCursor(Qt.PointingHandCursor)
            self.chip_editar.setToolTip("Elige un video y DaVinci abre SOLO su proyecto, con su línea en Edición: "
                                        "retoca lo que no te guste (cortes, textos, color, música).")
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
            v.addSpacing(12)
            # (1.6.0) el panel de abajo (el «dock» del diseño): lo que hay, el evento, el formato, las duraciones y la
            # hora en que estara listo. Los dos formatos guardan sus duraciones; el selector muestra las de uno
            px = piezas.px
            self.dock = QFrame(objectName="dock")
            dv = QVBoxLayout(self.dock)
            dv.setContentsMargins(0, 0, 0, 0)
            dv.setSpacing(0)
            # (19-nov, la persona: «más minimalista, 3 botones: tráiler, plantillas y el nombre») el panel es UNA barra:
            # el nombre | Plantillas | Tráiler (verde). Lo demás (formato, duraciones, material, la hora, evento
            # nuevo) va dentro de sus popups
            f1 = QHBoxLayout()
            f1.setSpacing(0)
            self.b_nombre = piezas.Chip("", "lapiz", "#EBCB8F", nombre="barra_c", lado=46)
            self.b_nombre.setProperty("lado", "izq")
            self.b_nombre.setToolTip("Los nombres del XV o de los novios")
            self.b_nombre.clicked.connect(self._editar_nombre)
            f1.addWidget(self.b_nombre, 16)
            self.b_plantillas = piezas.Chip("   Plantillas", "claqueta", "#EEF3F4", nombre="barra_c", lado=46)
            self.b_plantillas.setProperty("centro", "1")
            self.b_plantillas.setToolTip("Cada video terminado, editable en DaVinci: abrirlo o sacarlo de nuevo")
            self.b_plantillas.clicked.connect(self._plantillas)
            f1.addWidget(self.b_plantillas, 10)
            self.b_trailer = piezas.Chip("   Tráiler", "play", "#FFFFFF", nombre="barra_trailer", lado=40)
            self.b_trailer.setToolTip("Qué videos salen y empezar a armarlos")
            self.b_trailer.clicked.connect(self._trailer)
            f1.addWidget(self.b_trailer, 10)
            # (1.7) la barra en QML entra un momento despues de abrir (_barra_a_qml): crearla cuesta ~0,5 s
            self.barra_qml = None
            self._f1_barra = f1
            dv.addLayout(f1)
            # las piezas de antes siguen (las llenan _pintar_evento y _sub_material) pero ya no se ven
            self.chips_mat = {}
            for tipo in ("foto", "video", "dron"):
                ch = piezas.Chip("", tipo, "#EEF3F4", self.dock, lado=50)
                ch.hide()
                self.chips_mat[tipo] = ch
            self.chip_mat = piezas.Chip("", "video", "#EEF3F4", self.dock, lado=50)
            self.chip_evento = piezas.Chip("", "lapiz", "#EEF3F4", self.dock, lado=46)
            self.chip_que = piezas.Chip("", "pelicula", "#EEF3F4", self.dock, lado=46)
            self.l_eta = QLabel("", self.dock, objectName="eta")
            self.chip_nuevo = piezas.ChipGiro("", "refrescar", "#EEF3F4", self.dock, lado=46)
            for x in (self.chip_mat, self.chip_evento, self.chip_que, self.l_eta, self.chip_nuevo):
                x.hide()
            self.caja_videos = QWidget(self.dock)    # va dentro del popup de chip_que; aqui, guardada sin verse
            self.caja_videos.hide()
            cv = QVBoxLayout(self.caja_videos)       # arriba el formato, abajo sus duraciones (en el popup no caben juntos)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(px(24))
            f_fmt = QHBoxLayout()
            f2 = QHBoxLayout()
            f2.setSpacing(px(18))
            cv.addLayout(f_fmt)
            cv.addLayout(f2)
            self.seg_formato = piezas.Segmentado(["Horizontal", "Vertical"], 0)
            self.seg_formato.setToolTip("Horizontal 16:9: usa los videos horizontales y también los verticales.\n"
                                        "Vertical 9:16 para celular: solo los videos grabados en vertical.")
            self.seg_formato.cambio.connect(self._ver_formato)
            f_fmt.addStretch(1)
            f_fmt.addWidget(self.seg_formato)
            f_fmt.addStretch(1)
            f2.addStretch(1)
            eleg_h, eleg_v = versiones_guardadas(self.est)
            self._palomita = piezas.qicono("palomita", "#FFFFFF", px(30))   # dibujada: «✓» no esta en la fuente
            self.pills, self.pills_v, self.etqs_formato, self.bs_todas = {}, {}, [], []
            for ayuda, pills, elegidas in (
                    ("16:9 · usa los videos horizontales y también los verticales", self.pills, eleg_h),
                    ("9:16 para celular · solo usa los videos grabados en vertical", self.pills_v, eleg_v)):
                for ver in motor.VERSIONES:
                    b = QPushButton((" " if ver in elegidas else "") + VERSION_TEXTO[ver], objectName="pill", checkable=True)
                    b.setIconSize(QSize(px(30), px(30)))
                    b.setIcon(self._palomita if ver in elegidas else QIcon())
                    b.setCursor(Qt.PointingHandCursor)
                    b.setChecked(ver in elegidas)
                    b.setToolTip(ayuda)
                    b.toggled.connect(self._cambio_plantillas)
                    pills[ver] = b
                    f2.addWidget(b)
            f2.addStretch(1)
            fila_d = QHBoxLayout()
            fila_d.setContentsMargins(px(90), 0, px(90), 0)
            fila_d.addWidget(self.dock, 1)
            v.addLayout(fila_d)
            # mientras trabaja, en vez del panel: los pasos y el avance de cada version (con «Cancelar»)
            self.panel_trabajo = QWidget()
            self.panel_trabajo.setMaximumWidth(px(1760))
            pt = QVBoxLayout(self.panel_trabajo)
            pt.setContentsMargins(0, 0, 0, 0)
            pt.setSpacing(px(40))
            self.pasos = piezas.Pasos(PASOS_VISTA)
            pt.addWidget(self.pasos)
            self.versiones = piezas.Versiones()
            self.versiones.cancelar.connect(self._cancelar)
            pt.addWidget(self.versiones)
            self._pt_trabajo, self.trabajo_qml = pt, None    # (1.7) _barra_a_qml los cambia por la de QML
            fila_p = QHBoxLayout()
            fila_p.addStretch(1)
            fila_p.addWidget(self.panel_trabajo, 10)
            fila_p.addStretch(1)
            v.addLayout(fila_p)
            self.panel_trabajo.hide()
            v.addSpacing(8)
            self._ver_formato(0)
            self._pintar_evento()
            return w

        def _barra_a_qml(self):
            """(1.7, la persona: «quédate con QML / Qt Quick por partes; es más rápido») la barra del Inicio pasa a
            la de QML (barra_qml.py, la pinta la tarjeta grafica). Va despues de abrir: crearla y su primer cuadro
            cuestan ~0,5 s; hasta entonces se ven los tres botones de siempre (mismo diseño). Si Qt Quick no carga,
            se quedan esos."""
            if self.barra_qml is not None:
                return
            try:
                import barra_qml
                if not barra_qml.disponible():
                    return
                # (1.8.5) Plantillas elige las de la pagina Plantillas (antes abria los proyectos de DaVinci, que
                # siguen en «Editar en DaVinci» / «Renderizar lo editado»)
                self.barra_qml = barra_qml.BarraQML(self.dock, self._editar_nombre, self._plantillas_barra, self._trailer)
                self._refrescar_barra()
                f1 = self._f1_barra
                for b in (self.b_nombre, self.b_plantillas, self.b_trailer):
                    f1.removeWidget(b)
                    b.hide()
                f1.addWidget(self.barra_qml.widget, 1)
                self.dock.setStyleSheet("QFrame#dock { background: transparent; border: none; }")
                self._pintar_evento()
            except Exception as ex:
                registro.info("La barra en QML no cargó (quedan los botones de siempre): %s" % ex)
                self.barra_qml = None
            # (1.7, parte 2) la pantalla de trabajo: los pasos y las versiones en QML (qml/Trabajo.qml). Los adaptadores
            # tienen la misma API que piezas.Pasos / piezas.Versiones: el resto de la ventana no cambia
            if self.barra_qml is not None and self.trabajo_qml is None:
                try:
                    t = barra_qml.TrabajoQML(self.panel_trabajo, PASOS_VISTA, self._cancelar, self.pasos, self.versiones)
                    viejo = self.versiones.b_cancelar
                    t.versiones.b_cancelar.setEnabled(viejo.isEnabled())
                    t.versiones.b_cancelar.setText(viejo.text())
                    t.versiones.poner_eta(self.versiones.l_eta.text())
                    for w in (self.pasos, self.versiones):
                        self._pt_trabajo.removeWidget(w)
                        w.hide()
                        w.deleteLater()
                    self._pt_trabajo.addWidget(t.widget)
                    self.trabajo_qml, self.pasos, self.versiones = t, t.pasos, t.versiones
                except Exception as ex:
                    registro.info("La pantalla de trabajo en QML no cargó (queda la de siempre): %s" % ex)
            # (1.7, parte 3) los popups en QML (qml/Popup.qml): se crea ya, asi el primero no tarda
            if self.barra_qml is not None and getattr(self, "popup_qml", None) is None:
                try:
                    self.popup_qml = barra_qml.PopupQML(self)
                except Exception as ex:
                    self.popup_qml = None
                    registro.info("Los popups en QML no cargaron (quedan los de siempre): %s" % ex)
            # (1.7, parte 4) las paginas Tráilers, Plantillas y Ajustes en QML. Los widgets de siempre siguen (sin
            # verse) guardando el estado; la pagina QML los lee (PaginaQML.leer) y les pide (acciones)
            if self.barra_qml is not None and not getattr(self, "paginas_qml", None):
                self.paginas_qml = {}
                for indice, archivo, poner, leer, acciones, soltar in (
                        (4, "Trailers.qml", self._pag_trailers, self._datos_trailers, self._acciones_trailers(), None),
                        (5, "Plantillas.qml", self._pag_plantillas, self._datos_plantillas, self._acciones_plantillas(),
                         self._soltar_plantillas),
                        (3, "Ajustes.qml", None, self._datos_ajustes, self._acciones_ajustes(), None)):
                    try:
                        if poner is not None:
                            pag, lay = poner
                            p = barra_qml.PaginaQML(archivo, pag, leer, acciones, soltar)
                            for c in pag.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                                if c is not p.widget:
                                    c.hide()
                            lay.setContentsMargins(0, 0, 0, 0)
                            lay.insertWidget(0, p.widget, 10)
                        else:
                            p = barra_qml.PaginaQML(archivo, self.aj_mas.parentWidget(), leer, acciones, soltar)
                            for c in (self.aj_principal, self.aj_mas, self.b_mas_aj):
                                c.hide()
                            self._aj_der.insertWidget(0, p.widget)
                        self.paginas_qml[indice] = p
                    except Exception as ex:
                        registro.info("La página %s en QML no cargó (queda la de siempre): %s" % (archivo, ex))
                self.paginas.currentChanged.connect(
                    lambda i: self.paginas_qml[i].entrar(self._direccion_pagina(i)) if i in self.paginas_qml
                    else self._direccion_pagina(i))

        # ---- (1.7) lo que muestran las paginas QML y lo que piden (las piezas de siempre, sin verse, mandan)
        def _datos_trailers(self):
            m = getattr(self, "seg_musica", None)
            return {"estilos": [b.text() for b in m.botones] if m else [], "estilo": m.actual() if m else -1,
                    "intros": [b.text() for b in self.seg_intro.botones], "intro": self.seg_intro.actual()}

        def _acciones_trailers(self):
            return {"estilo": lambda i: self.seg_musica.botones[int(i)].click(),
                    "intro": lambda i: self.seg_intro.botones[int(i)].click(),
                    "oir": lambda i: self._ver_canciones(int(i)),
                    "ver_intro": lambda i: self._ver_intro(int(i))}

        PLANTILLAS_OPCIONES = {"plantillas_texto": "Título con los nombres", "plantillas_destellos": "Destellos de luz",
                               "plantillas_fundidos": "Transiciones"}

        def _datos_plantillas(self):
            from PySide6.QtCore import QUrl
            lista = []
            for i in self.plantillas.infos:
                portada = os.path.join(i.get("carpeta", ""), "portada.jpg")
                lista.append({"nombre": i.get("nombre", ""), "dur": round(float(i.get("dur") or 0), 1),
                              "planos": len(i.get("planos") or []),
                              "portada": QUrl.fromLocalFile(portada).toString() if os.path.isfile(portada) else ""})
            return {"lista": lista, "marcadas": sorted(self.plantillas.marcadas),
                    "opciones": [{"clave": k, "texto": self.PLANTILLAS_OPCIONES.get(k, k), "si": ch.isChecked()}
                                 for k, ch in self.ch_pl.items()]}

        def _acciones_plantillas(self):
            def marcar(nombre):
                marcadas = set(self.plantillas.marcadas) ^ {nombre}
                self.plantillas.elegidas(sorted(marcadas))
                self._plantillas_elegidas(sorted(marcadas))
            return {"marcar": marcar,
                    "opcion": lambda v: self.ch_pl[v["clave"]].setChecked(bool(v["si"])),
                    "agregar": lambda _v: self._elegir_plantilla()}

        def _soltar_plantillas(self, archivos):
            import plantillas_ui
            videos = [a for a in archivos if a.lower().endswith(plantillas_ui.VIDEO_EXT)]
            if videos:
                self._importar_plantillas(videos)
            else:
                self._avisar("Para una plantilla suelta un video (Reel, TikTok, CapCut).", "warn")

        def _datos_ajustes(self):
            ia, oido = self.l_ia.text(), self.l_oido.text()
            return {"interruptores": [{"clave": k, "texto": t, "si": ch.isChecked()} for k, t, ch in (
                        ("render", "Renderizar al terminar", self.ch_render), ("igualar", "Igualar luz y color", self.ch_igualar),
                        ("vert", "Usar videos verticales", self.ch_vert),
                        ("liberar", "Cerrar programas pesados al armar", self.ch_liberar),
                        ("proxies", "Proxies para editar", self.ch_proxies))],
                    "proxies_ruta": rutas.carpeta_proxies() if self.ch_proxies.isChecked() else "",
                    # (19-nov) el ruido de DaVinci (temporal, el que mas limpia), a la vista: antes solo en el menu
                    "ruido_dv": {"texto": self.l_ruido_dv.text(), "hay": not self.b_ruido_quitar.isHidden(),
                                 "ocupado": not self.b_ruido_dv.isEnabled()},
                    "voz": [{"clave": k, "texto": b.text(), "si": b.isChecked()} for k, b in self.ch_voz.items()],
                    "ruido": self.s_ruido.value(),
                    "ia": {"texto": ia, "ok": "Lista" in ia, "boton": "" if self.b_ia.isHidden() else self.b_ia.text()},
                    "oido": {"texto": oido, "ok": "Listo" in oido,
                             "boton": "" if self.b_oido.isHidden() else self.b_oido.text()},
                    "cache": {"texto": self.l_cache.text(), "frac": round(float(self.barra_cache.frac), 3)},
                    "version": self.l_version.text(), "act": "" if self.l_act.isHidden() else self.l_act.text(),
                    "buscando": not self.b_buscar.isEnabled()}          # (1.8.4) el boton de vidrio, «ocupado»

        def _acciones_ajustes(self):
            ch = {"render": self.ch_render, "igualar": self.ch_igualar, "vert": self.ch_vert, "liberar": self.ch_liberar,
                  "proxies": self.ch_proxies}

            def abrir_proxies(_v):
                os.makedirs(rutas.carpeta_proxies(), exist_ok=True)
                rutas.abrir(rutas.carpeta_proxies())
            return {"interruptor": lambda v: ch[v["clave"]].setChecked(bool(v["si"])),
                    "abrir_proxies": abrir_proxies,
                    "ruido_dv_guardar": lambda _v: self._guardar_ruido_dv(),
                    "ruido_dv_quitar": lambda _v: self._quitar_ruido_dv(),
                    "voz": lambda v: self.ch_voz[v["clave"]].setChecked(bool(v["si"])),
                    "ruido": lambda v: self.s_ruido.setValue(int(v)),
                    "instalar_ia": lambda _v: self._instalar_ia(),
                    "instalar_oido": lambda _v: self._instalar_oido(),
                    "borrar_cache": lambda _v: self._borrar_cache(),
                    "buscar": lambda _v: self._buscar_actualizacion(manual=True)}

        def _elegir_videos(self, titulo="¿Qué videos salen?",
                           texto="Horizontal para pantalla y YouTube; vertical para el celular. Marca las duraciones.",
                           botones=("Listo",)):
            """(19-nov) El formato y las duraciones, en un popup (antes, una fila fija en el Inicio). Devuelve el boton."""
            if self.trabajo is not None:
                return None
            qml = getattr(self, "popup_qml", None)
            if qml is not None and not qml.abierto():  # (1.7) en QML: el formato y sus duraciones, en pastillas
                vacio_ok = bool(self.plantillas.marcadas)      # (1.8.5) con plantillas, el tráiler puede quedar fuera
                datos = {"formato": max(0, self.seg_formato.actual()), "h": self._versiones(), "v": self._versiones_v(),
                         "versiones": [[k, VERSION_TEXTO[k]] for k in motor.VERSIONES], "vacio_ok": vacio_ok}
                r, res = qml.preguntar(titulo, texto, botones, "info", 0, None, "trailer", datos)
                if r == 0:
                    for pills, quiero in ((self.pills, res.get("h") or []), (self.pills_v, res.get("v") or [])):
                        for k, b in pills.items():
                            b.blockSignals(True)
                            b.setChecked(k in quiero)
                            b.blockSignals(False)
                    f = 1 if res.get("v") and not res.get("h") else 0      # (1.8.5) ya no hay pestañas: lo marcado
                    self.seg_formato.poner(f)
                    self._ver_formato(f)
                    self._cambio_plantillas(vacio_ok=vacio_ok)   # palomitas, texto y la hora en que estara listo
                    try:                                         # (1.8.5) que quede guardado aunque no se arme aun
                        d = motor.leer_estado()
                        d.update({"versiones": self._versiones(), "versiones_vertical": self._versiones_v()})
                        motor.guardar_estado(d)
                    except Exception as ex:
                        registro.info("No se guardo el tráiler elegido: %s" % ex)
                self._sub_material()
                return r
            if not self.caja_videos.styleSheet():   # el popup pone su estilo a todos los botones: aqui, el de la ventana
                self.caja_videos.setStyleSheet(QApplication.instance().styleSheet())
            self.caja_videos.show()
            piezas.sin_recorte(self.seg_formato.botones + self._pastillas())    # cada boton, del ancho de su texto
            try:
                r = piezas.preguntar(self, titulo, texto, botones, "info", 0, contenido=self.caja_videos)
            finally:
                self.caja_videos.setParent(self.dock)            # el popup se borra: las pastillas vuelven aqui
                self.caja_videos.hide()
            self._sub_material()
            return r

        # (19-nov, la persona: «3 botones: tráiler, plantillas y el nombre») los tres de la barra del Inicio
        def _trailer(self):
            """Tráiler: horizontal, vertical o los dos, con sus duraciones (1.8.5: solo ELIGE; se empieza tocando el
            centro o «Empezar»). Dice lo que hay de material y la hora en que estará."""
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            self._sub_material()
            m = self.material
            c = m["cuenta"]
            falta = [_cuantos(n, t) for t, n in dict(m["faltan"]).items() if n]
            hay = [_cuantos(c.get(t, 0), t) for t in ("foto", "video", "dron") if c.get(t)]
            texto = "Falta " + " y ".join(falta) if falta else " · ".join(hay) if hay else "Todavía no hay material"
            if self.l_eta.text():
                texto += "  ·  " + self.l_eta.text().lower()
            texto += "\nMarca horizontal, vertical o los dos. Para empezar, toca el centro o «Empezar»."
            self._elegir_videos("¿Qué tráiler sale?", texto, ("Listo", "Cancelar"))
            self._refrescar_barra()

        def _plantillas_barra(self):
            """(1.8.5, la persona: «en plantillas me debe de cargar las plantillas que tengo en la página Plantillas»)
            Las plantillas de video (Reel, TikTok, CapCut) en pastillas: se marcan las que salen al armar."""
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            infos = list(getattr(self.plantillas, "infos", None) or [])
            if not infos:
                r = self._popup("Todavía no tienes plantillas de video. Agrega un Reel, TikTok o CapCut y sale un "
                                "video más con sus cortes y su música.", ("Agregar plantilla", "Ir a Plantillas",
                                                                          "Cancelar"), "info", titulo="Plantillas")
                if r == 0:
                    self._elegir_plantilla()
                elif r == 1:
                    self._cambiar_pagina(5)
                return
            nombres = [i.get("nombre", "") for i in infos if i.get("nombre")]
            etiquetas = {n: n.title() for n in nombres}
            r, lista = self._elegir_de_videos(
                "¿Qué plantillas salen?", "Cada una sale como un video más, con sus cortes y su música. "
                "Para empezar, toca el centro o «Empezar».", nombres, set(self.plantillas.marcadas), True,
                ("Listo", "Agregar otra", "Cancelar"), etiquetas)
            if r == 0:
                if sorted(lista) != sorted(self.plantillas.marcadas):
                    self.plantillas.elegidas(sorted(lista))
                    self._plantillas_elegidas(sorted(lista))
            elif r == 1:
                self._elegir_plantilla()

        def _refrescar_barra(self):
            """(1.8.5) La barra del Inicio dice lo que va a salir: plantillas elegidas y el tráiler (o nada)."""
            barra = getattr(self, "barra_qml", None)
            if barra is None:
                return
            h, v = self._versiones(), self._versiones_v()
            marcadas = sorted(getattr(self.plantillas, "marcadas", None) or [])
            if not h and not v and not marcadas:
                h = list(motor.VERSIONES)                  # lo mismo que hace _guardar: sin nada, el tráiler
            tr = "Horizontal y vertical" if h and v else "Horizontal" if h else "Vertical" if v else ""
            if h and v:
                pass                                       # «Horizontal y vertical» ya llena el renglon
            elif tr and len(h) + len(v) > 1:
                tr += " · %d videos" % (len(h) + len(v))
            elif tr:
                tr += " · " + VERSION_TEXTO[(h or v)[0]]
            barra.poner_eleccion(marcadas, tr)

        def _editar_nombre(self):
            """El nombre del XV o de los novios (y de qué es el evento). «Evento nuevo» deja el programa en blanco."""
            qml = getattr(self, "popup_qml", None)
            if qml is not None and not qml.abierto():      # (1.7) en QML: el tipo en pastillas y el nombre
                r, res = qml.preguntar("¿De quién es el evento?", "El nombre sale en los títulos del video.",
                                       ("Guardar", "Evento nuevo", "Cancelar"), "info", 0, 2, "nombre",
                                       {"tipos": [t for _, t in TIPOS], "tipo_i": self.c_tipo.currentIndex(),
                                        "nombre": self.e_nombre.text()})
                self._nombre_elegido(r, res.get("tipo_i", self.c_tipo.currentIndex()), res.get("nombre", ""))
                return
            px = piezas.px
            caja = QWidget()
            caja.setStyleSheet(QApplication.instance().styleSheet())    # el popup pone su estilo: aqui, el de la ventana
            v = QVBoxLayout(caja)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(px(26))
            tipos = piezas.Pastillas([t for _, t in TIPOS], self.c_tipo.currentIndex(), nombre="pill_tipo", espacio=10)
            piezas.sin_recorte(tipos.botones)
            v.addWidget(tipos, 0, Qt.AlignHCenter)
            e = QLineEdit(self.e_nombre.text())
            e.setPlaceholderText("Valeria  ·  Ana y Luis")
            v.addWidget(e)
            e.returnPressed.connect(lambda: self.popup_abierto is not None and self.popup_abierto.botones[0].click())
            QTimer.singleShot(250, e.setFocus)
            r = piezas.preguntar(self, "¿De quién es el evento?", "El nombre sale en los títulos del video.",
                                 ("Guardar", "Evento nuevo", "Cancelar"), "info", 0, escape=2, contenido=caja)
            self._nombre_elegido(r, tipos.actual(), e.text())

        def _nombre_elegido(self, r, tipo_i, nombre):
            """Lo que se eligio en el popup del nombre: guardar, evento nuevo o nada."""
            if r == 0:
                self.c_tipo.setCurrentIndex(max(0, int(tipo_i)))
                self.e_nombre.setText((nombre or "").strip())
                try:                                        # que quede guardado aunque no se arme todavia
                    d = motor.leer_estado()
                    d.update({"tipo_evento": self.c_tipo.currentData(), "nombre_xv": self.e_nombre.text().strip()})
                    motor.guardar_estado(d)
                except Exception as ex:
                    registro.info("No se guardo el nombre: %s" % ex)
            elif r == 1:
                self._proyecto_nuevo()

        def _plantillas(self):
            """Plantillas: cada video terminado tiene su proyecto de DaVinci. Se marca uno y se abre, o se sacan de
            nuevo los marcados (sin volver a armar). Junta «Editar en DaVinci» y «Renderizar lo editado»."""
            if self.trabajo is not None:
                self._avisar("Espera a que termine: después podrás editar sus plantillas.", "warn")
                return
            est = motor.leer_estado()
            # (19-nov, la persona: «debe de tirarme las plantillas que ya hay») las de TODOS los eventos terminados,
            # primero el de ahora; antes, sin el evento actual terminado, decia «Todavía no hay plantillas»
            grupos = motor.eventos_con_plantillas()
            if not grupos:
                evento = est.get("evento")
                if evento and est.get("timelines") and motor.evento_terminado():    # de antes: una sola linea
                    r = self._popup("Abre la línea de «%s» en DaVinci para retocarla, o saca de nuevo los videos con "
                                    "lo que cambiaste." % evento, ("Abrir en DaVinci", "Renderizar lo editado",
                                                                  "Cancelar"), "pregunta", titulo="Plantillas")
                    if r == 0:
                        self._editar_en_davinci()
                    elif r == 1:
                        self._renderizar_editado()
                    return
                self._popup("Todavía no hay plantillas. Pulsa «Tráiler»: al terminar, cada video queda con su propia "
                            "plantilla para retocarlo en DaVinci.", ("Entendido",), "info", titulo="Plantillas")
                return
            varios = len(grupos) > 1
            claves, etiquetas = [], {}
            for ev, vids in grupos:
                for v in vids:
                    k = "%s|%s" % (ev, v)
                    claves.append(k)
                    corto = self._etiqueta_video(v)
                    etiquetas[k] = "%s · %s" % (ev, corto) if varios else corto
            ev0 = grupos[0][0]
            abiertos = ["%s|%s" % (est.get("editando_evento"), v) for v in est.get("editando") or []]
            abiertos = [k for k in abiertos if k in etiquetas]
            r, elegidos = self._elegir_de_videos(
                "Plantillas" if varios else "Plantillas de %s" % ev0,
                "Abre un video en DaVinci para retocarlo: solo su proyecto, con su línea en Edición. «Renderizar» saca "
                "de nuevo los marcados, sin volver a armar.",
                claves, abiertos[-1:] or claves[:1], True, ("Abrir en DaVinci", "Renderizar", "Cancelar"), etiquetas)
            if not elegidos or r not in (0, 1):
                return
            evento = elegidos[0].split("|", 1)[0]
            del_evento = [k.split("|", 1)[1] for k in elegidos if k.split("|", 1)[0] == evento]
            if r == 0:
                self._editar_en_davinci(del_evento[0], evento)
            else:
                if len(del_evento) < len(elegidos):
                    self._avisar("Se renderiza un evento a la vez: ahora los de «%s»." % evento, "warn")
                self._renderizar_editado(del_evento, evento)

        @staticmethod
        def _etiqueta_video(v):
            """«VIDEO FINAL HORIZONTAL 1 MIN» -> «1 min»; «PLANTILLA 1 VERTICAL - 2026-11-08» -> «Plantilla 1»."""
            txt = re.sub(r" - \d{4}-\d\d-\d\d$", "", v.upper()).replace("VIDEO FINAL ", "").replace("HORIZONTAL ", "")
            txt = txt.replace(" MIN", " min")
            if txt.startswith("PLANTILLA"):
                txt = txt.replace(" VERTICAL", "")
            return txt[:1] + txt[1:].lower() if not txt[:1].isdigit() else txt

        def _ver_formato(self, i):
            """El selector Horizontal | Vertical muestra las duraciones de ese formato (las dos se guardan)."""
            for b in self.pills.values():
                b.setVisible(i == 0)
            for b in self.pills_v.values():
                b.setVisible(i == 1)

        def _tarjeta_carpeta(self, tipo, titulo, ayuda):
            """(1.6.0) Tarjeta de Fotos / Videos / Dron: el numero grande y tres miniaturas encimadas. Un clic agrega."""
            px = piezas.px
            t = QFrame(objectName="stat")
            t.setToolTip(ayuda + "\n\nClic: agregar " + titulo.lower())
            t.setCursor(Qt.PointingHandCursor)
            g = QHBoxLayout(t)
            g.setContentsMargins(px(44), px(24), px(26), px(22))
            g.setSpacing(px(10))
            col = QVBoxLayout()
            col.setSpacing(0)
            cab = QHBoxLayout()
            cab.setSpacing(px(22))
            ic = QLabel()
            ic.setPixmap(piezas.icono("pelicula" if tipo == "video" else tipo, piezas.ORO, px(52)))   # dorados
            cab.addWidget(ic)
            et = QLabel(titulo, objectName="stat_t")
            cab.addWidget(et)
            cab.addStretch(1)
            col.addLayout(cab)
            n = QLabel("0", objectName="stat_n")
            col.addWidget(n)
            e = QLabel("", objectName="estado_c")
            col.addWidget(e)
            col.addStretch(1)
            g.addLayout(col, 1)
            pila = piezas.Pila()
            g.addWidget(pila, 0, Qt.AlignVCenter)
            t.mousePressEvent = lambda ev, tp=tipo: self._agregar(tp) if ev.button() == Qt.LeftButton else None
            self.tarjetas[tipo] = (t, n, e)
            self.pilas[tipo] = pila
            return t

        def _agregar_carpeta(self):
            """(1.6.0) «Agregar carpeta»: como soltarla en la ventana (se usa donde está, sin copiarla)."""
            d = QFileDialog.getExistingDirectory(self, "Agregar la carpeta del evento", os.path.expanduser("~"))
            if d:
                self._recibir([d])

        def _minis_plan(self, pedidos):
            import miniaturas

            def listo(res, error):
                if error is None and res:
                    self.plan_v.poner_minis({r: QPixmap(j) for r, j in res.items()})
            for k in range(0, len(pedidos), 24):         # por tandas: las primeras se ven enseguida
                tanda = pedidos[k:k + 24]
                qt_kit.correr_en_hilo(self, lambda t=tanda: miniaturas.varias(t), listo, baja=True)

        def _cargar_plan(self):
            """«Qué entra al video»: el plan de cada version y lo que queda fuera (receta.plan_ventana), en un hilo."""
            import analizar_material as am

            def calcular():
                import json
                import importlib.util
                with open(am._cache_ruta(), encoding="utf-8") as f:
                    j = json.load(f)
                spec = importlib.util.spec_from_file_location("receta", rutas.codigo("receta.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.plan_ventana({"items": j.get("items") or [], "fecha": j.get("fecha")},
                                        motor.leer_estado().get("tipo_evento", "xv"))

            def listo(res, error):
                if error is not None or not res:
                    if error is not None:
                        registro.error("Qué entra al video: %s" % error)
                    return
                hay = {c for c, _ in res.get("versiones") or []}
                # (19-nov) las pestañas de reserva toman el nombre de cada plantilla elegida
                fijas = 6
                plantillas = [(c, t) for c, t in res.get("versiones") or [] if c.startswith("PLANTILLA") or
                              c not in {x for x, _ in self.VERS_PLAN[:fijas]}]
                for k in range(fijas, len(self.VERS_PLAN)):
                    par = plantillas[k - fijas] if k - fijas < len(plantillas) else ("__plantilla%d" % (k - fijas), "")
                    self.VERS_PLAN[k] = par
                    self.seg_plan.botones[k].setText(par[1])
                if res.get("error_plantillas"):
                    registro.error("Qué entra al video (plantillas): %s" % res["error_plantillas"])
                for (clave, _t), b in zip(self.VERS_PLAN, self.seg_plan.botones):
                    b.setVisible(clave in hay)
                self.plan_v.editable = self.trabajo is None
                self.plan_v.poner(res)
                actual = next((n for n, (c, _) in enumerate(self.VERS_PLAN) if c == self.plan_v.clave), 0)
                self.seg_plan.poner(actual)
            qt_kit.correr_en_hilo(self, calcular, listo, baja=True)

        def _toma_decidida(self, nombre, que):
            """La persona quito una toma del video o pidio usar una descartada: al estado, y el plan se rehace."""
            est = motor.leer_estado()
            no = [n for n in est.get("tomas_no") or [] if n != nombre]
            si = [n for n in est.get("tomas_si") or [] if n != nombre]
            if que == "no":
                no.append(nombre)
            elif que == "si":
                si.append(nombre)
            est["tomas_no"], est["tomas_si"] = no, si
            self.est["tomas_no"], self.est["tomas_si"] = no, si
            motor.guardar_estado(est)
            self._avisar({"no": "Listo: «%s» no entra al video.", "si": "Listo: «%s» se usa de todos modos.",
                          "auto": "Listo: «%s» vuelve a lo que decidió el programa."}[que] % nombre)
            self._cargar_plan()

        def _tarjeta_plantillas(self):
            """Material > «Plantillas de video» (la persona, 18-nov: «crea una sección para escoger qué plantilla quiero
            usar en la página de Material»)."""
            import plantillas_ui
            px = piezas.px                 # (19-nov) sin esto la 1.6.19 se caia al abrir (NameError en Material)
            tarjeta = QFrame(objectName="vidrio")
            lay = QVBoxLayout(tarjeta)
            lay.setContentsMargins(px(24), px(26), px(24), px(26))
            lay.setSpacing(px(14))
            fila = QHBoxLayout()
            fila.setContentsMargins(px(14), 0, px(14), 0)
            fila.setSpacing(px(26))
            ic = QLabel()
            ic.setPixmap(piezas.icono("pelicula", piezas.ORO, px(54)))
            fila.addWidget(ic)
            fila.addWidget(QLabel("Plantillas de video", objectName="titulo_card"))
            self.l_plantillas = QLabel("Opcional: cada una sale como un video más, con sus cortes y su música.")
            self.l_plantillas.setStyleSheet("color:%s;" % TENUE)
            self.l_plantillas.setWordWrap(True)       # que no empuje los botones fuera de la ventana
            self.l_plantillas.setMinimumWidth(0)
            fila.addWidget(self.l_plantillas, 1)
            b = QPushButton("  Agregar plantilla", objectName="borde")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("Un video (Reel, TikTok, CapCut) se convierte en plantilla: se detectan sus cortes y se usa su "
                         "música. También puedes soltar el video sobre las tarjetas.")
            b.clicked.connect(self._elegir_plantilla)
            fila.addWidget(b)
            # (19-nov, la persona: «que no tenga tantas cosas que abrumen») cerrada hasta que se pide
            self.b_ver_pl = QPushButton("Ver plantillas", objectName="borde")
            self.b_ver_pl.setCursor(Qt.PointingHandCursor)
            self.b_ver_pl.clicked.connect(lambda: self._ver_plantillas(not self.cuerpo_pl.isVisible()))
            fila.addWidget(self.b_ver_pl)
            lay.addLayout(fila)
            self.cuerpo_pl = QWidget()
            lay_pl = QVBoxLayout(self.cuerpo_pl)
            lay_pl.setContentsMargins(0, 0, 0, 0)
            lay_pl.setSpacing(px(14))
            lay.addWidget(self.cuerpo_pl)
            # (19-nov, la persona: «deja opción de omitir texto para las plantillas»; «deja la opción para quitar
            # barridos de luz o transiciones: lo importante es que repliques tal cual la plantilla») lo extra, a elegir
            opciones = QHBoxLayout()
            opciones.setContentsMargins(px(14), 0, px(14), 0)
            opciones.setSpacing(px(18))
            self.ch_pl = {}
            for clave, txt, tip in (
                    ("plantillas_texto", "Título con los nombres",
                     "Al inicio de cada plantilla, los nombres en letra elegante (donde no tapen caras)."),
                    ("plantillas_destellos", "Destellos de luz",
                     "Donde la plantilla original tiene un destello blanco, uno suave. Apagado: corte seco."),
                    ("plantillas_fundidos", "Transiciones",
                     "Donde la plantilla original funde de una toma a otra, un fundido. Apagado: corte seco.")):
                l_op = QLabel(txt, objectName="fila_aj")
                ch = piezas.Interruptor("")
                ch.setChecked(self.est.get(clave, True) is not False)
                l_op.setToolTip(tip)
                ch.setToolTip(tip)
                ch.toggled.connect(lambda si, c=clave, n=txt: self._plantillas_opcion(c, n, si))
                self.ch_pl[clave] = ch
                opciones.addWidget(l_op)
                opciones.addWidget(ch)
                opciones.addSpacing(px(22))
            opciones.addStretch(1)
            nota = QLabel("Todo apagado: la plantilla tal cual, con sus cortes y su música.")
            nota.setStyleSheet("color:%s;" % TENUE)
            opciones.addWidget(nota)
            lay_pl.addLayout(opciones)
            self.plantillas = plantillas_ui.PlantillasRef()
            self.plantillas.cambio.connect(self._plantillas_elegidas)
            self.plantillas.soltado.connect(self._importar_plantillas)
            lay_pl.addWidget(self.plantillas)
            self.cuerpo_pl.setVisible(bool(self.est.get("plantillas_ref")))    # abierta solo si ya hay elegidas
            self.b_ver_pl.setText("Ocultar" if self.cuerpo_pl.isVisibleTo(tarjeta) else "Ver plantillas")
            QTimer.singleShot(0, self._cargar_plantillas)
            return tarjeta

        def _ver_plantillas(self, ver):
            import animacion
            self.cuerpo_pl.setVisible(ver)
            self.b_ver_pl.setText("Ocultar" if ver else "Ver plantillas")
            if ver:
                animacion.aparecer(self.cuerpo_pl)

        def _cargar_plantillas(self):
            def leer():
                import plantilla_ref
                return plantilla_ref.lista()

            def listo(res, error):
                if error is None:
                    self.plantillas.poner(res or [])
                    # (1.8.5, la persona: «son 4 plantillas que deben estar seleccionadas por default») mientras la
                    # persona no elija, TODAS marcadas (y guardadas: el motor las lee del estado)
                    elegidas = self.est.get("plantillas_ref") or []
                    try:
                        est = motor.leer_estado()
                        if not est.get("plantillas_ref_persona"):
                            elegidas = [i.get("nombre") for i in res or [] if i.get("nombre")]
                            if sorted(est.get("plantillas_ref") or []) != sorted(elegidas):
                                est["plantillas_ref"] = list(elegidas)
                                motor.guardar_estado(est)
                            self.est["plantillas_ref"] = list(elegidas)
                    except Exception as ex:
                        registro.info("Plantillas por defecto: %s" % ex)
                    self.plantillas.elegidas(elegidas)
                    self._refrescar_barra()
            qt_kit.correr_en_hilo(self, leer, listo, baja=True)

        def _plantillas_elegidas(self, nombres):
            est = motor.leer_estado()
            est["plantillas_ref"] = self.est["plantillas_ref"] = list(nombres)
            est["plantillas_ref_persona"] = True          # (1.8.5) ya eligio: no se vuelven a marcar todas
            motor.guardar_estado(est)
            self._avisar("Listo: al armar también sale %s." % ", ".join(n.title() for n in nombres) if nombres
                         else "Listo: sin plantillas de video.")
            self._refrescar_barra()
            self._cargar_plan()                     # su pestaña en «Qué entra al video», con sus huecos

        def _plantillas_opcion(self, clave, nombre, si):
            est = motor.leer_estado()
            est[clave] = self.est[clave] = bool(si)
            motor.guardar_estado(est)
            self._avisar("Listo: plantillas %s «%s»." % ("con" if si else "sin", nombre.lower()))

        def _elegir_plantilla(self):
            archivos, _ = QFileDialog.getOpenFileNames(self, "Videos para convertir en plantilla", os.path.expanduser("~"),
                                                       "Videos (*.mov *.mp4 *.m4v *.mkv *.avi *.webm)")
            if archivos:
                self._importar_plantillas(archivos)

        def _importar_plantillas(self, archivos):
            """Convierte los videos en plantillas (cortes, musica y portada) en un hilo."""
            self._avisar("Convirtiendo %d video%s en plantilla..." % (len(archivos), "" if len(archivos) == 1 else "s"))

            def hacer():
                import plantilla_ref
                return [plantilla_ref.importar(a, log=registro.info)["nombre"] for a in archivos]

            def listo(res, error):
                if error is not None:
                    self._avisar("No se pudo convertir en plantilla: %s" % error, "warn")
                    return
                self._avisar("Lista%s: %s." % ("" if len(res) == 1 else "s", ", ".join(n.title() for n in res)))
                try:                                   # (1.8.5) la que se agrega sale marcada
                    est = motor.leer_estado()
                    est["plantillas_ref"] = sorted(set(est.get("plantillas_ref") or []) | set(res))
                    self.est["plantillas_ref"] = est["plantillas_ref"]
                    motor.guardar_estado(est)
                except Exception as ex:
                    registro.info("No se marco la plantilla nueva: %s" % ex)
                self._cargar_plantillas()
            qt_kit.correr_en_hilo(self, hacer, listo, baja=True)

        def _tomas_cambiadas(self):
            """El slider «Cuántas tomas»: al estado (build_trailers.factor_planos) y el plan se rehace."""
            est = motor.leer_estado()
            est["tomas_ritmo"] = self.est["tomas_ritmo"] = int(self.s_tomas.value())
            motor.guardar_estado(est)
            self._cargar_plan()

        def _plan_reordenado(self, clave, ids):
            """La persona arrastro una toma a otro lugar (o pidio el orden del programa): al estado y el plan se rehace."""
            est = motor.leer_estado()
            orden = dict(est.get("orden_planos") or {})
            if ids:
                orden[clave] = ids
            else:
                orden.pop(clave, None)
            est["orden_planos"] = self.est["orden_planos"] = orden
            motor.guardar_estado(est)
            self._avisar("Listo: el %s va en el orden que pusiste." % clave.replace("V ", "vertical ").replace("min", " min")
                         if ids else "Listo: vuelve al orden del programa.")
            self._cargar_plan()

        def _traer_minis(self, pedidos):
            """Miniaturas de la Línea del día, en un hilo (miniaturas.py); se pintan a medida que llegan."""
            import miniaturas

            def listo(res, error):
                if error is None and res:
                    self.linea.poner_minis({r: QPixmap(j) for r, j in res.items()})
            qt_kit.correr_en_hilo(self, lambda: miniaturas.varias(pedidos), listo, baja=True)

        def _minis_pila(self, tipo, items):
            import miniaturas
            pedidos = [(i["ruta"], i["tipo"], None) for i in items]

            def listo(res, error):
                if error is None and res:
                    self.pilas[tipo].poner([QPixmap(res[r]) for r, _, _ in pedidos if r in res])
            qt_kit.correr_en_hilo(self, lambda: miniaturas.varias(pedidos), listo, baja=True)

        def _foto_vista(self, items):
            """La mejor foto de la persona festejada (o la mas nitida) de fondo en la vista previa de Textos."""
            fotos = [i for i in items if i["tipo"] == "foto" and i.get("ruta") and not i.get("descartar")]
            if not fotos:
                return

            def puntaje(i):
                ia = i.get("ia") or {}
                et = set(ia.get("etiquetas") or [])
                return (2 if et & {"festejada", "novia", "novios"} else 0) + (1 if i.get("prota") else 0) + \
                    (0 if ia.get("util") is False else 1), -abs(hash(i["nombre"])) % 7
            ruta = max(fotos, key=puntaje)["ruta"]

            def leer():
                r = QImageReader(ruta)
                r.setAutoTransform(True)                 # la orientacion EXIF del celular
                tam = r.size()
                if tam.isValid() and tam.width() > 1600:
                    r.setScaledSize(tam.scaled(1600, 1600, Qt.KeepAspectRatio))
                return r.read()

            def listo(img, error):
                if error is None and img is not None and not img.isNull():
                    self.vista.poner_fondo(QPixmap.fromImage(img))
            qt_kit.correr_en_hilo(self, leer, listo, baja=True)

        def _pagina_material(self):
            import linea_dia
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(piezas.px(18), piezas.px(14), piezas.px(18), piezas.px(10))
            v.setSpacing(piezas.px(30))
            cab = QHBoxLayout()
            cab.setSpacing(piezas.px(12))
            px = piezas.px
            raya = QFrame()
            raya.setFixedSize(px(8), px(58))
            raya.setStyleSheet("background: #E2B04F; border-radius: 2px;")
            cab.addWidget(raya)
            cab.addSpacing(px(14))
            tit = QLabel("Material del evento", objectName="titulo_pag")
            cab.addWidget(tit)
            cab.addStretch(1)
            self.l_copia = QLabel("")
            self.l_copia.setWordWrap(False)
            self.l_copia.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.l_copia.setStyleSheet("color:%s;" % TENUE)
            cab.addWidget(self.l_copia)
            self.b_agregar = QPushButton("  Agregar carpeta", objectName="boton_verde")     # aire entre icono y texto
            self.b_agregar.setIcon(piezas.qicono("carpeta", "#FFFFFF", px(46)))
            self.b_agregar.setIconSize(QSize(px(46), px(46)))
            self.b_agregar.setCursor(Qt.PointingHandCursor)
            self.b_agregar.setToolTip("Elige la carpeta del evento: se usa donde está (no se copia). "
                                      "También puedes arrastrarla a la ventana.")
            self.b_agregar.clicked.connect(self._agregar_carpeta)
            cab.addWidget(self.b_agregar)
            v.addLayout(cab)
            fila = QHBoxLayout()
            fila.setSpacing(piezas.px(30))
            self.tarjetas, self.pilas = {}, {}
            fila.addWidget(self._tarjeta_carpeta("foto", "Fotos", "Se usan 8 para los destellos de la intro: "
                                                 "pon al menos 8 (mejor muchas: el programa elige las más nítidas "
                                                 "y no repite fotos de una ráfaga)."))
            fila.addWidget(self._tarjeta_carpeta("video", "Videos", "Videos de cámara y celular de todo el evento: "
                                                 "maquillaje, iglesia y fiesta."))
            fila.addWidget(self._tarjeta_carpeta("dron", "Dron", "Tomas aéreas (opcional). Abren el tráiler "
                                                 "y las versiones largas."))
            v.addLayout(fila)
            # lo que ya se hizo con el material: medido, visto por la IA, escuchado por el oido
            fila_e = QHBoxLayout()
            fila_e.setSpacing(8)
            self.chips_estado = {}
            fila_e.setSpacing(px(24))
            for clave in ("medido", "ia", "oido"):
                ch = piezas.Chip("", "check_lleno", "#22C47E", nombre="chip_ok", lado=36)
                ch.setCursor(Qt.ArrowCursor)
                ch.setProperty("tipo", "ok")
                ch.hide()
                fila_e.addWidget(ch)
                self.chips_estado[clave] = ch
            fila_e.addStretch(1)
            self.b_analizar = QPushButton("Analizar ahora", objectName="borde")
            self.b_analizar.setCursor(Qt.PointingHandCursor)
            self.b_analizar.setToolTip("Revisa hora, nitidez, luz, color y audio de cada archivo y los ordena por "
                                       "momento. Lo ya analizado no se repite: después el botón de Inicio va directo.")
            self.b_analizar.clicked.connect(self._analizar_ahora)
            fila_e.addWidget(self.b_analizar)
            v.addLayout(fila_e)
            # (19-nov) las plantillas de referencia tienen su pagina (_pagina_plantillas)
            # --- la linea del dia (el analisis)
            org = QFrame(objectName="vidrio")
            go = QVBoxLayout(org)
            go.setContentsMargins(px(24), px(26), px(24), px(26))
            go.setSpacing(px(14))
            fila_t = QHBoxLayout()
            fila_t.setContentsMargins(px(14), 0, px(14), 0)
            fila_t.setSpacing(px(26))
            ic = QLabel()
            ic.setPixmap(piezas.icono("pelicula", piezas.ORO, px(54)))
            fila_t.addWidget(ic)
            t2 = QLabel("Qué entra al video", objectName="titulo_card")
            fila_t.addWidget(t2)
            self.l_org = QLabel("")
            self.l_org.setStyleSheet("color:%s;" % TENUE)
            self.l_org.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fila_t.addWidget(self.l_org, 1)
            go.addLayout(fila_t)
            self.linea = linea_dia.LineaDia()
            self.linea.limites_cambiados.connect(self._limites_cambiados)
            self.linea.cuentas_vivas.connect(self._pintar_cuentas)
            self.linea.pide_minis.connect(self._traer_minis)
            self.linea.toma_movida.connect(self._toma_movida)
            # (18-nov, la persona: «línea del día no entiendo qué hace... rediseña para que sea algo útil de verdad»; eligio
            # la propuesta A) en su lugar, «Qué entra al video»: el plan de la version elegida plano por plano y lo que
            # queda fuera con su motivo (plan_video.py). La linea sigue existiendo, sin verse (lo que la usa no cambia).
            self.linea.hide()
            import plan_video
            self.VERS_PLAN = [("1min", "1 min"), ("3min", "3 min"), ("15min", "15 min"), ("30min", "30 min"),
                              ("V 1min", "Vertical 1 min"), ("V 3min", "Vertical 3 min")]
            # (19-nov) + una pestaña por plantilla de video elegida (sus huecos, uno por corte): se nombran al cargar
            self.VERS_PLAN += [("__plantilla%d" % k, "Plantilla") for k in range(6)]
            self.seg_plan = piezas.Pastillas([t for _, t in self.VERS_PLAN], 0, nombre="pill_tipo", espacio=10)
            for b in self.seg_plan.botones[4:]:     # (19-nov) verticales y plantillas: solo cuando el plan las trae
                b.hide()                            # (las 12 a la vez ensanchaban la pagina mas que la ventana)
            fila_p = QHBoxLayout()
            fila_p.setContentsMargins(px(14), 0, px(14), 0)
            fila_p.addWidget(self.seg_plan)
            fila_p.addStretch(1)
            # (18-nov, la persona: «que exista un slider para decir cuántas tomas, ya que hay muchas tomas y estresa»)
            # pocas = planos mas largos; el plan se rehace al soltar (build_trailers.factor_planos)
            fila_p.addWidget(QLabel("Cuántas tomas", objectName="fila_aj"))
            fila_p.addSpacing(px(14))
            fila_p.addWidget(QLabel("Pocas", objectName="nota_t"))
            self.s_tomas = QSlider(Qt.Horizontal)
            self.s_tomas.setRange(0, 100)
            self.s_tomas.setValue(int(self.est.get("tomas_ritmo", 50)))
            self.s_tomas.setMinimumWidth(px(220))
            self.s_tomas.setToolTip("Pocas: planos más largos y tranquilos. Muchas: más cortes. Los cortes siguen el "
                                    "ritmo de la música. El plan de arriba se rehace al soltar.")
            self._t_tomas = QTimer(self, singleShot=True, interval=350)
            self._t_tomas.timeout.connect(self._tomas_cambiadas)
            self.s_tomas.valueChanged.connect(lambda _v: self._t_tomas.start())
            fila_p.addWidget(self.s_tomas)
            fila_p.addWidget(QLabel("Muchas", objectName="nota_t"))
            go.addLayout(fila_p)
            self.plan_v = plan_video.PlanVideo()
            self.seg_plan.cambio.connect(lambda i: self.plan_v.elegir(self.VERS_PLAN[i][0]))
            self.plan_v.pide_minis.connect(self._minis_plan)
            self.plan_v.decidida.connect(self._toma_decidida)
            self.plan_v.reordenada.connect(self._plan_reordenado)
            go.addWidget(self.plan_v, 1)
            self.l_momentos = {}
            self.l_avisos = QLabel("")
            self.l_avisos.setWordWrap(True)
            self.l_avisos.setTextFormat(Qt.RichText)
            self.l_avisos.setStyleSheet("color:%s; font-size: 12px;" % AMBAR)
            go.addWidget(self.l_avisos)
            fila_a = QHBoxLayout()
            fila_a.setContentsMargins(px(14), 0, px(14), 0)
            fila_a.setSpacing(px(20))
            ic2 = QLabel()
            ic2.setPixmap(piezas.icono("info", "#AFC0C4", px(40)))
            fila_a.addWidget(ic2)
            ayuda = QLabel("Clic en una toma para quitarla del video o para usarla de todos modos", objectName="ayuda_t")
            ayuda.setToolTip("Lo que decidas a mano se respeta en el próximo armado. Las fotos de la intro las elige "
                             "el programa.")
            fila_a.addWidget(ayuda, 1)
            go.addLayout(fila_a)
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
                self.l_org.setText("todavía sin analizar")
                self.b_analizar.setText("Analizar ahora")
                self.b_analizar.show()
                for ch in self.chips_estado.values():
                    ch.hide()
                self.l_avisos.setText(nota_raros)
                return
            # (1.6.0) los chips de lo hecho, las miniaturas de las tarjetas y la foto de la vista previa
            videos = [i for i in items if i["tipo"] != "foto"]
            con_ia = sum(1 for i in videos if (i.get("ia") or {}).get("escena") or (i.get("ia") or {}).get("instantes"))
            con_audio = [i for i in videos if i.get("audio_pista", True) is not False]
            con_oido = sum(1 for i in con_audio if (i.get("oido") or {}).get("paso"))
            chs = self.chips_estado
            chs["medido"].setText("Medido" if al_dia else "Hay material nuevo")
            repulir(chs["medido"], tipo="ok" if al_dia else "falta")
            chs["ia"].setText("IA %d/%d" % (con_ia, len(videos)))
            chs["oido"].setText("Oído %d/%d" % (con_oido, len(con_audio)))
            for clave, ch in chs.items():
                ch.setVisible(clave != "oido" or con_oido > 0)
            self.b_analizar.setVisible(not al_dia)
            for tipo in ("foto", "video", "dron"):
                cand = [i for i in items if i["tipo"] == tipo and i.get("ruta")]
                if cand:
                    self._minis_pila(tipo, [cand[int(len(cand) * f)] for f in (0.15, 0.5, 0.85)] if len(cand) > 3
                                     else cand)
            self._foto_vista(items)
            self._cargar_plan()
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
            self.l_org.setText("%s  ·  %d archivos  ·  %d cámara%s" % (
                fecha, len(items), len(camaras), "" if len(camaras) == 1 else "s"))
            self.b_analizar.setText("Analizar lo nuevo")
            self._fecha_material = res.get("fecha")
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
            self.l_avisos.setText("<br>".join(a.replace("&", "&amp;").replace("<", "&lt;") for a in av[:6]))

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

        def _toma_movida(self, nombre, momento):
            """(1.6.0) En la Linea del dia se arrastro una toma a otro carril: queda como excepcion a mano
            (CLASIFICACION «archivos») y se reordena (rapido: no se vuelve a medir)."""
            import analizar_material as am
            import linea_dia
            self.linea.editable = False

            def correr():
                am.guardar_excepcion(nombre, momento)
                return am.reclasificar(rutas.BASE, log=registro.info)

            def listo(res, error):
                if error is not None:
                    self._avisar("No pude mover la toma: %s" % error, "error")
                else:
                    self._avisar("Listo: «%s» va ahora en %s. Se usa en el próximo armado." % (
                        nombre, linea_dia.NOMBRE.get(momento, momento)))
                self._cargar_organizacion()
            qt_kit.correr_en_hilo(self, correr, listo)

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
            # (1.6.0, el diseño de Higgsfield) a la izquierda el formulario; a la derecha la vista previa en vivo
            px = piezas.px
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(px(0), px(40), px(4), px(20))
            cuerpo = QHBoxLayout()
            cuerpo.setSpacing(px(24))
            caja = QFrame(objectName="vidrio")
            g = QVBoxLayout(caja)
            g.setContentsMargins(px(26), px(62), px(36), px(40))
            g.setSpacing(px(22))
            self.c_tipo = QComboBox(caja)            # el valor (lo leen motor y el estado); se elige con self.seg_tipo
            for clave, texto in TIPOS:
                self.c_tipo.addItem(texto, clave)
            actual = next((k for k, (c, _) in enumerate(TIPOS) if c == self.est.get("tipo_evento", "xv")), 0)
            self.c_tipo.setCurrentIndex(actual)
            self.c_tipo.hide()
            l_tipo = QLabel("Tipo de evento", objectName="etq_campo")
            l_tipo.setContentsMargins(px(26), 0, 0, 0)
            l_tipo.setToolTip("Los capítulos, frases y el «gracias» cambian solos según el tipo de evento.")
            g.addWidget(l_tipo)
            self.seg_tipo = piezas.Pastillas([t for _, t in TIPOS], actual, nombre="pill_tipo", espacio=10)
            self.seg_tipo.cambio.connect(self.c_tipo.setCurrentIndex)
            g.addWidget(self.seg_tipo)
            g.addSpacing(px(70))
            self.e_nombre = QLineEdit(self.est.get("nombre_xv", ""))
            self.e_nombre.setPlaceholderText("Valeria  ·  K & R")
            self.e_frase = QLineEdit(self.est.get("frase", ""))
            self.e_frase.setPlaceholderText("Vacío = la del tipo de evento")
            self.e_fecha = QLineEdit(self.est.get("fecha_lugar", ""))
            self.e_fecha.setPlaceholderText("Vacío = la fecha del material")
            for etq, wid in (("Nombres", self.e_nombre), ("Frase bajo el nombre", self.e_frase),
                             ("Tarjeta final", self.e_fecha)):
                l = QLabel(etq, objectName="etq_campo")
                l.setContentsMargins(px(22), 0, 0, 0)
                g.addWidget(l)
                wid.setContentsMargins(px(14), 0, 0, 0)
                g.addWidget(wid)
                g.addSpacing(px(50))
            g.addStretch(1)
            cuerpo.addWidget(caja, 33)
            caja2 = QFrame(objectName="vidrio")
            g2 = QVBoxLayout(caja2)
            g2.setContentsMargins(px(10), px(20), px(10), px(30))
            g2.setSpacing(px(36))
            self.vista = piezas.VistaTitulo(rutas.FUENTES)
            fondo = os.path.join(rutas.RECURSOS, "fondo_titulo.jpg")      # (Higgsfield) hasta que haya fotos del evento
            if os.path.isfile(fondo):
                self.vista.poner_fondo(QPixmap(fondo))
            g2.addWidget(self.vista)
            self.seg_vista = piezas.Pastillas(["Título", "Capítulo", "Gracias", "Tarjeta final"], 0,
                                              nombre="pill_vista", espacio=16, estirar=True)
            self.seg_vista.cambio.connect(self._pintar_vista)
            fila_s = QHBoxLayout()
            fila_s.setContentsMargins(px(20), 0, px(20), 0)     # (18-nov) con 105 la pagina no cabia y salia cortada
            fila_s.addWidget(self.seg_vista, 1)
            g2.addLayout(fila_s)
            pie = QLabel("Vista previa en vivo", objectName="nota_t")
            pie.setAlignment(Qt.AlignCenter)
            g2.addWidget(pie)
            g2.addStretch(1)
            cuerpo.addWidget(caja2, 67)
            v.addLayout(cuerpo)
            v.addStretch(1)
            for wid in (self.e_nombre, self.e_frase, self.e_fecha):
                wid.textChanged.connect(self._pintar_evento)
                wid.textChanged.connect(self._pintar_vista)
            self.c_tipo.currentIndexChanged.connect(self._pintar_evento)
            self.c_tipo.currentIndexChanged.connect(self._pintar_vista)
            self.c_tipo.currentIndexChanged.connect(self.seg_tipo.poner)   # si otro lado cambia el tipo
            self._pintar_vista()
            return w

        def _pintar_vista(self, *_):
            """La vista previa del titulo con lo escrito (o lo que el tipo de evento pone solo)."""
            if not hasattr(self, "vista"):
                return
            if not hasattr(self, "_perfiles"):
                try:
                    self._perfiles = motor.cargar_perfiles()
                except Exception:
                    self._perfiles = {}
            perfil = self._perfiles.get(self.c_tipo.currentData() or "xv") or {}
            caps = perfil.get("capitulos") or {}          # {MOMENTO: ["Los preparativos", "Capítulo I"], ...}
            primero = next(iter(caps.values()), []) if isinstance(caps, dict) else caps
            if isinstance(primero, (list, tuple)):
                cap, cap_n = (list(primero) + ["", ""])[:2]
            else:
                cap, cap_n = str(primero or ""), ""
            cap, cap_n = str(cap or "Los preparativos"), str(cap_n or "Capítulo I")
            fecha = self.e_fecha.text().strip()
            if not fecha and getattr(self, "_fecha_material", None):
                f = str(self._fecha_material)
                fecha = "%s · %s · %s" % (f[8:10], f[5:7], f[:4]) if len(f) >= 10 else f
            self.vista.poner(["titulo", "capitulo", "gracias", "final"][max(0, self.seg_vista.actual())],
                             nombre=self.e_nombre.text().strip() or "Valeria",
                             frase=self.e_frase.text().strip() or perfil.get("titulo") or "",
                             capitulo=cap, capitulo_n=cap_n,
                             gracias=perfil.get("gracias") or "", fecha=fecha)

        def _pintar_ruido_dv(self, info=None):
            info = info if info is not None else motor.estado_ruido_davinci()
            if info.get("hay"):
                vio = ", ".join(info.get("de_ruido") or [])
                self.l_ruido_dv.setText("Ruido de DaVinci: el del clip «%s»" % info.get("clip", "?"))
                self.l_ruido_dv.setToolTip("Guardado el %s del clip «%s»%s. Se aplica a todas las tomas al armar." % (
                    info.get("fecha", "?"), info.get("clip", "?"),
                    " (%s)" % vio if vio else " (ojo: en ese clip no vi reducción de ruido)"))
            else:
                self.l_ruido_dv.setText("Ruido de DaVinci: el del programa")
                self.l_ruido_dv.setToolTip("Sin guardar: las tomas usan el filtro del programa. Para usar el de "
                                           "DaVinci, déjalo a tu gusto en un clip (página Color) y guárdalo aquí.")
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

        def _estilos_musica(self):
            """Las carpetas de estilo de la musica original («1 CINE LATINO»...), o [] si el programa no la trae."""
            d = os.path.join(rutas.RECURSOS, "musica")
            try:
                return sorted(n for n in os.listdir(d) if n[:1].isdigit() and os.path.isdir(os.path.join(d, n)))
            except OSError:
                return []

        def _estilo_musica(self):
            """Lo elegido en Ajustes > Sonido > Música: el nombre del estilo o «PLANTILLA»."""
            seg = getattr(self, "seg_musica", None)
            if seg is None:
                return self.est.get("musica_estilo", "")
            i = seg.actual() - 1                 # 0 = Auto (el del tipo de evento); el ultimo = Plantilla
            if i < 0:
                return "AUTO"
            return self.estilos_musica[i].lstrip("0123456789 ") if i < len(self.estilos_musica) else "PLANTILLA"

        def _intro_tipo(self):
            seg = getattr(self, "seg_intro", None)
            return self.intros[seg.actual()] if seg is not None and 0 <= seg.actual() < len(self.intros) \
                else self.est.get("intro_tipo", "rampa")

        def _guardar_musica(self):
            """Guarda al momento lo elegido en Ajustes > Sonido (música e intro): el armado lo lee del estado."""
            est = motor.leer_estado()
            est["musica_estilo"] = self.est["musica_estilo"] = self._estilo_musica()
            est["intro_tipo"] = self.est["intro_tipo"] = self._intro_tipo()
            motor.guardar_estado(est)

        def _pagina_ajustes(self):
            """(1.6.0) IGUAL a la maqueta (docs/capturas/propuesta_4_ajustes.png): el bodegon de fondo
            (recursos/ajustes_bodegon.png, recortado y vivo sobre el cielo) y las tarjetas Video, Sonido, Inteligencia, Disco
            y Programa. Lo que no esta en la maqueta (armar solo al soltar, ruido de DaVinci, carpetas, nombres
            originales) va en el menu del logo (_menu_mas)."""
            px = piezas.px
            w = piezas.FondoPagina(os.path.join(rutas.RECURSOS, "ajustes_bodegon.png"))
            v = QHBoxLayout(w)
            v.setContentsMargins(0, px(40), px(30), px(20))
            v.setSpacing(0)
            v.addStretch(21)
            der = QVBoxLayout()
            der.setSpacing(px(40))
            # (18-nov, la persona: «hay incoherencias») las tarjetas en UNA rejilla de 6 columnas (19-nov: la de
            # «Más opciones»): Video y Voz arriba, del mismo alto; las tres de abajo iguales y alineadas
            # --- Video
            tv, lv = piezas.tarjeta("Video", "video")
            self.ch_render = piezas.Interruptor("")
            self.ch_render.setChecked(self.est.get("renderizar", True))
            self.ch_render.setToolTip("Apagado, solo arma las timelines en DaVinci (sin sacar los videos).")
            self.ch_igualar = piezas.Interruptor("")
            self.ch_igualar.setChecked(self.est.get("igualar", True))
            self.ch_igualar.setToolTip("Igualar luz y balance de blancos de cada toma.")
            self.ch_vert = piezas.Interruptor("")
            self.ch_vert.setChecked(bool(self.est.get("usar_verticales", True)))
            self.ch_vert.setToolTip("Encendido (lo normal), el video horizontal acepta videos horizontales y verticales: "
                                    "los verticales entran recortados para llenar la pantalla y DaVinci reencuadra "
                                    "siguiendo a la persona. Apagado, quedan fuera del horizontal (siguen en el media "
                                    "pool). El formato vertical de Inicio usa siempre solo los verticales.")
            self.ch_liberar = piezas.Interruptor("")      # (18-nov) liberar.py
            self.ch_liberar.setChecked(self.est.get("liberar_auto", True) is not False)
            self.ch_liberar.setToolTip("Al pulsar ▶ cierra solos los programas pesados (DxO PureRAW, Photoshop, "
                                       "Premiere, Lightroom, Topaz, CineCaptions, navegadores) como si pulsaras la X: "
                                       "cada uno puede pedir guardar. Con la memoria de video libre la IA va hasta 4 "
                                       "veces más rápida. Nunca toca Windows ni DaVinci.")
            # (19-nov, la persona) los proxies para editar: si o no; si, todos en Videos/PROXIES TRAILER AUTOMATICO
            self.ch_proxies = piezas.Interruptor("")
            self.ch_proxies.setChecked(rutas.proxies_activos())
            self.ch_proxies.setToolTip("Copias livianas (540p) de los videos para que DaVinci edite fluido. Encendido, "
                                       "van todas (de cualquier evento o plantilla) en tu carpeta Videos, en «%s». "
                                       "Apagado, no se hacen: DaVinci usa los originales." % rutas.NOMBRE_PROXIES)
            self.ch_proxies.toggled.connect(self._cambio_proxies)
            lv.setSpacing(px(16))
            for txt, ch in (("Renderizar al terminar", self.ch_render), ("Igualar luz y color", self.ch_igualar),
                            ("Usar videos verticales", self.ch_vert),
                            ("Cerrar programas pesados al armar", self.ch_liberar),
                            ("Proxies para editar", self.ch_proxies)):
                fila = QHBoxLayout()
                l = QLabel(txt, objectName="fila_aj")
                l.setToolTip(ch.toolTip())
                fila.addWidget(l, 1)
                fila.addWidget(ch)
                lv.addLayout(fila)
            lv.addStretch(1)
            # (19-nov) voz original y ruido: su tarjeta, dentro de «Más opciones»
            tvz, lvz = piezas.tarjeta("Voz y ruido", "onda")
            lvz.addSpacing(px(20))
            fila_r = QHBoxLayout()
            fila_r.setSpacing(px(24))
            fila_r.addWidget(QLabel("Quitar ruido", objectName="fila_aj"))
            self.s_ruido = QSlider(Qt.Horizontal)
            self.s_ruido.setRange(0, 100)
            self.s_ruido.setValue(int(self.est.get("ruido") if self.est.get("ruido") is not None else 60))
            self.l_ruido = QLabel(str(self.s_ruido.value()), objectName="fila_aj")
            self.l_ruido.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.s_ruido.valueChanged.connect(lambda x: self.l_ruido.setText(str(x)))
            self.s_ruido.setMinimumWidth(px(160))
            fila_r.addWidget(self.s_ruido, 1)
            fila_r.addWidget(self.l_ruido)
            # --- Musica: el estilo y la intro (lo unico de Ajustes que queda a la vista)
            ts, ls = piezas.tarjeta("Música", "nota")
            ls.addSpacing(px(20))
            l_voz = QLabel("Voz original", objectName="sub_aj")
            l_voz.setToolTip("Lo que se dice en el evento (la palabra del pastor, el brindis, los discursos) suena sobre "
                             "la música. Solo entra cuando alguien habla de corrido: nada de ruidos ni voces sueltas.")

            def fila_seg(etiqueta, seg, en=None):
                # (17-nov) etiqueta a la izquierda y su selector al lado: con Música e Intro, una encima de otra la
                # tarjeta crecia y empujaba las de abajo fuera de la ventana
                f = QHBoxLayout()
                f.setSpacing(px(16))
                etiqueta.setFixedWidth(px(200))
                f.addWidget(etiqueta)
                f.addWidget(seg, 1)
                (en or ls).addLayout(f)
            guardada = self.est.get("voz") if isinstance(self.est.get("voz"), dict) else {}
            self.seg_voz = piezas.Segmentado(["1 min", "3 min", "15 min", "30 min"], None, exclusivo=False)
            self.ch_voz = {}
            # (18-nov, la persona: «que pueda desactivar el sonido de 30 min») antes iba siempre y el boton estaba fijo
            for clave, b in zip(("1min", "3min", "15min", "30min"), self.seg_voz.botones):
                b.setChecked(bool(guardada.get(clave, motor.VOZ_DEFECTO[clave])))
                b.setToolTip("Solo cuando alguien habla de corrido: pastor, brindis, discursos.")
                self.ch_voz[clave] = b
            fila_seg(l_voz, self.seg_voz, lvz)
            lvz.addSpacing(px(20))
            lvz.addWidget(piezas.separador_h())
            lvz.addSpacing(px(14))
            lvz.addLayout(fila_r)
            lvz.addStretch(1)
            # (17-nov) Musica: los estilos de musica original (recursos/musica/<N ESTILO>) o las canciones de la plantilla
            self.estilos_musica = self._estilos_musica()
            if self.estilos_musica:
                l_mus = QLabel("Estilo", objectName="sub_aj")
                l_mus.setToolTip("Música original del programa, hecha a la medida de los videos (sin dueño: no la "
                                 "bloquean en redes). Cada estilo trae su intro, romántica, fiesta y épica. "
                                 "«Plantilla» deja las canciones que trae la plantilla de DaVinci.")
                quiero = str(self.est.get("musica_estilo", "")).upper()
                actual = next((i + 1 for i, n in enumerate(self.estilos_musica) if quiero and quiero in n.upper()),
                              len(self.estilos_musica) + 1 if quiero == "PLANTILLA" else 0)
                self.seg_musica = piezas.Segmentado(
                    ["Auto"] + [n.lstrip("0123456789 ").capitalize().replace("Clasico", "Clásico")
                                for n in self.estilos_musica] + ["Plantilla"], actual)
                self.seg_musica.botones[0].setToolTip("El estilo que le va al tipo de evento: XV cine latino, boda "
                                                      "emotivo, bautizo clásico, graduación y cumpleaños juvenil.")
                self.seg_musica.cambio.connect(lambda _i: self._guardar_musica())
                ls.addWidget(l_mus)              # 6 opciones: a lo ancho, con su etiqueta encima (al lado no cabe)
                ls.addWidget(self.seg_musica)
            # (17-nov) Intro: el ritmo de las 8 fotos de la apertura, cada uno con su SFX (build_trailers.INTROS)
            ls.addSpacing(px(14))
            l_int = QLabel("Intro", objectName="sub_aj")
            l_int.setToolTip("Cómo entran las 8 fotos del principio antes de que arranque el video: «Rampa» pareja, "
                             "«Acelera» de lenta a rápida, «Frena» ráfaga que se detiene, «Latido» de dos en dos. "
                             "Cada una lleva su efecto de sonido y la música entra con el impacto.")
            self.intros =["rampa", "acelera", "frena", "latido"]
            quiero_i = str(self.est.get("intro_tipo", "rampa")).lower()
            self.seg_intro = piezas.Segmentado([n.capitalize() for n in self.intros],
                                               self.intros.index(quiero_i) if quiero_i in self.intros else 0)
            self.seg_intro.cambio.connect(lambda _i: self._guardar_musica())
            fila_seg(l_int, self.seg_intro)
            # (18-nov, la persona: «si doy doble click me salga el pop up con todas las canciones de cada música de
            # estilo, y en las intro igual: doble click me da el ejemplo de cómo se ve»)
            self._doble = {}
            for n, b in enumerate(getattr(self, "seg_musica", None).botones if self.estilos_musica else []):
                self._doble[b] = ("musica", n)
                b.setToolTip((b.toolTip() + "\n" if b.toolTip() else "") + "Doble clic: ver y oír sus canciones.")
                b.installEventFilter(self)
            for n, b in enumerate(self.seg_intro.botones):
                self._doble[b] = ("intro", n)
                b.setToolTip("Doble clic: ver un ejemplo de esta intro.")
                b.installEventFilter(self)
            ls.addStretch(1)
            # (19-nov, la persona: «que no tenga tantas cosas que abrumen») a la vista solo la Musica; lo demas, en
            # «Más opciones» (se cambia de una vista a la otra: la pagina nunca crece)
            self.aj_principal = QWidget()
            rp = QGridLayout(self.aj_principal)
            rp.setContentsMargins(0, 0, 0, 0)
            for c in range(6):
                rp.setColumnStretch(c, 1)
            self.tarjeta_musica = ts                 # (19-nov) va en la pagina Tráilers (_pagina_trailers)
            self.aj_mas = QWidget()
            rej = QGridLayout(self.aj_mas)
            rej.setContentsMargins(0, 0, 0, 0)
            rej.setSpacing(px(30))
            for c in range(6):
                rej.setColumnStretch(c, 1)
            rej.addWidget(tv, 0, 0, 1, 3)
            rej.addWidget(tvz, 0, 3, 1, 3)
            # --- Inteligencia: la IA local que ve y el oido que escucha
            ti, li = piezas.tarjeta("Inteligencia", "chip")
            li.addSpacing(px(10))
            # (17-nov, la persona: «te faltó la IA de vista») «IA local» ES la vista: se llama por lo que hace
            self.p_ia, self.l_ia, self.b_ia = self._fila_estado(li, "Vista")
            self.b_ia.clicked.connect(self._instalar_ia)
            self.p_oido, self.l_oido, self.b_oido = self._fila_estado(li, "Oído")
            self.b_oido.clicked.connect(self._instalar_oido)
            li.addStretch(1)
            rej.addWidget(ti, 1, 0, 1, 2)
            QTimer.singleShot(1500, self._revisar_ia)
            QTimer.singleShot(1600, self._revisar_oido)
            # --- Disco: lo que ocupa la cache y «Borrar caché»
            td, ld = piezas.tarjeta("Disco", "disco")
            ld.addSpacing(px(10))
            self.l_cache = QLabel("Midiendo la caché…", objectName="fila_aj")
            ld.addWidget(self.l_cache)
            self.barra_cache = piezas.BarraUso()
            ld.addWidget(self.barra_cache)
            b = QPushButton("  Borrar caché", objectName="borde")
            b.setIcon(piezas.qicono("papelera", TEXTO, px(44)))
            b.setIconSize(QSize(px(44), px(44)))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self._borrar_cache)
            ld.addWidget(b)
            ld.addStretch(1)
            rej.addWidget(td, 1, 2, 1, 2)
            # --- Programa: version y actualizaciones (como CineCaptions)
            tp, lp = piezas.tarjeta("Programa", "engrane")
            lp.addSpacing(px(16))
            self.l_version = QLabel("Versión %s · Al día" % rutas.version(), objectName="fila_aj")
            lp.addWidget(self.l_version)
            self.l_act = QLabel("", objectName="nota_t")       # lo que dicen las actualizaciones (si hay algo)
            self.l_act.setWordWrap(True)
            self.l_act.hide()
            lp.addWidget(self.l_act)
            lp.addSpacing(px(16))
            self.b_buscar = QPushButton("  Buscar actualizaciones", objectName="borde")
            self.b_buscar.setIcon(piezas.qicono("refrescar", TEXTO, px(48)))
            self.b_buscar.setIconSize(QSize(px(48), px(48)))
            self.b_buscar.setCursor(Qt.PointingHandCursor)
            self.b_buscar.clicked.connect(lambda: self._buscar_actualizacion(manual=True))
            lp.addWidget(self.b_buscar)
            lp.addStretch(1)
            rej.addWidget(tp, 1, 4, 1, 2)
            self._aj_der = der                           # (1.7) _barra_a_qml pone ahi qml/Ajustes.qml
            der.addWidget(self.aj_principal)
            der.addWidget(self.aj_mas)
            self.aj_principal.hide()                 # (19-nov) la Musica se fue a Tráilers: aqui, lo demas a la vista
            fila_mas = QHBoxLayout()
            fila_mas.addStretch(1)
            self.b_mas_aj = QPushButton("Más opciones", objectName="borde")
            self.b_mas_aj.setCursor(Qt.PointingHandCursor)
            self.b_mas_aj.setToolTip("Video, voz original, ruido, inteligencia, disco y versión del programa.")
            self.b_mas_aj.clicked.connect(lambda: self._ver_mas_ajustes(not self.aj_mas.isVisible()))
            fila_mas.addWidget(self.b_mas_aj)
            self.b_mas_aj.hide()
            der.addLayout(fila_mas)
            der.addStretch(1)
            v.addLayout(der, 79)
            # lo que no esta en la maqueta: vive en el menu del logo (los objetos siguen, sin verse)
            oculto = QWidget(w)
            oculto.hide()
            self.ch_auto = piezas.Interruptor("")
            self.ch_auto.setParent(oculto)
            self.ch_auto.setChecked(self.est.get("armar_al_soltar", False))      # (1.6.0) apagado: sala de espera
            self.l_ruido_dv = QLabel("", oculto)
            self.b_ruido_dv = QPushButton("", oculto)
            self.b_ruido_quitar = QPushButton("", oculto)
            self.l_base = QLabel(rutas.SALIDA, oculto)
            self._pintar_ruido_dv()
            QTimer.singleShot(2500, self._medir_cache)
            return w

        def _cambio_proxies(self, si):
            """Ajustes > «Proxies para editar»: se guarda ya; al encenderlo, la carpeta en Videos y los de antes ahi."""
            c = rutas.leer_config()
            c["proxies_activos"] = bool(si)
            rutas.guardar_config(c)
            if not si:
                self._avisar("Proxies apagados: DaVinci editará con los videos originales.")
                return
            os.makedirs(rutas.carpeta_proxies(), exist_ok=True)
            self._avisar("Proxies encendidos: van todos en %s." % rutas.carpeta_proxies())
            self._mudar_proxies()

        def _mudar_proxies(self):
            """Los proxies de antes (por dentro) a la carpeta de Videos, en un hilo (son GB: otro disco = copiar)."""
            if not rutas.proxies_activos() or not os.path.isdir(rutas.PROXIES_VIEJOS):
                return
            import editable

            def listo(n, error):
                if error is None and n:
                    self._avisar("Proxies mudados a tu carpeta Videos: %d." % n)
            qt_kit.correr_en_hilo(self, lambda: editable.mudar_proxies(registro.info), listo, baja=True)

        def _pagina_trailers(self):
            """(19-nov, la persona: «la de tráilers súper minimalista, solo de escoger el estilo y listo») el estilo
            de la música y la intro (la tarjeta Música, que antes estaba en Ajustes). Cada clic se guarda solo."""
            px = piezas.px
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(px(140), px(60), px(140), px(40))
            v.setSpacing(px(16))
            v.addStretch(1)
            t = QLabel("Elige el estilo", objectName="titulo_pag")
            t.setAlignment(Qt.AlignCenter)
            v.addWidget(t)
            s = QLabel("Un clic y listo: se guarda solo. Doble clic para oír sus canciones o ver la intro.")
            s.setAlignment(Qt.AlignCenter)
            s.setStyleSheet("color:%s;" % TENUE)
            v.addWidget(s)
            v.addSpacing(px(40))
            v.addWidget(self.tarjeta_musica)
            self._pag_trailers = (w, v)                # (1.7) _barra_a_qml la cambia por qml/Trailers.qml
            v.addStretch(2)
            return w

        def _pagina_plantillas(self):
            """(19-nov, la persona: «crea una página que sea para plantillas») las plantillas de video (Reels, TikTok,
            CapCut que el programa copia con las tomas del evento): antes, cerradas dentro de Material."""
            px = piezas.px
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(px(60), px(50), px(60), px(30))
            v.setSpacing(px(24))
            v.addWidget(self._tarjeta_plantillas())
            self._pag_plantillas = (w, v)              # (1.7) _barra_a_qml la cambia por qml/Plantillas.qml
            self.b_ver_pl.hide()                     # en su pagina, siempre abierta
            self.cuerpo_pl.show()
            v.addStretch(1)
            return w

        def _ver_mas_ajustes(self, ver):
            """Ajustes: de la Musica a «Más opciones» y de vuelta, con un fundido."""
            import animacion
            self.aj_principal.setVisible(not ver)
            self.aj_mas.setVisible(ver)
            self.b_mas_aj.setText("Volver" if ver else "Más opciones")
            animacion.aparecer(self.aj_mas if ver else self.aj_principal)

        def _menu_mas(self):
            """(1.6.0) El menu del logo: lo que la maqueta no muestra pero se usa."""
            from PySide6.QtWidgets import QMenu
            m = QMenu(self)
            m.addAction("Clasificación del evento", self._clasificacion)
            m.addAction("Abrir DaVinci Resolve", rutas.abrir_resolve)
            m.addAction("Videos terminados", self._abrir_terminado)
            m.addAction("Nombres originales", self._restaurar_nombres)
            m.addAction("Carpeta del programa", lambda: rutas.abrir(rutas.PROGRAMA))
            if rutas.CONGELADO:
                m.addAction("Cambiar la carpeta de eventos terminados…", self._cambiar_base)
            m.addSeparator()
            auto = m.addAction("Armar solo al soltar una carpeta")
            auto.setCheckable(True)
            auto.setChecked(self.ch_auto.isChecked())
            auto.toggled.connect(self.ch_auto.setChecked)
            dv = self.l_ruido_dv.text()
            m.addAction("Ruido de DaVinci: usar el del clip actual", self._guardar_ruido_dv).setToolTip(dv)
            if self.b_ruido_quitar.isVisible() or "clip" in dv:
                m.addAction("Ruido de DaVinci: volver al del programa", self._quitar_ruido_dv)
            m.addSeparator()
            m.addAction("Ver lo que va haciendo", lambda: self.b_log.setChecked(not self.b_log.isChecked()))
            m.exec(self.b_logo.mapToGlobal(self.b_logo.rect().bottomLeft()))

        def _fila_estado(self, lay, nombre):
            """Una fila de Inteligencia (en su cajita, como la maqueta): punto de color y «IA local · Lista»; si falta
            algo, el enlace para instalarlo."""
            px = piezas.px
            caja = QFrame(objectName="caja_estado")
            fila = QHBoxLayout(caja)
            fila.setContentsMargins(px(26), px(14), px(20), px(14))
            fila.setSpacing(px(20))
            p = QLabel()
            p.setPixmap(piezas.icono("punto", TENUE, px(26)))
            fila.addWidget(p)
            l = QLabel(nombre + " · revisando…", objectName="fila_aj")
            fila.addWidget(l, 1)
            b = QPushButton("Instalar", objectName="link")
            b.setCursor(Qt.PointingHandCursor)
            b.hide()
            fila.addWidget(b)
            lay.addWidget(caja)
            return p, l, b

        def _medir_cache(self):
            """Cuanto ocupa lo que «Borrar caché» puede liberar (en un hilo: recorrer la cache de DaVinci tarda)."""
            import limpieza

            def listo(items, error):
                if error is not None or items is None:
                    self.l_cache.setText("No se pudo medir la caché")
                    return
                total = sum(i["bytes"] for i in items)
                self.l_cache.setText("%s de caché" % limpieza.texto_tam(total))
                self.barra_cache.poner(total / 30e9)
            qt_kit.correr_en_hilo(self, limpieza.que_hay, listo, baja=True)

        # ============================================================== IA local (1.5.7)
        def _revisar_ia(self):
            """En un hilo: ¿hay IA local que vea las tomas? (Ollama con un modelo de vision)."""
            import vision_ia
            qt_kit.correr_en_hilo(self, vision_ia.estado, self._pintar_ia, baja=True)

        def _pintar_ia(self, r, error):
            if error is not None or not r:
                self.l_ia.setText("No se pudo revisar la vista.")
                return
            texto, accion = r
            self.l_ia.setText("Vista · %s" % ("Lista" if accion is None else "falta instalarla"))
            self.l_ia.setToolTip(texto)
            self.p_ia.setPixmap(piezas.icono("punto", ESMERALDA.name() if accion is None else AMBAR, 10))
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
            if not self._si("¿Bajar el modelo de IA local %s (unos 6 GB)?\n\nCon él el programa ve "
                            "cada toma (iglesia, fiesta, preparativos, los momentos clave) y arma mejor. Se baja "
                            "una sola vez; luego todo es local, sin internet." % vision_ia.MODELO_RECOMENDADO,
                            "Bajar", "Ahora no"):
                return
            self.b_ia.setEnabled(False)
            self.l_ia.setText("Bajando el modelo… (puede tardar varios minutos)")
            qt_kit.correr_en_hilo(self, lambda: vision_ia.instalar_modelo(registro.info),
                                  lambda r, e: self._revisar_ia())

        # ============================================================== oido (1.5.9)
        def _revisar_oido(self):
            """En un hilo: ¿esta earshot, el oido que escucha cada toma y el audio final?"""
            import oido
            qt_kit.correr_en_hilo(self, oido.estado, self._pintar_oido, baja=True)

        def _pintar_oido(self, r, error):
            if error is not None or not r:
                self.l_oido.setText("No se pudo revisar el oído.")
                return
            texto, listo = r
            self.l_oido.setText("Oído · %s" % ("Listo" if listo else "no instalado (opcional)"))
            self.l_oido.setToolTip(texto)
            self.p_oido.setPixmap(piezas.icono("punto", ESMERALDA.name() if listo else TENUE, 10))
            self.b_oido.setText("Cómo instalarlo")
            self.b_oido.setVisible(not listo)

        def _instalar_oido(self):
            import oido
            QApplication.clipboard().setText(oido.INSTALAR)
            self._popup("El oído es earshot (%s): libre y local, sin internet.\n\n"
                        "Para instalarlo, en una terminal con uv:\n\n%s\n\n(El comando ya quedó copiado.) "
                        "La primera vez baja su modelo de sonidos (1 GB). Luego abre el programa otra vez."
                        % (oido.PAGINA, oido.INSTALAR), titulo="Instalar el oído")

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
                self._popup("Cierra y vuelve a abrir el programa para usar:\n%s" % d, titulo="Listo")

        def _restaurar_nombres(self):
            """(1.5.7) Deshace el renombrado del material del evento (vuelven los nombres que traian los archivos)."""
            if self.trabajo is not None or self.copia is not None:
                self._avisar("Espera a que termine lo que está haciendo.", "warn")
                return
            if not self._si("¿Devolver a los archivos del evento los nombres que traían?\n\n"
                            "No se borra ni se mueve nada; DaVinci los vuelve a encontrar. Mientras sea este "
                            "evento, el programa ya no los renombrará.", "Devolver nombres", "Cancelar"):
                return
            qt_kit.correr_en_hilo(self, lambda: motor.restaurar_nombres(registro.info),
                                  lambda n, error: self._avisar(
                                      "No se pudieron restaurar los nombres: %s" % error if error is not None
                                      else "Nombres originales restaurados: %d archivos." % (n or 0),
                                      "error" if error is not None else "ok"))

        def _borrar_cache(self):
            """(17-nov) «Borrar caché»: lo que el programa vuelve a hacer solo si hace falta (caché de render de DaVinci,
            proxies, respaldos viejos, actualizaciones ya instaladas, temporales; limpieza.py). Nunca el material, los
            videos terminados, las plantillas, las capturas de la intro ni los nombres originales."""
            if self.trabajo is not None or self.copia is not None:
                self._avisar("Espera a que termine lo que está haciendo.", "warn")
                return
            import limpieza

            def fin(r, error):
                if error is not None or not r:
                    self._avisar("No se pudo borrar la caché: %s" % error, "error")
                    return
                libres, fallas, saltadas = r
                texto = "Caché borrada: %s liberados." % limpieza.texto_tam(libres)
                if "davinci" in saltadas:
                    texto += " La de DaVinci queda: ciérralo y vuelve a borrar."
                if fallas:
                    texto += " %d archivos en uso quedaron." % fallas
                self._avisar(texto, "ok")
                self._medir_cache()                      # (1.6.0) la barra de la tarjeta Disco

            def listo(r, error):
                if error is not None or not r:
                    self._avisar("No se pudo revisar la caché: %s" % error, "error")
                    return
                items, abierto = r
                if not items:
                    self._avisar("No hay caché que borrar: el disco ya está limpio.", "ok")
                    return
                lineas, total = [], 0
                for it in items:
                    extra = ""
                    if it["clave"] == "davinci" and abierto:
                        extra = "  (cierra DaVinci para borrarla)"
                    else:
                        total += it["bytes"]
                    lineas.append("•  %s: %s%s" % (it["texto"], limpieza.texto_tam(it["bytes"]), extra))
                msg = ("Se borra lo que el programa vuelve a hacer solo si hace falta:\n\n%s\n\nSe liberan: %s\n\n"
                       "No se borra tu material, los videos terminados, las plantillas de DaVinci, las capturas de "
                       "la intro ni los nombres originales." % ("\n".join(lineas), limpieza.texto_tam(total)))
                if not self._si(msg, "Borrar caché", "Cancelar", titulo="¿Borrar la caché?"):
                    return
                qt_kit.correr_en_hilo(self, lambda: limpieza.borrar(registro.info, davinci_abierto=abierto), fin)
            qt_kit.correr_en_hilo(self, lambda: (limpieza.que_hay(), motor.resolve_abierto()), listo)

        def _abrir_terminado(self):
            """La carpeta EVENTO TERMINADO del último evento (o donde se crean, si todavía no hay ninguna)."""
            evento = (self.resultado or {}).get("evento") or motor.leer_estado().get("evento")
            carpeta = rutas.carpeta_terminado(evento) if evento else ""
            rutas.abrir(carpeta if carpeta and os.path.isdir(carpeta) else rutas.SALIDA)

        # ============================================================== estado
        def _ir(self, nombre):
            self.tabs[nombre].setChecked(True)
            self._cambiar_pagina(list(self.tabs).index(nombre))

        ORDEN_VISTA = ("Inicio", "Tráilers", "Plantillas", "Ajustes")

        def _igualar_tabs(self):
            """(1.7.9) Las 4 pestañas del mismo ancho (el de la mas ancha, en negrita): separacion pareja y la gota no
            cambia de tamaño al viajar. Se rehace al cambiar la escala de la ventana (cambia la letra)."""
            visibles = [self.tabs[t] for t in self.ORDEN_VISTA if t in self.tabs]
            for b in visibles:
                b.setMinimumWidth(0)
                b.setMaximumWidth(16777215)
            negrita = QFont(visibles[0].font())
            negrita.setWeight(QFont.DemiBold)
            from PySide6.QtGui import QFontMetrics
            extra = max(0, max(b.sizeHint().width() - b.fontMetrics().horizontalAdvance(b.text()) for b in visibles))
            ancho = max(QFontMetrics(negrita).horizontalAdvance(b.text()) for b in visibles) + extra
            for b in visibles:
                b.setFixedWidth(ancho)

        def _direccion_pagina(self, i):
            """(1.7.8) +1 si la pagina nueva esta a la derecha de la anterior en la barra de pestañas, -1 si a la
            izquierda (la pagina entra deslizandose desde ese lado), 0 si no se sabe."""
            nombres = list(self.tabs)
            antes = getattr(self, "_pagina_vista", 0)
            self._pagina_vista = i
            try:
                a = self.ORDEN_VISTA.index(nombres[antes])
                b = self.ORDEN_VISTA.index(nombres[i])
            except (ValueError, IndexError):
                return 0
            return (b > a) - (b < a)

        def _cambiar_pagina(self, i):
            """(1.6.0) Cambio de pestaña con fundido: la foto de la pagina de antes se desvanece sobre la nueva."""
            if i == self.paginas.currentIndex():
                return
            # (1.7.8, auditoria de animaciones) una pagina QML entra sola (entrar(): fundido y subida en la tarjeta):
            # con la foto encima se veian DOS fundidos a la vez y el de la foto repintaba toda la zona con el procesador
            if i in (getattr(self, "paginas_qml", None) or {}):
                self.paginas.setCurrentIndex(i)
                return
            foto = self.paginas.currentWidget().grab() if self.isVisible() and not self.isMinimized() else None
            self.paginas.setCurrentIndex(i)
            if foto is not None:
                self.fundido.empezar(foto)

        def _avisar(self, texto, tipo="info"):
            """(1.6.0) La franja de avisos ya no queda fija: aparece con cada aviso y se va sola (7 s; 20 s si es un
            problema). Con una actualizacion lista para instalar se queda."""
            self.aviso_t.setText(texto)
            self.aviso_h.setText(time.strftime("%H:%M"))
            repulir(self.aviso, tipo=tipo)
            repulir(self.aviso_i, tipo=tipo)
            self.aviso_i.setText("i" if tipo in ("info", "ok") else "!")
            self.aviso.show()
            if not hasattr(self, "t_aviso"):
                self.t_aviso = QTimer(self, singleShot=True)
                self.t_aviso.timeout.connect(lambda: None if self.b_actualizar.isVisible() else self.aviso.hide())
            self.t_aviso.start(7000 if tipo in ("info", "ok") else 20000)

        def _estado(self, texto, tipo="ok", ayuda=None):
            """La pastilla de arriba a la derecha: un punto de color y pocas palabras («Todo listo», «Trabajando»)."""
            color = {"ok": ESMERALDA.name(), "warn": AMBAR, "error": ROJO, "oro": "#D9A441"}.get(tipo, TENUE)
            self.b_log.setText(texto)
            # (19-nov, la persona: «que no abrume») con todo en orden y quieto no se ve: solo trabajando o con avisos
            oculta = tipo == "ok" and texto == "Todo listo"
            if oculta and self.b_log.isChecked():
                self.b_log.setChecked(False)          # el registro abierto se cierra con ella (si no, sin boton)
            self.b_log.setVisible(not oculta)
            self._estado_vivo = (color, tipo)          # (1.6.0) el punto late (mas rapido trabajando)
            self._latir_estado()
            repulir(self.b_log, tipo=tipo)
            if ayuda is not None:
                self.b_log.setToolTip(ayuda + "\n\nClic: ver lo que va haciendo")

        def _latir_estado(self):
            color, tipo = getattr(self, "_estado_vivo", (TENUE, "ok"))
            if not hasattr(self, "t_latido"):
                self.t_latido = QTimer(self, interval=90)
                self.t_latido.timeout.connect(self._latir_estado)
                self.t_latido.start()
            if self.isMinimized():
                return
            f = 0.5 + 0.5 * math.sin(time.monotonic() * (5.0 if tipo == "oro" else 2.0))
            self.b_log.setIcon(QIcon(piezas.punto_latido(color, piezas.px(24), f)))

        def _brillos(self):
            """(1.6.0) Botones, pastillas y pestañas brillan suave al pasar el raton."""
            import animacion
            colores = {"chip": piezas.ORO, "chip2": piezas.ORO, "segb": piezas.ORO, "pill": "#7CF5C0", "tab": piezas.ORO,
                       "boton_verde": "#B8FFE0", "cancelar": piezas.ORO, "pill_tipo": piezas.ORO,
                       "pill_vista": piezas.ORO, "boton": piezas.ORO, "borde": piezas.ORO, "estado": piezas.ORO}
            # (18-nov, la persona: «al pasar el mouse se ve redondeado, muy mal») el brillo se pintaba como pastilla o
            # con 16 px fijos encima de botones de 9-12 px: dos formas a la vez. Ahora usa el radio REAL de cada boton
            # (el de su estilo), asi el brillo calza con el borde.
            import re
            hoja = QApplication.instance().styleSheet() + "\n" + self.styleSheet()     # manda la ultima regla
            radios = {}
            for n in colores:
                m = re.findall(r"#%s\b[^{]*\{[^}]*?border-radius:\s*(\d+)px" % n, hoja)
                radios[n] = float(m[-1]) if m else 10.0
            for b in self.findChildren(QPushButton):
                n = b.objectName()
                if n in colores:
                    animacion.brillo_al_pasar(b, colores[n], radios[n])
            r = piezas.px(40)                       # la barra del Inicio: el radio del panel (dock_r)
            for b, color, abierto in ((self.b_nombre, piezas.ORO, "der"), (self.b_plantillas, piezas.ORO, "ambos"),
                                      (self.b_trailer, "#B8FFE0", "izq")):
                animacion.brillo_al_pasar(b, color, r, abierto)

        def _sub(self, texto, tipo=""):
            self.sub.setText(texto)
            repulir(self.sub, tipo=tipo)
            # (1.6.0) vacio no ocupa lugar; trabajando no se ve (la maqueta: solo «Trabajando…», pasos y versiones)
            self.sub.setVisible(bool(texto) and self.trabajo is None and not self.panel_trabajo.isVisible())

        def _pintar_evento(self, *_):
            tipo = self.c_tipo.currentText() if hasattr(self, "c_tipo") else \
                dict(TIPOS).get(self.est.get("tipo_evento", "xv"), "XV años")
            nombre = self.e_nombre.text().strip() if hasattr(self, "e_nombre") else self.est.get("nombre_xv", "")
            self.chip_evento.setText(("   %s" % (("%s · %s" % (tipo, nombre)) if nombre else "Pon los nombres"))
                                     .replace("&", "&&"))
            if hasattr(self, "b_nombre"):                             # (19-nov) la barra: solo el nombre
                self.b_nombre.setText(("   " + (nombre or "Pon el nombre")).replace("&", "&&"))
                self.b_nombre.setToolTip("%s · toca para cambiar el nombre" % tipo)
            if getattr(self, "barra_qml", None) is not None:
                self.barra_qml.poner_nombre(nombre or "Pon el nombre", "%s · toca para cambiar el nombre" % tipo)
            if self.chip_evento.icon().isNull():                      # el lapiz, dibujado («✎» no esta en la fuente)
                self.chip_evento.setIconSize(QSize(14, 14))
                self.chip_evento.setIcon(icono_trazo("lapiz", "#EBCB8F", 14))

        def _cambio_plantillas(self, _=None, vacio_ok=False):
            if not vacio_ok and not any(b.isChecked() for b in self._pastillas()):
                quien = self.sender()                             # siempre al menos una, de un formato u otro
                (quien if quien in self._pastillas() else self.pills[motor.VERSIONES[0]]).setChecked(True)
            for pills in (self.pills, self.pills_v):
                for v, b in pills.items():
                    b.setIcon(self._palomita if b.isChecked() else QIcon())
                    b.setText((" " if b.isChecked() else "") + VERSION_TEXTO[v])     # un respiro entre palomita y texto
            self._sub_material()
            self._refrescar_barra()

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
                nuevos = None                # (18-nov) lo ya analizado no se cuenta otra vez (decia 80 min de mas)
                try:
                    import analizar_material as am
                    faltan, total = am.cuantos_faltan()
                    if total:
                        nuevos = int(round(n * faltan / float(total)))
                    self._ya_analizado = bool(total) and faltan == 0
                except Exception:
                    pass
                return motor.estimar_segundos(n, gb, self._versiones(), vert, getattr(self, "_con_render", True),
                                              nuevos)
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
            """(1.6.0) Lo que hay va en las pastillas del panel (en ambar lo que falta) y la hora en que estara listo."""
            m = self.material
            c = m["cuenta"]
            faltan = dict(m["faltan"])
            for tipo, ch in getattr(self, "chips_mat", {}).items():
                ch.setText("   " + _cuantos(c.get(tipo, 0), tipo))         # el aire entre icono y texto (maqueta)
                repulir(ch, tipo="falta" if faltan.get(tipo) else "")
            if hasattr(self, "chip_mat"):            # (19-nov) un solo resumen: lo que falta o lo que hay
                falta = [_cuantos(n, t) for t, n in faltan.items() if n]
                hay = [_cuantos(c.get(t, 0), t) for t in ("foto", "video", "dron") if c.get(t)]
                self.chip_mat.setText("   " + ("Falta " + " y ".join(falta) if falta else
                                               " · ".join(hay) if hay else "Sin material"))
                repulir(self.chip_mat, tipo="falta" if falta else "")
            if hasattr(self, "chip_que"):
                corto = lambda vs: " · ".join(VERSION_TEXTO[v].split()[0] for v in vs) + " min" if vs else ""
                h, vv = corto(self._versiones()), corto(self._versiones_v())
                self.chip_que.setText("   " + (h + (" + vertical " + vv if vv else "") if h else
                                               "Vertical " + vv if vv else "Elige los videos"))
            if hasattr(self, "l_eta"):
                s = self._estimar() if self.trabajo is None else None
                self.l_eta.setText("Listo a las %s" % time.strftime("%H:%M", time.localtime(time.time() + s)) if s else "")
            # (1.6.1) la sala de espera: las carpetas flotando y «Empezar», mientras no este trabajando ni mirando otra
            espera = self._en_espera and self.trabajo is None and self.copia is None
            if hasattr(self, "sala"):
                self.sala.poner(self._carpetas if espera else [])
            if self.trabajo is not None or self.flujo is not None:
                return
            n = len(self._carpetas)
            if m["ok"] and n and self._en_espera:
                self._sub("%s  ·  suelta otra o pulsa Empezar" % (
                    "1 carpeta lista" if n == 1 else "%d carpetas listas" % n), "ok")
            elif m["ok"]:
                self._sub("")
            else:
                self._sub("Falta material: %s  ·  pulsa el botón y te digo qué agregar" % ", ".join(
                    _cuantos(n, t) for t, n in m["faltan"]))

        def _preanalizar(self):
            """(1.8.2, la persona: «aplica todo») Analiza mientras la persona escribe el nombre y elige: al pulsar
            Empezar casi todo ya esta medido y visto por la IA. Si ya hay uno andando (otra carpeta soltada), el que
            sigue lo encadena al terminar: el analisis es por archivo y lo hecho no se repite."""
            pre = getattr(self, "preanalisis", None)
            if pre is not None and pre.isRunning():
                self._preanalisis_otra = True
                return
            self._preanalisis_otra = False
            self.preanalisis = Preanalisis()
            self.preanalisis.linea.connect(self._linea_preanalisis)
            self.preanalisis.finished.connect(self._fin_preanalisis)
            self.preanalisis.start()

        def _fin_preanalisis(self):
            if getattr(self, "_preanalisis_otra", False) and self.trabajo is None:
                self._preanalizar()
            elif self.trabajo is None and self._en_espera:
                self._ya_analizado = True
                self._sub("Material analizado: pulsa Empezar y va directo a las plantillas.", "ok")

        def _linea_preanalisis(self, m):
            """Si ya se pulso Empezar, el avance del analisis se ve como el del trabajo; si no, en una linea discreta."""
            if self.trabajo is not None:
                self._linea(m)
                return
            registro.info("[preanalisis] " + m)
            a = re.match(r"\s+(\d+)/(\d+)\s+(\S.*)$", m)
            if a and self.flujo is None:
                self._sub("Analizando mientras esperas: %s de %s" % (a.group(1), a.group(2)))
            elif m.startswith(("La IA local", "Viendo cada toma", "El oído")) and self.flujo is None:
                self._sub("Analizando mientras esperas: " + m.split(":")[0].split("(")[0].strip().lower())

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
                import animacion
                animacion.contar(n, cuantos)                   # (1.6.0) el numero sube contando
                if falta:
                    e.setText("Faltan %d" % falta if cuantos else "Vacía: agrega %s" % (
                        "al menos 8 fotos" if tipo == "foto" else "videos"))
                else:
                    e.setText("" if cuantos else "Opcional")   # (1.6.0) lo que esta bien no se repite
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
            self._estado("Revisando…", "", "Chequeo de arranque…")     # (1.6.0) en la pastilla, no en una franja
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
            """(1.6.0) El chequeo de arranque va a la pastilla de estado (ya no a una franja fija)."""
            mal = [(n, d) for n, ok, d in res if not ok]
            self._chequeo = (len(res), mal)
            if self.trabajo is not None:                 # (19-nov) no pisa «Trabajando» (ni oculta la pastilla)
                return
            detalle = "\n".join("· " + (d if ok else "Falta: " + d) for n, ok, d in res)
            # (1.8.5, la persona: «elimina eso») sin la pastilla «1 aviso»: lo que falta ya lo dice Ajustes
            # (Inteligencia, Programa) y queda en el registro; arriba solo se ve trabajando
            if mal:
                registro.info("Chequeo de arranque:\n" + detalle)
            self._estado("Todo listo", "ok", "Chequeo de arranque: %d de %d en orden." % (len(res) - len(mal), len(res)))
            QTimer.singleShot(800, self._revisar_permisos)

        # ---- (1.8.2, la persona: «un popup con todos los permisos... si ya tiene todos ya no sale») permisos.py
        def _revisar_permisos(self, despues=None):
            import permisos

            def listo(res, error):
                if error is not None or res is None:
                    return
                faltan = permisos.faltan(res)
                if despues is not None:
                    despues(faltan)
                    return
                if faltan and self.trabajo is None:
                    self._pedir_permisos(faltan)
            qt_kit.correr_en_hilo(self, permisos.revisar, listo)

        def _pedir_permisos(self, faltan, mensajes=()):
            import permisos
            lista = "\n".join("·  %s" % p["nombre"] for p in faltan)
            previo = ("\n\n" + "\n".join(mensajes)) if mensajes else ""
            if self._popup("Para trabajar con total libertad el programa necesita:\n\n%s%s\n\n%s" % (
                               lista, previo, "Lo que pide administrador va en una sola ventana de Windows."
                               if rutas.ES_WIN else "Se abre Privacidad: activa «Tráiler automático» en cada lista."),
                           ("Dar permisos", "Ahora no"), "aviso", titulo="Permisos",
                           # (20-nov) Enter/Esc = «Ahora no»: lo que pide administrador solo con un CLIC a proposito
                           # (en una prueba un Enter suelto lo acepto y Windows lo dio sin preguntar)
                           primario=1) != 0:
                return
            self._avisar("Dando los permisos…")

            def hecho(msj, error):
                msj = list(msj or []) + ([str(error)] if error is not None else [])

                def revisado(siguen):
                    if siguen:
                        self._pedir_permisos(siguen, msj)
                    else:
                        self._avisar("Listo: el programa tiene todos los permisos.", "ok")
                self._revisar_permisos(revisado)
            qt_kit.correr_en_hilo(self, lambda: permisos.dar(faltan), hecho)

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
            # (1.6.0) tambien mientras mira o toma otra carpeta: lo soltado espera su turno (_cola_soltar)
            if e.mimeData().hasUrls() and self.trabajo is None and self.flujo in (None, "mirando", "copiando"):
                e.acceptProposedAction()
                self.hoja.mostrar("soltar", "Suelta aquí la carpeta del evento",
                                  "La agrego a la lista y la ordeno en fotos, videos y dron.\n"
                                  "Puedes soltar más: empiezo cuando tú lo digas.", icono="↓")

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
            if self.trabajo is not None or self.flujo in ("datos", "cuenta", "pregunta"):
                self._avisar("Espera a que termine lo que está haciendo y vuelve a soltar el material.", "warn")
                return
            if self.copia is not None or self.flujo is not None:      # (1.6.0) mirando otra: esta espera su turno
                self._cola_soltar.append((archivos, tipo))
                self._avisar("La agrego en cuanto termine con la anterior.")
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
            self.dock.hide()                         # (1.6.0) mientras toma el material, sin el panel de abajo
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
            self.dock.show()
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
                if getattr(self, "_ya_analizado", False):
                    resumen = "Material YA ANALIZADO: elige la plantilla y pulsa Empezar  ·  " + resumen
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
            try:                                         # (1.6.0) la lista de la sala de espera
                self._carpetas = [c for c in (motor.leer_estado().get("carpetas") or []) if isinstance(c, str)]
            except Exception:
                pass
            self._en_espera = True
            self._chips_editable(False)                  # (19-nov) material nuevo esperando: editar el de antes, no
            self._falta_datos = self._tipo_copia is None and (self._evento_nuevo or not self.e_nombre.text().strip())
            self._revisar_material()
            if self.material["ok"] and not getattr(self, "_ya_analizado", False):
                self._preanalizar()
            self.l_copia.setText(resumen.split("\n")[0].split("  ·  ")[0])      # corto: cabe en una linea junto al boton
            if not self.material["ok"]:
                self._fin_flujo(resumen.split("\n")[0] + "  ·  todavía falta: " + ", ".join(
                    "%d %s" % (n, motor.NOMBRE_CARPETA[t].lower()) for t, n in self.material["faltan"]), "warn")
            elif self._tipo_copia is not None or not self.ch_auto.isChecked() or self._cola_soltar:
                # (1.6.0) sala de espera: no arma solo; se pueden soltar mas carpetas y empieza al pulsar el boton
                self._fin_flujo(resumen.split("\n")[0])          # («suelta otra o pulsa Empezar» ya lo dice la sala)
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
                               ("Ahora no", lambda: self._fin_flujo("Material ordenado. Pulsa ▶ cuando quieras armar."),
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
            self.titulo.setText(TITULO_INICIO)
            self._play(auto=True)

        def _fin_flujo(self, texto, tipo="info"):
            self.hoja.ocultar()
            self.flujo = None
            self.titulo.setText(TITULO_INICIO)
            self._avisar(texto, tipo)
            self._sub_material()
            if self._cola_soltar and self.trabajo is None:           # (1.6.0) la siguiente carpeta que esperaba turno
                archivos, tipo_c = self._cola_soltar.pop(0)
                QTimer.singleShot(0, lambda: self._recibir(archivos, tipo_c))

        def _popup(self, texto, botones=("Entendido",), tipo="info", titulo=None, primario=0):
            """(1.6.1) Las preguntas y avisos van en un popup dentro de la ventana (piezas.Popup, diseño de Higgsfield),
            no en cuadros del sistema. Devuelve el numero del boton elegido (Esc = el ultimo). Sin titulo, usa el primer
            parrafo del texto si es corto."""
            if titulo is None:
                primero, _, resto = texto.partition("\n\n")
                if resto and len(primero) <= 70 and "\n" not in primero:
                    titulo, texto = primero, resto
                else:
                    titulo = {"aviso": "Atención", "pregunta": "Confirma", "error": "Algo falló"}.get(tipo, "Aviso")
            return piezas.preguntar(self, titulo, texto, botones, tipo, primario)

        def _si(self, texto, si="Sí", no="No", tipo="pregunta", titulo=None):
            return self._popup(texto, (si, no), tipo, titulo) == 0

        # ---- (1.6.1) proyecto nuevo: el boton de refrescar del Inicio
        def _proyecto_nuevo(self):
            if self.trabajo is not None or self.copia is not None or self.flujo is not None:
                self._avisar("Espera a que termine lo que está haciendo para empezar un proyecto nuevo.", "warn")
                return
            if self._si("El programa queda en blanco para otro evento: se quitan de la lista las carpetas puestas y se "
                        "borran los nombres y textos.\n\nNo se borra ningún archivo: las carpetas siguen donde están y "
                        "los videos terminados no se tocan.", "Proyecto nuevo", "Cancelar",
                        titulo="¿Empezar un proyecto nuevo?"):
                self._hacer_proyecto_nuevo()

        def _hacer_proyecto_nuevo(self):
            self.flujo = "nuevo"
            self._sub("Dejando todo en blanco para un proyecto nuevo…")

            def limpiar():
                nombre = motor.evento_actual()[0] or motor.evento_terminado()
                return motor.archivar_material(nombre)        # lo de dentro pasa a ANTERIORES; el estado, en blanco

            def listo(res, error):
                self._cola_soltar = []
                if error is not None:
                    self._fin_flujo("No pude empezar el proyecto nuevo: %s" % error, "error")
                    return
                self.est = motor.leer_estado()
                self._carpetas, self._en_espera, self._falta_datos = [], False, False
                for w in (self.e_nombre, self.e_frase, self.e_fecha):
                    w.setText("")
                self.l_copia.setText("")
                self.chip_videos.hide()
                self._chips_editable(False)
                self._revisar_material()
                self._fin_flujo("Proyecto nuevo: suelta la carpeta del evento.")
            qt_kit.correr_en_hilo(self, limpiar, listo)

        # ============================================================== play
        def _guardar(self):
            versiones, verticales = self._versiones(), self._versiones_v()
            # (1.8.2) sin versiones pero con plantillas marcadas: SOLO las plantillas (antes salian tambien las 4)
            if not versiones and not verticales and not sorted(getattr(self.plantillas, "marcadas", None) or []):
                versiones = list(motor.VERSIONES)
            d = motor.leer_estado()
            d.update({"tipo_evento": self.c_tipo.currentData(), "nombre_xv": self.e_nombre.text().strip(),
                      "frase": self.e_frase.text().strip(), "fecha_lugar": self.e_fecha.text().strip(),
                      "versiones": versiones, "versiones_vertical": verticales, "ruido": self.s_ruido.value(),
                      "igualar": self.ch_igualar.isChecked(), "renderizar": self.ch_render.isChecked(),
                      "armar_al_soltar": self.ch_auto.isChecked(),
                      "voz": {k: ch.isChecked() for k, ch in self.ch_voz.items()},
                      "usar_verticales": self.ch_vert.isChecked(), "musica_estilo": self._estilo_musica(),
                      "liberar_auto": self.ch_liberar.isChecked(),
                      "intro_tipo": self._intro_tipo()})
            motor.guardar_estado(d)
            return dict(evento=d.get("evento_manual", ""), nombre_xv=d["nombre_xv"], fecha_lugar=d["fecha_lugar"],
                        frase=d["frase"], tipo_evento=d["tipo_evento"], ruido=d["ruido"], igualar=d["igualar"],
                        voz=d["voz"], verticales=d["usar_verticales"],
                        solo=versiones if 0 < len(versiones) < len(motor.VERSIONES) else None,
                        horizontal=bool(versiones), vertical=verticales, render=d["renderizar"])

        def _pedir_material(self):
            faltan = self.material["faltan"]
            texto = "Para armar el video falta " + " y ".join(
                ("al menos %d fotos (faltan %d)" % (motor.MINIMOS[t], n) if t == "foto"
                 else "al menos %d video" % motor.MINIMOS[t]) for t, n in faltan) + \
                ".\n¿Lo agregas ahora? También puedes arrastrar la carpeta del evento a la ventana."
            r = self._popup(texto, ("Agregar carpeta", "Abrir carpeta", "Ahora no"), "aviso", titulo="Falta material")
            tipo = faltan[0][0]
            if r == 0:                            # (19-nov) sin pagina de Material: la carpeta del evento, donde esta
                self._agregar_carpeta()
            elif r == 1:
                rutas.abrir(rutas.CARPETAS[tipo])

        def _chips_editable(self, ver=None):
            """«Editar en DaVinci» y «Renderizar lo editado» se ven cuando hay un evento armado (y no se esta trabajando)."""
            if ver is None:                       # (19-nov) solo con el evento TERMINADO (sus videos ya salieron)
                est = motor.leer_estado()
                ver = bool(est.get("timelines") and motor.evento_terminado()) and self.trabajo is None \
                    and not getattr(self, "_en_espera", False)
            # (19-nov) ya no se ven: los dos van dentro de «Plantillas», en la barra del Inicio
            self.chip_editar.hide()
            self.chip_render.hide()

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
            r = self._popup("«%s» ya está armado en DaVinci.\n\n"
                            "•  Renderizar lo editado: saca los videos con lo que hayas cambiado a mano en DaVinci.\n\n"
                            "•  Volver a armar: lo arma de nuevo desde cero y reemplaza esas líneas "
                            "(se pierden los cambios hechos a mano)." % evento,
                            ("Renderizar lo editado", "Volver a armar", "Cancelar"), "pregunta",
                            titulo="Este evento ya está armado")
            return "editado" if r == 0 else "armar" if r == 1 else None

        def _editar_en_davinci(self, video=None, evento=None):
            """video (y su evento, si es de otro evento terminado): ya elegido en el popup de Plantillas."""
            if self.trabajo is not None:
                self._avisar("Espera a que termine: después podrás retocarlo en DaVinci.", "warn")
                return
            evento = evento or motor.leer_estado().get("evento")
            videos = [video] if video else motor.videos_editables(evento)
            if not videos:                       # eventos de antes, sin proyecto por video: la linea en EVENTOS CINEMA
                self._avisar("Abriendo DaVinci en la línea del evento…")
                qt_kit.correr_en_hilo(self, lambda: motor.abrir_editable(registro.info), self._editar_listo)
                return
            # (19-nov, la persona: «no me des tantas líneas de tiempo abiertas... ábreme solo la plantilla con la que
            # estoy trabajando») se elige el video y DaVinci abre SOLO su proyecto, con su unica linea
            elegidos = videos if video else self._elegir_de_videos(
                "¿Qué video editas?", "DaVinci guarda y cierra lo que tenga abierto y abre solo el proyecto de ese "
                "video, con su línea de tiempo en Edición.", videos, [videos[0]], False, "Abrir en DaVinci")
            if not elegidos:
                return
            video = elegidos[0]
            self._avisar("Abriendo en DaVinci solo «%s»…" % video)
            qt_kit.correr_en_hilo(self, lambda: motor.abrir_video_editable(registro.info, video, evento),
                                  self._editar_listo)

        def _elegir_de_videos(self, titulo, texto, videos, marcados, varios, boton, etiquetas=None):
            """(19-nov) Popup con una pastilla por video («1 min», «Vertical 1 min»...). varios=False: uno solo.
            Devuelve la lista elegida ([] = cancelar). Con varios botones (tupla): (numero del boton, lista)."""
            def etiqueta(v):                     # etiquetas: {valor: texto} (Plantillas de varios eventos)
                return (etiquetas or {}).get(v) or self._etiqueta_video(v)
            qml = getattr(self, "popup_qml", None)
            if qml is not None and not qml.abierto():      # (1.7) en QML: una pastilla por video
                botones = boton if isinstance(boton, tuple) else (boton, "Cancelar")
                r, res = qml.preguntar(titulo, texto, botones, "pregunta", 0, None, "videos",
                                       {"videos": [[v, etiqueta(v)] for v in videos], "varios": bool(varios),
                                        "elegidos": [v for v in videos if v in marcados]})
                lista = [v for v in videos if v in (res.get("elegidos") or [])]
                if isinstance(boton, tuple):
                    return r, lista
                return lista if r == 0 else []
            px = piezas.px
            elegir = QWidget()
            g = QGridLayout(elegir)
            g.setContentsMargins(0, 0, 0, 0)
            g.setSpacing(px(10))
            elegir.setStyleSheet(                # el popup pone su propio estilo a los botones: aqui el de elegir
                "QPushButton { font-size: %dpx; font-weight: 500; color: #E3EBED; padding: %dpx %dpx;"
                " background: rgba(255,255,255,0.04); border: 1px solid rgba(226,176,79,0.45); border-radius: %dpx; }"
                "QPushButton:hover { background: rgba(255,255,255,0.10); }"
                "QPushButton:checked { background: #1FA971; color: #FFFFFF; border: 1px solid #44D894; }"
                % (px(26), px(14), px(26), px(30)))
            grupo = QButtonGroup(elegir)
            grupo.setExclusive(not varios)
            for i, v in enumerate(videos):
                b = QPushButton(etiqueta(v), checkable=True)
                b.setMinimumWidth(px(250))
                b.setCursor(Qt.PointingHandCursor)
                b.setChecked(v in marcados)
                grupo.addButton(b, i)
                g.addWidget(b, i // 3, i % 3)
            botones = boton if isinstance(boton, tuple) else (boton, "Cancelar")
            r = piezas.preguntar(self, titulo, texto, botones, "pregunta", 0, contenido=elegir)
            lista = [videos[i] for i, b in enumerate(grupo.buttons()) if b.isChecked()]
            if isinstance(boton, tuple):
                return r, lista
            return lista if r == 0 else []

        def _editar_listo(self, nombre, error):
            if error is not None:
                self._avisar("No pude abrirlo en DaVinci: %s" % error, "warn")
            else:
                self._avisar("DaVinci quedó en Edición con «%s». Retoca lo que quieras y pulsa "
                             "«Renderizar lo editado»." % nombre)

        def _renderizar_editado(self, elegidos=None, evento_elegido=None):
            """Saca de nuevo los videos con las lineas tal como estan en DaVinci (sin volver a armar). elegidos: ya
            marcados en el popup de Plantillas (si no, se pregunta); evento_elegido: si son de otro evento terminado."""
            if self.trabajo is not None:
                self.b_log.setChecked(True)
                return
            if self.copia is not None:
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            est = motor.leer_estado()
            evento = evento_elegido or est.get("evento")
            if not evento:
                self._avisar("Todavía no hay ningún evento armado: pulsa ▶ primero.", "warn")
                return
            op = {"evento": evento}
            videos = motor.videos_editables(evento)
            if elegidos:
                op["videos"] = list(elegidos)
            elif videos:                 # (19-nov) cuales se sacan de nuevo: marcados los que se abrieron para editar
                abiertos = [v for v in est.get("editando") or [] if v in videos
                            and est.get("editando_evento") in (None, evento)]
                op["videos"] = self._elegir_de_videos(
                    "¿Qué videos sacas de nuevo?", "Cada uno sale desde su proyecto de DaVinci, con lo que retocaste "
                    "y el audio a -14 LUFS. No se vuelve a armar nada.", videos, abiertos or videos[:1], True,
                    "Renderizar")
                if not op["videos"]:
                    return
            self._arrancar(op, True, "Renderizando lo editado de %s (sin volver a armar)…" % evento,
                           motor.renderizar_editado)
            self._marcar("sfx", "activo")                 # el armado no corre: directo al render

        def _play(self, auto=False):
            # (18-nov) cada ▶/«Empezar» queda en el registro con el motivo si no arranca: antes un clic que no hacia
            # nada no dejaba rastro y no se sabia si llego el clic o si se freno aqui
            registro.info("▶ pulsado%s" % (" (solo)" if auto else ""))

            def no_arranca(motivo):
                registro.info("▶ no arranca: %s" % motivo)
            if self.trabajo is not None:
                no_arranca("ya esta trabajando")
                self.b_log.setChecked(True)
                return
            if self.copia is not None:
                no_arranca("todavia copia material")
                self._avisar("Espera a que termine de copiar el material.", "warn")
                return
            self._revisar_material()
            if not self.material["ok"]:
                no_arranca("falta material (%s)" % (self.material.get("falta") or self.material.get("motivo") or "?"))
                self._avisar("Falta material: suelta la carpeta del evento y vuelve a pulsar ▶.", "warn")
                self._pedir_material()
                return
            if self.flujo is not None and not auto:       # (1.6.0) aun mira lo ultimo que se solto
                no_arranca("aun mira la carpeta soltada")
                self._avisar("Espera un momento: termino de mirar la carpeta que soltaste.", "warn")
                return
            if not auto and self._falta_datos and not self.e_nombre.text().strip():
                no_arranca("faltan los nombres: se piden")
                self._falta_datos = False                 # (1.6.0) evento nuevo: de quien es, y a armar
                self._pedir_datos(self.l_copia.text() or "Material listo.")
                return
            self._falta_datos = False
            self._cola_soltar = []
            if not auto:                                  # ya armado con este material: ¿lo editado o desde cero?
                armado = self._ya_armado()
                if armado:
                    que = self._preguntar_ya_armado(armado)
                    registro.info("▶ ya armado: la persona eligio %s" % (que or "cancelar"))
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
                    if not self._si("Quedan %.1f GB libres en el disco donde quedan los videos y el render necesita unos "
                                    "%.1f GB.\n\nLibera espacio, o arma solo en DaVinci y renderiza después."
                                    % (libre, necesita), "Armar sin renderizar", "Cancelar", "aviso",
                                    titulo="Falta espacio en el disco"):
                        self._avisar("Sin espacio para renderizar: libera espacio y vuelve a pulsar ▶.", "warn")
                        return
                    op["render"] = False
            self._arrancar(op, bool(op.get("render", True)), "Armando %s…" % self._texto_versiones())
            if self.analisis is not None:
                self._avisar("Termino de analizar el material y sigo solo…")

        def _arrancar(self, op, con_render, texto, funcion=None):
            """Pone la ventana a trabajar y lanza el hilo: armar todo (funcion=None) o renderizar lo editado.
            (1.8.0, auditoria) Protegido: si algo falla al preparar la vista, la ventana no se queda en «Trabajando…»
            con las pastillas apagadas."""
            try:
                self._arrancar_vista(op, con_render, texto, funcion)
            except Exception as ex:
                registro.error("Arrancar: %s" % traceback.format_exc())
                t = getattr(self, "trabajo", None)
                if t is not None and t.isRunning():
                    return                               # el hilo ya corre: el fallo fue despues, al terminar de pintar
                self.trabajo = None
                self._fallo(str(ex))
                self._liberar()

        def _arrancar_vista(self, op, con_render, texto, funcion=None):
            self.registro.clear()
            self._en_espera = False                      # (1.6.0) ya dio la orden: se acaba la sala de espera
            self.sala.poner([])
            self.chip_videos.hide()
            self._chips_editable(False)
            self._con_render = con_render
            self.pasos_go = {k: "pendiente" for k, _ in PASOS_GO}
            self._prog = 0.0
            self.boton.poner_estado("trabajando", centro="Preparando")
            self.boton.poner_progreso(0.0)
            self.escena.empezar()
            self._marcar("timeline", "activo")
            # (1.6.0) en vez del panel de abajo: la fila de pasos y el avance de cada version
            rutas.PARAR.clear()
            self.dock.hide()
            for a in self.adornos:
                a.hide()
            self.pasos.reiniciar()
            self.pasos.poner("analizar", "activo")
            if funcion is None:
                vers = self._versiones() + ["VERTICAL " + x for x in self._versiones_v()]
                # (19-nov, prueba real: salian 6 videos y solo se veia «1 min») tambien las plantillas marcadas; el
                # VERTICAL 1 min automatico entra cuando el armado lo anuncia (_versiones_vista)
                hay = {i.get("nombre") for i in getattr(self.plantillas, "infos", [])}
                vers += [n for n in sorted(self.plantillas.marcadas) if n in hay]
            elif op.get("videos"):                   # (19-nov) solo los videos elegidos (los demas no salen en rojo)
                vers = [motor.rutas.etiqueta_de("%s - %s" % (op["evento"], v)) for v in op["videos"]]
            else:                                    # renderizar lo editado: las lineas del evento (estado de AHORA)
                vers = [motor.rutas.etiqueta_de(t) for t in motor.leer_estado().get("timelines") or []]
            self.versiones.poner_versiones(vers)
            self.versiones.poner_eta("")
            if vers:
                self.versiones.poner(vers[0], "armando", "Armando…" if funcion is None else "En cola")
            self.panel_trabajo.show()
            if self.trabajo_qml is not None:          # (1.7) en QML aparecen solos (un efecto de Qt no le llega)
                self.trabajo_qml.entrar()
            else:
                import animacion
                animacion.aparecer(self.panel_trabajo, 450)  # (1.6.0) los pasos y las versiones aparecen suaves
            self.sub.hide()                          # la maqueta: solo «Trabajando…», los pasos y las versiones
            self.titulo.tam = 86
            self._clips = {}
            self._acomodar()
            self.titulo.setText("Trabajando…")
            self._sub("Empezando…")
            self._estado("Trabajando", "oro", texto)
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
            # (1.8.0, auditoria) «Listo a las» solo se recalculaba cuando llegaba avance: mientras DaVinci abria o
            # renderizaba el de 30 min se quedaba viejo (decia 14:05 a las 14:20). Cada 20 s se vuelve a calcular
            if getattr(self, "_reloj_eta", None) is None:
                self._reloj_eta = QTimer(self)
                self._reloj_eta.setInterval(20000)
                self._reloj_eta.timeout.connect(lambda: self._poner_eta(self._prog))
            self._reloj_eta.start()

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
            if resto < 60:                               # (1.8.0) nunca una hora que ya paso
                self.versiones.poner_eta("Terminando…")
                return
            fin = time.strftime("%H:%M", time.localtime(time.time() + resto))
            self.versiones.poner_eta("Listo a las <b>%s</b>  ·  <span style='color:%s;'>faltan %s</span>" % (
                fin, TENUE, motor.texto_tiempo(resto).split(" (")[0].replace("unos ", "")))

        def _paso_vista(self, texto):
            """(1.6.0) La fila de pasos avanza con lo que va diciendo el trabajo (nunca hacia atras)."""
            orden = [c for c, _ in PASOS_VISTA]
            actual = self.pasos.activo()
            for clave_txt, paso in ETAPAS_VISTA:
                if clave_txt in texto:
                    if actual is None or orden.index(paso) > orden.index(actual):
                        self.pasos.poner(paso, "activo")
                    return

        def _agregar_version(self, etq):
            """Una fila mas en el avance, sin perder lo que ya muestran las otras."""
            antes = [(e, f.estado, f.texto, f.pct, f.detalle) for e, f in self.versiones.filas.items()]
            b = self.versiones.b_cancelar
            cancelar = (b.isEnabled(), b.text())         # poner_versiones lo deja en «Cancelar»
            orden = [e for e, *_ in antes]
            # los tráilers juntos (el vertical despues de los horizontales) y las plantillas al final
            pos = max([i + 1 for i, e in enumerate(orden) if re.search(r"\d+min$", e)] or [0])
            self.versiones.poner_versiones(orden[:pos] + [etq] + orden[pos:])
            for e, estado, texto, pct, detalle in antes:
                self.versiones.poner(e, estado, texto, pct, detalle)
            b.setEnabled(cancelar[0])
            b.setText(cancelar[1])
            self._acomodar()

        def _versiones_vista(self, m):
            """(1.6.0) El estado de cada version: «1min lista» al armarse; en el render, «1min Rendering 45%»."""
            filas = self.versiones.filas
            # (19-nov) el VERTICAL 1 min que el armado agrega solo (hay videos verticales): su fila, al anunciarlo
            if "se arma tambien el VERTICAL 1 min" in m and "VERTICAL 1min" not in filas:
                self._agregar_version("VERTICAL 1min")
                filas = self.versiones.filas
            a = re.search(r"\b((?:VERTICAL )?\d+min) lista", m)
            b = re.search(r"VIDEO FINAL (VERTICAL |HORIZONTAL )?(\d+) MIN lista", m, re.I)    # nombre de linea de la 1.5.7
            etq = a.group(1) if a else (("VERTICAL " if (b.group(1) or "").upper().startswith("V") else "") + b.group(2)
                                        + "min") if b else None
            if etq is None:                          # (19-nov) las plantillas: «XV 2026-11-08 - PLANTILLA 1 lista: ...»
                etq = next((e for e in filas if re.search(r"(^|- )%s lista\b" % re.escape(e), m)), None)
            if etq in filas:
                n = re.search(r"lista: (\d+) (?:clips|planos)", m)  # «plano 87 de 140» en el render
                if n:
                    self._clips[etq] = int(n.group(1))
                filas[etq].poner("armada", "Armada")
                sig = next((e for e, f in filas.items() if f.estado == "cola"), None)
                if sig and not re.search(r"\b\d+min \w+ \d+%", m):
                    filas[sig].poner("armando", "Armando…")
                return
            # la cola de render: «  95 s  1min Rendering 45% | PLANTILLA 1 Ready 0% | ...» (cada parte, su fila)
            render = []
            for parte in m.split(" | "):
                r = re.match(r"^\s*(?:\d+ s\s+)?(.+?) (\w+) (\d+)%\s*$", parte)
                if r:
                    render.append(r.groups())
            for etq, estado, pct in render:
                f = filas.get(etq)
                if f is None:
                    continue
                if estado == "Complete":
                    f.poner("listo", "Listo", 1.0)
                elif estado in ("Failed", "Cancelled"):
                    f.poner("error", "No se pudo renderizar")
                elif estado == "Rendering":
                    clips = getattr(self, "_clips", {}).get(etq)
                    f.poner("render", "%s%%" % pct, int(pct) / 100.0,
                            "plano %d de %d" % (max(1, round(int(pct) / 100.0 * clips)), clips) if clips else "")
                else:
                    f.poner("cola", "En cola")

        def _linea(self, m):
            self.registro.appendPlainText(m)
            registro.info(m)
            self._paso_vista(m)
            self._versiones_vista(m)
            a = re.match(r"\s+(\d+)/(\d+)\s+(\S.*)$", m)         # avance del analisis: «  12/65  DSC_0012.MP4»
            if a and int(a.group(2)) > 0 and self._prog < 0.12:
                i, n = int(a.group(1)), int(a.group(2))
                self._poner_prog(0.03 + 0.08 * i / float(n))
                self._sub("Analizando %d de %d · %s" % (i, n, a.group(3)[:40]))
                return
            if m.startswith("Esperando a"):              # (1.8.0) DaVinci tarda en abrir / una copia sigue: que se vea
                self._sub(m)
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
            self._paso_vista(texto)
            self._poner_prog(pct / 100.0)
            self._sub(texto + "…")

        def _cancelar(self):
            """(1.6.0) «Cancelar»: lo ya armado queda en DaVinci; el trabajo se corta en el paso que va (el render se
            detiene en DaVinci)."""
            if self.trabajo is None:
                return
            si = self._si("¿Cancelar el trabajo?\n\nLo que ya quedó armado en DaVinci se "
                          "queda ahí; lo demás se detiene en el paso que va.", "Cancelar el trabajo", "Seguir", "aviso")
            if not si or self.trabajo is None:
                return
            rutas.PARAR.set()
            self.versiones.b_cancelar.setEnabled(False)
            self.versiones.b_cancelar.setText("Cancelando…")
            self._sub("Cancelando: termina lo que está haciendo en este momento…")

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
            return None                              # (1.6.0) sin la barra de la escena: el avance va en self.versiones
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
            """Termino el trabajo (o la escena guardo sus etiquetas): vuelve el panel de abajo."""
            if self.boton.estado != "trabajando" and self.trabajo is None:
                self.panel_trabajo.hide()
                for a in self.adornos:
                    a.show()
                self.titulo.tam = 100
                self.titulo.setText(self.titulo.text())
                self.sub.setVisible(bool(self.sub.text()))
                self.dock.show()
                import animacion
                animacion.aparecer(self.dock, 450)
                self._ver_formato(self.seg_formato.actual())
                self._sub_material()
                self._acomodar()

        def _acomodar(self):
            """El tamano del astrolabio sigue al espacio libre (como en CineCaptions)."""
            if hasattr(self, "escena"):
                self.escena.setGeometry(self.cielo.rect())
            if hasattr(self, "hoja") and self.hoja.isVisible():
                self.hoja.setGeometry(self.cielo.rect())
            pag = self.paginas.widget(0)
            libre = self.hueco_boton.height() - 4
            self.boton.poner_lado(int(max(160, min(libre, pag.width() * 0.42))))     # (1.6.0) el astrolabio
            self._centrar_boton()
            self._escalar_luego()
            if hasattr(self, "gota_tabs"):           # (1.7.9) la gota, en su pestaña ya acomodada
                QTimer.singleShot(0, self.gota_tabs._recolocar)

        def _centrar_boton(self):
            h = self.hueco_boton
            self.boton.move(max(0, (h.width() - self.boton.width()) // 2), max(0, (h.height() - self.boton.height()) // 2))

        def _pagina(self, i):
            en_inicio = i == 0
            # (1.6.0, la maqueta) la escena de particulas ya no se ve: el astrolabio es la imagen de Higgsfield
            self.escena.setVisible(False)
            self.escena.activar(False)
            self.cielo.pausar(False)
            if en_inicio:
                self._acomodar()

        def _escalar_luego(self):
            """(1.6.0) Al cambiar de tamaño, todo sigue a la maqueta: medidas y letras por ancho / 2048 (en un rato,
            cuando se suelta el borde: re-aplicar el estilo a toda la ventana cuesta)."""
            if not hasattr(self, "t_escala"):
                self.t_escala = QTimer(self, singleShot=True, interval=350)
                self.t_escala.timeout.connect(self._escalar)
            self.t_escala.start()

        def _escalar(self):
            s = max(0.5, min(1.0, min(self.width() / 2048.0, self.height() / 1300.0)))
            if abs(s - piezas.ESCALA) < 0.015:
                return
            QApplication.instance().setStyleSheet(estilo_completo(s))
            for w in self.findChildren(QWidget):
                if hasattr(w, "reescalar"):
                    w.reescalar()
            for q in [getattr(self, "barra_qml", None), getattr(self, "trabajo_qml", None)] + \
                    list((getattr(self, "paginas_qml", None) or {}).values()):
                if q is not None:                    # (1.7) las piezas en QML no son widgets propios
                    q.reescalar()
            self.b_logo.setIconSize(QSize(piezas.px(72), piezas.px(72)))
            self._estado(self.b_log.text(), self.b_log.property("tipo") or "ok")
            self.b_log.setIconSize(QSize(piezas.px(24), piezas.px(24)))
            self._sin_recorte()
            self._brillos()                          # los radios del estilo cambiaron con la escala
            self._acomodar()

        def _sin_recorte(self):
            """(1.6.1) Pestañas y pastillas con sitio para su texto en negrita (piezas.sin_recorte)."""
            piezas.sin_recorte(list(self.tabs.values()))
            if hasattr(self, "gota_tabs"):
                self._igualar_tabs()                 # (1.7.9) y las 4 del mismo ancho
            for p in self.findChildren(piezas.Pastillas):
                piezas.sin_recorte(p.botones)

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
                # (18-nov) el Inicio pedia 470 fijos y su panel (fotos/videos/dron, 1-30 min, «Listo a las») quedaba
                # cortado: ahora pide lo que de verdad necesita
                pide = pag.widget().minimumSizeHint().width() if scroll else max(470, pag.sizeHint().width())
                libre = self._medio.geometry().width() - pide - max(0, self._medio.spacing())
                self.registro.setFixedWidth(max(260, min(400, libre)))
                # en el Inicio no hay desplazamiento: si el panel no cabe junto al registro, el registro se aparta
                # (el error ya sale en la barra de arriba) y vuelve en las otras pestañas o con la ventana mas ancha
                self.registro.setVisible(scroll or libre >= 260)
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
            for c, _ in PASOS_VISTA:                   # (1.6.0) la fila de pasos y cada version, al final
                if self.pasos.estado.get(c) in ("pendiente", "activo") and (videos or c in ("analizar", "ia", "armar")):
                    self.pasos.poner(c, "hecho")
                elif self.pasos.estado.get(c) == "activo":         # sin videos (solo armar): no quedo a medias
                    self.pasos.poner(c, "pendiente")
            hechos = {motor.rutas.etiqueta_de(n) for n, si, _ in videos if si}
            for etq, f in self.versiones.filas.items():
                if videos:
                    f.poner("listo", "Listo", 1.0) if etq in hechos else f.poner("error", "No salió")
                elif f.estado in ("armada", "armando", "cola"):
                    f.poner("listo", "Armada en DaVinci", 1.0)
            self.versiones.b_cancelar.setEnabled(False)
            self.versiones.poner_eta("Terminado a las <b>%s</b>" % time.strftime("%H:%M"))
            self._estado("Todo listo" if bien else "Revisa los videos", "ok" if bien else "warn")

            def cerrar():
                self.escena.terminar(bien, "ok" if bien else "aviso")
                self.boton.poner_estado("hecho", centro="", tono="ok" if bien else "aviso")
            cerrar()                                   # (1.6.0) sin la explosion de la escena (ya no se ve)
            self.titulo.setText("¡Listo!")
            if videos:
                self._sub("%d de %d videos en «%s»" % (len(ok), len(videos), os.path.basename(
                    rutas.carpeta_terminado(self.resultado.get("evento", "")))),
                          "ok" if len(ok) == len(videos) else "error")
                self._avisar("Terminado: %d videos con audio a -14 LUFS%s." % (
                    len(ok), " (con lo que editaste en DaVinci)" if self.resultado.get("editado") else ""))
                self.chip_videos.show()
                self._abrir_videos()
                # (19-nov) sin IntelliSearch al final: DaVinci queda en el proyecto del video y el indexado lo sacaba
                # de ahi a EVENTOS CINEMA a los 4 s (las caras ya las reconoce la IA propia al analizar)
            else:
                self._sub("Armado en DaVinci · %s" % self.resultado.get("evento", ""), "ok")
                self._avisar("Timelines armadas en DaVinci (sin render).")
            for a in (self.resultado.get("avisos") or [])[:3]:        # lo que el formato vertical no pudo armar
                self._avisar(a, "warn")
            if not self.resultado.get("editado") and videos:
                self._avisar("Cada video quedó en su propio proyecto de DaVinci (una sola línea). Pulsa «Editar en "
                             "DaVinci», elige el video y, si retocas algo, «Renderizar lo editado».")
            self._chips_editable()                   # (19-nov) solo si el evento quedo terminado (con sus videos)

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
            vista = self.pasos.activo()
            if vista:
                self.pasos.poner(vista, "error")
            for f in self.versiones.filas.values():
                if f.estado in ("armando", "render"):
                    f.poner("error", "Cancelado" if texto == CANCELADO else "Se detuvo")
            self.versiones.b_cancelar.setEnabled(False)
            self._ultimo_fallo = texto
            self.titulo.setText(TITULO_INICIO)
            if texto == CANCELADO:                     # (1.6.0) lo pidio la persona: no es un error
                self.escena.terminar(False, "aviso")
                self.boton.poner_estado("error", centro="Cancelado")
                self._sub("Cancelado: lo que ya quedó armado sigue en DaVinci.")
                self._estado("Cancelado", "warn")
                self._avisar("Trabajo cancelado. Lo que ya quedó armado sigue en DaVinci.", "warn")
                return
            self.escena.terminar(False, "ok")
            self.boton.poner_estado("error", centro="Error")
            self._sub("No se pudo terminar: %s" % texto, "error")
            self._estado("Error", "error", texto)
            self._avisar("Error: %s" % texto, "error")
            self.b_log.setChecked(True)

        def _liberar(self):
            self.trabajo = None
            if getattr(self, "_reloj_eta", None) is not None:
                self._reloj_eta.stop()
            self._chips_editable()
            self._cargar_organizacion()
            for b in self._pastillas(True):
                b.setEnabled(True)
            rutas.PARAR.clear()
            QTimer.singleShot(6000, lambda: self.titulo.setText(TITULO_INICIO) if self.trabajo is None else None)
            QTimer.singleShot(7000, self._quitar_reserva)      # vuelve el panel de abajo (si la escena no avisa antes)

        def _abrir_videos(self):
            rutas.abrir((self.resultado or {}).get("carpeta") or rutas.SALIDA)

        def _clasificacion(self):
            if os.path.exists(rutas.CLASIFICACION):
                rutas.abrir(rutas.CLASIFICACION)
            else:
                self._popup("Se crea sola la primera vez que armas un evento.", titulo="Todavía no hay clasificación")

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

        def _ver_canciones(self, n):
            """Doble clic en un estilo de Música: sus canciones, para verlas y oírlas (vistas_ajustes.ListaCanciones)."""
            import vistas_ajustes
            estilos = self.estilos_musica
            if n == 0:                                   # Auto: el que le toca al tipo de evento
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("musica_propia", rutas.codigo("musica_propia.py"))
                    mp = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mp)
                    quiero = mp.POR_TIPO.get(self.c_tipo.currentData() or "xv", "")
                except Exception:
                    quiero = ""
                carpeta = next((e for e in estilos if quiero and quiero in e.upper()), estilos[0] if estilos else None)
                titulo = "Auto: %s" % (carpeta or "").lstrip("0123456789 ").capitalize()
            elif n - 1 < len(estilos):
                carpeta = estilos[n - 1]
                titulo = "Música: %s" % carpeta.lstrip("0123456789 ").capitalize()
            else:
                self._popup("Plantilla\n\nUsa las canciones que trae la plantilla de DaVinci, sin cambiarlas. "
                            "No son del programa: revisa que puedas publicarlas en redes.")
                return
            if not carpeta:
                return
            lista = vistas_ajustes.ListaCanciones(os.path.join(rutas.RECURSOS, "musica", carpeta))
            try:
                piezas.preguntar(self, titulo, "", ("Cerrar",), "info", 0, contenido=lista)
            finally:
                vistas_ajustes.callar()

        def _ver_intro(self, n):
            """Doble clic en un tipo de Intro: las 8 fotos entrando con ese ritmo y su sonido (vistas_ajustes.VistaIntro)."""
            import vistas_ajustes
            ritmos = {"rampa": [5] * 8, "acelera": [9, 7, 6, 5, 4, 4, 3, 2], "frena": [2, 3, 4, 4, 5, 6, 7, 9],
                      "latido": [7, 3, 7, 3, 7, 3, 7, 3]}            # = build_trailers.INTROS
            tipo = self.intros[n] if 0 <= n < len(self.intros) else "rampa"
            fotos = []
            try:
                import analizar_material as am
                todas = [i["ruta"] for i in am.leer_ultimo().get("items") or []
                         if i.get("tipo") == "foto" and i.get("ruta") and not i.get("descartar") and os.path.isfile(i["ruta"])]
                if todas:
                    fotos = [todas[int(k * (len(todas) - 1) / 8.0)] for k in range(9)]
            except Exception:
                pass
            if not fotos:
                fondo = os.path.join(rutas.RECURSOS, "fondo_titulo.jpg")
                fotos = [fondo] if os.path.isfile(fondo) else []
            sfx = os.path.join(rutas.RECURSOS, "sfx", "XV_RAMPA%s.wav" % ("" if tipo == "rampa" else "_" + tipo.upper()))
            vista = vistas_ajustes.VistaIntro(ritmos.get(tipo, ritmos["rampa"]), fotos, sfx)
            textos = {"rampa": "Pareja: una foto cada 5 cuadros.", "acelera": "Empieza lenta y se dispara hasta el impacto.",
                      "frena": "Ráfaga que se va deteniendo en la última foto.", "latido": "De dos en dos, como un corazón."}
            try:
                piezas.preguntar(self, "Intro: %s" % tipo.capitalize(), textos.get(tipo, ""), ("Cerrar",), "info", 0,
                                 contenido=vista)
            finally:
                vistas_ajustes.callar()

        def eventFilter(self, obj, ev):
            t = ev.type()
            if t == QEvent.MouseButtonDblClick and obj in getattr(self, "_doble", {}):
                que, n = self._doble[obj]
                QTimer.singleShot(0, lambda: self._ver_canciones(n) if que == "musica" else self._ver_intro(n))
                return True
            if t == QEvent.ContextMenu and isinstance(obj, QLineEdit) and obj.window() is self:
                # (1.6.1) el menu del clic derecho de los cuadros de texto, en español (Qt lo trae en ingles y las
                # traducciones de Qt no van en el programa): Deshacer, Cortar, Copiar, Pegar…
                menu = obj.createStandardContextMenu()
                nombres = {"Undo": "Deshacer", "Redo": "Rehacer", "Cut": "Cortar", "Copy": "Copiar", "Paste": "Pegar",
                           "Delete": "Borrar", "Select All": "Seleccionar todo"}
                for a in menu.actions():
                    base, _, atajo = a.text().partition("\t")
                    es = nombres.get(base.replace("&", ""))
                    if es:
                        a.setText(es + ("\t" + atajo if atajo else ""))
                menu.setAttribute(Qt.WA_DeleteOnClose)
                menu.popup(ev.globalPos())
                return True
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
            vivo = self.trabajo is not None and self.trabajo.isRunning()
            if vivo and getattr(self, "_cerrando", False):
                e.ignore()                               # ya se esta deteniendo: se cierra solo al terminar
                return
            if self.trabajo is not None and not self._si(
                    "Si cierras ahora, el armado se detiene donde va.", "Cerrar", "Seguir trabajando", "aviso",
                    titulo="Todavía está trabajando"):
                e.ignore()
                return
            if vivo:
                # (1.8.0, auditoria) antes se cerraba con el hilo corriendo: el programa se caia («QThread destroyed»)
                # y DaVinci seguia renderizando. Ahora se pide parar (Cancelar detiene el render en DaVinci), se
                # espera al hilo y se cierra; si en 30 s no paro, se guarda y se sale igual
                self._cerrando = True
                rutas.PARAR.set()
                self._sub("Cerrando: detengo DaVinci…")
                self.trabajo.finished.connect(self.close)
                QTimer.singleShot(30000, self._cerrar_ya)
                e.ignore()
                return
            try:
                self._guardar()
            except Exception:
                pass
            pre = getattr(self, "preanalisis", None)
            if pre is not None and pre.isRunning():          # (1.8.2) el analisis previo se corta (lo hecho ya
                rutas.PARAR.set()                            # esta guardado por archivo) y se espera un poco
                if not pre.wait(5000):
                    registro.info("Cierre: el analisis previo no se detuvo en 5 s; salgo igual.")
                    os._exit(0)
            if self.actualizacion and not self._instalando:      # la version nueva ya bajada se instala al cerrar
                self._instalando = True
                self._lanzar_instalacion(reabrir=False)
            try:                                       # (1.6.0) los videos se paran antes de destruirse la ventana
                import animacion
                animacion.detener_todas()
            except Exception:
                pass
            e.accept()

        def _cerrar_ya(self):
            """El trabajo no se detuvo en 30 s (DaVinci no contesta): se guarda lo de la ventana y se sale."""
            if self.trabajo is None or not self.trabajo.isRunning():
                return
            registro.info("Cierre: el trabajo no se detuvo en 30 s; salgo igual.")
            try:
                self._guardar()
            except Exception:
                pass
            os._exit(0)

    if rutas.ES_WIN:
        try:
            import ctypes
            # el MISMO ID que llevan los accesos del Inicio y el Escritorio (Instalador.cs: AUMID); si no coinciden,
            # Windows no sabe abrirlo desde un icono anclado: «no puede encontrar cinemaproductions.trailer» (1.6.0)
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
        import escena_go, linea_dia, piezas, animacion  # noqa: F401   (1.6.0: boton_go ya no se usa)
    except Exception:
        pass
    _tiempo("modulos de la escena")
    # (1.6.0) Sin portada de Qt tampoco (ni en Windows ni en la Mac): la persona no quiere ningun cuadro al arrancar.
    # Lo de abajo queda por si se vuelve a pedir (PORTADA = True).
    portada = None
    try:
        if nativa or not PORTADA:
            raise RuntimeError("sin portada")
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
    if "--vigia" in args:                                   # (18-nov) el vigia de DaVinci: otro proceso, sin ventana
        import vigia_davinci
        vigia_davinci.principal(int(args[args.index("--vigia") + 1]))
        sys.exit(0)
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
