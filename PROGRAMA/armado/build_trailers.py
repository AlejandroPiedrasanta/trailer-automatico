# -*- coding: utf-8 -*-
"""
build_trailers.py - Arma un evento en las 4 plantillas del TRAILER DE XV (DaVinci Resolve Studio 21).

Usa el analisis de analizar_material.py (fotos y videos por hora, clasificados en MAQUILLAJE / IGLESIA /
FIESTA, con la calidad de cada medio segundo de video). Por cada plantilla "TRAILER XV - 1min/3min/15min/30min":
  1. La duplica como "<EVENTO> - 1min", etc. La plantilla NO se toca.
  2. Intro (pista V2): 8 fotos de 5 frames, con los whoosh de la plantilla. Solo esas 8 fotos.
  3. Zonas en V1 segun los marcadores de la plantilla:
       APERTURA (fin de las fotos -> MAQUILLAJE): resumen con las mejores tomas de todo el evento
       MAQUILLAJE / IGLESIA / FIESTA: videos de ese momento en orden; IGLESIA y FIESTA abren con dron
     Elige las mejores tomas (nitidas, bien expuestas, sin temblor) y corta al ritmo de la musica.
  4. Acabado: transiciones (fundido a negro entre momentos, encadenados suaves en las versiones largas,
     fundido final), titulos con diseno (letra script + subtitulo, sombra, animacion y fundidos),
     whoosh en cada cambio de momento, LUT de color activado.
  5. Clasifica por colores: media pool en carpetas MAQUILLAJE / IGLESIA / FIESTA y cada clip con su
     color (morado / verde / rosa), tambien en la timeline.
  6. Sin audio original. Deja el render en cola en EVENTO TERMINADO - <EVENTO>\\VIDEO TERMINADO (no lo inicia).

Se ejecuta dentro de Resolve: desde el programa (motor.py) o con el MCP (run_script_unsafe).
Variables opcionales antes de ejecutar: EVENTO, SOLO, REHACER, DRY_RUN, NOMBRE_XV, FRASE, FECHA_LUGAR.
"""
import os
import re
import math
import time
import bisect
import random
import datetime
import importlib.util
from concurrent.futures import ThreadPoolExecutor

# ============================ CONFIGURACION ============================
import rutas                                     # carpetas del programa y de Resolve (Windows y Mac)
BASE = rutas.BASE
SKILL_DIR = rutas.PROGRAMA

# corte = (min, max) s por plano en las zonas; apertura = idem en el resumen inicial (mas rapido).
# tr = transiciones en frames: zona (fundido a negro entre momentos), suave (encadenado) en suaves_en,
#      final (fundido a negro al terminar). (16-nov) La persona vio feo el encadenado en TODOS los cortes («tiene un
#      efecto raro, las transiciones se ven feo»: doble imagen a cada rato): dentro de cada momento se corta al ritmo
#      y el encadenado va solo donde ayuda: al entrar o salir de una camara lenta o una foto, y entre dos planos con
#      un salto fuerte de luz (transiciones()). suaves_en queda vacio (se puede volver a poner por momento).
ZONAS_TODAS = ["MAQUILLAJE", "IGLESIA", "FIESTA"]
VERSIONES = [
    {"plantilla": "TRAILER XV - 1min", "sufijo": "1min", "seg": 60, "corte": (1.0, 2.2), "apertura": (0.6, 1.2),
     "grupo": "XV 1min - COLOR", "tr": {"zona": 14, "suave": 7, "suaves_en": (), "apertura": 3, "final": 30}},
    # (17-nov, la persona: «en el de 1 minuto al ritmo de la música; de 3 a 30, más tranquilo, para no aburrir con tanto
    # corte») planos mas largos en las versiones largas: 3 min 1,8-4,0 -> 2,4-5,0; 15 min 3-7 -> 4-9; 30 min 4-9 -> 5-12
    {"plantilla": "TRAILER XV - 3min", "sufijo": "3min", "seg": 180, "corte": (2.4, 5.0), "apertura": (0.8, 1.6),
     "grupo": "XV 3min - COLOR", "tr": {"zona": 20, "suave": 12, "suaves_en": (), "apertura": 4, "final": 42}},
    {"plantilla": "TRAILER XV - 15min", "sufijo": "15min", "seg": 900, "corte": (4.0, 9.0), "apertura": (1.2, 2.5),
     "grupo": "XV 15min - COLOR", "tr": {"zona": 28, "suave": 18, "suaves_en": (), "apertura": 5, "final": 54}},
    {"plantilla": "TRAILER XV - 30min", "sufijo": "30min", "seg": 1800, "corte": (5.0, 12.0), "apertura": (1.5, 3.0),
     "grupo": "XV 30min - COLOR", "tr": {"zona": 32, "suave": 20, "suaves_en": (), "apertura": 6, "final": 60}},
]
# (1.5.7, la persona: «las transiciones están muy bruscas») antes solo habia fundidos entre momentos y en algunas zonas
# de las versiones largas: todo lo demas era corte seco. Ahora: disolvencia corta en TODOS los cortes (mas corta en la
# apertura, que va al ritmo), mas larga en las versiones largas, y un fundido a color mas largo al cambiar de momento.
INTRO_CORTES = [5] * 8                  # 8 fotos de 5 frames (24 fps): las unicas fotos del video
# (17-nov, la persona: «en Ajustes, escoger los tipos de intro, ya sea la speed ramp u otras, con su SFX y musica») El
# ritmo de las 8 fotos de la apertura; todos suman 40 cuadros (el impacto de la musica y del SFX cae ahi, al arrancar
# el video). Cada uno tiene su SFX (hacer_sfx.RAMPAS -> recursos/sfx/XV_RAMPA*.wav; sfx.momentos lo elige por el ritmo).
INTROS = {"rampa": [5] * 8,                      # pareja: una foto cada 5 cuadros
          "acelera": [9, 7, 6, 5, 4, 4, 3, 2],   # empieza lenta y se dispara hasta el impacto
          "frena": [2, 3, 4, 4, 5, 6, 7, 9],     # rafaga que se va deteniendo en la ultima foto
          "latido": [7, 3, 7, 3, 7, 3, 7, 3]}    # de dos en dos, como un corazon
try:
    import motor as _motor_intro
    INTRO_CORTES = list(INTROS.get(str(os.environ.get("TRAILER_INTRO") or
                                       _motor_intro.leer_estado().get("intro_tipo") or "rampa").lower(), INTRO_CORTES))
except Exception:
    pass
ZONAS = ["MAQUILLAJE", "IGLESIA", "FIESTA"]
COLORES = {"MAQUILLAJE": "Purple", "IGLESIA": "Green", "FIESTA": "Pink", "DESCARTADOS": "Brown"}
PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS, PISTA_WHOOSH = "VIDEOS", "FOTOS INTRO", "TEXTOS", "SFX WHOOSH"
MARGEN = 1.0                  # s que se evitan al inicio y fin de cada video (arranque de camara, handles)
SEPARACION = 0.5              # s minimos entre dos planos del mismo video
PASO_CALIDAD = 0.5            # s por muestra de calidad (igual que analizar_material)
BRILLO_MIN_INTRO = 0.18
UMBRAL_LENTO = 0.55           # emocion media (0-1) para que un plano vaya en camara lenta
UMBRAL_LENTO_MIN = 0.30       # si no hay bastantes con UMBRAL_LENTO, se baja hasta aqui (los mas emotivos primero)
UMBRAL_TEMBLOR = 0.35         # temblor medio (px en 192 de ancho) para pasar el estabilizador de Resolve (1.5.7: antes
#                               0,6; la persona: «mejora la estabilidad»: se estabiliza mucho mas y se prefieren tomas firmes)
TEMBLOR_ESTABILIZAR_MAX = 2.5  # (16-nov) y solo si tiembla poco: con mas, el estabilizador de Resolve recorta y deforma
#                               la toma («no apuntan a nada, tal vez el error es al estabilizarlo»); las que tiemblan mas
#                               de TEMBLOR_MAX ya no entran y entre medio pierden mucho puntaje (PESO_TEMBLOR)
PESO_TEMBLOR = 0.6            # cuanto baja el puntaje de un medio segundo que tiembla (las tomas firmes ganan)
LENTOS = {"1min": 3, "3min": 6, "15min": 24, "30min": 40}    # planos en camara lenta por version (1.8.7: 12/18 -> 24/40 en
#                               los largos; la persona: «aplica técnicas de cámara lenta»)
# (1.8.7) LENTO NATURAL en los videos largos: las tomas grabadas a 48 c/s o mas se ven al 40 % sin inventar cuadros (como
# en las peliculas de boda: el B-roll va lento). Esta parte de los planos firmes de cada capitulo, los de mas emocion y
# donde sale la persona festejada primero. No en el resumen del principio (va al ritmo), ni en quien habla con su voz.
LENTO_NATURAL = {"15min": 0.30, "30min": 0.35}
LENTO_MIN_S = 1.5             # s en pantalla que debe durar un plano para ir en camara lenta (si no, no se aprecia)
LENTO_PARTE_ZONA = 0.45       # como mucho esta parte de las camaras lentas en un mismo momento (repartidas)
LENTO_TEMBLOR_MAX = 1.5       # temblor medio maximo para ir lento si la toma es de 48 fps o mas (lento natural)
LENTO_TEMBLOR_WARP = 0.8      # (16-nov) y si es de 24-30 fps (Speed Warp inventa cuadros: con movimiento, deforma)
LENTO_BARRIDO_WARP = 2.0      # px por cuadro de barrido medio maximo para Speed Warp
# El FINAL: desde un poco antes del marcador CIERRE hasta el ultimo cuadro va UNA sola imagen con la tarjeta final
# encima: la mejor foto del evento con zoom lento (Planificador.foto_final) o, si no hay foto que valga, el mejor
# plano de video en camara lenta (Planificador.heroe). Antes caia el plano que tocara (espaldas bailando).
FINAL_ANTES_S = 1.5           # s antes del marcador CIERRE en que entra el plano final
FINAL_VEL = 0.5               # velocidad del plano final (Speed Warp de Resolve inventa los cuadros que faltan)
# Las PERSONAS que reconoce DaVinci (escenas_ia.reconocer -> it["caras"], it["prota"]): cuanto pesa en el puntaje de
# un video que salga la persona festejada, que salga alguien de frente o que no salga nadie (el piso, espaldas,
# detalles sueltos). El dron no cuenta: ahi nunca hay caras.
PESO_PROTA, PESO_SIN_CARAS = 1.25, 0.72
# (1.5.7) lo que VE la IA local en cada toma (analizar_material -> vision_ia, it["ia"]): los momentos clave suben, los
# novios / la festejada un poco, y lo que no sirve (si no quedo ya fuera) casi no entra
CLAVE_IA = {"beso", "anillos", "votos", "primer_baile", "pastel", "brindis", "entrada", "lagrimas", "risas"}
# (1.5.9) el oido (analisis/oido.py, earshot): sonido -> (desde que probabilidad cuenta, emocion maxima). Boda 7-nov: el
# aplauso real da 0,68; los vitores de la pista 0,2-0,4
OIDO_EMOCION = {"aplausos": (0.3, 0.9), "vitores": (0.25, 0.85), "risas": (0.2, 0.85), "llanto": (0.2, 0.85),
                "campanas": (0.3, 0.6)}
OIDO_PESO_VOLUMEN = 0.5       # con el oido, el volumen solo vale la mitad
# (1.5.7) multicamara: un plano emotivo con otra camara que grabo lo mismo se parte en dos angulos
MULTICAM_MAX, MULTICAM_MIN_S, MULTICAM_EMOCION = 3, 2.4, 0.6
PESO_CLAVE_IA, PESO_PROTA_IA, PESO_GENTE_IA, PESO_INUTIL_IA = 1.35, 1.12, 1.05, 0.3
ACCIDENTAL_SIN_CARAS = 0.35   # un video sin ninguna cara es accidental si sirve menos de esta parte (con caras: 0,15)
UMBRAL_PLANO = 0.20           # puntaje minimo de un tramo para entrar; por debajo se rellena (dron, fotos) o se
#                               repite uno bueno, antes que meter una toma floja
VOCES = {"1min": 1, "3min": 2, "15min": 10, "30min": 22}     # pasajes de voz original (pastor, brindis, discursos)
#                                                               (1.8.7: 6/14 -> 10/22, «la voz más presente, no poquito»)
# Voz original por version. En el video largo (30 min) va SIEMPRE; en el de 15 viene activada y en los cortos no
# (la persona lo cambia en Ajustes > Voz original: llega aqui como VOZ = {"1min": True, ...}).
VOZ_DEFECTO = {"1min": False, "3min": False, "15min": True, "30min": True}
VOZ_SIEMPRE = ()             # (18-nov, la persona: «que pueda desactivar el sonido de 30 min») ya ninguna es obligada
VOZ_LARGO = {"1min": (3.0, 7.0), "3min": (4.0, 9.0), "15min": (8.0, 22.0), "30min": (10.0, 30.0)}  # s de cada pasaje
#             (1.8.7: 15 min 6-16 -> 8-22 s; 30 min 8-24 -> 10-30 s: que se entienda la idea completa)
# ---- Tomas malas: medidas ABSOLUTAS del analizador ("vista" de cada medio segundo). No se comparan con el propio
# video: un video entero grabado por accidente (camara colgando, apuntando al piso) ya no puntua como uno bueno.
FOCO_MIN = 0.20               # enfoque respecto al tipico de ESA camara: por debajo esta desenfocada o movida
# (16-nov) y respecto a la MEJOR camara del evento: el celular de noche (barridos, gente como manchas) tenia un enfoque
# tipico de 13,7 contra 35,7 de la camara principal, asi que contra «lo suyo» siempre parecia normal y entraba
# (18-nov, la persona: «agrega reglas estrictas: no tomas al piso, a paredes, borrosas, quemadas, muy movidas o sin
# sentido»; visto en la hoja de contacto del de 3 min: un barrido borroso del dron sobre el cesped, DOS veces; el
# maquillaje en vertical con los lados estirados; 25 s seguidos del mismo encuadre de la mesa) Umbrales mas duros
# (antes 0,55 / 0,25 / 6,0 / 3,0), regla propia para el dron (FOCO_DRON, BARRIDO_DRON: antes no se le pedia enfoque) y
# el «estorbo» fuera en TODAS las versiones, sin volver a admitirlo cuando falta material.
FOCO_ABS_MIN = 0.62           # por debajo de esta parte del enfoque tipico de la mejor camara: borrosa, fuera
FOCO_ABS_VERTICAL = 0.75      # lo vertical dentro del horizontal se ve chico y con los lados rellenos: mas exigente
FOCO_ABS_BIEN = 0.9           # desde aqui no resta puntaje
QUEMADO_MAX = 0.20            # parte de la imagen con las luces reventadas desde la que la toma no se usa
QUEMADO_SUAVE = 0.02          # desde aqui ya resta puntaje: se prefiere otra toma del mismo momento
BARRIDO_MAX = 4.5             # px por cuadro (192 de ancho, 10 c/s): la camara barre y no se ve nada (antes 8, luego 6)
TEMBLOR_MAX = 2.6             # temblor que ni el estabilizador arregla (antes 5: la camara principal tiene 1,6 tipico y
#                               3 en una de cada cuatro tomas; con 5 entraba lo que el estabilizador deformaba)
FOCO_DRON = 0.65              # el dron, contra SU enfoque tipico: por debajo va borroso (movido al girar o acelerar)
BARRIDO_DRON = 3.2            # y barre mas despacio que una camara en mano: desde aqui es una pasada borrosa
PESO_VERTICAL = 0.35          # en el video horizontal, un video vertical (lados rellenos) pesa esto: solo si hace falta
OSCURA_MAX = 0.07             # luz media con la que ya no se ve nada
TORCIDA = (25, 0.20, 0.16)    # giro minimo, pico minimo y eje maximo: camara ladeada o apuntando al piso
ENFOQUE_CAIDA = 0.40           # el enfoque cae a esta parte del de 2 s alrededor: desenfoque momentaneo o tiron
BORDE_MALO = 0.5              # s que se evitan a cada lado de un tramo malo (la camara aun se esta acomodando)
VIDEO_ACCIDENTAL = 0.15       # si sirve menos de esta parte del video, el video entero fue un accidente
PARECIDAS = 10                # bits de diferencia (de 64) con los que dos imagenes son el mismo encuadre
TOPE_MISMO_ENCUADRE = 0.15    # parte de los planos de una zona que puede venir del mismo video o encuadre (antes 0,22)
TOPE_DRON = 0.15              # parte de los planos de una zona que puede ser de dron
# (1.8.7, la persona: «hay tomas aéreas que no apuntan a nada... debería agarrar tomas en paneo o cosas importantes, no
# cuando está despegando, y centra al objeto que se está grabando») del dron fuera el despegue y el aterrizaje, se
# prefieren los tramos con un paneo parejo (ni quieto ni brusco) y el plano se centra en lo importante (encuadre.py)
DRON_DESPEGUE_S, DRON_ATERRIZA_S = 10.0, 3.0
DRON_PANEO = (0.35, 2.6)      # px por cuadro de un paneo parejo (192 de ancho): sube el puntaje; quieto, baja
# (1.8.7, «la persona que habla, un par de tomas que la enfoque») quien habla se ve DOS veces: al empezar (algo
# acercado, se ve donde esta) y hacia el final de la voz (mas cerca); las aereas se centran en lo importante
ZOOM_HABLA = (1.12, 1.38)     # primera vez (contexto) / segunda (cerca)
ZOOM_HABLA_MAX = 2.0          # (1.8.7) hasta aqui se acerca a quien habla si la toma lo da nitido (4K -> 1080: 2x)
CARA_HABLA = (0.11, 0.20)     # alto de su cara (del cuadro): plano medio la 1.a vez, medio corto la 2.a
CARA_HABLA_SEGURA = 0.07      # (1.8.7) con la cara mas chica (de lejos) es menos seguro quien es: hasta 1,5x
ZOOM_AEREO = 1.16
HABLA_OTRA_VEZ_S = 2.5        # s minimos entre una vez y la otra (y de la segunda en pantalla)
HABLA_MAX_TOMA = 2           # (1.8.7) veces que se ve a quien habla por toma y por version (sus otras frases, sobre otras tomas)
# ---- Relleno cuando no alcanzan las tomas buenas (mejor que repetir o meter una toma fea)
RELLENO_FOTOS = ("15min", "30min")   # versiones que se rellenan con fotos del mismo momento (1.8.7: tambien el de 15;
#                                      la persona: «si no hay material suficiente lo armas con fotos»)
# (1.8.7, la persona: «no repitas más de 2 veces una toma ni de la misma escena») Cada toma (archivo) sale como mucho
# MAX_USOS_TOMA veces en una version, en partes distintas; y la misma ESCENA (casi la misma imagen desde la misma
# camara: la camara fija de la ceremonia, la misma mesa) tambien como mucho MAX_USOS_ESCENA. Si asi no alcanza: dron,
# fotos del momento, fotos de todo el evento y solo al final se repite (avisando).
MAX_USOS_TOMA = 2
MAX_USOS_ESCENA = 2
# (1.8.7) con poco material bueno (NUESTRA BODA: de 101 videos, 55 con tramos buenos de 5 s o mas, 31 min) un video de
# 30 min salia con 415 fotos de 532 planos. Antes que fotos, los planos buenos que ya entraron DURAN MAS (como en un
# documental de boda: la ceremonia, los discursos y el baile respiran): hasta LARGO_X veces el corte mas largo de la
# version, con mas de su misma toma si es buena y no se uso. Solo en las versiones de planos largos (corte desde 3 s).
LARGO_X = 2.0
LARGO_DESDE_S = 3.0
# (1.8.7, la persona: «ni de la misma escena») una ESCENA continua (tomas grabadas sin pausa de mas de ESCENA_PAUSA_S
# entre ellas: la bendicion en casa, el baile) no llena mas de ESCENA_MAX_PARTE de un capitulo de los videos largos
ESCENA_PAUSA_S = 180.0
ESCENA_MAX_PARTE = 0.40
FOTO_RELLENO_S = (3.0, 4.5)   # s que dura cada foto de relleno
# 30 c/s en una linea de 24: Resolve tira 1 de cada 5 cuadros y el movimiento salta. Al 80 % se ven TODOS los
# cuadros (lento suave, sin saltos). Solo en los planos sin voz sincronizada.
CONFORMAR_30_A_24 = True
FUNDIDO_FOTO = 12             # cuadros del encadenado al entrar y salir de una foto de relleno
FUNDIDO_SALTO = 8             # cuadros del encadenado entre dos planos casi iguales (evita el salto)
# El mismo video usado varias veces en una zona (la camara fija de la ceremonia, el vals): se alterna el plano
# abierto con uno acercado, como si fueran dos camaras. Asi el corte entre dos trozos del mismo encuadre no se ve
# como un salto. Solo con fuente 4K (acercar no pierde nitidez en la linea de 1080).
ACERCAR = 1.28                # cuanto se acerca el plano alterno
ACERCAR_ANCHO_MIN = 3000      # ancho minimo de la fuente para acercar
# True = tambien entran los videos grabados en vertical (celular parado): llenan la pantalla recortados y el
# reencuadre inteligente de Resolve Studio (Smart Reframe) sigue a la persona. Lo decide Ajustes > Videos verticales.
USAR_VIDEOS_VERTICALES = bool(globals().get("VERTICALES", True))
PESO_VERTICAL = 0.5               # en lo horizontal un video vertical ocupa solo el centro (con los lados rellenos con su
#                                   imagen desenfocada): entra solo si es muy buena o si ya no quedan horizontales (16-nov)
# Formato de la entrega (lo elige el apartado de la pantalla de Inicio):
#   "horizontal" = 16:9, lo de siempre: entran los videos horizontales y los verticales.
#   "vertical"   = 9:16 para celular, con las mismas duraciones: SOLO los videos grabados en vertical.
VERTICAL = str(globals().get("FORMATO") or "").lower().startswith("v")
FORMATO = "vertical" if VERTICAL else "horizontal"
ETIQUETA_VERTICAL = "VERTICAL"    # la linea se llama «XV 2026-11-08 - VERTICAL 1min»
VERTICAL_MATERIAL_MIN = 1.0       # video vertical que hace falta: al menos lo que dura la version (medido: con
                                  # 17 min de video, la de 30 min repetia la mitad de los planos y la de 15, 4 de cada 10)


def etiqueta(ver):
    """Como se llama la version en la linea y en el archivo: «1min» o «VERTICAL 1min»."""
    return ("%s %s" % (ETIQUETA_VERTICAL, ver["sufijo"])) if VERTICAL else ver["sufijo"]
# Igualacion automatica por plano (CDL en el nodo del clip): exposicion, negros, balance de blancos, saturacion
IGUALAR = globals().get("IGUALAR", True)
# Las tomas ya vienen en Rec.709 (color terminado de camara): la correccion por plano solo EMPAREJA, con poco margen.
FUERZA_EXPOSICION = 0.4           # 0 = no toca, 1 = iguala del todo a la luz tipica del momento
FUERZA_BLANCOS = 0.4              # cuanto corrige la dominante de color de los grises
LUZ_OBJETIVO = (0.30, 0.50)       # limites de la luz tipica de cada momento
PENDIENTE_LIMITES = (0.92, 1.12)  # cuanto puede oscurecer o aclarar una toma
NEGRO_LECHOSO = 0.08              # desde aqui el negro se considera lavado y se limpia (antes 0.05: tocaba de mas)
DESPLAZO_LIMITES = (-0.04, 0.02)  # cuanto baja unos negros lechosos
BLANCOS_LIMITES = (0.96, 1.04)    # cuanto mueve cada canal al quitar una dominante
SAT_OBJETIVO = 0.36               # respaldo; lo normal es la saturacion tipica del propio evento (objetivo_de_saturacion)
SAT_OBJETIVO_LIMITES = (0.28, 0.38)
SAT_LIMITES = (0.85, 1.00)        # cuanto puede bajar la saturacion de una toma (LED de fiesta); nunca sube
POTENCIA_MAX = 1.22               # cuanto puede bajar los medios (gamma) una toma sobreexpuesta, sin tocar el blanco
FUERZA_QUEMADA = 0.75             # fuerza de la exposicion cuando la toma viene con las luces reventadas de camara
FUENTE_TITULO, FUENTE_SUB = "Great Vibes", "Montserrat"
ESTILO_SUB = "Regular"            # peso del subtitulo (Light se pierde sobre vestidos blancos)
VELO_TITULO = 0.55                # oscuridad del velo suave detras de los titulos (0 = sin velo)
ORDEN_ACTOS = ["FIESTA", "ROMANTICA", "CEREMONIA", "EPICA"]   # palabra del marcador ACTO -> frase del perfil
WHOOSH = "50 overcrowed"      # parte del nombre del whoosh en el media pool
CARPETAS_MOMENTO = {"MAQUILLAJE": "01 MAQUILLAJE", "IGLESIA": "02 IGLESIA", "FIESTA": "03 FIESTA",
                    "DESCARTADOS": "99 DESCARTADOS"}
# Color y ruido por separado (universal): ruido en el nodo de cada clip, correccion en el nodo PRE-CLIP del
# grupo de color de la version y el LOOK (LUT) en el nodo POST-CLIP. Cada uno se apaga por separado.
DCTL_RUIDO = "MCP/XV_REDUCCION_RUIDO.dctl"
DCTL_COLOR = "MCP/XV_CORRECCION_COLOR.dctl"
DIR_LUT = rutas.DIR_LUT
ACTIVAR_LUT = True
LOOK_REC709 = {"1min": "MCP/XV_1min_CINE_TEAL_ORANGE_REC709.cube", "3min": "MCP/XV_3min_ROMANTICO_CALIDO_REC709.cube",
               "15min": "MCP/XV_15min_FILM_KODAK_REC709.cube", "30min": "MCP/XV_30min_NATURAL_SUAVE_REC709.cube"}
ACTIVAR_SIEMPRE = ["MULTITEXT"]   # titulos de la plantilla que se activan aunque esten apagados (firma)
CORTAR_AL_RITMO = True
ENCOLAR_RENDER = True
EDITABLE = True                   # deja la linea de cada video (.drt) en EVENTO TERMINADO - <evento>/PLANTILLAS DE LOS VIDEOS

EVENTO = globals().get("EVENTO") or None
SOLO = globals().get("SOLO") or None
REHACER = globals().get("REHACER", True)
DRY_RUN = globals().get("DRY_RUN", False)
NOMBRE_XV = globals().get("NOMBRE_XV") or ""
FRASE = globals().get("FRASE") or ""
FECHA_LUGAR = globals().get("FECHA_LUGAR") or ""
TIPO_EVENTO = (globals().get("TIPO_EVENTO") or "xv").lower()   # xv, boda, bautizo, graduacion, cumpleanos
RUIDO = globals().get("RUIDO")          # intensidad de la reduccion de ruido 0-100 (None = la de ruido.DEFECTO)
# =======================================================================

try:
    resolve
except NameError:  # ejecucion fuera de Resolve
    import DaVinciResolveScript as _dvr
    resolve = _dvr.scriptapp("Resolve")

reporte = {"avisos": [], "versiones": []}


def aviso(msg):
    print("AVISO: " + msg)
    reporte["avisos"].append(msg)


