# Tráiler automático — leer SOLO esto; lo demás se consulta por demanda

- **Qué es:** app PySide6 (Python 3.14, versión en `PROGRAMA/config/version.txt`) que arma tráilers de eventos (XV, boda, bautizo, graduación, cumpleaños) en DaVinci Resolve Studio 21 y los renderiza. Funciona en Windows y Mac.
- **En Resolve:** base `EVENTOS`, proyecto `EVENTOS CINEMA`, plantillas `TRAILER XV - 1min/3min/15min/30min`.
- **Carpetas:** en la raíz del proyecto solo hay DOS a la vista, `PROGRAMA` y `3 INSTALADORES` (la persona, 16-nov). No poner nada más ahí.
  - `1 MATERIAL`: FOTOS · VIDEOS · DRON · ANTERIORES, siempre POR DENTRO: `DATOS/trabajo` (instalado) o `PROGRAMA/datos/trabajo` (desde el código). Una carpeta soltada NO se copia aquí: se usa donde está.
  - `EVENTO TERMINADO - <evento>`: en el Escritorio (instalado y desde el código): `VIDEO TERMINADO` (`VIDEO FINAL 1 MIN`, `VIDEO FINAL VERTICAL 1 MIN`…) y `PLANTILLAS DE LOS VIDEOS` (un proyecto `.drp` por video, mismo nombre: solo esa línea, con proxies y caché). Los de antes de la 1.5.7 (`2 VIDEOS TERMINADOS`, `3 PLANTILLAS EDITABLES`) ya se pasaron ahí.
  - `3 INSTALADORES`: Windows (.exe) · Mac (.dmg).
  - Proxies (Ajustes › Video › «Proxies para editar», encendido de fábrica): TODOS, de cualquier evento o plantilla, en `Videos/PROXIES TRAILER AUTOMATICO` (`rutas.carpeta_proxies`; Mac: Películas). Nombre = nombre del video + tamaño (no la carpeta). Llevan audio PCM y el código de tiempo del original («;» drop frame): si no, DaVinci los rechaza en silencio (`editable.arreglar_proxy`).
  - `PROGRAMA`: solo carpetas. Código en `interfaz/` (ventana, icono, Inicio; `interfaz/qml/` = piezas nuevas en QML / Qt Quick, por partes, con `barra_qml.py`), `nucleo/` (motor, rutas, registro, tareas), `analisis/` (material, escenas IA, ritmo), `armado/` (plantillas, SFX, mezcla, IntelliSearch), `entrega/` (render, master) y `herramientas/` (mapa_codigo, empaquetar). Además `config/` (versión, perfiles, requisitos, LEEME), `datos/` (cachés, respaldos, `registro/`), `recursos/`, `recursos_protegidos/`, `dctl/`, `compilar/` (`windows/`, `mac/`, `icono/`) y `docs/` (SKILL, mapa, capturas).
  - Ocultos en la raíz: `.git*`, `.github` y este `CLAUDE.md` (atributo oculto).
  - Iconos de carpeta como CINESLIDE (ocultos `.cf/icono.ico` + `desktop.ini` en cada una): `python PROGRAMA/herramientas/iconos_carpetas.py`; al crear una carpeta nueva, volver a correrlo.
  - `LEEME.txt` para la persona: `PROGRAMA/config/LEEME.txt`. Para abrir sin instalar: `PROGRAMA/herramientas/ARMAR TRAILERS.bat` / `.command` (también sirven junto a `PROGRAMA` en el paquete de Mac).

## Encontrar algo sin leer archivos (en este orden)
1. `python PROGRAMA/herramientas/mapa_codigo.py mapa <palabras>` da el tema. `mapa id=<tema>` da sus archivos, sus símbolos con la línea y sus notas.
2. `donde <nombre>` · `simbolo <nombre>` (solo el código de esa función) · `modulo <archivo>` · `llamadas <nombre>`.
3. Si falta algo: Grep + Read con `offset`/`limit` (~60 líneas).
4. NUNCA leer enteros: `build_trailers.py`, `trailer_xv.py`, `escena_go.py`, `estilos_inicio.py`, `orbe_mecanica.py`, `SKILL.md`, `PROGRAMA/datos/**`, `PROGRAMA/recursos/**`.

