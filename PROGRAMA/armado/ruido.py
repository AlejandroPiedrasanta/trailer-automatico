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
NOMBRES = {0: "apagada", 1: "limpia", 2: "poco ruido", 3: "ruido medio", 4: "ruido alto", 5: "ruido muy alto",
           "davinci": "con el ruido de DaVinci"}
# El ruido propio de DaVinci Studio (temporal y espacial) limpia mucho mas que un DCTL, pero no se puede configurar por
# API. La persona lo deja UNA vez a su gusto en un clip (pagina Color) y aqui se guarda ese grado (.drx): al armar se
# aplica a todas las tomas, el mismo para cualquier video, y el DCTL del nodo 1 queda transparente (N0).
DIR_DAVINCI = os.path.join(rutas.DATOS, "ruido_davinci")
RUTA_DRX = os.path.join(DIR_DAVINCI, "ruido.drx")
RUTA_DRX_INFO = os.path.join(DIR_DAVINCI, "ruido.json")
ETIQUETA_DAVINCI = "RUIDO DE DAVINCI"
# medida de ruido_tomas x1000 -> de N1 a N5. Con ruido puesto a proposito: 0.8/255 da 5 a 6; 1.5/255, 9 a 11;
# 3.1/255, 16 a 20; 5.6/255, 28 a 36. Una toma limpia da de 2.5 a 3.6.
UMBRALES = (5.0, 9.0, 16.0, 28.0)
LUMA_MEDIOS = 0.32                          # tope de la limpieza de luz fuera de las sombras (19-nov: 0,40 -> 0,32, mas textura de piel y pelo; con la nitidez, mismo grano)
# (19-nov, la persona: «un poco de nitidez») realce de bordes por nivel: (fuerza, umbral del ruido que queda). Mas en las
# tomas limpias, casi nada en las ruidosas (ahi realzaria el grano). TOPE: lo maximo que mueve un pixel (sin halos).
NITIDEZ = {1: (0.55, 0.004), 2: (0.45, 0.005), 3: (0.32, 0.007), 4: (0.20, 0.010), 5: (0.10, 0.014)}
TOPE_NITIDEZ = 0.035
NIVEL_SIN_MEDIDA = 2                        # si un video no se pudo medir


def archivo(n):
    return "XV_RUIDO_N%d.dctl" % int(n)


def ruta_resolve(n):
    return "MCP/" + archivo(n) if int(n) > 0 else RUTA_RESOLVE


def drx_activo(intensidad=DEFECTO):
    """Ruta del ajuste de ruido de DaVinci guardado, o None si no hay o si «Quitar ruido» esta en 0."""
    return RUTA_DRX if int(intensidad) > 0 and os.path.isfile(RUTA_DRX) else None


def estado_davinci():
    """Lo guardado: {"hay", "fecha", "clip", "linea", "herramientas", "de_ruido"}."""
    import json
    info = {"hay": os.path.isfile(RUTA_DRX)}
    if info["hay"]:
        try:
            with open(RUTA_DRX_INFO, encoding="utf-8") as f:
                info.update(json.load(f))
        except Exception:
            pass
        info["hay"] = True
    return info


def quitar_davinci():
    for r in (RUTA_DRX, RUTA_DRX_INFO):
        try:
            os.remove(r)
        except OSError:
            pass


def es_de_ruido(herramienta):
    """¿Ese renglon de «herramientas del nodo» es la reduccion de ruido? Viene en el idioma de DaVinci
    («Reducción de ruido», «Noise Reduction»...). El DCTL del programa («LUT: XV_RUIDO_N3») no cuenta."""
    t = str(herramienta).lower()
    if t.startswith("lut"):
        return False
    return any(p in t for p in ("ruido", "noise", "denois", "rausch", "bruit", "rumore", "ruído"))


