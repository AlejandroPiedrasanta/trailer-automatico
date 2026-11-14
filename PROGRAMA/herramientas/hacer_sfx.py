# -*- coding: utf-8 -*-
"""
hacer_sfx.py - Crea los efectos de sonido PROPIOS del programa (recursos/sfx/*.wav), sintetizados con numeros:
no salen de ninguna biblioteca ni de ningun archivo ajeno, asi que van dentro del programa y de sus
actualizaciones (la musica y los SFX con licencia de recursos/audio no se publican).

  XV_GOLPE.wav ...... golpe grave de cine (para la entrada de la fiesta y del titulo)
  XV_SUBIDA.wav ..... subida de aire que termina en seco (justo antes del golpe)
  XV_BRILLO.wav ..... destellos agudos, como campanitas (titulo y tarjeta final)
  XV_PASO.wav ....... paso de aire corto y suave (capitulos, entrada de la foto final)
  XV_OBTURADOR.wav .. clic de camara (rafaga de fotos de la intro)

  python PROGRAMA/herramientas/hacer_sfx.py        los vuelve a crear (siempre salen iguales: semilla fija)

Los coloca armado/sfx.py (momentos) y los importa build_trailers (sfx_propios).
"""
import os
import sys
import wave

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.dirname(AQUI)
DESTINO = os.path.join(PROG, "recursos", "sfx")
FS = 48000


def _t(seg):
    return np.arange(int(FS * seg), dtype=np.float64) / FS


def _paso_bajo(x, corte):
    """Un polo (6 dB por octava), dos pasadas."""
    a = float(np.exp(-2.0 * np.pi * corte / FS))
    y = np.empty_like(x)
    for _ in range(2):
        acc = 0.0
        for i in range(len(x)):
            acc = (1.0 - a) * x[i] + a * acc
            y[i] = acc
        x = y.copy()
    return y


def _banda_movil(ruido, f0, f1):
    """Ruido filtrado por una banda que se mueve de f0 a f1 Hz (filtro de estado variable)."""
    n = len(ruido)
    f = f0 * (f1 / float(f0)) ** (np.arange(n) / float(n))
    g = 2.0 * np.sin(np.pi * np.minimum(f, FS / 6.0) / FS)
    q = 0.35
    bajo = banda = 0.0
    y = np.empty(n)
    for i in range(n):
        bajo += g[i] * banda
        alto = ruido[i] - bajo - q * banda
        banda += g[i] * alto
        y[i] = banda
    return y


def _normal(x, pico_db):
    return x * (10 ** (pico_db / 20.0) / (np.abs(x).max() + 1e-12))


def _estereo(izq, der):
    return np.stack([izq, der], axis=1)


def golpe(rng):
    t = _t(2.6)
    fase = 2 * np.pi * np.cumsum(34.0 + 46.0 * np.exp(-t / 0.09)) / FS      # 80 Hz que cae a 34
    cuerpo = np.sin(fase) * np.exp(-t / 0.55) * np.minimum(1.0, t / 0.004)
    chasquido = _paso_bajo(rng.standard_normal(len(t)), 1800.0) * np.exp(-t / 0.045)
    cola_i = _paso_bajo(rng.standard_normal(len(t)), 420.0) * np.exp(-t / 0.7) * np.minimum(1.0, t / 0.02)
    cola_d = _paso_bajo(rng.standard_normal(len(t)), 420.0) * np.exp(-t / 0.7) * np.minimum(1.0, t / 0.02)
    base = 1.0 * cuerpo + 0.5 * chasquido
    fin = np.minimum(1.0, (t[-1] - t) / 0.25)
    return _normal(_estereo((base + 0.55 * cola_i) * fin, (base + 0.55 * cola_d) * fin), -4.0)


def subida(rng):
    t = _t(3.0)
    sube = (t / t[-1]) ** 2.6
    aire_i = _banda_movil(rng.standard_normal(len(t)), 180.0, 7000.0)
    aire_d = _banda_movil(rng.standard_normal(len(t)), 200.0, 7600.0)
    tono = np.sin(2 * np.pi * np.cumsum(90.0 * (9.0 ** (t / t[-1]))) / FS) * 0.25
    corte = np.minimum(1.0, (t[-1] - t) / 0.012)                             # termina en seco
    return _normal(_estereo((aire_i + tono) * sube * corte, (aire_d + tono) * sube * corte), -6.0)


def brillo(rng):
    t = _t(3.2)
    izq, der = np.zeros(len(t)), np.zeros(len(t))
    notas = [1760.0, 2093.0, 2637.0, 3136.0, 3520.0, 4186.0, 5274.0, 6272.0]   # La mayor con sexta, bien arriba
    for k in range(34):
        ini = rng.uniform(0.0, 1.9) ** 1.25
        f = notas[rng.integers(0, len(notas))] * rng.choice([1.0, 1.0, 2.0])
        amp = rng.uniform(0.25, 1.0) * np.exp(-ini / 1.6)
        d = np.clip(t - ini, 0.0, None)
        nota = np.where(t >= ini, np.sin(2 * np.pi * f * d) * np.exp(-d / rng.uniform(0.18, 0.5)), 0.0) * amp
        pan = rng.uniform(0.15, 0.85)
        izq += nota * (1.0 - pan)
        der += nota * pan
    fin = np.minimum(1.0, (t[-1] - t) / 0.4)
    return _normal(_estereo(izq * fin, der * fin), -9.0)


def paso(rng):
    t = _t(0.9)
    forma = np.sin(np.pi * t / t[-1]) ** 2.2
    izq = _banda_movil(rng.standard_normal(len(t)), 500.0, 3800.0) * forma
    der = _banda_movil(rng.standard_normal(len(t)), 650.0, 4400.0) * np.roll(forma, int(0.03 * FS))
    return _normal(_estereo(izq, der), -9.0)


def obturador(rng):
    t = _t(0.16)
    clic = np.zeros(len(t))
    for ini, dec, corte in ((0.0, 0.006, 5200.0), (0.055, 0.010, 3200.0)):      # sube el espejo, cae la cortina
        d = np.clip(t - ini, 0.0, None)
        clic += np.where(t >= ini, _paso_bajo(rng.standard_normal(len(t)), corte) * np.exp(-d / dec), 0.0)
    return _normal(_estereo(clic, np.roll(clic, 7)), -8.0)


SONIDOS = {"XV_GOLPE": golpe, "XV_SUBIDA": subida, "XV_BRILLO": brillo, "XV_PASO": paso, "XV_OBTURADOR": obturador}


def guardar(nombre, x):
    ruta = os.path.join(DESTINO, nombre + ".wav")
    datos = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(datos.tobytes())
    return ruta


def main():
    os.makedirs(DESTINO, exist_ok=True)
    for k, (nombre, hacer) in enumerate(SONIDOS.items()):
        x = hacer(np.random.default_rng(2026 + k))
        ruta = guardar(nombre, x)
        print("%-16s %.2f s  pico %.1f dB  %d KB" % (nombre + ".wav", len(x) / float(FS),
                                                    20 * np.log10(np.abs(x).max() + 1e-12), os.path.getsize(ruta) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
