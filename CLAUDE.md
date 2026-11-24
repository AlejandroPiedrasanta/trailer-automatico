# Tráiler automático — leer SOLO esto; lo demás, por demanda

App PySide6 (Python 3.14; versión en `PROGRAMA/config/version.txt`) que arma tráilers de eventos (XV, boda, bautizo, graduación, cumpleaños) en DaVinci Resolve Studio 21 y los renderiza; Windows y Mac. En Resolve: base `EVENTOS`, proyecto `EVENTOS CINEMA`, plantillas `TRAILER XV - 1min/3min/15min/30min`.

## Carpetas
- Raíz: a la vista solo `PROGRAMA` y `3 INSTALADORES` (Windows .exe · Mac .dmg); ocultos `.git*`, `.github`, este `CLAUDE.md`. Nada más ahí.
- `PROGRAMA`: solo carpetas. Código: `interfaz/` (ventana; QML en `interfaz/qml/` con `barra_qml.py`), `nucleo/` (motor, rutas, registro, tareas), `analisis/`, `armado/`, `entrega/`, `herramientas/`. Además `config/`, `datos/`, `recursos/`, `recursos_protegidos/`, `dctl/`, `compilar/`, `docs/`. Cada archivo nuevo en su carpeta; al crear carpeta, `python PROGRAMA/herramientas/iconos_carpetas.py`.
- `1 MATERIAL` (FOTOS · VIDEOS · DRON · ANTERIORES) va por dentro (`DATOS/trabajo` o `PROGRAMA/datos/trabajo`); lo soltado no se copia.
- Salida en el Escritorio: `EVENTO TERMINADO - <evento>/VIDEO TERMINADO` (`VIDEO FINAL 1 MIN`, `VIDEO FINAL VERTICAL 1 MIN`…) y `/PLANTILLAS DE LOS VIDEOS` (un .drp por video).
- Proxies: todos en `Videos/PROXIES TRAILER AUTOMATICO` (`rutas.carpeta_proxies`), nombre = video + tamaño, con audio PCM y el timecode del original o DaVinci los rechaza (`editable.arreglar_proxy`).
- LEEME: `PROGRAMA/config/LEEME.txt`. Sin instalar: `PROGRAMA/herramientas/ARMAR TRAILERS.bat` / `.command`.

## Encontrar algo sin leer archivos
1. `python PROGRAMA/herramientas/mapa_codigo.py mapa <palabras>` → tema; `mapa id=<tema>` → archivos, símbolos con línea, temas conectados y títulos de notas; nota entera: `mapa id=<tema> nota N` o `buscar <palabras>` (`notas` = todas: caro).
2. `conexiones <módulo|tema>` · `donde <nombre>` · `simbolo <nombre>` (`modulo.nombre` si se repite) · `modulo <archivo>` · `llamadas <nombre>`.
3. Si falta: Grep + Read con offset/limit (~60 líneas). Historia y medidas de una regla: Grep en `PROGRAMA/docs/reglas_detalle.md` o `SKILL.md`.
4. NUNCA leer enteros: `build_trailers.py`, `trailer_xv.py`, `escena_go.py`, `estilos_inicio.py`, `orbe_mecanica.py`, `SKILL.md`, `reglas_detalle.md`, `PROGRAMA/datos/**`, `PROGRAMA/recursos/**`.

