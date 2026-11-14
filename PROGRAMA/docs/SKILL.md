---
name: trailer-xv-auto
description: Arma automáticamente las versiones del tráiler de XV años (1, 3, 15 y 30 min) en DaVinci Resolve Studio 21 a partir de las carpetas de fotos, videos y dron del Escritorio, usando las plantillas del proyecto EVENTOS CINEMA. Úsala cuando la persona pida "arma/edita los tráilers", "procesa el material", "renderiza el XV" o suba material nuevo.
---

# Tráiler XV automático

Todo corre en local con el programa: `ARMAR TRAILERS.bat` (Windows) o `ARMAR TRAILERS.command` (Mac) abren `PROGRAMA/interfaz/trailer_xv.py`, una ventana Qt6/PySide6 con un solo botón **▶ ARMAR TODO** (`motor.armar_todo`: analizar → armar → renderizar → masterizar → abrir carpeta). Claude solo hace falta para revisar o corregir.

## Repositorio público y Mac
- El repositorio público es https://github.com/AlejandroPiedrasanta/trailer-automatico (rama `main`). El `.gitignore` deja fuera `1 MATERIAL`, `2 VIDEOS TERMINADOS`, `INSTALADORES`, `PROGRAMA/datos`, `recursos/audio` y `FogtwoNo5.ttf`.
- La música, los SFX y las fuentes con licencia **no se publican en claro**. Van cifrados con AES-256-GCM en `PROGRAMA/recursos_protegidos/protegidos.bin.parteNN` (menos de 90 MB cada uno, por el límite de GitHub).
  - Script: `compilar/protegidos.py cifrar|descifrar`.
  - La clave solo está en `PROGRAMA/datos/clave_recursos.txt` y en el secreto `TRAILER_CLAVE` del repositorio.
  - Si cambia la música: `python PROGRAMA/compilar/protegidos.py cifrar`, después commit y push.
- Para compilar en Mac: Actions → «Instaladores Mac» (`gh workflow run "Instaladores Mac"`).
  - Corre en `macos-15` (Apple Silicon) y `macos-15-intel`, con `construir_mac.sh`.
  - Los .dmg quedan en Artifacts: `gh run download <id> -D "3 INSTALADORES/Mac"`.
- Para subir workflows, `gh` necesita el permiso `workflow`: `gh auth refresh -h github.com -s workflow`. Lo autoriza la persona.

## Pantalla de Inicio = la de CineCaptions
- Librerías: solo PySide6 (QPainter) + numpy, sin web ni OpenGL. Son los módulos de CineCaptions copiados tal cual:
  - `escena_go.py`: esfera de unas 7000 partículas proyectada con numpy, con resplandor (bloom), objetos absorbidos, cometas por paso, barra de avance abajo y explosión al 100 %.
  - `estilos_inicio.py`: estilos Nebulosa, **Astrolabio** (por defecto) y Proceso.
  - `orbe_mecanica.py`: el astrolabio de bronce.
  - `ritmo_ui.py`: un reloj alineado con la pantalla.
  - `boton_go.py`: `BotonGo`, extraído de `un_clic_ui.py`.
- Adaptadores de lo que esos módulos tomaban de CineCaptions: `qt_kit.py` (`fuente`, `correr_en_hilo`, `icono_linea`), `i18n.py` (`tr`), `ajustes_ui.py` (`go_estilo` del estado), `efectos_ui.py`, `tema.py`, `sfx_audio.py` (sonidos apagados para no meter QtMultimedia) y `registro.aviso`.
- Solo se cambiaron textos: `PALABRAS`, `EMOJIS`, `NOMBRES_PASO` (Material, DaVinci, Ritmo, Montaje, Render, Audio) y `FRASE`. Las claves de fase siguen siendo las de CineCaptions (timeline, voz, ia, diseno, sfx, resolve), porque cada una enciende una pieza del astrolabio.
- Cableado en `trailer_xv.py`, como `PanelGo` en CineCaptions:
  - `EscenaGo` es hija de `cielo`, va bajada (`lower`) y solo está visible y activa en Inicio.
  - Le pasa `proveedor = _geo_escena` (centro y radio del botón, rectángulo de la lista de pasos en `self.reserva`), `datos_barra = _datos_barra` (con `PESO_GO` por fase) y `boton.seguir_a(escena)`, para usar un solo reloj.
  - Las líneas del registro (`LINEAS`) llevan a `_marcar(fase)`, que llama a `escena.paso`, `escena.poner_fase` y `boton.poner_fase`.
  - El % pasa por `_poner_prog`, que llama a `boton.poner_progreso` y `escena.progreso`.
  - Al terminar: `escena.explotar(cerrar)`, después `escena.terminar` y `boton.poner_estado('hecho')`.
  - `etiquetas_ocultas` devuelve las plantillas y la etiqueta del evento.

## Ventana (`trailer_xv.py`)
- Ventana sin marco con fondo de cielo animado (`Cielo`) y un botón de reloj con engranaje (`BotonReloj`): el engranaje gira y el aro esmeralda muestra el % mientras trabaja.
- Debajo del botón: chip del evento, que lleva a «Textos», y selector **PLANTILLAS** (1/3/15/30 min y Todas, siempre al menos una). Lo elegido se guarda en `estado.versiones`.
- Pestañas: Inicio, Material (tarjetas FOTOS/VIDEOS/DRON con «Agregar…» y zona para soltar archivos), Textos y Ajustes. El botón ☰ muestra el registro.
- `motor.revisar_material` aplica `MINIMOS` (8 fotos, 1 video, dron opcional). Con ▶ y material faltante, `_pedir_material` lo pide. `QFileSystemWatcher` recuenta solo.
- Arrastrar o agregar usa `motor.copiar_material`: ordena por extensión, manda `DJI_*` a DRON y no copia lo que ya está con el mismo nombre y tamaño.
- `motor.chequeo` es el chequeo de arranque: material, ffmpeg, DaVinci, plantillas, carpeta de LUT y librosa. El punto del menú indica si DaVinci está abierto (`EstadoDV`, en hilo).
- **QSS:** un `QPushButton` sin borde (`border: none`) o con radio mayor que la mitad de su alto sale con esquinas rectas. Usa `border: 1px solid transparent` y radio ≤ alto/2.

