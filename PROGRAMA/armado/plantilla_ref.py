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
BN_CROMA = 0.012               # (1.9.6) color medio por debajo de esto: plano en blanco y negro
LUZ_DESTELLO = 0.11            # (1.9.6) pico de brillo (0-1) en un cambio de plano: entra con luz
CALIDO_DESTELLO = 0.07         # o pico de calidez (rojo - azul): luz naranja
TRANS_MIN_S, TRANS_MAX_S = 0.2, 1.5    # lo que puede durar un fundido medido
PLANO_LARGO_S = 6.0            # (1.9.6) un hueco mas largo se parte...
PARTE_LARGA_S = 3.5            # ...en partes de unos 3,5 s que entran en fundido


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


def _franjas(ruta, dur):
    """(1.9.6, «denis y iris»: tráiler de cine 2.39:1 dentro de 16:9) 'crop=w:h:x:y' de las franjas negras que el
    video trae fijas (cropdetect a 1 cuadro por segundo, el recorte que mas se repite), o '' si no tiene."""
    from collections import Counter
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", ruta, "-vf", "fps=1,cropdetect=24:2:0", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600, creationflags=rutas.SIN_VENTANA)
    vistos = Counter(re.findall(r"crop=(\d+:\d+:\d+:\d+)", p.stderr or ""))
    if not vistos:
        return ""
    w, h, x, y = (int(v) for v in vistos.most_common(1)[0][0].split(":"))
    # el mas grande de los que se repiten (en una escena oscura cropdetect recorta de mas)
    comunes = [tuple(int(v) for v in k.split(":")) for k, c in vistos.items() if c >= 0.1 * sum(vistos.values())]
    w, h, x, y = max(comunes, key=lambda c: c[0] * c[1]) if comunes else (w, h, x, y)
    return "crop=%d:%d:%d:%d" % (w, h, x, y) if w >= 16 and h >= 16 else ""


