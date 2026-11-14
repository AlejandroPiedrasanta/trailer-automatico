# -*- coding: utf-8 -*-
"""
ruido.py - Reduccion de ruido de cada toma, con la fuerza que pide SU ruido. El mismo proceso para cualquier video.

Cada video se mide (analisis/ruido_tomas.py) y recibe uno de 5 niveles en el nodo 1 de su clip ("REDUCCION DE RUIDO"):
    N1 limpia · N2 poco ruido · N3 ruido medio · N4 ruido alto · N5 ruido muy alto
Cada nivel es un DCTL (XV_RUIDO_N1.dctl ... N5) con el mismo filtro bilateral que respeta los bordes, mas abierto y mas
fuerte cuanto mas ruido: limpia siempre el ruido de color y, en la luz, con toda la fuerza solo en las sombras (donde
vive el ruido); en los tonos medios nunca pasa de LUMA_MEDIOS para no borrar textura. Ninguna toma se queda sin filtro.

Por que niveles: con un solo filtro para todo, las tomas limpias perdian detalle y las ruidosas quedaban a medias.
Medido con ruido puesto a proposito (PSNR contra la toma limpia): una toma limpia con N1 queda 1.2 dB mejor que con el
filtro unico de antes; con ruido de 5.6/255, N5 da +3 dB y con 8.9/255, +3.9 dB.

El control «Quitar ruido» (0 a 100, 60 de fabrica) sube o baja un nivel o dos a todas las tomas; 0 lo apaga.
XV_REDUCCION_RUIDO.dctl se sigue escribiendo (equivale a N2) para las lineas armadas con versiones anteriores.
"""
import os

import rutas
DIR_LUT_MCP = rutas.DIR_LUT_MCP
ARCHIVO = "XV_REDUCCION_RUIDO.dctl"
RUTA_RESOLVE = "MCP/" + ARCHIVO
DEFECTO = 60
#          borde   luma   croma  paso  grueso
# paso 2 = recoge de mas lejos (manchas grandes); grueso = cuanto usa esa limpieza amplia para la LUZ de las sombras
NIVELES = {1: (0.016, 0.18, 0.85, 1, 0.0), 2: (0.026, 0.40, 1.00, 1, 0.0), 3: (0.040, 0.58, 1.00, 2, 0.5),
           4: (0.058, 0.76, 1.00, 2, 0.7), 5: (0.085, 0.90, 1.00, 2, 0.85)}
NOMBRES = {0: "apagada", 1: "limpia", 2: "poco ruido", 3: "ruido medio", 4: "ruido alto", 5: "ruido muy alto"}
# medida de ruido_tomas x1000 -> de N1 a N5. Con ruido puesto a proposito: 0.8/255 da 5 a 6; 1.5/255, 9 a 11;
# 3.1/255, 16 a 20; 5.6/255, 28 a 36. Una toma limpia da de 2.5 a 3.6.
UMBRALES = (5.0, 9.0, 16.0, 28.0)
LUMA_MEDIOS = 0.40                          # tope de la limpieza de luz fuera de las sombras, en cualquier nivel
NIVEL_SIN_MEDIDA = 2                        # si un video no se pudo medir


def archivo(n):
    return "XV_RUIDO_N%d.dctl" % int(n)


def ruta_resolve(n):
    return "MCP/" + archivo(n) if int(n) > 0 else RUTA_RESOLVE


def nivel(intensidad):
    i = int(intensidad)
    return "Apagada" if i <= 0 else "Suave" if i <= 40 else "Normal" if i <= 70 else "Fuerte"


def ajuste(intensidad):
    """Cuantos niveles sube o baja el control «Quitar ruido»."""
    i = int(intensidad)
    return -2 if i <= 15 else -1 if i <= 40 else 0 if i <= 70 else 1 if i <= 90 else 2


def nivel_base(medida):
    """Nivel (1 a 5) que pide el ruido medido de un video."""
    if not medida:
        return NIVEL_SIN_MEDIDA
    s = 1000.0 * max(float(medida.get("luz") or 0), float(medida.get("sombra") or 0))
    return 1 + sum(s >= u for u in UMBRALES)


def nivel_para(medida, intensidad):
    """Nivel final de un video: 0 = apagada (control en 0); si no, de 1 a 5."""
    if int(intensidad) <= 0:
        return 0
    return max(1, min(5, nivel_base(medida) + ajuste(intensidad)))


TRANSPARENTE = """// XV - REDUCCION DE RUIDO apagada (intensidad 0): deja pasar la imagen tal cual.
__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B)
{
    return make_float3(p_R, p_G, p_B);
}
"""

