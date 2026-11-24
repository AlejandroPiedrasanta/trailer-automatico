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
  XV_RAMPA*.wav ..... la rampa de las 8 fotos de la intro, una por tipo (RAMPAS)
  (1.9.0) XV_RAMPA_ZOOM.wav, la de la intro «Zoom», lleva el riser de la biblioteca CON LICENCIA: va a recursos/audio
  (CON_LICENCIA), fuera de git y de la actualizacion publica

  python PROGRAMA/herramientas/hacer_sfx.py        los vuelve a crear (siempre salen iguales: semilla fija)
  python PROGRAMA/herramientas/hacer_sfx.py XV_RAMPA_ZOOM    solo esos

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


def rampa(rng, cortes=(5,) * 8):
    """(17-nov) La apertura es una RAMPA DE VELOCIDAD de las 8 fotos (40 cuadros = 1,667 s) y luego arranca el video:
    aire que sube y late una vez por foto (cortes = cuadros de cada foto: build_trailers.INTROS) y, justo al terminar
    las fotos, un impacto grave con un platillo de aire que se abre."""
    fotos = sum(cortes) / 24.0
    t = _t(fotos + 2.6)
    antes = t < fotos
    u = np.clip(t / fotos, 0.0, 1.0)
    sube = u ** 2.2
    late = np.full(len(t), 0.55)                                              # un latido al empezar cada foto
    ini = 0.0
    for c in cortes:
        d = t - ini
        late += 0.45 * np.where((d >= 0) & (d < c / 24.0), np.exp(-d / (0.35 * c / 24.0)), 0.0)
        ini += c / 24.0
    aire_i = _banda_movil(rng.standard_normal(len(t)), 220.0, 9000.0)
    aire_d = _banda_movil(rng.standard_normal(len(t)), 260.0, 9800.0)
    tono = np.sin(2 * np.pi * np.cumsum(70.0 * (12.0 ** u)) / FS) * 0.3
    corte = np.minimum(1.0, np.clip(fotos - t, 0.0, None) / 0.01)             # el aire termina en seco en el impacto
    sub_i, sub_d = (aire_i + tono) * sube * late * corte * antes, (aire_d + tono) * sube * late * corte * antes
    d = np.clip(t - fotos, 0.0, None)
    ya = t >= fotos
    fase = 2 * np.pi * np.cumsum(32.0 + 58.0 * np.exp(-d / 0.08)) / FS
    grave = np.sin(fase) * np.exp(-d / 0.6) * np.minimum(1.0, d / 0.003) * ya
    chasq = _paso_bajo(rng.standard_normal(len(t)), 2400.0) * np.exp(-d / 0.05) * ya
    plato_i = (rng.standard_normal(len(t)) - _paso_bajo(rng.standard_normal(len(t)), 3000.0)) * np.exp(-d / 0.9) * ya
    plato_d = (rng.standard_normal(len(t)) - _paso_bajo(rng.standard_normal(len(t)), 3000.0)) * np.exp(-d / 0.9) * ya
    fin = np.minimum(1.0, (t[-1] - t) / 0.3)
    izq = 0.55 * _normal(sub_i, 0.0) + (grave + 0.5 * chasq + 0.12 * plato_i) * fin
    der = 0.55 * _normal(sub_d, 0.0) + (grave + 0.5 * chasq + 0.12 * plato_d) * fin
    return _normal(_estereo(izq, der), -4.0)


# (1.9.0) los propios hechos con un sonido de la biblioteca CON LICENCIA van a recursos/audio (fuera de git y de la
# actualizacion publica; para la Mac, cifrados con compilar/protegidos.py), no a recursos/sfx
AUDIO = os.path.join(PROG, "recursos", "audio")
RISER = "ES_Designed, Riser, Riser, Dark, Cinematic, Mechanical - Epidemic Sound.wav"


def _leer(ruta):
    import subprocess
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-ac", "2", "-ar", str(FS), "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, "<i2").astype(np.float64).reshape(-1, 2) / 32767.0