## Instalador .exe (Windows) — mismo método que CineCaptions
- `pwsh -File PROGRAMA\compilar\windows\construir.ps1` hace todo en %TEMP%\trailer_automatico_build y deja `3 INSTALADORES\Windows\Instalar Trailer automatico <version>.exe`. La versión está en `PROGRAMA\version.txt`.
  1. Ícono (`compilar\icono\icono.py`, que dibuja `interfaz\icono_app.py`: la imagen EXACTA que dio la persona: `recursos\icono_fuente.png`, limpiada con `python compilar\icono\icono.py limpiar <imagen>`, que recorta el cuadro y quita el fondo claro y la sombra; sin ese archivo dibuja una versión vectorial).
  2. PyInstaller en modo carpeta, sin consola (`compilar\windows\trailer.spec`). Los `.py` propios van también como datos porque `build_trailers.py` se ejecuta desde su archivo. Incluye `recursos` y `dctl`, más ffmpeg y ffprobe en `ffmpeg\`. Deja fuera librosa, scipy, Qt OpenGL y las traducciones de Qt.
  3. Autoprueba `TrailerAutomatico.exe --tarea verificar <txt>`: si no termina en `OK|`, no se crea el instalador.
  4. Zip del programa.
  5. Al terminar bien (con ventana, sin `/noabrir` ni `/silencioso`) el instalador **abre el programa y se cierra solo** a los 1,5 s (3 s si hubo avisos), pedido por la persona. En la Mac lo hace el `postinstall` en segundo plano: espera el recibo del paquete, abre la app, cierra el Instalador y expulsa el .dmg.
6. `compilar\windows\Instalador.cs` compilado con el `csc.exe` de .NET Framework 4 (C# 5: nada de `$""` ni `?.`).
  6. El zip se pega al final del instalador, seguido de un pie de 8 bytes de posición + `TRAILER1`.
- El instalador es per-user (`asInvoker`): va en `%LOCALAPPDATA%\Programs\TrailerAutomatico`.
  - Crea accesos en Inicio y Escritorio (`WScript.Shell`) y la entrada `HKCU\…\Uninstall\TrailerAutomatico`.
  - El desinstalador es el mismo .exe sin el zip (`Desinstalar.exe /desinstalar`).
  - Al final llama a `TrailerAutomatico.exe --tarea instalar <txt>`: carpetas de trabajo, fuentes (HKCU), DCTL y LUT en `LUT\MCP` y migración de análisis. Lee líneas `PROGRESO|n|texto` y `OK|` / `ERROR|`.
  - Modos: `/silencioso /noabrir /sinescritorio /dir=`.
- Instalado (`rutas.CONGELADO`):
  - Los recursos están en `sys._MEIPASS`.
  - Los datos (análisis, estado, `registro.log`, `config.json`) van en `%LOCALAPPDATA%\TrailerAutomatico`.
  - La carpeta de trabajo sale de `config.carpeta_trabajo`; si no está, se usa `Escritorio\TRAILER XV AUTOMATICO`.
  - Para fusionscript se definen `PYTHON3HOME=_MEIPASS` y `os.add_dll_directory(<carpeta de Resolve>)`.
- Sin librosa en el .exe: `ritmo.py` usa el ritmo ya calculado de las canciones de las plantillas (`recursos\ritmo_plantillas.json`, clave `nombre|inicio|duración`). Si falta una canción, recurre a `_golpes_numpy` (flujo espectral + programación dinámica de Ellis).
- `registro.py`: `registro.log` rotativo, `excepthook`, `threading.excepthook`, `faulthandler` (`fallo_nativo.log`) y stdout/stderr a devnull en el .exe. `QLockFile` impide abrir dos instancias.
- **Bug corregido:** `pm.SaveProject()` sobre el «Untitled Project» que Resolve abre al arrancar saca el cuadro «Crear proyecto» y la API se queda esperando para siempre. Ahora solo se guarda un proyecto con nombre (`_sin_titulo`), y `_Vigilante` cancela ese cuadro si aparece mientras se conecta. `estado_davinci` ya no usa la API ni el candado: mira el proceso (`tasklist` / `pgrep`) y el título de la ventana.

## Actualizaciones (como CineCaptions, pedido 2026-11-13: «todo en su repo pública»)
- Se publican en el repositorio PÚBLICO `AlejandroPiedrasanta/trailer-automatico-releases` (GitHub Releases): `version.json` firmado (Ed25519) + los instaladores **públicos sin música, SFX ni FogtwoNo5** (`Actualizar_Trailer_automatico_<v>.exe`, `Actualizar_Trailer_automatico_Mac_<arq>_<v>.dmg`). El programa lee `releases/latest/download/version.json`.
- Publicar: subir `config/version.txt`, commit y push, y `pwsh -File PROGRAMA\herramientas\publicar_version.ps1 -Notas "..."` (compila Windows, compila los .dmg públicos en GitHub con `publico=true`, arma y firma el manifiesto, crea el release).
- Claves privadas FUERA del repo: `~/TrailerAutomatico_claves/firma_principal.txt` y `firma_reserva.txt` (guardar la de reserva aparte). Las públicas están en `actualizaciones.CLAVES_FIRMA`. Sin clave, nadie puede repartir un instalador a los programas.
- El instalador COMPLETO (`3 INSTALADORES`) trae la música; al instalarse la guarda aparte en `rutas.PROTEGIDOS` (Windows `%LOCALAPPDATA%\TrailerAutomatico`, Mac `/Users/Shared/TrailerAutomatico`), así las actualizaciones públicas no la borran. El `preinstall` de la Mac rescata la de versiones viejas.
- Programa abierto: busca al abrir y cada 4 h, baja sola la versión nueva y la instala al cerrar (o «Instalar ahora», que la reabre). Ajustes muestra la versión y «Buscar actualizaciones».
- Programa cerrado: Windows, tarea programada del usuario «Trailer automatico Actualizaciones» (cada 4 h y al iniciar sesión; la quita el desinstalador). Mac, LaunchDaemon `com.cinemaproductions.trailerautomatico.actualizar` de root (lo pone el `postinstall`, lo quita `Desinstalar.command`): instala el .pkg sin contraseña; el archivo `/Users/Shared/TrailerAutomatico/.sin_abrir` le dice al `postinstall` que no abra la app.
- **1.5.1 publicada el 2026-11-13** (color suave para Rec.709, ruido por toma, reloj sin poner y ceremonia tras una pausa). Probada antes con el programa instalado armando en DaVinci (46 de 46 clips) y con un XV real de 309 fotos, 75 videos y 4 de dron: análisis 10 min, armado de las 4 versiones 11 min (estabiliza hasta 150 tomas por versión), render 9 min, audio a −14.0 LUFS. Después: «Pruebas en varios equipos» 7 de 7 y la Mac subió sola de 1.5.0 a 1.5.1 en 15 s.
  - Un comando de la herramienta Bash de más de unos 8000 caracteres llega cortado («unexpected EOF»): partirlo o escribir el archivo con Write.
- **1.5.0 publicada el 2026-11-13** («suelta la carpeta y listo», fotos de cámara en la intro). Antes de publicar: instalar la completa aquí y `probar_arrastre.py --programa <exe instalado>`. Después: «Pruebas en varios equipos» (7 de 7) y «Probar instalador Mac» con `vieja=1.4.1` (el servicio la subió sola a 1.5.0 en 14 s, con la música intacta). Si se lanzan a mano las dos compilaciones de Mac (`publico=true` y `false`), bajar los .dmg a `datos/publicar` y a `3 INSTALADORES/Mac` y publicar con `-SinCompilar`.
- Probado en Windows (2026-11-13): instalación completa → música guardada aparte; actualización en segundo plano con el instalador público (manifiesto local firmado con `TRAILER_URL_ACTUALIZACIONES=file:///...`) → instalado en 31 s, música intacta, autoprueba OK.

