# -*- coding: utf-8 -*-
"""
medir_fluidez.py - (1.8.9, la persona: «aún tiene trabones o tirones, no está nada fluido») Mide la ventana REAL:
recorre Inicio -> Tráilers (carrusel; popups de canciones, de la intro y un aviso) -> Plantillas -> Ajustes -> Inicio
-> cambiar de tamaño -> maximizar y restaurar, y anota los huecos del hilo de la ventana (> 20 ms sin atender), la pila
de Python durante cada hueco (si no hay pila propia, es Qt pintando), los cuadros por segundo de cada pieza QML y el CPU
por fase. (1.9.0) Al final, «CONGELONES > 50 ms»: cada uno con lo que lo empezo > … > donde estaba. Medir con el
equipo tranquilo (Get-Process ffmpeg): otro programa renderizando da congelones que no son de aqui.

  python PROGRAMA/herramientas/medir_fluidez.py [recorrido|musica]      (abre la ventana ~40 s, con datos aparte)

Deja el informe en datos/fluidez/fluidez.txt (+ .json; con «musica», capturas del popup de canciones). La ventana se
abre de verdad: no tocar el teclado mientras mide (un Enter cierra el popup).
"""
import os
import sys
import json
import time
import threading
import collections

from PySide6.QtCore import QTimer, Qt


def _corta(pila):
    out = []
    for x in reversed(pila):
        out.append("%s:%d %s" % (os.path.basename(x.filename), x.lineno, x.name))
    return " <- ".join(out)