def cargar_perfil(tipo):
    """Perfil del tipo de evento (perfiles_evento.json): titulos, frases y nombres de los momentos."""
    import json
    try:
        with open(rutas.perfiles(), encoding="utf-8") as f:
            perfiles = json.load(f)
    except Exception as ex:
        aviso("No se pudo leer perfiles_evento.json (%s); se usan textos de XV." % ex)
        perfiles = {}
    perfil = perfiles.get(tipo) or perfiles.get("xv") or {}
    perfil.setdefault("prefijo", "XV")
    perfil.setdefault("titulo", "Mis XV años")
    perfil.setdefault("frase", "MIS XV AÑOS")
    perfil.setdefault("momentos", {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia", "FIESTA": "Fiesta"})
    perfil.setdefault("actos", {"FIESTA": ["¡A celebrar!", ""], "ROMANTICA": ["Un sueño hecho realidad", ""]})
    perfil.setdefault("plantilla", {})
    return perfil


def _gesto(f):
    """(1.6.0) La mirada de una foto (la vio la IA en el analisis, cache «mirada»): 0 con los ojos cerrados; un poco mas
    si sonrie y mira a la camara; 1 si no se sabe."""
    m = f.get("mirada") or {}
    if m.get("ojos") == "cerrados":
        return 0.0
    return 1.0 + 0.15 * bool(m.get("sonrie")) + 0.05 * bool(m.get("mira"))


# (1.8.2, la persona: «aplica todo») el ruido medido (ruido_tomas, ya medido al analizar) como preferencia SUAVE:
# entre dos tomas parecidas entra la limpia. Nunca descarta: ruido alto x0,94, muy alto x0,86.
PESO_RUIDO = {4: 0.94, 5: 0.86}
_RUIDO_PLAN = {}


def _peso_ruido(v):
    if v.get("tipo") == "foto":
        return 1.0
    if "medidas" not in _RUIDO_PLAN:
        try:
            rt, rdm = _modulo("ruido_tomas"), _modulo("ruido")
            _RUIDO_PLAN.update(medidas=rt.leer_cache(), clave=rt._clave, nivel=rdm.nivel_base)
        except Exception:
            _RUIDO_PLAN["medidas"] = None
    if not _RUIDO_PLAN.get("medidas"):
        return 1.0
    try:
        medida = _RUIDO_PLAN["medidas"].get(_RUIDO_PLAN["clave"](v["ruta"]))
        return PESO_RUIDO.get(_RUIDO_PLAN["nivel"](medida), 1.0) if isinstance(medida, dict) else 1.0
    except Exception:
        return 1.0


def _modulo(nombre):
    ruta = rutas.codigo(nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ utilidades
def restar(intervalos, quitar):
    res = [tuple(x) for x in intervalos]
    for qa, qb in quitar:
        nuevo = []
        for a, b in res:
            if qb <= a or qa >= b:
                nuevo.append((a, b))
            else:
                if qa > a:
                    nuevo.append((a, qa))
                if qb < b:
                    nuevo.append((qb, b))
        res = nuevo
    return [(a, b) for a, b in res if b - a > 0.05]


def espaciadas(lista, n, desfase=0.5):
    if n <= 0 or not lista:
        return []
    if n >= len(lista):
        return list(lista)
    paso = len(lista) / float(n)
    idx, vistos = [], set()
    for i in range(n):
        j = min(len(lista) - 1, int((i + desfase) * paso))
        while j in vistos and j + 1 < len(lista):
            j += 1
        vistos.add(j)
        idx.append(j)
    return [lista[j] for j in sorted(idx)]


def _min_seg(s):
    """«4:05» (minutos:segundos) para decir cuanto video hay."""
    return "%d:%02d" % (int(s) // 60, int(s) % 60)


def _hora(it, desplazamiento=0.0):
    return datetime.datetime.fromisoformat(it["hora"]) + datetime.timedelta(seconds=desplazamiento)


# ------------------------------------------------------------------ plan (sin tocar Resolve)
# Los pasos de cada momento, en el orden en que pasan. Cada paso: las etiquetas (de la IA de vista) que lo muestran.
HISTORIA = {
    "xv": {"MAQUILLAJE": [("maquillaje", "peinado"), ("vestido", "zapatos"), ("festejada",)],
           "IGLESIA": [("entrada", "cortejo"), ("altar", "sacerdote", "votos"), ("familia", "grupo")],
           "FIESTA": [("entrada",), ("primer_baile",), ("brindis",), ("pastel",), ("baile", "dj"), ("familia", "grupo", "risas")]},
    "boda": {"MAQUILLAJE": [("maquillaje", "peinado"), ("vestido", "traje"), ("anillos", "zapatos", "detalle")],
             "IGLESIA": [("entrada", "cortejo"), ("votos", "altar", "sacerdote"), ("anillos",), ("beso",), ("familia", "grupo")],
             "FIESTA": [("entrada",), ("primer_baile",), ("brindis",), ("pastel",), ("baile", "dj"), ("familia", "grupo", "risas")]},
    "bautizo": {"MAQUILLAJE": [("vestido", "traje", "detalle"), ("familia",)],
                "IGLESIA": [("entrada",), ("altar", "sacerdote"), ("familia", "grupo")],
                "FIESTA": [("mesa", "comida"), ("pastel",), ("niños", "risas"), ("familia", "grupo")]},
}
HISTORIA["graduacion"] = HISTORIA["cumpleanos"] = HISTORIA["xv"]


def _lo_que_muestra(v):
    """Etiquetas de la toma: las de la primera vista y los momentos clave de sus cuadros buenos."""
    ia = v.get("ia") or {}
    et = set(ia.get("etiquetas") or [])
    for x in ia.get("instantes") or []:
        if len(x) > 2 and x[2] is not False:
            et.update(x[1] or [])
    return et


def factor_planos():
    """(18-nov, la persona: «que exista un slider para decir cuántas tomas, ya que hay muchas tomas y estresa») estado
    tomas_ritmo 0-100 (50 = como siempre): 0 = pocas tomas (planos hasta 2 veces mas largos), 100 = muchas (30 % mas
    cortos como mucho: mas cortos se vuelve un parpadeo). Multiplica el largo de cada plano; los cortes siguen al ritmo."""
    try:
        v = float(_modulo("motor").leer_estado().get("tomas_ritmo", 50))
    except Exception:
        return 1.0
    v = max(0.0, min(100.0, v))
    return 1.0 + (50.0 - v) / 50.0 if v < 50 else 1.0 - 0.3 * (v - 50.0) / 50.0


def id_plano(p):
    """Como se reconoce un plano entre el plan que se ve y el que se arma: archivo y segundo de la toma."""
    return "%s@%.1f" % ((p.get("item") or {}).get("nombre", ""), float(p.get("ini") or 0.0))


def aplicar_orden(zonas, clave, fps):
    """(18-nov, la persona: «que pueda mover el orden de las tomas para hacer la corrección del video de una vez») El
    orden que la persona arrastro en «Qué entra al video» (estado orden_planos[clave] = [id_plano...]): cada HUECO del
    plan conserva su duracion y su corte a la musica y recibe la toma que la persona puso en esa posicion; las que no
    estan en su lista siguen en su orden. Devuelve cuantos planos cambiaron de lugar."""
    try:
        orden = (_modulo("motor").leer_estado().get("orden_planos") or {}).get(clave) or []
    except Exception:
        orden = []
    if not orden:
        return 0
    huecos = [(zi, pi) for zi, z in enumerate(zonas) for pi, p in enumerate(z[3]) if p.get("tipo") != "foto"]
    piezas = [zonas[zi][3][pi] for zi, pi in huecos]
    por_id = {}
    for p in piezas:
        por_id.setdefault(id_plano(p), []).append(p)
    nueva, usadas = [], set()
    for i in orden:
        if por_id.get(i):
            p = por_id[i].pop(0)
            nueva.append(p)
            usadas.add(id(p))
    nueva += [p for p in piezas if id(p) not in usadas]
    movidos = 0
    for (zi, pi), contenido in zip(huecos, nueva):
        viejo = zonas[zi][3][pi]
        if contenido is viejo:
            continue
        p = dict(contenido)
        p["dur_f"] = viejo["dur_f"]                     # el hueco manda: duracion y corte a la musica
        dur_toma = float((p.get("item") or {}).get("dur") or 0.0)
        hace_falta = p["dur_f"] * float(p.get("vel") or 1.0) / float(fps)
        if dur_toma > 0:
            p["ini"] = max(0.0, min(float(p.get("ini") or 0.0), dur_toma - hace_falta))
        zonas[zi][3][pi] = p
        movidos += 1
    return movidos


def decisiones(items):
    """(18-nov, «Qué entra al video» de Material) Lo que la persona decidio a mano manda sobre el analisis: las tomas
    de «No la uses» (estado tomas_no) quedan fuera y las de «Úsala de todos modos» (tomas_si) vuelven a entrar aunque
    el analisis las hubiera descartado enteras (sus tramos malos siguen sin usarse)."""
    try:
        est = _modulo("motor").leer_estado()
        no = {str(n).upper() for n in est.get("tomas_no") or []}
        si = {str(n).upper() for n in est.get("tomas_si") or []}
    except Exception:
        return items
    if not (no or si):
        return items
    out = []
    for i in items:
        n = str(i.get("nombre", "")).upper()
        if n in no:
            i = dict(i, descartar=True, a_mano="no")
        elif n in si:
            i = dict(i, descartar=False, forzada=True, a_mano="si")
        out.append(i)
    return out


PREPARATIVOS_VISTOS = r"maquill|peina|peinad|arregl|ajust|vistiendo|se viste|revisa su vestido|se pone el vestido"


def _sin_acentos(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class Planificador:
    def __init__(self, items, fps):
        self.fps = fps
        # videos verticales (celular parado) no entran al montaje 16:9; quedan clasificados en el media pool
        validos = [i for i in items if i["tipo"] != "foto" and not i.get("descartar")]
        horizontales = [i for i in validos if i.get("horizontal", True)]
        utiles_h = sum(max(0.0, i.get("dur", 0) - sum(b - a for a, b in i.get("oscuros") or [])) for i in horizontales)
        verticales = USAR_VIDEOS_VERTICALES or len(horizontales) < 3 or utiles_h < 45
        n_vert = len(validos) - len(horizontales)
        fotos = [i for i in items if i["tipo"] == "foto" and not i.get("descartar")]
        if VERTICAL:                                     # 9:16: solo lo grabado en vertical
            # (19-nov, la persona: «testea con tomas aéreas de dron... si es vertical, vertical») y el dron, recortado
            # al centro: un vuelo 4K llena el 9:16 de sobra (1215 x 2160) y el paisaje aguanta el recorte
            self.vids = [i for i in validos if not i.get("horizontal", True) or i["tipo"] == "dron"]
            fotos_v = [i for i in fotos if not i.get("horizontal", True)]
            if len(fotos_v) > len(INTRO_CORTES):         # alcanzan para la intro y el final
                fotos = fotos_v
            elif fotos:
                print("Hay %d fotos verticales: la intro se completa con fotos horizontales recortadas." % len(fotos_v))
        else:
            self.vids = validos if verticales else horizontales
            if n_vert and not verticales:
                print("%d video%s fuera del montaje (%s en el media pool)."
                      % (n_vert, " vertical queda" if n_vert == 1 else "s verticales quedan", "esta" if n_vert == 1 else "estan"))
            elif n_vert and not USAR_VIDEOS_VERTICALES:  # casi todo es de celular parado: mejor recortado que en negro
                print("Hay pocos videos horizontales: se usan tambien los %d verticales (llenando el cuadro)." % n_vert)
            elif n_vert:
                print("%d video%s entra%s tambien al montaje, llenando el cuadro."
                      % (n_vert, " vertical" if n_vert == 1 else "s verticales", "" if n_vert == 1 else "n"))
            fotos_h = [i for i in fotos if i.get("horizontal", True)]
            if len(fotos_h) > len(INTRO_CORTES) or not fotos:
                fotos = fotos_h
            else:                                        # casi todas las fotos son verticales: sin ellas no hay intro
                print("Hay %d fotos horizontales: la intro se completa con fotos verticales recortadas." % len(fotos_h))
        # (1.8.7, NUESTRA BODA: la camara C puesta en hora por el sonido dejo «una joven con corona se maquilla» en
        # medio de la iglesia) el orden del dia gana a la IA por la hora; pero si la IA VIO preparativos claros (se
        # maquilla, la peinan, le ajustan o revisa el vestido) la toma es de los preparativos
        for i in validos + fotos:
            ia = i.get("ia") or {}
            if ia.get("momento") == "MAQUILLAJE" and i.get("momento") != "MAQUILLAJE" and not i.get("tramos") and \
                    re.search(PREPARATIVOS_VISTOS, _sin_acentos(ia.get("escena") or "")):
                i["momento"], i["por"] = "MAQUILLAJE", "ia (preparativos que se ven)"
        # (1.8.7, NUESTRA BODA: la recepcion en casa, el pastel y el primer baile —la IA vio «fiesta» en 25 tomas—
        # quedaron como IGLESIA por el orden del dia y el capitulo de la ceremonia tenia 8 min del mismo cuarto)
        # Cuando TERMINA la ceremonia (la ultima toma de video que la IA vio como iglesia, con 10 min de margen), lo que
        # quedo como IGLESIA y la IA no vio como iglesia es la celebracion
        igl = [i for i in validos if i.get("momento") == "IGLESIA" and (i.get("ia") or {}).get("momento") == "IGLESIA"]
        if igl:
            fin_igl = max(_hora(i, i.get("dur", 0)) for i in igl) + datetime.timedelta(minutes=10)
            for i in validos + fotos:
                if i.get("momento") == "IGLESIA" and (i.get("ia") or {}).get("momento") != "IGLESIA" and \
                        not i.get("tramos") and _hora(i) > fin_igl:
                    i["momento"], i["por"] = "FIESTA", "ia (despues de la ceremonia)"
        self.fotos = self._sin_repetidas(fotos)
        self.usados = {}
        self.usos = {}                # (1.8.7) ruta -> planos de esa toma en la version (tope MAX_USOS_TOMA)
        self.escenas = []             # (1.8.7) [(toma, huella)] de cada plano puesto (tope MAX_USOS_ESCENA por escena)
        self.fotos_usadas = set()
        self._pref = {}
        self._emo = {}
        self._vistas = {}
        self.estorbo_duro = False     # (16-nov) en 1 y 3 min el estorbo tambien queda fuera (poner_estorbo_duro)
        self._firmas = {}
        self._refs = self._enfoque_tipico(self.vids)
        self._ref_evento = self._enfoque_evento(self.vids)
        # videos grabados por accidente (camara colgando, desenfocada, apuntando al piso): no entran al montaje
        accidentes = [v for v in self.vids if not v.get("forzada") and (v.get("vista") or {}).get("nit") and self.parte_buena(v) < (
            ACCIDENTAL_SIN_CARAS if v["tipo"] == "video" and v.get("caras") == [] else VIDEO_ACCIDENTAL)]
        self.accidentales = []
        if accidentes and len(accidentes) < len(self.vids):
            self.accidentales = [v["nombre"] for v in accidentes]
            fuera = {v["ruta"] for v in accidentes}
            self.vids = [v for v in self.vids if v["ruta"] not in fuera]
            print("%d video%s fuera del montaje por accidental%s (desenfocado, movido o apuntando al piso): %s"
                  % (len(accidentes), "" if len(accidentes) == 1 else "s", "" if len(accidentes) == 1 else "es",
                     ", ".join(v["nombre"] for v in accidentes[:8]) + ("…" if len(accidentes) > 8 else "")))

    @staticmethod
    def _camara(v):
        return (v.get("camara") or "?", v.get("ancho"), v["tipo"] == "dron")

    def _enfoque_tipico(self, vids):
        """Enfoque tipico (mediana) de cada camara del evento: contra ESO se mide cada toma."""
        por = {}
        for v in vids:
            por.setdefault(self._camara(v), []).extend((v.get("vista") or {}).get("nit") or [])
        return {k: _mediana(x) for k, x in por.items() if x}

    def _enfoque_evento(self, vids):
        """(16-nov) Enfoque tipico de la MEJOR camara del evento (sin el dron, que ve paisajes; con al menos 30 s
        medidos): contra eso se mide tambien cada toma, para que lo borroso del celular no pase por «normal»."""
        por = {}
        for v in vids:
            if v["tipo"] != "dron":
                por.setdefault(self._camara(v), []).extend((v.get("vista") or {}).get("nit") or [])
        tipicos = [_mediana(x) for x in por.values() if len(x) >= 60] or [_mediana(x) for x in por.values() if x]
        return max(tipicos) if tipicos else 0.0

    def vista(self, v):
        """([(a, b)] tramos que NO se usan, [factor 0-1 de cada medio segundo]) por lo que se ve en la toma:
        desenfocada o movida, luces reventadas, camara barriendo, temblor fuerte, a oscuras o ladeada / al piso."""
        r = self._vistas.get(v["ruta"])
        if r is not None:
            return r
        vi = v.get("vista") or {}
        nit = vi.get("nit") or []
        ref = self._refs.get(self._camara(v)) or 0.0
        quem, pan = vi.get("quem") or [], vi.get("pan") or []
        giro, pico, eje = vi.get("giro") or [], vi.get("pico") or [], vi.get("eje") or []
        tem, col = v.get("temblor") or [], v.get("color") or []
        dron = v["tipo"] == "dron"
        ref_ev = self._ref_evento if not dron else 0.0
        abs_min = FOCO_ABS_VERTICAL if (not VERTICAL and not v.get("horizontal", True)) else FOCO_ABS_MIN
        # (16-nov) lo que la IA vio que no sirve en la revision cuadro por cuadro (techo, piso, de cabeza, gente sin
        # cabeza o sin ninguna cara): fuera ese tramo (medio paso antes y despues de cada cuadro malo)
        ia_malo = set()
        inst = [x for x in (v.get("ia") or {}).get("instantes") or [] if len(x) >= 3]
        if inst:
            ts = sorted(x[0] for x in inst)
            paso = _mediana([b - a for a, b in zip(ts, ts[1:])]) if len(ts) > 1 else 3.0
            for x in inst:
                if _cuadro_malo(x, dron) or (self.estorbo_duro and x[2] is False and len(x) > 3
                                             and x[3] in IA_BLANDOS):
                    for i in range(max(0, int((x[0] - paso / 2.0) / PASO_CALIDAD)),
                                   int(math.ceil((x[0] + paso / 2.0) / PASO_CALIDAD))):
                        ia_malo.add(i)
        malo, factor = [], []
        for i in range(len(nit)):
            foco = nit[i] / ref if ref > 0 else 1.0
            foco_ev = nit[i] / ref_ev if ref_ev > 0 else 1.0
            q = quem[i] if i < len(quem) else 0.0
            p = math.hypot(pan[i][0], pan[i][1]) if i < len(pan) else 0.0
            t = tem[i] if i < len(tem) else 0.0
            luz = col[i][0] if i < len(col) else 0.3
            torcida = (not dron and i < len(giro) and i < len(pico) and i < len(eje)
                       and giro[i] >= TORCIDA[0] and pico[i] >= TORCIDA[1] and eje[i] <= TORCIDA[2])
            # se va de foco un momento, alguien cruza pegado al lente o la camara da un tiron: el enfoque cae a
            # menos de la mitad de lo que tiene 2 s antes y despues
            cerca = max(nit[max(0, i - 4):i + 5])
            tiron = cerca > 0 and nit[i] < ENFOQUE_CAIDA * cerca and cerca >= 0.4 * ref
            m = (foco < FOCO_MIN or foco_ev < abs_min or q >= QUEMADO_MAX or p > BARRIDO_MAX or t > TEMBLOR_MAX
                 or luz < OSCURA_MAX or torcida or tiron or i in ia_malo
                 or (dron and (foco < FOCO_DRON or p > BARRIDO_DRON)))
            if m and v.get("forzada") and i not in ia_malo:
                m = False        # (18-nov) «Úsala de todos modos»: la persona la vio y la quiere; solo manda lo que vio la IA
            malo.append(m)
            if m:
                factor.append(0.0)
            else:
                fq = 1.0 - 0.65 * _lim((q - QUEMADO_SUAVE) / (QUEMADO_MAX - QUEMADO_SUAVE), 0.0, 1.0)
                ff = _lim(foco / 0.6, 0.4, 1.0) * _lim(0.6 + 0.4 * (foco_ev - abs_min) / (FOCO_ABS_BIEN - abs_min),
                                                       0.6, 1.0)
                fp = 1.0 - 0.4 * _lim((p - 3.0) / (BARRIDO_MAX - 3.0), 0.0, 1.0)
                ft = 1.0 - PESO_TEMBLOR * _lim((t - 0.5) / (TEMBLOR_MAX - 0.5), 0.0, 1.0)     # (1.5.7) firme gana
                factor.append(fq * ff * fp * ft)
        if ia_malo and len(malo) * PASO_CALIDAD < float(v.get("dur") or 0.0):
            # (19-nov) sin las medidas de cada medio segundo (vino solo el resumen) lo que vio la IA quedaba SIN
            # aplicar: sus cuadros malos cuentan igual hasta el final de la toma
            for i in range(len(malo), int(math.ceil(float(v.get("dur") or 0.0) / PASO_CALIDAD))):
                m = i in ia_malo
                malo.append(m)
                factor.append(0.0 if m else 1.0)
        tramos, i = [], 0
        while i < len(malo):
            if malo[i]:
                j = i
                while j + 1 < len(malo) and malo[j + 1]:
                    j += 1
                tramos.append((i * PASO_CALIDAD - BORDE_MALO, (j + 1) * PASO_CALIDAD + BORDE_MALO))
                i = j + 1
            else:
                i += 1
        r = (tramos, factor)
        self._vistas[v["ruta"]] = r
        return r

    def poner_estorbo_duro(self, duro):
        """(16-nov) En las versiones cortas (1 y 3 min) solo entra lo limpio: el estorbo (gente borrosa pegada al
        lente) queda fuera como lo demas; en las largas es blando (hace falta material). Limpia lo ya calculado."""
        if bool(duro) != self.estorbo_duro:
            self.estorbo_duro = bool(duro)
            self._vistas, self._pref = {}, {}

    def parte_buena(self, v):
        """Parte (0-1) del video que se puede usar."""
        _, factor = self.vista(v)
        return sum(1 for f in factor if f > 0.0) / float(len(factor)) if factor else 1.0

    def huella(self, v, t):
        """Huella de la imagen (64 bits) del video en el segundo t; None si no se midio."""
        hs = (v.get("vista") or {}).get("hash") or []
        if not hs:
            return None
        return int(hs[min(len(hs) - 1, max(0, int(t / PASO_CALIDAD)))], 16)

    def firma(self, v):
        """Tres huellas del video (al 25, 50 y 75 %): dos videos con la misma firma son el mismo encuadre (la camara
        en el tripode grabando varios archivos seguidos)."""
        f = self._firmas.get(v["ruta"])
        if f is None:
            f = [self.huella(v, v["dur"] * k) for k in (0.25, 0.5, 0.75)]
            self._firmas[v["ruta"]] = f
        return f

    def mismo_encuadre(self, a, b):
        if a is b:
            return True
        fa, fb = self.firma(a), self.firma(b)
        if None in fa or None in fb:
            return False
        return sum(1 for x in fa if min(bin(x ^ y).count("1") for y in fb) <= PARECIDAS + 3) >= 2

    @staticmethod
    def _sin_repetidas(fotos):
        """Rafagas: de varias fotos casi iguales (huella dHash parecida, tomadas seguidas) queda la mas nitida."""
        fotos = sorted(fotos, key=lambda f: f["hora"])
        quedan = []
        for f in fotos:
            h = f.get("dhash")
            gemela = None
            if h:
                for j in range(len(quedan) - 1, max(-1, len(quedan) - 7), -1):
                    g = quedan[j]
                    if g.get("dhash") and bin(int(h, 16) ^ int(g["dhash"], 16)).count("1") <= 10:
                        gemela = j
                        break
            if gemela is None:
                quedan.append(f)
            elif f.get("nitidez", 0) > quedan[gemela].get("nitidez", 0):
                quedan[gemela] = f
        return quedan

    @staticmethod
    def momento_en(v, t):
        """Momento del video en el segundo t (los videos largos pueden pasar de IGLESIA a FIESTA)."""
        for a, b, m in v.get("tramos") or []:
            if a <= t < b:
                return m
        return v.get("momento")

    def utiles(self, v, momentos=None, estricto=True):
        u = restar([(MARGEN, v["dur"] - MARGEN)], v.get("oscuros") or [])
        if v["tipo"] == "dron" and v.get("dur", 0) > DRON_DESPEGUE_S + DRON_ATERRIZA_S + 4.0:
            u = restar(u, [(0.0, DRON_DESPEGUE_S), (v["dur"] - DRON_ATERRIZA_S, v["dur"])])     # (1.8.7)
        if estricto:                                # fuera lo que se ve mal (desenfocado, quemado, al piso...)
            u = restar(u, self.vista(v)[0])
        if momentos and v.get("tramos"):            # solo los tramos de ese momento
            u = restar(u, [(a, b) for a, b, m in v["tramos"] if m not in momentos])
        return u

    def libres(self, v, momentos=None):
        return restar(self.utiles(v, momentos), self.usados.get(v["ruta"], []))

    def _serie(self, v):
        """Puntaje de cada medio segundo: calidad (nitidez, luz, sin temblor) x lo que se ve (enfoque real, luces
        sin quemar, camara quieta) x emocion del audio (aplausos, gritos, brindis: sube sobre lo normal del video)."""
        cal = v.get("calidad") or []
        emo = self.emocion(v)
        _, factor = self.vista(v)
        gente = self.gente(v) * self.lo_que_ve(v) * (PESO_VERTICAL if not VERTICAL and not v.get("horizontal", True)
                                                     else 1.0)
        tramo_ia = self.ia_tramos(v, len(cal))
        mov = [1.0] * len(cal)
        if v["tipo"] == "dron":                  # (1.8.7) un paneo parejo vale mas que el dron quieto o colgado
            pan = [math.hypot(q[0], q[1]) for q in (v.get("vista") or {}).get("pan") or []]
            for i in range(len(cal)):
                x = pan[i] if i < len(pan) else 0.0
                mov[i] = 1.15 if DRON_PANEO[0] <= x <= DRON_PANEO[1] else (0.8 if x < DRON_PANEO[0] * 0.5 else 1.0)
        return [c * gente * tramo_ia[i] * mov[i] * (factor[i] if i < len(factor) else 1.0) *
                (0.85 + 0.35 * (emo[i] if i < len(emo) else 0.0)) for i, c in enumerate(cal)]

    @staticmethod
    def lo_que_ve(v):
        """(1.5.7) Cuanto vale la toma por lo que VE la IA local: beso, anillos, votos, primer baile, pastel, brindis o la
        entrada suben; los novios o la festejada, un poco; lo que la IA dice que no sirve baja mucho. Sin IA: 1."""
        ia = v.get("ia") or {}
        if not ia:
            return 1.0
        et = set(ia.get("etiquetas") or [])
        p = PESO_CLAVE_IA if et & CLAVE_IA else 1.0
        if et & {"novia", "novio", "festejada"}:
            p *= PESO_PROTA_IA
        elif et & {"familia", "grupo", "baile"}:
            p *= PESO_GENTE_IA
        try:                                     # (17-nov) lo bonito primero: belleza 1-10 de la vista -> x0,8 a x1,25
            p *= 0.75 + 0.05 * max(1, min(10, int(ia["belleza"])))
        except (KeyError, TypeError, ValueError):
            pass
        return p * (PESO_INUTIL_IA if ia.get("util") is False else 1.0) * _peso_ruido(v)

    @staticmethod
    def gente(v):
        """Cuanto vale un video por QUIEN sale (lo que reconocio DaVinci): mas si sale la persona festejada, menos si
        no sale nadie de frente. Sin analizar todavia (None) o dron: no cambia."""
        caras = v.get("caras")
        if caras is None or v["tipo"] == "dron":
            return 1.0
        if v.get("prota"):
            return PESO_PROTA
        return 1.0 if caras else PESO_SIN_CARAS

    def emocion(self, v):
        """0-1 por medio segundo: el audio sube sobre lo normal del video (aplausos, gritos) y los momentos clave que
        entendio Resolve al escuchar (votos, "los declaro", el beso que viene despues, "te amo", brindis)."""
        cache = self._emo.get(v["ruta"])
        if cache is not None:
            return cache
        n = len(v.get("calidad") or []) or int(v.get("dur", 0) / PASO_CALIDAD)
        emo = [0.0] * n
        aud = v.get("audio") or []
        if len(aud) >= 6:
            normal = sorted(aud)[len(aud) // 2]
            crudo = [max(0.0, min(1.0, (x - normal - 4.0) / 10.0)) for x in aud]
            for i in range(min(n, len(crudo))):
                emo[i] = (crudo[max(0, i - 1)] + crudo[i] + crudo[min(len(crudo) - 1, i + 1)]) / 3.0
        for fr in v.get("frases") or []:
            fin = fr["fin"] + (8.0 if fr["tipo"] == "DECLARACION" else 2.0)    # tras "puede besar...": el beso
            for i in range(max(0, int((fr["ini"] - 1.0) / PASO_CALIDAD)), min(n, int(fin / PASO_CALIDAD) + 1)):
                emo[i] = max(emo[i], 0.6 + 0.4 * fr.get("puntaje", 0.5))
        # (1.5.9) lo que ESCUCHO el oido (earshot): aplausos, vitores, risas, llanto, campanas, en ventanas de 8 s cada
        # 4 s (cada medio segundo vale el promedio de las ventanas que lo cubren). Con el oido, el volumen solo pesa
        # menos: la musica fuerte o alguien hablando junto al micro no son emocion
        oido = v.get("oido") or {}
        paso, ven = oido.get("paso"), oido.get("ventana")
        if paso and ven:
            emo = [e * OIDO_PESO_VOLUMEN for e in emo]
            for grupo, (umbral, tope) in OIDO_EMOCION.items():
                serie = oido.get(grupo) or []
                if not serie or max(serie) < umbral:
                    continue
                suma, cuenta = [0.0] * n, [0] * n
                for j, p in enumerate(serie):
                    for i in range(int(j * paso / PASO_CALIDAD), min(n, int((j * paso + ven) / PASO_CALIDAD))):
                        suma[i] += p
                        cuenta[i] += 1
                for i in range(n):
                    p = suma[i] / cuenta[i] if cuenta[i] else 0.0
                    if p >= umbral:
                        emo[i] = max(emo[i], tope - 0.3 + 0.3 * min(1.0, (p - umbral) / umbral))
        # (1.5.7) los instantes clave que VIO la IA local en la toma (el beso, los anillos, el pastel...): ±3 s
        for x in (v.get("ia") or {}).get("instantes") or []:
            t, et = x[0], x[1]
            if set(et) & CLAVE_IA and x[2] is not False:
                for i in range(max(0, int((t - 3.0) / PASO_CALIDAD)), min(n, int((t + 3.0) / PASO_CALIDAD) + 1)):
                    emo[i] = max(emo[i], 0.8)
        self._emo[v["ruta"]] = emo
        return emo

    @staticmethod
    def ia_tramos(v, n):
        """(1.5.7) 0-1 por medio segundo segun lo que vio la IA local a lo largo de la toma: donde vio el piso, la
        pantalla de una camara o algo borroso (±4 s), la toma vale mucho menos."""
        f = [1.0] * n
        inst = [x for x in (v.get("ia") or {}).get("instantes") or [] if len(x) >= 3]
        ts = sorted(x[0] for x in inst)
        paso = _mediana([b - a for a, b in zip(ts, ts[1:])]) if len(ts) > 1 else 3.0
        for x in inst:
            t = x[0]
            if _cuadro_malo(x, v["tipo"] == "dron"):     # (16-nov) el tramo mismo ya queda fuera (vista); alrededor,
                for i in range(max(0, int((t - 4.0) / PASO_CALIDAD)), min(n, int((t + 4.0) / PASO_CALIDAD) + 1)):
                    f[i] = min(f[i], 0.6)                 # hasta 4 s, la camara aun se esta acomodando: vale menos
            elif x[2] is False and len(x) > 3 and x[3] in IA_BLANDOS:   # algo de gente delante: vale mucho menos
                for i in range(max(0, int((t - paso / 2.0) / PASO_CALIDAD)),
                               min(n, int(math.ceil((t + paso / 2.0) / PASO_CALIDAD)))):
                    f[i] = min(f[i], PESO_ESTORBO)
        for x in inst:                                   # (17-nov) donde la persona SONRIE, el tramo vale mas: ahi se corta
            if x[2] is not False and "sonrisa" in (x[1] or []):
                for i in range(max(0, int((x[0] - paso / 2.0) / PASO_CALIDAD)),
                               min(n, int(math.ceil((x[0] + paso / 2.0) / PASO_CALIDAD)))):
                    if f[i] >= 1.0:
                        f[i] = PESO_SONRISA
        return f

    def media(self, serie, a, l):
        if not serie:
            return 0.0
        i0 = min(len(serie) - 1, max(0, int(a / PASO_CALIDAD)))
        i1 = min(len(serie), max(i0 + 1, int(math.ceil((a + l) / PASO_CALIDAD))))
        return sum(serie[i0:i1]) / float(i1 - i0)

    def marcar_efectos(self, zonas, fps, max_lentos, natural=0.0):
        """Despues de cortar al ritmo: camara lenta (Speed Warp de Resolve) en los planos mas emotivos y estabilizador
        en los que tiemblan. Pone p['vel'] (0,4-0,5) y p['estabilizar']. natural (1.8.7): parte de los planos de cada
        capitulo que van en LENTO NATURAL (grabados a 48 c/s o mas: se ven lentos sin inventar cuadros)."""
        cand, con_ella = [], []
        for nombre, _, _, piezas in zonas:
            for p in piezas:
                if p["tipo"] != "video" or p.get("sincro") or p.get("heroe"):
                    continue
                v = p["item"]
                l = p["dur_f"] / float(fps)
                e = self.media(self.emocion(v), p["ini"], l)
                # camara lenta donde pasa algo (aplausos, gritos, una frase clave) y la toma esta firme: lento sobre
                # una toma que tiembla o barre solo alarga el defecto. (16-nov) Y en 24-30 fps el Speed Warp inventa
                # los cuadros: con la camara moviendose deforma la imagen (el «efecto raro»): ahi, solo muy firme
                natural = (v.get("fps") or 30) >= 48
                pan = [math.hypot(q[0], q[1]) for q in (v.get("vista") or {}).get("pan") or []]
                firme = (self.media(v.get("temblor") or [], p["ini"], l) <= (LENTO_TEMBLOR_MAX if natural
                                                                            else LENTO_TEMBLOR_WARP)
                         and self.media(pan, p["ini"], l) <= (BARRIDO_MAX / 2.0 if natural else LENTO_BARRIDO_WARP))
                if nombre in ("IGLESIA", "FIESTA", "APERTURA") and l >= LENTO_MIN_S and firme:
                    if e >= UMBRAL_LENTO_MIN:
                        cand.append((e, nombre, p))
                    elif v.get("prota"):         # sin emocion en el audio, pero sale la persona festejada
                        con_ella.append((self.puntaje(v, p["ini"], l), nombre, p))
        lentos, por_zona = sum(1 for _, _, _, ps in zonas for p in ps if p.get("heroe")), {}
        tope_zona = max(1, int(math.ceil(max_lentos * LENTO_PARTE_ZONA)))
        for umbral in (UMBRAL_LENTO, UMBRAL_LENTO_MIN):          # primero los claros; si faltan, los siguientes
            for e, nombre, p in sorted(cand, key=lambda t: -t[0]):
                if lentos >= max_lentos:
                    break
                if e < umbral or p.get("vel") or por_zona.get(nombre, 0) >= tope_zona:
                    continue
                vf = p["item"].get("fps") or 30
                p["vel"] = 0.4 if vf >= 48 else 0.5      # 60 fps: lento natural; 24-30 fps: Speed Warp inventa cuadros
                por_zona[nombre] = por_zona.get(nombre, 0) + 1
                lentos += 1
        # si el audio no marco bastantes momentos (un evento con musica alta todo el rato), se completa hasta el 70 %
        # con las mejores tomas firmes donde sale la persona festejada (la reconocio DaVinci)
        for _, nombre, p in sorted(con_ella, key=lambda t: -t[0]):
            if lentos >= int(math.ceil(max_lentos * 0.7)):
                break
            if p.get("vel") or por_zona.get(nombre, 0) >= tope_zona:
                continue
            p["vel"] = 0.4 if (p["item"].get("fps") or 30) >= 48 else 0.5
            por_zona[nombre] = por_zona.get(nombre, 0) + 1
            lentos += 1
        # (1.8.7, la persona: «aplica técnicas de cámara lenta») LENTO NATURAL en los videos largos: como en las
        # peliculas de boda, lo grabado a 48 c/s o mas va lento (al 40 % con 60 c/s) sin que Resolve invente cuadros.
        # Los firmes primero por emocion, la persona festejada y lo bonito que vio la IA. Nunca quien habla con su
        # voz, ni el resumen del principio (va al ritmo), ni el plano final (ya va lento).
        if natural > 0:
            for nombre, _, _, piezas in zonas:
                if nombre not in ZONAS:
                    continue
                videos = [p for p in piezas if p["tipo"] != "foto"]
                ya = sum(1 for p in videos if p.get("vel"))
                tope = int(round(len(videos) * natural))
                cand_n = []
                for p in videos:
                    v = p["item"]
                    vf = float(v.get("fps") or 30)
                    l = p["dur_f"] / float(fps)
                    if p.get("vel") or p.get("sincro") or p.get("heroe") or p.get("final") or vf < 48 or l < LENTO_MIN_S:
                        continue
                    pan = [math.hypot(q[0], q[1]) for q in (v.get("vista") or {}).get("pan") or []]
                    if self.media(v.get("temblor") or [], p["ini"], l) > LENTO_TEMBLOR_MAX or \
                            self.media(pan, p["ini"], l) > BARRIDO_MAX / 2.0:
                        continue
                    belleza = float(((v.get("ia") or {}).get("belleza")) or 5) / 10.0
                    sc = self.media(self.emocion(v), p["ini"], l) + (0.35 if v.get("prota") else 0.0) + 0.3 * belleza
                    cand_n.append((sc, p))
                for _, p in sorted(cand_n, key=lambda t: -t[0]):
                    if ya >= tope:
                        break
                    vf = float(p["item"].get("fps") or 60)
                    p["vel"] = round(max(0.25, min(0.5, fps / vf)), 3)
                    p["lento_natural"] = True
                    lentos += 1
                    ya += 1
        for _, _, _, piezas in zonas:
            for p in piezas:
                if p["tipo"] == "foto" or p["tipo"] == "dron":
                    continue
                l = p["dur_f"] / float(fps) * p.get("vel", 1.0)
                if de_cabeza(p["item"]):          # (1.8.7) medida derecha y aplicada de cabeza: empeoraria
                    continue
                if UMBRAL_TEMBLOR <= self.media(p["item"].get("temblor") or [], p["ini"], l) <= TEMBLOR_ESTABILIZAR_MAX:
                    p["estabilizar"] = True
        return lentos, sum(1 for _, _, _, ps in zonas for p in ps if p.get("estabilizar"))

    def foto_final(self, dur_f):
        """La imagen del FINAL: la mejor foto del evento (las del fotografo son retratos cuidados de la persona
        festejada), de la ceremonia o la fiesta si hay, bien expuesta y sin quemar: la mas nitida. Va con zoom lento
        y la tarjeta final encima. Devuelve la pieza o None si no hay ninguna foto que valga."""
        cand = [f for f in self.fotos if f.get("nitidez") is not None and f.get("quemado", 0.0) < 0.08
                and 0.22 <= f.get("brillo", 0.5) <= 0.62]
        if VERTICAL:
            # (16-nov) en 9:16 una foto horizontal se recorta al centro: en la boda la imagen final quedo con el padre
            # (al centro) y sin los novios. Solo fotos verticales; si no hay, el mejor plano de video (heroe)
            cand = [f for f in cand if not f.get("horizontal", True)]
            if not cand:
                return None
        tarde = [f for f in cand if f.get("momento") in ("IGLESIA", "FIESTA")]
        cand = tarde or cand

        def lo_que_vio(f):                            # (1.5.7) la IA local: los DOS novios (o la festejada), y mejor
            ia = f.get("ia") or {}                    # en un momento clave (beso, anillos, votos, primer baile)
            if ia.get("util") is False:
                return -1
            et = set(ia.get("etiquetas") or [])
            return 2 * ({"novia", "novio"} <= et) + bool(et & {"novia", "novio", "festejada"}) + \
                bool(et & {"beso", "anillos", "votos", "primer_baile"})
        mejor_ia = max([lo_que_vio(f) for f in cand] or [0])
        if mejor_ia > 0:
            cand = [f for f in cand if lo_que_vio(f) == mejor_ia]
        elif any(f.get("ia") for f in cand) and not any(f.get("prota") for f in cand):
            # (16-nov) la IA miro las fotos y en ninguna salen los novios ni la festejada (en la boda, en vertical solo
            # quedaba una mesa de botanas): la imagen final es el mejor plano de video (heroe)
            return None
        # con la persona festejada y poca gente (un retrato suyo, no una foto de grupo); si no hay, donde salga
        retratos = [f for f in cand if f.get("prota") and len(f.get("caras") or []) <= 3]
        cand = retratos or [f for f in cand if f.get("prota")] or cand
        # (1.6.0) «foto final sin ojos cerrados»: la IA miro las candidatas (cache «mirada»): fuera las de ojos cerrados
        # y, a nitidez parecida, gana la que sonrie y mira a la camara
        cand = [f for f in cand if _gesto(f) > 0] or cand
        if not cand:
            return None
        f = max(cand, key=lambda x: x["nitidez"] * _gesto(x))
        self.fotos_usadas.add(f["ruta"])
        return {"tipo": "foto", "item": f, "dur_f": dur_f, "orden": _hora(f), "momento": f.get("momento"),
                "relleno": True, "final": True, "hash": int(f["dhash"], 16) if f.get("dhash") else None}

    def heroe(self, dur_f, vel=FINAL_VEL):
        """El plano del FINAL: el mejor tramo del evento para cerrar (emotivo, firme, sin quemar), que ira en camara
        lenta. De la ceremonia o la fiesta, no de dron. Devuelve la pieza o None."""
        l = dur_f / float(self.fps) * vel               # en lento se gasta menos toma de la que se ve
        mejor = None
        hay_prota = any(v.get("prota") for v in self.vids)
        libres_h = [v for v in self.vids if self.puede_usar(v)]      # (1.8.7) mejor una toma que no salio 2 veces
        for v in (libres_h if any(x["tipo"] == "video" for x in libres_h) else self.vids):
            if v["tipo"] != "video" or not (v.get("vista") or {}).get("nit") or (hay_prota and not v.get("prota")):
                continue
            tem, pan = v.get("temblor") or [], (v.get("vista") or {}).get("pan") or []
            for a, b in self.utiles(v, ("IGLESIA", "FIESTA")):
                x = a
                while x + l <= b + 1e-6:
                    if self.momento_en(v, x + l / 2.0) not in ("IGLESIA", "FIESTA"):
                        x += 0.5
                        continue
                    emo = self.media(self.emocion(v), x, l)
                    quieto = 1.0 - 0.5 * _lim(self.media(tem, x, l) / 3.0, 0.0, 1.0)
                    i0 = int(x / PASO_CALIDAD)
                    barre = max([math.hypot(q[0], q[1]) for q in pan[i0:i0 + max(1, int(l / PASO_CALIDAD))]] or [0.0])
                    sc = self.puntaje(v, x, l) * (0.6 + 0.8 * emo) * quieto * (1.0 - 0.5 * _lim(barre / 6.0, 0.0, 1.0))
                    if mejor is None or sc > mejor[0]:
                        mejor = (sc, v, x)
                    x += 0.5
        if mejor is None:
            return None
        p = self._pieza(mejor[1], mejor[2], dur_f, marcar=False)
        p["vel"] = 0.4 if (mejor[1].get("fps") or 30) >= 48 else vel
        # colocar() centra la parte que se ve dentro de [ini, ini + largo en pantalla]: se corre el inicio para que lo
        # que se vea sea justo el tramo elegido
        p["ini"] = max(0.0, mejor[2] - dur_f / float(self.fps) * (1.0 - p["vel"]) / 2.0)
        p["heroe"] = True
        return p

    def puntaje(self, v, a, l):
        """Puntaje medio (0-1,2) del tramo [a, a+l] del video."""
        pref = self._pref.get(v["ruta"])
        if pref is None:
            pref = [0.0]
            for x in self._serie(v):
                pref.append(pref[-1] + x)
            self._pref[v["ruta"]] = pref
        n = len(pref) - 1
        if n < 1:
            return 0.5
        i0 = min(n - 1, max(0, int(a / PASO_CALIDAD)))
        i1 = min(n, max(i0 + 1, int(math.ceil((a + l) / PASO_CALIDAD))))
        return (pref[i1] - pref[i0]) / float(i1 - i0)

    def intro(self, k):
        n = len(INTRO_CORTES)
        cand = [f for f in self.fotos if f.get("brillo", 0.5) >= BRILLO_MIN_INTRO] or self.fotos
        # (1.5.7) lo que vio la IA local: fuera las que no sirven; con los novios / la festejada si alcanzan
        cand = [f for f in cand if (f.get("ia") or {}).get("util") is not False] or cand
        cand = [f for f in cand if _gesto(f) > 0] or cand          # (1.6.0) sin ojos cerrados (los que vio la IA)
        con_novios = [f for f in cand if set((f.get("ia") or {}).get("etiquetas") or []) & {"novia", "novio", "festejada"}]
        if len(con_novios) >= n:
            cand = con_novios
        con_ella = [f for f in cand if f.get("prota")]           # la intro es de la persona festejada
        if len(con_ella) >= 2 * n:
            cand = con_ella
        nit = sorted(f["nitidez"] for f in cand if f.get("nitidez") is not None)
        if len(nit) > 3 * n:                        # fuera las movidas o desenfocadas (el 30 % menos nitido)
            corte = nit[int(len(nit) * 0.3)]
            cand = [f for f in cand if f.get("nitidez") is None or f["nitidez"] >= corte]
        libres = [f for f in cand if f["ruta"] not in self.fotos_usadas]
        sel = espaciadas(libres if len(libres) >= n else cand, n, 0.2 + 0.19 * k)
        for f in sel:
            self.fotos_usadas.add(f["ruta"])
        sel.sort(key=lambda f: f["hora"])
        return [{"tipo": "foto", "item": f, "dur_f": d} for f, d in zip(sel, INTRO_CORTES)]

    def capacidad_f(self, momento, corte):
        """(1.5.7) Frames de planos DISTINTOS que da el material bueno de ese momento con ese largo de corte (lo que
        cabe sin repetir tomas)."""
        lo, hi = corte
        # (17-nov, XV 8-nov: la «iglesia» eran 3 videos y en el de 1 min uno salia 4 veces) en las versiones cortas una
        # misma toma no cuenta mas de 2 planos (1 min) o 3 (3 min): el momento con poco material se acorta y su tiempo
        # pasa a los que tienen de sobra (repartir_zonas), en vez de repetir la toma
        tope = MAX_USOS_TOMA                     # (1.8.7) en todas las versiones (antes 3 en el de 3 min y sin tope en
        #                                          los largos: una toma larga salia muchas veces)
        # (1.8.7) cada plano puede durar hasta hi x LARGO_X en las versiones de planos largos (_alargar)
        pieza = hi * LARGO_X if lo >= LARGO_DESDE_S else (lo + hi) / 2.0
        total = 0.0
        for v in self.vids:
            if v.get("momento") != momento and not any(m == momento for _, _, m in v.get("tramos") or []):
                continue
            # cada plano sale de UN tramo bueno: con 2 planos por toma, lo que dan sus 2 tramos mas largos
            tramos = sorted((b - a for a, b in self.utiles(v, [momento]) if b - a >= lo), reverse=True)
            total += sum(min(t, pieza) for t in tramos[:tope])
        return int(total * self.fps)

    def zona(self, momentos, dur_f, corte, rng, dron_primero, con_fotos=False):
        """Planos de video (las mejores tomas libres) para llenar dur_f frames, en orden cronologico. Si las tomas
        buenas no alcanzan se rellena con dron y, con con_fotos, con fotos del momento (self.relleno dice cuantos)."""
        fps = self.fps
        lo, hi = corte
        vz = [v for v in self.vids if v.get("momento") in momentos
              or any(m in momentos for _, _, m in v.get("tramos") or [])]
        filtro = momentos
        if not vz:
            aviso("No hay videos de %s; se usa material de todo el evento." % "/".join(momentos))
            vz, filtro = self.vids, None
        cortes, rest = [], dur_f
        while rest > 0:
            c = int(round(rng.uniform(lo, hi) * fps))
            if rest - c < int(lo * fps * 0.6):
                c = rest
            c = min(c, rest)
            cortes.append(c)
            rest -= c
        # (1.8.7, la persona: «usa las tomas aéreas en momentos claves») el capitulo ABRE desde el aire: la mejor toma
        # de dron de ese momento, en el plano mas largo (las aereas necesitan tiempo); si no hay, como siempre
        clave_dron = None
        if dron_primero and len(cortes) >= 3:
            largo_d = max(cortes)
            clave_dron = self.dron_clave(filtro, largo_d)
            if clave_dron is not None:
                cortes.remove(largo_d)
        cand = [(v, [x for x in self.libres(v, filtro) if x[1] - x[0] >= lo]) for v in vz]
        cand = [(v, ls) for v, ls in cand if ls]
        pesos, topes = [], []
        for v, ls in cand:
            largo = sum(b - a for a, b in ls)
            peso = largo * (0.2 + self.puntaje(v, 0, v["dur"]))
            if not VERTICAL and not v.get("horizontal", True):
                peso *= PESO_VERTICAL            # (18-nov) lo vertical dentro del horizontal, solo si falta material
            if v["ruta"] in (getattr(self, "otras_plantillas", None) or ()):
                peso *= 0.2                      # (1.8.7) ya salio en otra plantilla: solo si no hay otra cosa
            pesos.append(peso)
            # (1.8.7) como mucho MAX_USOS_TOMA planos de cada toma en toda la version (cuenta lo que ya salio antes)
            topes.append(max(0, min(int(largo // (lo + SEPARACION)),
                                    (getattr(self, "tope_toma", None) or MAX_USOS_TOMA) - self.usos.get(v["ruta"], 0))))
        # variedad: los videos del mismo encuadre (la camara en el tripode, varios archivos seguidos) cuentan como uno
        # y todo el dron junto tiene su propio tope (es bonito, pero no es el evento)
        grupo = list(range(len(cand)))
        for i in range(len(cand)):
            if cand[i][0]["tipo"] == "dron":
                grupo[i] = "dron"
                continue
            for j in range(i):
                if grupo[j] != "dron" and self.mismo_encuadre(cand[i][0], cand[j][0]):
                    grupo[i] = grupo[j]
                    break
        # (1.8.7) escena continua de cada toma (por la hora real): ninguna llena mas de ESCENA_MAX_PARTE del capitulo
        escena = [0] * len(cand)
        if lo >= LARGO_DESDE_S and len(cand) >= 2:
            orden_h = sorted(range(len(cand)), key=lambda i: _hora(cand[i][0]))
            n_esc, fin_esc = 0, None
            for i in orden_h:
                v = cand[i][0]
                ini_v = _hora(v)
                if fin_esc is not None and (ini_v - fin_esc).total_seconds() > ESCENA_PAUSA_S:
                    n_esc += 1
                escena[i] = n_esc
                fin_v = _hora(v, v.get("dur", 0))
                fin_esc = fin_v if fin_esc is None or fin_v > fin_esc else fin_esc
        tope_escena = int(math.ceil(len(cortes) * ESCENA_MAX_PARTE)) if len(set(escena)) >= 2 else len(cortes)
        varios = len(set(grupo)) >= 3
        tope_de = {g: (max(1, int(math.ceil(len(cortes) * TOPE_DRON))) if g == "dron" and varios else
                       max(2, int(math.ceil(len(cortes) * TOPE_MISMO_ENCUADRE))) if varios else len(cortes))
                   for g in set(grupo)}
        total = sum(pesos)

        def repartir(topes):
            cuenta, en_grupo, en_esc = [0] * len(cand), {}, {}
            if total <= 0:
                return cuenta
            ideal = [len(cortes) * p / total for p in pesos]
            orden = sorted(range(len(cand)), key=lambda i: -ideal[i])
            for i in orden:                         # primero la parte entera, sin pasar el tope de su encuadre
                n = min(int(ideal[i]), topes[i], tope_de[grupo[i]] - en_grupo.get(grupo[i], 0),
                        tope_escena - en_esc.get(escena[i], 0))
                if n > 0:
                    cuenta[i] = n
                    en_grupo[grupo[i]] = en_grupo.get(grupo[i], 0) + n
                    en_esc[escena[i]] = en_esc.get(escena[i], 0) + n
            # lo que falta, a las de mas peso primero (antes: por la parte decimal, que con tope por toma dejaba fuera
            # a las mejores)
            falta = len(cortes) - sum(cuenta)
            while falta > 0:
                hubo = False
                for i in orden:
                    if falta > 0 and cuenta[i] < topes[i] and en_grupo.get(grupo[i], 0) < tope_de[grupo[i]] and \
                            en_esc.get(escena[i], 0) < tope_escena:
                        cuenta[i] += 1
                        en_grupo[grupo[i]] = en_grupo.get(grupo[i], 0) + 1
                        en_esc[escena[i]] = en_esc.get(escena[i], 0) + 1
                        falta -= 1
                        hubo = True
                if not hubo:
                    break
            return cuenta
        # (17-nov, XV 8-nov: el de 1 min sacaba 5 veces la misma toma larga de la fiesta y 3 otra, con 56 videos de
        # fiesta sin usar: el reparto es por minutos de toma y una de 10 min se lo lleva todo) VARIEDAD: cada toma sale
        # como mucho lo justo para llenar la zona entre todas (x1,5); si asi no alcanza, se reparte como antes.
        por_toma = max(1, int(math.ceil(1.5 * len(cortes) / float(max(1, len(cand))))))
        cuenta = repartir([min(t, por_toma) for t in topes])
        if sum(cuenta) < len(cortes):
            cuenta = repartir(topes)
        # (18-nov, «crear historias con el video: tú sabes cómo es el proceso de una boda y de unos quince años») Los
        # PASOS del momento (HISTORIA: maquillaje, vestido... entrada, vals, brindis, pastel, baile) que el material
        # tiene no se quedan fuera: si ninguna toma elegida muestra un paso, entra la mejor que lo muestra, quitandole
        # un plano a la que mas tiene. El orden sigue siendo el de la hora (la historia del dia).
        if len(momentos) == 1 and len(cortes) >= 2:
            pasos = (HISTORIA.get(TIPO_EVENTO) or HISTORIA["xv"]).get(momentos[0]) or []
            falta_h = []
            for paso in pasos:
                con = [i for i, (v, _ls) in enumerate(cand) if set(paso) & _lo_que_muestra(v)]
                if not con or any(cuenta[i] > 0 for i in con):
                    continue
                mejor = max((i for i in con if topes[i] >= 1), key=lambda i: pesos[i], default=None)
                dona = max(range(len(cand)), key=lambda i: cuenta[i]) if cand else None
                if mejor is not None and dona is not None and cuenta[dona] >= 2:
                    cuenta[dona] -= 1
                    cuenta[mejor] = 1
                else:
                    falta_h.append(paso[0])
            self.historia = {"pasos": [p[0] for p in pasos],
                             "hay": [p[0] for p in pasos if any(set(p) & _lo_que_muestra(v) for v, _ in cand)],
                             "sin_sitio": falta_h}
        piezas, pendientes, cola = [], [], list(cortes)
        for (v, ls), n in zip(cand, cuenta):
            if n <= 0:
                continue
            largos = [cola.pop() for _ in range(min(n, len(cola)))]
            puestos, sobran = self._colocar(v, ls, largos)
            piezas += puestos
            pendientes += sobran
        pendientes += cola
        self.relleno = {"dron": 0, "fotos": 0}
        if pendientes:                          # no alcanzan las tomas buenas: dron, fotos y, al final, repetir
            hay = sum(1 for p in piezas if p["tipo"] == "dron")
            pendientes = self._rellenar_dron(pendientes, piezas, max(0, int(len(cortes) * TOPE_DRON) - hay), filtro)
        # (1.8.7) cupo de tiempo de cada escena continua (lo que ya entro cuenta); _reusar y _alargar lo respetan
        esc_de = {cand[i][0]["ruta"]: escena[i] for i in range(len(cand))}
        tiempo_esc = {}
        for p in piezas:
            e = esc_de.get(p["item"]["ruta"]) if p["tipo"] != "foto" else None
            if e is not None:
                tiempo_esc[e] = tiempo_esc.get(e, 0) + p["dur_f"]
        tope_f = int(dur_f * ESCENA_MAX_PARTE) if len(set(escena)) >= 2 else None
        self._cupo_escena = (esc_de, tope_f, tiempo_esc)
        reusos, sobran = 0, []
        for d in pendientes:                    # otra parte de una toma que aun no sale 2 veces
            p = self._reusar([v for v in vz if self.cabe_escena(v, d)], d, rng, filtro)
            if p:
                self.cabe_escena(p["item"], p["dur_f"], sumar=True)
            if p:
                piezas.append(p)
                reusos += 1
            else:
                sobran.append(d)
        if sobran and lo >= LARGO_DESDE_S:      # (1.8.7) antes que fotos: los planos buenos duran mas
            sobran = self._alargar(piezas, sobran, filtro, hi * LARGO_X, (lo + hi) / 2.0)
        if sobran:                              # (1.8.7) antes que pasar de 2 veces una toma: fotos (en todas las
            sobran = self._rellenar_fotos(sobran, piezas, filtro or momentos)          # versiones), las de ese
            if sobran:                                                                  # momento y luego las demas
                sobran = self._rellenar_fotos(sobran, piezas, None)
        for d in sobran:                        # ultimo recurso: ni fotos quedan, se repite la mejor toma posible
            p = self._reusar(vz, d, rng, filtro, tope=False)
            if p:
                piezas.append(p)
                reusos += 1
                self.repetidos = getattr(self, "repetidos", 0) + 1
        piezas.sort(key=lambda p: p["orden"])
        if clave_dron is not None:
            piezas.insert(0, clave_dron)
        elif dron_primero:
            dron = next((p for p in piezas if p["tipo"] == "dron"), None)
            if dron is not None:
                piezas.remove(dron)
                piezas.insert(0, dron)
        self.separar(piezas)
        return piezas, reusos

    def cabe_escena(self, v, f, sumar=False):
        """(1.8.7) La escena continua de la toma v aun tiene sitio para f cuadros (ESCENA_MAX_PARTE del capitulo)."""
        esc_de, tope_f, tiempo = getattr(self, "_cupo_escena", None) or ({}, None, {})
        e = esc_de.get(v.get("ruta"))
        if tope_f is None or e is None:
            return True
        if tiempo.get(e, 0) + f > tope_f:
            return False
        if sumar:
            tiempo[e] = tiempo.get(e, 0) + f
        return True

    def _alargar(self, piezas, largos, momentos, hasta_s, medio_s):
        """(1.8.7) Material corto: antes que fotos, los planos de video que ya entraron duran mas (hasta `hasta_s`), con
        lo que sigue o lo que viene antes en su misma toma (si es bueno, de ese momento y no se uso). Los mejores
        primero. Devuelve los largos que aun faltan (en planos de ~medio_s)."""
        fps = self.fps
        falta = sum(largos)
        tope_f = int(hasta_s * fps)
        orden = sorted((p for p in piezas if p["tipo"] != "foto" and not p.get("dron_clave")),
                       key=lambda p: -self.puntaje(p["item"], p["ini"], p["dur_f"] / float(fps)))
        for p in orden:
            if falta <= 0:
                break
            v = p["item"]
            sitio = tope_f - p["dur_f"]
            if sitio < int(1.0 * fps):
                continue
            a0, a1 = p["ini"], p["ini"] + p["dur_f"] / float(fps)
            propias = self.usados.get(v["ruta"], [])
            otros = [w for w in propias if not (abs(w[0] - a0) < 1e-6 and abs(w[1] - a1) < 1e-6)]
            libres = restar(self.utiles(v, momentos), [(x - SEPARACION, y + SEPARACION) for x, y in otros])
            tramo = next(((x, y) for x, y in libres if x <= a0 + 1e-6 and a1 <= y + 1e-6), None)
            if tramo is None:
                continue
            mas_fin = max(0, min(sitio, int((tramo[1] - a1) * fps), falta))
            if mas_fin and self.puntaje(v, a1, mas_fin / float(fps)) < UMBRAL_PLANO:
                mas_fin = 0
            mas_ini = max(0, min(sitio - mas_fin, int((a0 - tramo[0]) * fps), falta - mas_fin))
            if mas_ini and self.puntaje(v, a0 - mas_ini / float(fps), mas_ini / float(fps)) < UMBRAL_PLANO:
                mas_ini = 0
            if mas_fin + mas_ini <= 0 or not self.cabe_escena(v, mas_fin + mas_ini, sumar=True):
                continue
            p["ini"] = a0 - mas_ini / float(fps)
            p["dur_f"] += mas_fin + mas_ini
            p["orden"] = _hora(v, p["ini"])
            p["alargado"] = True
            for k, w in enumerate(propias):
                if abs(w[0] - a0) < 1e-6 and abs(w[1] - a1) < 1e-6:
                    propias[k] = (p["ini"], p["ini"] + p["dur_f"] / float(fps))
                    break
            falta -= mas_fin + mas_ini
        if falta <= 0:
            return []
        n = max(1, int(round(falta / (medio_s * fps))))
        base = falta // n
        return [base + (1 if i < falta - base * n else 0) for i in range(n)]

    def _rellenar_dron(self, largos, piezas, cupo, momentos=None):
        """Planos de dron que aun no se usaron para lo que falta, hasta `cupo`. Devuelve los largos que siguen sin
        llenar. (19-nov, la persona: «no vas a poner una toma del dron del día si van por la fiesta... sé coherente
        dónde va en el orden») solo el dron de ESOS momentos; antes, de cualquiera."""
        faltan = []
        for lf in sorted(largos, reverse=True):
            l = lf / float(self.fps)
            puesto = None
            if cupo > 0:
                for v in sorted((d for d in self.vids if d["tipo"] == "dron" and self.puede_usar(d)
                                 and (not momentos or d.get("momento") in momentos)),
                                key=lambda d: -self.puntaje(d, 0, d["dur"])):
                    ls = [x for x in self.libres(v) if x[1] - x[0] >= l]
                    if ls:
                        puesto, _ = self._colocar(v, ls, [lf])
                        if puesto:
                            break
            if puesto:
                piezas += puesto
                cupo -= 1
                self.relleno["dron"] += 1
            else:
                faltan.append(lf)
        return faltan

    def _rellenar_fotos(self, largos, piezas, momentos):
        """Fotos del mismo momento (nitidas, sin quemar, sin repetir) para lo que falta: cada hueco se llena con
        fotos de 3 a 4,5 s. Devuelve los largos que siguen sin llenar."""
        fps = self.fps
        lo, hi = (int(round(x * fps)) for x in FOTO_RELLENO_S)
        tramos = []
        for lf in largos:                       # un hueco largo son varias fotos
            k = max(1, int(math.ceil(lf / float(hi))))
            base = lf // k
            tramos.append([base + (1 if i < lf - base * k else 0) for i in range(k)])
        cand = [f for f in self.fotos if f["ruta"] not in self.fotos_usadas
                and (not momentos or f.get("momento") in momentos)
                and f.get("quemado", 0.0) < 0.12 and f.get("brillo", 0.5) >= BRILLO_MIN_INTRO]
        pedidas = sum(len(t) for t in tramos)
        con_gente = [f for f in cand if f.get("caras")]          # fotos con alguien de frente antes que detalles
        if len(con_gente) >= pedidas:
            cand = con_gente
        nit = sorted(f["nitidez"] for f in cand if f.get("nitidez") is not None)
        if len(nit) > 2 * pedidas:               # sobran: fuera el 30 % menos nitido
            corte = nit[int(len(nit) * 0.3)]
            cand = [f for f in cand if f.get("nitidez") is None or f["nitidez"] >= corte]
        sel = espaciadas(cand, pedidas)
        faltan = []
        for t in tramos:
            if len(sel) < len(t) or min(t) < lo // 2:
                faltan.append(sum(t))
                continue
            for d in t:
                f = sel.pop(0)
                self.fotos_usadas.add(f["ruta"])
                piezas.append({"tipo": "foto", "item": f, "dur_f": d, "orden": _hora(f), "momento": f.get("momento"),
                               "relleno": True, "hash": int(f["dhash"], 16) if f.get("dhash") else None})
                self.relleno["fotos"] += 1
        return faltan

    @staticmethod
    def _parecidas(a, b):
        """Dos planos que se ven casi iguales (mismo video o mismo encuadre): juntos se ven como un salto."""
        if a["item"] is b["item"]:
            return True
        ha, hb = a.get("hash"), b.get("hash")
        return ha is not None and hb is not None and bin(ha ^ hb).count("1") <= PARECIDAS

    @classmethod
    def separar(cls, piezas, alcance=4):
        """Variedad: que no vayan dos planos seguidos del MISMO video ni del mismo encuadre (se ve como un salto). Se
        adelanta un plano cercano distinto (hasta `alcance` puestos), asi el orden sigue siendo casi cronologico.
        Devuelve cuantos pares quedaron pegados (cuando el momento tiene un solo video no hay con que separar)."""
        n = len(piezas)
        for i in range(1, n):
            if not cls._parecidas(piezas[i], piezas[i - 1]):
                continue
            for j in range(i + 1, min(n, i + 1 + alcance)):
                if not cls._parecidas(piezas[j], piezas[i - 1]):
                    piezas.insert(i, piezas.pop(j))
                    break
        return sum(1 for a, b in zip(piezas, piezas[1:]) if cls._parecidas(a, b))

    def _colocar(self, v, intervalos, largos):
        """Elige las mejores ventanas del video (calidad alta, repartidas) para cada largo pedido."""
        fps = self.fps
        libres = list(intervalos)
        res, falta, elegidos, vistas = [], [], [], []
        for lf in sorted(largos, reverse=True):
            l = lf / float(fps)
            mejor = None
            ya_vistas = self.escenas_de(v)                   # (1.8.7) la misma escena, como mucho 2 veces
            for a, b in libres:
                x = a
                while x + l <= b + 1e-6:
                    if ya_vistas and self.escena_llena(self.huella(v, x + l / 2.0), ya_vistas):
                        x += 0.25
                        continue
                    sc = self.puntaje(v, x, l)
                    if elegidos:
                        dist = min(abs(x - e) for e in elegidos)
                        sc -= 0.25 * max(0.0, 1.0 - dist / max(4.0 * l, 8.0))
                        h = self.huella(v, x + l / 2.0)          # otro plano del mismo video: que se vea distinto
                        if h is not None and any(bin(h ^ o).count("1") <= PARECIDAS for o in vistas):
                            sc -= 0.2
                    if mejor is None or sc > mejor[0]:
                        mejor = (sc, x)
                    x += 0.25
            if mejor is None or self.puntaje(v, mejor[1], l) < UMBRAL_PLANO:      # nada o solo tramos flojos
                falta.append(lf)
                continue
            s = mejor[1]
            res.append(self._pieza(v, s, lf))
            elegidos.append(s)
            if res[-1].get("hash") is not None:
                vistas.append(res[-1]["hash"])
            libres = [x for x in restar(libres, [(s - SEPARACION, s + l + SEPARACION)]) if x[1] - x[0] >= l * 0.5]
        return res, falta

    def _reusar(self, vids, lf, rng, momentos=None, tope=True):
        """Lo que falta cuando ya no quedan tomas buenas libres. (1.8.7) Con tope: otra parte (sin usar) de una toma
        que aun no sale MAX_USOS_TOMA veces y que no sea una escena ya vista 2 veces; None si no hay (entonces van
        fotos). Sin tope (ultimo recurso, ni fotos quedan): como antes, la mejor parte posible aunque se repita."""
        l = lf / float(self.fps)
        if tope:
            ok = [v for v in vids if self.puede_usar(v)]
            sin_dron = [v for v in ok if v["tipo"] != "dron"]
            cand = [(v, u) for v in sin_dron for u in self.libres(v, momentos) if u[1] - u[0] >= l] or \
                   [(v, u) for v in ok for u in self.libres(v, momentos) if u[1] - u[0] >= l]
        else:
            sin_dron = [v for v in vids if v["tipo"] != "dron"]   # el dron ya tiene su tope: no se repite de relleno
            cand = [(v, u) for v in sin_dron for u in self.utiles(v, momentos) if u[1] - u[0] >= l] or \
                   [(v, u) for v in vids for u in self.utiles(v, momentos) if u[1] - u[0] >= l] or \
                   [(v, u) for v in self.vids for u in self.utiles(v) if u[1] - u[0] >= l] or \
                   [(v, u) for v in self.vids for u in self.utiles(v, None, False) if u[1] - u[0] >= l]
        if not cand:
            return None
        pruebas, vistas = [], {}
        for _ in range(48 if tope else 24):
            v, (a, b) = rng.choice(cand)
            x = rng.uniform(a, b - l)
            if tope:
                if v["ruta"] not in vistas:
                    vistas[v["ruta"]] = self.escenas_de(v)
                if self.escena_llena(self.huella(v, x + l / 2.0), vistas[v["ruta"]]):
                    continue
            pruebas.append((self.puntaje(v, x, l), v, x))
        if not pruebas:
            return None
        _, v, x = max(pruebas, key=lambda t: t[0])
        return self._pieza(v, x, lf, marcar=tope)

    def multicamara(self, piezas, maximo=MULTICAM_MAX):
        """(1.5.7) Angulos alternos en los momentos clave: si un plano emotivo (el beso, los votos, el pastel...) tiene
        otra camara que grabo LO MISMO (simultaneas confirmadas por el sonido), el plano se parte en dos: la primera
        mitad desde su camara y la segunda desde la otra, en el mismo instante real (como un multicamara). El largo del
        plano no cambia. Como mucho `maximo` por zona. Devuelve cuantos partio."""
        por_ruta = {v["ruta"]: v for v in self.vids}
        out, n = [], 0
        for p in piezas:
            v = p["item"]
            l = p["dur_f"] / float(self.fps)
            otras = [s for s in v.get("simultaneas") or [] if s.get("audio") and s["ruta"] in por_ruta]
            if (n >= maximo or p["tipo"] == "foto" or not otras or l < MULTICAM_MIN_S
                    or self.media(self.emocion(v), p["ini"], l) < MULTICAM_EMOCION):
                out.append(p)
                continue
            mitad_f = p["dur_f"] // 2
            t_corte = p["ini"] + mitad_f / float(self.fps)               # segundo del plano donde cambia de camara
            hecho = False
            for s in otras:
                b = por_ruta[s["ruta"]]
                if not self.puede_usar(b):                                # (1.8.7) como mucho 2 veces cada toma
                    continue
                ini_b = t_corte - s["desde"]                              # el mismo instante en la otra camara
                fin_b = ini_b + (p["dur_f"] - mitad_f) / float(self.fps)
                if not any(a <= ini_b and fin_b <= c for a, c in self.utiles(b)):
                    continue
                primera = dict(p, dur_f=mitad_f)
                segunda = self._pieza(b, ini_b, p["dur_f"] - mitad_f)
                segunda["multicam"] = True
                out += [primera, segunda]
                n += 1
                hecho = True
                break
            if not hecho:
                out.append(p)
        piezas[:] = out
        return n

    def _pieza(self, v, ini, dur_f, marcar=True):
        medio = ini + dur_f / (2.0 * self.fps)
        h = self.huella(v, medio)
        if marcar:
            self.usados.setdefault(v["ruta"], []).append((ini, ini + dur_f / float(self.fps)))
            self.usos[v["ruta"]] = self.usos.get(v["ruta"], 0) + 1
            if h is not None:
                self.escenas.append((v, h))
        return {"tipo": v["tipo"], "item": v, "ini": ini, "dur_f": dur_f, "orden": _hora(v, ini),
                "momento": self.momento_en(v, medio), "hash": h}

    def puede_usar(self, v):
        """(1.8.7) La toma aun no salio MAX_USOS_TOMA veces en esta version (tope_toma: otro tope, el del resumen)."""
        return self.usos.get(v["ruta"], 0) < (getattr(self, "tope_toma", None) or MAX_USOS_TOMA)

    def escenas_de(self, v):
        """(1.8.7) Huellas de lo ya puesto que es la MISMA escena que la toma v (la misma toma o el mismo encuadre: la
        camara fija). Se calcula una vez por toma y se compara con cada ventana (escena_llena)."""
        return [h for item, h in self.escenas if item is v or self.mismo_encuadre(item, v)]

    @staticmethod
    def escena_llena(h, vistas):
        """(1.8.7) La imagen h ya salio MAX_USOS_ESCENA veces entre las huellas `vistas` (escenas_de)."""
        if h is None or not vistas:
            return False
        return sum(1 for o in vistas if bin(h ^ o).count("1") <= PARECIDAS) >= MAX_USOS_ESCENA

    def dron_clave(self, momentos, lf):
        """(1.8.7, la persona: «usa las tomas aéreas en momentos claves») La mejor toma de dron de ESOS momentos que aun
        se puede usar, para abrir un capitulo o despedir el video. Devuelve la pieza (ya contada) o None."""
        l = lf / float(self.fps)
        drones = [d for d in self.vids if d["tipo"] == "dron" and self.puede_usar(d)
                  and (not momentos or d.get("momento") in momentos
                       or any(m in momentos for _, _, m in d.get("tramos") or []))]
        for d in sorted(drones, key=lambda d: -self.puntaje(d, 0, d["dur"])):
            ls = [x for x in self.libres(d, momentos) if x[1] - x[0] >= l]
            if ls:
                puesto, _ = self._colocar(d, ls, [lf])
                if puesto:
                    puesto[0]["dron_clave"] = True
                    return puesto[0]
        return None


def al_ritmo(piezas, z0, z1, golpes, fps, lo):
    """Mueve cada corte al golpe de musica mas cercano (sin acortar demasiado ningun plano)."""
    if not golpes or len(piezas) < 2:
        return 0
    bordes, pos = [], z0
    for p in piezas[:-1]:
        pos += p["dur_f"]
        bordes.append(pos)
    minimo = max(6, int(lo * fps * 0.55))
    nuevos, prev, movidos = [], z0, 0
    for i, b in enumerate(bordes):
        tol = min(int(0.5 * fps), piezas[i]["dur_f"] // 2, piezas[i + 1]["dur_f"] // 2)
        j = bisect.bisect_left(golpes, b)
        mejor = None
        for g in golpes[max(0, j - 2): j + 2]:
            if abs(g - b) <= tol and g - prev >= minimo and z1 - g >= minimo:
                if mejor is None or abs(g - b) < abs(mejor - b):
                    mejor = g
        nb = max(mejor if mejor is not None else b, prev + minimo)
        movidos += mejor is not None
        nuevos.append(nb)
        prev = nb
    for i, p in enumerate(piezas[1:]):                  # (1.5.7) multicamara: el otro angulo sigue en el mismo instante
        if p.get("multicam"):
            p["ini"] += (nuevos[i] - bordes[i]) / float(fps)
    pos = z0
    for p, nb in zip(piezas, nuevos + [z1]):
        d = max(1, nb - pos)
        if p["tipo"] != "foto":
            limite = p["item"]["dur"] - 0.15
            if p["ini"] + d / float(fps) > limite:
                p["ini"] = max(0.15, limite - d / float(fps))
        p["dur_f"] = d
        pos += d
    return movidos


def _lim(x, a, b):
    return max(a, min(b, x))


def _mediana(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def _cuadro_malo(x, dron=False):
    """(16-nov) Un instante de la revision de la IA local ([t, etiquetas, sirve, motivo]) que no sirve: techo, piso,
    de cabeza, algo tapa, gente sin cabeza o sin ninguna cara (la regla de la persona). Al dron no se le piden caras."""
    if len(x) < 3 or x[2] is not False:
        return False
    motivo = x[3] if len(x) > 3 else ""
    if motivo in IA_BLANDOS:                      # el estorbo no tira: solo baja el puntaje (ia_tramos)
        return False
    return not (dron and motivo in ("sin_cara", "sin_cabeza", "piso"))    # desde el aire: hacia abajo


IA_BLANDOS = ("estorbo",)     # (16-nov) algo de gente delante: se prefiere lo limpio, pero no se tira (vision_ia.BLANDOS)
PESO_SONRISA = 1.3            # (17-nov) un tramo donde la vista ve sonreir a la persona vale un 30 % mas
PESO_ESTORBO = 0.12         # cuanto vale un tramo con estorbo frente a uno limpio (16-nov: con 0,35 el de 15 min metia
#                               9 veces en un minuto el hombro borroso con huipil: ahora queda bajo UMBRAL_PLANO y el
#                               armado prefiere repetir una toma buena o rellenar, como pide la regla del montaje)
ESTRICTO = os.environ.get("TRAILER_ESTRICTO", "1") != "0"     # (18-nov) reglas estrictas: nada dudoso aunque falte material
ESTORBO_DURO_HASTA_S = int(os.environ.get("TRAILER_ESTORBO_DURO_S", 99999 if ESTRICTO else 180))    # (16-nov) en las versiones de hasta 3 min el estorbo queda fuera del todo (solo lo limpio)


def objetivos_de_luz(items):
    """Luz tipica de cada momento (mediana de los videos), para igualar las tomas entre si."""
    res = {}
    for mom in ZONAS:
        luces = [_mediana([s[0] for s in i["color"]]) for i in items
                 if i["tipo"] != "foto" and i.get("momento") == mom and i.get("color")]
        res[mom] = _lim(_mediana(luces) if luces else 0.42, *LUZ_OBJETIVO)
    return res


def objetivo_de_saturacion(items):
    """Saturacion tipica de los videos del evento: cada toma se acerca a ESA, no a un numero fijo, para emparejar sin
    cambiarle el color a todo el evento."""
    sats = [_mediana([s[2] for s in i["color"]]) for i in items if i["tipo"] != "foto" and i.get("color")]
    sats = [x for x in sats if x > 0.02]
    return _lim(_mediana(sats), *SAT_OBJETIVO_LIMITES) if sats else SAT_OBJETIVO


def cdl_para(pieza, objetivo, sat_objetivo=None, fps=24.0):
    """CDL (slope / offset / saturacion) que empareja este plano con poco margen (son tomas Rec.709): exposicion hacia
    la luz tipica de su momento, negros limpios, balance de blancos con los grises y saturacion hacia la del evento."""
    v = pieza["item"]
    col = v.get("color") or []
    if not col or pieza["tipo"] == "foto":
        return None
    i0 = max(0, int(pieza["ini"] / PASO_CALIDAD))
    # (1.8.0, auditoria) el tramo de la toma que SE VE: en camara lenta (vel 0,4) se usa menos toma; antes se medía
    # 2,5 veces mas y un cambio de luz posterior podia entrar en la mediana del color
    usa_s = pieza["dur_f"] / float(fps or 24.0) * float(pieza.get("vel") or 1.0)
    i1 = min(len(col), max(i0 + 1, int(math.ceil((pieza["ini"] + usa_s) / PASO_CALIDAD))))
    m = col[i0:i1] or col
    luz = _mediana([s[0] for s in m])
    negro = _mediana([s[1] for s in m])
    sat = _mediana([s[2] for s in m])
    grises = [s for s in m if s[6] >= 0.05 and min(s[3:6]) > 0.05]
    quem = _mediana(((v.get("vista") or {}).get("quem") or [])[i0:i1] or [0.0])     # luces reventadas de camara
    fuerza = FUERZA_EXPOSICION + (FUERZA_QUEMADA - FUERZA_EXPOSICION) * _lim(quem / 0.10, 0.0, 1.0)
    meta = luz + fuerza * (objetivo - luz)
    potencia = 1.0
    if meta < luz and 0.05 < luz < 0.98:
        # sobreexpuesta: baja los medios con gamma y deja el blanco donde esta (bajar la pendiente volvia grises las
        # luces quemadas y la toma seguia viendose reventada)
        potencia = _lim(math.log(max(meta, 0.02)) / math.log(luz), 1.0, POTENCIA_MAX)
        s = 1.0
        o = _lim(0.03 - negro, *DESPLAZO_LIMITES) if negro > NEGRO_LECHOSO else 0.0
    else:
        if negro > NEGRO_LECHOSO:                      # negros lechosos: mapea negro->0.03 y luz->meta
            s = (meta - 0.03) / max(0.05, luz - negro)
        else:
            s = meta / max(0.02, luz)
        # si ya trae luces al tope no se aclara: se quemaria mas
        tope = 1.0 + (PENDIENTE_LIMITES[1] - 1.0) * max(0.0, 1.0 - quem / 0.03)
        s = _lim(s, PENDIENTE_LIMITES[0], tope)
        o = _lim(meta - luz * s, *DESPLAZO_LIMITES) if negro > NEGRO_LECHOSO else 0.0
    gan = [1.0, 1.0, 1.0]
    if len(grises) >= max(1, len(m) // 3):            # hay suficientes grises: corrige la dominante
        rgb = [sum(x[k] for x in grises) / len(grises) for k in (3, 4, 5)]
        prom = sum(rgb) / 3.0
        gan = [_lim(1 + FUERZA_BLANCOS * (prom / c - 1), *BLANCOS_LIMITES) for c in rgb]
        l = 0.2126 * gan[0] + 0.7152 * gan[1] + 0.0722 * gan[2]
        gan = [g / l for g in gan]
    # saturacion medida: la toma mas viva que lo tipico del evento (luces LED, flores) baja hacia eso (raiz =
    # correccion suave). NUNCA se sube: el color de camara ya viene terminado y la persona lo ve chillon.
    saturacion = _lim(((sat_objetivo or SAT_OBJETIVO) / sat) ** 0.5, *SAT_LIMITES) if sat > 0.02 else 1.0
    pend = [s * g for g in gan]
    return {"NodeIndex": "1", "Slope": "%.4f %.4f %.4f" % tuple(pend), "Offset": "%.4f %.4f %.4f" % (o, o, o),
            "Power": "%.4f %.4f %.4f" % (potencia, potencia, potencia), "Saturation": "%.3f" % saturacion}


AJUSTE_ACTO_S = 5.0     # s: si el cambio de cancion (marcador ACTO) esta asi de cerca, el momento empieza ahi
ACTO_DE_ZONA = {"IGLESIA": ("CEREMONIA", "ROMANTICA"), "FIESTA": ("FIESTA",)}


def zonas_de(marcadores, total_f, intro_f, fps=24):
    """[(nombre, inicio_f, fin_f)]: APERTURA (fin de fotos -> 1er marcador) y las zonas de los marcadores.
    Si el marcador ACTO de la cancion de ese momento esta a menos de AJUSTE_ACTO_S, la zona empieza en el ACTO:
    asi la imagen, la cancion y el texto del acto cambian juntos."""
    marcas, actos = {}, []
    for f, m in sorted(marcadores.items()):
        n = (m.get("name") or "").strip().upper()
        if n in ZONAS and n not in marcas:
            marcas[n] = int(f)
        elif n.startswith("ACTO"):
            actos.append((int(f), n))
    for z, claves in ACTO_DE_ZONA.items():
        if z in marcas:
            cerca = [(abs(f - marcas[z]), f) for f, n in actos if any(c in n for c in claves)
                     and abs(f - marcas[z]) <= AJUSTE_ACTO_S * fps]
            if cerca:
                marcas[z] = min(cerca)[1]
    if len(marcas) < len(ZONAS):
        faltan = [z for z in ZONAS if z not in marcas]
        defecto = {"MAQUILLAJE": 0.12, "IGLESIA": 0.35, "FIESTA": 0.62}
        for z in faltan:
            marcas[z] = int(total_f * defecto.get(z, 0.5))
        aviso("Faltan los marcadores %s en la plantilla; se usan posiciones por defecto." % ", ".join(faltan))
    orden = sorted(marcas.items(), key=lambda x: x[1])
    cortes = [("APERTURA", intro_f)] + [(n, max(intro_f, min(f, total_f))) for n, f in orden]
    zonas = []
    for i, (n, ini) in enumerate(cortes):
        fin = cortes[i + 1][1] if i + 1 < len(cortes) else total_f
        if fin > ini:
            zonas.append((n, ini, fin))
    return zonas


def repartir_zonas(zonas, capacidad, fps):
    """(1.5.7, la persona: «aplica todo»: zonas segun el material) Las zonas de los momentos duran lo que marca la
    plantilla; si un momento no tiene material para su zona (la boda del 7-nov: 5,6 min de iglesia para una zona de
    ~8 min en la version de 30, y nada de preparativos), su zona se achica a lo que alcanza sin repetir tomas y lo que
    sobra pasa a las zonas con material de sobra (la fiesta), segun su holgura. El largo total no cambia; un momento sin
    nada desaparece (ni su capitulo). La apertura no se toca.
    (1.8.7, NUESTRA BODA: en el de 30 min la ceremonia pasaba a 20 min y la fiesta a 3) Cada momento queda entre la
    MITAD y 1,5 VECES lo que marca la plantilla: la historia sigue equilibrada aunque a todos les falte material (lo que
    falta lo llenan planos mas largos y fotos de ese momento)."""
    mov = [(n, a, b) for n, a, b in zonas if n in capacidad]
    if len(mov) < 2:
        return zonas
    largo = {n: b - a for n, a, b in mov}
    total = sum(largo.values())
    vacios = {n for n in largo if capacidad[n] <= 0}
    if len(vacios) == len(largo):
        return zonas
    piso = {n: 0 if n in vacios else largo[n] // 2 for n in largo}
    techo = {n: 0 if n in vacios else int(largo[n] * 1.5) for n in largo}
    nuevo = {n: min(techo[n], max(piso[n], capacidad[n])) for n in largo}
    for _ in range(4):
        dif = total - sum(nuevo.values())
        if abs(dif) < fps:
            break
        if dif > 0:                  # sobra tiempo: a los que aun pueden crecer (mas al que mas material le sobra)
            crecen = [n for n in largo if n not in vacios and nuevo[n] < techo[n]]
            sin_techo = not crecen
            if sin_techo:
                crecen = [n for n in largo if n not in vacios]
            peso = {n: max(1, capacidad[n] - nuevo[n], largo[n] // 4) for n in crecen}
            pt = float(sum(peso.values()))
            for n in crecen:
                x = int(dif * peso[n] / pt)
                nuevo[n] += x if sin_techo else min(x, techo[n] - nuevo[n])
        else:                        # el material da para mas: los que pasan su largo vuelven hacia el
            exceso = {n: nuevo[n] - largo[n] for n in largo if nuevo[n] > largo[n]}
            if not exceso:
                exceso = {n: nuevo[n] - piso[n] for n in largo if nuevo[n] > piso[n]}
            et = float(sum(exceso.values())) or 1.0
            for n, e in exceso.items():
                nuevo[n] -= min(e, int(-dif * e / et))
    nuevo[mov[-1][0]] += total - sum(nuevo.values())          # lo que quedo por redondeo
    if all(abs(nuevo[n] - largo[n]) < fps for n in largo):
        return zonas
    fijas = [z for z in zonas if z[0] not in capacidad]
    pos, out = mov[0][1], []
    for n, _, _ in mov:
        if nuevo[n] >= int(fps):
            out.append((n, pos, pos + nuevo[n]))
            pos += nuevo[n]
        elif out:                                      # menos de 1 s: se suma a la anterior
            out[-1] = (out[-1][0], out[-1][1], out[-1][2] + nuevo[n])
            pos += nuevo[n]
    cambios = ["%s %.0f→%.0f s" % (n, largo[n] / float(fps), nuevo[n] / float(fps)) for n in largo
               if abs(nuevo[n] - largo[n]) >= fps]
    if cambios:
        print("Zonas segun el material que hay: " + " · ".join(cambios))
    return sorted(fijas + out, key=lambda z: z[1])


def de_cabeza(it):
    """(1.8.7) La toma trae rotacion de 180 (celular de cabeza): DaVinci la muestra al reves si no se gira."""
    try:
        return abs(int(float((it or {}).get("rotacion") or 0))) % 360 == 180
    except (TypeError, ValueError):
        return False


def colocar(mp, secuencia, pool, fps):
    """Coloca [(pista, frame, pieza)] en orden. Devuelve [(pieza, timeline_item)].
    Las fotos se ponen de una en una y se recortan (Resolve les da duracion fija). Los videos van en
    lotes y se ajustan al frame exacto (mezclar 29.97 y 24 fps los deja 1 frame cortos)."""
    puestos, lote = [], []

    def ajustar(x, d):
        if x.GetDuration() != d:
            x.SetRightOffset(x.GetDuration() + x.GetRightOffset() - d)

    def vaciar():
        if lote:
            r = mp.AppendToTimeline([i for i, _ in lote]) or []
            for x, (_, p) in zip(r, lote):
                if p.get("vel", 1.0) < 1.0:
                    p["lento_ok"] = poner_lento(x, p)
                ajustar(x, p["dur_f"])
                if de_cabeza(p.get("item")):
                    # (1.8.7, NUESTRA BODA: 4 planos salian al reves) el celular grabado de cabeza trae «rotacion
                    # -180» y DaVinci no la aplica (la de 90 si): se gira aqui
                    try:
                        x.SetProperty("RotationAngle", 180.0)
                    except Exception:
                        pass
                puestos.append((p, x))
            del lote[:]

    for pista, pos, p in secuencia:
        c = pool.get(os.path.normcase(p["item"]["ruta"]))
        if c is None:
            continue
        d = p["dur_f"]
        if p["tipo"] == "foto":
            vaciar()
            r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": d - 1,
                                      "mediaType": 1, "trackIndex": pista, "recordFrame": pos}]) or []
            if r:
                ajustar(r[0], d)
                if p.get("relleno"):            # foto dentro del video: zoom lento para que no quede quieta
                    try:
                        r[0].SetProperty("DynamicZoomEnabled", True)
                        r[0].SetProperty("DynamicZoomEase", resolve.DYNAMIC_ZOOM_EASE_IN_AND_OUT)
                    except Exception:
                        pass
                puestos.append((p, r[0]))
        else:
            vf = p["item"]["fps"]
            vel = p.get("vel", 1.0)
            if p.get("sincro"):                  # se le ve hablar con su voz: a velocidad real
                vel = 1.0
                p.pop("vel", None)
            elif CONFORMAR_30_A_24 and vel >= 1.0 and fps == 24 and 28.0 <= float(vf or 0) <= 31.0:
                vel = p["vel"] = fps / float(vf)     # 30 c/s en 24: al 80 % se ven todos los cuadros, sin saltos
                p["conformado"] = True
            # lento: Resolve conserva el largo en la timeline y usa menos fuente (desde el inicio); se centra la
            # parte que se ve en el medio de la ventana elegida
            s = int(round((p["ini"] + d / float(fps) * (1.0 - vel) / 2.0) * vf))
            n = max(1, int(math.ceil(d * vf / float(fps) - 1e-6)))
            lote.append(({"mediaPoolItem": c, "startFrame": s, "endFrame": s + n - 1,
                          "mediaType": 1, "trackIndex": pista, "recordFrame": pos}, p))
            if len(lote) >= 60:
                vaciar()
    vaciar()
    return puestos


def poner_lento(x, p):
    """Camara lenta de Resolve Studio: velocidad p['vel'] y, si el video es de 24-30 fps, Speed Warp (IA) para
    inventar los cuadros que faltan; con 60 fps alcanza con los cuadros reales."""
    try:
        ok = bool(x.SetSpeed({"Percentage": round(p["vel"] * 100.0, 2), "PitchCorrection": False,
                              "StretchKeyframesToFit": False, "RippleTimeline": False}))
    except Exception:
        ok = False
    if ok and (p["item"].get("fps") or 30) < 48 and not p.get("conformado"):
        try:
            x.SetProperty("RetimeProcess", resolve.RETIME_OPTICAL_FLOW)
            x.SetProperty("MotionEstimation", resolve.MOTION_EST_SPEED_WARP_BETTER)
        except Exception:
            pass
    return ok


def marcar_acercados(zonas):
    """Pone p['zoom'] = ACERCAR en uno de cada dos planos que salen del MISMO video dentro de una zona (el 2.o, el
    4.o...). Los de dron, las fotos y los que van sincronizados con una voz no se tocan. Devuelve cuantos."""
    n = 0
    for nombre, _, _, piezas in zonas:
        veces = {}
        for p in piezas:
            it = p["item"]
            if p["tipo"] != "video" or p.get("sincro") or (it.get("ancho") or 0) < ACERCAR_ANCHO_MIN:
                continue
            k = veces.get(it["ruta"], 0)
            veces[it["ruta"]] = k + 1
            if k % 2 == 1:
                p["zoom"] = ACERCAR
                n += 1
    return n


def acercar(puestos):
    """Aplica el acercamiento marcado (despues de estabilizar, que puede tocar el encuadre)."""
    n = 0
    for p, x in puestos:
        e = p.get("encuadre")                    # (1.8.7) quien habla enfocado / la aerea centrada
        if e:
            try:
                z, pan, tilt = e
                n += bool(x.SetProperty("ZoomX", z) and x.SetProperty("ZoomY", z))
                x.SetProperty("Pan", float(pan))
                x.SetProperty("Tilt", float(tilt))
            except Exception:
                pass
            continue
        z = p.get("zoom")
        if not z:
            continue
        try:
            n += bool(x.SetProperty("ZoomX", z) and x.SetProperty("ZoomY", z))
        except Exception:
            pass
    return n


# ResolveFX que llena las franjas con la propia imagen ampliada y desenfocada. Su nombre Y su id cambian con el idioma
# de DaVinci (visto el 2026-11-16: «Resolve FX/ResolveFX – Estilizado/Relleno»); en otro idioma no se encuentra y los
# verticales siguen recortados + Smart Reframe.
RELLENO_LADOS = ("blanking fill", "relleno")


def _efecto_relleno():
    """Id del ResolveFX «Blanking Fill» («Relleno») en este DaVinci, o None."""
    try:
        for e in resolve.GetEffectsList("video") or []:
            if e.get("category") == "ofx" and (e.get("name") or "").strip().lower() in RELLENO_LADOS:
                return e.get("id")
    except Exception:
        pass
    return None


def vestir_verticales(puestos):
    """Lo grabado en vertical dentro de la linea horizontal entra ENTERO (ajustado al alto: no se le corta la cabeza
    ni los pies a nadie) y los lados se llenan con su propia imagen ampliada y desenfocada (ResolveFX Blanking Fill),
    como se hace a mano con un video de celular. A esos planos no se les acerca ni se les estabiliza (se moveria el
    recuadro). Devuelve cuantos vistio; si DaVinci no trae el efecto, quedan como estaban (llenando el cuadro)."""
    efecto, n = None, 0
    for p, x in puestos:
        if p["item"].get("horizontal", True):
            continue
        if efecto is None:
            efecto = _efecto_relleno() or ""
        if not efecto:
            break
        try:
            if x.AddEffect("ofx", efecto) is None:
                continue
            if not x.SetProperty("Scaling", resolve.SCALE_FIT):
                x.SetProperties({"Scaling": resolve.SCALE_FIT})
            p["vestido"] = True
            p["estabilizar"] = False
            p.pop("zoom", None)
            n += 1
        except Exception:
            pass
    return n


def reencuadrar(project, puestos, limite_s=180.0):
    """Videos verticales en la linea horizontal que NO se pudieron vestir (vestir_verticales): llenan la pantalla
    recortados (SCALE_FILL) y el reencuadre inteligente de Resolve Studio (Smart Reframe) sigue a la persona para
    que el recorte no le corte la cabeza. Devuelve cuantos se reencuadraron."""
    t0, n = time.time(), 0
    for p, x in puestos:
        if p["tipo"] == "foto" or p["item"].get("horizontal", True) or p.get("vestido") \
                or time.time() - t0 > limite_s:
            continue
        try:
            if x.SmartReframe():
                fin = time.time() + 30.0
                while time.time() < fin:                 # trabaja en segundo plano: se espera a que termine
                    est = project.GetSmartReframeStatus() or {}
                    if str(est.get("JobStatus", "")).lower() not in ("running", "queued", "inprogress", "in progress"):
                        break
                    time.sleep(0.3)
                n += 1
        except Exception:
            pass
    return n


VELO_PLANTILLA = 0.30             # oscuridad del velo bajo los titulos propios de la plantilla (0 = sin velo)


def velos_plantilla(tl, mp, png, fps, intro_f=0):
    """Los titulos propios de la plantilla (la firma, el titulo grande, la frase de la intro) son de trazo fino y
    blancos: sobre un vestido claro o un cielo no se leen. No se pueden redisenar (son macros de titulos), asi que
    en la linea del evento se baja un poco la luz de la imagen MIENTRAS estan en pantalla: un velo oscuro en la
    pista TEXTOS, que queda por debajo de ellos y por encima del video. La plantilla no se toca.
    Devuelve cuantos velos puso."""
    if png is None or VELO_PLANTILLA <= 0:
        return 0
    st = tl.GetStartFrame()
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    ocupado = [(x.GetStart() - st, x.GetEnd() - st) for x in tl.GetItemListInTrack("video", pt) or []]
    tramos = []
    for t in range(pt + 1, tl.GetTrackCount("video") + 1):
        nombre_pista = (tl.GetTrackName("video", t) or "").upper()
        if "TITULO" not in nombre_pista and "TEXTO" not in nombre_pista:
            continue                                         # barras de cine, brillos, ajustes: no son textos
        for x in tl.GetItemListInTrack("video", t) or []:
            a, b = x.GetStart() - st, x.GetEnd() - st
            if x.GetMediaPoolItem() is not None or not x.GetClipEnabled() or a < intro_f or b - a < fps:
                continue
            tramos.append((a, b))
    tramos.sort()
    juntos = []
    for a, b in tramos:                                      # titulos seguidos: un solo velo
        if juntos and a - juntos[-1][1] <= fps:
            juntos[-1] = (juntos[-1][0], max(b, juntos[-1][1]))
        else:
            juntos.append((a, b))
    n = 0
    for a, b in juntos:
        a, b = max(0, a - int(0.25 * fps)), b + int(0.25 * fps)
        if any(x0 < b and a < x1 for x0, x1 in ocupado):
            continue
        r = mp.AppendToTimeline([{"mediaPoolItem": png, "startFrame": 0, "endFrame": b - a - 1, "trackIndex": pt,
                                  "recordFrame": st + a, "mediaType": 1}])
        it = r[0] if r else None
        if it is None:
            continue
        if it.GetDuration() != b - a:
            it.SetRightOffset(it.GetRightOffset() + it.GetDuration() - (b - a))
        try:
            it.SetName("VELO PLANTILLA")
        except Exception:
            pass
        comp = it.GetFusionCompByIndex(1) or it.AddFusionComp()
        if comp is None:
            continue
        comp.Lock()
        try:
            velo = comp.FindTool("Velo") or comp.AddTool("Background", -32768, -32768)
            velo.SetAttrs({"TOOLS_Name": "Velo"})
            velo.SetInput("UseFrameFormatSettings", 1)
            for k, v in (("TopLeftRed", 0.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0),
                         ("TopLeftAlpha", VELO_PLANTILLA)):
                velo.SetInput(k, v)
            comp.FindTool("MediaOut1").ConnectInput("Input", velo)
        finally:
            comp.Unlock()
        try:
            it.SetFades({"FadeIn": int(0.4 * fps), "FadeOut": int(0.4 * fps)})
        except Exception:
            pass
        ocupado.append((a, b))
        n += 1
    return n


def legibilidad_plantilla(tl):
    """Los textos PROPIOS de la plantilla (la firma, el titulo grande, la frase de la intro) son de trazo fino y se
    pierden sobre un vestido claro o un cielo. En la linea del evento (la plantilla no se toca) se les enciende un
    halo oscuro suave con los elementos de sombreado del propio Text+. Devuelve cuantos textos se tocaron."""
    n = 0
    for t in range(1, tl.GetTrackCount("video") + 1):
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS):
            continue
        for it in tl.GetItemListInTrack("video", t) or []:
            try:
                comp = it.GetFusionCompByIndex(1)
            except Exception:
                comp = None
            if comp is None:
                continue
            for herr in (comp.GetToolList(False, "TextPlus") or {}).values():
                try:
                    if not isinstance(herr.GetInput("StyledText"), str) or not herr.GetInput("StyledText").strip():
                        continue
                    herr.SetInput("Enabled3", 1)             # elemento 3: halo oscuro centrado
                    herr.SetInput("ElementShape3", 0)
                    for k in ("Red3", "Green3", "Blue3"):
                        herr.SetInput(k, 0.0)
                    herr.SetInput("Opacity3", 0.7)
                    herr.SetInput("SoftnessX3", 7.0)
                    herr.SetInput("SoftnessY3", 7.0)
                    herr.SetInput("Offset3", {1: 0.0, 2: 0.0, 3: 0.0})
                    n += 1
                except Exception:
                    pass
    return n


ZOOM_TITULO_VERTICAL = 1.5        # cuanto se agrandan en 9:16 los titulos de la plantilla ya ajustados al ancho
# (18-nov, boda vista cuadro a cuadro) con 1,5 para todos «NUESTRA BODA» (mayusculas, ocupa el ancho del 16:9) se salia
# por los lados y «Un sueño que empieza» / «Cindy & Dereck» (manuscrita, un tercio del ancho) quedaban diminutos
ZOOM_TITULO_V_ANCHO = 1.12        # titulos en MAYUSCULAS (ocupan todo el ancho): enteros dentro del 9:16
# frases y nombres (minusculas / manuscrita): segun su largo, que ocupen ~88 % del ancho. MEDIDO en DaVinci (boda):
# «Un sueño que empieza» (20 letras) a 2,3 ocupaba 1,15 del ancho y se cortaba -> ancho = 0,025 x letras x zoom
ANCHO_POR_LETRA_V = 0.025
ANCHO_FRASE_V = 0.88
# titulos propios (disenar_titulo) en 9:16: el Size de Text+ va contra el ANCHO del cuadro. MEDIDO (boda): «Cindy &
# Dereck» (14 letras) a 0,30 ocupaba ~105 % del ancho (se salia) -> ancho = 0,25 x letras x tamano
ANCHO_SCRIPT_V = 0.25
TAM_V_MAX = 0.30
SUB_V = 1.6                       # el subtitulo en mayusculas espaciadas, tambien mas grande en 9:16
FRASE_UNA_LINEA_V = 20            # frase mas larga que esto: en dos lineas en 9:16
Y_FRASE_V = 0.27                  # altura de las frases en 9:16 (0,19 quedaba bajo los botones del celular)
ZOOM_TITULO_V_MIN = 1.0
ZOOM_TITULO_V_MAX = 2.2


def _zoom_vertical(comp):
    """Cuanto agrandar en 9:16 un titulo de la plantilla segun su texto (ver ZOOM_TITULO_V_*)."""
    textos = []
    try:
        for herr in (comp.GetToolList(False, "TextPlus") or {}).values():
            txt = herr.GetInput("StyledText")
            if isinstance(txt, str) and txt.strip():
                textos.append(txt.strip())
    except Exception:
        pass
    if not textos:                  # macros (mWedding): el texto esta en una entrada «...StyledText» de la macro
        try:
            for herr in (comp.GetToolList(False) or {}).values():
                for inp in (herr.GetInputList() or {}).values():
                    iid = (inp.GetAttrs() or {}).get("INPS_ID", "")
                    if iid.endswith("StyledText"):
                        txt = herr.GetInput(iid)
                        if isinstance(txt, str) and txt.strip():
                            textos.append(txt.strip())
        except Exception:
            pass
    if not textos:
        return ZOOM_TITULO_VERTICAL
    principal = max(textos, key=len)
    letras = [c for c in principal if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) > 0.8 * len(letras):
        return ZOOM_TITULO_V_ANCHO
    z = ANCHO_FRASE_V / (ANCHO_POR_LETRA_V * max(1, len(principal)))
    return max(ZOOM_TITULO_V_MIN, min(ZOOM_TITULO_V_MAX, z))


ZOOM_MULTITEXT_V = 1.6            # (18-nov, mirado en DaVinci) «UN FILM DE / CINEMA PRODUCTIONS» a ~75 % del ancho
ESPACIO_LINEAS_V = 0.037          # entre las lineas apiladas del MultiText (en 16:9 iban desplazadas de lado)
SIN_EN_VERTICAL = ("CINE BARS",)  # franjas de cine 2,39:1: en 9:16 dejaban la imagen en una franja delgada


def _multitext_a_vertical(it):
    """El credito de la intro (macro MultiText: «UN FILM DE» a la izquierda y «CINEMA PRODUCTIONS» a la derecha, zoom
    0,5 y corrido de lado): en 9:16 salia chico y torcido. Sus lineas se apilan centradas (en su orden de arriba abajo),
    sin corrimiento y mas grandes. Devuelve True si lo cambio."""
    comp = it.GetFusionCompByIndex(1) if it.GetFusionCompCount() else None
    h = comp.FindTool("Template") if comp is not None else None
    if h is None:
        return False
    lineas = []
    for k in range(1, 9):
        txt = h.GetInput("Text%d.StyledText" % k)
        c = h.GetInput("Text%d.Center" % k)
        if not isinstance(txt, str) or not txt.strip() or not isinstance(c, dict):
            continue
        lineas.append((float(c.get(2, 0.5)), k, txt))
    if not lineas:
        return False
    lineas.sort(reverse=True)                          # la de mas arriba primero
    y0 = 0.5 + ESPACIO_LINEAS_V * (len(lineas) - 1) / 2.0
    for n, (_, k, txt) in enumerate(lineas):
        h.SetInput("Text%d.StyledText" % k, txt.strip())
        h.SetInput("Text%d.Center" % k, {1: 0.5, 2: y0 - n * ESPACIO_LINEAS_V, 3: 0.0})
    for prop, v in (("Pan", 0.0), ("Tilt", 0.0), ("ZoomX", ZOOM_MULTITEXT_V), ("ZoomY", ZOOM_MULTITEXT_V)):
        it.SetProperty(prop, v)
    return True


def titulos_a_vertical(tl):
    """Los titulos propios de la plantilla (macros mWedding: «MIS XV», las frases de la intro) llevan dentro un
    «mLetterbox» que adapta su diseno 16:9 al cuadro. Los que estan en modo llenar (1) salen en 9:16 tres veces mas
    grandes y cortados por los lados (visto el 2026-11-16); en modo ajustar (0) caben enteros. En la linea vertical
    del evento se pasan todos a ajustar y el clip se agranda un poco para que se lea en el celular. La plantilla no
    se toca. Solo se pide a Fusion ese tipo de herramienta (recorrer la macro entera es lentisimo). Devuelve cuantos."""
    n = 0
    for t in range(1, tl.GetTrackCount("video") + 1):
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS):
            continue
        for it in tl.GetItemListInTrack("video", t) or []:
            try:
                nombre_it = (it.GetName() or "").strip().upper()
                if nombre_it in SIN_EN_VERTICAL:
                    it.SetClipEnabled(False)
                    n += 1
                    continue
                if nombre_it == "MULTITEXT":
                    n += bool(_multitext_a_vertical(it))
                    continue
                comp = it.GetFusionCompByIndex(1) if it.GetFusionCompCount() else None
                cajas = (comp.GetToolList(False, "Letterbox") or {}) if comp is not None else {}
                if not cajas:
                    continue
                for caja in cajas.values():
                    caja.SetInput("Mode", 0)
                if abs(float(it.GetProperty("ZoomX") or 1.0) - 1.0) < 0.01:      # sin zoom propio en la plantilla
                    z = _zoom_vertical(comp)
                    it.SetProperty("ZoomX", z)
                    it.SetProperty("ZoomY", z)
                n += 1
            except Exception:
                pass
    return n


def sfx_propios(mp, root):
    """Los efectos de sonido propios del programa (recursos/sfx/XV_*.wav) en el media pool (06 EFECTOS\\SFX PROPIOS):
    {"XV_GOLPE": MediaPoolItem, ...}. Los importa la primera vez."""
    carpeta = os.path.join(rutas.RECURSOS, "sfx")
    try:
        archivos = sorted(f for f in os.listdir(carpeta) if f.lower().endswith(".wav"))
    except OSError:
        return {}
    res, faltan = {}, []
    for f in archivos:
        clave = os.path.splitext(f)[0]
        c = buscar_clip(root, clave)
        if c is not None:
            res[clave] = c
        else:
            faltan.append(os.path.join(carpeta, f))
    if faltan:
        efe = carpeta_raiz(mp, root, "EFECTOS")
        dest = next((x for x in efe.GetSubFolderList() or [] if x.GetName() == "SFX PROPIOS"), None) or \
            mp.AddSubFolder(efe, "SFX PROPIOS")
        mp.SetCurrentFolder(dest)
        for c in mp.ImportMedia(faltan) or []:
            res[os.path.splitext(c.GetName() or "")[0]] = c
    return res


ESTAB_PARALELO = 8           # planos que se miden a la vez (ffmpeg con la GPU + numpy; DaVinci no se toca mientras)
#                              (18-nov, medido: 4 a la vez con el procesador 1,0 s por plano; 8 con la tarjeta, ~0,45)


def _lento_de_verdad(p):
    """Camara lenta elegida (Speed Warp o 60 fps), NO el ajuste de 30 a 24 fps: ese pone vel = 0,8 con «conformado»
    (cada cuadro de la toma en un cuadro de la linea) y va a velocidad casi real. (16-nov: confundirlos dejo los planos
    sin estabilizar y con un encadenado en cada corte.)"""
    return p.get("vel", 1.0) < 0.99 and not p.get("conformado")
# (16-nov) profundidad con IA en las tomas protagonistas: APAGADO. Probado en DaVinci 21.2: un comp de clip con la
# herramienta Depth Map de Fusion no se renderiza (sale el clip sin el comp, ni con el mapa directo a la salida), asi
# que no se pone algo que no se ve. Queda el codigo (profundidad.py) por si una version de DaVinci lo arregla.
ENFOQUE_CINE = bool(globals().get("ENFOQUE_CINE", False))


def enfoque_cine(puestos):
    """(16-nov) En las tomas protagonistas (camara lenta, el heroe y la imagen final) el fondo se desenfoca y baja un
    poco de luz con el Depth Map de DaVinci Studio (profundidad.py): los novios o la festejada se separan del fondo.
    Devuelve en cuantos planos se puso."""
    try:
        prof = _modulo("profundidad")
    except Exception as ex:
        aviso("No se pudo cargar el enfoque de cine (%s)" % ex)
        return 0
    n = 0
    for p, x in puestos:
        if p.get("vestido") or not (_lento_de_verdad(p) or p.get("final") or p.get("heroe")):
            continue
        n += bool(prof.aplicar(x, log=aviso))
    return n


def estabilizar(puestos, fps=24, limite_s=None):
    """(16-nov) Estabilizador PROPIO (estabilizar.py) en los planos que tiemblan: mide el movimiento del tramo, quita
    solo el temblor (los paneos quedan), acerca lo minimo (hasta estabilizar.ZOOM_MAX) y lo pone como un Transform de
    Fusion «ESTABILIZADOR» con un keyframe por cuadro (se ve y se retoca en la pagina Fusion). Reemplaza al
    estabilizador de Resolve, que en las tomas movidas recortaba y deformaba («no apuntan a nada, tal vez el error es
    al estabilizarlo»). La camara lenta no se toca (ya se elige firme). Si un plano no se pudo medir, queda como esta.
    Devuelve cuantos se estabilizaron."""
    try:
        est = _modulo("estabilizar")
    except Exception as ex:
        aviso("No se pudo cargar el estabilizador (%s)" % ex)
        return 0
    orden = [(p, x) for p, x in puestos if p.get("estabilizar") and p["tipo"] != "foto" and not p.get("vestido")
             and not _lento_de_verdad(p)]
    if not orden:
        return 0
    t0 = time.time()

    velocidades = [est.velocidad(x) for _, x in orden]     # 29,97 fps en una linea de 24: al 80 % (cuadro a cuadro)

    def medir(par):
        (p, _), vel = par
        try:
            return est.calcular(p["item"]["ruta"], p.get("ini", 0.0), p["dur_f"] / float(fps) * vel,
                                p["item"].get("dur"))
        except Exception:
            return None
    with ThreadPoolExecutor(ESTAB_PARALELO) as ex:
        medidas = list(ex.map(medir, zip(orden, velocidades)))
    try:
        est.guardar()                            # (18-nov) lo medido queda para el proximo armado
    except Exception:
        pass
    n, antes, despues, zooms = 0, [], [], []
    for (p, x), c, vel in zip(orden, medidas, velocidades):
        if not c or (limite_s and time.time() - t0 > limite_s):
            continue
        if est.aplicar(x, c, fps, p.get("ini", 0.0), vel, log=aviso):
            n += 1
            antes.append(c["antes"])
            despues.append(c["despues"])
            zooms.append(c["zoom"])
    if n:
        print("Estabilizados %d planos con el estabilizador propio en %.0f s: temblor %.2f -> %.2f, acercamiento "
              "medio %.0f%% (maximo %.0f%%)." % (n, time.time() - t0, sum(antes) / n, sum(despues) / n,
                                                 100 * (sum(zooms) / n - 1), 100 * (max(zooms) - 1)))
    return n


TIPOS_VOZ = ("VOTOS", "DECLARACION")    # frases sueltas que tambien valen como voz (el "si, acepto" de una boda)
VOZ_PARTE_ZONA = 0.55         # como mucho esta parte de una zona lleva voz encima (1.8.7: 0,35 -> 0,55)
VOZ_ESCENA_PARTE = 0.25       # (1.8.7) y la voz de UNA escena continua (la bendicion en casa), esta parte
VOZ_AISLAR = 60               # aislamiento de voz de Resolve Studio (0-100): quita musica y murmullo de fondo (1.8.7:
#                               70 -> 60, queda un poco del lugar y la voz no suena «de estudio»)
VOZ_FUNDIDOS = (6, 12)        # cuadros de entrada y salida de cada voz
# (1.8.7, la persona: «con la voz del audio original pasando tomas encima de la voz, algo bonito») como en una pelicula
# de bodas: la voz entra un poco ANTES de ver a quien habla (corte J), se le ve decir la frase, luego tomas de ese mismo
# momento (otra camara en el mismo instante, reacciones) y la voz termina sobre otra toma (corte L); los cortes bajo la
# voz caen en las pausas entre oraciones (no a media palabra).
VOZ_ADELANTO_S = 1.2          # s que la voz se oye antes de ver a quien habla
VOZ_SALE_ANTES_S = 0.9        # s antes del final de la voz en que ya no se ve a quien habla (no mueve los labios sin voz)
VOZ_PAUSA_TOL_S = 1.0         # un corte bajo la voz se mueve hasta esto para caer en una pausa
VOZ_HABLA_MAX_S = 6.5         # (1.8.7) si se ve a quien habla mas que esto, a la mitad se pasa a otra camara en el mismo
#                               instante o a una foto de ese momento (reacciones), y la voz sigue
VOZ_CIERRE_TRAS_S = 1.2       # la frase de cierre termina este tiempo despues de que entra la imagen final
RAMPA_VOZ_SUBE = 30           # cuadros en que la musica vuelve a subir tras una voz en los videos largos (sin golpe)
VOZ_GANANCIA = 4.0            # dB de salida del nivelador de dialogo (0-6)
MUSICA_BAJO_VOZ = -16.0       # dB que baja la musica debajo de la voz (1.8.7: -11 -> -16, la voz por delante)
RAMPA_VOZ = 14                # cuadros que tarda la musica en bajar y en volver a subir (sin escalon)
PISTA_MUSICA_BAJA = "MUSICA BAJA (voz)"
CRUCE_CANCIONES_S = 2.5       # s que se alarga la cancion que sale para cruzarse con la que entra
CRUCE_ENTRA_S = 2.5           # s de entrada de la cancion nueva
CRUCE_SALE_S = 4.0            # s de salida de la cancion que termina (mas largo: asi no hay "hueco" de volumen)
CRUCE_RETRASO_MAX = 60.0      # s que como mucho se retrasa una cancion que se acaba antes de que entre la siguiente.
#                               Es acumulado hacia atras: cada una termina donde entra la otra, y la primera (a la que
#                               le sobra musica) se alarga. La entrada de la cancion de la fiesta no se mueve.


def voz_activa(sufijo):
    """Si esta version lleva la voz original: siempre en el video largo; en las demas, lo que diga Ajustes (VOZ) o
    lo que viene por defecto (activada en el de 15 minutos)."""
    if sufijo in VOZ_SIEMPRE:
        return True
    elegido = globals().get("VOZ")
    if isinstance(elegido, dict) and sufijo in elegido:
        return bool(elegido[sufijo])
    return VOZ_DEFECTO.get(sufijo, False)


def _trozos(pasaje, lo, hi):
    """Parte un pasaje de habla en trozos de lo..hi segundos cortados en limites de oracion: [(ini, fin, palabras)].
    Una oracion mas larga que hi se corta a hi (con el fundido de salida no se nota)."""
    ors = pasaje.get("oraciones") or [[pasaje["ini"], pasaje["fin"], pasaje.get("palabras", 0)]]
    res, i = [], 0
    while i < len(ors):
        a, pal, j = ors[i][0], 0, i
        while j < len(ors) and ors[j][1] - a <= hi:
            pal += ors[j][2]
            j += 1
        if j == i:                               # una sola oracion ya pasa de hi
            res.append((a, a + hi, int(ors[i][2] * hi / max(0.1, ors[i][1] - a))))
            i += 1
            continue
        b = ors[j - 1][1]
        if b - a >= lo:
            res.append((a, b, pal))
        i = j
    if not res and pasaje["fin"] - pasaje["ini"] >= lo:
        res.append((pasaje["ini"], min(pasaje["fin"], pasaje["ini"] + hi), pasaje.get("palabras", 0)))
    return res


def elegir_voces(items, sufijo, zonas, fps, excluir=()):
    """La voz original que va sobre la musica: SOLO lo importante. Pasajes donde alguien habla de corrido (la palabra
    del pastor, un brindis, un discurso) en la ceremonia o en la fiesta, mas los votos de una boda. Nada de ruidos ni
    voces sueltas del publico.
    (1.8.7, la persona: «arma una historia bonita») En los videos largos la IA local (guion_voz) lee los trozos como
    una editora y elige la frase de APERTURA (al empezar el primer capitulo, como adelanto, sobre los preparativos), las
    de la HISTORIA (en el momento en que se dijeron) y la de CIERRE (sobre la ultima aerea y la imagen final). Sin IA:
    la mas emotiva y corta abre y la mejor de la fiesta cierra.
    Devuelve [{item, ini, fin, zona, tipo, texto, oraciones, papel}] en orden."""
    n = VOCES.get(sufijo, 1)
    if n <= 0 or not voz_activa(sufijo):
        return []
    lo, hi = VOZ_LARGO.get(sufijo, (4.0, 9.0))
    de_zona = {z[0]: z for z in zonas}
    # quien habla (lo dice la transcripcion de DaVinci): el pastor, quien brinda o da el discurso hablan MUCHO a lo
    # largo del evento; una voz que aparece una sola vez unos segundos es alguien del publico
    habla = {}
    for it in items:
        for pa in it.get("pasajes") or []:
            if pa.get("hablante"):
                habla[pa["hablante"]] = habla.get(pa["hablante"], 0.0) + (pa["fin"] - pa["ini"])
    mas_habla = max(habla.values()) if habla else 0.0
    cand = []
    for it in items:
        if it["tipo"] != "video" or it.get("descartar") or it["nombre"] in excluir:
            continue
        for pa in it.get("pasajes") or []:
            mom = Planificador.momento_en(it, (pa["ini"] + pa["fin"]) / 2.0)
            if mom not in ("IGLESIA", "FIESTA") or mom not in de_zona:
                continue
            if mom == "FIESTA" and pa["tipo"] == "DISCURSO" and pa.get("claves", 0) < 2:
                continue                         # en la fiesta suena musica con letra: eso no es un discurso
            trozos = sorted(_trozos(pa, lo, hi), key=lambda t: -(t[2] / max(0.1, t[1] - t[0])))
            voz = 0.7 + 0.3 * (habla.get(pa.get("hablante"), 0.0) / mas_habla if mas_habla > 0 else 1.0)
            for k, (a, b, pal) in enumerate(trozos):
                ritmo = min(1.0, pal / max(0.1, b - a) / 2.5)          # habla clara y seguida
                ors = [o for o in pa.get("oraciones") or [] if o[0] >= a - 0.05 and o[1] <= b + 0.05]
                texto = " ".join(str(o[3]) for o in ors if len(o) > 3).strip() or pa.get("texto") or ""
                cand.append((pa["puntaje"] * voz * (0.6 + 0.4 * ritmo) * (0.85 ** k), it, pa["tipo"], a, b, mom,
                             ors, texto))
        if TIPO_EVENTO == "boda" and not it.get("pasajes") and it.get("momento") == "IGLESIA" and "IGLESIA" in de_zona:
            for fr in it.get("frases") or []:    # boda sin pasajes: los votos y "los declaro" (frases cortas)
                if fr["tipo"] in TIPOS_VOZ and 1.2 <= fr["fin"] - fr["ini"] <= 9.0:
                    cand.append((fr["puntaje"] * 0.9, it, fr["tipo"], fr["ini"], fr["fin"], "IGLESIA", [],
                                 fr.get("texto") or ""))
    cand.sort(key=lambda t: -t[0])
    largo_v = n >= 4                             # los videos largos (15 y 30 min) cuentan una historia con la voz
    pool = []                                    # sin dos trozos pegados del mismo momento
    for c in cand:
        if any(e[1] is c[1] and c[3] < e[4] + 6.0 and c[4] > e[3] - 6.0 for e in pool):
            continue
        pool.append(c)
        if len(pool) >= (max(12, 3 * n + 6) if largo_v else 4 * n):
            break
    primera = next((z for z in ZONAS if z in de_zona), None)
    ultima = next((z for z in reversed(ZONAS) if z in de_zona), None)
    papeles, orden = {}, list(range(len(pool)))
    if largo_v and len(pool) >= 3:
        g = None
        try:
            mins = int(re.sub(r"\D", "", str(sufijo)) or 15)
            g = _modulo("guion_voz").elegir([{"momento": c[5], "tipo": c[2], "dur": c[4] - c[3], "texto": c[7]}
                                             for c in pool], n, TIPO_EVENTO, mins, print)
        except Exception as ex:
            aviso("La IA editora de la voz no pudo elegir (%s); se elige como siempre." % ex)
        if g:
            # (1.8.7) apertura y cierre primero: con la historia antes, el tope de voces se llenaba y el cierre (la
            # frase sobre la imagen final) no entraba nunca (NUESTRA BODA: 6 voces sin cierre en el de 15)
            orden = [i for i in [g["apertura"], g["cierre"]] + list(g["historia"]) if i is not None]
            if g["apertura"] is not None:
                papeles[g["apertura"]] = "apertura"
            if g["cierre"] is not None:
                papeles[g["cierre"]] = "cierre"
            minimo = max(2, n // 2)              # si eligio muy pocas, se completa con las de mas puntaje que la IA
            notas = g.get("notas") or []         # no descarto (nota NOTA_RELLENO o mas: se entienden)
            if len(orden) < minimo:
                orden += [i for i in range(len(pool)) if i not in orden and i < len(notas)
                          and notas[i] >= 4][:minimo - len(orden)]
        else:                                    # sin IA: abre la mas emotiva y corta, cierra la mejor de la fiesta
            ap = next((i for i, c in enumerate(pool) if c[4] - c[3] <= 15.0 and c[2] in ("VOTOS", "DECLARACION", "AMOR")),
                      None)
            if ap is None:
                ap = next((i for i, c in enumerate(pool) if c[4] - c[3] <= 15.0), None)
            ci = next((i for i, c in enumerate(pool) if i != ap and c[5] == "FIESTA" and c[2] in ("BRINDIS", "DISCURSO")),
                      None)
            for i, papel in ((ap, "apertura"), (ci, "cierre")):
                if i is not None:
                    papeles[i] = papel
            orden = [i for i in (ap, ci) if i is not None] + [i for i in range(len(pool)) if i not in (ap, ci)]
    # (1.8.7, MEDIDO en NUESTRA BODA 30 min: 13 bendiciones seguidas, 5,5 min de voz de la MISMA escena en la casa, y
    # casi no quedaba fiesta) la voz de una escena continua (tomas sin pausa de mas de ESCENA_PAUSA_S) no pasa de
    # VOZ_ESCENA_PARTE del capitulo: quedan las mejores, que la IA editora ya puso primero
    escena_de = {}
    try:
        n_esc, fin_esc = 0, None
        for v_ in sorted((x for x in items if x.get("tipo") in ("video", "dron") and x.get("ruta")),
                         key=lambda x: _hora(x)):
            ini_v = _hora(v_)
            if fin_esc is not None and (ini_v - fin_esc).total_seconds() > ESCENA_PAUSA_S:
                n_esc += 1
            escena_de[v_["ruta"]] = n_esc
            fin_v = _hora(v_, v_.get("dur", 0))
            fin_esc = fin_v if fin_esc is None or fin_v > fin_esc else fin_esc
    except Exception:
        escena_de = {}
    elegidas, tiempo, tiempo_esc = [], {}, {}
    for i in orden:
        if len(elegidas) >= n:
            break
        _, it, tipo, a, b, mom, ors, texto = pool[i]
        papel = papeles.get(i, "historia")
        zona = primera if papel == "apertura" else ultima if papel == "cierre" else mom
        if zona not in de_zona:
            continue
        z = de_zona[zona]
        if tiempo.get(zona, 0.0) + (b - a) > VOZ_PARTE_ZONA * (z[2] - z[1]) / float(fps):
            continue
        esc = (zona, escena_de.get(it.get("ruta")))
        if papel == "historia" and esc[1] is not None and \
                tiempo_esc.get(esc, 0.0) + (b - a) > VOZ_ESCENA_PARTE * (z[2] - z[1]) / float(fps):
            continue
        if any(e["item"] is it and a < e["fin"] + 6.0 and b > e["ini"] - 6.0 for e in elegidas):
            continue                             # no dos trozos pegados del mismo momento
        elegidas.append({"item": it, "ini": a, "fin": b, "zona": zona, "tipo": tipo, "texto": texto,
                         "oraciones": ors, "papel": papel, "momento_voz": mom})
        tiempo[zona] = tiempo.get(zona, 0.0) + (b - a)
        tiempo_esc[esc] = tiempo_esc.get(esc, 0.0) + (b - a)
    pesos_papel = {"apertura": 0, "historia": 1, "cierre": 2}
    elegidas.sort(key=lambda e: (ZONAS.index(e["zona"]), pesos_papel[e["papel"]], _hora(e["item"], e["ini"])))
    return elegidas


def _inicios(piezas, z0):
    out, pos = [], z0
    for p in piezas:
        out.append(pos)
        pos += p["dur_f"]
    return out


def _mover_corte(piezas, k, delta, fps, minimo_s=0.8):
    """(1.8.7) Corre el corte entre el plano k y el k+1 `delta` cuadros (positivo: el k dura mas y el k+1 empieza
    despues). El largo de la zona no cambia. El plano k+1 corre su toma lo mismo (si estaba en sincronia, sigue).
    False si alguno quedaria muy corto o su toma no da para eso."""
    if not delta:
        return True
    if k + 1 >= len(piezas):
        return False
    a, b = piezas[k], piezas[k + 1]
    if any(x.get("final") or x.get("heroe") for x in (a, b)):
        return False
    if a["dur_f"] + delta < minimo_s * fps or b["dur_f"] - delta < minimo_s * fps:
        return False
    if delta > 0 and a["tipo"] != "foto" and a["ini"] + (a["dur_f"] + delta) / float(fps) > a["item"]["dur"] - 0.2:
        return False
    if b["tipo"] != "foto":
        nuevo = b["ini"] + delta / float(fps)
        if nuevo < 0.2 or nuevo + (b["dur_f"] - delta) / float(fps) > b["item"]["dur"] - 0.2:
            return False
        b["ini"] = nuevo
    a["dur_f"] += delta
    b["dur_f"] -= delta
    return True


def _sincronizar(v, piezas, z0, j, lead, largo, plan, fps):
    """(1.8.7) El plano j pasa a ser el de quien habla, sincronizado con su voz (entra `lead` cuadros despues de que
    empieza la voz: corte J). Deja de verse antes de que la voz termine (corte L): si el plano dura mas, el corte se
    adelanta y el siguiente plano se alarga. True si quedo en sincronia."""
    p, c = piezas[j], v["item"]
    a = v["ini"] + lead / float(fps)                     # lo que se oye cuando entra el plano
    resto = (largo - lead) / float(fps) - VOZ_SALE_ANTES_S
    if resto < 1.5:
        return False
    if p["dur_f"] / float(fps) > resto:
        quiero = int(round(resto * fps))
        if not _mover_corte(piezas, j, quiero - p["dur_f"], fps):
            # se le veria hablar sin voz: no, salvo que el plano se pueda partir (la segunda mitad son reacciones)
            if p["dur_f"] / float(fps) > resto + VOZ_SALE_ANTES_S and p["dur_f"] / float(fps) <= VOZ_HABLA_MAX_S:
                return False
    d = p["dur_f"] / float(fps)
    malos = plan.vista(c)[0] if plan is not None else []
    if a + d > c["dur"] - 0.15 or any(x < a + d and y > a for x, y in malos):
        return False
    p.update({"tipo": c["tipo"], "item": c, "ini": a, "sincro": True, "habla": 1, "voz_tipo": v.get("tipo"),
              "voz_momento": v.get("momento_voz"),
              "momento": Planificador.momento_en(c, a + d / 2.0),
              "hash": plan.huella(c, a + d / 2.0) if plan is not None else None})
    for clave in ("vel", "relleno", "lento_natural", "conformado"):
        p.pop(clave, None)
    v["sincro"] = True
    return True


def _otra_vez_quien_habla(v, piezas, z0, largo, plan, fps):
    """(1.8.7, la persona: «la persona que habla, un par de tomas que la enfoque para dar contexto») Hacia el final de
    la voz se vuelve a ver a quien habla, mas cerca y en sincronia (corte L: deja de verse antes de que termine). True
    si quedo."""
    if plan is None:
        return False
    c = v["item"]
    ini = _inicios(piezas, z0)
    fin_v = v["pos"] + largo
    ya = [ini[k] + p["dur_f"] for k, p in enumerate(piezas) if p.get("sincro") and p.get("item") is c
          and ini[k] < fin_v and ini[k] + p["dur_f"] > v["pos"]]
    desde = (max(ya) if ya else v["pos"]) + int(HABLA_OTRA_VEZ_S * fps)
    hasta = fin_v - int(VOZ_SALE_ANTES_S * fps)
    malos = plan.vista(c)[0]
    for k in sorted(range(len(piezas)), key=lambda k: -ini[k]):           # la mas cercana al final primero
        p = piezas[k]
        if ini[k] < desde or ini[k] + p["dur_f"] > hasta or p["dur_f"] < int(HABLA_OTRA_VEZ_S * fps) or \
                p.get("final") or p.get("heroe") or p.get("sincro") or p.get("dron_clave"):
            continue
        t = v["ini"] + (ini[k] - v["pos"]) / float(fps)
        d = p["dur_f"] / float(fps)
        if t < 0.2 or t + d > c["dur"] - 0.15 or any(x < t + d and y > t for x, y in malos):
            continue
        p.update({"tipo": c["tipo"], "item": c, "ini": t, "sincro": True, "habla": 2, "voz_tipo": v.get("tipo"),
                  "voz_momento": v.get("momento_voz"),
                  "momento": Planificador.momento_en(c, t + d / 2.0), "hash": plan.huella(c, t + d / 2.0)})
        for clave in ("vel", "relleno", "lento_natural", "conformado", "zoom"):
            p.pop(clave, None)
        return True
    return False


def enfocar(zonas, fps):
    """(1.8.7) El encuadre de quien habla (su cara, con la IA de caras: algo acercado la primera vez, mas cerca la
    segunda) y de las aereas (lo importante al centro, con la IA de vista). Pone p['encuadre'] = (zoom, pan, tilt);
    acercar() lo aplica en DaVinci. Devuelve (caras, aereas)."""
    try:
        enc = _modulo("encuadre")
    except Exception as ex:
        aviso("Sin encuadre automatico (%s)" % ex)
        return 0, 0
    n_c = n_a = 0
    for _nombre, _z0, _z1, piezas in zonas:
        for p in piezas:
            it = p.get("item") or {}
            if p["tipo"] == "foto" or not it.get("horizontal", True) or p.get("final") or p.get("heroe"):
                continue
            medio = float(p.get("ini") or 0.0) + p["dur_f"] / (2.0 * fps)      # el centro de la ventana (tambien en lento)
            try:
                if p.get("habla"):
                    # (1.8.7, MEDIDO) la cara mas grande era a veces el padrino, no el sacerdote que hablaba: se
                    # centra la cara de QUIEN HABLA (la boca que se mueve; si no, la IA de vista); si no se sabe quien
                    # es, el plano queda abierto (da mas contexto que acercarse a una cara cualquiera)
                    c = None
                    if p.get("voz_momento") == "IGLESIA" and p.get("voz_tipo") in ("PASTOR", "DISCURSO"):
                        c = enc.el_sacerdote(it["ruta"], medio)      # (1.8.7) el sermon es del sacerdote, no del novio
                    if c is None:
                        c = enc.quien_habla(it["ruta"], medio)
                    if c:
                        z = ZOOM_HABLA[1] if p["habla"] == 2 else ZOOM_HABLA[0]
                        if c[2] > 0.30:                  # la cara ya ocupa mucho: no tanto
                            z = 1.0 + (z - 1.0) * 0.5
                        else:
                            # (1.8.7, visto en NUESTRA BODA: con 1,12x quien hablaba al borde se quedaba al borde y en la
                            # casa las caras eran de 5 % del alto) que su cara quede de plano medio la 1.a vez y medio
                            # corto la 2.a, y lo bastante para traerla al centro, sin pasar de lo que la toma da nitido
                            # (4K en una linea de 1080: hasta 2x)
                            z_max = max(ZOOM_HABLA[1], min(ZOOM_HABLA_MAX if c[2] >= CARA_HABLA_SEGURA else 1.5,
                                                           float(it.get("ancho") or 1920) / 1920.0))
                            z = max(z, CARA_HABLA[1 if p["habla"] == 2 else 0] / max(c[2], 0.01))
                            lejos = abs(c[0] - 0.5) * 2.0
                            if lejos < 0.95:
                                z = max(z, 1.0 / (1.0 - lejos))
                            z = round(min(z, z_max), 3)
                        pan, tilt = enc.acercar(c[0], c[1], z, (0.5, 0.42))
                        p["encuadre"] = (z, pan, tilt)
                        n_c += 1
                elif p["tipo"] == "dron":
                    s = enc.sujeto_aereo(it["ruta"], medio)
                    if s and (abs(s[0] - 0.5) > 0.12 or abs(s[1] - 0.5) > 0.12):
                        pan, tilt = enc.acercar(s[0], s[1], ZOOM_AEREO)
                        p["encuadre"] = (ZOOM_AEREO, pan, tilt)
                        n_a += 1
            except Exception:
                continue
    return n_c, n_a


def _partir_habla(v, piezas, z0, j, plan, fps):
    """(1.8.7) Si se ve a quien habla mas de VOZ_HABLA_MAX_S, el plano se parte en una pausa cerca de la mitad: la
    segunda parte es otra camara en el mismo instante (sincronia) o, si no hay, una foto de ese momento (la novia, los
    invitados: reacciones), y la voz sigue sonando encima. True si lo partio."""
    if plan is None:
        return False
    p, c = piezas[j], v["item"]
    if p["dur_f"] / float(fps) <= VOZ_HABLA_MAX_S:
        return False
    ini = _inicios(piezas, z0)
    medio = ini[j] + p["dur_f"] // 2
    pausas = []
    ors = v.get("oraciones") or []
    for o1, o2 in zip(ors, ors[1:]):
        if o2[0] - o1[1] >= 0.12:
            pausas.append(v["pos"] + int(round(((o1[1] + o2[0]) / 2.0 - v["ini"]) * fps)))
    cerca = [x for x in pausas if ini[j] + int(2.5 * fps) <= x <= ini[j] + p["dur_f"] - int(2.0 * fps)]
    corte = min(cerca, key=lambda x: abs(x - medio)) if cerca else medio
    d1 = corte - ini[j]
    d2 = p["dur_f"] - d1
    t_c = v["ini"] + (corte - v["pos"]) / float(fps)      # el instante de la voz en el corte
    nueva = None
    por_ruta = {x["ruta"]: x for x in plan.vids}
    for s_ in c.get("simultaneas") or []:
        b = por_ruta.get(s_.get("ruta"))
        if b is None or b is c or not s_.get("audio") or not plan.puede_usar(b):
            continue
        tb = t_c - s_["desde"]
        if any(a0 <= tb and tb + d2 / float(fps) <= a1 for a0, a1 in plan.utiles(b)):
            nueva = plan._pieza(b, tb, d2)
            nueva.update({"sincro": True, "multicam": True, "reaccion": True})
            break
    if nueva is None:                                     # una foto de ese momento, la mas cercana en el tiempo
        try:
            hora = _hora(c, t_c)
            fotos = [f for f in plan.fotos if f["ruta"] not in plan.fotos_usadas
                     and f.get("momento") == Planificador.momento_en(c, t_c) and (f.get("ia") or {}).get("util") is not False
                     and f.get("caras")]
            f = min(fotos, key=lambda f: abs((_hora(f) - hora).total_seconds())) if fotos else None
        except Exception:
            f = None
        if f is None or abs((_hora(f) - hora).total_seconds()) > 900:
            return False
        plan.fotos_usadas.add(f["ruta"])
        nueva = {"tipo": "foto", "item": f, "dur_f": d2, "orden": _hora(f), "momento": f.get("momento"),
                 "relleno": True, "reaccion": True, "hash": int(f["dhash"], 16) if f.get("dhash") else None}
    p["dur_f"] = d1
    piezas.insert(j + 1, nueva)
    return True


def _reaccion(v, piezas, z0, j, largo, plan, fps):
    """(1.8.7) Despues de ver a quien habla, OTRA camara en el MISMO instante (las «simultaneas» que confirmo el
    sonido): la novia escuchando, los invitados... reacciones de verdad, en sincronia. True si puso una."""
    if plan is None or j + 1 >= len(piezas):
        return False
    if _partir_habla(v, piezas, z0, j, plan, fps):
        return True
    c = v["item"]
    ini = _inicios(piezas, z0)
    k = j + 1
    if ini[k] >= v["pos"] + largo - int(1.0 * fps) or piezas[k].get("final") or piezas[k].get("heroe"):
        return False
    t_c = v["ini"] + (ini[k] - v["pos"]) / float(fps)     # el instante de la voz cuando entra el plano k
    d = piezas[k]["dur_f"] / float(fps)
    por_ruta = {x["ruta"]: x for x in plan.vids}
    for s_ in c.get("simultaneas") or []:
        b = por_ruta.get(s_.get("ruta"))
        if b is None or b is c or not s_.get("audio") or not plan.puede_usar(b):
            continue
        tb = t_c - s_["desde"]
        if any(a0 <= tb and tb + d <= a1 for a0, a1 in plan.utiles(b)):
            nueva = plan._pieza(b, tb, piezas[k]["dur_f"])
            nueva.update({"sincro": True, "multicam": True, "reaccion": True})
            piezas[k] = nueva
            return True
    return False


def _misma_toma_en_sincro(v, piezas, z0, largo, fps):
    """(1.8.7) Bajo la voz, otro plano de la MISMA toma (otra parte de quien habla) se le veria mover los labios con
    otras palabras: se pone en el instante que suena (sincronia)."""
    c, n = v["item"], 0
    ini = _inicios(piezas, z0)
    fin_v = v["pos"] + largo
    for k, p in enumerate(piezas):
        if p.get("sincro") or p["tipo"] == "foto" or p.get("item") is not c:
            continue
        if ini[k] + p["dur_f"] <= v["pos"] or ini[k] >= fin_v:
            continue
        t = v["ini"] + (ini[k] - v["pos"]) / float(fps)
        if 0.2 <= t and t + p["dur_f"] / float(fps) <= c["dur"] - 0.2:
            p["ini"] = t
            p["sincro"] = True
            for clave in ("vel", "lento_natural", "conformado"):
                p.pop(clave, None)
            n += 1
    return n


def _cortes_en_pausas(v, piezas, z0, largo, fps):
    """(1.8.7) Bajo la voz los cortes caen en las PAUSAS entre oraciones (no a media palabra): cada corte se mueve a
    la pausa mas cercana si esta a menos de VOZ_PAUSA_TOL_S. Devuelve cuantos movio."""
    ors = v.get("oraciones") or []
    pausas = []
    for o1, o2 in zip(ors, ors[1:]):
        if o2[0] - o1[1] >= 0.12:
            pausas.append(v["pos"] + int(round(((o1[1] + o2[0]) / 2.0 - v["ini"]) * fps)))
    if not pausas:
        return 0
    fin_v = v["pos"] + largo
    tol = int(VOZ_PAUSA_TOL_S * fps)
    movidos, pos = 0, z0
    for k in range(len(piezas) - 1):
        pos += piezas[k]["dur_f"]                        # el corte entre k y k+1
        if pos <= v["pos"] + int(0.5 * fps) or pos >= fin_v - int(0.3 * fps):
            continue
        cerca = min(pausas, key=lambda x: abs(x - pos))
        delta = cerca - pos
        if 0 < abs(delta) <= tol and _mover_corte(piezas, k, delta, fps):
            pos += delta
            movidos += 1
    return movidos


def ubicar_voces(voces, zonas, plan, fps):
    """A cada voz su lugar en la linea. (1.8.7) Como en una pelicula de bodas:
      - HISTORIA: donde el video cuenta ESE momento (la hora real de la voz: las tomas de alrededor son de ahi). La voz
        entra VOZ_ADELANTO_S antes de ver a quien habla (corte J), se le ve decirlo en sincronia, luego otra camara en el
        mismo instante (reacciones) y tomas de ese momento; deja de verse antes de que termine la voz (corte L).
      - APERTURA: al empezar el primer capitulo, sobre los preparativos, sin ver a quien habla (adelanto).
      - CIERRE: termina poco despues de que entra la imagen final (sobre la ultima aerea y la foto final).
    Bajo cada voz los cortes caen en las pausas entre oraciones. Pone v['pos'] (cuadros desde el inicio de la linea)
    y devuelve las que caben."""
    puestas = []
    # (1.8.7, MEDIDO en NUESTRA BODA 30 min: la toma del sacerdote se vio 5 veces en 100 s, una por frase) quien habla se
    # ve como mucho HABLA_MAX_TOMA veces por toma y por version; sus otras frases van sobre otras tomas (ya se sabe
    # quien es: la persona, «no repitas más de 2 veces una toma ni de la misma escena»)
    vistas = {}
    for nombre, z0, z1, piezas in zonas:
        vs = [v for v in voces if v["zona"] == nombre]
        if not vs:
            continue
        tope = z1 - int(2.0 * fps)
        for v in [v for v in vs if v.get("papel") == "cierre"]:
            largo = int(round((v["fin"] - v["ini"]) * fps))
            ini = _inicios(piezas, z0)
            k_fin = next((k for k, p in enumerate(piezas) if p.get("final") or p.get("heroe")), None)
            fin_v = min((ini[k_fin] if k_fin is not None else z1 - int(4.0 * fps)) + int(VOZ_CIERRE_TRAS_S * fps),
                        z1 - int(0.5 * fps))
            if fin_v - largo >= z0 + int(2.0 * fps):
                v["pos"] = fin_v - largo
                tope = min(tope, v["pos"] - int(3.0 * fps))
        libre = z0 + int(2.0 * fps)
        for v in vs:
            largo = int(round((v["fin"] - v["ini"]) * fps))
            papel = v.get("papel", "historia")
            ini = _inicios(piezas, z0)
            if papel == "cierre":
                if v.get("pos") is None:
                    continue
            elif papel == "apertura":            # sobre la aerea que abre el capitulo (no hace falta un corte)
                if z0 + int(2.0 * fps) + largo > tope:
                    continue
                v["pos"] = z0 + int(2.0 * fps)
            else:
                cand = [j for j, x in enumerate(ini) if libre <= x and x + largo <= tope
                        and not piezas[j].get("final") and not piezas[j].get("heroe")]
                if not cand:
                    continue
                try:
                    hv = _hora(v["item"], v["ini"])
                    j = min(cand, key=lambda j: abs((piezas[j]["orden"] - hv).total_seconds())
                            if piezas[j].get("orden") else 1e9)
                except Exception:
                    quiero = z0 + int((len(puestas) % 3 + 0.5) / 3.0 * (z1 - z0)) - largo // 2
                    j = min(cand, key=lambda j: abs(ini[j] - quiero))
                lead = int(round(VOZ_ADELANTO_S * fps))
                if j == 0 or ini[j] - lead < libre or piezas[j - 1].get("sincro") or \
                        piezas[j - 1]["dur_f"] < lead + int(0.6 * fps):
                    lead = 0
                v["pos"] = ini[j] - lead
                ruta_v = v["item"].get("ruta")
                if vistas.get(ruta_v, 0) < HABLA_MAX_TOMA and _sincronizar(v, piezas, z0, j, lead, largo, plan, fps):
                    vistas[ruta_v] = vistas.get(ruta_v, 0) + 1
                    _reaccion(v, piezas, z0, j, largo, plan, fps)
            _misma_toma_en_sincro(v, piezas, z0, largo, fps)
            ruta_v = v["item"].get("ruta")
            if papel == "historia" and v.get("sincro") and vistas.get(ruta_v, 0) < HABLA_MAX_TOMA and \
                    _otra_vez_quien_habla(v, piezas, z0, largo, plan, fps):
                vistas[ruta_v] = vistas.get(ruta_v, 0) + 1
            # (1.8.7) quien habla no se ve mas de VOZ_HABLA_MAX_S seguidos: a la mitad, reacciones (otra camara o foto)
            ini2 = _inicios(piezas, z0)
            for k, q in enumerate(piezas):
                if q.get("sincro") and q.get("item") is v["item"] and q["dur_f"] > VOZ_HABLA_MAX_S * fps and                         ini2[k] < v["pos"] + largo and ini2[k] + q["dur_f"] > v["pos"]:
                    _partir_habla(v, piezas, z0, k, plan, fps)
                    break
            _cortes_en_pausas(v, piezas, z0, largo, fps)
            libre = v["pos"] + largo + int(3.0 * fps)
            puestas.append(v)
    return puestas


REACCION_TRAS_S = 4.0         # (1.8.7) s despues de la frase en que se busca la reaccion del publico
REACCION_MIN = 0.4            # cuanto tiene que oirse (0-1 del oido: aplausos, vitores, risas)


def _reaccion_real(tl, mp, c, it, v, x, fps):
    """(1.8.7) Si despues de la frase la gente aplaudio, grito o se rio (lo oyo el oido), ESE sonido entra justo al
    terminar la voz (en la pista del ambiente, sin aislar), mientras la musica vuelve a subir."""
    o = it.get("oido") or {}
    paso, ven = float(o.get("paso") or 0.0), float(o.get("ventana") or 0.0)
    if not paso:
        return False
    fin = v["fin"]
    mejor = max([p for g in ("aplausos", "vitores", "risas") for k, p in enumerate(o.get(g) or [])
                 if k * paso < fin + REACCION_TRAS_S and k * paso + ven > fin + 0.5] or [0.0])
    dur = min(REACCION_TRAS_S, float(it.get("dur") or 0.0) - fin - 0.2)
    if mejor < REACCION_MIN or dur < 1.5:
        return False
    pista = next((t for t in range(1, tl.GetTrackCount("audio") + 1)
                  if (tl.GetTrackName("audio", t) or "").strip().upper() == "EXTRA AUDIO 1"), None)
    if pista is None:
        return False
    vf = float(it.get("fps") or 30)
    rec = x.GetEnd() - int(0.3 * fps)
    largo = int(round((dur + 0.3) * fps))
    if any(y.GetStart() < rec + largo and rec < y.GetEnd() for y in tl.GetItemListInTrack("audio", pista) or []):
        return False
    tl.SetTrackLock("audio", pista, False)
    s0 = int(round((fin - 0.3) * vf))
    r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": s0, "endFrame": s0 + int(round((dur + 0.3) * vf)),
                              "mediaType": 2, "trackIndex": pista, "recordFrame": rec}]) or []
    if not r:
        return False
    try:
        r[0].SetProperty("AudioVolume", -4.0)
        r[0].SetFades({"FadeIn": int(0.25 * fps), "FadeOut": int(1.2 * fps)})
    except Exception:
        pass
    return True


def pista_voz(tl):
    """La pista de voz de la plantilla ("VOZ NATURAL"); si no hay ninguna que empiece con VOZ, crea "VOZ"."""
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if (tl.GetTrackName("audio", t) or "").strip().upper().startswith("VOZ"):
            return t
    if not tl.AddTrack("audio", "stereo"):
        return None
    t = tl.GetTrackCount("audio")
    tl.SetTrackName("audio", t, "VOZ")
    return t


def pulir_voz(x):
    """Voz limpia y pareja con la IA de Resolve Studio, clip por clip: aislamiento de voz (quita musica y murmullo)
    y nivelador de dialogo (sube lo bajo, baja lo fuerte). Devuelve True si se pudo aislar."""
    ok = False
    try:
        ok = bool(x.SetProperty("AudioVoiceIsolationEnabled", True)) and \
            bool(x.SetProperty("AudioVoiceIsolationAmount", VOZ_AISLAR))
    except Exception:
        pass
    try:
        if x.SetProperty("AudioDialogueLevelerEnabled", True):
            x.SetProperty("AudioDialogueLevelerMode", resolve.DIALOGUE_LEVELER_MODE_OPTIMIZE_MODERATE_LEVELS)
            x.SetProperty("AudioDialogueLevelerReduceLoudDialogue", True)
            x.SetProperty("AudioDialogueLevelerLiftSoftDialogue", True)
            x.SetProperty("AudioDialogueLevelerBackgroundReduction", True)
            x.SetProperty("AudioDialogueLevelerOutputGain", VOZ_GANANCIA)
    except Exception:
        pass
    return ok


def poner_voces(tl, mp, pool, voces, fps):
    """Pone cada voz ya ubicada (v['pos']) en la pista VOZ (solo el audio), con fundidos y pulida (aislamiento de voz
    y nivelador de dialogo). Devuelve [(inicio, fin, voz)] en frames de timeline (para bajar la musica debajo)."""
    voces = [v for v in voces if v.get("pos") is not None]
    if not voces:
        return []
    t = pista_voz(tl)
    if t is None:
        aviso("No se pudo crear la pista VOZ.")
        return []
    tl.SetTrackLock("audio", t, False)
    st = tl.GetStartFrame()
    tramos, aisladas = [], 0
    for v in voces:
        it = v["item"]
        c = pool.get(os.path.normcase(it["ruta"]))
        if c is None:
            continue
        vf = float(it.get("fps") or 30)
        s = int(round(v["ini"] * vf))
        e = s + int(round((v["fin"] - v["ini"]) * vf))
        r = mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": s, "endFrame": e, "mediaType": 2,
                                  "trackIndex": t, "recordFrame": st + v["pos"]}]) or []
        if not r:
            continue
        x = r[0]
        try:
            x.SetFades({"FadeIn": VOZ_FUNDIDOS[0], "FadeOut": VOZ_FUNDIDOS[1]})
        except Exception:
            pass
        aisladas += bool(pulir_voz(x))
        tramos.append((x.GetStart(), x.GetEnd(), v))
        try:                                     # (1.8.7) los aplausos o risas de verdad que vinieron despues
            if _reaccion_real(tl, mp, c, it, v, x, fps):
                v["reaccion_real"] = True
        except Exception:
            pass
    if tramos and aisladas < len(tramos):        # sin aislamiento por clip: el de la pista entera
        try:
            tl.SetVoiceIsolationState(t, {"isEnabled": True, "amount": VOZ_AISLAR})
        except Exception:
            pass
    return tramos


def _pistas_musica(tl):
    return [t for t in range(1, tl.GetTrackCount("audio") + 1)
            if "MUSICA" in (tl.GetTrackName("audio", t) or "").upper()
            and "BAJA" not in (tl.GetTrackName("audio", t) or "").upper()]


def _niveles_db(ruta, ini_s, dur_s, paso=0.25):
    """Volumen (dB RMS) de cada `paso` segundos de un tramo de un archivo de audio. [] si no se puede leer."""
    import array
    import subprocess
    if dur_s <= 0 or not ruta or not os.path.exists(ruta):
        return []
    try:
        crudo = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-ss", "%.3f" % max(0.0, ini_s),
                                "-t", "%.3f" % dur_s, "-i", ruta, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
                               capture_output=True, timeout=120, creationflags=rutas.SIN_VENTANA).stdout
    except Exception:
        return []
    m = array.array("h")
    m.frombytes(crudo[:len(crudo) // 2 * 2])
    n = int(8000 * paso)
    res = []
    for i in range(0, len(m) - n + 1, n):
        s = 0
        for x in m[i:i + n]:
            s += x * x
        res.append(10.0 * math.log10(s / float(n) / 1073741824.0 + 1e-12))
    return res


def _final_de_cancion(x, fps, ventana=24.0, paso=0.25):
    """Segundos ANTES del final del clip en que la cancion deja de sonar de verdad (se acaba sola, se va apagando o
    el archivo trae silencio). 0 = suena hasta el corte. Mira los ultimos `ventana` segundos."""
    mpi = x.GetMediaPoolItem()
    ruta = mpi.GetClipProperty("File Path") if mpi else ""
    dur = x.GetDuration() / float(fps)
    v = min(ventana, dur)
    niv = _niveles_db(ruta, x.GetLeftOffset() / float(fps) + dur - v, v, paso)
    if len(niv) < 8:
        return 0.0
    ref = _mediana(niv[:len(niv) // 2])                  # lo normal de la cancion, antes del final
    ultimo = -1
    for i, d in enumerate(niv):
        if d >= ref - 10.0:
            ultimo = i
    return max(0.0, (len(niv) - 1 - ultimo) * paso)


def _entrada_de_cancion(x, fps, ventana=12.0, paso=0.25):
    """Segundos desde el inicio del clip hasta que la cancion se empieza a oir (silencio o entrada muy baja)."""
    mpi = x.GetMediaPoolItem()
    ruta = mpi.GetClipProperty("File Path") if mpi else ""
    v = min(ventana, x.GetDuration() / float(fps))
    niv = _niveles_db(ruta, x.GetLeftOffset() / float(fps), v, paso)
    if len(niv) < 8:
        return 0.0
    ref = _mediana(niv[len(niv) // 3:])
    for i, d in enumerate(niv):
        if d >= ref - 18.0:
            return i * paso
    return 0.0


def _mover_cancion(tl, mp, x, pista_n, d, fps):
    """Mueve una cancion `d` cuadros (positivo = mas tarde) sin cambiarle el punto donde empieza ni el largo. Resolve
    no mueve clips por script: se quita y se vuelve a poner. Devuelve el clip nuevo, o None si no se pudo mover."""
    mpi = x.GetMediaPoolItem()
    if mpi is None or not d:
        return None
    r0, r1 = x.GetStart(), x.GetEnd()
    try:
        s0 = x.GetSourceStartFrame()
        fades = x.GetFades() or {}
        vol = x.GetProperty("AudioVolume")
    except Exception:
        return None
    k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
    fin = s0 + int(round((r1 - r0) * k))                 # en audio el cuadro final no se incluye (probado)
    if not tl.DeleteClips([x], False):
        return None
    movido = True
    nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0, "endFrame": fin, "mediaType": 2,
                                  "trackIndex": pista_n, "recordFrame": r0 + d}]) or []
    if not nuevo:                                        # no se pudo: se deja donde estaba
        movido = False
        nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": s0, "endFrame": fin, "mediaType": 2,
                                      "trackIndex": pista_n, "recordFrame": r0}]) or []
    if not nuevo:
        return None
    y = nuevo[0]
    try:
        if vol is not None:
            y.SetProperty("AudioVolume", float(vol))
        y.SetFades({"FadeIn": int(fades.get("FadeIn", 0)), "FadeOut": int(fades.get("FadeOut", 0))})
    except Exception:
        pass
    return y if movido else None


def cruces_de_musica(tl, mp, fps):
    """Cambio de cancion que no se note. Midiendo el sonido de cada cancion, de la ULTIMA hacia la primera (la entrada
    de la cancion de la fiesta es la que mas importa que caiga en su sitio):
    - La que SALE se acaba antes de que entre la siguiente (termina, se va apagando, el archivo trae silencio o es mas
      corta que su sitio en la plantilla): quedaban huecos casi en silencio de varios segundos. Si le queda cancion,
      se alarga; si no, se RETRASA entera para que termine justo donde entra la otra. El retraso se acumula hacia
      atras hasta una cancion a la que si le sobra musica (la primera), que se alarga.
    - La que sale sigue sonando hasta el corte: en la plantilla se cruzan 2 s con dos fundidos iguales y en el medio
      el volumen hace un hueco. La que sale se alarga y se apaga despacio mientras la otra ya subio.
    Devuelve cuantos cambios arreglo."""
    clips = []
    for t in _pistas_musica(tl):
        if "INTRO" in (tl.GetTrackName("audio", t) or "").upper():
            continue
        tl.SetTrackLock("audio", t, False)
        for x in tl.GetItemListInTrack("audio", t) or []:
            if x.GetDuration() and x.GetDuration() > 8 * fps:
                clips.append([x, t])
    clips.sort(key=lambda c: c[0].GetStart())
    n = 0
    for i in range(len(clips) - 2, -1, -1):
        (a, ta), b = clips[i], clips[i + 1][0]
        cruce = a.GetEnd() - b.GetStart()
        if not -(CRUCE_RETRASO_MAX + 20) * fps <= cruce <= 6 * fps:      # ni se tocan ni estan cerca
            continue
        try:
            # (17-nov, medido en el de 15 min: 2,5 s de silencio) dos pistas PROPIAS del mismo papel puestas seguidas
            # (musica_propia las encadena: una acaba en su final y la otra entra en su primer golpe) no son un «cambio
            # de cancion» que arreglar: alargar la que sale la metia en su cola de silencio y la otra entraba 4 s tarde
            ra = os.path.normcase(a.GetMediaPoolItem().GetClipProperty("File Path") or "")
            rb = os.path.normcase(b.GetMediaPoolItem().GetClipProperty("File Path") or "")
            propia = os.path.normcase(os.path.join(rutas.RECURSOS, "musica"))
            if abs(cruce) <= 2 and ra.startswith(propia) and rb.startswith(propia) and any(
                    p in os.path.basename(ra).upper() and p in os.path.basename(rb).upper()
                    for p in ("FIESTA", "ROMANTICA", "EPICA")):
                continue
        except Exception:
            pass
        try:
            cola = _final_de_cancion(a, fps)                         # s finales en que la que sale ya no suena
            # cuadros que le faltan a la que sale para sonar hasta 1,5 s despues de entrar la otra
            entra = _entrada_de_cancion(b, fps) if cola > 0.75 or cruce < 0 else 0.0     # la otra puede entrar muy bajito
            hasta = b.GetStart() + int((1.5 + min(entra, 4.0)) * fps)
            falta = hasta - (a.GetEnd() - int(round(cola * fps)))
            if falta > int(0.5 * fps):
                if cola <= 0.75:                                     # le queda cancion: se alarga
                    extra = int(min(falta + int(CRUCE_SALE_S * fps * 0.5), max(0, a.GetRightOffset())))
                    if extra > 0 and a.SetRightOffset(a.GetRightOffset() - extra):
                        cola = _final_de_cancion(a, fps)
                        falta = hasta - (a.GetEnd() - int(round(cola * fps)))
                if falta > int(0.5 * fps):                           # se acabo: entera mas tarde
                    nuevo = _mover_cancion(tl, mp, a, ta, int(min(falta, CRUCE_RETRASO_MAX * fps)), fps)
                    if nuevo is not None:
                        a = clips[i][0] = nuevo
                fa, fb = a.GetFades() or {}, b.GetFades() or {}
                a.SetFades({"FadeIn": int(fa.get("FadeIn", 0)),
                            "FadeOut": int(min(CRUCE_SALE_S, max(2.0, cola + 1.0)) * fps)})
                b.SetFades({"FadeIn": int(min(CRUCE_ENTRA_S, 1.5) * fps), "FadeOut": int(fb.get("FadeOut", 0))})
                n += 1
                continue
            extra = int(min(CRUCE_CANCIONES_S * fps, max(0, a.GetRightOffset())))
            if cola <= 0.75 and extra > 0 and a.SetRightOffset(a.GetRightOffset() - extra):
                cruce = a.GetEnd() - b.GetStart()
            if cruce < fps:                      # ni asi se cruzan: se quedan como estaban
                continue
            fa, fb = a.GetFades() or {}, b.GetFades() or {}
            sale = int(min(CRUCE_SALE_S * fps, cruce, a.GetDuration() // 3))
            entra_f = int(min(CRUCE_ENTRA_S * fps, cruce, b.GetDuration() // 3))
            a.SetFades({"FadeIn": int(fa.get("FadeIn", 0)), "FadeOut": sale})
            b.SetFades({"FadeIn": entra_f, "FadeOut": int(fb.get("FadeOut", 0))})
            n += 1
        except Exception:
            pass
    return n


def bajar_musica(tl, mp, tramos, fps, db=MUSICA_BAJO_VOZ):
    """Baja la musica debajo de cada voz, SIN escalon. Resolve no deja poner keyframes de volumen por script, asi
    que el tramo bajo va en otra pista (PISTA_MUSICA_BAJA) con la misma cancion en el mismo punto: la de arriba se
    apaga en RAMPA_VOZ cuadros mientras la baja entra, y al terminar la voz al reves. Como son la misma senal en
    fase, la suma es una rampa de volumen. Si no se puede crear la pista, corta en la misma pista como antes."""
    if not tramos:
        return 0
    margen_a, margen_b = int(0.7 * fps), int(0.6 * fps)
    zonas = []
    for a, b, _ in sorted((t[0], t[1], 0) for t in tramos):
        a, b = a - margen_a, b + margen_b
        if zonas and a - zonas[-1][1] < int(2.0 * fps):          # dos voces casi seguidas: la musica no sube entre ellas
            zonas[-1] = (zonas[-1][0], max(b, zonas[-1][1]))
        else:
            zonas.append((a, b))
    baja = None
    for t in range(1, tl.GetTrackCount("audio") + 1):
        if (tl.GetTrackName("audio", t) or "").strip().upper() == PISTA_MUSICA_BAJA.upper():
            baja = t
    if baja is None and tl.AddTrack("audio", "stereo"):
        baja = tl.GetTrackCount("audio")
        tl.SetTrackName("audio", baja, PISTA_MUSICA_BAJA)
    R = RAMPA_VOZ if baja else 2
    # (1.8.7) en los videos largos la musica vuelve a subir mas despacio tras la voz (sin golpe de volumen): la subida
    # empieza donde siempre y dura RAMPA_VOZ_SUBE cuadros
    try:
        largo_tl = (tl.GetEndFrame() - tl.GetStartFrame()) / float(fps)
    except Exception:
        largo_tl = 0.0
    R2 = RAMPA_VOZ_SUBE if baja and largo_tl > 200 else R
    if R2 != R:
        zonas = [(a, b + (R2 - R)) for a, b in zonas]
    n = 0
    for t in _pistas_musica(tl):
        tl.SetTrackLock("audio", t, False)
        for x in list(tl.GetItemListInTrack("audio", t) or []):
            r0, r1 = x.GetStart(), x.GetEnd()
            tocan = [(max(a, r0), min(b, r1)) for a, b in zonas if a < r1 and b > r0]
            tocan = [(a, b) for a, b in tocan if b - a > 2 * R]
            if not tocan:
                continue
            try:
                vol = float(x.GetProperty("AudioVolume") or 0.0)
            except Exception:
                vol = 0.0
            if all(a <= r0 and b >= r1 for a, b in tocan):          # todo el clip queda bajo la voz
                n += bool(x.SetProperty("AudioVolume", vol + db))
                continue
            mpi = x.GetMediaPoolItem()
            if mpi is None:
                continue
            try:
                s0 = x.GetSourceStartFrame()
                fades = x.GetFades() or {}
            except Exception:
                continue
            k = float(mpi.GetClipProperty("FPS") or fps) / float(fps)
            # (pista, inicio, fin, volumen, fundido de entrada, fundido de salida)
            cortes, cur = [], r0
            for a, b in sorted(tocan):
                if a > cur:                      # tramo a volumen normal: se apaga R cuadros dentro del tramo bajo
                    cortes.append((t, cur if (cur == r0 or not baja) else cur - R2, a + R if baja else a, vol,
                                   int(fades.get("FadeIn", 0)) if cur == r0 else R2, R))
                cortes.append((baja or t, a, b, vol + db, R if a > r0 else int(fades.get("FadeIn", 0)),
                               R2 if b < r1 else int(fades.get("FadeOut", 0))))
                cur = b
            if cur < r1:
                cortes.append((t, cur - R2 if baja else cur, r1, vol, R2, int(fades.get("FadeOut", 0))))
            if not tl.DeleteClips([x], False):
                continue
            for pista_n, a, b, v, fin_, fout in cortes:
                ini = s0 + int(round((a - r0) * k))
                fin = s0 + int(round((b - r0) * k))          # en audio el cuadro final no se incluye (probado)
                nuevo = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": ini, "endFrame": fin, "mediaType": 2,
                                              "trackIndex": pista_n, "recordFrame": a}]) or []
                if not nuevo:
                    continue
                y = nuevo[0]
                y.SetProperty("AudioVolume", v)
                try:
                    y.SetFades({"FadeIn": fin_, "FadeOut": fout})
                except Exception:
                    pass
            n += 1
    return n


def pista(tl, tipo, nombre, defecto):
    for t in range(1, tl.GetTrackCount(tipo) + 1):
        if (tl.GetTrackName(tipo, t) or "").strip().upper() == nombre:
            return t
    return defecto


def poner_transicion(item, tipo, dur, posicion, alineaciones=("center", "right", "left")):
    for al in alineaciones:
        try:
            if item.AddTransition({"type": tipo, "category": "simple", "position": posicion,
                                   "alignment": al, "duration": int(dur)}):
                return True
        except Exception:
            pass
    return False


SALTO_LUZ = 0.15              # diferencia de luz media (0-1) entre dos planos seguidos que ya pide encadenado


def _luz_pieza(p, fps):
    """Luz media (0-1) del tramo de la toma que usa el plano (lo medido por el analizador cada medio segundo)."""
    col = (p.get("item") or {}).get("color") or []
    if not col or p.get("tipo") == "foto":
        return (p.get("item") or {}).get("brillo", 0.4)
    i0 = int(p.get("ini", 0.0) / PASO_CALIDAD)
    i1 = max(i0 + 1, int((p.get("ini", 0.0) + p.get("dur_f", 0) / float(fps or 24) * p.get("vel", 1.0)) / PASO_CALIDAD))
    tramo = [c[0] for c in col[i0:i1]] or [col[min(i0, len(col) - 1)][0]]
    return sum(tramo) / len(tramo)


def transiciones(tl, pv, zonas, ver, puestos=()):
    tr = ver["tr"]
    st = tl.GetStartFrame()
    try:
        fps = float(tl.GetSetting("timelineFrameRate") or 24)
    except Exception:
        fps = 24.0
    items = sorted([x for x in tl.GetItemListInTrack("video", pv) or [] if x.GetMediaPoolItem() is not None],
                   key=lambda x: x.GetStart())          # sin transiciones (Resolve las lista como items)
    inicios = {st + z0: n for n, z0, _, _ in zonas}
    pieza_en = {}
    for p, x in puestos:
        try:
            pieza_en[x.GetStart()] = p
        except Exception:
            pass
    n_ok = 0
    fallan = []
    for a, b in zip(items, items[1:]):
        if a.GetDuration() is None or b.GetDuration() is None:
            continue
        corte = b.GetStart()
        zona = None
        for n, z0, _, _ in zonas:
            if st + z0 <= corte:
                zona = n
        pa, pb = pieza_en.get(a.GetStart()), pieza_en.get(corte)
        if corte in inicios and inicios[corte] != "APERTURA":
            tipo, dur = "Dip To Color Dissolve", tr["zona"]
        elif tr["suave"] and zona in tr["suaves_en"]:
            tipo, dur = "Cross Dissolve", tr["suave"]
        elif pa and pb and (pa.get("relleno") or pb.get("relleno")):
            # una foto entre videos entra y sale fundida; la imagen final, mas despacio
            tipo, dur = "Cross Dissolve", (FUNDIDO_FOTO * 2 if pb.get("final") else FUNDIDO_FOTO)
        elif pa and pb and zona != "APERTURA" and (_lento_de_verdad(pa) or _lento_de_verdad(pb)):
            tipo, dur = "Cross Dissolve", tr["suave"]         # (16-nov) la camara lenta entra y sale suave
        elif pa and pb and zona != "APERTURA" and abs(_luz_pieza(pa, fps) - _luz_pieza(pb, fps)) >= SALTO_LUZ:
            tipo, dur = "Cross Dissolve", tr["suave"]         # (16-nov) de un plano oscuro a uno claro: sin fogonazo
        elif pa and pb and zona != "APERTURA" and Planificador._parecidas(pa, pb):
            tipo, dur = "Cross Dissolve", FUNDIDO_SALTO          # dos planos casi iguales: fundido corto, no salto
        elif zona == "APERTURA" and tr.get("apertura"):
            tipo, dur = "Cross Dissolve", tr["apertura"]         # (1.5.7) la apertura va al ritmo: fundido cortito
        else:
            continue
        dur = max(2, min(dur, a.GetDuration() // 2, b.GetDuration() // 2))
        if poner_transicion(b, tipo, dur, "start"):
            n_ok += 1
        else:
            fallan.append((b, tipo, dur))
    # (1.8.1, MEDIDO en DaVinci) con el estabilizador ya guardado (9 s en vez de 95) la linea del 15 min salio con 0
    # transiciones de 142: recien puestos los 128 comps de Fusion, la linea no esta «asentada» y AddTransition da False.
    # Las que fallan se reintentan tras una pausa (hasta ~20 s)
    for espera in (2, 4, 6, 8):
        if not fallan:
            break
        time.sleep(espera)
        quedan = []
        for b, tipo, dur in fallan:
            if poner_transicion(b, tipo, dur, "start"):
                n_ok += 1
            else:
                quedan.append((b, tipo, dur))
        fallan = quedan
    if fallan:
        aviso("%s: %d transiciones no se pudieron poner (DaVinci no las aceptó)." % (ver.get("sufijo", ""), len(fallan)))
    if items:                                    # fundido a negro al final
        poner_transicion(items[-1], "Cross Dissolve", min(tr["final"], items[-1].GetDuration() - 2), "end", ("left",))
    return n_ok


def disenar_titulo(it, principal, secundario, frase=False, abajo=False):
    """Titulo con diseno: letra script grande con empuje lento + subtitulo en mayusculas espaciadas,
    halo oscuro y sombra para que se lea sobre cualquier toma. frase=True: frase en script mas pequena en
    el tercio inferior (sin subtitulo), para no tapar la accion. abajo=True: el titulo entero en el tercio
    inferior (la tarjeta final va sobre un retrato: en el centro le tapaba la cara)."""
    comp = it.GetFusionCompByIndex(1)
    if comp is None:
        return False
    d = max(2, it.GetDuration())
    if frase:
        secundario = ""
    comp.Lock()
    try:
        t1 = comp.FindTool("Template")
        if t1 is None:
            return False
        if frase:
            tam = 0.088 if len(principal) <= 26 else 0.076 if len(principal) <= 34 else 0.066
            y = 0.19
        else:
            tam = 0.15 if len(principal) <= 12 else 0.11 if len(principal) <= 24 else 0.085
            y = 0.545 if secundario else 0.5
            if abajo:
                tam *= 0.86
                y -= 0.275
        sube_abajo = 0.26                  # cuanto baja el subtitulo de la tarjeta final
        if VERTICAL:                       # (18-nov) en 9:16 el mismo tamano quedaba diminuto: ~80 % del ancho
            if frase and len(principal) > FRASE_UNA_LINEA_V and "\n" not in principal:
                # «El amor es paciente, el amor es bondadoso» en una linea salia diminuta: en dos, por el espacio mas
                # cercano a la mitad
                medio = len(principal) // 2
                cortes = [i for i, ch in enumerate(principal) if ch == " "]
                if cortes:
                    i = min(cortes, key=lambda k: abs(k - medio))
                    principal = principal[:i].rstrip() + "\n" + principal[i + 1:].lstrip()
            largo = max(len(l) for l in principal.split("\n"))
            tam = max(tam, min(TAM_V_MAX, (0.70 if frase else 0.80) / (ANCHO_SCRIPT_V * max(1, largo))))
            if frase:
                y = Y_FRASE_V                  # sobre los botones de Reels / TikTok, que tapan lo de abajo
            if abajo:
                y += 0.075                     # la fecha quedaba casi en el borde de abajo
                sube_abajo = 0.185
        t1.SetInput("StyledText", principal)
        t1.SetInput("Font", FUENTE_TITULO)
        t1.SetInput("Style", "Regular")
        t1.SetInput("Center", {1: 0.5, 2: y, 3: 0.0})
        escritura = max(int(ESCRITURA_S[0] * 24), min(int(ESCRITURA_S[1] * 24), int(d * 0.25)))   # se escribe
        try:                                                  # empuje lento del nombre
            t1.AddModifier("Size", "BezierSpline")
            t1.SetInput("Size", tam, 0)
            t1.SetInput("Size", tam * 1.045, d)
        except Exception:
            t1.SetInput("Size", tam)
        try:                                                  # el nombre se escribe letra por letra
            t1.AddModifier("End", "BezierSpline")
            t1.SetInput("End", 0.0, 1)
            t1.SetInput("End", 1.0, escritura)
        except Exception:
            pass
        t2 = comp.FindTool("Subtitulo")
        if t2 is None:
            t2 = comp.AddTool("TextPlus", -32768, -32768)
            t2.SetAttrs({"TOOLS_Name": "Subtitulo"})
        t2.SetInput("StyledText", secundario.upper())
        t2.SetInput("Font", FUENTE_SUB)
        t2.SetInput("Style", ESTILO_SUB)
        t2.SetInput("Size", 0.031 * (SUB_V if VERTICAL else 1.0))
        t2.SetInput("Center", {1: 0.5, 2: 0.405 - (sube_abajo if abajo else 0.0), 3: 0.0})
        try:                                                  # el subtitulo se va abriendo
            t2.AddModifier("CharacterSpacing", "BezierSpline")
            t2.SetInput("CharacterSpacing", 1.22, 0)
            t2.SetInput("CharacterSpacing", 1.42, d)
        except Exception:
            t2.SetInput("CharacterSpacing", 1.3)
        # Halo y sombra con los elementos de sombreado del propio Text+ (ligeros). NO usar la herramienta
        # Shadow de Fusion: con suavizado alto pide buffers de decenas de GB y tumba Resolve.
        for t, (halo_suave, sombra_suave, halo_op) in ((t1, (9.0, 2.0, 0.85)), (t2, (6.0, 1.0, 0.9))):
            t.SetInput("Enabled3", 1)                       # elemento 3: "Black Shadow" -> halo centrado
            t.SetInput("ElementShape3", 0)
            t.SetInput("Red3", 0.0)
            t.SetInput("Green3", 0.0)
            t.SetInput("Blue3", 0.0)
            t.SetInput("Opacity3", halo_op)
            t.SetInput("SoftnessX3", halo_suave)
            t.SetInput("SoftnessY3", halo_suave)
            t.SetInput("Offset3", {1: 0.0, 2: 0.0, 3: 0.0})
            t.SetInput("Enabled5", 1)                       # elemento 5: sombra corta abajo a la derecha
            t.SetInput("ElementShape5", 0)
            t.SetInput("Red5", 0.0)
            t.SetInput("Green5", 0.0)
            t.SetInput("Blue5", 0.0)
            t.SetInput("Alpha5", 1.0)
            t.SetInput("Opacity5", 0.75)
            t.SetInput("SoftnessX5", sombra_suave)
            t.SetInput("SoftnessY5", sombra_suave)
            t.SetInput("Offset5", {1: 0.002, 2: -0.003, 3: 0.0})
            try:
                t.SetInput("PriorityBack5", t.GetInput("PriorityBack3"))
            except Exception:
                pass
        m = comp.FindTool("MezclaTitulo")
        if m is None:
            m = comp.AddTool("Merge", -32768, -32768)
            m.SetAttrs({"TOOLS_Name": "MezclaTitulo"})
        fondo = t1
        if VELO_TITULO > 0:                                   # velo eliptico suave: el texto se lee sobre blancos
            velo = comp.FindTool("Velo") or comp.AddTool("Background", -32768, -32768)
            velo.SetAttrs({"TOOLS_Name": "Velo"})
            velo.SetInput("UseFrameFormatSettings", 1)
            for k, v in (("TopLeftRed", 0.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0),
                         ("TopLeftAlpha", VELO_TITULO)):
                velo.SetInput(k, v)
            forma = comp.FindTool("VeloForma") or comp.AddTool("EllipseMask", -32768, -32768)
            forma.SetAttrs({"TOOLS_Name": "VeloForma"})
            forma.SetInput("Width", 1.15 if frase else 0.9)
            forma.SetInput("Height", 0.17 if frase else 0.27 if secundario else 0.2)
            forma.SetInput("SoftEdge", 0.16)
            forma.SetInput("Center", {1: 0.5, 2: 0.19 if frase else (0.47 if secundario else 0.5) - (0.265 if abajo else 0.0)})
            velo.ConnectInput("EffectMask", forma)
            mv = comp.FindTool("MezclaVelo") or comp.AddTool("Merge", -32768, -32768)
            mv.SetAttrs({"TOOLS_Name": "MezclaVelo"})
            mv.ConnectInput("Background", velo)
            mv.ConnectInput("Foreground", t1)
            fondo = mv
        m.ConnectInput("Background", fondo)
        m.ConnectInput("Foreground", t2)
        try:                                                  # el subtitulo entra cuando el nombre ya casi esta
            m.AddModifier("Blend", "BezierSpline")
            m.SetInput("Blend", 0.0, int(escritura * 0.6))
            m.SetInput("Blend", 1.0, escritura + 10)
        except Exception:
            pass
        comp.FindTool("MediaOut1").ConnectInput("Input", m)
        for viejo in ("HaloTitulo", "SombraTitulo"):         # restos de versiones anteriores
            x = comp.FindTool(viejo)
            if x is not None:
                x.Delete()
    finally:
        comp.Unlock()
    return True


def titulos(tl, ver, fps, fecha_txt, perfil, anio):
    st = tl.GetStartFrame()
    total_f = int(ver["seg"] * fps)
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    actos = sorted((int(f), (m.get("name") or "").upper()) for f, m in (tl.GetMarkers() or {}).items()
                   if (m.get("name") or "").upper().startswith("ACTO"))

    def fmt(s):
        return (s or "").replace("{nombre}", NOMBRE_XV).replace("{fecha}", fecha_txt).replace("{anio}", str(anio))
    nombre = NOMBRE_XV or fmt(perfil["titulo"])
    frase = fmt(FRASE) or (fmt(perfil["frase"]) if NOMBRE_XV else "")
    n_ok = 0
    for it in tl.GetItemListInTrack("video", pt) or []:
        n = (it.GetName() or "").upper()
        rel = it.GetStart() - st
        if n.startswith("TEXTO NOMBRE"):
            p1, p2 = nombre, frase
        elif n.startswith("TEXTO FINAL"):
            p1, p2 = nombre, fmt(FECHA_LUGAR) or fecha_txt
            d = min(int(6 * fps), total_f - rel - int(0.5 * fps),        # tarjeta final de hasta 6 s
                    it.GetDuration() + max(0, it.GetRightOffset()))      # (lo que el titulo permita alargar)
            if d > it.GetDuration():
                it.SetRightOffset(it.GetDuration() + it.GetRightOffset() - d)
        elif n.startswith("TEXTO ACTO"):
            etiqueta = ([e for f, e in actos if f <= rel + fps] or [""])[-1]
            clave = next((k for k in ORDEN_ACTOS if k in etiqueta and k in perfil["actos"]), None)
            p1, p2 = [fmt(x) for x in perfil["actos"][clave]] if clave else ("", "")
            if not p1:
                continue
        else:
            continue
        if disenar_titulo(it, p1, p2, abajo=n.startswith("TEXTO FINAL")):
            n_ok += 1
            poner_transicion(it, "Cross Dissolve", 12, "start", ("right",))
            poner_transicion(it, "Cross Dissolve", 12, "end", ("left",))
    return n_ok


# texto de la plantilla -> clave de "plantilla" en el perfil (el primero que coincida; los mas largos primero)
TEXTOS_FIJOS = [("MIS XV AÑOS", "titulo_largo"), ("MIS XV", "titulo"), ("UN SUEÑO QUE EMPIEZA", "frase1"),
                ("TE ELIJO", "intro")]


def textos_plantilla(tl, perfil):
    """Cambia los textos fijos de la plantilla (titulo grande 'MIS XV', frase de la intro) por los del
    tipo de evento. Solo en la timeline del evento: la plantilla no se toca."""
    reemplazos = perfil.get("plantilla") or {}
    if not reemplazos:
        return 0
    n = 0
    for t in range(1, tl.GetTrackCount("video") + 1):
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS, PISTA_TEXTOS):
            continue
        for it in tl.GetItemListInTrack("video", t) or []:
            try:
                comp = it.GetFusionCompByIndex(1)
            except Exception:
                comp = None
            if comp is None:
                continue
            for herr in (comp.GetToolList(False) or {}).values():
                for inp in (herr.GetInputList() or {}).values():
                    iid = (inp.GetAttrs() or {}).get("INPS_ID", "")
                    if not iid.endswith("StyledText"):
                        continue
                    actual = herr.GetInput(iid)
                    if not isinstance(actual, str):
                        continue
                    for clave_txt, clave in TEXTOS_FIJOS:
                        if clave_txt in actual.upper():
                            nuevo = reemplazos.get(clave)
                            if nuevo:
                                herr.SetInput(iid, nuevo.upper() if actual.isupper() else nuevo)
                                n += 1
                            break
    return n


# ------------------------------------------------------------------ textos nuevos (capitulos, frases, gracias)
TEXTO_PNG = os.path.join(rutas.RECURSOS, "TEXTO_TRANSPARENTE.png")
TEXTO_PNG_VERTICAL = os.path.join(rutas.RECURSOS, "TEXTO_VERTICAL.png")
# (1.5.7, la persona: «los captions pasan muy rápido y no están bien distribuidos»): mas tiempo en pantalla, mas
# separacion, menos frases y repartidas en lo que queda de cada momento despues de su capitulo
DUR_CAPITULO, DUR_FRASE, DUR_GRACIAS = 6.0, 7.5, 7.5      # s en pantalla (antes 3,2 / 4 / 4,5; 1.8.6: 5 / 6 / 6,5)
SEPARACION_TEXTOS = 12.0                                  # s minimos entre dos textos (antes 2; 1.8.6: 4)
# (1.8.7, la persona: «que los captions no salgan muy rápido entre cada uno y animaciones más fluidas») menos frases en
# los largos (una cada 150 / 200 s de momento), escritura de 1,5 s, fundidos de 1 s y nunca encima de la voz original
CADA_FRASE = [(60, 30.0), (180, 55.0), (900, 150.0), (1e9, 200.0)]   # (hasta s de version, s de momento por frase)
FUNDIDO_TEXTO = (1.0, 1.2)                                # s de entrada y salida de cada texto (antes 0,5 / 0,6)
ESCRITURA_S = (0.9, 1.6)                                  # s en que el texto se escribe (antes 8-22 cuadros)
TRAS_CORTE_S = 0.3                                        # el texto entra un poco despues del corte, no con el


def png_texto(mp, root, vertical=False):
    """Clip transparente 1920x1080 (06 EFECTOS\\GRAFICOS): base de los textos nuevos de la pista TEXTOS. En el formato
    vertical es de 1080x1920: el texto se compone ya en 9:16 (misma proporcion respecto al ancho, mas aire arriba y
    abajo) en vez de quedar en una franja al centro."""
    nombre = "TEXTO_VERTICAL" if vertical else "TEXTO_TRANSPARENTE"
    ruta = TEXTO_PNG_VERTICAL if vertical else TEXTO_PNG
    c = buscar_clip(root, nombre)
    if c is not None:
        return c
    if not os.path.exists(ruta):
        import subprocess
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=black@0.0:s=%s,format=rgba" % ("1080x1920" if vertical else "1920x1080"),
                        "-frames:v", "1", ruta], creationflags=rutas.SIN_VENTANA)
    efe = carpeta_raiz(mp, root, "EFECTOS")
    gra = next((f for f in efe.GetSubFolderList() or [] if f.GetName() == "GRAFICOS"), None) or \
        mp.AddSubFolder(efe, "GRAFICOS")
    mp.SetCurrentFolder(gra)
    r = mp.ImportMedia([ruta]) if os.path.exists(ruta) else None
    return r[0] if r else None


def poner_vertical(tl):
    """La linea duplicada pasa a 9:16 (1920x1080 -> 1080x1920) con sus propios ajustes: la plantilla y el proyecto no
    se tocan. Lo que no sea vertical llena el cuadro recortado. Devuelve (ancho, alto) o None si Resolve no lo acepto."""
    try:
        w, h = int(tl.GetSetting("timelineResolutionWidth")), int(tl.GetSetting("timelineResolutionHeight"))
    except Exception:
        w, h = 1920, 1080
    if h > w:
        return w, h
    tl.SetSetting("useCustomSettings", "1")
    ok = True
    for clave, valor in (("timelineResolutionWidth", h), ("timelineResolutionHeight", w),
                         ("timelineOutputResolutionWidth", h), ("timelineOutputResolutionHeight", w)):
        ok = bool(tl.SetSetting(clave, str(valor))) and ok
    try:
        tl.SetSetting("timelineInputResMismatchBehavior", "scaleToCrop")
    except Exception:
        pass
    try:
        ok = int(tl.GetSetting("timelineResolutionHeight")) > int(tl.GetSetting("timelineResolutionWidth"))
    except Exception:
        pass
    return (h, w) if ok else None


def nuevo_texto(tl, mp, png, pt, ini, dur, nombre, p1, p2, frase, fps):
    st = tl.GetStartFrame()
    r = mp.AppendToTimeline([{"mediaPoolItem": png, "startFrame": 0, "endFrame": dur - 1, "trackIndex": pt,
                              "recordFrame": st + ini, "mediaType": 1}])
    it = r[0] if r else None
    if it is None:
        return False
    if it.GetDuration() != dur:              # las imagenes entran con duracion fija: se ajusta
        it.SetRightOffset(it.GetRightOffset() + it.GetDuration() - dur)
    try:
        it.SetName(nombre)
    except Exception:
        pass
    comp = it.GetFusionCompByIndex(1) or it.AddFusionComp()
    if comp is None:
        return False
    if comp.FindTool("Template") is None:
        t = comp.AddTool("TextPlus", -32768, -32768)
        t.SetAttrs({"TOOLS_Name": "Template"})
    ok = disenar_titulo(it, p1, p2, frase)
    try:
        it.SetFades({"FadeIn": int(FUNDIDO_TEXTO[0] * fps), "FadeOut": int(FUNDIDO_TEXTO[1] * fps)})
    except Exception:
        pass
    return ok


def textos_extra(tl, mp, png, zonas, fps, perfil, ver, cortes, evitar=()):
    """Capitulo al empezar cada momento, frases repartidas dentro de cada momento (mas en las versiones
    largas) y 'gracias' antes de la tarjeta final (3 min o mas). Nunca encima de otro texto. evitar (1.8.7): los tramos
    de la voz original [(ini, fin)] en cuadros desde el inicio: las frases no van mientras alguien habla."""
    if png is None:
        return 0
    st = tl.GetStartFrame()
    pt = pista(tl, "video", PISTA_TEXTOS, 3)
    tl.SetTrackLock("video", pt, False)
    ocupado = []
    for t in range(1, tl.GetTrackCount("video") + 1):     # textos y titulos que ya hay (V3, V5...)
        if (tl.GetTrackName("video", t) or "").strip().upper() in (PISTA_VIDEOS, PISTA_FOTOS):
            continue
        for x in tl.GetItemListInTrack("video", t) or []:
            if t == pt or x.GetMediaPoolItem() is None:
                ocupado.append((x.GetStart() - st, x.GetEnd() - st))
    m = int(SEPARACION_TEXTOS * fps)
    voz = [(int(a), int(b)) for a, b in evitar or ()]

    def libre(a, b, sin_voz=False):
        return all(b + m <= x0 or a >= x1 + m for x0, x1 in ocupado) and \
            (not sin_voz or all(b <= x0 or a >= x1 for x0, x1 in voz))

    def al_corte(f, margen=1.5):
        cerca = [c for c in cortes if abs(c - f) <= margen * fps]
        return min(cerca, key=lambda c: abs(c - f)) if cerca else int(f)
    n = 0
    caps = perfil.get("capitulos") or {}
    frases = perfil.get("frases") or {}
    cada = next(s for hasta, s in CADA_FRASE if ver["seg"] <= hasta)
    marcas = {(mk.get("name") or "").strip().upper(): int(f) for f, mk in (tl.GetMarkers() or {}).items()}
    cierre = marcas.get("CIERRE", int(ver["seg"] * fps) - 6 * fps)
    for nombre, z0, z1, piezas in zonas:
        if nombre not in ZONAS:
            continue
        # (1.5.7) el evento no tiene ese momento (una boda sin preparativos: la zona se llena con la llegada a la
        # iglesia): ni su capitulo («Los preparativos») ni sus frases
        if piezas and not any((p.get("item") or {}).get("momento") == nombre for p in piezas):
            continue
        z1 = min(z1, cierre)
        d = int(DUR_CAPITULO * fps)
        a = z0 + int(0.4 * fps)
        if nombre in caps and a + d < z1 - fps and libre(a, a + d):
            p1, p2 = (caps[nombre] + [""])[:2]
            if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO CAPITULO " + nombre, p1, p2, False, fps):
                ocupado.append((a, a + d))
                n += 1
        lista = frases.get(nombre) or []
        cuantas = min(len(lista), int((z1 - z0) / float(cada * fps) + 0.5))
        d = int(DUR_FRASE * fps)
        k = 0
        # (1.5.7) repartidas en lo que queda del momento DESPUES de su capitulo (antes podian quedar pegadas a el)
        u0 = z0 + int((DUR_CAPITULO + SEPARACION_TEXTOS) * fps) if nombre in caps else z0
        for j in range(cuantas):
            centro = u0 + (j + 0.5) * (z1 - u0) / float(cuantas)
            for desv in sorted(range(-int((z1 - u0) / (2.0 * (cuantas + 1))), int((z1 - u0) / (2.0 * (cuantas + 1))) + 1,
                                     max(1, fps // 2)), key=abs):
                a = al_corte(centro + desv - d / 2) + int(TRAS_CORTE_S * fps)
                if u0 <= a and a + d <= z1 - fps and libre(a, a + d, sin_voz=True):
                    if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO FRASE %s %d" % (nombre, k + 1), lista[k], "", True, fps):
                        ocupado.append((a, a + d))
                        n += 1
                        k += 1
                    break
    gracias = perfil.get("gracias")
    if gracias and ver["seg"] >= 180:
        d = int(DUR_GRACIAS * fps)
        final = [x.GetStart() - st for x in tl.GetItemListInTrack("video", pt) or []
                 if (x.GetName() or "").upper().startswith("TEXTO FINAL")]
        a = min(final + [cierre]) - m - d                # justo antes de la tarjeta final
        if libre(a, a + d):
            if nuevo_texto(tl, mp, png, pt, a, d, "TEXTO GRACIAS", gracias, "", False, fps):
                n += 1
    return n


def whooshes(tl, mp, zonas, fps, clip):
    if clip is None:
        return 0
    st = tl.GetStartFrame()
    pa = pista(tl, "audio", PISTA_WHOOSH, 7)
    tl.SetTrackLock("audio", pa, False)
    ocupado = [(x.GetStart(), x.GetEnd()) for x in tl.GetItemListInTrack("audio", pa) or []]
    dur = int(2.5 * fps)
    n = 0
    for nombre, z0, _, _ in zonas:
        if nombre == "APERTURA":
            continue
        f = st + z0 - int(0.8 * fps)
        if any(a < f + dur and f < b for a, b in ocupado):
            continue
        nuevo = mp.AppendToTimeline([{"mediaPoolItem": clip, "startFrame": 0, "endFrame": dur - 1, "mediaType": 2,
                                      "trackIndex": pa, "recordFrame": f}])
        if nuevo:
            try:                                 # (1.5.7, «mejora los sfx»): entra y sale suave, no de golpe
                nuevo[0].SetFades({"FadeIn": int(0.25 * fps), "FadeOut": int(0.6 * fps)})
            except Exception:
                pass
            ocupado.append((f, f + dur))
            n += 1
    return n


def buscar_clip(carpeta, clave):
    clave = clave.lower()
    for c in carpeta.GetClipList() or []:
        if clave in (c.GetName() or "").lower():
            return c
    for s in carpeta.GetSubFolderList() or []:
        r = buscar_clip(s, clave)
        if r:
            return r
    return None


def fuente(i):
    if i["tipo"] == "dron" or i.get("origen_hora") == "dji":
        return "DRON"
    return "CELULAR" if i.get("origen_hora") == "iphone" else "CAMARA"


def instalar_dctl(project):
    """Copia los DCTL de la skill a la carpeta de LUTs de Resolve si faltan."""
    import shutil
    origen = os.path.join(SKILL_DIR, "dctl")
    destino = os.path.join(DIR_LUT, "MCP")
    try:
        os.makedirs(destino, exist_ok=True)
        for f in os.listdir(origen):
            o, d = os.path.join(origen, f), os.path.join(destino, f)
            if not os.path.isfile(o) or f.startswith(".") or f.lower() == "desktop.ini":
                continue                         # .cf y desktop.ini son el icono de la carpeta, no DCTL
            if not os.path.exists(d) or open(o, "rb").read() != open(d, "rb").read():
                shutil.copy2(o, destino)                     # copia los que faltan o cambiaron
        project.RefreshLUTList()
    except Exception as ex:
        aviso("No se pudieron instalar los DCTL de color/ruido (%s)" % ex)


def preparar_grupo(grupo, ver=None):
    """Grupo de color de la version: PRE-CLIP = correccion de color universal, POST-CLIP = LOOK.
    El look es el _REC709 (a media fuerza, ver herramientas/suavizar_looks.py): las tomas ya vienen en Rec.709 y el
    look entero les sube demasiado el contraste y la saturacion."""
    try:
        pre, post = grupo.GetPreClipNodeGraph(), grupo.GetPostClipNodeGraph()
        pre.SetLUT(1, DCTL_COLOR)
        pre.SetNodeLabel(1, "1 BASE (TODAS LAS TOMAS)")         # (1.8.1) numerados en el orden de la cadena
        pre.SetNodeEnabled(1, True)
        if ACTIVAR_LUT:
            look = LOOK_REC709.get((ver or {}).get("sufijo"))
            if look and os.path.exists(os.path.join(DIR_LUT, look.replace("/", os.sep))):
                if not post.SetLUT(1, look):
                    aviso("Grupo %s: no se pudo poner el look suave (%s); queda el look entero." % (grupo.GetName(), look))
                else:
                    nombre_look = re.sub(r"^XV_\w+?min_|_REC709\.cube$", "", os.path.basename(look)).replace("_", " ")
                    post.SetNodeLabel(1, "3 LOOK %s (SIN QUEMAR NI SATURAR)" % nombre_look)
            post.SetNodeEnabled(1, True)
    except Exception as ex:
        aviso("Grupo %s: no se pudo preparar el color (%s)" % (grupo.GetName(), ex))


# Carpetas principales del media pool, numeradas para que salgan siempre en este orden.
CARPETAS_RAIZ = {"PLANTILLAS": "01 PLANTILLAS", "EVENTOS": "02 EVENTOS", "VIDEO": "03 VIDEO",
                 "FOTOS": "04 FOTOS", "MUSICA": "05 MUSICA", "EFECTOS": "06 EFECTOS"}
ALIAS_RAIZ = {"EVENTOS": ("SECUENCIAS",)}          # nombres de versiones anteriores


def carpeta_raiz(mp, root, clave, crear=True):
    """Carpeta principal por clave ('VIDEO', 'EVENTOS'...), con o sin numero delante."""
    nombres = (clave,) + ALIAS_RAIZ.get(clave, ())
    for f in root.GetSubFolderList() or []:
        if re.sub(r"^\d+\s+", "", f.GetName()) in nombres:
            return f
    return mp.AddSubFolder(root, CARPETAS_RAIZ.get(clave, clave)) if crear else None


def lotes_sin_secuencia(fotos, tam=100):
    """Resolve junta en UNA «secuencia de imagenes» las fotos con numeros seguidos (IMG_1001.JPG, IMG_1002.JPG...: los
    nombres que pone la camara) cuando entran en la misma llamada, y entonces ninguna sirve para la intro. Repartidas por
    la paridad de su ultimo numero nunca van dos seguidas juntas (con saltos de 2 las deja sueltas)."""
    pares = ([], [])
    for r in fotos:
        nums = re.findall(r"\d+", os.path.splitext(os.path.basename(r))[0])
        pares[int(nums[-1]) % 2 if nums else 0].append(r)
    return [lote[j:j + tam] for lote in pares for j in range(0, len(lote), tam)]


def importar_fotos(mp, dest, faltan):
    """Importa las fotos como fotos sueltas (ver lotes_sin_secuencia) y, si alguna no quedo (Resolve armo una secuencia
    de todos modos), la importa sola: de una en una nunca hace secuencia.
    OJO: aqui no se borra nada del media pool. mp.DeleteClips justo despues de importar cerro DaVinci (2026-11-13: al
    borrar cambia un instante a la pagina Medios y ahi se cayo); una secuencia vieja se queda, no estorba."""
    for lote in lotes_sin_secuencia(faltan):
        mp.SetCurrentFolder(dest)
        mp.ImportMedia(lote)
    hay = {os.path.normcase(c.GetClipProperty("File Path") or "") for c in dest.GetClipList() or []}
    for r in faltan:
        if os.path.normcase(r) not in hay:
            mp.SetCurrentFolder(dest)
            mp.ImportMedia([r])


def organizar_pool(mp, root, evento, items):
    """Media pool profesional: 04 FOTOS\\<EVENTO>\\01 MAQUILLAJE ... y 03 VIDEO\\<EVENTO>\\01 MAQUILLAJE\\CAMARA|
    CELULAR|DRON, cada clip con el color de su momento (morado / verde / rosa). Mueve lo ya importado y solo
    importa lo que falte. Devuelve {ruta: MediaPoolItem}."""
    def sub(padre, nombre, crear=True):
        if padre is root:
            return carpeta_raiz(mp, root, nombre, crear)
        for f in padre.GetSubFolderList() or []:
            if f.GetName() == nombre:
                return f
        return mp.AddSubFolder(padre, nombre) if crear else None

    existentes = {}

    def recorrer(f):
        for c in f.GetClipList() or []:
            r = c.GetClipProperty("File Path")
            if r:
                existentes.setdefault(os.path.normcase(r), (c, f))
        for s in f.GetSubFolderList() or []:
            recorrer(s)
    for top in ("FOTOS", "VIDEO", "DRON"):               # lo ya importado en este u otro evento se MUEVE
        f = sub(root, top, False)
        if f:
            ev = sub(f, evento, False)
            if ev:
                recorrer(ev)                              # primero el evento actual (prioridad)
            for otro in f.GetSubFolderList() or []:
                if otro.GetName() != evento:
                    recorrer(otro)
    pool = {}
    for top, tipos in (("FOTOS", ("foto",)), ("VIDEO", ("video", "dron"))):
        for mom in ZONAS + ["DESCARTADOS"]:
            sel = [i for i in items if i["tipo"] in tipos and
                   ("DESCARTADOS" if i.get("descartar") else i.get("momento")) == mom]
            if not sel:
                continue
            carpeta_mom = sub(sub(sub(root, top), evento), CARPETAS_MOMENTO[mom])
            por_destino = {}
            for i in sel:
                por_destino.setdefault(fuente(i) if top == "VIDEO" else "", []).append(i)
            for nombre_dest, grupo_sel in sorted(por_destino.items()):
                dest = sub(carpeta_mom, nombre_dest) if nombre_dest else carpeta_mom
                mover = [existentes[k][0] for k in (os.path.normcase(i["ruta"]) for i in grupo_sel)
                         if k in existentes and existentes[k][1].GetUniqueId() != dest.GetUniqueId()]
                if mover:
                    mp.MoveClips(mover, dest)
                faltan = [i["ruta"] for i in grupo_sel if os.path.normcase(i["ruta"]) not in existentes]
                mp.SetCurrentFolder(dest)
                if top == "FOTOS":
                    importar_fotos(mp, dest, faltan)
                else:
                    for j in range(0, len(faltan), 100):
                        if not mp.ImportMedia(faltan[j:j + 100]):
                            mp.ImportMedia([{"FilePath": r} for r in faltan[j:j + 100]])
                color = COLORES.get(mom, "Brown")
                for c in dest.GetClipList() or []:
                    r = c.GetClipProperty("File Path")
                    if r:
                        pool[os.path.normcase(r)] = c
                        # (19-nov, medido) SetClipColor tarda 65 ms aunque ya tenga ese color (GetClipColor 0,1 ms):
                        # con 450 clips eran ~30 s en cada armado
                        if c.GetClipColor() != color:
                            c.SetClipColor(color)

    def vaciar_viejas(f):                            # quita carpetas que quedaron vacias
        for s in f.GetSubFolderList() or []:
            vaciar_viejas(s)
        if not (f.GetClipList() or []) and not (f.GetSubFolderList() or []):
            mp.DeleteFolders([f])
    for top in ("FOTOS", "VIDEO", "DRON"):
        f = sub(root, top, False)
        for ev in (f.GetSubFolderList() or []) if f else []:
            vaciar_viejas(ev)
        if top == "DRON" and f and not (f.GetClipList() or []) and not (f.GetSubFolderList() or []):
            mp.DeleteFolders([f])
    return pool


def metadatos_davinci(pool, items):
    """(18-nov, la persona: «deberían estar los metadatos») Lo que se entiende de cada toma, en el panel Metadatos de
    su clip en DaVinci: Descripción (qué pasa), Comentarios (momento · escena · belleza · si sirve), Palabras clave y
    Escena (el momento). Sirve para buscar en el media pool. Solo escribe lo que cambió. Devuelve cuántos clips."""
    try:
        mt = _modulo("metadatos")
    except Exception:
        return 0
    voces, esc = {}, None
    try:
        esc = _modulo("escenas_ia")
        voces = esc.leer_cache() or {}
    except Exception:
        pass
    n = 0
    for i in items:
        c = pool.get(os.path.normcase(i["ruta"]))
        if c is None or not (i.get("ia") or i.get("momento")):
            continue
        try:
            campos = mt.campos_de(i, voces.get(esc._clave(i["ruta"])) if esc else None)
            escrito = mt.leer(i["ruta"])         # lo que el analisis dejo en el archivo (con la receta): lo mismo aqui
            if escrito.get("comentario"):
                campos["comentario"] = escrito["comentario"]
            nuevo = {"Description": campos["titulo"], "Comments": campos["comentario"],
                     "Keywords": campos["etiquetas"].replace("; ", ","), "Scene": campos["descripcion"]}
            if (c.GetMetadata("Comments") or "") == nuevo["Comments"]:
                continue
            if c.SetMetadata(nuevo):
                n += 1
        except Exception:
            pass
    return n


def sanear_pool(mp, pool, items):
    """(17-nov, vertical del XV 8-nov: huecos en NEGRO) Clips del media pool que DaVinci cree de otro largo que el
    archivo que hay hoy en esa ruta (aqui: «VIDEO VERTICAL 035» decia 206 cuadros y el archivo tiene 897; venian de un
    armado anterior del mismo evento, con otros nombres, reenlazados). El plan se hace con el largo real y DaVinci
    recorta con el suyo: el plano sale mas corto y queda un hueco.
    NO se borran del media pool: los usan otras lineas del proyecto y al quitarlos (primer intento, 17-nov) DaVinci se
    quedo 45 minutos colgado invalidando la cache de todas. Aqui solo se le dice al plan cuanto mide de verdad cada
    clip PARA DAVINCI: la toma se usa hasta el menor de los dos largos (queda en i["dur"] solo durante este armado).
    Devuelve cuantas tomas ajusto."""
    n = 0
    for i in items:
        c = pool.get(os.path.normcase(i["ruta"]))
        if c is None or i["tipo"] == "foto" or not i.get("dur"):
            continue
        try:
            cuadros, fps_c = float(c.GetClipProperty("Frames") or 0), float(c.GetClipProperty("FPS") or 0)
        except Exception:
            continue
        if cuadros > 0 and fps_c > 0 and abs(cuadros / fps_c - i["dur"]) > max(0.6, 0.03 * i["dur"]):
            # (1.8.2, MEDIDO en el XV 8-nov: 42 clips asi por el renumerado viejo) DaVinci RELEE el archivo de esa ruta
            # (ReplaceClip, 0,02 s): toma su largo y su codigo de tiempo de verdad y su proxy ya no se rechaza.
            # Si no puede, como antes: el plan usa el largo menor
            try:
                if c.ReplaceClip(i["ruta"]):
                    cuadros, fps_c = float(c.GetClipProperty("Frames") or 0), float(c.GetClipProperty("FPS") or 0)
                    if cuadros > 0 and fps_c > 0 and abs(cuadros / fps_c - i["dur"]) <= max(0.6, 0.03 * i["dur"]):
                        n += 1
                        continue
            except Exception:
                pass
            corto = min(float(i["dur"]), cuadros / fps_c)
            if corto < i["dur"]:
                i["dur_real"] = i["dur"]
                i["dur"] = round(corto, 2)
                for clave in ("calidad", "audio"):       # las series por medio segundo, hasta ahi
                    if isinstance(i.get(clave), list):
                        i[clave] = i[clave][:max(1, int(corto / PASO_CALIDAD))]
            n += 1
    return n


# ------------------------------------------------------------------ todo junto
def main():
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        aviso("No hay proyecto abierto en Resolve.")
        return
    analisis = globals().get("ANALISIS") or _modulo("analizar_material").analizar(BASE, log=print)
    items = decisiones(analisis.get("items") or [])
    analisis = dict(analisis, items=items)
    if not any(i["tipo"] == "foto" for i in items) or not any(i["tipo"] != "foto" for i in items):
        aviso("Faltan fotos o videos en las carpetas.")
        return
    perfil = cargar_perfil(TIPO_EVENTO)
    evento = EVENTO or "%s %s" % (perfil["prefijo"], analisis["fecha"])
    reporte["evento"] = evento
    reporte["tipo"] = TIPO_EVENTO
    reporte["formato"] = FORMATO
    util_v = 0.0
    if VERTICAL:                                     # solo acepta videos grabados en vertical
        vert = [i for i in items if i["tipo"] != "foto" and not i.get("descartar") and not i.get("horizontal", True)]
        util_v = sum(max(0.0, i.get("dur", 0) - sum(b - a for a, b in i.get("oscuros") or [])) for i in vert)
        if not vert:
            aviso("El formato vertical solo usa videos grabados en vertical y en el material no hay ninguno.")
            return
        print("Formato vertical (9:16): %d videos verticales, %s de video." % (len(vert), _min_seg(util_v)))
    f = datetime.date.fromisoformat(analisis["fecha"])
    fecha_txt = "%02d · %02d · %d" % (f.day, f.month, f.year)
    for i, z in enumerate(ZONAS, 1):                 # carpetas del media pool con los nombres del perfil
        CARPETAS_MOMENTO[z] = "%02d %s" % (i, perfil["momentos"].get(z, z).upper())

    tls = {}
    for i in range(1, project.GetTimelineCount() + 1):
        t = project.GetTimelineByIndex(i)
        tls[t.GetName()] = t
    pendientes = []
    for ver in VERSIONES:
        if SOLO and ver["sufijo"] not in SOLO:
            continue
        if VERTICAL and util_v < ver["seg"] * VERTICAL_MATERIAL_MIN:
            aviso("%s no se arma: hay %s de video vertical y hacen falta al menos %s." % (
                etiqueta(ver), _min_seg(util_v), _min_seg(ver["seg"] * VERTICAL_MATERIAL_MIN)))
            continue
        if ver["plantilla"] not in tls:
            aviso("No existe la plantilla '%s' en el proyecto." % ver["plantilla"])
        else:
            pendientes.append((ver, tls[ver["plantilla"]]))
    if not pendientes:
        return
    try:
        fps = int(round(float(pendientes[0][1].GetSetting("timelineFrameRate"))))
    except Exception:
        fps = 24
    intro_f = sum(INTRO_CORTES)
    ritmo = _modulo("ritmo") if CORTAR_AL_RITMO and not globals().get("SIN_RESOLVE") else None   # el plan previo: sin musica

    # ---------- plan (con lo que Resolve entendio de cada escena: votos, brindis, el beso...) ----------
    ia = _modulo("escenas_ia")
    ia.aplicar(items)                            # lo ya escuchado en otros armados (cache)
    protas, huella_personas = ia.aplicar_personas(items, None, TIPO_EVENTO)   # y las personas ya reconocidas

    def planificar():
        reporte["versiones"] = []
        plan = Planificador(items, fps)
        planes = []
        largo_planos = factor_planos()
        for k, (ver, tpl) in enumerate(pendientes):
            if abs(largo_planos - 1.0) > 0.01:          # (18-nov) el slider «Cuántas tomas» de «Qué entra al video»
                ver = dict(ver, corte=tuple(x * largo_planos for x in ver["corte"]),
                           apertura=tuple(x * largo_planos for x in ver["apertura"]))
            rng = random.Random(2000 + k)
            total_f = int(ver["seg"] * fps)
            golpes = []
            if ritmo:
                try:
                    # (17-nov) con musica propia el ritmo es el de ESA musica, no el de la cancion de la plantilla
                    golpes = ritmo.golpes(tpl, fps, BASE, log=print, tramos=_modulo("musica_propia").tramos_ritmo(
                        tpl, fps, TIPO_EVENTO, ritmo.tramos_musica(tpl, fps)))
                except Exception as ex:
                    aviso("%s: no se pudo leer el ritmo (%s)" % (ver["sufijo"], ex))
            plan.poner_estorbo_duro(ver["seg"] <= ESTORBO_DURO_HASTA_S)
            intro = plan.intro(k)
            plan.usados = {}                     # cada version elige de TODO el material: la larga no se queda con las sobras
            plan.usos, plan.escenas, plan.repetidos = {}, [], 0      # (1.8.7) tope de 2 por toma y por escena
            zonas, info_z, al_golpe = [], {}, 0
            capacidad = {m: plan.capacidad_f(m, ver["corte"]) for m in ZONAS}
            for nombre, z0, z1 in repartir_zonas(zonas_de(tpl.GetMarkers() or {}, total_f, intro_f, fps), capacidad,
                                                 fps):
                if nombre == "APERTURA":
                    # el resumen inicial muestra los mejores momentos: en las versiones largas NO los reserva,
                    # porque luego se cuentan completos en su zona (en 1 y 3 min si, para no repetir planos)
                    reservados = {k: list(v) for k, v in plan.usados.items()}
                    usos_antes = (dict(plan.usos), list(plan.escenas))
                    if ver["seg"] > 180:                 # (1.8.7) en el adelanto de los largos, cada toma una vez
                        plan.tope_toma = 1
                    # (18-nov, la persona: «mejora el armado para crear historias») el resumen tambien cuenta el dia
                    # EN ORDEN: una parte de preparativos, otra de ceremonia y otra de fiesta (segun lo que haya de
                    # cada una), no «lo mejor de todo» junto (abria con el pastel y luego volvia al maquillaje)
                    con = [m for m in ZONAS if capacidad.get(m, 0) > 0]
                    if len(con) >= 2:
                        peso = {"MAQUILLAJE": 0.25, "IGLESIA": 0.30, "FIESTA": 0.45}
                        total_p = sum(peso[m] for m in con)
                        piezas, reusos, queda = [], 0, z1 - z0
                        for n_m, m in enumerate(con):
                            parte = queda if n_m == len(con) - 1 else int(round((z1 - z0) * peso[m] / total_p))
                            if parte < int(ver["apertura"][0] * fps):
                                continue
                            p_m, r_m = plan.zona([m], parte, ver["apertura"], rng, n_m == 0)
                            piezas += p_m
                            reusos += r_m
                            queda -= sum(p["dur_f"] for p in p_m)
                    else:
                        piezas, reusos = plan.zona(ZONAS, z1 - z0, ver["apertura"], rng, True)
                    if ver["seg"] > 180:
                        plan.usados = reservados
                        # (1.8.7) el resumen es un ADELANTO de lo que luego se cuenta completo: sus planos no gastan
                        # los 2 usos de cada toma (con ellos el de 30 min se quedaba sin video para los capitulos)
                        plan.usos, plan.escenas = usos_antes
                    plan.tope_toma = None
                    lo = ver["apertura"][0]
                else:
                    antes_u = {k: list(v) for k, v in plan.usados.items()}
                    antes_c = (dict(plan.usos), list(plan.escenas), plan.repetidos)
                    # (1.8.7) en los videos largos TODOS los capitulos abren desde el aire (si hay dron de ese momento)
                    abre_dron = nombre != "MAQUILLAJE" or ver["seg"] > 180
                    piezas, reusos = plan.zona([nombre], z1 - z0, ver["corte"], rng, abre_dron,
                                               ver["sufijo"] in RELLENO_FOTOS)
                    if reusos and plan.estorbo_duro and not ESTRICTO:
                        # (17-nov) en 1 y 3 min el «estorbo» (alguien delante, pegado al lente) queda fuera, pero la
                        # vista lo marca de mas (328 de 1368 cuadros; de 12 mirados, la mitad eran tomas buenas): si
                        # sin esas tomas hay que REPETIR, entran (con su peso bajo) antes que repetir
                        con_u = plan.usados
                        con_c = (plan.usos, plan.escenas, plan.repetidos)
                        plan.usados = antes_u
                        plan.usos, plan.escenas, plan.repetidos = dict(antes_c[0]), list(antes_c[1]), antes_c[2]
                        plan.poner_estorbo_duro(False)
                        p2, r2 = plan.zona([nombre], z1 - z0, ver["corte"], rng, abre_dron,
                                           ver["sufijo"] in RELLENO_FOTOS)
                        plan.poner_estorbo_duro(True)
                        if r2 < reusos:
                            piezas, reusos = p2, r2
                        else:
                            plan.usados = con_u
                            plan.usos, plan.escenas, plan.repetidos = con_c
                    lo = ver["corte"][0]
                multicam = plan.multicamara(piezas)
                al_golpe += al_ritmo(piezas, z0, z1, golpes, fps, lo)
                zonas.append((nombre, z0, z1, piezas))
                info_z[nombre] = {"seg": round((z1 - z0) / float(fps), 1),
                                  "videos": sum(1 for p in piezas if p["tipo"] != "foto"),
                                  "dron": sum(1 for p in piezas if p["tipo"] == "dron"),
                                  "fotos": sum(1 for p in piezas if p["tipo"] == "foto"),
                                  "relleno_dron": plan.relleno["dron"], "reutilizados": reusos,
                                  "multicamara": multicam}
                if reusos:
                    aviso("%s %s: %d planos repiten video ya usado (falta material)." % (ver["sufijo"], nombre, reusos))
            try:                                 # el FINAL: un solo plano, el mejor, en camara lenta
                marcas = {(m.get("name") or "").strip().upper(): int(f) for f, m in (tpl.GetMarkers() or {}).items()}
                antes = FINAL_ANTES_S if ver["seg"] > 60 else 0.5       # en el de 1 minuto cada segundo cuenta
                c0 = marcas.get("CIERRE", total_f - 6 * fps) - int(antes * fps)
                if zonas and c0 > zonas[-1][1] + 2 * fps:
                    nombre_z, z0, z1, piezas = zonas[-1]
                    h = plan.foto_final(z1 - c0) or plan.heroe(z1 - c0)
                    if h is not None:
                        pos, quedan = z0, []
                        for p in piezas:
                            if pos >= c0:
                                break
                            if pos + p["dur_f"] > c0:    # el plano que cruza el final se acorta hasta ahi
                                if c0 - pos < int(0.8 * fps) and quedan:
                                    quedan[-1]["dur_f"] += c0 - pos
                                    pos = c0
                                    break
                                p["dur_f"] = c0 - pos
                            quedan.append(p)
                            pos += p["dur_f"]
                        if pos < c0 and quedan:
                            quedan[-1]["dur_f"] += c0 - pos
                        # (1.8.7, «tomas aéreas en momentos claves») en los videos largos el video se despide desde el
                        # aire: el ultimo plano antes de la imagen final es la mejor aerea de ese momento (si queda)
                        if ver["seg"] > 180 and quedan and quedan[-1]["tipo"] != "dron" and \
                                quedan[-1]["dur_f"] >= int(3.0 * fps):
                            adios = plan.dron_clave([nombre_z], quedan[-1]["dur_f"])
                            if adios is not None:
                                quedan[-1] = adios
                        zonas[-1] = (nombre_z, z0, z1, quedan + [h])
            except Exception as ex:
                aviso("%s: no se pudo preparar el plano final (%s)" % (ver["sufijo"], ex))
            movidos = aplicar_orden(zonas, ("V " if VERTICAL else "") + str(ver["sufijo"]), fps)
            if movidos:
                print("%s: %d planos en el orden que pusiste a mano." % (ver["sufijo"], movidos))
            lentos, estab = plan.marcar_efectos(zonas, fps, LENTOS.get(ver["sufijo"], 2),
                                                LENTO_NATURAL.get(ver["sufijo"], 0.0))
            if plan.repetidos:
                aviso("%s: %d planos pasan de 2 veces la misma toma (no alcanzaron ni las fotos)."
                      % (ver["sufijo"], plan.repetidos))
            planes.append((ver, tpl, intro, zonas))
            reporte["versiones"].append({"timeline": rutas.nombre_linea(evento, etiqueta(ver)), "zonas": info_z,
                                         "fotos_intro": len(intro), "cortes_al_ritmo": al_golpe,
                                         "camara_lenta": lentos, "estabilizar": estab})
            print("%s: %s | %d cortes al ritmo | %d en camara lenta | %d a estabilizar" % (ver["sufijo"], ", ".join(
                "%s %d" % (n, z["videos"]) for n, z in info_z.items()), al_golpe, lentos, estab))
        return plan, planes
    plan, planes = planificar()
    globals()["PLANES"] = planes                 # para las pruebas: el plan sin tocar Resolve
    if plan.accidentales:
        reporte["accidentales"] = plan.accidentales
    if DRY_RUN:
        return

    # ---------- respaldo ----------
    # (1.8.1, MEDIDO: exportar EVENTOS CINEMA entero = 14,4 s y 63 MB en CADA armado) Solo hace falta cuando el armado
    # va a REEMPLAZAR lineas de este evento (rearmar: lo retocado a mano se perderia). Un evento nuevo solo AGREGA lineas.
    try:
        ya_armado = any((project.GetTimelineByIndex(i).GetName() or "").startswith(evento + " - ")
                        for i in range(1, project.GetTimelineCount() + 1)) if evento else True
    except Exception:
        ya_armado = True
    try:
        pm.SaveProject()
        if ya_armado:
            dir_r = rutas.RESPALDOS
            os.makedirs(dir_r, exist_ok=True)
            pm.ExportProject(project.GetName(), os.path.join(
                dir_r, "%s_%s.drp" % (project.GetName(), datetime.datetime.now().strftime("%Y-%m-%d_%H%M"))), False)
    except Exception as ex:
        aviso("No se pudo respaldar el proyecto (%s)" % ex)

    # ---------- media pool clasificado por colores ----------
    mp = project.GetMediaPool()
    root = mp.GetRootFolder()
    instalar_dctl(project)
    rd = _modulo("ruido")
    ruido_n = int(RUIDO) if RUIDO is not None else rd.DEFECTO
    try:                                        # DCTL de ruido con la intensidad elegida
        rd.escribir(ruido_n, os.path.join(rutas.DATOS, "dctl"))
        project.RefreshLUTList()
    except Exception as ex:
        aviso("No se pudo escribir la reduccion de ruido (%s)" % ex)
    reporte["ruido"] = ruido_n
    ruidos = {}                                  # ruta -> ruido medido (el mismo proceso para cualquier video)
    drx_ruido = rd.drx_activo(ruido_n)           # el ruido de DaVinci que la persona dejo guardado (o None)
    if drx_ruido:
        print("Ruido: se usa el ajuste de DaVinci guardado en todas las tomas.")
    try:
        rt = _modulo("ruido_tomas")
    except Exception as ex:
        rt = None
        aviso("No se pudo cargar el medidor de ruido (%s); todas las tomas van con el nivel normal." % ex)
    objetivos = objetivos_de_luz(items)
    sat_evento = objetivo_de_saturacion(items)
    reporte["luz_objetivo"] = {k: round(v, 3) for k, v in objetivos.items()}
    pool = organizar_pool(mp, root, evento, items)
    try:
        viejos_pool = sanear_pool(mp, pool, items)
        if viejos_pool:
            print("Media pool: %d clips medían para DaVinci distinto que su archivo: DaVinci los volvió a leer (los que "
                  "no pudo, el plan los usa con el largo menor)." % viejos_pool)
    except Exception as ex:
        aviso("No se pudo revisar el largo de los clips del media pool (%s)" % ex)
    print("Media pool: %d archivos en carpetas MAQUILLAJE / IGLESIA / FIESTA con colores" % len(pool))
    try:
        n_meta = metadatos_davinci(pool, items)
        if n_meta:
            print("Metadatos en DaVinci: %d clips con su descripción, comentarios, palabras clave y escena." % n_meta)
    except Exception as ex:
        aviso("No se pudieron poner los metadatos en DaVinci (%s)" % ex)
    otra_vez = bool(locals().get("viejos_pool"))     # cambiaron largos: el plan se hace otra vez con ellos
    try:                                         # la IA de Resolve reconoce a las personas (IntelliSearch con caras)
        pares_p = [(pool[os.path.normcase(i["ruta"])], i) for i in items
                   if not i.get("descartar") and os.path.normcase(i["ruta"]) in pool]
        cache_p = ia.reconocer(pares_p, print, renderizando=project.IsRenderingInProgress, raiz=root)
        protas, huella = ia.aplicar_personas(items, cache_p, TIPO_EVENTO)
        otra_vez = otra_vez or huella != huella_personas
        vid = [i for i in items if i["tipo"] == "video" and i.get("caras") is not None]
        fot = [i for i in items if i["tipo"] == "foto" and i.get("caras") is not None]
        reporte["personas"] = {"protagonistas": len(protas), "videos_con_ella": sum(1 for i in vid if i.get("prota")),
                               "videos_sin_caras": sum(1 for i in vid if not i["caras"]),
                               "fotos_con_ella": sum(1 for i in fot if i.get("prota"))}
        if protas:
            print("Personas (IA de DaVinci): la persona festejada sale en %d fotos y %d videos; %d videos sin nadie de frente."
                  % (reporte["personas"]["fotos_con_ella"], reporte["personas"]["videos_con_ella"],
                     reporte["personas"]["videos_sin_caras"]))
    except Exception as ex:
        aviso("No se pudo reconocer a las personas con la IA de DaVinci (%s)" % ex)
    try:                                         # la IA de Resolve escucha los videos: votos, brindis, discursos
        pares = [(pool[os.path.normcase(i["ruta"])], i) for i in items
                 if i["tipo"] == "video" and i.get("audio_pista", True) and not i.get("descartar")
                 and os.path.normcase(i["ruta"]) in pool]
        antes = ia.aplicar(items)
        cache_ia = ia.entender(resolve, project, pares, print)
        if ia.aplicar(items, cache_ia) != antes or otra_vez:
            otra_vez = False
            plan, planes = planificar()          # con las frases nuevas el plan cambia
    except Exception as ex:
        aviso("No se pudo escuchar los videos con la IA de DaVinci (%s)" % ex)
    if otra_vez:                                 # personas nuevas y la escucha fallo: igual se vuelve a planificar
        plan, planes = planificar()
    whoosh = buscar_clip(root, WHOOSH)
    png = png_texto(mp, root, VERTICAL)
    try:
        propios = sfx_propios(mp, root)
    except Exception as ex:
        propios = {}
        aviso("No se pudieron cargar los efectos de sonido propios (%s)" % ex)
    grupos = {g.GetName(): g for g in project.GetColorGroupsList() or []}

    def carpeta_tl():                           # 02 EVENTOS\<EVENTO>: las timelines armadas
        padre = carpeta_raiz(mp, root, "EVENTOS")
        for x in padre.GetSubFolderList() or []:
            if x.GetName() == evento:
                return x
        return mp.AddSubFolder(padre, evento)
    dir_tl = carpeta_tl()
    salida = rutas.videos_terminados(evento)        # Escritorio/EVENTO TERMINADO - <evento>/VIDEO TERMINADO (1.5.7)

    for (ver, tpl, intro, zonas), info in zip(planes, reporte["versiones"]):
        nombre = info["timeline"]
        # (1.5.7) la misma version con el nombre de antes («BODA - 1min»): se reemplaza igual (y no quedan dos)
        for vieja in [n for n in tls if n != nombre and n.startswith(evento + " - ")
                      and rutas.etiqueta_de(n) == rutas.etiqueta_de(nombre)]:
            if REHACER:
                project.SetCurrentTimeline(tpl)
                if mp.DeleteTimelines([tls[vieja]]):
                    del tls[vieja]
            elif nombre not in tls:
                nombre = vieja
        if nombre in tls:
            if not REHACER:
                aviso("%s ya existe; no se toca (REHACER = True para volver a armarla)." % nombre)
                continue
            project.SetCurrentTimeline(tpl)         # Resolve no borra la timeline abierta
            if not mp.DeleteTimelines([tls[nombre]]):
                aviso("No se pudo borrar la version anterior de %s; ciérrala en Resolve y vuelve a armar." % nombre)
                continue
            del tls[nombre]
        mp.SetCurrentFolder(dir_tl)
        tl = None
        for intento in range(4):                # justo despues de borrar, Resolve a veces tarda en liberar el nombre
            tl = tpl.DuplicateTimeline(nombre)
            if tl:
                break
            time.sleep(1.5)
            project.SetCurrentTimeline(tpl)
        if not tl:
            aviso("No se pudo duplicar %s (vuelve a pulsar Armar)" % ver["plantilla"])
            continue
        tls[nombre] = tl
        try:
            mp.MoveClips([tl.GetMediaPoolItem()], dir_tl)
        except Exception:
            pass
        project.SetCurrentTimeline(tl)
        time.sleep(1.0)            # Resolve solo cambia el estado de los clips de la timeline activa y ya asentada
        tl = project.GetCurrentTimeline() or tl
        try:                                    # (17-nov) musica original del tipo de evento en vez de la de la plantilla
            mus = carpeta_raiz(mp, root, "MUSICA")
            propia = next((f for f in mus.GetSubFolderList() or [] if f.GetName() == "MUSICA PROPIA"), None) \
                or mp.AddSubFolder(mus, "MUSICA PROPIA")
            info_musica = _modulo("musica_propia").aplicar(tl, mp, propia, fps, TIPO_EVENTO, print)
        except Exception as ex:
            info_musica = 0
            aviso("Música propia: no se pudo cambiar (%s); queda la de la plantilla." % ex)
        mp.SetCurrentFolder(dir_tl)
        tam_v = None
        if VERTICAL:                            # la copia pasa a 9:16; la plantilla sigue como estaba
            tam_v = poner_vertical(tl)
            if not tam_v:
                aviso("%s: DaVinci no dejo poner la linea en vertical; no se arma." % nombre)
                project.SetCurrentTimeline(tpl)
                mp.DeleteTimelines([tl])
                del tls[nombre]
                continue
            time.sleep(0.5)
        for t in range(1, tl.GetTrackCount("video") + 1):
            for it in tl.GetItemListInTrack("video", t) or []:
                if (it.GetName() or "").strip().upper() in ACTIVAR_SIEMPRE and not it.GetClipEnabled():
                    tl.SetTrackLock("video", t, False)
                    it.SetClipEnabled(True)
        st = tl.GetStartFrame()
        pv, pf = pista(tl, "video", PISTA_VIDEOS, 1), pista(tl, "video", PISTA_FOTOS, 2)
        for t in (pv, pf):
            tl.SetTrackLock("video", t, False)
            viejos = tl.GetItemListInTrack("video", t) or []
            if viejos:
                tl.DeleteClips(viejos, False)

        voces_plan = []
        try:                                    # la voz original (pastor, brindis, discursos): donde va cada una
            voces_plan = ubicar_voces(elegir_voces(items, ver["sufijo"], zonas, fps, plan.accidentales),
                                      zonas, plan, fps)
        except Exception as ex:
            aviso("%s: no se pudo elegir la voz (%s)" % (nombre, ex))
        marcar_acercados(zonas)
        try:                                     # (1.8.7) quien habla, enfocado; las aereas, centradas en lo importante
            n_c, n_a = enfocar(zonas, fps)
            if n_c or n_a:
                print("%s: encuadre automatico: %d planos de quien habla enfocados, %d aereas centradas."
                      % (nombre, n_c, n_a))
        except Exception as ex:
            aviso("%s: no se pudo calcular el encuadre (%s)" % (nombre, ex))
        secuencia, pos = [], st
        for p in intro:
            secuencia.append((pf, pos, p))
            pos += p["dur_f"]
        for _, z0, _, piezas in zonas:
            pos = st + z0
            for p in piezas:
                secuencia.append((pv, pos, p))
                pos += p["dur_f"]
        puestos = colocar(mp, secuencia, pool, fps)
        info["clips"] = len(puestos)
        if len(puestos) < len(secuencia):
            aviso("%s: se pidieron %d clips y se colocaron %d." % (nombre, len(secuencia), len(puestos)))

        grupo = grupos.get(ver["grupo"])
        try:                                    # ruido de cada video de esta version (cada video se mide una sola vez)
            sin_medir = [(p["item"]["ruta"], p["item"].get("dur")) for p, _ in puestos
                         if p["tipo"] != "foto" and os.path.normcase(p["item"]["ruta"]) not in ruidos]
            if rt and sin_medir and ruido_n > 0 and not drx_ruido:
                ruidos.update(rt.medir_varios(sin_medir, print))
        except Exception as ex:
            aviso("No se pudo medir el ruido de los videos (%s); van con el nivel normal." % ex)
        niveles_ruido = {}
        # (1.8.1) un cuadro real del tramo de cada plano, para MEDIR el color antes de ponerlo (color_guardia)
        guardia, img_planos, look_local, vigilados, vigilados_cdl = None, {}, None, {}, {}
        if IGUALAR:
            try:
                guardia = _modulo("color_guardia")
                pedidos = {id(p): (p["item"]["ruta"], round(float(p.get("ini") or 0.0) + p["dur_f"] / float(fps) *
                                                            float(p.get("vel") or 1.0) / 2.0, 1))
                           for p, _ in puestos if p["tipo"] != "foto" and p.get("item", {}).get("ruta")}
                hechas = guardia.cuadros(list(pedidos.values()))
                img_planos = {k: hechas.get(v) for k, v in pedidos.items()}
                lk = LOOK_REC709.get(ver.get("sufijo")) if ACTIVAR_LUT else None
                look_local = os.path.join(SKILL_DIR, "dctl", os.path.basename(lk)) if lk else None
                # el CDL de cada plano y su revision, todos a la vez antes de tocar DaVinci
                trabajos = {}
                for p, _ in puestos:
                    if id(p) in img_planos and img_planos[id(p)] is not None:
                        c0 = cdl_para(p, objetivos.get((p.get("momento") or p["item"].get("momento")), 0.42),
                                      sat_evento, fps)
                        if c0:
                            trabajos[id(p)] = (c0, img_planos[id(p)])
                vigilados_cdl = guardia.vigilar_varios(trabajos, look_local)
            except Exception as ex:
                guardia = None
                aviso("%s: no se pudo medir el color de los planos (%s); va el color calculado." % (nombre, ex))
        for p, x in puestos:                    # llenar cuadro, color del momento, grupo, ruido e igualacion
            try:                                # fotos 3:2 o videos 4:3 llenan el 16:9 sin franjas negras
                if not x.SetProperties({"Scaling": resolve.SCALE_FILL}):
                    x.SetProperty("Scaling", resolve.SCALE_FILL)
            except Exception:
                pass
            try:
                col = COLORES.get((p.get("momento") or p["item"].get("momento")), "Brown")
                if x.GetClipColor() != col:          # (19-nov) 65 ms aunque ya lo tenga
                    x.SetClipColor(col)
                if grupo:
                    x.AssignToColorGroup(grupo)
                if p["tipo"] != "foto":
                    medida = ruidos.get(os.path.normcase(p["item"]["ruta"]))
                    nv = rd.aplicar(x, ruido_n, medida, drx_ruido)
                    if nv is not None:
                        niveles_ruido[nv] = niveles_ruido.get(nv, 0) + 1
                    if nv == "davinci" and not IGUALAR:  # el grado guardado trae el color del clip donde se capturo
                        x.SetCDL({"NodeIndex": "1", "Slope": "1.0 1.0 1.0", "Offset": "0.0 0.0 0.0",
                                  "Power": "1.0 1.0 1.0", "Saturation": "1.0"})
                    if IGUALAR:
                        cdl = cdl_para(p, objetivos.get((p.get("momento") or p["item"].get("momento")), 0.42), sat_evento,
                                       fps)
                        if cdl and id(p) in vigilados_cdl:
                            # (1.8.1) medido con forma de onda / vectorscopio: si estropeaba el plano, va suavizado
                            cdl, fallas, _t = vigilados_cdl[id(p)]
                            for f_ in fallas:
                                vigilados[f_] = vigilados.get(f_, 0) + 1
                            if fallas:
                                vigilados["suavizados"] = vigilados.get("suavizados", 0) + 1
                        if cdl and x.SetCDL(cdl):
                            info["igualados"] = info.get("igualados", 0) + 1
            except Exception:
                pass
        if grupo:
            preparar_grupo(grupo, ver)
        if guardia is not None:
            print("   color medido plano por plano (forma de onda y vectorscopio): %d planos, %d con la corrección "
                  "suavizada%s." % (len(img_planos), vigilados.get("suavizados", 0), (" (" + ", ".join(
                      "%s %d" % (k, v) for k, v in sorted(vigilados.items()) if k != "suavizados") + ")")
                                     if vigilados.get("suavizados") else ""))
        info["ruido"] = rd.resumen(niveles_ruido)
        info["camara_lenta"] = sum(1 for p, _ in puestos if p.get("lento_ok") and not p.get("conformado"))
        info["fotos_relleno"] = sum(1 for p, _ in puestos if p.get("relleno"))
        if not VERTICAL:                                # lo vertical, entero y con los lados llenos
            info["verticales_enteros"] = vestir_verticales(puestos)
        info["estabilizados"] = estabilizar(puestos, fps)
        if ENFOQUE_CINE:
            info["enfoque_cine"] = enfoque_cine(puestos)
        info["acercados"] = acercar(puestos)
        if USAR_VIDEOS_VERTICALES and not VERTICAL:     # en 9:16 los verticales ya entran enteros
            info["reencuadrados"] = reencuadrar(project, puestos)
        info["transiciones"] = transiciones(tl, pv, zonas, ver, puestos)
        info["titulos"] = titulos(tl, ver, fps, fecha_txt, perfil, f.year)
        info["textos_plantilla"] = textos_plantilla(tl, perfil)
        if VERTICAL:                                    # los titulos de la plantilla, enteros dentro del 9:16
            try:
                info["titulos_vertical"] = titulos_a_vertical(tl)
            except Exception as ex:
                aviso("%s: no se pudieron ajustar los titulos de la plantilla al formato vertical (%s)" % (nombre, ex))
        try:
            info["textos_con_halo"] = legibilidad_plantilla(tl)
            info["velos_plantilla"] = velos_plantilla(tl, mp, png, fps, intro_f)
        except Exception as ex:
            aviso("%s: no se pudo dar contraste a los textos de la plantilla (%s)" % (nombre, ex))
        cortes = sorted(x.GetStart() - st for _, x in puestos)
        try:                                     # capitulos, frases y gracias
            info["textos_nuevos"] = textos_extra(tl, mp, png, zonas, fps, perfil, ver, cortes,
                                                 [(v["pos"], v["pos"] + int(round((v["fin"] - v["ini"]) * fps)))
                                                  for v in voces_plan or [] if v.get("pos") is not None])
        except Exception as ex:
            aviso("%s: no se pudieron poner los textos nuevos (%s)" % (nombre, ex))
        try:                                     # (1.6.0) los titulos de los capitulos para YouTube (capitulos.py)
            _modulo("capitulos").guardar_titulos(
                nombre, " · ".join(x for x in (NOMBRE_XV, FRASE or perfil.get("titulo", "")) if x) or "Inicio",
                {z: (v[0] if isinstance(v, (list, tuple)) and v else str(v))
                 for z, v in (perfil.get("capitulos") or {}).items()})
        except Exception as ex:
            aviso("%s: no se pudieron guardar los capitulos (%s)" % (nombre, ex))
        info["whoosh"] = whooshes(tl, mp, zonas, fps, whoosh)
        # (1.8.0, auditoria) donde va la voz original (pastor, brindis): los SFX no la tapan
        tramos_voz = [(v["pos"], v["pos"] + int(round((v["fin"] - v["ini"]) * fps)))
                      for v in voces_plan or [] if v.get("pos") is not None]
        try:                                     # SFX segun el momento (campanas en la iglesia, vitores en la fiesta)
            info["sfx"] = _modulo("sfx").sonorizar(tl, mp, lambda k: buscar_clip(root, k),
                                                   [(n, a, b) for n, a, b, _ in zonas], fps, cortes, print,
                                                   evitar=tramos_voz)
        except Exception as ex:
            aviso("%s: no se pudieron colocar los SFX (%s)" % (nombre, ex))
        try:                                     # los momentos fuertes: subida y golpe a la fiesta, destellos, clics
            ini_fotos, pos_f = [], 0
            for p in intro:
                ini_fotos.append(pos_f)
                pos_f += p["dur_f"]
            info["momentos"] = _modulo("sfx").momentos(tl, mp, propios, fps, ini_fotos, print)
        except Exception as ex:
            aviso("%s: no se pudieron colocar los momentos (%s)" % (nombre, ex))
        try:                                     # (17-nov) overlays de luz propios: destello en cada cambio de momento
            efe_ov = carpeta_raiz(mp, root, "EFECTOS")           # y brillos sobre el nombre y la tarjeta final
            dir_ov = next((x for x in efe_ov.GetSubFolderList() or [] if x.GetName() == "OVERLAYS"), None) or \
                mp.AddSubFolder(efe_ov, "OVERLAYS")
            cambios_ov = [z[1] for z in zonas if z[0] in ZONAS][1:]
            info["overlays"] = _modulo("overlays").poner(resolve, tl, mp, dir_ov, fps, TIPO_EVENTO, VERTICAL,
                                                         cambios_ov, print)
            mp.SetCurrentFolder(dir_tl)
        except Exception as ex:
            aviso("%s: no se pudieron poner los overlays de luz (%s)" % (nombre, ex))
        try:                                     # (17-nov) los gritos, aplausos y risas DE VERDAD de ese plano, bajo la musica
            info["ambiente"] = _modulo("ambiente").poner(tl, mp, pool, puestos, fps, print, evitar=tramos_voz)
        except Exception as ex:
            aviso("%s: no se pudo poner el ambiente real (%s)" % (nombre, ex))
        try:                                     # (18-nov) SFX de emocion donde la IA vio el beso, el pastel, los anillos...
            info["emocion"] = _modulo("sfx").emocion(tl, mp, lambda k: buscar_clip(root, k), puestos, fps,
                                                     propios, print, evitar=tramos_voz)
        except Exception as ex:
            aviso("%s: no se pudieron poner los SFX de emoción (%s)" % (nombre, ex))
        try:                                     # (17-nov) el nombre DETRAS de la persona (recorte local, sin Mascara
            pd_mod = _modulo("persona_delante")  # Magica): solo si tapa una parte de las letras; en 9:16 aun no
            if pd_mod.activo() and not VERTICAL:
                efe_pd = carpeta_raiz(mp, root, "EFECTOS")
                dir_pd = next((x for x in efe_pd.GetSubFolderList() or [] if x.GetName() == "RECORTES"), None) or \
                    mp.AddSubFolder(efe_pd, "RECORTES")
                info["texto_detras"] = pd_mod.aplicar(resolve, project, tl, mp, dir_pd, print)
                mp.SetCurrentFolder(dir_tl)
                if resolve.GetCurrentPage() != "edit":       # el render del tramo deja a DaVinci en Entrega
                    resolve.OpenPage("edit")
                    time.sleep(1.0)
                project.SetCurrentTimeline(tl)
        except Exception as ex:
            aviso("%s: no se pudo poner el texto detrás de la persona (%s)" % (nombre, ex))
        voces = []
        try:                                     # la palabra del pastor, brindis y discursos sobre la musica
            voces = poner_voces(tl, mp, pool, voces_plan, fps)
            info["voces"] = ["%s%s %.0f s%s%s «%s»" % ("" if v.get("papel", "historia") == "historia"
                                                      else v["papel"].upper() + " · ", v["tipo"], v["fin"] - v["ini"],
                                                      " (se le ve hablar)" if v.get("sincro") else "",
                                                      " + aplausos reales" if v.get("reaccion_real") else "",
                                                      v["texto"][:60])
                             for _, _, v in voces]
            try:                                 # (1.8.7) un destello suave al terminar las frases que abren y cierran
                info["destellos_voz"] = _modulo("sfx").tras_voces(tl, mp, propios, voces, fps, print)
            except Exception as ex:
                aviso("%s: no se pudieron poner los destellos de la voz (%s)" % (nombre, ex))
        except Exception as ex:
            aviso("%s: no se pudo poner la voz (%s)" % (nombre, ex))
        try:                                     # cruce entre canciones sin hueco de volumen
            info["cruces_musica"] = cruces_de_musica(tl, mp, fps)
        except Exception as ex:
            aviso("%s: no se pudieron suavizar los cruces de musica (%s)" % (nombre, ex))
        try:                                     # (1.8.7) cruces_de_musica puede atrasar la cancion que sigue al
            if _modulo("sfx").brillo_titulo_sin_hueco(tl, mp, propios, fps):     # titulo: el destello, a su sitio
                print("%s: el destello del titulo termina cuando entra la musica (sin silencio)." % nombre)
        except Exception as ex:
            aviso("%s: no se pudo acomodar el destello del titulo (%s)" % (nombre, ex))
        try:                                     # mezcla medida: canciones, SFX y voz a su nivel (LUFS)
            info["mezcla"] = _modulo("mezcla").nivelar(tl, fps, BASE, print)
        except Exception as ex:
            aviso("%s: no se pudo nivelar el sonido (%s)" % (nombre, ex))
        try:                                     # la musica baja debajo de cada voz
            info["musica_bajada"] = bajar_musica(tl, mp, voces, fps)
        except Exception as ex:
            aviso("%s: no se pudo bajar la musica bajo la voz (%s)" % (nombre, ex))

        total_f = int(ver["seg"] * fps)
        tl.SetMarkInOut(st, st + total_f - 1, "all")
        if ENCOLAR_RENDER:
            try:
                os.makedirs(salida, exist_ok=True)
                for job in project.GetRenderJobList() or []:
                    if job.get("TimelineName") == nombre:
                        project.DeleteRenderJob(job.get("JobId"))
                ajustes = {"SelectAllFrames": False, "MarkIn": st, "MarkOut": st + total_f - 1,
                           "TargetDir": salida, "CustomName": rutas.nombre_video(nombre)}     # «VIDEO FINAL 1 MIN»
                if tam_v:                        # el archivo sale en 9:16, del tamano de la linea
                    ajustes.update({"FormatWidth": tam_v[0], "FormatHeight": tam_v[1]})
                project.SetRenderSettings(ajustes)
                info["render_en_cola"] = bool(project.AddRenderJob())
                if tam_v:                        # la pagina Entrega vuelve al tamano horizontal de siempre
                    project.SetRenderSettings({"FormatWidth": tam_v[1], "FormatHeight": tam_v[0]})
            except Exception as ex:
                aviso("%s: no se pudo encolar el render (%s)" % (nombre, ex))
        if EDITABLE:                             # la plantilla de DaVinci de este video: EVENTO TERMINADO/PLANTILLAS DE LOS VIDEOS
            try:
                carpeta_ed = rutas.plantillas_evento(evento)
                os.makedirs(carpeta_ed, exist_ok=True)
                ruta_ed = os.path.join(carpeta_ed, rutas.nombre_video(nombre) + ".drt")
                info["editable"] = ruta_ed if tl.Export(ruta_ed, resolve.EXPORT_DRT) else None
            except Exception as ex:
                aviso("%s: no se pudo guardar la plantilla editable (%s)" % (nombre, ex))
        print("%s lista: %d clips, %d igualados en color, %d transiciones, %d titulos + %d textos nuevos, %d whoosh, "
              "%d SFX por momento, %d sonidos nivelados, %d en camara lenta, %d estabilizados, %d voces" % (
                  nombre, len(puestos), info.get("igualados", 0), info["transiciones"], info["titulos"],
                  info.get("textos_nuevos", 0), info["whoosh"], len(info.get("sfx") or []), info.get("mezcla", 0),
                  info.get("camara_lenta", 0), info.get("estabilizados", 0), len(info.get("voces") or [])))
        for v in info.get("voces") or []:
            print("   voz: %s" % v)
        if info.get("ruido"):
            print("   ruido quitado segun cada toma: %s" % info["ruido"])
    pm.SaveProject()


if not globals().get("SOLO_DEFINIR"):     # (18-nov) receta.tramos_fuera usa las cuentas (Planificador.vista) sin armar nada
    main()
result = reporte