def capturar_de_resolve(resolve, log=print):
    """Guarda el grado del clip que DaVinci tiene bajo el cursor (donde la persona dejo el ruido a su gusto).
    Devuelve lo mismo que estado_davinci(). Lanza RuntimeError con un mensaje claro si no se puede."""
    import glob
    import json
    import shutil
    import time
    p = resolve.GetProjectManager().GetCurrentProject()
    tl = p.GetCurrentTimeline() if p else None
    if tl is None:
        raise RuntimeError("Abre en DaVinci la línea de tiempo donde dejaste el ruido a tu gusto.")
    item = tl.GetCurrentVideoItem()
    if item is None or not es_video(item):
        raise RuntimeError("Pon el cursor de DaVinci sobre el clip de video donde ajustaste el ruido.")
    g = item.GetNodeGraph()
    herramientas = []
    for n in range(1, int(g.GetNumNodes() or 0) + 1):
        herramientas += [str(t) for t in (g.GetToolsInNode(n) or [])]
    alb = p.GetGallery().GetCurrentStillAlbum()
    still = tl.GrabStill()
    if not still or alb is None:
        raise RuntimeError("DaVinci no dejó capturar ese clip: abre la página Color sobre él y vuelve a intentar.")
    tmp = os.path.join(DIR_DAVINCI, "captura")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    try:
        ok = alb.ExportStills([still], tmp, "ruido", "drx")
    finally:
        try:
            alb.DeleteStills([still])                # la captura no se queda en la galeria de la persona
        except Exception:
            pass
    drx = sorted(glob.glob(os.path.join(tmp, "*.drx")), key=os.path.getmtime)
    if not ok or not drx:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("DaVinci no pudo guardar el ajuste de ese clip.")
    os.replace(drx[-1], RUTA_DRX)
    shutil.rmtree(tmp, ignore_errors=True)
    info = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "clip": item.GetName(), "linea": tl.GetName(),
            "herramientas": herramientas, "de_ruido": [t for t in herramientas if es_de_ruido(t)]}
    with open(RUTA_DRX_INFO, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    log("Ajuste de ruido de DaVinci guardado del clip %s (%s)." % (info["clip"], ", ".join(info["de_ruido"]) or
                                                                  "sin reducción de ruido a la vista"))
    return estado_davinci()


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
__CONSTANT__ float NITIDEZ = @NITIDEZ@f;
__CONSTANT__ float UMBRAL_NITIDEZ = @UMBRAL@f;
__CONSTANT__ float TOPE_NITIDEZ = @TOPE@f;

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
    float sy = 0.0f, wy = 0.0f, scb = 0.0f, scr = 0.0f, wc = 0.0f, sg = 0.0f, wg = 0.0f, sd = 0.0f, wd = 0.0f;
    float sn = 0.0f, wn = 0.0f;
    // la nitidez se mide a la escala que se VE: una toma 4K va a una linea HD (la mitad), asi que de 2 en 2 pixeles
    int esc = p_Width > 2600 ? 2 : 1;
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
            float wd0 = _expf(-d2 / 4.5f);
            float w = wd0 * _expf(-dl * dl * inv_borde);
            sy += w * yy;
            wy += w;
            int xn = p_X + dx * esc;             // nitidez: la zona a la escala que se ve, limpia (bilateral) y desenfocada
            int yn = p_Y + dy * esc;
            xn = xn < 0 ? 0 : (xn >= p_Width ? p_Width - 1 : xn);
            yn = yn < 0 ? 0 : (yn >= p_Height ? p_Height - 1 : yn);
            float yq = luma(_tex2D(p_TexR, xn, yn), _tex2D(p_TexG, xn, yn), _tex2D(p_TexB, xn, yn));
            float dq = yq - y0;
            float wq = wd0 * _expf(-dq * dq * inv_borde);
            sn += wq * yq;
            wn += wq;
            sd += wd0 * yq;
            wd += wd0;
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
    // (19-nov, la persona: «un poco de nitidez para mejorar la calidad») NITIDEZ de bordes, no de grano: el detalle es
    // la imagen ya limpia (el bilateral respeta los bordes) menos la desenfocada; lo que no pasa de UMBRAL_NITIDEZ es
    // ruido que quedo y no se toca; nunca mueve mas de TOPE_NITIDEZ (sin halos) y en las sombras va a la mitad.
    float det = sn / wn - sd / wd;
    float mag = _fabs(det);
    det = det * _saturatef((mag - UMBRAL_NITIDEZ) / UMBRAL_NITIDEZ);
    float realce = NITIDEZ * (1.0f - 0.5f * sombra) * det;
    yf = yf + _clampf(realce, -TOPE_NITIDEZ, TOPE_NITIDEZ);
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
    nitidez, umbral = NITIDEZ[n]
    cambios = {"@N@": str(n), "@NOMBRE@": NOMBRES[n], "@BORDE@": "%.4f" % borde, "@LUMA@": "%.3f" % luma,
               "@CROMA@": "%.3f" % croma, "@PASO@": str(int(paso)), "@GRUESO@": "%.3f" % grueso, "@MEDIOS@": "%.3f" % LUMA_MEDIOS,
               "@NITIDEZ@": "%.3f" % nitidez, "@UMBRAL@": "%.4f" % umbral, "@TOPE@": "%.3f" % TOPE_NITIDEZ}
    texto = PLANTILLA
    for clave, valor in cambios.items():
        texto = texto.replace(clave, valor)
    return texto


def escribir(intensidad, copia_en=None):
    """Escribe los DCTL de los 5 niveles (y el de siempre) en la carpeta de LUTs de Resolve, y una copia opcional.
    Devuelve la ruta del de siempre."""
    textos = {archivo(n): fuente(n) for n in NIVELES}
    textos[archivo(0)] = TRANSPARENTE                            # cuando el ruido lo quita DaVinci (ajuste guardado)
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


def aplicar(item, intensidad, medida=None, drx=None):
    """Pone la reduccion de ruido de un clip. Devuelve como quedo: "davinci", el nivel (0 a 5) o None si no se pudo.
    Con `drx` (el ajuste de DaVinci guardado) se aplica ese grado y el DCTL del nodo 1 queda transparente; si DaVinci
    no lo acepta, el clip sigue con el filtro del programa. El nodo 1 lleva tambien la igualacion de color (CDL), que
    el armado vuelve a poner despues: el grado guardado trae la del clip donde se capturo."""
    g = item.GetNodeGraph()
    if g is None:
        return None
    if drx and int(intensidad) > 0:
        try:
            aplicado = g.ApplyGradeFromDRX(drx, 0)
        except Exception:
            aplicado = False
        if aplicado:
            g = item.GetNodeGraph() or g
            g.SetLUT(1, "MCP/" + archivo(0))
            g.SetNodeLabel(1, ETIQUETA_DAVINCI)
            g.SetNodeEnabled(1, True)
            return "davinci"
    n = nivel_para(medida, intensidad)
    ok = g.SetLUT(1, ruta_resolve(n))
    # (1.8.1) el nombre dice el ORDEN de la cadena: 1 base del grupo -> 2 este nodo (balance/exposicion del CDL y el
    # ruido de la toma) -> 3 look del grupo
    g.SetNodeLabel(1, "2 BALANCE Y EXPOSICION + RUIDO" + (" N%d" % n if n else ""))
    g.SetNodeEnabled(1, True)
    return n if ok else None


def aplicar_a_item(item, intensidad, medida=None):
    """Como aplicar(), solo con el filtro del programa. Devuelve True si se pudo."""
    return aplicar(item, intensidad, medida) is not None


def resumen(cuenta):
    """{como quedo: cuantos clips} -> «12 limpia, 30 poco ruido» (para el registro)."""
    return ", ".join("%d %s" % (cuenta[k], NOMBRES.get(k, str(k))) for k in sorted(cuenta, key=str))
