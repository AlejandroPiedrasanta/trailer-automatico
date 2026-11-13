# -*- coding: utf-8 -*-
"""boton_go.py - El boton GO de la pantalla de Inicio (el astrolabio de bronce de CineCaptions, de orbe_mecanica /
estilos_inicio): respira en reposo, cada fase enciende una pieza, el engranaje acelera con el avance real y el final se cierra
en tres tiempos (carga y temblor, destello, palomita). Un solo reloj lo mueve todo: el de la escena (seguir_a)."""
import math

from PySide6.QtCore import QEasingCurve, QPointF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QAbstractButton

from i18n import tr

def _anim(padre, duracion, al_cambiar, bucle=False, curva=QEasingCurve.Type.Linear):
    a = QVariantAnimation(padre)
    a.setDuration(duracion)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(curva)
    if bucle:
        a.setLoopCount(-1)
    a.valueChanged.connect(al_cambiar)
    return a


class BotonGo(QAbstractButton):
    """El botón GO: el astrolabio (orbe_mecanica). Estados: listo (respira), apagado, trabajando (cada fase enciende una pieza, el
    engranaje se acelera con el progreso real, ETA), hecho (cierre en tres tiempos: carga y temblor → destello → el engranaje
    se detiene y la palomita se dibuja), error (el orbe se apaga poco a poco). Un solo reloj lo mueve todo (el de la escena);
    el ratón inclina las capas (paralaje) y el tamaño sigue al alto disponible (poner_lado)."""
    CARGA = 0.7                  # s de carga/temblor antes del destello del final

    def __init__(self, padre=None, lado=280):
        super().__init__(padre)
        self.setFixedSize(lado, lado)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.estado = 'listo'
        self.progreso = 0.0
        self._prog_visto = 0.0
        self.cortes = ()                 # v5.22: dónde acaba cada paso (0..1): el anillo los marca como la barra de abajo
        self.texto_centro = ''
        self.texto_bajo = ''
        self.fase = ''
        self._fase_t0 = -9.0
        self.tono = 'ok'                 # 'ok' | 'aviso' (terminó con avisos)
        self._t = 0.0
        self._hover = 0.0
        self._hover_obj = 0.0
        self._presion = 0.0
        self._presion_obj = 0.0
        self._iman = QPointF(0, 0)
        self._iman_obj = QPointF(0, 0)
        self._par = [0.0, 0.0]
        self._marca = 0.0
        self._sacudida = 0.0
        self._flare = 0.0
        self._cierre = -1.0              # segundos desde que terminó (hecho/error); -1 = no terminó
        self._estallo = False
        self._clic_fin = False
        self._apagon = 0.0
        self._residuo = 0.0
        self._vel = 1.0
        self._ent = 0.0                  # segundos desde que apareció: las piezas se ensamblan de fuera hacia dentro
        self._ent_hecha = False
        self._desde = 0.0
        self._suave_t = 1.0
        self._t_ini = None               # cuándo empezó a trabajar (para el tiempo restante)
        self._eta_fin = None
        self._eta_manual = ''            # el tiempo restante que calcula el estimador de GO (manda sobre el cálculo por ritmo)
        self._escena = None
        import efectos_ui
        self._quieto = efectos_ui.reducir_animaciones()
        import estilos_inicio
        self._estilos = estilos_inicio
        self._poner_estilo(estilos_inicio.clave_guardada())
        self._flare_hecho = False
        self._flare = 0.0
        self._lado_obj = lado
        self._lado_f = float(lado)
        self._reloj = QTimer(self)
        self._reloj.setTimerType(Qt.TimerType.PreciseTimer)         # 60 fps parejos (el temporizador normal de Windows da saltos)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start(16)
        import time as _time
        self._time = _time
        self._ultimo = _time.perf_counter()

    def _poner_estilo(self, clave):
        """Cambia el estilo de Inicio (v5.49: los 3, todos con el astrolabio): cada uno lleva su propia instancia con su movimiento."""
        self._estilo_clave = clave
        self._estilo = self._estilos.crear(clave)
        self._ctx = self._estilos.Ctx()
        self.update()

    def poner_lado(self, lado):
        """El tamaño que debe tener; el botón se acerca a él con suavidad (si aún no se ve, de golpe)."""
        lado = int(max(200, min(620, lado)))
        self._lado_obj = lado
        if not self.isVisible() or not self._ent_hecha:
            self._lado_f = float(lado)
            if lado != self.width():
                self.setFixedSize(lado, lado)

    def _modo(self):
        return getattr(self._escena, 'modo', 'completo') if self._escena is not None else 'completo'

    # -- reloj -------------------------------------------------------------------
    def _tic(self):
        ahora = self._time.perf_counter()
        dt = min(0.05, ahora - self._ultimo)
        self._ultimo = ahora
        self._t += dt
        self._ent += dt
        self._flare = max(0.0, self._flare - dt / 1.0)
        if abs(self._lado_obj - self._lado_f) > 0.4:                      # el orbe cambia de tamaño con suavidad
            self._lado_f += (self._lado_obj - self._lado_f) * min(1.0, dt * 7.0)
            n = int(round(self._lado_f))
            if n != self.width():
                self.setFixedSize(n, n)
        est = self.estado
        # velocidad de giro: lenta en reposo; con el progreso real se acelera; el cierre la sube, la frena en seco y la devuelve
        if est == 'listo':
            obj = 1.0
        elif est == 'apagado':
            obj = 0.2
        elif est == 'trabajando':
            obj = 3.0 + 6.0 * self._prog_visto
        elif est == 'hecho':
            c = max(0.0, self._cierre)
            if c < self.CARGA:
                obj = 4.0 + 8.0 * (c / self.CARGA)
            elif c < 3.2:
                obj = 0.12 + 9.0 * math.exp(-(c - self.CARGA) * 3.4)
            else:
                obj = 1.0
        else:
            obj = 0.7 * (1.0 - self._apagon) + 0.04
        self._vel += (obj - self._vel) * min(1.0, dt * (14.0 if est == 'hecho' and self._cierre < 3.2 else 6.0))
        quieto = self._quieto or bool(getattr(self._escena, '_quieto', False))
        if self._escena is not None and getattr(self._escena, 'estilo_clave', self._estilo_clave) != self._estilo_clave:
            self._poner_estilo(self._escena.estilo_clave)
        self._estilo.avanzar(dt, 0.0 if quieto else self._vel)
        k = min(1.0, dt * 12)
        self._hover += (self._hover_obj - self._hover) * k
        self._presion += (self._presion_obj - self._presion) * min(1.0, dt * 22)
        self._iman = self._iman + (self._iman_obj - self._iman) * min(1.0, dt * 8)
        # v5.22: el % que se ve sigue al estimador SIN escalones (antes: una curva de 0,35 s cada medio segundo y quieto el resto, a
        # saltos) y nunca retrocede mientras trabaja. Es el mismo valor que pinta la barra de abajo de la escena (PanelGo._datos_barra).
        d = self.progreso - self._prog_visto
        if d > 0.0:
            self._prog_visto += d * min(1.0, dt * 3.4) if d > 0.0015 else d
        elif est != 'trabajando':
            self._prog_visto = self.progreso
        # el cierre en tres tiempos
        if self._cierre >= 0.0:
            self._cierre += dt
            if est == 'hecho':
                if self._cierre >= self.CARGA and not self._estallo:
                    self._estallo = True
                    self._flare = 1.0                                   # 2.º tiempo: el destello
                if self._cierre >= self.CARGA + 0.2 and self._marca < 1.0:
                    self._marca = min(1.0, self._marca + dt / 0.85)     # la palomita se dibuja trazo a trazo
                if self._cierre >= 1.9 and not self._clic_fin:
                    self._clic_fin = True
                    self._flare = max(self._flare, 0.4)                 # 3.er tiempo: el «clic» al detenerse el engranaje
            elif est == 'error':
                self._apagon = min(1.0, self._cierre / 2.5)
        if self._residuo > 0.0 and est in ('listo', 'apagado'):
            self._residuo = max(0.0, self._residuo - dt / 1.8)
        if self._sacudida > 0:
            self._sacudida = max(0.0, self._sacudida - dt)
        if self.isVisible():
            self.update()

    def seguir_a(self, escena):
        """Un solo reloj para todo Inicio: el botón avanza cuando avanza la escena, así Qt junta los dos repintados en uno."""
        self._externo = True
        self._escena = escena
        self._reloj.stop()
        escena.al_tic.append(self._tic)

    def showEvent(self, e):
        self._ultimo = self._time.perf_counter()
        if not self._ent_hecha:
            self._ent_hecha = True
            self._ent = 0.0
        if not getattr(self, '_externo', False):
            self._reloj.start(16)
        super().showEvent(e)

    def hideEvent(self, e):
        self._reloj.stop()
        super().hideEvent(e)

    def enterEvent(self, e):
        self._hover_obj = 1.0
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_obj = 0.0
        self._iman_obj = QPointF(0, 0)
        super().leaveEvent(e)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if self.estado in ('listo', 'hecho', 'error'):
            self._presion_obj = 1.0
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._presion_obj = 0.0
        super().mouseReleaseEvent(e)

    # -- estado ---------------------------------------------------------------
    def poner_estado(self, estado, centro=None, bajo=None, tono=None):
        anterior = self.estado
        self.estado = estado
        if centro is not None:
            self.texto_centro = centro
        if bajo is not None:
            self.texto_bajo = bajo
        self.setCursor(Qt.CursorShape.PointingHandCursor if estado in ('listo', 'hecho', 'error')
                       else Qt.CursorShape.ArrowCursor)
        if estado == 'trabajando' and anterior != 'trabajando':
            self._flare = 1.0
            self._cierre = -1.0
            self._estallo = self._clic_fin = False
            self._apagon = 0.0
            self._residuo = 0.0
            self._marca = 0.0
            self.tono = 'ok'
            self.fase = ''
            self._t_ini = self._time.perf_counter()
            self._eta_fin = None
            self._eta_manual = ''
        if estado == 'hecho' and anterior != 'hecho':
            self._marca = 0.0
            self._cierre = 0.0
            self._estallo = self._clic_fin = False
            self.tono = tono or 'ok'
        if estado == 'error' and anterior != 'error':
            self._cierre = 0.0
            self._apagon = 0.0
            if not self._quieto:
                self._sacudida = 0.5
        if estado in ('listo', 'apagado') and anterior == 'hecho':
            self._residuo = 1.0                                        # la palomita se desvanece mientras vuelve la gema
            self._cierre = -1.0
        elif estado in ('listo', 'apagado'):
            self._cierre = -1.0
        self.update()

    def poner_fase(self, clave):
        """El paso en curso: enciende una pieza distinta del astrolabio y da un pequeño temblor al cambiar."""
        if clave != self.fase:
            self.fase = clave
            self._fase_t0 = self._t

    def poner_progreso(self, f):
        f = max(0.0, min(1.0, float(f)))
        if f < self._prog_visto - 0.05:                  # un GO nuevo (o un retroceso grande): se ve ya, sin deslizar hacia atrás
            self._prog_visto = f
        self.progreso = f
        # tiempo restante: se estima con el ritmo hasta ahora y se suaviza (no salta)
        if self.estado == 'trabajando' and self._t_ini is not None and f > 0.08:
            ahora = self._time.perf_counter()
            transcurrido = ahora - self._t_ini
            if transcurrido > 1.0:
                fin = ahora + transcurrido * (1.0 - f) / f
                self._eta_fin = fin if self._eta_fin is None else 0.8 * self._eta_fin + 0.2 * fin

    def poner_eta(self, texto):
        self._eta_manual = str(texto or '')
        self.update()

    def _eta_texto(self):
        if self.estado == 'trabajando' and self._eta_manual:
            return self._eta_manual
        if self.estado != 'trabajando' or self._eta_fin is None or self._t_ini is None:
            return ''
        ahora = self._time.perf_counter()
        if ahora - self._t_ini < 8.0 or self._prog_visto > 0.97:
            return ''
        resto = max(0.0, self._eta_fin - ahora)
        if resto < 10:
            return tr('unos segundos')
        if resto < 90:
            return tr('~ {s} s', s=int(round(resto / 5.0) * 5))
        return tr('~ {m} min', m=int(round(resto / 60.0)))

    def centro_global(self):
        return self.mapToGlobal(self.rect().center())

    # -- dibujo ---------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        sac = 0.0
        if self._sacudida > 0:
            sac = math.sin(self._t * 60) * 10 * (self._sacudida / 0.5)
        c = QPointF(w / 2 + sac, h / 2)
        escala = 1 - 0.03 * self._presion                                  # solo al PULSAR se hunde un poco; al pasar el ratón no se mueve
        R = min(w, h) * 0.40 * escala
        estado, prog, texto = self.estado, self._prog_visto, self.texto_centro
        vibra = 0.0
        if estado == 'hecho' and 0.0 <= self._cierre < self.CARGA:            # 1.er tiempo: carga y temblor, todavía al 100 %
            estado, prog, texto = 'trabajando', 1.0, tr('Listo')
            vibra = min(1.0, self._cierre / 0.45) * 0.9
        elif self.estado == 'trabajando' and self._t - self._fase_t0 < 0.35:   # al cambiar de fase, un temblor corto
            vibra = 0.5 * (1.0 - (self._t - self._fase_t0) / 0.35)
        cx = self._ctx
        cx.estado, cx.t, cx.progreso, cx.marca, cx.flare = estado, self._t, prog, self._marca, self._flare
        cx.hover, cx.presion, cx.fase, cx.fase_t, cx.tono = self._hover, self._presion, (self.fase if self.estado == 'trabajando' else ''), self._t - self._fase_t0, self.tono
        cx.vibra, cx.apagon, cx.residuo, cx.eta, cx.texto = vibra, self._apagon, self._residuo, self._eta_texto(), texto
        cx.entrada, cx.vel, cx.quieto, cx.cierre = self._ent, self._vel, self._quieto, self._cierre
        cx.cortes = self.cortes if estado == 'trabajando' else ()
        if not getattr(self._estilo, 'ensambla', False) and self._ent < 1.2:      # entrada: aparece creciendo (el astrolabio se ensambla pieza a pieza)
            e = min(1.0, self._ent / 0.8)
            p.setOpacity(e)
            R *= 0.86 + 0.14 * (1 - (1 - e) ** 3)
        self._estilo.dibujar(p, c, R, cx, min(w, h) * 0.40)
        p.end()

