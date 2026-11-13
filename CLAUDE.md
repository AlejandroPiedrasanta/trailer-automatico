# Tráiler automático — leer SOLO esto; lo demás se consulta por demanda

- **Qué es:** app PySide6 (Python 3.14, versión en `PROGRAMA/version.txt`) que arma tráilers de eventos (XV, boda, bautizo, graduación, cumpleaños) en DaVinci Resolve Studio 21 y los renderiza. Funciona en Windows y Mac.
- **En Resolve:** base `EVENTOS`, proyecto `EVENTOS CINEMA`, plantillas `TRAILER XV - 1min/3min/15min/30min`.
- **Carpetas:**
  - `1 MATERIAL`: FOTOS · VIDEOS · DRON.
  - `2 VIDEOS TERMINADOS`.
  - `PROGRAMA`: código; `datos/` (cachés, respaldos), `recursos/` (.drp, audio, fuentes), `dctl/`, `compilar/`, `docs/`.
  - `INSTALADORES`.
  - `LEEME.txt`: para la persona.

## Encontrar algo sin leer archivos (en este orden)
1. `python PROGRAMA/mapa_codigo.py mapa <palabras>` da el tema. `mapa id=<tema>` da sus archivos, sus símbolos con la línea y sus notas.
2. `donde <nombre>` · `simbolo <nombre>` (solo el código de esa función) · `modulo <archivo>` · `llamadas <nombre>`.
3. Si falta algo: Grep + Read con `offset`/`limit` (~60 líneas).
4. NUNCA leer enteros: `build_trailers.py`, `trailer_xv.py`, `escena_go.py`, `estilos_inicio.py`, `orbe_mecanica.py`, `SKILL.md`, `PROGRAMA/datos/**`, `PROGRAMA/recursos/**`.

## Mapa de temas (`mapa id=<tema>`)
<!-- MAPA:INICIO (lo escribe PROGRAMA/mapa_codigo.py generar) -->
- **boton-play**: El boton GO hace todo: analizar, armar en DaVinci, renderizar, masterizar, abrir carpeta
- **inicio-escena**: Pantalla de Inicio = la de CineCaptions: esfera de particulas, astrolabio GO, cometas, explosion
- **ventana**: Ventana sin marco: pestanas Material/Textos/Ajustes, bordes, chequeo de arranque, instancia unica
- **material**: 1 MATERIAL: minimos, pedir lo que falta, arrastrar/agregar, y el panel 'Como quedo organizado' (linea del dia)
- **rutas**: Todas las rutas: codigo vs instalado (.exe), DATOS, carpeta de trabajo, Resolve y LUT por sistema, ffmpeg
- **analisis**: Analisis del material: relojes por camara (UTC, fecha mala), contenido, calidad/color/audio en 1 lectura, tramos
- **resolve**: Conexion con DaVinci: abrir, cargar/importar proyecto, cuadros que bloquean, reenlazar medios
- **armado**: Armado de cada version: duplicar plantilla, planificar planos, zonas por marcador, cortes al ritmo
- **media-pool**: Media pool en carpetas numeradas 01 PLANTILLAS .. 06 EFECTOS, por momento y fuente, con colores
- **color**: Color por plano (exposicion, negros, blancos, saturacion medida), grupos PRE/POST y reduccion de ruido
- **textos**: Titulos Fusion (script + subtitulo + velo), capitulos, frases y gracias (PNG transparente en V3)
- **sonido**: SFX por momento (campanas, petalos, entrada, chispa, vitores), whoosh, ritmo y mezcla medida en LUFS
- **entrega**: Render de la cola, audio a -14 LUFS con limitador, medicion de saturacion/luz del video final
- **perfiles**: Tipos de evento (xv, boda, bautizo, graduacion, cumpleanos): titulos, capitulos, frases, gracias
- **instalador**: Instalador .exe como el de CineCaptions: banner animado (astrolabio), PASOS, % y barra; PyInstaller + C#
- **mac**: Mac: .dmg como el de CineCaptions (fondo de 2 pasos) con .pkg; se compila en una Mac o GitHub Actions
- **registro**: Registro en archivo (registro.log), ganchos de errores, faulthandler; donde mirar cuando algo falla
- **ia-resolve**: IA de Resolve Studio: escuchar votos/brindis (transcripcion + clasificacion), voz sobre la musica, camara lenta Speed Warp, estabilizar, IntelliSearch al final
<!-- MAPA:FIN -->

## Reglas que no se rompen
- **La persona:** español, respuestas breves, PowerShell 7. Antes de tareas grandes, un plan corto.
- **Resolve:**
  - Preguntar antes de cambiar de proyecto.
  - Nunca `pm.SaveProject()` sobre "Untitled Project": saca «Crear proyecto» y la API se cuelga.
  - Nunca `InsertFusionTitleIntoTimeline` ni la herramienta Shadow de Fusion.
  - Los cambios de clips solo funcionan en la timeline activa y ya asentada.
- **Plantillas:** `TRAILER XV - *` no se tocan; cada evento es un duplicado.
- **Montaje:**
  - Solo 8 fotos, en la intro; sin el audio original.
  - Colores: MAQUILLAJE morado, IGLESIA verde, FIESTA rosa.
  - Entrega en MOV H.265 a -14 LUFS.
- **Ventana:** en su hilo no se llama a la API de Resolve ni se usa `subprocess`/`sleep`: eso va en hilos (`Trabajo`, `EstadoDV`, `qt_kit.correr_en_hilo`).
- **Escena de Inicio:** `escena_go`, `estilos_inicio`, `orbe_mecanica`, `ritmo_ui` y `boton_go` vienen de CineCaptions; ahí solo se cambian textos.
- **Rutas:** siempre con `rutas.py`, porque en el .exe los recursos están en `sys._MEIPASS`.

## Al cambiar algo
- **Tema nuevo o cambiado:** agregar su entrada en `PROGRAMA/docs/mapa.json` y correr `python PROGRAMA/mapa_codigo.py generar`, que avisa de los símbolos que ya no existen.
- **Probar:**
  - Usar arneses en el scratchpad: motor simulado y `grab()` a PNG de la ventana real.
  - Contra Resolve sin tocar nada: `python PROGRAMA/trailer_xv.py --seco`.
- **Compilar:** solo si la persona lo pide.
  1. Subir `PROGRAMA/version.txt`.
  2. Correr `pwsh -File PROGRAMA/compilar/construir.ps1`.
  3. Instalar con `/silencioso`.
- **Detalle e historia:** `PROGRAMA/SKILL.md`, leído por secciones con Grep.