## Mapa de temas (`mapa id=<tema>`)
<!-- MAPA:INICIO (lo escribe PROGRAMA/herramientas/mapa_codigo.py generar) -->
- **que-entra**: Material > «Qué entra al video» (reemplaza a la Linea del dia): el plan de cada version plano por plano, lo que queda fuera con su motivo, «No la uses» / «Úsala de todos modos», y el tiempo estimado que ya no cuenta lo analizado
- **boton-play**: El boton GO hace todo: analizar, armar en DaVinci, renderizar, masterizar, abrir carpeta
- **inicio-escena**: Escena GO de CineCaptions (esfera de particulas, cometas, explosion): OCULTA desde 1.6.0; el Inicio es el astrolabio vivo de la maqueta (tema animaciones)
- **ventana**: Ventana sin marco: portada al instante, pestanas Inicio/Tráilers/Plantillas/Ajustes (Material y Textos ocultas desde el 19-nov) (voz original, verticales, ruido), chequeo de arranque, instancia unica
- **diseno**: Diseño 1.6.0 (maquetas de Higgsfield, docs/capturas/propuesta_*): pastilla de estado, panel de Inicio, Material con miniaturas y Linea del dia por momento, Textos con vista previa, Ajustes en tarjetas, Trabajando con pasos, avance por version y Cancelar
- **animaciones**: Animaciones 1.6.0 hechas en Higgsfield (Kling 3.0): astrolabio vivo (reposo, despertar, trabajo, hecho, dormir), cielo que fluye, bodegon de Ajustes; fundido entre paginas, luz en el titulo, pasos, versiones y Linea del dia vivos, vista previa de Textos con zoom lento, brillo al pasar el raton
- **arranque**: Abrir sin tiempo de carga y con fluidez: sin portada (la persona no la quiere), fuentes (una familia, sin simbolos de reserva, hilo por ctypes), numpy/Pillow al primer uso, linea del dia y cielo guardados, tiempos con TRAILER_TIEMPOS
- **material**: Material: solo fotos JPG, al menos 1 video (las fotos de la intro salen de capturas del video si faltan), arrastrar/agregar y el panel 'Como quedo organizado' (linea del dia)
- **soltar**: Suelta la carpeta y listo: se usa DONDE ESTA (sin copiar), se une al mismo evento, sus archivos se renombran en su sitio con tipo y momento (nunca se borra nada); nuevo evento solo si el anterior ya termino
- **rutas**: Todas las rutas: codigo vs instalado (.exe), DATOS, trabajo POR DENTRO, EVENTO TERMINADO en el Escritorio, nombres VIDEO FINAL, pasar_adentro, Resolve y LUT por sistema, ffmpeg
- **analisis**: Analisis del material: relojes por camara, contenido, calidad/color/audio, la 'vista' de cada medio segundo y lo que VE la IA local (Qwen3-VL en Ollama): momento, escena, etiquetas y si la toma sirve
- **oido**: Oido (earshot, opcional): escucha cada toma (aplausos, vitores, risas, llanto, habla, musica, campanas) para la emocion del armado y revisa clics, huecos y saturacion del audio final (marcadores amarillos)
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
- **limpieza**: Borrar cache en Ajustes: cache de render de DaVinci (18 GB en la boda), proxies, respaldos viejos, actualizaciones instaladas y temporales; nunca material, videos, plantillas ni capturas
- **pruebas**: Como probar sin gastar tokens: datos aislados (TRAILER_DATOS), armado sin DaVinci (storyboard / exec de build_trailers), ventana real con grab(), oido y audio final, compilar Windows + Mac Apple Silicon
- **tiempos**: Cuanto tarda cada etapa y donde se va el tiempo (medido); como ver el avance sin leer el registro (avance.py); que ya se acelero y que no sirve intentar
- **musica**: Musica ORIGINAL por estilo (Cine latino, Juvenil, Clasico, Emotivo) en vez de las canciones de la plantilla: papeles, pistas encadenadas para 1-30 min, intro con la rampa de fotos, selector en Ajustes, y escuchar.py para oir sin oidos (earshot)
- **efectos**: Tipos de intro (ritmo de las 8 fotos + su SFX de rampa), overlays de luz propios (destello en cambios de momento, brillos en titulos; XV/boda, H/V) y el titulo DETRAS de la persona con recorte local (RVM, sin Mascara Magica)
- **analisis-seguro**: Que el analisis no se pierda ni se repita y SE VEA: metadatos visibles dentro de cada video (titulo y comentario en Windows y DaVinci), punto de guardado cada minuto, incrustado oculto por archivo (flujo NTFS :trailer), ficha en la carpeta del evento y archivo buscable (buscar.py)
- **permisos**: Popup de permisos al abrir (solo si falta alguno): controlar DaVinci (Scripting externo), carpetas protegidas de Defender, escribir en Escritorio/Videos, leer todos los discos, rutas largas; en Mac acceso total al disco, Accesibilidad, Automatizacion y Grabacion de pantalla
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
- **Sala de espera:** soltar una carpeta NO arma: queda flotando en el Inicio (`piezas.Sala`) y espera; se pueden soltar más y solo empieza cuando la persona pulsa «Empezar» (la persona, 17-nov).
- **Fluidez:** las piezas animan a 60 por segundo (`piezas.CUADRO_MS`) y por tiempo, nunca por pasos; repintar la ventana entera cuesta 8-12 ms, así que ninguna animación la repinta toda salvo el cielo (20 por segundo, con fundido). Antes de dar por buena una animación nueva, medir (`mapa id=animaciones`).
- **Popups:** nunca `QMessageBox` ni cuadros del sistema: avisos y preguntas con `self._popup(...)` / `self._si(...)` (`piezas.Popup`, dentro de la ventana, animado). Nada estático: toda pieza nueva lleva su animación (la persona, 17-nov).
- **Soltar:** la carpeta soltada se usa DONDE ESTÁ (no se copia; `estado.carpetas`, `rutas.fuentes()`). Al armar, sus archivos se renombran en su sitio: `VIDEO HORIZONTAL 001 (CEREMONIA).MP4`, `VIDEO VERTICAL 004 (FIESTA).MOV`, `DRON 001 (FIESTA).MP4`, `FOTO 003 (MAQUILLAJE).JPG` (nombres viejos en `datos/analisis/nombres.json`). NUNCA se borra ningún archivo. Otra carpeta soltada se une al mismo evento sin preguntar; solo si el evento ya está terminado (con sus videos) empieza uno nuevo.
- **Material:** solo fotos JPG (RAW, DNG, PNG, HEIC no cuentan ni se tocan). Sin fotos JPG para la intro, se sacan capturas del video (`motor.capturas_intro`, por dentro en `CAPTURAS`). Si hay videos verticales, se arma solo también el VERTICAL 1 min.
- **Montaje:**
  - 8 fotos en la intro y UNA al final (la mejor de la persona festejada, con la tarjeta final abajo).
  - **Sin repetir** (la persona, 20-nov): cada toma como mucho 2 veces por versión y la misma escena (misma toma o mismo encuadre, imagen casi igual) tampoco más de 2 (`MAX_USOS_TOMA`, `MAX_USOS_ESCENA`). El resumen inicial de 15/30 no gasta esos usos (cada toma una vez ahí). Si no alcanza el material: dron, otra parte de una toma con usos libres, planos más largos (hasta 2× el corte, `_alargar`, como documental) y luego fotos del momento (todas las versiones); repetir es lo último y se avisa. Cada capítulo dura entre la mitad y 1,5× lo de la plantilla según su material (`repartir_zonas`).
  - **Misma escena continua** (tomas sin pausa de más de 3 min: la bendición en casa, el baile): como mucho 40 % de un capítulo de 15/30. **Momentos**: lo que la IA ve como preparativos claros va a MAQUILLAJE y lo posterior al fin de la ceremonia que la IA no ve como iglesia va a FIESTA, aunque el orden del día diga otra cosa. **Celular de cabeza** (rotation -180): DaVinci no lo gira (el de 90 sí): `RotationAngle` 180 en la línea, sin estabilizar, y su proxy sin enderezar.
  - **Quien habla se ve dos veces** (al empezar, algo acercado; hacia el final, más cerca), enfocado en SU cara (`encuadre.quien_habla`: la boca que se mueve en 2 s, YuNet + cambio de la boca contra la frente; si no está claro, la IA de vista; si no, plano abierto. La cara más grande falló en 4 de 4; comparar con el volumen del audio, peor. En la iglesia, `el_sacerdote`: la IA de vista lo reconoce por la ropa). Acercamiento para plano medio, hasta 2× en 4K (1,5× si la cara es chica), como mucho 2 veces por toma y versión (`HABLA_MAX_TOMA`); la voz de una misma escena continua, como mucho 25 % del capítulo (`VOZ_ESCENA_PARTE`: eran 13 bendiciones seguidas). **Aéreas**: sin despegue (10 s) ni aterrizaje, mejor con paneo parejo, y centradas en lo importante (Qwen3-VL con cajas `bbox_2d` 0-1000: con «x, y 0-100» siempre respondía el centro), también en las plantillas 9:16, donde solo se ve el tercio central (`armar_ref._centrar_aereo`). Antes de renderizar se descarga la IA de la tarjeta (`vision_ia.soltar_gpu`): con ella cargada el Speed Warp se arrastraba y el de 30 min se paraba. **Captions**: 7,5 s en pantalla, 12 s mínimo entre uno y otro, escritura de ~1,5 s, fundidos de 1 s y nunca encima de la voz. **Plantillas de referencia**: cada una con tomas distintas a las anteriores del mismo armado.
  - **Dron en momentos clave**: en 15/30 cada capítulo abre desde el aire (mejor aérea de ESE momento, `dron_clave`) y el último plano antes de la imagen final es una aérea. **Cámara lenta**: los más emotivos (24 en 15, 40 en 30) y en los largos «lento natural» de lo grabado a 48 c/s o más (`LENTO_NATURAL`).
  - Personas: las reconoce la IA propia durante el análisis (`analisis/caras.py`, YuNet + SFace; 448 archivos en 222 s) y, solo si faltan sus modelos, DaVinci (IntelliSearch, ~20 min); quedan en `it["caras"]`, `it["prota"]`; la festejada es la cara que sale en más archivos y sus tomas y fotos van primero.
  - Tomas malas fuera: desenfocadas, quemadas, torcidas o al piso (medidas `vista` del analizador, en absoluto; nitidez también contra la mejor cámara del evento).
  - **Si sale gente, se le ve la cara**: la IA local revisa cada toma cada 3 s (`vision_ia.instantes`; lo que las medidas ya dejan fuera no se le pregunta, `receta.tramos_fuera`); techo, piso, de cabeza, tapada, sin cabeza, de espaldas o sin ninguna cara → fuera ese tramo (o la toma entera si es la mayor parte). Lo muy movido no entra (el estabilizador lo deforma).
  - Antes de dar por bueno un video: hoja de contacto (2 cuadros/s) y mirarla.
  - Estabilizar con el estabilizador propio (`armado/estabilizar.py`, Transform de Fusion con keyframes, zoom mínimo), no con `Stabilize()` de Resolve; los comps se ponen ANTES del primer render del clip (DaVinci reusa lo renderizado). La Magic Mask no se puede automatizar (puntos a mano) y el Depth Map de Fusion no se renderiza en un comp de clip (`profundidad.py` apagado).
  - Voz original solo de quien habla de corrido (pastor, brindis, discursos), nunca ruidos ni voces sueltas: siempre en 30 min, activada en 15, a elegir en 1 y 3 (Ajustes › Voz original). En 15/30 la IA local etiqueta cada frase (`armado/guion_voz.py`: tipo —voto, bendición de la familia, oración, agradecimiento, brindis, aviso…— y cuántas palabras raras trae; la nota la pone el programa: avisos y frases sin sentido fuera. Con «nota 0-10» la IA daba todo 0 o todo 8) y arma la historia: APERTURA (sobre la aérea de los preparativos), HISTORIA (donde el video cuenta ese momento) y CIERRE (sobre la imagen final). Como película de bodas: corte J (la voz entra 1,2 s antes de ver a quien habla), en sincronía, a los 6,5 s otra cámara del mismo instante o una foto de ese momento, corte L, cortes en las pausas; después, los aplausos reales y un destello; la música vuelve a subir en 30 cuadros.
  - Oído (earshot, opcional, `oido.py`): aplausos, vítores y risas solo SUBEN la emoción de un tramo; el audio final se revisa (clics sueltos, huecos, saturación) y se marca en amarillo. Nunca descarta tomas ni frena nada; sin earshot todo sigue igual.
  - Color: la saturación nunca pasa de la de cámara (ni el CDL ni el look la suben).
  - Colores: MAQUILLAJE morado, IGLESIA verde, FIESTA rosa.
  - Entrega en MOV H.265 a -14 LUFS.
  - Formatos: el horizontal acepta videos horizontales y verticales; el vertical (9:16, mismas duraciones, líneas «… - VERTICAL 1min») solo los grabados en vertical.
