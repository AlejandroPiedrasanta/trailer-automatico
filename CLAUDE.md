# Tráiler automático — leer SOLO esto; lo demás se consulta por demanda

- **Qué es:** app PySide6 (Python 3.14, versión en `PROGRAMA/config/version.txt`) que arma tráilers de eventos (XV, boda, bautizo, graduación, cumpleaños) en DaVinci Resolve Studio 21 y los renderiza. Funciona en Windows y Mac.
- **En Resolve:** base `EVENTOS`, proyecto `EVENTOS CINEMA`, plantillas `TRAILER XV - 1min/3min/15min/30min`.
- **Carpetas:** en la raíz del proyecto solo hay DOS a la vista, `PROGRAMA` y `3 INSTALADORES` (la persona, 16-nov). No poner nada más ahí.
  - `1 MATERIAL`: FOTOS · VIDEOS · DRON · ANTERIORES, siempre POR DENTRO: `DATOS/trabajo` (instalado) o `PROGRAMA/datos/trabajo` (desde el código). Una carpeta soltada NO se copia aquí: se usa donde está.
  - `EVENTO TERMINADO - <evento>`: en el Escritorio (instalado y desde el código): `VIDEO TERMINADO` (`VIDEO FINAL 1 MIN`, `VIDEO FINAL VERTICAL 1 MIN`…) y `PLANTILLAS DE LOS VIDEOS` (un proyecto `.drp` por video, mismo nombre: solo esa línea, con proxies y caché). Los de antes de la 1.5.7 (`2 VIDEOS TERMINADOS`, `3 PLANTILLAS EDITABLES`) ya se pasaron ahí.
  - `3 INSTALADORES`: Windows (.exe) · Mac (.dmg).
  - `PROGRAMA`: solo carpetas. Código en `interfaz/` (ventana, icono, Inicio), `nucleo/` (motor, rutas, registro, tareas), `analisis/` (material, escenas IA, ritmo), `armado/` (plantillas, SFX, mezcla, IntelliSearch), `entrega/` (render, master) y `herramientas/` (mapa_codigo, empaquetar). Además `config/` (versión, perfiles, requisitos, LEEME), `datos/` (cachés, respaldos, `registro/`), `recursos/`, `recursos_protegidos/`, `dctl/`, `compilar/` (`windows/`, `mac/`, `icono/`) y `docs/` (SKILL, mapa, capturas).
  - Ocultos en la raíz: `.git*`, `.github` y este `CLAUDE.md` (atributo oculto).
  - `LEEME.txt` para la persona: `PROGRAMA/config/LEEME.txt`. Para abrir sin instalar: `PROGRAMA/herramientas/ARMAR TRAILERS.bat` / `.command` (también sirven junto a `PROGRAMA` en el paquete de Mac).

## Encontrar algo sin leer archivos (en este orden)
1. `python PROGRAMA/herramientas/mapa_codigo.py mapa <palabras>` da el tema. `mapa id=<tema>` da sus archivos, sus símbolos con la línea y sus notas.
2. `donde <nombre>` · `simbolo <nombre>` (solo el código de esa función) · `modulo <archivo>` · `llamadas <nombre>`.
3. Si falta algo: Grep + Read con `offset`/`limit` (~60 líneas).
4. NUNCA leer enteros: `build_trailers.py`, `trailer_xv.py`, `escena_go.py`, `estilos_inicio.py`, `orbe_mecanica.py`, `SKILL.md`, `PROGRAMA/datos/**`, `PROGRAMA/recursos/**`.