## Pruebas en varios equipos (GitHub Actions)
- **«Pruebas en varios equipos»** (`.github/workflows/pruebas_equipos.yml`) prueba los instaladores PUBLICADOS en Windows Server 2022 y 2025, en Windows 11 ARM (x64 emulado), en Mac macOS 15 y 26 con chip Apple, en Mac Intel y en la versión Intel bajo Rosetta. Cada equipo hace esto:
  - instala y abre;
  - corre la autoprueba;
  - revisa la tarea o el servicio de actualizaciones y que lea la versión publicada;
  - usa el instalador con ventana (abre el programa y se cierra solo) y una carpeta con espacios y acentos;
  - desinstala sin dejar nada.
  - Scripts: `compilar/windows/probar_equipo.ps1` y `compilar/mac/probar_instalacion.sh` (`PROBAR_EXTRA=1`).
- **«Probar instalador Mac»** con `vieja=1.3.9` compila una versión vieja, la instala y comprueba que el servicio la actualice solo a la publicada sin perder la música.
- Lecciones del 2026-11-13:
  - El LaunchDaemon arranca al cargarse **dentro del postinstall** y actualizaba encima de la instalación en curso. Ahora `actualizar_fondo.instalando()` espera si hay un Instalador o installer corriendo, y la tarea de Windows empieza 30 min después de crearse.
  - En Windows 11 ARM `schtasks` tardó más de 30 s al instalar. Ahora tiene 90 s y 3 intentos, y el programa la vuelve a crear al abrirse.
  - La ventana tenía un mínimo de 818 px de alto por el astrolabio fijo en el layout. Ahora va en `hueco_boton` (fuera del layout), las páginas usan `QScrollArea` y el mínimo es 880×580.
  - Al copiar material, dos cámaras con `DSC_0001.JPG` se pisaban. Ahora la segunda se llama «(2)», se ignoran los `._` de la Mac y la copia pasa por un temporal.

## Suelta la carpeta y listo (pedido 2026-11-13: «arrastrar una carpeta con de todo y que lo ordene y empiece a armar»)
- **Flujo** (`trailer_xv.py`, `self.flujo`): soltar → `motor.examinar_origen` (cuenta fotos, videos, dron, lo que no sirve y la fecha) → si es de otro día que lo que hay, hoja «¿Es un evento nuevo?» → `Copia` (hilo, con avance y «Cancelar la copia») → hoja con tipo y nombres, o cuenta atrás → `_play()`.
  - El interruptor de Ajustes «Al soltar una carpeta, ordenarla y armar el tráiler solo» (`auto_armar`) lo apaga: entonces solo copia y ordena.
  - Evento nuevo: `motor.archivar_material` mueve lo anterior a `1 MATERIAL/ANTERIORES/<evento>` y limpia nombres, frase y líneas guardadas. Nunca borra.
  - Los avisos y preguntas van en `Hoja` (tarjeta sobre la escena), no en `QMessageBox`.
