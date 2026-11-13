# -*- coding: utf-8 -*-
"""
ruido.py - Reduccion de ruido universal con intensidad ajustable (0 a 100).

Genera el DCTL "XV_REDUCCION_RUIDO.dctl" con la fuerza elegida y lo deja en la carpeta de LUTs de Resolve.
Como todos los clips de todas las timelines usan ese mismo archivo en su nodo "REDUCCION DE RUIDO",
cambiar la intensidad y volver a aplicarlo actualiza todo a la vez. 0 = DCTL transparente (sin efecto).
"""
import os

import rutas
DIR_LUT_MCP = rutas.DIR_LUT_MCP
ARCHIVO = "XV_REDUCCION_RUIDO.dctl"
RUTA_RESOLVE = "MCP/" + ARCHIVO
DEFECTO = 60


def nivel(intensidad):
    i = int(intensidad)
    return "Apagada" if i <= 0 else "Suave" if i <= 30 else "Media" if i <= 65 else "Fuerte"


def parametros(intensidad):
    s = max(0, min(100, int(intensidad))) / 100.0
    return {"luma": round(0.6 * s, 3), "croma": round(min(1.0, 1.7 * s), 3), "borde": round(0.025 + 0.035 * s, 4)}


TRANSPARENTE = """// XV - REDUCCION DE RUIDO apagada (intensidad 0): deja pasar la imagen tal cual.
__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B)
{
    return make_float3(p_R, p_G, p_B);
}
"""


def fuente(intensidad):
    if int(intensidad) <= 0:
        return TRANSPARENTE
    p = parametros(intensidad)
    return """// XV - REDUCCION DE RUIDO (universal, nodo de cada clip) - intensidad %d (%s)
// Generado por el programa Trailer XV automatico. Filtro bilateral 5x5 que respeta los bordes:
// limpia el ruido de color (croma) y, mas suave, el de luz (luma).

__CONSTANT__ float SIGMA_BORDE = %ff;
__CONSTANT__ float FUERZA_LUMA = %ff;
__CONSTANT__ float FUERZA_CROMA = %ff;

__DEVICE__ float luma(float r, float g, float b)
{
    return 0.2126f * r + 0.7152f * g + 0.0722f * b;
}

__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, __TEXTURE__ p_TexR, __TEXTURE__ p_TexG, __TEXTURE__ p_TexB)
{
    float r0 = _tex2D(p_TexR, p_X, p_Y);
    float g0 = _tex2D(p_TexG, p_X, p_Y);
    float b0 = _tex2D(p_TexB, p_X, p_Y);
    float y0 = luma(r0, g0, b0);
    float inv_borde = 1.0f / (2.0f * SIGMA_BORDE * SIGMA_BORDE);
    float inv_croma = 1.0f / (8.0f * SIGMA_BORDE * SIGMA_BORDE);
    float sy = 0.0f, wy = 0.0f, scb = 0.0f, scr = 0.0f, wc = 0.0f;
    for (int dy = -2; dy <= 2; dy++)
    {
        int y = p_Y + dy;
        y = y < 0 ? 0 : (y >= p_Height ? p_Height - 1 : y);
        for (int dx = -2; dx <= 2; dx++)
        {
            int x = p_X + dx;
            x = x < 0 ? 0 : (x >= p_Width ? p_Width - 1 : x);
            float r = _tex2D(p_TexR, x, y);
            float g = _tex2D(p_TexG, x, y);
            float b = _tex2D(p_TexB, x, y);
            float yy = luma(r, g, b);
            float d2 = (float)(dx * dx + dy * dy);
            float dl = yy - y0;
            float w = _expf(-d2 / 4.5f) * _expf(-dl * dl * inv_borde);
            sy += w * yy;
            wy += w;
            float w2 = _expf(-d2 / 8.0f) * _expf(-dl * dl * inv_croma);
            scb += w2 * (b - yy);
            scr += w2 * (r - yy);
            wc += w2;
        }
    }
    float yf = y0 + FUERZA_LUMA * (sy / wy - y0);
    float cb = (b0 - y0) + FUERZA_CROMA * (scb / wc - (b0 - y0));
    float cr = (r0 - y0) + FUERZA_CROMA * (scr / wc - (r0 - y0));
    float r1 = cr + yf;
    float b1 = cb + yf;
    float g1 = (yf - 0.2126f * r1 - 0.0722f * b1) / 0.7152f;
    return make_float3(r1, g1, b1);
}
""" % (int(intensidad), nivel(intensidad), p["borde"], p["luma"], p["croma"])


def escribir(intensidad, copia_en=None):
    """Escribe el DCTL en la carpeta de LUTs de Resolve (y una copia opcional). Devuelve la ruta."""
    texto = fuente(int(intensidad))
    destinos = [DIR_LUT_MCP] + ([copia_en] if copia_en else [])
    for d in destinos:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ARCHIVO), "w", encoding="utf-8") as f:
            f.write(texto)
    return os.path.join(DIR_LUT_MCP, ARCHIVO)


def es_video(item):
    mpi = item.GetMediaPoolItem()
    if mpi is None:
        return False
    ruta = (mpi.GetClipProperty("File Path") or "").lower()
    return not ruta.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".webp"))


def aplicar_a_item(item, intensidad):
    """El nodo 1 del clip lleva la reduccion de ruido (este DCTL) y la igualacion de color (CDL):
    nunca se apaga; con intensidad 0 el DCTL es transparente."""
    g = item.GetNodeGraph()
    if g is None:
        return False
    ok = g.SetLUT(1, RUTA_RESOLVE)
    g.SetNodeLabel(1, "REDUCCION DE RUIDO")
    g.SetNodeEnabled(1, True)
    return bool(ok)