def _cuadros(ruta, fps, vertical=True, recorte=""):
    """[(histograma normalizado (48), brillo 0-1)] de cada cuadro."""
    import numpy as np
    # (1.9.6) el cuadro de analisis va en la orientacion del video y lleno de imagen (sin relleno ni franjas negras):
    # un video horizontal en 64 x 112 era 1/3 imagen y 2/3 negro, y con franjas de cine menos de 1/4; los cambios de
    # plano no llegaban al UMBRAL y el brillo medio parecia «final en negro» (denis y iris: 2 planos en 2:55)
    w, h = (W, H) if vertical else (H, W)
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-vf",
                        "fps=%g,%sscale=%d:%d" % (fps, recorte + "," if recorte else "", w, h),
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, timeout=900, creationflags=rutas.SIN_VENTANA)
    n = len(p.stdout) // (w * h * 3)
    if n < 2:
        return np.zeros((0, 48)), np.zeros(0), np.zeros((0, 112))
    a = np.frombuffer(p.stdout[:n * w * h * 3], np.uint8).reshape(n, h * w, 3)
    hist = np.concatenate([np.stack([np.bincount(c, minlength=16) for c in (a[:, :, k] >> 4)]) for k in range(3)], 1)
    hist = hist.astype(np.float32) / float(h * w * 3)
    brillo = a.mean(axis=(1, 2)) / 255.0
    _cuadros.calido = (a[:, :, 0].astype(np.float32) - a[:, :, 2]).mean(axis=1) / 255.0   # (1.9.6) rojo - azul
    # (1.9.6) cuanto color tiene cada cuadro (Cb y Cr de video, 0-1; un cuadro en blanco y negro da ~0) y una muestra
    # cada medio segundo para medir el color de la referencia (look_ref)
    croma = np.zeros(n, np.float32)
    for i in range(0, n, 400):
        x = a[i:i + 400].astype(np.float32) / 255.0
        y = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        croma[i:i + 400] = np.sqrt(((x[..., 2] - y) * 0.5389) ** 2 + ((x[..., 0] - y) * 0.6350) ** 2).mean(axis=1)
    _cuadros.croma = croma
    _cuadros.muestra = a[::max(1, int(round(fps / 2.0)))].astype(np.float32) / 255.0
    # (18-nov, plantilla 1: fundidos lentos entre planos del mismo color rosa) la FORMA de la imagen: gris de 8 x 14,
    # sin su brillo medio (un destello no cuenta como otra forma)
    filas, cols = (14, 8) if vertical else (8, 14)
    g = a.reshape(n, h, w, 3).mean(axis=3).reshape(n, filas, h // filas, cols, w // cols).mean(axis=(2, 4))
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
    recorte = _franjas(ruta, dur)
    hist, brillo, forma = _cuadros(ruta, fps, alto > ancho, recorte)
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
    # (1.9.6, la persona: «las transiciones y destellos TAL CUAL como el video») en «denis y iris» la luz (blanca o
    # naranja) entra DURANTE el fundido: un pico de luz o de calidez que sube sobre lo de antes Y lo de despues
    # (un fundido de una toma oscura a una clara solo sube: no cuenta). Medido mirando los cuadros: 20,5 24,5 40,9 52,9
    # 92,9 125,7 134 s eran destellos; con LUZ_DESTELLO 0,11 / CALIDO_DESTELLO 0,07 salen esos y pocos de mas.
    calido = getattr(_cuadros, "calido", np.zeros(n))
    luz_en, durs = {}, {}
    wl = max(2, int(round(0.6 * fps)))               # la luz se busca a +-0,6 s y se compara con 0,6-2,4 s antes/despues
    for f in exactos:
        def pico(serie):
            antes = np.median(serie[max(0, f - 4 * wl):max(1, f - wl)])
            despues = np.median(serie[f + wl:f + 4 * wl + 1]) if f + wl < n else antes
            return float(serie[max(0, f - wl):f + wl + 1].max() - max(antes, despues))
        luz_en[f] = pico(brillo) >= LUZ_DESTELLO or pico(calido) >= CALIDO_DESTELLO
        # lo que dura el fundido: donde el cambio sigue en la mitad de su pico (menos la ventana de medida)
        a0 = b0 = f
        while a0 > 0 and cambio[a0 - 1] >= 0.5 * cambio[f]:
            a0 -= 1
        while b0 < n - 1 and cambio[b0 + 1] >= 0.5 * cambio[f]:
            b0 += 1
        durs[f] = min(TRANS_MAX_S, max(TRANS_MIN_S, (b0 - a0 - 2 * w) / fps))
    limites = [0] + exactos + [util]
    lista = []
    for k in range(len(limites) - 1):
        a, b = limites[k], limites[k + 1]
        if b - a < 1:
            continue
        # (1.9.6, «denis y iris»: 1:16-1:31 eran fundidos tan suaves entre tomas parecidas que no se ven: un hueco de
        # 15,7 s salia como UNA toma quieta del evento) un hueco de mas de PLANO_LARGO_S se parte en partes iguales de
        # unos PARTE_LARGA_S que entran en fundido (con tomas del evento queda vivo, como la referencia)
        partes = max(1, int(round((b - a) / fps / PARTE_LARGA_S))) if (b - a) / fps > PLANO_LARGO_S else 1
        for j in range(partes):
            a2, b2 = a + (b - a) * j // partes, a + (b - a) * (j + 1) // partes
            pl = {"ini": round(a2 / fps, 3), "fin": round(b2 / fps, 3), "dur": round((b2 - a2) / fps, 3),
                  "entra": (formas[k] if k < len(formas) else "corte") if j == 0 else "fundido"}
            if j == 0 and a in durs:
                pl["trans"] = round(durs[a], 2)          # segundos del fundido del original
                if luz_en.get(a) and pl["entra"] != "destello":
                    pl["luz"] = True                     # y entra con luz (destello encima del fundido)
            lista.append(pl)
    # (1.9.6, «pule más, no es igual al ejemplo») los planos en BLANCO Y NEGRO de la referencia (casi sin color en
    # su mitad central) y el COLOR del resto (look_ref: luz, contraste y tono en Lab) para llevarlo a las tomas
    croma = getattr(_cuadros, "croma", None)
    color_ref = None
    if croma is not None and len(croma) == n:
        for pl in lista:
            i0, i1 = int(pl["ini"] * fps), int(pl["fin"] * fps)
            m = croma[i0 + (i1 - i0) // 4:i1 - (i1 - i0) // 4 + 1]
            if len(m) and float(np.median(m)) < BN_CROMA:
                pl["bn"] = True
        try:
            import look_ref
            muestra = getattr(_cuadros, "muestra", None)
            paso = max(1, int(round(fps / 2.0)))
            if muestra is not None:
                color = [muestra[k] for k in range(len(muestra))
                         if k * paso < util and croma[min(n - 1, k * paso)] >= BN_CROMA]
                color_ref = look_ref.estadisticas(color)
                # (1.9.6, «mejora el blanco y negro») la luz y el contraste de SUS planos en blanco y negro
                bn = [muestra[k] for k in range(len(muestra))
                      if k * paso < util and croma[min(n - 1, k * paso)] < BN_CROMA]
                if color_ref is not None and len(bn) >= 6:
                    color_ref["bn"] = look_ref.estadisticas(bn)
        except Exception:
            color_ref = None
    return {"dur": round(dur, 3), "fps": round(fps, 3), "ancho": ancho, "alto": alto, "vertical": alto > ancho,
            "con_audio": con_audio, "planos": lista, "final": round(final_f / fps, 2), "franjas": recorte,
            "color_ref": color_ref}


def importar(ruta, nombre=None, log=print, seccion=None):
    """Convierte el video en plantilla (musica + cortes + portada). Devuelve el info.json guardado. seccion="trailer":
    una plantilla del TRÁILER (se elige en Tráilers, no en Plantillas)."""
    info = detectar(ruta)
    nombre = _nombre_limpio(nombre or ruta)
    dest = os.path.join(carpeta(), nombre)
    os.makedirs(dest, exist_ok=True)
    info.update({"nombre": nombre, "origen": os.path.abspath(ruta)})
    if seccion:
        info["seccion"] = seccion
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


def lista(todas=False):
    """[info] de las plantillas importadas, por nombre. (1.9.6) Las de Tráilers (info «seccion» = «trailer», p. ej. la
    PLANTILLA 2 del tráiler hecha de «denis y iris») no salen en la página Plantillas: solo con todas=True (el armado)."""
    out = []
    base = carpeta()
    if not os.path.isdir(base):
        return out
    for n in sorted(os.listdir(base)):
        try:
            with open(os.path.join(base, n, "info.json"), encoding="utf-8") as f:
                d = json.load(f)
            d["carpeta"] = os.path.join(base, n)
            if todas or d.get("seccion") != "trailer":
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