- **Ventana:** en su hilo no se llama a la API de Resolve ni se usa `subprocess`/`sleep`: eso va en hilos (`Trabajo`, `EstadoDV`, `qt_kit.correr_en_hilo`).
- **Arranque:** el estilo lleva UNA familia de fuente (nunca una lista) y al abrir no se pinta ningún símbolo que Segoe UI no traiga (✓ ☰ ✕ ▶ ⤓ ⚠ ✎, emojis): cualquiera de las dos cosas suma 0,4 s de carga. Nada pesado antes de la ventana (`numpy`, Pillow, lecturas grandes).
- **Inicio y animaciones (1.6.0):** el Inicio es el astrolabio de la maqueta, vivo (`piezas.Astrolabio` + videos de Higgsfield en `recursos/animaciones`, `mapa id=animaciones`); la escena de CineCaptions (`escena_go` y compañía) queda oculta. Nada se queda quieto, pero cada animación pinta solo mientras se ve y los videos arrancan después de abrir la ventana.
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
- **Compilar:** solo si la persona lo pide, y SOLO Windows y Mac Apple Silicon (nada de Intel; la persona, 17-nov).
  1. Subir `PROGRAMA/config/version.txt`.
  2. Correr `pwsh -File PROGRAMA/compilar/windows/construir.ps1` (deja el .exe en `3 INSTALADORES/Windows`).
  3. Instalar con `/silencioso`.
  4. Mac: commit + push de la rama y `pwsh -File PROGRAMA/compilar/mac/construir_desde_windows.ps1` (GitHub Actions; deja el .dmg en `3 INSTALADORES/Mac`).
  - El repositorio es PÚBLICO: música, SFX y fuentes con licencia nunca van tal cual. Las canciones con derechos en los estilos llevan « - » y el título en el nombre (`02 ROMANTICA C - A THOUSAND YEARS (VIOLIN).mp3`): fuera de git y de la actualización pública; para Mac, `python PROGRAMA/compilar/protegidos.py cifrar` y subir `recursos_protegidos`.
- **Ahorrar tokens:** no releer lo ya leído; el avance de un armado con `python PROGRAMA/herramientas/avance.py` (3 líneas; `tiempos` da los minutos por etapa), nunca leyendo el registro; mientras corre no se consulta: el sistema avisa al terminar; tiempos medidos y qué ya se intentó en `mapa id=tiempos`; recetas de prueba en `mapa id=pruebas`; salidas largas con `Select-Object -Last N`.
- **Icono:** `PROGRAMA/interfaz/icono_app.py` (lo usan la ventana, el .ico y el .icns).
- **Detalle e historia:** `PROGRAMA/docs/SKILL.md`, leído por secciones con Grep.
