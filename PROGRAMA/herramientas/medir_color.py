# -*- coding: utf-8 -*-
"""
medir_color.py - (1.8.1, la persona: «al colorizar satura o expone demasiado... usa el vectorscopio o la forma de onda
para medir») Compara, plano por plano, el VIDEO FINAL contra la TOMA ORIGINAL en el mismo instante, con las medidas de
los monitores de DaVinci:

  forma de onda (luz Rec.709 0-1): p50 (medios), p99 (altas), % quemado (> 0,98) y % aplastado (< 0,02)
  vectorscopio: saturacion (radio Cb/Cr) p50 y p95, % fuera del 75 % (radio > 0,30) y dominante de color de los
  grises (Cb, Cr medios de lo casi neutro: 0 = blanco limpio)

Marca QUEMA si el final quema mas que la toma, SATURA si su saturacion p95 pasa la de la toma, DOMINANTE si los grises
quedan teñidos, OSCURO/CLARO si los medios se fueron lejos de lo tipico. Sin cambiar nada en DaVinci (solo lee la linea).

  python PROGRAMA/herramientas/medir_color.py "<linea>" "<video final>" [hoja.jpg]
"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))
import rutas  # noqa: E402

ANCHO = 640
QUEMADO, APLASTADO = 0.98, 0.02
FUERA_75 = 0.30                       # radio Cb/Cr del 75 % de las barras (amarillo/cian ~0,33; aqui un poco antes)


def cuadro(ruta, t, ancho=ANCHO):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % max(0.0, t), "-i", ruta,
                        "-frames:v", "1", "-vf", "scale=%d:-2:flags=area,format=rgb24" % ancho, "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
    b = r.stdout
    if not b or len(b) % (ancho * 3):
        return None
    return np.frombuffer(b, np.uint8).reshape(-1, ancho, 3).astype(np.float32) / 255.0


def sin_franjas(img):
    """Quita las franjas negras de arriba/abajo (Cine Bars) para no contarlas como negros aplastados."""
    filas = img.mean(axis=(1, 2))
    vivas = (filas > 0.03).nonzero()[0]
    if len(vivas) < img.shape[0] * 0.5:
        return img
    return img[vivas[0]:vivas[-1] + 1]


def medidas(img):
    import numpy as np
    img = sin_franjas(img)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cb, cr = (b - y) / 1.8556, (r - y) / 1.5748
    rad = np.sqrt(cb * cb + cr * cr)
    neutro = (rad < 0.04) & (y > 0.25) & (y < 0.9)
    return {"y50": float(np.percentile(y, 50)), "y99": float(np.percentile(y, 99)),
            "quem": float((y > QUEMADO).mean() * 100), "aplast": float((y < APLASTADO).mean() * 100),
            "s50": float(np.percentile(rad, 50)), "s95": float(np.percentile(rad, 95)),
            "s95r": float(np.percentile(rad / (y + 0.10), 95)),       # (1.8.7) color relativo a la luz
            "fuera": float((rad > FUERA_75).mean() * 100),
            "cb": float(cb[neutro].mean()) if neutro.sum() > 200 else 0.0,
            "cr": float(cr[neutro].mean()) if neutro.sum() > 200 else 0.0}


def problemas(src, out):
    p = []
    if out["quem"] > max(1.0, src["quem"] * 1.5 + 0.5):
        p.append("QUEMA")
    # (1.8.7) como color_guardia: el radio Cb/Cr crece al aclarar sin que el color se vea mas vivo; se compara el
    # color relativo a la luz (y lo que pasa del 75 %)
    if out["s95r"] > src["s95r"] * 1.06 + 0.01 or out["fuera"] > src["fuera"] + 0.5:
        p.append("SATURA")
    if max(abs(out["cb"]), abs(out["cr"])) > 0.025 and max(abs(out["cb"]), abs(out["cr"])) > \
            max(abs(src["cb"]), abs(src["cr"])):
        p.append("DOMINANTE")
    if out["y50"] < 0.18:
        p.append("OSCURO")
    if out["y50"] > 0.68:
        p.append("CLARO")
    if out["aplast"] > max(3.0, src["aplast"] * 2 + 1):
        p.append("NEGROS")
    return p


def planos(nombre_linea):
    """[(tl_ini, tl_fin, ruta, src_medio_s, encima)] de la pista de VIDEOS de esa linea (solo lee DaVinci)."""
    import motor
    r = motor._dvr().scriptapp("Resolve")
    p = r.GetProjectManager().GetCurrentProject()
    tl = next((p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1)
               if p.GetTimelineByIndex(i).GetName() == nombre_linea), None)
    if tl is None:
        raise SystemExit("No encuentro la linea «%s» en %s" % (nombre_linea, p.GetName()))
    fps = float(tl.GetSetting("timelineFrameRate") or 24)
    st = tl.GetStartFrame()
    out = []
    capas = {}
    for v in range(2, tl.GetTrackCount("video") + 1):
        nombre = tl.GetTrackName("video", v)
        for it in tl.GetItemListInTrack("video", v) or []:
            capas.setdefault(nombre, []).append((it.GetStart(), it.GetEnd(), it.GetName()))
    for it in tl.GetItemListInTrack("video", 1) or []:
        m = it.GetMediaPoolItem()
        ruta = (m.GetClipProperty("File Path") or "") if m else ""
        if not ruta or ruta.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        cfps = float(m.GetClipProperty("FPS") or fps) or fps
        a, b = it.GetStart(), it.GetEnd()
        if b - a < 8:
            continue
        sm = (it.GetSourceStartFrame() + it.GetSourceEndFrame()) / 2.0 / cfps
        medio = (a + b) / 2.0
        encima = sorted({"%s:%s" % (n, x[2]) for n, xs in capas.items() for x in xs if x[0] <= medio < x[1]})
        out.append(((a - st) / fps, (b - st) / fps, ruta, sm, encima))
    return out, fps


def main():
    import numpy as np
    if len(sys.argv) < 3:
        print(__doc__)
        return
    linea, video = sys.argv[1], sys.argv[2]
    hoja = sys.argv[3] if len(sys.argv) > 3 else None
    lista, _ = planos(linea)
    filas, tiras = [], []
    print("%-34s %5s | %-26s | %-26s | %-14s %s" % ("plano (s)", "", "LUZ  medios/altas/quem%", "SAT  p50/p95/fuera%",
                                                       "grises Cb/Cr", "problemas"))
    for k, (a, b, ruta, sm, encima) in enumerate(lista):
        t = (a + b) / 2.0
        o, s = cuadro(video, t), cuadro(ruta, sm)
        if o is None or s is None:
            continue
        mo, ms = medidas(o), medidas(s)
        pr = problemas(ms, mo)
        filas.append((a, ruta, ms, mo, pr, encima))
        print("%5.1f %-28s toma | %.2f %.2f %4.1f%% neg %4.1f%% | %.3f %.3f %4.1f%%          | %+.3f %+.3f" % (
            a, os.path.basename(ruta)[:28], ms["y50"], ms["y99"], ms["quem"], ms["aplast"], ms["s50"], ms["s95"],
            ms["fuera"], ms["cb"], ms["cr"]))
        print("%5s %-28s final| %.2f %.2f %4.1f%% neg %4.1f%% | %.3f %.3f %4.1f%%          | %+.3f %+.3f  %s %s" % (
            "", "", mo["y50"], mo["y99"], mo["quem"], mo["aplast"], mo["s50"], mo["s95"], mo["fuera"], mo["cb"], mo["cr"],
            " ".join(pr) or "ok", ("[" + ", ".join(encima)[:60] + "]") if encima else ""))
        if hoja:
            h = min(o.shape[0], s.shape[0])
            tiras.append(np.concatenate([s[:h], o[:h]], axis=1))
    n = len(filas)
    if n:
        def cuenta(x):
            return sum(1 for f in filas if x in f[4])
        print("\n%d planos: QUEMA %d · SATURA %d · DOMINANTE %d · OSCURO %d · CLARO %d · NEGROS %d" % (
            n, cuenta("QUEMA"), cuenta("SATURA"), cuenta("DOMINANTE"), cuenta("OSCURO"), cuenta("CLARO"), cuenta("NEGROS")))
        for clave in ("y50", "y99", "quem", "s50", "s95", "fuera"):
            print("  %-5s toma %.3f -> final %.3f (mediana)" % (
                clave, float(np.median([f[2][clave] for f in filas])), float(np.median([f[3][clave] for f in filas]))))
    if hoja and tiras:
        from PIL import Image
        w = max(t.shape[1] for t in tiras)
        tiras = [np.pad(t, ((0, 0), (0, w - t.shape[1]), (0, 0))) for t in tiras]
        Image.fromarray((np.concatenate(tiras[:24], axis=0) * 255).astype(np.uint8)).save(hoja, quality=85)
        print("hoja (izquierda la toma, derecha el final):", hoja)


if __name__ == "__main__":
    main()