PLANTILLA = """// XV - REDUCCION DE RUIDO nivel @N@ de 5 (@NOMBRE@). Nodo 1 de cada clip.
// Generado por el programa Trailer automatico. Filtro bilateral 5x5 que respeta los bordes:
// limpia el ruido de color (croma) y el de luz (luma), este mas en las sombras que en las altas luces.

__CONSTANT__ float SIGMA_BORDE = @BORDE@f;
__CONSTANT__ float FUERZA_LUMA = @LUMA@f;
__CONSTANT__ float FUERZA_CROMA = @CROMA@f;
__CONSTANT__ int PASO_CROMA = @PASO@;
__CONSTANT__ float GRUESO_LUMA = @GRUESO@f;
__CONSTANT__ float LUMA_MEDIOS = @MEDIOS@f;

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
    float sy = 0.0f, wy = 0.0f, scb = 0.0f, scr = 0.0f, wc = 0.0f, sg = 0.0f, wg = 0.0f;
    for (int dy = -2; dy <= 2; dy++)
    {
        for (int dx = -2; dx <= 2; dx++)
        {
            float d2 = (float)(dx * dx + dy * dy);
            int x = p_X + dx;
            int y = p_Y + dy;
            x = x < 0 ? 0 : (x >= p_Width ? p_Width - 1 : x);
            y = y < 0 ? 0 : (y >= p_Height ? p_Height - 1 : y);
            float yy = luma(_tex2D(p_TexR, x, y), _tex2D(p_TexG, x, y), _tex2D(p_TexB, x, y));
            float dl = yy - y0;
            float w = _expf(-d2 / 4.5f) * _expf(-dl * dl * inv_borde);
            sy += w * yy;
            wy += w;
            int xc = p_X + dx * PASO_CROMA;
            int yc = p_Y + dy * PASO_CROMA;
            xc = xc < 0 ? 0 : (xc >= p_Width ? p_Width - 1 : xc);
            yc = yc < 0 ? 0 : (yc >= p_Height ? p_Height - 1 : yc);
            float r = _tex2D(p_TexR, xc, yc);
            float g = _tex2D(p_TexG, xc, yc);
            float b = _tex2D(p_TexB, xc, yc);
            float yv = luma(r, g, b);
            float dc = yv - y0;
            float w2 = _expf(-d2 / 8.0f) * _expf(-dc * dc * inv_croma);
            scb += w2 * (b - yv);
            scr += w2 * (r - yv);
            wc += w2;
            float w3 = _expf(-d2 / 8.0f) * _expf(-dc * dc * inv_borde);
            sg += w3 * yv;
            wg += w3;
        }
    }
    // La fuerza entera del nivel solo en las sombras (1 en lo oscuro, 0 desde 0.35): ahi vive el ruido. En los tonos
    // medios nunca pasa de LUMA_MEDIOS, para no borrar textura (hojas, tela, pelo) aunque el nivel sea alto, y en las
    // altas luces baja otro 30 por ciento.
    float sombra = _saturatef((0.35f - y0) / 0.25f);
    float medios = _fminf(FUERZA_LUMA, LUMA_MEDIOS);
    float fl = (medios + (FUERZA_LUMA - medios) * sombra) * (1.0f - 0.30f * _saturatef((y0 - 0.60f) / 0.40f));
    // en las sombras, la luz tambien se limpia con las muestras lejanas: quita el ruido de manchas de las tomas de noche
    float yb = sy / wy;
    yb = yb + GRUESO_LUMA * sombra * (sg / wg - yb);
    float yf = y0 + fl * (yb - y0);
    float cb = (b0 - y0) + FUERZA_CROMA * (scb / wc - (b0 - y0));
    float cr = (r0 - y0) + FUERZA_CROMA * (scr / wc - (r0 - y0));
    float r1 = cr + yf;
    float b1 = cb + yf;
    float g1 = (yf - 0.2126f * r1 - 0.0722f * b1) / 0.7152f;
    return make_float3(r1, g1, b1);
}
"""


def fuente(n):
    """Texto del DCTL del nivel n (0 = transparente)."""
    n = int(n)
    if n <= 0:
        return TRANSPARENTE
    n = max(1, min(5, n))
    borde, luma, croma, paso, grueso = NIVELES[n]
    cambios = {"@N@": str(n), "@NOMBRE@": NOMBRES[n], "@BORDE@": "%.4f" % borde, "@LUMA@": "%.3f" % luma,
               "@CROMA@": "%.3f" % croma, "@PASO@": str(int(paso)), "@GRUESO@": "%.3f" % grueso, "@MEDIOS@": "%.3f" % LUMA_MEDIOS}
    texto = PLANTILLA
    for clave, valor in cambios.items():
        texto = texto.replace(clave, valor)
    return texto


def escribir(intensidad, copia_en=None):
    """Escribe los DCTL de los 5 niveles (y el de siempre) en la carpeta de LUTs de Resolve, y una copia opcional.
    Devuelve la ruta del de siempre."""
    textos = {archivo(n): fuente(n) for n in NIVELES}
    textos[ARCHIVO] = fuente(nivel_para(None, intensidad))       # lineas de versiones anteriores: nivel 2 +- el control
    for d in [DIR_LUT_MCP] + ([copia_en] if copia_en else []):
        os.makedirs(d, exist_ok=True)
        for nombre, texto in textos.items():
            with open(os.path.join(d, nombre), "w", encoding="utf-8") as f:
                f.write(texto)
    return os.path.join(DIR_LUT_MCP, ARCHIVO)


def es_video(item):
    mpi = item.GetMediaPoolItem()
    if mpi is None:
        return False
    ruta = (mpi.GetClipProperty("File Path") or "").lower()
    return not ruta.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".webp"))


def aplicar_a_item(item, intensidad, medida=None):
    """El nodo 1 del clip lleva la reduccion de ruido (el DCTL de su nivel) y la igualacion de color (CDL):
    nunca se apaga; con el control en 0 el DCTL es transparente."""
    g = item.GetNodeGraph()
    if g is None:
        return False
    n = nivel_para(medida, intensidad)
    ok = g.SetLUT(1, ruta_resolve(n))
    g.SetNodeLabel(1, "REDUCCION DE RUIDO" + (" N%d" % n if n else ""))
    g.SetNodeEnabled(1, True)
    return bool(ok)