- **Ordenar** (`motor.copiar_material`): copia por trozos a `.copiando` y renombra al final; salta lo idéntico, renombra choques «(2)», revisa el espacio en disco e ignora basura (`._`, `Thumbs.db`, vacíos, RAW, documentos).
  - Dron: nombre `DJI_`, carpeta llamada dron/drone/aéreo/mavic, o el codificador DJI en los metadatos (`_info_video`, no Osmo/Pocket/Action).
- **Momentos** (`analizar_material._auto`): primero por contenido (`_auto_contenido`: programación dinámica MAQUILLAJE → IGLESIA → FIESTA, ajustada al hueco de 8 min o más que esté cerca); si no hay con qué, por huecos (`_auto_huecos`).
  - Si la `CLASIFICACION` guardada es de otro día, se renombra a `.anterior` y se empieza de cero.
- **Plan previo sin DaVinci** (`motor.plan_previo`): corre `build_trailers` con `DRY_RUN` y `SIN_RESOLVE` sobre `recursos/plantillas_marcadores.json` (marcadores de las 4 plantillas) y lo guarda en `datos/analisis/plan_previo.json`. Sale en el registro antes de conectar con DaVinci.
  - Si se cambian los marcadores de una plantilla, volver a leerlos de EVENTOS CINEMA y actualizar ese JSON.
- **Variedad** (`Planificador.separar`): separa cortes seguidos del mismo video (55 % → 11 % en la boda de prueba).
- **Prueba de arrastre** (todo en local, no toca `1 MATERIAL` ni el proyecto de Resolve):
  - `python PROGRAMA/herramientas/probar_arrastre.py` crea un evento de mentira (27 fotos, 17 videos, 3 de dron, archivos rotos y basura), abre el programa con `TRAILER_BASE` y `TRAILER_DATOS` aparte, suelta la carpeta con eventos de Qt y comprueba cada etapa. Deja `resultado.txt` y capturas.
  - `--programa <exe>` prueba el instalado o compilado · `--dos-eventos` prueba la pregunta y ANTERIORES · `--con-davinci` arma de verdad la de 1 min (crea «BODA 2026-10-17 - 1min»; preguntar antes).
  - Sin `--con-davinci` apunta `RESOLVE_SCRIPT_LIB` a una ruta que no existe: debe terminar en «No encuentro DaVinci Resolve Studio…».
  - El guion vive en `nucleo/prueba_arrastre.py` (`Guion`), se activa con `TRAILER_PRUEBA_ARRASTRE` y en ese modo no busca actualizaciones ni crea la tarea programada.
  - En GitHub: **«Prueba de arrastre»** (`.github/workflows/prueba_arrastre.yml`) en Windows 2022/2025/ARM y Mac 15/26/Intel, con el código y con el programa compilado ahí mismo.
- Lecciones:
  - En Windows `os._exit` con hilos de Qt vivos terminaba con 0xC0000005: la prueba sale con `TerminateProcess`.
  - El error completo va al registro; en la ventana solo «No se pudo terminar: …».
  - Con el registro (☰) abierto, la pestaña Material quedaba cortada a la derecha: `_ancho_registro` angosta el panel (260 a 400 px) según lo que pide la página, y si ni así cabe la página se desplaza de lado.
  - El plan previo junta los avisos «repiten video» en una sola línea («Con el video que hay, las versiones de … repiten tomas»).
  - Resultado del 2026-11-13: 24 de 24 en GitHub (6 equipos × código y compilado × una carpeta y evento nuevo), 16 a 27 s cada una.
  - **Prueba real con DaVinci (2026-11-13, `--con-davinci`)**: armó «BODA 2026-10-17 - 1min» en 75 s con 46 clips, igual que la línea real, y destapó tres cosas:
    - Resolve junta en UNA «secuencia de imágenes» las fotos con números seguidos (`IMG_1001.JPG`, `IMG_1002.JPG`: los nombres de cámara) si entran en la misma llamada a `ImportMedia`, y la intro quedaba sin fotos («se pidieron 46 clips y se colocaron 38»). `lotes_sin_secuencia` las reparte por la paridad de su último número (con saltos de 2 quedan sueltas) e `importar_fotos` importa sola la que falte. La forma `{"FilePath": patrón, "StartIndex": n, "EndIndex": n}` también las junta.
    - `mp.DeleteClips` justo después de importar cerró DaVinci (al borrar cambia un instante a la página Medios). En el armado no se borra nada del media pool; una secuencia vieja se queda.
    - `_fin_copia` soltaba `self.copia` cuando el hilo aún no salía de `run()`: Qt destruye el `QThread` vivo y el programa se cierra sin avisar (1 vez de 4). Ahora queda en `_hilos_vivos` hasta que termina. Regla: un `QThread` se suelta en `finished`, nunca en su propia señal de resultado.
    - La prueba ahora falla si el registro dice «se pidieron … y se colocaron …».
    - Después de la prueba se borran la línea y las carpetas «BODA 2026-10-17» del proyecto (con DaVinci en reposo `DeleteTimelines` y `DeleteFolders` funcionan bien).

