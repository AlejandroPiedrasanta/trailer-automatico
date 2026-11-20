# -*- coding: utf-8 -*-
"""
plantilla_ref.py - (18-nov) Un video de referencia (un Reel / TikTok / CapCut) convertido en PLANTILLA.

La persona (18-nov): «te daré videos que quiero que los conviertas en plantillas y detectes los cortes para poner mis
videos, y usa la música de cada plantilla, ya no le metas otra música; crea una sección para escoger qué plantilla quiero
usar en la página de Material».

De cada video se guarda, en DATOS/plantillas_ref/<nombre>/:
    musica.m4a      su audio tal cual (es LA musica del video que sale)
    portada.jpg     el cuadro mas representativo (para la tarjeta de Material)
    info.json       {"nombre", "origen", "dur", "fps", "ancho", "alto", "vertical",
                     "planos": [{"ini", "fin", "dur", "entra": "inicio"|"corte"|"destello"|"fundido"}],
                     "final": segundos del final con logo sobre negro (se cambia por la tarjeta final) o 0}

LOS CORTES. Las plantillas de CapCut cortan con cortes secos, DESTELLOS de luz (blanco o naranja) y FUNDIDOS: el detector
de escenas de ffmpeg (scdet) no veia ninguno en una y en otra daba planos de 23 s (medido). Aqui:
  1. cada cuadro, chico (64 px) y en color: histograma (3 x 16) y brillo;
  2. CAMBIO(t) = distancia entre el histograma de 0,4 s ANTES y el de 0,4 s DESPUES (mas largo que un destello): alto
     solo si el contenido de verdad cambio, venga como venga el cambio; un paneo o un destello dentro del mismo plano no;
  3. picos de CAMBIO separados al menos PLANO_MIN_S; el corte va al cuadro exacto: el mayor salto de un cuadro al
     siguiente (corte seco), el pico de brillo (destello) o la mitad del cambio (fundido).
"""
import json
import os
import re
import shutil
import subprocess

import rutas

W, H = 64, 112                 # cuadro de analisis (vertical); se escala sin deformar mas de la cuenta
VENTANA_S = 0.4                # antes / despues para medir el cambio de contenido
UMBRAL = 0.30                  # distancia de histogramas (0-1) que ya es otro plano
PLANO_MIN_S = 0.45
SALTO_SECO = 0.22              # cambio entre DOS cuadros vecinos: corte seco
DESTELLO = 0.16                # el brillo sube esto sobre lo de alrededor: destello
NEGRO = 0.09                   # brillo medio de un cuadro «negro con logo»
FINAL_MIN_S = 1.5
FORMA_PESO = 1.0               # peso del cambio de forma frente al de color
FUNDIDO_MIN_S = 0.9            # un plano que entra en fundido dura al menos esto


def carpeta():
    return os.path.join(rutas.DATOS, "plantillas_ref")


def _nombre_limpio(n):
    n = re.sub(r"[^\w\- ]+", "", os.path.splitext(os.path.basename(n))[0]).strip().upper()
    return re.sub(r"\s+", " ", n) or "PLANTILLA"


