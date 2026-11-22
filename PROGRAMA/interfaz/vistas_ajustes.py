# -*- coding: utf-8 -*-
"""
vistas_ajustes.py - Lo que se abre con DOBLE CLIC en Ajustes > Sonido (18-nov).

La persona: «si doy doble click, que me salga el pop up con todas las canciones de cada música de estilo, y en las
intro igual: doble click me da el ejemplo de cómo se ve».

    ListaCanciones(carpeta)        las pistas de un estilo, cada una con su boton para oirla (un trozo)
    VistaIntro(cortes, fotos, sfx) las 8 fotos de la apertura entrando con ESE ritmo (y su efecto de sonido), en bucle
    sonar(ruta, desde, seg) / callar()

El sonido no usa QtMultimedia (no va en el instalador): ffmpeg saca un trozo a WAV en un hilo y lo toca winsound
(Windows) o afplay (Mac). Sin ffmpeg o sin sonido, las piezas siguen funcionando calladas.
"""
import os
import sys
import time
import shutil
import tempfile
import threading
import subprocess

from PySide6.QtCore import Qt, QRectF, QTimer, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QImageReader, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

import rutas
import piezas
from piezas import px

_sonando = {"n": 0, "proc": None}
PAPELES = {"INTRO": "apertura (con las fotos)", "ROMANTICA": "romántica (maquillaje, iglesia)", "FIESTA": "fiesta",
           "EPICA": "épica (final)"}