## Mapa de temas (`mapa id=<tema>`)
<!-- MAPA:INICIO (lo escribe PROGRAMA/herramientas/mapa_codigo.py generar) -->
- **que-entra**: Material › «Qué entra al video»: plan plano a plano, lo que queda fuera y por qué
- **boton-play**: El botón GO: analizar, armar, renderizar, masterizar, abrir carpeta
- **inicio-escena**: Escena GO de CineCaptions: OCULTA desde 1.6.0
- **ventana**: Ventana sin marco, pestañas, chequeo de arranque, instancia única
- **diseno**: Diseño 1.6.0: pastilla de estado, Inicio, Ajustes en tarjetas, pasos y avance
- **animaciones**: Animaciones (Higgsfield): astrolabio vivo, cielo, fundidos, brillos; medir fluidez
- **arranque**: Abrir rápido y fluido: fuentes, cargas diferidas, TRAILER_TIEMPOS
- **material**: Material: solo JPG + al menos 1 video, capturas para la intro, agregar/arrastrar
- **soltar**: Soltar carpeta: se usa donde está, se une al evento, renombra en su sitio, nunca borra
- **rutas**: Rutas: código vs instalado, DATOS, EVENTO TERMINADO, Resolve, LUT, ffmpeg
- **analisis**: Análisis: relojes, calidad/color/audio, la «vista» y la IA local (Qwen3-VL)
- **oido**: Oído (earshot, opcional): emoción por sonidos y revisión del audio final
- **resolve**: Conexión con DaVinci: abrir, proyecto, cuadros que bloquean, reenlazar
- **armado**: Armado de cada versión: planos, zonas, cortes al ritmo, lentos, repetir, speed ramp
- **media-pool**: Media pool en carpetas 01-06 por momento y fuente, con colores
- **color**: Color por plano (CDL, DCTL, looks), guardián y reducción de ruido
- **textos**: Títulos Fusion, capítulos, frases, gracias y tarjeta final
- **sonido**: SFX, whoosh, cambio de canción, música bajo la voz, mezcla en LUFS
- **formatos**: HORIZONTAL y VERTICAL 9:16 (lo horizontal recortado a lo importante, vertical.py)
- **entrega**: Render, -14 LUFS, medición final y revisar_video.py
- **editable**: Evento editable: .drp por video, «Editar en DaVinci», «Renderizar lo editado»
- **perfiles**: Tipos de evento (xv, boda, bautizo, graduación, cumpleaños): textos y capítulos
- **instalador**: Instalador .exe 1 MB + .dat (PyInstaller + C#) e icono
- **mac**: Mac: .dmg compilado desde Windows con GitHub Actions
- **registro**: registro.log, ganchos de errores, faulthandler y el icono del registro (popup de errores): dónde mirar
- **ia-resolve**: IA de Resolve Studio: IntelliSearch, transcripción, Speed Warp, Smart Reframe
- **actualizaciones**: Actualizaciones firmadas (trailer-automatico-releases)
- **limpieza**: Borrar caché en Ajustes (nunca material, videos, plantillas ni capturas)
- **pruebas**: Probar sin gastar: datos aislados, sin DaVinci, grab(), mapa del código
- **tiempos**: Cuánto tarda cada etapa, avance.py y qué ya se aceleró
- **musica**: Música original por estilo, canciones a gusto, escuchar.py
- **efectos**: Intros (Zoom por defecto) y su SFX, overlays de luz, título detrás de la persona
- **analisis-seguro**: Análisis que no se pierde: metadatos, guardado, flujo NTFS, buscar.py
- **permisos**: Popup de permisos al abrir (Windows y Mac)
<!-- MAPA:FIN -->

## Reglas que no se rompen
- **La persona:** español, respuestas breves, PowerShell 7; plan corto antes de tareas grandes.
- **Resolve:** preguntar antes de cambiar de proyecto · nunca `pm.SaveProject()` sobre "Untitled Project" (sale «Crear proyecto» y la API se cuelga) · nunca `InsertFusionTitleIntoTimeline` ni la herramienta Shadow de Fusion · los cambios de clips solo en la timeline activa y ya asentada.
- **Plantillas** `TRAILER XV - *`: no se tocan; cada evento es un duplicado.
- **Editable:** al terminar, la línea queda abierta en Edición y un .drp por video (solo esa línea) en `PLANTILLAS DE LOS VIDEOS`. ▶ rearma y reemplaza: sobre un evento ya armado se pregunta antes; lo retocado a mano sale con «Renderizar lo editado».
- **Sala de espera:** soltar NO arma: queda en el Inicio (`piezas.Sala`); solo arma con «Empezar».
- **Soltar:** la carpeta se usa DONDE ESTÁ (`estado.carpetas`, `rutas.fuentes()`); al armar sus archivos se renombran en su sitio (`VIDEO HORIZONTAL 001 (CEREMONIA).MP4`, `DRON 001 (FIESTA).MP4`, `FOTO 003 (MAQUILLAJE).JPG`; nombres viejos en `datos/analisis/nombres.json`). NUNCA se borra ningún archivo. Otra carpeta se une al evento; solo si el evento ya terminó empieza uno nuevo.
- **Material:** solo fotos JPG; sin JPG, la intro sale de capturas del video (`motor.capturas_intro`, por dentro en `CAPTURAS`). Con videos verticales se arma solo también el VERTICAL 1 min.
- **Popups:** nunca `QMessageBox` ni cuadros del sistema: `self._popup(...)` / `self._si(...)` (`piezas.Popup`). Toda pieza nueva lleva su animación.
- **Ventana:** en su hilo nada de API de Resolve, `subprocess` ni `sleep` (van en `Trabajo`, `EstadoDV`, `qt_kit.correr_en_hilo`).
- **Fluidez** (`mapa id=animaciones`, `id=arranque`): animar a 60 c/s por tiempo (`piezas.CUADRO_MS`); nada repinta la ventana entera salvo el cielo (20 c/s). Medir lo nuevo con `herramientas/medir_fluidez.py` (equipo tranquilo). Ventana con `setSwapInterval(0)` y nacida en RHI (`_ancla_rhi`); sin filtros de eventos globales (bordes = `BordeVentana`); QML por partes; disco en hilos. Nunca `QApplication.setStyleSheet` después de abrir (la hoja va en la ventana, `_hoja()`), ni sonido (`vistas_ajustes._hilo_sonido`) ni `QGraphicsOpacityEffect` sobre piezas grandes en el hilo de la ventana (`Popup._congelar`); avisos de tamaño pendientes en reposo (`_preparar_fotos`).
- **Arranque:** UNA familia de fuente; al abrir ningún símbolo que Segoe UI no traiga (✓ ☰ ✕ ▶ ⤓ ⚠ ✎, emojis); nada pesado antes de la ventana (numpy, Pillow, lecturas grandes).
- **Inicio:** el astrolabio vivo (`piezas.Astrolabio`, videos en `recursos/animaciones`); la escena de CineCaptions, oculta. Cada animación pinta solo mientras se ve.
- **Rutas:** siempre `rutas.py` (en el .exe todo queda en `sys._MEIPASS`): `import rutas` pone el código en `sys.path` (un script suelto agrega antes `PROGRAMA/nucleo`); un .py por ruta con `rutas.codigo("x.py")`; versión, perfiles y LEEME en `rutas.CONFIG_PROG`.

## Montaje (detalle: `mapa id=armado`, `efectos`, `formatos`, `sonido`, `textos`, `color`)
- 8 fotos en la intro y UNA al final (la mejor de la festejada, con la tarjeta final abajo).
- **Intro «Zoom»** (por defecto): cada foto se aleja parejo (1 + 0,045 × cuadros → 1; cortes 7-6-5-5-5-4-4-4), desenfoque 180° y viñeta 25 % (`zoom_rapido`, `ZOOM_INTRO_*`); el comp se exporta e importa (`ExportFusionComp`/`ImportFusionComp`). SFX `XV_RAMPA_ZOOM.wav` (riser con licencia) en `recursos/audio` (`hacer_sfx.py XV_RAMPA_ZOOM`); si falta, `XV_RAMPA`.
- **Sin repetir:** cada toma y cada escena como mucho 2 veces por versión (`MAX_USOS_TOMA`, `MAX_USOS_ESCENA`; el resumen de 15/30 no gasta usos). Si falta material: dron, otra parte libre de una toma, planos más largos (`_alargar`), fotos del momento; repetir es lo último, se avisa y se reparte. Capítulos entre ½ y 1,5× la plantilla (`repartir_zonas`): lo que sobra va a quien tiene material (`material_f`); un momento vacío escala el 1,5× de los demás; el que no da ni para la mitad baja (hasta ¼), salvo que otro pase su 1,5×.
- **Escena continua** (sin pausa de 3 min): ≤ 40 % de un capítulo de 15/30.
- **Momentos:** preparativos claros que ve la IA (maquilla, peinan, viste) → MAQUILLAJE; «se arregla/ajusta el vestido» solo si la hora no la deja en medio de otro momento (`_momento_vecinas`); tras la ceremonia, lo que la IA no ve como iglesia → FIESTA. Los cortes del día salen de lo que la IA ve en los videos con hora fiable (`_auto_ia`; luz/color solo si no hay). El día lo proponen teléfono/dron y votan todas las cámaras; lo grabado por teléfono/dron después del día = otro evento, fuera (`otro_dia`). Música elegida por tipo de evento (`musica_estilo_tipo`).
- **Tomas giradas** (`analisis/orientacion.py`, lo que se ve): `it["girar"]` 180 → `RotationAngle` 180 (también en plantillas); 90/270 → fuera; 0 → no se gira aunque el archivo diga -180; sin medida, -180 → 180. Sin estabilizar; la revisión final busca «TOMA AL REVÉS».
- **Personas:** IA propia en el análisis (`analisis/caras.py`, YuNet + SFace; sin modelos, IntelliSearch) → `it["caras"]`, `it["prota"]`; la festejada = la cara en más archivos; sus tomas y fotos primero.
- **Tomas malas fuera:** desenfocadas, quemadas, torcidas, al piso (`vista`, también contra la mejor cámara; la que grabó buena parte del evento y en la que se ven caras —una GoPro gran angular— se mide contra su propio enfoque: `_enfoque_evento`, `_ref_camara`). La IA revisa cada 3 s (`vision_ia.instantes`; no pregunta lo que ya quedó fuera, `receta.tramos_fuera`; si después deja de estar fuera, lo repasa: `_repasar_saltados`): techo, piso, de cabeza, tapada, sin cabeza, de espaldas o sin caras → fuera ese tramo. Lo muy movido no entra.
- **Quien habla** se ve dos veces, en SU cara (`encuadre.quien_habla`: la boca que se mueve; si no, la IA; si no, plano abierto; en iglesia `el_sacerdote`), plano medio hasta 2× en 4K, ≤ 2 por toma (`HABLA_MAX_TOMA`); la voz de una escena continua ≤ 25 % del capítulo (`VOZ_ESCENA_PARTE`).
- **Aéreas:** sin despegue ni aterrizaje, mejor con paneo parejo, centradas en lo importante (Qwen3-VL, `bbox_2d` 0-1000), también en 9:16 (`armar_ref._centrar_aereo`); en 15/30 cada capítulo abre desde el aire (`dron_clave`) y el último plano antes de la imagen final es aéreo. Antes de renderizar, la IA sale de la GPU (`vision_ia.soltar_gpu`).
- **Cámara lenta:** los más emotivos (24 en 15, 40 en 30) y «lento natural» de lo grabado a ≥ 48 c/s (`LENTO_NATURAL`).
- **Speed ramp** (interruptor en Tráilers, estado `speed_ramp`, apagado de fábrica; `TRAILER_SPEED_RAMP=1`): `marcar_rampas` pone 2/3/6/10 en tomas firmes de acción: normal → 2,5× (`poner_rapido`) → lento desde un golpe; son tres clips seguidos de la misma toma (`SetSpeed` no hace curvas), sin fundido, zoom ni estabilizador entre ellos, mismo color (`rampa_tramo`) y franja 9:16. FALTA verlo en DaVinci.
- **Formatos:** horizontal = horizontales y verticales; vertical 9:16 («… - VERTICAL 1min») y plantillas 9:16 = lo vertical y lo horizontal recortado a lo importante (`armado/vertical.py`: la festejada al centro, sin cortar caras, con el Pan del clip; horizontal pesa 0,6, HD 0,3). Seguir a la persona (Fusion «REENCUADRE») APAGADO hasta verlo (`vertical.SEGUIR`; `TRAILER_SEGUIR=1` para probar).
- **Captions:** en 15/30 frases 9 s, capítulos 7,5 s, «gracias» 8,5 s y ≥ 30 s entre textos (el capítulo manda); título y actos de la plantilla 5,2 s; escritura 1,2-2,2 s, fundidos 1,2/1,5 s, nunca sobre la voz (1 y 3 min: 7,5 y 12 s). Plantillas de referencia: cada una con tomas distintas.
- **Voz original** solo de quien habla de corrido (pastor, brindis, discursos): siempre en 30, activada en 15, a elegir en 1 y 3. En 15/30 `guion_voz.py` etiqueta cada frase (la nota la pone el programa) y arma APERTURA / HISTORIA / CIERRE: corte J 1,2 s, sincronía, a los 6,5 s otra cámara o foto, corte L, cortes en pausas; luego aplausos reales y destello; la música sube en 30 cuadros.
- **Sonido 15/30:** sin vítores/aplausos de biblioteca ni gritos invertidos fuera de la intro; un whoosh por capítulo; voz con aislamiento 75 y fundidos 0,5/1 s; la última canción acaba con su final natural (fundido 2 s); antes de la foto final, los novios en lento si no hay aérea (`FINAL_NOVIOS_S`).
- **Canciones a gusto** (`vistas_ajustes.CancionesEstilo`): oír, cambiar, quitar, agregar de «Tu música» o de la PC; lo agregado se COPIA a `DATOS/musica/<estilo>`; lo quitado queda en `musica_quitadas`; `musica_propia.pistas` lo junta para el armado. Nada se borra.
- **Estabilizador propio** (`armado/estabilizar.py`, Transform de Fusion con keyframes, zoom mínimo), no `Stabilize()`; comps ANTES del primer render del clip. Magic Mask no se automatiza; Depth Map no se renderiza en un comp de clip (`profundidad.py` apagado).
- **Color:** la saturación nunca pasa la de cámara (ni CDL ni look); `color_guardia` compara color relativo a la luz; el CDL apunta a la luz con el look puesto (`devolver_luz`); `medir_color` marca falsos SATURA/OSCURO en planos acercados. MAQUILLAJE morado, IGLESIA verde, FIESTA rosa.
- **Revisión con IA** del video final (`revision_ia`): cuadro a cuadro contra lo analizado, sin preguntar en fundidos, aéreas, fotos ni verticales con relleno; cada aviso se confirma con otro cuadro. `GetIsTrackEnabled` da False en pistas de una línea no activa. **Oído** (earshot, opcional, `oido.py`): solo sube la emoción y marca clics, huecos y saturación; nunca descarta ni frena.
- Antes de dar por bueno un video: hoja de contacto (2 cuadros/s) y mirarla. Entrega en MOV H.265 a -14 LUFS.

## Al cambiar algo
- **Mapa:** tema nuevo o cambiado en `PROGRAMA/docs/mapa.json` (cada nota empieza diciendo de qué trata: es su título; símbolo repetido como `modulo.nombre`) y `python PROGRAMA/herramientas/mapa_codigo.py generar`.
- **Probar:** SIEMPRE con `TRAILER_LIBERAR=0`: al abrir, el programa cierra a la fuerza Google y Claude (`liberar.al_abrir`, Ajustes › Rendimiento) y se da prioridad alta. Arneses en el scratchpad (motor simulado, `grab()` de la ventana real); contra Resolve sin tocar nada `python PROGRAMA/interfaz/trailer_xv.py --seco`; el plan sin DaVinci `python PROGRAMA/herramientas/storyboard.py 1min sb.jpg`; recetas en `mapa id=pruebas`.
- **Compilar:** solo si la persona lo pide; SOLO Windows y Mac Apple Silicon (nada de Intel). 1) subir `version.txt`; 2) `pwsh -File PROGRAMA/compilar/windows/construir.ps1` (→ `3 INSTALADORES/Windows`); 3) instalar con `/silencioso` (cierra el programa abierto: preguntar antes); 4) Mac: commit + push y `pwsh -File PROGRAMA/compilar/mac/construir_desde_windows.ps1` (→ `3 INSTALADORES/Mac`).
- **Repo PÚBLICO:** música, SFX y fuentes con licencia nunca van tal cual: canciones con derechos llevan « - » y el título en el nombre; fuera de git y de la actualización pública (y «Tu música», `recursos/musica/TU MUSICA`, entera); Mac: `python PROGRAMA/compilar/protegidos.py cifrar` y subir `recursos_protegidos`.
- **Tokens:** no releer lo leído; un armado en curso con `python PROGRAMA/herramientas/avance.py` (`tiempos` = minutos por etapa), nunca el registro, y sin consultar mientras corre; salidas largas con `Select-Object -Last N`; lo medido y lo ya intentado en `mapa id=tiempos`.
- **Icono:** `PROGRAMA/interfaz/icono_app.py`.
