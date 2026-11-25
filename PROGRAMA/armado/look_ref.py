# -*- coding: utf-8 -*-
"""
look_ref.py - (1.9.6) El COLOR de un video de referencia llevado a las tomas del evento.

La persona (24-nov, con «denis y iris» como Plantilla 2 del tráiler): «pule más la plantilla, no es igual al ejemplo».
Lado a lado, lo que mas se notaba era el color: la referencia es oscura, con contraste, verdes profundos y piel calida;
lo nuestro salia claro y plano. Aqui:

    estadisticas(imagenes)        -> {"media": [L, a, b], "desv": [L, a, b]} (Lab, imagenes RGB 0-1)
    escribir_lut(evento, ref, ruta) la LUT 3D (.cube, 33) que lleva lo del evento a lo de la referencia: transferencia
                                   de color de Reinhard en Lab (media y contraste de cada canal), con topes: el contraste
                                   de luz entre 0,75 y 1,5 veces y el color NUNCA mas saturado que la camara (regla del
                                   proyecto: la saturacion solo baja); el tono (calido / verde) se mueve un 80 % hacia el
                                   de la referencia.

Las imagenes van en el espacio de la toma (Rec.709, gamma ~2,4 de pantalla): se tratan como sRGB, que es lo que se ve.
"""
import os

import numpy as np

FUERZA = 0.85                      # cuanto se acerca (1 = igual a la referencia)
TONO = 0.8                         # parte del cambio de tono (a, b medios) que se aplica
CONTRASTE = (0.75, 1.5)            # topes del cambio de contraste de la luz
LADO = 33