## Carpetas (`rutas.py`, igual en Windows y Mac)
```
TRAILER XV AUTOMATICO/
  ARMAR TRAILERS.bat / .command    el botón
  1 MATERIAL/ FOTOS · VIDEOS · DRON
  2 VIDEOS TERMINADOS/<EVENTO>/    renders masterizados
  3 INSTALADORES/                  Windows/ (.exe) · Mac/ (.dmg)
  PROGRAMA/                        SOLO carpetas (2026-11-13, pedido de la persona):
    interfaz/ nucleo/ analisis/ armado/ entrega/ herramientas/    el código por tema
    config/                        version.txt, perfiles_evento.json, requisitos.txt, LEEME.txt
    recursos/                      plantillas/EVENTOS CINEMA - PLANTILLAS.drp, audio/ (música y SFX), fuentes/
    recursos_protegidos/ dctl/     audio cifrado del repo · DCTL + LUTs de look
    compilar/                      windows/ (construir.ps1, spec, C#) · mac/ · icono/ · protegidos.py
    docs/                          SKILL.md, mapa.json, capturas/
    datos/                         analisis/ (cachés), respaldos/, registro/, CLASIFICACION_EVENTO.json, venv-mac/
  (ocultos: .git, .github, .gitignore, .gitattributes, CLAUDE.md)
```
- El código va en carpetas pero los módulos se importan igual (`import motor`): `import rutas` agrega las carpetas a `sys.path` (`rutas.GRUPOS`); los scripts sueltos agregan antes `PROGRAMA/nucleo`. Un `.py` por ruta con `rutas.codigo()`. En el .exe/.app todo queda junto en `_MEIPASS` (los spec juntan las carpetas).
- Los archivos ocultos de Windows no se abren con `"w"` (acceso denegado): `mapa_codigo` reescribe `CLAUDE.md` con `"r+"` y `truncate`.
- Rutas de Resolve por sistema en `rutas.py` (`SCRIPT_API`, `SCRIPT_LIB`, `DIR_LUT`, `RESOLVE_APP`). En Mac se agrega Homebrew al PATH.
- Caché de análisis con clave `nombre|tamaño`: sobrevive a mover carpetas o pasar a Mac.
- `motor.conectar_resolve`: si el proyecto no existe (Mac u otra PC), hace `ImportProject` del `.drp` de `recursos/plantillas`. `motor.reenlazar` reenlaza por nombre (`RelinkClips`) los clips cuyo archivo no está, buscando en `1 MATERIAL` y `recursos`. `motor.instalar_fuentes` copia las fuentes a `~/Library/Fonts` en Mac.
- `empaquetar.py` crea `PARA LA MAC.zip`: programa + recursos, sin `datos`, y con el `.command` ejecutable.
- Para regenerar el `.drp` de plantillas: exportar el proyecto, importarlo como temporal, borrar `02 EVENTOS`, `03 VIDEO`, `04 FOTOS` y la cola, exportar a `recursos/plantillas`, volver a EVENTOS CINEMA y borrar el temporal.

## Resolve
- Base **EVENTOS**, proyecto **EVENTOS CINEMA**, 24 fps.
- Plantillas: `TRAILER XV - 1min / 3min / 15min / 30min`. Tienen música por actos, SFX, textos Text+ y grupo de color, con V1 y V2 vacías. **No se modifican**: cada evento es un duplicado `<EVENTO> - 1min`, etc.
- Marcadores de la persona en cada plantilla: `FOTOS`, `MAQUILLAJE`, `IGLESIA`, `FIESTA`.
- Pistas: V1 VIDEOS, V2 FOTOS INTRO, V3 TEXTOS, V4 AJUSTE (8 destellos de la intro), V5 TITULOS, V6 EFECTOS · A2–A3 MUSICA, A7 SFX WHOOSH.

## Tipos de evento (plantillas universales)
`perfiles_evento.json` define 5 tipos: `xv`, `boda`, `bautizo`, `graduacion` y `cumpleanos`. Cada perfil tiene:
- **prefijo**: nombre del evento, por ejemplo «BODA 2026-11-07».
- **titulo / frase**: título con el nombre y subtítulo.
- **momentos**: nombres de las zonas MAQUILLAJE / IGLESIA / FIESTA en el media pool.
- **actos**: frases según el marcador ACTO.
- **plantilla**: reemplazos de los textos fijos «MIS XV», «MIS XV AÑOS» (Luxe Shine), «Un sueño que empieza» y «Te elijo hoy, mañana y siempre».

La firma «CINEMA PRODUCTIONS / UN FILM DE» no se toca. El tipo se elige en la ventana o con `TIPO_EVENTO` (estado `tipo_evento`). Si aparece otro texto fijo en la plantilla, agrégalo a `TEXTOS_FIJOS` en `build_trailers.py` y a los perfiles.

## Reglas de la persona
- **Solo 8 fotos**, en los destellos de la intro (5 frames cada una). Después, solo video.
- **Sin audio original** de los videos.
- Clasificar por momento con colores: MAQUILLAJE morado, IGLESIA verde, FIESTA rosa.
- Color y ruido por separado y universales, sin el clip de ajuste «RUIDO Y RETOQUE» (ya eliminado).
- Entrega en MOV H.265 (la cola de render ya está configurada así).