## Mapa de temas (`mapa id=<tema>`)
<!-- MAPA:INICIO (lo escribe PROGRAMA/herramientas/mapa_codigo.py generar) -->
- **boton-play**: El boton GO hace todo: analizar, armar en DaVinci, renderizar, masterizar, abrir carpeta
- **inicio-escena**: Pantalla de Inicio = la de CineCaptions: esfera de particulas, astrolabio GO, cometas, explosion
- **ventana**: Ventana sin marco: portada al instante, pestanas Material/Textos/Ajustes (voz original, verticales, ruido), chequeo de arranque, instancia unica
- **arranque**: Abrir sin tiempo de carga y con fluidez: portada nativa, fuentes (una familia, sin simbolos de reserva, hilo por ctypes), numpy/Pillow al primer uso, linea del dia y cielo guardados, tiempos con TRAILER_TIEMPOS
- **material**: Material: solo fotos JPG, al menos 1 video (las fotos de la intro salen de capturas del video si faltan), arrastrar/agregar y el panel 'Como quedo organizado' (linea del dia)
- **soltar**: Suelta la carpeta y listo: se usa DONDE ESTA (sin copiar), se une al mismo evento, sus archivos se renombran en su sitio con tipo y momento (nunca se borra nada); nuevo evento solo si el anterior ya termino
- **rutas**: Todas las rutas: codigo vs instalado (.exe), DATOS, trabajo POR DENTRO, EVENTO TERMINADO en el Escritorio, nombres VIDEO FINAL, pasar_adentro, Resolve y LUT por sistema, ffmpeg
- **analisis**: Analisis del material: relojes por camara, contenido, calidad/color/audio, la 'vista' de cada medio segundo y lo que VE la IA local (Qwen3-VL en Ollama): momento, escena, etiquetas y si la toma sirve
- **resolve**: Conexion con DaVinci: abrir, cargar/importar proyecto, cuadros que bloquean, reenlazar medios
- **armado**: Armado de cada version: duplicar plantilla, planificar planos (tomas malas fuera, relleno con dron/fotos, final con foto), zonas por marcador, cortes al ritmo, camara lenta
- **media-pool**: Media pool en carpetas numeradas 01 PLANTILLAS .. 06 EFECTOS, por momento y fuente, con colores
- **color**: Color por plano (exposicion, negros, blancos; la saturacion nunca sube de la de camara), grupos PRE/POST, looks _REC709 y reduccion de ruido
- **textos**: Titulos Fusion (script + subtitulo + velo), capitulos, frases, gracias y tarjeta final abajo (PNG transparente en V3); velo bajo los titulos de la plantilla
- **sonido**: SFX por momento, SFX propios en los momentos clave, whoosh, cambio de cancion sin huecos, musica bajo la voz en rampa y mezcla medida en LUFS
- **formatos**: Dos formatos en Inicio con las mismas duraciones: HORIZONTAL (16:9, acepta videos horizontales y verticales) y VERTICAL (9:16 para celular, solo videos grabados en vertical)
- **entrega**: Render de la cola (solo las versiones pedidas), audio a -14 LUFS con limitador, medicion del video final y revisar_video.py
- **editable**: Cada evento terminado queda editable en DaVinci: linea abierta en Edicion, un proyecto .drp por video (solo esa linea, proxies y cache) en EVENTO TERMINADO/PLANTILLAS DE LOS VIDEOS, «Editar en DaVinci» y «Renderizar lo editado» (sin volver a armar)
- **perfiles**: Tipos de evento (xv, boda, bautizo, graduacion, cumpleanos): titulos, capitulos, frases, gracias
- **instalador**: Instalador .exe de 1 MB + .dat (abre al instante) como el de CineCaptions: banner animado, PASOS, % y barra; PyInstaller + C#; icono
- **mac**: Mac: .dmg de «Doble clic para instalar» como CineSlide: ventana nativa (Swift) igual a la de Windows que copia a Aplicaciones sin contrasena, Dock, primer arranque, abre y expulsa; se compila desde Windows en GitHub Actions
- **registro**: Registro en archivo (registro.log), ganchos de errores, faulthandler; donde mirar cuando algo falla
- **ia-resolve**: IA de Resolve Studio: personas (IntelliSearch con caras -> quien es la festejada), quien habla y pasajes de voz (transcripcion), Speed Warp, estabilizar, Smart Reframe
- **actualizaciones**: Actualizaciones como CineCaptions: version.json firmado en trailer-automatico-releases, descarga con huella, al cerrar o en segundo plano (tarea Windows / servicio Mac)
<!-- MAPA:FIN -->

## Reglas que no se rompen
- **La persona:** español, respuestas breves, PowerShell 7. Antes de tareas grandes, un plan corto.
- **Resolve:**
  - Preguntar antes de cambiar de proyecto.
  - Nunca `pm.SaveProject()` sobre "Untitled Project": saca «Crear proyecto» y la API se cuelga.
  - Nunca `InsertFusionTitleIntoTimeline` ni la herramienta Shadow de Fusion.
  - Los cambios de clips solo funcionan en la timeline activa y ya asentada.