def _mci(orden):
    """Una orden al reproductor de Windows (MCI). Devuelve (codigo de error, respuesta)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(orden, buf, 255, None)
    return err, buf.value


def estado():
    """«playing» mientras suena (Windows); '' si no."""
    if os.name != "nt":
        return "playing" if _sonando["proc"] is not None and _sonando["proc"].poll() is None else ""
    try:
        return _mci("status trailer_oir mode")[1]
    except Exception:
        return ""


def callar():
    _sonando["n"] += 1
    try:
        if os.name == "nt":
            _mci("stop trailer_oir")
            _mci("close trailer_oir")
            import winsound
            winsound.PlaySound(None, 0)
        elif _sonando["proc"] is not None:
            _sonando["proc"].kill()
    except Exception:
        pass
    _sonando["proc"] = None


def sonar(ruta, desde=0.0, seg=25.0):
    """Toca un trozo del archivo sin trabar la ventana. Otra llamada o callar() lo corta.

    (18-nov, la persona en el instalado: «hay un error en el pop up, no me deja reproducir») En Windows lo toca el
    reproductor del sistema (MCI) directo del MP3 o WAV, desde el hilo de la ventana (son ordenes que vuelven al
    instante): no depende de ffmpeg ni de hilos. Si MCI no puede, queda el camino de antes (ffmpeg + winsound)."""
    callar()
    turno = _sonando["n"]
    if os.name == "nt":
        try:
            corto = ruta
            try:                                  # MCI no quiere rutas largas ni con caracteres raros: la corta (8.3)
                import ctypes
                b = ctypes.create_unicode_buffer(600)
                if ctypes.windll.kernel32.GetShortPathNameW(ruta, b, 600):
                    corto = b.value
            except Exception:
                pass
            err, _ = _mci('open "%s" type mpegvideo alias trailer_oir' % corto)
            if not err:
                _mci("set trailer_oir time format milliseconds")
                a = int(desde * 1000)
                err, _ = _mci("play trailer_oir from %d to %d" % (a, a + int(seg * 1000)))
                if err:                           # mas corta que el trozo pedido: entera
                    err, _ = _mci("play trailer_oir from 0")
                if not err:
                    return
            _mci("close trailer_oir")
        except Exception:
            pass

    def correr():
        try:
            if sys.platform == "darwin":
                _sonando["proc"] = subprocess.Popen(["afplay", "-t", "%.1f" % seg, ruta])
                return
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or os.name != "nt":
                return
            wav = os.path.join(tempfile.gettempdir(), "trailer_oir_%d.wav" % (turno % 4))
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.2f" % desde, "-t", "%.2f" % seg,
                            "-i", ruta, "-ac", "2", "-ar", "44100", wav], capture_output=True, timeout=60,
                           creationflags=rutas.SIN_VENTANA)
            if turno == _sonando["n"] and os.path.exists(wav):       # nadie pidio otra cosa mientras tanto
                import winsound
                winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=correr, daemon=True, name="oir").start()


def _papel(nombre):
    base = os.path.splitext(nombre)[0].upper()
    for k, v in PAPELES.items():
        if k in base:
            return v
    return ""


PAPEL_TXT = {"apertura": "Apertura", "romantica": "Romántica", "fiesta": "Fiesta", "epica": "Épica"}
GRUPO_TXT = {"VALS": "Vals", "FIESTA": "Fiesta", "MUSICA DE BODA": "Música de boda", "MUSICA DE XV": "Música de XV",
             "INSTRUMENTALES": "Instrumentales"}
_FUERA_TITULO = ("(official music video)", "[official music video]", "(video oficial)", "(official video)",
                 "(official audio)", "sub español", "karaoke♬")


def titulo_cancion(nombre):
    """El nombre para leer: «02 ROMANTICA C - A THOUSAND YEARS (VIOLIN).mp3» -> «A Thousand Years (Violin)»;
    «03 FIESTA CORTA.mp3» -> «Fiesta corta»; los de YouTube sin «(Official Music Video)» ni lo que va tras «｜»."""
    import re

    def mayuscula(w):                                      # «(VIOLIN)» -> «(Violin)», «XV» se queda
        if w in ("XV", "DJ", "II", "III"):
            return w
        i = next((k for k, c in enumerate(w) if c.isalpha()), None)
        return w if i is None else w[:i] + w[i].upper() + w[i + 1:].lower()
    base = os.path.splitext(os.path.basename(nombre))[0]
    m = re.match(r"^\d+\s+(INTRO|ROMANTICA|FIESTA|EPICA)\b\s*\S?\s*-\s+(.+)$", base, re.I)
    if m:
        base = m.group(2)
    elif re.match(r"^\d+\s+(INTRO|ROMANTICA|FIESTA|EPICA)\b", base, re.I):
        p = re.sub(r"^\d+\s+", "", base).split()
        primera = {"ROMANTICA": "Romántica", "EPICA": "Épica"}.get(p[0].upper(), p[0].capitalize())
        return " ".join([primera] + [w.upper() if len(w) == 1 else w.lower() for w in p[1:]])
    base = re.sub(r"@\S+", "", base.split("｜")[0])         # sin «@canal» de YouTube
    for x in _FUERA_TITULO:
        i = base.lower().find(x)
        if i >= 0:
            base = base[:i] + base[i + len(x):]
    base = re.sub(r"\s+", " ", base).strip(" -·")
    if base.isupper():                                     # TODO EN MAYUSCULAS -> Cada Palabra
        base = " ".join(mayuscula(w) for w in base.split())
    return base or nombre


class CancionesEstilo(QWidget):
    """(1.8.9, la persona: «si escojo el estilo de música me sale el pop up, pero si agrego otra canción o cambio
    alguna, que se pueda; ya te di las carpetas de música pero no lo veo ahí aún») El popup de un estilo de música:

      En este estilo   cada canción con su ▶ (un trozo), «Cambiar» y «Quitar»; las quitadas, con «Volver a poner»
      Tu música        las carpetas de música de la persona (recursos/musica/TU MUSICA), en grupos que se abren;
                       cada una con «Agregar» (y su parte: apertura, romántica, fiesta o épica) o «Usar esta» al cambiar
      Otra de la PC    cualquier archivo de audio

    Lo hace musica_propia (agregar / quitar / devolver): se guarda al momento y el armado lo usa. Una sola hoja de
    estilo para todo (antes una por boton: el popup tardaba 90 ms en abrir) y los grupos se arman al abrirlos."""

    def __init__(self, estilo, mp, ventana=None, parent=None):
        super().__init__(parent)
        self.estilo, self.mp, self.ventana = estilo, mp, ventana
        self._cambiando = None
        self._oyendo = None
        self._nueva = None
        self._abiertos = set()
        self.setObjectName("canciones")
        self.setStyleSheet(self._hoja())
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(px(16))
        self.aviso = QLabel(objectName="aviso")
        self.aviso.setWordWrap(True)
        self.aviso.setMaximumHeight(0)
        v.addWidget(self.aviso)
        from PySide6.QtWidgets import QScrollArea, QFrame
        self.scroll = QScrollArea(objectName="lista")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(self.scroll, 1)
        pie = QHBoxLayout()
        pie.setSpacing(px(18))
        self.b_pc = QPushButton("Otra canción de la PC…", objectName="accion")
        self.b_pc.setCursor(Qt.PointingHandCursor)
        self.b_pc.clicked.connect(self._de_la_pc)
        self.b_cancelar = QPushButton("No cambiar", objectName="accion")
        self.b_cancelar.setCursor(Qt.PointingHandCursor)
        self.b_cancelar.clicked.connect(lambda: self._modo_cambio(None))
        self.b_cancelar.hide()
        nota = QLabel("Clic en el botón verde para oír un trozo. Lo que cambies se guarda solo.", objectName="nota")
        nota.setWordWrap(True)
        pie.addWidget(self.b_pc)
        pie.addWidget(self.b_cancelar)
        pie.addWidget(nota, 1)
        v.addLayout(pie)
        # alto FIJO: el popup no crece despues de abrirse; al salir el aviso de «Cambiar» la lista le cede su sitio
        # (con un minimo para la lista el pie quedaba encima de la ultima fila)
        alto_v = ventana.height() if ventana is not None else 900
        # lo demas del popup (icono, titulo, «Listo» y margenes) se lleva ~px(640): en una ventana baja, menos lista
        self.setFixedHeight(max(px(300), min(int(alto_v * 0.56), alto_v - px(640) - 40, px(1050))))
        self.scroll.setMinimumHeight(px(160))
        self.setMinimumWidth(px(1040))
        self._llenar()

    # ------------------------------------------------------------------ aspecto
    @staticmethod
    def _hoja():
        return (
            "QWidget#canciones, QScrollArea#lista, QWidget#cuerpo { background: transparent; border: none; }"
            "QFrame#fila { border-radius: %(r)dpx; border: 1px solid rgba(255,255,255,0.13);"
            " background: rgba(255,255,255,0.035); }"
            "QFrame#fila:hover { background: rgba(255,255,255,0.075); }"
            "QFrame#fila[estado=\"quitada\"] { background: transparent; border-style: dashed; }"
            "QFrame#fila[estado=\"nueva\"] { border: 1px solid #22C47E; background: rgba(34,196,126,0.16); }"
            "QFrame#fila[estado=\"cambiando\"] { border: 1px solid #E2B04F; background: rgba(226,176,79,0.12); }"
            "QLabel#titulo { font-size: %(f1)dpx; font-weight: 600; color: #F4F8F6; background: transparent; }"
            "QFrame#fila[estado=\"quitada\"] QLabel#titulo { color: #7E8E93; }"
            "QLabel#sub { font-size: %(f2)dpx; color: #9DB0B6; background: transparent; }"
            "QLabel#seccion { font-size: %(f3)dpx; font-weight: 700; color: #E2B04F; background: transparent;"
            " padding-top: %(p)dpx; }"
            "QLabel#nota { font-size: %(f2)dpx; color: #9DB0B6; }"
            "QLabel#aviso { font-size: %(f2)dpx; color: #F3D9A0; background: rgba(226,176,79,0.13);"
            " border: 1px solid rgba(226,176,79,0.55); border-radius: %(r)dpx; padding: %(p)dpx %(p2)dpx; }"
            "QPushButton#oir { padding: 0px; min-width: %(b)dpx; max-width: %(b)dpx; min-height: %(b)dpx;"
            " max-height: %(b)dpx; border-radius: %(br)dpx; border: 1px solid rgba(124,245,192,0.45); background: rgba(34,196,126,0.10); }"
            "QPushButton#oir:hover { background: rgba(34,196,126,0.22); }"
            "QPushButton#oir:checked { background: rgba(34,196,126,0.55); border-color: #7CF5C0; }"
            "QPushButton#accion, QPushButton#chip, QPushButton#chip_sugerido, QPushButton#accion_oro {"
            " padding: 0 %(p2)dpx; min-height: %(ba)dpx; border-radius: %(bar)dpx; font-size: %(f2)dpx;"
            " font-weight: 600; color: #EAF2EF; border: 1px solid rgba(255,255,255,0.22);"
            " background: rgba(255,255,255,0.04); }"
            "QPushButton#accion:hover, QPushButton#chip:hover { background: rgba(255,255,255,0.11); }"
            "QPushButton#chip_sugerido, QPushButton#accion_oro { color: #04150D; border-color: #22C47E;"
            " background: #22C47E; }"
            "QPushButton#chip_sugerido:hover, QPushButton#accion_oro:hover { background: #3EE09A; }"
            "QPushButton#grupo { text-align: left; padding: 0 %(p2)dpx; min-height: %(bg)dpx; border-radius: %(r)dpx;"
            " font-size: %(f1)dpx; font-weight: 600; color: #EAF2EF; border: 1px solid rgba(226,176,79,0.30);"
            " background: rgba(226,176,79,0.06); }"
            "QPushButton#grupo:hover { background: rgba(226,176,79,0.14); }"
            % {"r": px(16), "f1": px(29), "f2": px(24), "f3": px(25), "p": px(10), "p2": px(24), "b": px(58),
               "br": px(29), "ba": px(54), "bar": px(27), "bg": px(66)})

    @staticmethod
    def _repulir(w, **props):
        for k, val in props.items():
            w.setProperty(k, val)
        for x in [w] + w.findChildren(QLabel):
            x.style().unpolish(x)
            x.style().polish(x)

    # ------------------------------------------------------------------ armar la lista
    def _llenar(self, enfocar=None):
        """(Re)hace la lista: las del estilo y los grupos de «Tu música» (cerrados, salvo los que estaban abiertos)."""
        callar()
        self._oyendo = None
        viejo = self.scroll.takeWidget()
        if viejo is not None:
            viejo.deleteLater()
        cuerpo = QWidget(objectName="cuerpo")
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(0, 0, px(14), 0)
        lay.setSpacing(px(10))
        pistas = self.mp.pistas(self.estilo)
        activas = [p for p in pistas if not p["quitada"]]
        # las que ya estan (por su titulo): en «Tu música» dicen «Ya está» en vez de «Agregar» (no se duplican)
        self._ya = {titulo_cancion(p["nombre"]).lower() for p in activas}
        lay.addWidget(QLabel("En este estilo  ·  %d canciones" % len(activas), objectName="seccion"))
        foco = None
        orden = {"apertura": 0, "romantica": 1, "fiesta": 2, "epica": 3}
        for p in sorted(pistas, key=lambda x: (x["quitada"], orden.get(x["papel"], 9), titulo_cancion(x["nombre"]))):
            sub = PAPEL_TXT.get(p["papel"], "")
            if p["propia"]:
                sub += "  ·  agregada por ti"
            if p.get("volvio"):
                sub += "  ·  vuelve: es la única de su parte"
            if p["quitada"]:
                fila = self._fila(titulo_cancion(p["nombre"]), "Quitada  ·  " + sub, p["ruta"],
                                  [("Volver a poner", "accion", lambda _=False, n=p["nombre"]: self._devolver(n))],
                                  estado="quitada")
            else:
                fila = self._fila(titulo_cancion(p["nombre"]), sub, p["ruta"],
                                  [("Cambiar", "accion", lambda _=False, x=p: self._modo_cambio(x)),
                                   ("Quitar", "accion", lambda _=False, x=p: self._quitar(x))],
                                  estado="cambiando" if self._cambiando and self._cambiando["ruta"] == p["ruta"] else "")
            if enfocar and p["ruta"] == enfocar:
                foco = fila
            lay.addWidget(fila)
        bib = self.mp.biblioteca()
        if bib:
            lay.addWidget(QLabel("Tu música  ·  tus carpetas, ya dentro del programa", objectName="seccion"))
            for grupo, rutas_g in bib:
                lay.addWidget(self._grupo(grupo, rutas_g))
        lay.addStretch(1)
        self.scroll.setWidget(cuerpo)
        if foco is not None:
            self._resaltar(foco)

    def _fila(self, titulo, sub, ruta, botones, estado=""):
        from PySide6.QtWidgets import QFrame
        f = QFrame(objectName="fila")
        f.setProperty("estado", estado)
        h = QHBoxLayout(f)
        h.setContentsMargins(px(16), px(10), px(16), px(10))
        h.setSpacing(px(18))
        if ruta:
            oir = QPushButton(objectName="oir", checkable=True)
            oir.setCursor(Qt.PointingHandCursor)
            oir.setIcon(_icono_play())
            oir.setIconSize(QSize(px(26), px(26)))
            oir.setFixedSize(px(58), px(58))          # (el estilo general de los botones lo estiraba a lo ancho)
            oir.setToolTip("Oír un trozo")
            oir.toggled.connect(lambda si, b=oir, r=ruta: self._oir(b, r, si))
            h.addWidget(oir)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        t = QLabel(titulo, objectName="titulo")
        t.setToolTip(os.path.basename(ruta) if ruta else "")
        t.setWordWrap(True)                            # un titulo largo no ensancha la lista (tapaba los botones)
        textos.addWidget(t)
        if sub:
            s = QLabel(sub, objectName="sub")
            s.setWordWrap(True)
            textos.addWidget(s)
        h.addLayout(textos, 1)
        f._botones = QHBoxLayout()
        f._botones.setSpacing(px(12))
        h.addLayout(f._botones)
        self._poner_botones(f, botones)
        return f

    @staticmethod
    def _poner_botones(fila, botones):
        while fila._botones.count():
            w = fila._botones.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for texto, nombre, fn in botones:
            b = QPushButton(texto, objectName=nombre)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            fila._botones.addWidget(b)

    def _grupo(self, grupo, rutas_g):
        """Un grupo de «Tu música»: el boton que lo abre y, al abrirlo, sus canciones (se arman en ese momento)."""
        caja = QWidget()
        v = QVBoxLayout(caja)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(px(10))
        nombre = GRUPO_TXT.get(grupo, grupo.capitalize())
        b = QPushButton(objectName="grupo")
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(piezas.qicono("nota", "#E2B04F", px(30)))
        b.setIconSize(QSize(px(30), px(30)))
        v.addWidget(b)
        cont = QWidget()
        cv = QVBoxLayout(cont)
        cv.setContentsMargins(px(30), 0, 0, 0)
        cv.setSpacing(px(10))
        v.addWidget(cont)

        def texto():
            b.setText("   %s  ·  %d canciones%s" % (nombre, len(rutas_g),
                                                    "  ·  ocultar" if grupo in self._abiertos else "  ·  ver"))

        def abrir(animar=True):
            if not cont.property("lleno"):
                for r in rutas_g:
                    cv.addWidget(self._fila_biblioteca(r))
                cont.setProperty("lleno", True)
            cont.show()
            if animar:
                _abrir_alto(cont)

        def alternar():
            if grupo in self._abiertos:
                self._abiertos.discard(grupo)
                cont.hide()
            else:
                self._abiertos.add(grupo)
                abrir()
            texto()
        b.clicked.connect(alternar)
        if grupo in self._abiertos:
            abrir(animar=False)
        else:
            cont.hide()
        texto()
        return caja

    def _fila_biblioteca(self, ruta):
        f = self._fila(titulo_cancion(ruta), "", ruta, [])
        self._botones_biblioteca(f, ruta)
        return f

    def _botones_biblioteca(self, fila, ruta):
        if titulo_cancion(ruta).lower() in getattr(self, "_ya", set()):
            ya = QLabel("Ya está en este estilo", objectName="sub")
            fila._botones.addWidget(ya)
        elif self._cambiando is not None:
            self._poner_botones(fila, [("Usar esta", "accion_oro", lambda _=False: self._usar(ruta))])
        else:
            self._poner_botones(fila, [("Agregar", "accion", lambda _=False: self._elegir_papel(fila, ruta))])

    def _elegir_papel(self, fila, ruta):
        """«Agregar»: aparecen las 4 partes, con la sugerida en verde; un clic la agrega a este estilo."""
        sug = self.mp.papel_sugerido(ruta)
        self._poner_botones(fila, [(PAPEL_TXT[p], "chip_sugerido" if p == sug else "chip",
                                    (lambda _=False, pp=p: self._agregar(ruta, pp)))
                                   for p in ("apertura", "romantica", "fiesta", "epica")])
        _aparecer(fila)

    # ------------------------------------------------------------------ acciones
    def _oir(self, boton, ruta, si):
        if si:
            if self._oyendo is not None and self._oyendo is not boton:
                try:
                    self._oyendo.blockSignals(True)
                    self._oyendo.setChecked(False)
                    self._oyendo.blockSignals(False)
                except RuntimeError:
                    pass
            self._oyendo = boton
            sonar(ruta, 0.0 if "INTRO" in os.path.basename(ruta).upper() else 12.0, 25.0)
        elif self._oyendo is boton:
            self._oyendo = None
            callar()

    def _agregar(self, ruta, papel, quitar=None):
        """Copia en un hilo (10 MB no deben trabar la ventana) y rehace la lista con la nueva resaltada."""
        import qt_kit
        estilo, mp = self.estilo, self.mp

        def trabajo():
            nueva = mp.agregar(estilo, ruta, papel)
            if quitar is not None:
                mp.quitar(estilo, quitar)
            return nueva

        def listo(nueva, error):
            if error is not None:
                self._avisar("No pude agregar «%s»: %s" % (titulo_cancion(ruta), error))
                return
            self._cambiando = None
            self._modo_cambio(None, rehacer=False)
            self._llenar(enfocar=nueva)
        qt_kit.correr_en_hilo(self, trabajo, listo)

    def _quitar(self, pista):
        try:
            self.mp.quitar(self.estilo, pista)
        except Exception as ex:
            self._avisar("No pude quitarla: %s" % ex)
            return
        self._llenar()

    def _devolver(self, nombre):
        self.mp.devolver(self.estilo, nombre)
        self._llenar(enfocar=os.path.join(self.mp.CARPETA, self.estilo, nombre))

    def _modo_cambio(self, pista, rehacer=True):
        """«Cambiar»: arriba el aviso de cual se cambia; en «Tu música» cada una dice «Usar esta» (y la de la PC)."""
        self._cambiando = pista
        if pista is not None:
            self.aviso.setText("Elige la canción que va en lugar de «%s» (%s): en «Tu música» pulsa «Usar esta» o "
                               "elige otra de la PC." % (titulo_cancion(pista["nombre"]),
                                                        PAPEL_TXT.get(pista["papel"], "").lower()))
            _abrir_alto(self.aviso, px(160))
            self.b_cancelar.show()
            if not self._abiertos and self.mp.biblioteca():
                self._abiertos.add(self.mp.biblioteca()[0][0])
        else:
            self.aviso.setMaximumHeight(0)
            self.b_cancelar.hide()
        if rehacer:
            self._llenar()
            if pista is not None:
                QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
                    self.scroll.verticalScrollBar().maximum()))

    def _usar(self, ruta):
        if self._cambiando is not None:
            self._agregar(ruta, self._cambiando["papel"], quitar=self._cambiando)

    def _de_la_pc(self):
        from PySide6.QtWidgets import QFileDialog
        inicio = getattr(CancionesEstilo, "_carpeta_pc", "") or os.path.join(os.path.expanduser("~"), "Music")
        ruta, _ = QFileDialog.getOpenFileName(self.window(), "Elige una canción", inicio,
                                              "Audio (*.mp3 *.wav *.m4a *.flac)")
        if not ruta:
            return
        CancionesEstilo._carpeta_pc = os.path.dirname(ruta)
        if titulo_cancion(ruta).lower() in getattr(self, "_ya", set()):
            self._avisar("«%s» ya está en este estilo." % titulo_cancion(ruta))
            return
        if self._cambiando is not None:
            self._usar(ruta)
            return
        # sin cambiar ninguna: una fila arriba con la canción elegida y sus 4 partes
        cuerpo = self.scroll.widget()
        fila = self._fila(titulo_cancion(ruta), "Nueva: ¿en qué parte va?", ruta, [])
        fila.setProperty("estado", "nueva")
        self._elegir_papel(fila, ruta)
        cuerpo.layout().insertWidget(1, fila)
        self.scroll.verticalScrollBar().setValue(0)

    def _resaltar(self, fila):
        self._repulir(fila, estado="nueva")
        QTimer.singleShot(60, lambda: self.scroll.ensureWidgetVisible(fila, 0, px(80)))
        _aparecer(fila)

        def apagar():
            try:
                self._repulir(fila, estado="")
            except RuntimeError:
                pass
        QTimer.singleShot(1600, apagar)

    def _avisar(self, texto):
        self.aviso.setText(texto)
        _abrir_alto(self.aviso, px(160))

    def hideEvent(self, e):
        callar()
        super().hideEvent(e)


_PLAY = {}


def _icono_play():
    if "i" not in _PLAY:
        _PLAY["i"] = piezas.qicono("play", "#7CF5C0", px(26))
    return _PLAY["i"]


def _abrir_alto(w, hasta=None):
    """Crece desde 0 hasta su alto (200 ms, OutCubic) y luego queda libre."""
    from PySide6.QtCore import QPropertyAnimation, QEasingCurve
    meta = hasta or max(1, w.sizeHint().height())
    a = QPropertyAnimation(w, b"maximumHeight", w)
    a.setDuration(200)
    a.setStartValue(0)
    a.setEndValue(meta)
    a.setEasingCurve(QEasingCurve.OutCubic)
    if hasta is None:
        a.finished.connect(lambda: w.setMaximumHeight(16777215))
    a.start(a.DeletionPolicy.DeleteWhenStopped)


def _aparecer(w):
    """Entra fundiendose (260 ms) y deja de usar el efecto al terminar (un efecto puesto encarece cada repintado)."""
    from PySide6.QtCore import QPropertyAnimation, QEasingCurve
    from PySide6.QtWidgets import QGraphicsOpacityEffect
    ef = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(ef)
    a = QPropertyAnimation(ef, b"opacity", w)
    a.setDuration(260)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)

    def fin():
        try:
            w.setGraphicsEffect(None)
        except RuntimeError:
            pass
    a.finished.connect(fin)
    a.start(a.DeletionPolicy.DeleteWhenStopped)


class ListaCanciones(CancionesEstilo):
    """(compatibilidad) La lista de antes: un estilo por su carpeta."""

    def __init__(self, carpeta, parent=None):
        import importlib.util
        spec = importlib.util.spec_from_file_location("musica_propia", rutas.codigo("musica_propia.py"))
        mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mp)
        super().__init__(os.path.basename(carpeta), mp, None, parent)


class VistaIntro(QWidget):
    """El ejemplo de una intro: las 8 fotos entrando con su ritmo (cortes en cuadros a 24 por segundo), el impacto y un
    momento del «video»; se repite. Con su efecto de sonido en cada vuelta si se puede."""
    FPS = 24.0
    PAUSA_S = 1.6                # lo que se queda la ultima imagen (el «video») antes de repetir

    def __init__(self, cortes, fotos, sfx=None, parent=None):
        super().__init__(parent)
        self.cortes = [max(1, int(c)) for c in cortes]
        self.sfx = sfx if sfx and os.path.isfile(sfx) else None
        self.setMinimumSize(px(900), px(590))        # el cuadro 16:9 + la tira del ritmo y sus letras
        self._fotos = []
        for r in list(fotos)[:len(self.cortes) + 1]:
            try:
                lector = QImageReader(r)
                lector.setAutoTransform(True)
                tam = lector.size()
                if tam.isValid() and tam.width() > 1280:
                    lector.setScaledSize(QSize(1280, int(tam.height() * 1280.0 / tam.width())))
                img = lector.read()
                if not img.isNull():
                    self._fotos.append(QPixmap.fromImage(img))
            except Exception:
                pass
        self._t0 = time.monotonic()
        self._vuelta = -1
        self._reloj = QTimer(self, interval=piezas.CUADRO_MS)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def _dur(self):
        return sum(self.cortes) / self.FPS + self.PAUSA_S

    def _tic(self):
        if not self.isVisible():
            return
        vuelta = int((time.monotonic() - self._t0) / self._dur())
        if vuelta != self._vuelta:
            self._vuelta = vuelta
            if self.sfx:
                sonar(self.sfx, 0.0, self._dur())
        self.update()

    def hideEvent(self, e):
        self._reloj.stop()
        callar()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        # 16:9 centrado
        w = min(r.width(), r.height() * 16.0 / 9.0)
        cuadro = QRectF(r.center().x() - w / 2, r.center().y() - w * 9 / 32.0, w, w * 9 / 16.0)
        marco = QPainterPath()
        marco.addRoundedRect(cuadro, px(18), px(18))
        p.setClipPath(marco)
        p.fillRect(cuadro, QColor(4, 10, 12))
        t = (time.monotonic() - self._t0) % self._dur()
        f = t * self.FPS
        k, ini = 0, 0.0
        while k < len(self.cortes) and f >= ini + self.cortes[k]:
            ini += self.cortes[k]
            k += 1
        en_video = k >= len(self.cortes)
        u = 0.0 if en_video else (f - ini) / float(self.cortes[k])        # avance dentro de esta foto
        n = len(self._fotos)
        if n:
            pm = self._fotos[min(k, n - 1) if n > len(self.cortes) else k % n]
            z = 1.06 - 0.06 * u if not en_video else 1.0 + 0.03 * min(1.0, (f - ini) / (self.PAUSA_S * self.FPS))
            esc = max(cuadro.width() / pm.width(), cuadro.height() / pm.height()) * z
            tw, th = pm.width() * esc, pm.height() * esc
            p.drawPixmap(QRectF(cuadro.center().x() - tw / 2, cuadro.center().y() - th / 2, tw, th), pm, QRectF(pm.rect()))
        else:
            p.fillRect(cuadro, QColor.fromHsv((k * 37) % 360, 120, 110))
        if not en_video and u < 0.35:                                   # el destello de cada corte
            p.fillRect(cuadro, QColor(255, 255, 255, int(150 * (1.0 - u / 0.35))))
        if en_video and (f - ini) < 5:                                   # el impacto: donde entra la musica
            p.fillRect(cuadro, QColor(255, 255, 255, int(220 * (1.0 - (f - ini) / 5.0))))
        p.setClipping(False)
        p.setPen(QPen(QColor(217, 177, 92, 200), max(1.0, px(3))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(cuadro, px(18), px(18))
        # la tira del ritmo: una marca por foto, del ancho de lo que dura
        total = float(sum(self.cortes))
        x, y, alto = cuadro.left(), cuadro.bottom() + px(18), px(16)
        if y + alto <= r.bottom():
            for i, c in enumerate(self.cortes):
                ancho = cuadro.width() * 0.72 * c / total
                activo = (i == k) and not en_video
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#22C47E") if activo else QColor(255, 255, 255, 60 if i < k or en_video else 28))
                p.drawRoundedRect(QRectF(x, y, max(2.0, ancho - px(6)), alto), alto / 2, alto / 2)
                x += ancho
            p.setBrush(QColor("#E2B04F") if en_video else QColor(226, 176, 79, 70))
            p.drawRoundedRect(QRectF(x, y, cuadro.right() - x, alto), alto / 2, alto / 2)
            f2 = QFont(self.font())
            f2.setPixelSize(max(9, px(24)))
            p.setFont(f2)
            p.setPen(QColor("#9DB0B6"))
            p.drawText(QRectF(cuadro.left(), y + alto + px(6), cuadro.width(), px(36)), Qt.AlignLeft | Qt.AlignVCenter,
                       "8 fotos")
            p.drawText(QRectF(cuadro.left(), y + alto + px(6), cuadro.width(), px(36)), Qt.AlignRight | Qt.AlignVCenter,
                       "arranca el video")

    def sizeHint(self):
        return QSize(px(1000), px(640))