class Guion:
    def __init__(self, w, app, carpeta, salida):
        self.w, self.app, self.salida = w, app, salida
        os.makedirs(salida, exist_ok=True)
        w._revisar_permisos = lambda *a, **k: None          # sin el popup de permisos en la prueba
        self.t0 = time.perf_counter()
        self.fase = "arranque"
        self.fases = [("arranque", 0.0, time.process_time())]
        self.latido = self.t0
        self.huecos = []
        self.grandes = []                                   # [(t, fase, ms, latido)] de los > 50 ms
        self.por_hueco = collections.defaultdict(collections.Counter)
        self.pilas = collections.defaultdict(collections.Counter)
        self.cuadros = collections.defaultdict(list)
        self.main_id = threading.get_ident()
        self.vivo = True
        self.reloj = QTimer()
        self.reloj.setTimerType(Qt.PreciseTimer)
        self.reloj.setInterval(4)
        self.reloj.timeout.connect(self._tic)
        self.reloj.start()
        threading.Thread(target=self._vigia, daemon=True, name="vigia").start()
        self.t_qml = QTimer()
        self.t_qml.timeout.connect(self._conectar_qml)
        self.t_qml.start(500)
        self._programar()

    # ------------------------------------------------------------------ medir
    def _tic(self):
        ahora = time.perf_counter()
        gap = (ahora - self.latido) * 1000.0
        if gap > 20.0:
            self.huecos.append((round(ahora - self.t0, 2), self.fase, round(gap, 1)))
            if gap > 50.0:                                  # (1.9.0) cada congelon grande, con sus pilas
                self.grandes.append((round(self.latido - self.t0, 2), self.fase, round(gap, 1), self.latido))
        self.latido = ahora

    @staticmethod
    def _resumir(pila):
        """La pila (de dentro hacia fuera) en una linea: lo que la empezo (justo despues de app) … donde esta."""
        fuera = list(reversed(pila))
        corte = max((i for i, x in enumerate(fuera) if x[2] in ("app", "<module>", "main")), default=-1)
        propia = ["%s:%d %s" % x for x in fuera[corte + 1:]]
        if not propia:
            return "(Qt por dentro: pinta, acomoda o crea QML; sin Python)"
        if len(propia) > 7:
            propia = propia[:4] + ["…"] + propia[-3:]
        return " > ".join(propia)

    def _vigia(self):
        while self.vivo:
            time.sleep(0.010)
            inicio = self.latido
            if time.perf_counter() - inicio > 0.030:
                # sin cambiar de hilo mientras se recorre la pila del otro (si no, sus cuadros pueden desaparecer)
                antes = sys.getswitchinterval()
                sys.setswitchinterval(1.0)
                try:
                    f = sys._current_frames().get(self.main_id)
                    pila = []
                    while f is not None and len(pila) < 40:
                        pila.append((os.path.basename(f.f_code.co_filename), f.f_lineno, f.f_code.co_name))
                        f = f.f_back
                finally:
                    sys.setswitchinterval(antes)
                if pila:
                    clave = self._resumir(pila)
                    self.pilas[self.fase][clave] += 1
                    self.por_hueco[inicio][clave] += 1

    def _conectar_qml(self):
        from PySide6.QtQuickWidgets import QQuickWidget
        for q in self.w.findChildren(QQuickWidget):
            if q.property("_medido"):
                continue
            q.setProperty("_medido", True)
            nombre = q.source().fileName() or q.objectName() or "qml"
            qw = q.quickWindow()
            if qw is not None:
                qw.afterRendering.connect(lambda n=nombre: self.cuadros[n].append((time.perf_counter() - self.t0, self.fase)),
                                          Qt.DirectConnection)

    # ------------------------------------------------------------------ el recorrido
    def _fase(self, nombre, accion=None):
        self.fase = nombre
        self.fases.append((nombre, time.perf_counter() - self.t0, time.process_time()))
        if accion:
            try:
                accion()
            except Exception as ex:
                self.fases.append(("ERROR %s: %s" % (nombre, ex), time.perf_counter() - self.t0, time.process_time()))

    def _cerrar_popup(self):
        p = getattr(self.w, "popup_abierto", None)
        if p is not None and getattr(p, "botones", None):
            p.botones[-1].click()

    def _estilo(self, i):
        seg = getattr(self.w, "seg_musica", None)
        if seg is not None and i < len(seg.botones):
            seg.botones[i].click()

    # ------------------------------------------------------------------ el popup de canciones (MEDIR_MUSICA=1)
    def _grab(self, nombre):
        self.w.grab().save(os.path.join(self.salida, nombre + ".png"))

    def _canciones(self):
        from PySide6.QtWidgets import QWidget
        return next((x for x in self.w.findChildren(QWidget) if x.objectName() == "canciones"), None)

    def _boton(self, nombre_obj, texto=None, n=0):
        from PySide6.QtWidgets import QPushButton
        c = self._canciones()
        if c is None:
            return None
        bs = [b for b in c.findChildren(QPushButton) if b.objectName() == nombre_obj and b.isVisible()
              and (texto is None or texto.lower() in b.text().lower())]
        return bs[n] if len(bs) > n else None

    def _clic(self, nombre_obj, texto=None, n=0):
        b = self._boton(nombre_obj, texto, n)
        if b is None:
            raise RuntimeError("no hay boton %s %s" % (nombre_obj, texto))
        b.click()

    def _programar_musica(self):
        w = self.w
        pasos = [
            (5.0, "a Tráilers", lambda: w._ir("Tráilers")),
            (2.0, "abrir popup", lambda: QTimer.singleShot(0, lambda: w._ver_canciones(4))),
            (2.0, "foto 1", lambda: self._grab("popup_1")),
            (0.5, "abrir Vals", lambda: self._clic("grupo", "Vals")),
            (1.0, "foto 2", lambda: self._grab("popup_2")),
            (0.5, "agregar", lambda: self._clic("accion", "Agregar")),
            (0.8, "foto 3", lambda: self._grab("popup_3")),
            (0.4, "elegir parte", lambda: self._clic("chip_sugerido")),
            (1.6, "foto 4", lambda: self._grab("popup_4")),
            (0.5, "cambiar", lambda: self._clic("accion", "Cambiar", 2)),
            (1.2, "foto 5", lambda: self._grab("popup_5")),
            (0.5, "usar esta", lambda: self._clic("accion_oro", "Usar esta")),
            (1.6, "foto 6", lambda: self._grab("popup_6")),
            (0.5, "cerrar popup", self._cerrar_popup),
            (1.5, "fin", self._terminar),
        ]
        t = 0.0
        for dur, nombre, accion in pasos:
            t += dur
            QTimer.singleShot(int(t * 1000), lambda n=nombre, a=accion: self._fase(n, a))

    def _programar(self):
        if os.environ.get("TRAILER_MEDIR_FLUIDEZ_RECORRIDO") == "musica":
            return self._programar_musica()
        w = self.w
        g0 = w.geometry()
        pasos = [
            (6.0, "Inicio quieto", None),
            (4.0, "a Tráilers", lambda: w._ir("Tráilers")),
            (1.2, "Tráilers quieto", None),
            (3.0, "carrusel 1", lambda: self._estilo(2)),
            (1.0, "carrusel 2", lambda: self._estilo(3)),
            (1.0, "carrusel 3", lambda: self._estilo(1)),
            (1.0, "carrusel 4", lambda: self._estilo(4)),
            (1.5, "popup canciones", lambda: QTimer.singleShot(0, lambda: w._ver_canciones(4))),
            (3.0, "cerrar popup", self._cerrar_popup),
            (1.5, "popup intro", lambda: QTimer.singleShot(0, lambda: w._ver_intro(0))),
            (2.5, "cerrar intro", self._cerrar_popup),
            (1.5, "popup aviso", lambda: QTimer.singleShot(0, lambda: w._popup("Un aviso corto para medir.",
                                                                                titulo="Prueba de fluidez"))),
            (2.0, "cerrar aviso", self._cerrar_popup),
            (1.5, "a Plantillas", lambda: w._ir("Plantillas")),
            (3.0, "a Ajustes", lambda: w._ir("Ajustes")),
            (3.0, "a Inicio", lambda: w._ir("Inicio")),
            (3.0, "redimensionar", lambda: w.setGeometry(g0.x(), g0.y(), int(g0.width() * 0.8), int(g0.height() * 0.85))),
            (1.5, "volver tamaño", lambda: w.setGeometry(g0)),
            (2.0, "maximizar", w.showMaximized),
            (2.0, "restaurar", w.showNormal),
            (2.5, "fin", self._terminar),
        ]
        t = 0.0
        for dur, nombre, accion in pasos:
            t += dur
            QTimer.singleShot(int(t * 1000), lambda n=nombre, a=accion: self._fase(n, a))

    # ------------------------------------------------------------------ el informe
    def _terminar(self):
        self.vivo = False
        fin = time.perf_counter() - self.t0
        cpu_fin = time.process_time()
        lineas, datos = [], {"fases": []}
        fases = [f for f in self.fases if not f[0].startswith("ERROR")] + [("_", fin, cpu_fin)]
        for f in self.fases:
            if f[0].startswith("ERROR"):
                lineas.append(f[0])
        for (n, a, ca), (_, b, cb) in zip(fases, fases[1:]):
            if n == "fin":
                continue
            hs = [h[2] for h in self.huecos if h[1] == n]
            cpu = 100.0 * (cb - ca) / max(b - a, 1e-3)
            q = {}
            for nom, ts in self.cuadros.items():
                t = [x[0] for x in ts if x[1] == n]
                if len(t) > 2:
                    iv = sorted((y - x) * 1000 for x, y in zip(t, t[1:]))
                    q[nom] = (len(t), round(len(t) / max(b - a, 1e-3)), round(iv[len(iv) // 2], 1),
                              round(iv[int(len(iv) * 0.95)], 1), round(iv[-1], 1))
            pil = self.pilas.get(n, collections.Counter()).most_common(4)
            datos["fases"].append({"fase": n, "seg": round(b - a, 2), "huecos": len(hs), "max_ms": max(hs) if hs else 0,
                                   "huecos_50": sum(1 for h in hs if h > 50), "cpu": round(cpu), "qml": q,
                                   "pilas": pil})
            lineas.append("%-16s %4.1fs cpu %3d%% | huecos %3d (>50ms %2d) max %6.1f ms" % (
                n, b - a, cpu, len(hs), sum(1 for h in hs if h > 50), max(hs) if hs else 0))
            for nom, (c, fps, p50, p95, mx) in sorted(q.items()):
                lineas.append("     qml %-16s %4d cuadros %3d/s  intervalo p50 %5.1f p95 %5.1f max %6.1f ms" % (
                    nom, c, fps, p50, p95, mx))
            for pila, k in pil[:3]:
                lineas.append("     pila x%-3d %s" % (k, pila[:260]))
        if self.grandes:                                    # (1.9.0) cada congelon grande y lo que lo hizo
            lineas.append("")
            lineas.append("CONGELONES > 50 ms (cuando, fase, cuanto, que hacia el hilo de la ventana):")
        for t, fase, ms, latido in self.grandes:
            lineas.append("  %6.2f s  %-16s %6.1f ms" % (t, fase, ms))
            for pila, k in self.por_hueco.get(latido, collections.Counter()).most_common(3):
                lineas.append("        x%-3d %s" % (k, pila[:300]))
        datos["huecos"] = self.huecos
        datos["grandes"] = [(t, f, ms, self.por_hueco.get(lt, collections.Counter()).most_common(3))
                            for t, f, ms, lt in self.grandes]
        with open(os.path.join(self.salida, "fluidez.json"), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
        with open(os.path.join(self.salida, "fluidez.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
        self.app.quit()


def main():
    """Abre la ventana con este medidor (datos aparte, con el estado de PROGRAMA/datos) y muestra el informe."""
    import shutil
    import subprocess
    aqui = os.path.dirname(os.path.abspath(__file__))
    programa = os.path.dirname(aqui)
    sys.path.insert(0, os.path.join(programa, "nucleo"))
    import rutas
    base = os.path.join(rutas.DATOS, "fluidez")
    datos = os.path.join(base, "datos")
    shutil.rmtree(datos, ignore_errors=True)
    os.makedirs(os.path.join(datos, "analisis"), exist_ok=True)
    if os.path.exists(rutas.ESTADO):
        shutil.copy2(rutas.ESTADO, os.path.join(datos, "analisis"))
    env = dict(os.environ, TRAILER_DATOS=datos, TRAILER_MEDIR_FLUIDEZ=base, TRAILER_VISION_MODELO="ninguno",
               TRAILER_MEDIR_FLUIDEZ_RECORRIDO=(sys.argv[1] if len(sys.argv) > 1 else "recorrido"),
               PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, os.path.join(programa, "interfaz", "trailer_xv.py")], env=env)
    with open(os.path.join(base, "fluidez.txt"), encoding="utf-8") as f:
        print(f.read())


if __name__ == "__main__":
    main()