def _probe(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation",
                        "-of", "json", ruta], capture_output=True, text=True, timeout=60, creationflags=rutas.SIN_VENTANA)
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams") or [] if s.get("codec_type") == "video"), {})
    a = any(s.get("codec_type") == "audio" for s in j.get("streams") or [])
    num, _, den = (v.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    ancho, alto = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = [d.get("rotation") for d in v.get("side_data_list") or [] if "rotation" in d]
    if rot and abs(int(float(rot[0]))) % 180 == 90:
        ancho, alto = alto, ancho
    return float((j.get("format") or {}).get("duration") or 0), fps, ancho, alto, a


def _cuadros(ruta, fps):
    """[(histograma normalizado (48), brillo 0-1)] de cada cuadro."""
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-vf",
                        "fps=%g,scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:-1:-1" % (fps, W, H, W, H),
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, timeout=600, creationflags=rutas.SIN_VENTANA)
    n = len(p.stdout) // (W * H * 3)
    if n < 2:
        return np.zeros((0, 48)), np.zeros(0), np.zeros((0, 112))
    a = np.frombuffer(p.stdout[:n * W * H * 3], np.uint8).reshape(n, H * W, 3)
    hist = np.concatenate([np.stack([np.bincount(c, minlength=16) for c in (a[:, :, k] >> 4)]) for k in range(3)], 1)
    hist = hist.astype(np.float32) / float(H * W * 3)
    brillo = a.mean(axis=(1, 2)) / 255.0
    # (18-nov, plantilla 1: fundidos lentos entre planos del mismo color rosa) la FORMA de la imagen: gris de 8 x 14,
    # sin su brillo medio (un destello no cuenta como otra forma)
    g = a.reshape(n, H, W, 3).mean(axis=3).reshape(n, 14, H // 14, 8, W // 8).mean(axis=(2, 4))
    g = g.reshape(n, -1) - g.reshape(n, -1).mean(axis=1, keepdims=True)
    g /= (np.linalg.norm(g, axis=1, keepdims=True) + 1e-6)
    return hist, brillo, g


def _distancia(a, b):
    import numpy as np
    return 0.5 * np.abs(a - b).sum(axis=-1)          # 0 = igual, 1 = nada en comun


def detectar(ruta):
    """(info sin guardar). Los planos del video con su forma de entrar y el final con logo."""
    import numpy as np
    dur, fps, ancho, alto, con_audio = _probe(ruta)
    hist, brillo, forma = _cuadros(ruta, fps)
    n = len(brillo)
    if n < 4:
        raise RuntimeError("no se pudieron leer los cuadros de %s" % os.path.basename(ruta))
    w = max(2, int(round(VENTANA_S * fps)))

    def dist(i, j):                                  # color O forma: lo que mas cambie
        return np.maximum(_distancia(hist[i], hist[j]), FORMA_PESO * (1.0 - (forma[i] * forma[j]).sum(axis=-1)) / 2.0)
    vecino = np.zeros(n)
    vecino[1:] = dist(np.arange(1, n), np.arange(0, n - 1))
    cambio = np.zeros(n)
    t = np.arange(w, n - w)
    cambio[w:n - w] = dist(t - w, t + w)
    # brillo de alrededor (mediana de una ventana ancha) para ver destellos
    fondo = np.array([np.median(brillo[max(0, t - 3 * w):t + 3 * w + 1]) for t in range(n)])
    # final con logo: los ultimos cuadros casi negros
    final_f = 0
    for t in range(n - 1, -1, -1):
        if brillo[t] > NEGRO:
            break
        final_f += 1
    if final_f / fps < FINAL_MIN_S:
        final_f = 0
    util = n - final_f
    # picos de cambio
    cortes, minimo = [], int(PLANO_MIN_S * fps)
    orden = sorted((t for t in range(w, util - w) if cambio[t] >= UMBRAL), key=lambda t: -cambio[t])
    for t in orden:
        if all(abs(t - c) >= minimo for c in cortes):
            cortes.append(t)
    cortes.sort()
    exactos, formas, ini = [], ["inicio"], 0
    for c in cortes:                                 # el cuadro exacto y la forma de entrar del plano que empieza
        zona = range(max(1, c - w), min(util, c + w + 1))
        seco = max(zona, key=lambda t: vecino[t])
        pico = max(zona, key=lambda t: brillo[t] - fondo[t])
        if brillo[pico] - fondo[pico] >= DESTELLO:
            f, entra = pico, "destello"
        elif vecino[seco] >= SALTO_SECO:
            f, entra = seco, "corte"
        else:
            f, entra = c, "fundido"
        if f - ini < (FUNDIDO_MIN_S * fps if entra == "fundido" else minimo) or util - f < minimo:
            continue                                 # (un fundido dejaba planitos de 0,4 s: su principio y su final)
        exactos.append(f)
        formas.append(entra)
        ini = f
    limites = [0] + exactos + [util]
    lista = []
    for k in range(len(limites) - 1):
        a, b = limites[k], limites[k + 1]
        if b - a < 1:
            continue
        lista.append({"ini": round(a / fps, 3), "fin": round(b / fps, 3), "dur": round((b - a) / fps, 3),
                      "entra": formas[k] if k < len(formas) else "corte"})
    return {"dur": round(dur, 3), "fps": round(fps, 3), "ancho": ancho, "alto": alto, "vertical": alto > ancho,
            "con_audio": con_audio, "planos": lista, "final": round(final_f / fps, 2)}


def importar(ruta, nombre=None, log=print):
    """Convierte el video en plantilla (musica + cortes + portada). Devuelve el info.json guardado."""
    info = detectar(ruta)
    nombre = _nombre_limpio(nombre or ruta)
    dest = os.path.join(carpeta(), nombre)
    os.makedirs(dest, exist_ok=True)
    info.update({"nombre": nombre, "origen": os.path.abspath(ruta)})
    if info["con_audio"]:
        musica = os.path.join(dest, "musica.m4a")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", ruta, "-vn", "-c:a", "copy", musica],
                           capture_output=True, timeout=300, creationflags=rutas.SIN_VENTANA)
        # (1.8.0, auditoria) un audio que no cabe en .m4a (Opus de un webm, PCM de un .mov) dejaba un archivo de 0 bytes
        # que SI existia: la plantilla quedaba muda. Ahora se convierte si ffmpeg fallo o el archivo salio vacio
        if r.returncode != 0 or not os.path.exists(musica) or os.path.getsize(musica) < 1000:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", ruta, "-vn", "-c:a", "aac", "-b:a", "256k", musica],
                           capture_output=True, timeout=300, creationflags=rutas.SIN_VENTANA)
        if not os.path.exists(musica) or os.path.getsize(musica) < 1000:
            log("Aviso: no se pudo sacar la música de %s: la plantilla queda sin su canción." % os.path.basename(ruta))
    # portada: el medio del plano mas largo
    largo = max(info["planos"], key=lambda p: p["dur"]) if info["planos"] else {"ini": 0, "dur": 0}
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % (largo["ini"] + largo["dur"] / 2), "-i", ruta,
                    "-frames:v", "1", "-vf", "scale=-2:640", os.path.join(dest, "portada.jpg")],
                   capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
    try:
        shutil.copy2(ruta, os.path.join(dest, "referencia" + os.path.splitext(ruta)[1].lower()))
    except OSError:
        pass
    with open(os.path.join(dest, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    log("Plantilla «%s»: %.1f s, %d planos (%s)%s." % (
        nombre, info["dur"], len(info["planos"]),
        ", ".join("%d %s" % (sum(1 for p in info["planos"] if p["entra"] == e), e)
                  for e in ("corte", "destello", "fundido") if any(p["entra"] == e for p in info["planos"])),
        "; final con logo de %.1f s" % info["final"] if info["final"] else ""))
    return info


def lista():
    """[info] de las plantillas importadas, por nombre."""
    out = []
    base = carpeta()
    if not os.path.isdir(base):
        return out
    for n in sorted(os.listdir(base)):
        try:
            with open(os.path.join(base, n, "info.json"), encoding="utf-8") as f:
                d = json.load(f)
            d["carpeta"] = os.path.join(base, n)
            out.append(d)
        except (OSError, ValueError):
            pass
    return out


if __name__ == "__main__":                      # python plantilla_ref.py video1.mov [video2.mov ...]: solo detectar
    import sys
    for r in sys.argv[1:]:
        d = detectar(r)
        print("== %s: %.1f s, %d planos, final %.1f s" % (os.path.basename(r), d["dur"], len(d["planos"]), d["final"]))
        print("   " + "  ".join("%.1f(%s)" % (p["dur"], p["entra"][0]) for p in d["planos"]))