## Scripts
- `analizar_material.py`: lee la hora real de cada archivo (EXIF, iPhone, nombre DJI/Pixel/Samsung, cámara), la duración y, en **una sola lectura** del video, la calidad por medio segundo (nitidez, luz, temblor), el color, los tramos negros y el nivel del audio. En las fotos mide nitidez y huella dHash (ráfagas). Clasifica con `CLASIFICACION_EVENTO.json`.
  - **Reloj sin poner** (XV del 2026-11-08: la cámara de video marcaba 2018 y los 75 videos caían «por contenido», casi todos en iglesia): `_reloj_corrido` prueba, minuto a minuto, el corrimiento único con el que las tomas de esa cámara caen donde trabajaron las cámaras fiables (fotos con EXIF, celular, dron) y lo acepta solo si la cámara cubre al menos media jornada y 2 h, el 75 % de sus tomas queda cubierto y ningún otro corrimiento a más de 45 min encaja casi igual. Probado rompiendo el reloj de 5 formas (recupera el minuto exacto) y en 2 casos en que no debe adivinar.
  - **Ceremonia tras una pausa** (`_ceremonia_tras_pausa`, dentro de `_auto_contenido`): los preparativos se graban a ratos y una ceremonia casi seguida. Si el primer tramo del día con video grabado al menos el 35 % de 20 min llega justo después de una pausa de todas las cámaras de 60 min o más (dos fotos sueltas no la rompen), IGLESIA empieza ahí aunque lo que se ve no parezca una iglesia (ceremonia en jardín o salón); FIESTA se recalcula después. Solo actúa si el corte por contenido quedó a más de 60 min; si después de la pausa siguen los preparativos (la boda de prueba), no dice nada. En el XV propone 14:23 (a ojo, 14:30); antes proponía 10:31.
  - Los prototipos de contenido fallan en eventos atípicos (maquillaje en cuarto cálido de madera, ceremonia en carpa blanca, fiesta de día): sin horas, el XV se clasifica bien solo al 48 %. Por eso las horas reales valen tanto: antes de dar por perdido el reloj de una cámara hay que intentar alinearlo.
  - **Relojes por cámara**: si la fecha del archivo y `creation_time` difieren en un múltiplo constante de media hora, los metadatos venían en UTC y se corrigen. Si la fecha está mal pero la hora del día cuadra con las demás cámaras, se pasa al día del evento. Si no hay forma (copiados sin hora, otro día), se ordena **por contenido** (luz, negro, saturación, calidez y grises en la escala de su cámara) y por el orden de sus archivos, siempre MAQUILLAJE → IGLESIA → FIESTA.
  - Los videos largos que cruzan un límite llevan `tramos` y el planificador usa solo el tramo del momento.
  - Ventana: el panel «Cómo quedó organizado» (`linea_dia.py`) muestra el día; arrastrar Iglesia o Fiesta guarda la hora (`guardar_momentos`) y reclasifica sin volver a medir (`reclasificar`).
- `escenas_ia.py` (IA de Resolve Studio que sí devuelve datos): clasificación de audio (`Category` en los metadatos) y transcripción en español. Encuentra VOTOS, DECLARACION («los declaro», «puede besar»), AMOR, XV, BRINDIS y DISCURSOS, filtra alucinaciones («¡Suscríbete!», «[Música]»), marca cada frase en el media pool (marcador lavanda «VOZ») y lo guarda en `datos/analisis/escenas.json`. **Solo funciona con la página Medios abierta**: la abre y vuelve.
  - Con eso el armado pone 1-4 frases como **voz** sobre la música, **solo de la IGLESIA y solo VOTOS o DECLARACION** (`TIPOS_VOZ`; la persona: «solo el audio de la iglesia, no metas audios random»). Si no hay votos claros, no hay voz. Va en la pista **VOZ NATURAL** de la plantilla, con Voice Isolation y a -15 LUFS, y la **música baja 9 dB** debajo (`bajar_musica` parte el clip: no hay keyframes de volumen por script). Es la única excepción a «sin el audio original».
  - **Cámara lenta** (`marcar_efectos` + `poner_lento`): en los planos más emotivos (frases clave, el beso tras «puede besar», aplausos), `SetSpeed` 50 % con Speed Warp Better (40 % sin IA si el video es de 60 fps). Tope por versión en `LENTOS`.
  - **Estabilizar** (`estabilizar`): `TimelineItem.Stabilize()` en los planos con temblor medio ≥ `UMBRAL_TEMBLOR` (el analizador mide el temblor a 10 cuadros/s por correlación de fase). El dron no se toca.
  - **IntelliSearch** no devuelve datos al script: `indexar.intellisearch_videos` lo corre al final (Better + rostros), un video a la vez, y cede el paso si se pulsa ▶ (`indexar.PARAR`).
- `ritmo.py`: detecta los golpes de la música de la plantilla con librosa, para cortar al ritmo.
- `build_trailers.py`: duplica cada plantilla y la llena.
  - Intro de 8 fotos en V2.
  - Zona APERTURA (resumen de las mejores tomas) y zonas por marcador en V1, con las mejores ventanas de cada video, en orden cronológico, abriendo con dron.
  - Transiciones (`AddTransition`).
  - Títulos Fusion (`disenar_titulo`): Great Vibes escrito letra por letra (`End` animado) con empuje de `Size`, subtítulo Montserrat Regular con tracking que se abre y entra por `Blend`, halo y sombra con los elementos 3 y 5 de Text+, y velo `Background` + `EllipseMask` (SoftEdge 0.16, alfa `VELO_TITULO`) detrás del texto.
  - Whoosh en cada cambio de momento.
  - DCTL de ruido en el nodo de cada clip.
  - DCTL de corrección en el nodo PRE-CLIP del grupo y LUT del look en el POST-CLIP.
  - Media pool por momento y fuente, con colores. Respaldo `.drp` y render en cola.
  - Carpetas principales numeradas (`CARPETAS_RAIZ`): 01 PLANTILLAS, 02 EVENTOS\<EVENTO> (timelines), 03 VIDEO, 04 FOTOS, 05 MUSICA (INTRO Y EPICA / IGLESIA Y ROMANTICA / BAILE Y FIESTA) y 06 EFECTOS (PUBLICO / TRANSICIONES / ESPECIALES). `carpeta_raiz` las encuentra con o sin número; si existe el nombre viejo SECUENCIAS, lo usa como EVENTOS. No hay `Folder.SetName`: para renombrar una carpeta se crea la nueva, se mueve todo con `MoveClips`/`MoveFolders` y se borra la vieja.