- **Plantillas:** `TRAILER XV - *` no se tocan; cada evento es un duplicado.
- **Editable:** al terminar, la línea del evento queda abierta en Edición y un `.drp` por video (solo esa línea) en `EVENTO TERMINADO - <evento>/PLANTILLAS DE LOS VIDEOS`. ▶ rearma y reemplaza las líneas: sobre un evento ya armado se pregunta antes; lo retocado a mano se saca con «Renderizar lo editado».
- **Soltar:** la carpeta soltada se usa DONDE ESTÁ (no se copia; `estado.carpetas`, `rutas.fuentes()`). Al armar, sus archivos se renombran en su sitio: `VIDEO HORIZONTAL 001 (CEREMONIA).MP4`, `VIDEO VERTICAL 004 (FIESTA).MOV`, `DRON 001 (FIESTA).MP4`, `FOTO 003 (MAQUILLAJE).JPG` (nombres viejos en `datos/analisis/nombres.json`). NUNCA se borra ningún archivo. Otra carpeta soltada se une al mismo evento sin preguntar; solo si el evento ya está terminado (con sus videos) empieza uno nuevo.
- **Material:** solo fotos JPG (RAW, DNG, PNG, HEIC no cuentan ni se tocan). Sin fotos JPG para la intro, se sacan capturas del video (`motor.capturas_intro`, por dentro en `CAPTURAS`). Si hay videos verticales, se arma solo también el VERTICAL 1 min.
- **Montaje:**
  - 8 fotos en la intro y UNA al final (la mejor de la persona festejada, con la tarjeta final abajo). Fotos dentro del video solo como relleno en el de 30 min (cuando no alcanzan las tomas buenas), antes que repetir o meter una toma fea.
  - Personas: las reconoce DaVinci (IntelliSearch con caras → `it["caras"]`, `it["prota"]`); la festejada es la cara que sale en más archivos y sus tomas y fotos van primero.
  - Tomas malas fuera: desenfocadas, quemadas, torcidas o al piso (medidas `vista` del analizador, en absoluto; nitidez también contra la mejor cámara del evento).
  - **Si sale gente, se le ve la cara**: la IA local revisa cada toma cada 3 s (`vision_ia.instantes`); techo, piso, de cabeza, tapada, sin cabeza, de espaldas o sin ninguna cara → fuera ese tramo (o la toma entera si es la mayor parte). Lo muy movido no entra (el estabilizador lo deforma).
  - Antes de dar por bueno un video: hoja de contacto (2 cuadros/s) y mirarla.
  - Estabilizar con el estabilizador propio (`armado/estabilizar.py`, Transform de Fusion con keyframes, zoom mínimo), no con `Stabilize()` de Resolve; los comps se ponen ANTES del primer render del clip (DaVinci reusa lo renderizado). La Magic Mask no se puede automatizar (puntos a mano) y el Depth Map de Fusion no se renderiza en un comp de clip (`profundidad.py` apagado).
  - Voz original solo de quien habla de corrido (pastor, brindis, discursos), nunca ruidos ni voces sueltas: siempre en 30 min, activada en 15, a elegir en 1 y 3 (Ajustes › Voz original).
  - Color: la saturación nunca pasa de la de cámara (ni el CDL ni el look la suben).
  - Colores: MAQUILLAJE morado, IGLESIA verde, FIESTA rosa.
  - Entrega en MOV H.265 a -14 LUFS.
  - Formatos: el horizontal acepta videos horizontales y verticales; el vertical (9:16, mismas duraciones, líneas «… - VERTICAL 1min») solo los grabados en vertical.
- **Ventana:** en su hilo no se llama a la API de Resolve ni se usa `subprocess`/`sleep`: eso va en hilos (`Trabajo`, `EstadoDV`, `qt_kit.correr_en_hilo`).
- **Arranque:** el estilo lleva UNA familia de fuente (nunca una lista) y al abrir no se pinta ningún símbolo que Segoe UI no traiga (✓ ☰ ✕ ▶ ⤓ ⚠ ✎, emojis): cualquiera de las dos cosas suma 0,4 s de carga. Nada pesado antes de la ventana (`numpy`, Pillow, lecturas grandes).
- **Escena de Inicio:** `escena_go`, `estilos_inicio`, `orbe_mecanica`, `ritmo_ui` y `boton_go` vienen de CineCaptions; ahí solo se cambian textos.
- **Rutas:** siempre con `rutas.py`, porque en el .exe todo queda junto en `sys._MEIPASS`.
  - `import rutas` pone las carpetas de código en `sys.path`; un script suelto agrega antes `PROGRAMA/nucleo`.
  - Un .py por ruta: `rutas.codigo("x.py")`. Versión, perfiles y LEEME: `rutas.CONFIG_PROG`.
- **Carpetas:** nada suelto en `PROGRAMA`; cada archivo nuevo va en su carpeta.

## Al cambiar algo
- **Tema nuevo o cambiado:** agregar su entrada en `PROGRAMA/docs/mapa.json` y correr `python PROGRAMA/herramientas/mapa_codigo.py generar`, que avisa de los símbolos que ya no existen.
- **Probar:**
  - Usar arneses en el scratchpad: motor simulado y `grab()` a PNG de la ventana real.
  - Contra Resolve sin tocar nada: `python PROGRAMA/interfaz/trailer_xv.py --seco`.
  - El plan de una versión sin DaVinci, plano por plano: `python PROGRAMA/herramientas/storyboard.py 1min sb.jpg`.
- **Compilar:** solo si la persona lo pide.
  1. Subir `PROGRAMA/config/version.txt`.
  2. Correr `pwsh -File PROGRAMA/compilar/windows/construir.ps1` (deja el .exe en `3 INSTALADORES/Windows`).
  3. Instalar con `/silencioso`.
- **Icono:** `PROGRAMA/interfaz/icono_app.py` (lo usan la ventana, el .ico y el .icns).
- **Detalle e historia:** `PROGRAMA/docs/SKILL.md`, leído por secciones con Grep.