def _lineal(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _gamma(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_MI = np.linalg.inv(_M)
_BLANCO = np.array([0.95047, 1.0, 1.08883])


def a_lab(rgb):
    """rgb (..., 3) 0-1 -> Lab (..., 3)."""
    xyz = _lineal(np.asarray(rgb, np.float64)) @ _M.T / _BLANCO
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def a_rgb(lab):
    fy = (lab[..., 0] + 16) / 116.0
    fx, fz = fy + lab[..., 1] / 500.0, fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > 0.2069, f ** 3, (f - 16 / 116.0) / 7.787) * _BLANCO
    return _gamma(xyz @ _MI.T)


def estadisticas(imagenes, max_px=400000):
    """Media y desviacion de L, a, b de un grupo de imagenes RGB 0-1 (sin las casi negras ni las quemadas)."""
    px = []
    for im in imagenes:
        if im is None:
            continue
        a = np.asarray(im, np.float32).reshape(-1, 3)
        paso = max(1, len(a) // max(1, max_px // max(1, len(imagenes))))
        px.append(a[::paso])
    if not px:
        return None
    lab = a_lab(np.concatenate(px))
    lab = lab[(lab[:, 0] > 3) & (lab[:, 0] < 99)]
    if len(lab) < 100:
        return None
    return {"media": [round(float(v), 3) for v in lab.mean(0)], "desv": [round(float(v), 3) for v in lab.std(0)]}


def transferir(lab, ev, ref, fuerza=FUERZA):
    me, de = np.array(ev["media"]), np.maximum(np.array(ev["desv"]), 1e-3)
    mr, dr = np.array(ref["media"]), np.array(ref["desv"])
    out = lab.copy()
    kl = float(np.clip(dr[0] / de[0], *CONTRASTE))
    out[..., 0] = (lab[..., 0] - me[0]) * kl + mr[0]
    kc = min(1.0, float(np.sqrt((dr[1] ** 2 + dr[2] ** 2) / (de[1] ** 2 + de[2] ** 2))))   # nunca mas saturado
    for c in (1, 2):
        out[..., c] = (lab[..., c] - me[c]) * kc + me[c] + TONO * (mr[c] - me[c])
    return lab + fuerza * (out - lab)


def escribir_lut(ev, ref, ruta, lado=LADO):
    """La LUT .cube que lleva el color del evento (ev) al de la referencia (ref). Devuelve la ruta."""
    g = np.linspace(0.0, 1.0, lado)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")         # en .cube el rojo cambia mas rapido
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = np.clip(a_rgb(transferir(a_lab(rgb), ev, ref)), 0.0, 1.0)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta + ".tmp", "w", encoding="ascii") as f:
        f.write("TITLE \"%s\"\nLUT_3D_SIZE %d\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n" % (os.path.basename(ruta), lado))
        f.write("\n".join("%.6f %.6f %.6f" % tuple(v) for v in out) + "\n")
    os.replace(ruta + ".tmp", ruta)
    return ruta


FOTOS_MUESTRA = 36


def de_fotos(items, cuantas=FOTOS_MUESTRA):
    """(1.9.6, «como la foto del evento») El color de las FOTOS del evento (las que sirven, repartidas a lo largo del
    dia): {"media", "desv"} en Lab, o None si hay menos de 6. Cada foto se lee chica (PIL draft: rapido en JPG)."""
    fotos = [i for i in items if i.get("tipo") == "foto" and not i.get("descartar") and i.get("ruta")
             and os.path.exists(i["ruta"])]
    if len(fotos) < 6:
        return None
    fotos.sort(key=lambda i: str(i.get("hora") or ""))
    paso = max(1, len(fotos) // cuantas)
    imgs = []
    try:
        from PIL import Image
    except Exception:
        return None
    for i in fotos[::paso][:cuantas]:
        try:
            with Image.open(i["ruta"]) as im:
                im.draft("RGB", (320, 320))
                im = im.convert("RGB")
                im.thumbnail((320, 320))
                imgs.append(np.asarray(im, np.float32) / 255.0)
        except Exception:
            pass
    return estadisticas(imgs) if len(imgs) >= 6 else None


CONTRASTE_BN = (0.9, 1.8)          # el blanco y negro puede ganar mas contraste (negros profundos, blancos limpios)


def escribir_lut_bn(ev, ref, ruta, lado=LADO):
    """(1.9.6, la persona: «mejora el blanco y negro») LUT de BLANCO Y NEGRO de cine: la luz (L de Lab) de las tomas
    llevada a la media y el contraste de los planos en blanco y negro de la referencia, NEUTRO (sin tinte: a = b = 0),
    con una curva suave que no aplasta los negros ni quema los blancos. ev / ref: {"media", "desv"} (solo cuenta L)."""
    g = np.linspace(0.0, 1.0, lado)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    lab = a_lab(rgb)
    me, de = float(ev["media"][0]), max(1e-3, float(ev["desv"][0]))
    mr, dr = float(ref["media"][0]), float(ref["desv"][0])
    # el blanco y negro de «denis y iris» es de noche (luz 28): una toma de dia llevada ahi quedaria a oscuras; la luz
    # va a medio camino y el contraste es el de la referencia
    mr = 0.5 * (me + mr)
    k = float(np.clip(dr / de, *CONTRASTE_BN))
    L = (lab[..., 0] - me) * k + mr
    # curva de pelicula: entra suave en 0 y en 100 (los negros conservan detalle, los blancos no se queman)
    t = np.clip(L / 100.0, 0.0, 1.0)
    L = 100.0 * (t * t * (3.0 - 2.0 * t) * 0.35 + t * 0.65)
    out = np.clip(a_rgb(np.stack([L, np.zeros_like(L), np.zeros_like(L)], -1)), 0.0, 1.0)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta + ".tmp", "w", encoding="ascii") as f:
        f.write("TITLE \"%s\"\nLUT_3D_SIZE %d\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n" % (os.path.basename(ruta), lado))
        f.write("\n".join("%.6f %.6f %.6f" % tuple(v) for v in out) + "\n")
    os.replace(ruta + ".tmp", ruta)
    return ruta


def aplicar_cdl(img, cdl):
    """La imagen como queda con el CDL del plano (Slope, Offset, Power, Saturation de DaVinci)."""
    try:
        s = np.array([float(v) for v in str(cdl.get("Slope", "1 1 1")).split()])
        o = np.array([float(v) for v in str(cdl.get("Offset", "0 0 0")).split()])
        p = np.array([float(v) for v in str(cdl.get("Power", "1 1 1")).split()])
        sat = float(cdl.get("Saturation", 1.0))
    except (TypeError, ValueError):
        return img
    x = np.power(np.clip(img * s + o, 0.0, 1.0), p)
    y = (x * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    return np.clip(y + (x - y) * sat, 0.0, 1.0)