- **Color: las tomas ya vienen en Rec.709 (color terminado de cámara) y se tocan POCO** (la persona, 2026-11-13: «son tomas Rec.709, no puedes manipularlo tanto»). Medido sobre la boda real (62 videos), la cadena completa deja saturación +6 a +11 % y contraste +2 a +14 %, sin nada quemado; antes daba saturación +18 a +31 %, contraste hasta +51 % y 3 a 7 % de altas luces quemadas. No subir estos márgenes sin volver a medir.
  - **Por plano** (`build_trailers.cdl_para`, `SetCDL` en el nodo 1; `analizar_material._color` mide luz, negro p2, saturación y grises cada medio segundo). Solo EMPAREJA:
    - exposición al 40 % hacia la luz típica de su momento (`objetivos_de_luz`), pendiente entre 0.92 y 1.12 (`PENDIENTE_LIMITES`);
    - negros lechosos solo desde 0.08 (`NEGRO_LECHOSO`), con desplazo de −0.04 a 0.02;
    - balance de blancos al 40 % y ±4 % por canal, solo si hay suficientes grises;
    - saturación hacia la típica DEL EVENTO (`objetivo_de_saturacion`, no un número fijo): `(objetivo / sat) ** 0.5` entre 0.90 y 1.08.
  - **Base** (`dctl/XV_CORRECCION_COLOR.dctl`, PRE-CLIP del grupo): casi neutra. Contraste 1.02 y rodilla en 0.90 para las altas luces; no mueve negros ni saturación.
  - **Look** (POST-CLIP del grupo): `preparar_grupo` pone el `_REC709.cube` de `LOOK_REC709`, que es el look mezclado con «sin cambio» (`herramientas/suavizar_looks.py`: fuerza 0.5; el Kodak a 0.25). El `XV_15min_FILM_KODAK.cube` es el Film Look de Resolve y espera imagen **Cineon Log**: entero sobre Rec.709 subía el contraste +45 %. Los .cube originales no se tocan.
  - El grupo de color es del proyecto: al armar cualquier evento, el look suave queda también en las líneas anteriores de esa versión.
  - Comprobado dentro de DaVinci (2026-11-13) sobre una copia de la línea real de 1 min con los CDL nuevos: iglesia, saturación ×1.02 y contraste ×1.12 contra el original (lo entregado con la 1.5.0 daba ×1.30 y ×1.28); fiesta de noche, ×0.97 y ×1.16 (antes ×1.28 y ×1.41). `SetLUT` del `_REC709` en el POST-CLIP funciona.
  - Una línea ya armada con el color viejo conserva sus CDL por plano: para que quede con el color nuevo completo hay que volver a armarla.
  - Para medir sin DaVinci: simular CDL + DCTL + LUT con numpy sobre cuadros de `1 MATERIAL` y comparar el módulo del croma y el contraste con el original (así se sacaron los números de arriba).
- **Ruido: cada toma se mide y recibe el nivel que pide SU ruido** (la persona, 2026-11-13: «mejora el ruido en todas las tomas, que sea algo importante» y «para cualquier video que ingrese a la plantilla es el mismo proceso»).
  - `analisis/ruido_tomas.py` mide 3 cuadros de cada video a tamaño de línea de tiempo: pasa-altos por bloques de 16×16 en tres escalas (fina, 2× y 4×, para el ruido de manchas que deja la compresión), solo en los bloques más lisos (percentil 10), y las sombras en proporción a su luz. Guarda en `datos/analisis/ruido_tomas.json` (una vez por video; 74 videos en unos 40 s).
  - `armado/ruido.py` lo pasa a 5 niveles (`UMBRALES` 5, 9, 16 y 28 ×1000) y escribe un DCTL por nivel (`XV_RUIDO_N1..N5.dctl`). El mismo bilateral 5×5: croma siempre; la luz con toda la fuerza solo en las sombras y nunca más de `LUMA_MEDIOS` (0.40) en tonos medios; desde N3 el croma y la luz de las sombras recogen de más lejos (`paso` 2, `grueso`).
  - «Quitar ruido» (0 a 100) sube o baja un nivel o dos a todas; 0 lo apaga. `motor.aplicar_ruido` lo aplica a las líneas ya armadas, también por toma.
  - Medido: con ruido puesto a propósito, igual que antes con poco ruido y +0.6 a +1.2 dB con mucho; en las tomas de noche de la boda, dentro de DaVinci, 12 a 21 % menos ruido que el filtro único de antes conservando 97 a 98 % del detalle; las tomas limpias (N1) conservan 98 % del detalle (antes 94 %).
  - Lo que NO sirve (probado): un bilateral «guiado» con el centro alisado borra textura (follaje a 66 %); medir el ruido con la diferencia entre cuadros se confunde con el movimiento de cámara; medir solo en fino no ve el ruido de noche.
  - La reducción de ruido propia de DaVinci (temporal) no se puede configurar por API: `TimelineItem.AddEffect("ofx", ...)` agrega «Reducción de ruido» pero con valores de fábrica no hace nada y `Effect` no tiene parámetros; un `.drx` lleva el grado en protobuf comprimido (zstd), sin nombres. Camino posible: que la persona deje el ruido a su gusto en un nodo, capturar ese grado (`GrabStill` + `ExportStills` a drx) y aplicarlo con `ApplyGradeFromDRX`.
  - Los nombres de efectos de `GetEffectsList` vienen en el idioma de DaVinci, y en `run_script` los literales con acentos no comparan bien: comparar por trozos sin acentos.
