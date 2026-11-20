# -*- coding: utf-8 -*-
"""
recorte.py - RECORTE DE PERSONA local (sin internet): de un tramo de video saca a la gente con transparencia.

(17-nov, la persona: «aplica Magic Mask para transiciones o captions») La Mascara Magica de DaVinci no se puede manejar
por script (pide marcar a la persona a mano). Esto hace lo mismo por fuera: el modelo RVM (Robust Video Matting,
recursos/modelos/rvm_mobilenetv3_fp32.onnx, 14 MB) corre con onnxruntime en el procesador y da el alfa de cada cuadro;
ffmpeg lo une al video y sale un .mov ProRes 4444 CON transparencia: solo la gente. Puesto en una pista ENCIMA de un
titulo, el texto queda DETRAS de la persona.

    recortar(video, salida_mov, ini_s, dur_s) -> {"cuadros", "cobertura" (parte del cuadro que es persona, 0-1),
                                                  "centro" (cobertura en la franja central, donde va el texto)}

    python PROGRAMA/armado/recorte.py <video> <salida.mov> [ini_s dur_s]        prueba suelta
"""
import os
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nucleo"))
import rutas

MODELO = os.path.join(rutas.RECURSOS, "modelos", "rvm_mobilenetv3_fp32.onnx")
ANCHO_IA = 768                     # el alfa se calcula a este ancho (o alto, en vertical) y se sube al del video
_sesion = None


def disponible():
    if not os.path.exists(MODELO):
        return False
    try:
        import onnxruntime  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _sesion_ia():
    global _sesion
    if _sesion is None:
        import onnxruntime as ort
        op = ort.SessionOptions()
        op.intra_op_num_threads = max(2, (os.cpu_count() or 4) - 2)
        _sesion = ort.InferenceSession(MODELO, sess_options=op, providers=["CPUExecutionProvider"])
    return _sesion


def _tamano(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "csv=p=0", video], capture_output=True, text=True,
                       timeout=60, creationflags=rutas.SIN_VENTANA)
    w, h, fr = [x for x in r.stdout.strip().splitlines() if x.strip()][0].strip().split(",")[:3]
    a, b = (fr.split("/") + ["1"])[:2]
    return int(w), int(h), float(a) / float(b or 1)


def recortar(video, salida, ini_s=0.0, dur_s=None, log=print):
    """El tramo [ini_s, ini_s + dur_s] de `video`, solo la gente, a `salida` (.mov ProRes 4444 con alfa)."""
    import numpy as np
    w, h, fps = _tamano(video)
    k = ANCHO_IA / float(max(w, h))
    wi, hi = int(round(w * k / 2.0)) * 2, int(round(h * k / 2.0)) * 2
    tramo = ["-ss", "%.3f" % ini_s] + (["-t", "%.3f" % dur_s] if dur_s else [])
    lee = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error"] + tramo + ["-i", video, "-vf",
                            "scale=%d:%d:flags=bilinear" % (wi, hi), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE, creationflags=rutas.SIN_VENTANA)
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    escribe = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + tramo + ["-i", video, "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", "%dx%d" % (wi, hi), "-r", "%.6f" % fps, "-i", "-", "-filter_complex",
         "[1:v]scale=%d:%d:flags=bicubic,format=gray[a];[0:v]format=yuv444p10le[v];[v][a]alphamerge" % (w, h),
         "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-an", "-shortest", salida],
        stdin=subprocess.PIPE, creationflags=rutas.SIN_VENTANA)
    s = _sesion_ia()
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    baja = np.array([0.5 if max(wi, hi) > 512 else 1.0], np.float32)
    n, cob, cen, tam = 0, 0.0, 0.0, wi * hi * 3
    try:
        while True:
            b = lee.stdout.read(tam)
            if len(b) < tam:
                break
            src = (np.frombuffer(b, np.uint8).reshape(hi, wi, 3).transpose(2, 0, 1)[None].astype(np.float32)) / 255.0
            _, pha, *rec = s.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                        "downsample_ratio": baja})
            a = pha[0, 0]
            a = np.clip((a - 0.08) / 0.84, 0.0, 1.0)             # sin velo: lo casi transparente fuera, lo casi solido, solido
            cob += float(a.mean())
            cen += float(a[int(hi * 0.3):int(hi * 0.7), int(wi * 0.2):int(wi * 0.8)].mean())
            escribe.stdin.write((a * 255.0 + 0.5).astype(np.uint8).tobytes())
            n += 1
    finally:
        try:
            escribe.stdin.close()
        except Exception:
            pass
        lee.kill()
        escribe.wait()
    if not n or not os.path.exists(salida):
        return None
    return {"cuadros": n, "cobertura": round(cob / n, 3), "centro": round(cen / n, 3), "fps": fps}


def alfas(video, tiempos, ancho=ANCHO_IA, previos=5):
    """{t: alfa (alto x ancho, 0-1)} de la gente en esos segundos de `video`, sin escribir nada. (19-nov) Para decidir
    ANTES de recortar todo el tramo (~5 cuadros/s) si el texto detras se va a poner: RVM es recurrente, asi que cada
    punto se calienta con `previos` cuadros anteriores (con 0 el primer alfa sale flojo)."""
    import numpy as np
    w, h, fps = _tamano(video)
    k = ancho / float(max(w, h))
    wi, hi = int(round(w * k / 2.0)) * 2, int(round(h * k / 2.0)) * 2
    s, out = _sesion_ia(), {}
    baja = np.array([0.5 if max(wi, hi) > 512 else 1.0], np.float32)     # (revision) igual que recortar()
    for t in tiempos:
        ini = max(0.0, t - previos / float(fps or 24))
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % ini, "-i", video, "-frames:v", str(previos + 1),
                            "-vf", "scale=%d:%d:flags=bilinear" % (wi, hi), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA)
        rec, a, tam = [np.zeros((1, 1, 1, 1), np.float32)] * 4, None, wi * hi * 3
        for i in range(len(r.stdout) // tam):
            src = np.frombuffer(r.stdout[i * tam:(i + 1) * tam], np.uint8).reshape(hi, wi, 3).transpose(2, 0, 1)[None]
            _, pha, *rec = s.run(None, {"src": src.astype(np.float32) / 255.0, "r1i": rec[0], "r2i": rec[1],
                                        "r3i": rec[2], "r4i": rec[3], "downsample_ratio": baja})
            a = np.clip((pha[0, 0] - 0.08) / 0.84, 0.0, 1.0)
        if a is not None:
            out[t] = a
    return out


if __name__ == "__main__":
    import time
    t0 = time.time()
    a = sys.argv[1:]
    r = recortar(a[0], a[1], float(a[2]) if len(a) > 2 else 0.0, float(a[3]) if len(a) > 3 else None)
    print(r, "en %.1f s" % (time.time() - t0))