def _impacto(rng, fotos, largo):
    """El impacto de las rampas (grave que cae, chasquido y platillo de aire) a los `fotos` segundos."""
    t = _t(largo)
    d = np.clip(t - fotos, 0.0, None)
    ya = t >= fotos
    fase = 2 * np.pi * np.cumsum(32.0 + 58.0 * np.exp(-d / 0.08)) / FS
    grave = np.sin(fase) * np.exp(-d / 0.6) * np.minimum(1.0, d / 0.003) * ya
    chasq = _paso_bajo(rng.standard_normal(len(t)), 2400.0) * np.exp(-d / 0.05) * ya
    pl_i = (rng.standard_normal(len(t)) - _paso_bajo(rng.standard_normal(len(t)), 3000.0)) * np.exp(-d / 0.9) * ya
    pl_d = (rng.standard_normal(len(t)) - _paso_bajo(rng.standard_normal(len(t)), 3000.0)) * np.exp(-d / 0.9) * ya
    fin = np.minimum(1.0, (t[-1] - t) / 0.3)
    return _estereo((grave + 0.5 * chasq + 0.12 * pl_i) * fin, (grave + 0.5 * chasq + 0.12 * pl_d) * fin)


def zoom_continuo(rng, cortes=(7, 6, 5, 5, 5, 4, 4, 4)):
    """(1.9.0, la persona eligio de 5 propuestas la «Continuo»; los barridos sintetizados de la primera no le gustaron)
    El riser cinematografico de la biblioteca (Epidemic Sound, con licencia) con su climax (2,10 s) justo en el impacto
    de las fotos, y encima el impacto de las rampas. None si falta el riser: sin el, sfx.momentos pone la rampa de
    siempre."""
    ruta = os.path.join(AUDIO, RISER)
    if not os.path.isfile(ruta):
        return None
    fotos = sum(cortes) / 24.0
    largo = fotos + 2.6
    x = np.zeros((int(largo * FS), 2))
    seg = _normal(_leer(ruta)[int((2.10 - fotos - 0.02) * FS):int(2.75 * FS)], -2.0)[:len(x)].copy()
    fi, fo = int(0.15 * FS), int(0.25 * FS)
    seg[:fi] *= np.linspace(0.0, 1.0, fi)[:, None]
    seg[-fo:] *= np.linspace(1.0, 0.0, fo)[:, None]
    x[:len(seg)] += seg
    x += 0.9 * _normal(_impacto(rng, fotos, largo), -3.0)
    return _normal(x, -4.0)


# una rampa por tipo de intro (los mismos ritmos que build_trailers.INTROS; sfx.momentos elige por el ritmo de las fotos)
RAMPAS = {"XV_RAMPA": (5,) * 8, "XV_RAMPA_ACELERA": (9, 7, 6, 5, 4, 4, 3, 2), "XV_RAMPA_FRENA": (2, 3, 4, 4, 5, 6, 7, 9),
          "XV_RAMPA_LATIDO": (7, 3, 7, 3, 7, 3, 7, 3)}
SONIDOS = {"XV_GOLPE": golpe, "XV_SUBIDA": subida, "XV_BRILLO": brillo, "XV_PASO": paso, "XV_OBTURADOR": obturador}
for _n, _c in RAMPAS.items():
    SONIDOS[_n] = (lambda rng, c=_c: rampa(rng, c))
CON_LICENCIA = {"XV_RAMPA_ZOOM": zoom_continuo}      # -> recursos/audio (la intro «Zoom»: 7,6,5,5,5,4,4,4)


def guardar(nombre, x, destino=None):
    ruta = os.path.join(destino or DESTINO, nombre + ".wav")
    datos = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(datos.tobytes())
    return ruta


def main():
    os.makedirs(DESTINO, exist_ok=True)
    solo = {a.upper() for a in sys.argv[1:]}          # (1.9.0) hacer_sfx.py XV_RAMPA_ZOOM: solo ese (misma semilla)
    todos = [(n, h, DESTINO) for n, h in SONIDOS.items()] + [(n, h, AUDIO) for n, h in CON_LICENCIA.items()]
    for k, (nombre, hacer, destino) in enumerate(todos):
        if solo and nombre not in solo:
            continue
        x = hacer(np.random.default_rng(2026 + k))
        if x is None:
            print("%-16s no se hizo: falta su sonido de la biblioteca (recursos/audio)" % (nombre + ".wav"))
            continue
        ruta = guardar(nombre, x, destino)
        print("%-16s %.2f s  pico %.1f dB  %d KB  (%s)" % (nombre + ".wav", len(x) / float(FS),
                                                          20 * np.log10(np.abs(x).max() + 1e-12),
                                                          os.path.getsize(ruta) // 1024, os.path.basename(destino)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