- `zonas_de` hace empezar IGLESIA o FIESTA en su marcador ACTO (CEREMONIA/ROMANTICA o FIESTA) cuando está a menos de `AJUSTE_ACTO_S` (5 s).
- Textos nuevos (`textos_extra`): capítulo por momento, frases repartidas según `CADA_FRASE` y «gracias» antes de la tarjeta final, en versiones de 3 min o más. Los textos salen de `perfiles_evento.json` (`capitulos`, `frases`, `gracias`). Cada texto es el PNG transparente `recursos/TEXTO_TRANSPARENTE.png`, que se importa a `06 EFECTOS\GRAFICOS` y se pone en V3 con `AppendToTimeline` (sobrescribe sin mover nada). Se recorta con `SetRightOffset`, lleva `AddFusionComp` con un TextPlus «Template» y `disenar_titulo(..., frase=True)` para las frases del tercio inferior, y entra y sale con `SetFades`. **No uses `InsertFusionTitleIntoTimeline`**: inserta en V1 y empuja toda la timeline (edición con ripple); con las pistas bloqueadas falla.
- `sfx.py` (`sonorizar`): borra de las pistas CHISPA, CAMPANAS, PUBLICO y PUBLICO 2 los SFX de posición fija, salvo el grito invertido. Luego coloca por momento campanas, pétalos, entrada, chispa, vítores sobre los cortes y aplausos en el cierre, con `SetFades`.
- `mezcla.py`: tras los whoosh, `nivelar` mide los LUFS del tramo exacto de cada clip de audio (ffmpeg ebur128) y pone `AudioVolume` = objetivo de la pista − medido (MUSICA -18, WHOOSH -22, CAMPANAS/GRITO -23, CHISPA -24, PUBLICO -25). Los trozos < 1 s usan la ganancia de su canción. Caché en `volumen.json`.
- `ruido.py`: DCTL de ruido con intensidad de 0 a 100 (0 = transparente; el nodo nunca se apaga porque lleva el CDL). `motor.aplicar_ruido` lo cambia en todas las timelines.
- Todo clip colocado lleva `Scaling = SCALE_FILL`, sin franjas. Los videos verticales se excluyen (`USAR_VIDEOS_VERTICALES`).
- `renderizar.py`: renderiza la cola del evento y espera a que termine.
- `indexar.py`: metadatos, marcadores «MEJOR TOMA», banderas e IntelliSearch (`AnalyzeForIntellisearch`).
- `motor.py`: funciones sin interfaz, con un candado para que nunca haya dos conversaciones con Resolve a la vez.
- `trailer_xv.py`: la ventana (Armar, Prueba en seco, Renderizar, Indexar). Sin ventana: `--una-vez`, `--seco`, `--vigilar`.
- `dctl/`: `XV_REDUCCION_RUIDO.dctl` y `XV_CORRECCION_COLOR.dctl`. Se copian solos a `LUT\MCP`.

## Pasos (cuando lo pide la persona)
1. `get_resolve_status`. Si Resolve está en otro proyecto, pregunta antes de cambiarlo.
2. `python trailer_xv.py --seco`: plan, ritmo y planos repetidos.
3. Revisa la clasificación con hojas de contacto. Corrige `CLASIFICACION_EVENTO.json` si hace falta.
4. `python trailer_xv.py --una-vez` (tarda de 1 a 5 min). Verifica con `run_script` y `get_image`.
5. `python renderizar.py "<EVENTO>"` en segundo plano. Verifica los .mov con ffprobe.

## Entrega
- `renderizar.py` masteriza el audio al terminar con `masterizar.py`: loudnorm lineal en dos pasadas a -14 LUFS, más `alimiter` a 0.79 (-2 dBFS, `level=false`), porque en modo lineal loudnorm no limita y quedaban picos de -0.8 dBTP. Usa `-shortest` para la duración exacta y copia el video sin recomprimir.
- `masterizar.verificar_imagen` mide el .mov final con signalstats a 1 fps: saturación media ≤ 60, cuadros con SATHIGH > 115 ≤ 10 %, luz media entre 60 y 150 y cuadros quemados ≤ 10 %.
- Verifica con `ffprobe` (duración) y con `ffmpeg -af ebur128=peak=true` (LUFS y pico).

## Lecciones (no repetir)
- `SetClipEnabled`, `DeleteClips` y otros cambios de clips solo funcionan en la timeline **activa y ya asentada**: `SetCurrentTimeline`, espera 1 s y vuelve a pedir la timeline.
- Con un cuadro de Resolve abierto («Organizador de proyectos», «Crear proyecto»), la API no responde o se queda colgada. `motor.dialogos_resolve()` los detecta antes de conectar.
- Justo después de `DeleteTimelines`, `DuplicateTimeline` con el mismo nombre puede fallar: reintenta con una pausa.
- `Project.SetName` renombra el proyecto (EVENTOS CINEMA) solo si no hay cuadros abiertos.
- **Nunca uses la herramienta Shadow de Fusion en los títulos**: con suavizado alto pide buffers de decenas de GB, llena la VRAM y tumba Resolve. Usa los elementos de sombreado de Text+.
- Resolve no borra la timeline abierta: activa antes la plantilla.
- Las fotos entran con duración fija: colócalas una a una y recórtalas con `SetRightOffset`. Los videos de 29.97 fps quedan 1 frame cortos: ajústalos después de colocarlos.
- `ImportMedia` con una lista simple de rutas.
- Las transiciones aparecen como elementos de la pista: fíltralas con `GetMediaPoolItem() is None`.
- `get_image` tiene un límite de 10 s. Si falla, revisa la VRAM con `nvidia-smi` y el registro `ResolveDebug.txt`.
- Otras sesiones o programas (Premiere) pueden estar usando la GPU y Resolve al mismo tiempo.
- Si lanzas el armado mientras Resolve todavía está arrancando con el Organizador de proyectos, `LoadProject` puede abrir el proyecto y aun así dejar colgado al script (proceso sin CPU). Espera a que Resolve muestre el proyecto o ábrelo antes; si el registro no avanza en 5 min, mata el proceso y relánzalo con `python -u ... *> log`.
- El velo de los títulos usa `EllipseMask` con SoftEdge moderado (0.16), que no causa problemas. Lo peligroso es solo la herramienta Shadow.
