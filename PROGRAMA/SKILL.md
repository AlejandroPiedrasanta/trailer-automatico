---
name: trailer-xv-auto
description: Arma automáticamente las versiones del tráiler de XV años (1, 3, 15 y 30 min) en DaVinci Resolve Studio 21 a partir de las carpetas de fotos, videos y dron del Escritorio, usando las plantillas del proyecto EVENTOS CINEMA. Úsala cuando la persona pida "arma/edita los tráilers", "procesa el material", "renderiza el XV" o suba material nuevo.
---

# Tráiler XV automático

Todo corre en local con el programa: `ARMAR TRAILERS.bat` (Windows) o `ARMAR TRAILERS.command` (Mac) abren `PROGRAMA/trailer_xv.py`, una ventana Qt6/PySide6 con un solo botón **▶ ARMAR TODO** (`motor.armar_todo`: analizar → armar → renderizar → masterizar → abrir carpeta). Claude solo hace falta para revisar o corregir.

## Repositorio público y Mac
- El repositorio público es https://github.com/AlejandroPiedrasanta/trailer-automatico (rama `main`). El `.gitignore` deja fuera `1 MATERIAL`, `2 VIDEOS TERMINADOS`, `INSTALADORES`, `PROGRAMA/datos`, `recursos/audio` y `FogtwoNo5.ttf`.
- La música, los SFX y las fuentes con licencia **no se publican en claro**. Van cifrados con AES-256-GCM en `PROGRAMA/recursos_protegidos/protegidos.bin.parteNN` (menos de 90 MB cada uno, por el límite de GitHub).
  - Script: `compilar/protegidos.py cifrar|descifrar`.
  - La clave solo está en `PROGRAMA/datos/clave_recursos.txt` y en el secreto `TRAILER_CLAVE` del repositorio.
  - Si cambia la música: `python PROGRAMA/compilar/protegidos.py cifrar`, después commit y push.
- Para compilar en Mac: Actions → «Instaladores Mac» (`gh workflow run "Instaladores Mac"`).
  - Corre en `macos-15` (Apple Silicon) y `macos-15-intel`, con `construir_mac.sh`.
  - Los .dmg quedan en Artifacts: `gh run download <id> -D INSTALADORES/Mac`.
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
- `pwsh -File PROGRAMA\compilar\construir.ps1` hace todo en %TEMP%\trailer_automatico_build y deja `INSTALADORES\Instalar Trailer automatico <version>.exe`. La versión está en `PROGRAMA\version.txt`.
  1. Ícono (`compilar\icono.py`).
  2. PyInstaller en modo carpeta, sin consola (`compilar\trailer.spec`). Los `.py` propios van también como datos porque `build_trailers.py` se ejecuta desde su archivo. Incluye `recursos` y `dctl`, más ffmpeg y ffprobe en `ffmpeg\`. Deja fuera librosa, scipy, Qt OpenGL y las traducciones de Qt.
  3. Autoprueba `TrailerAutomatico.exe --tarea verificar <txt>`: si no termina en `OK|`, no se crea el instalador.
  4. Zip del programa.
  5. `compilar\Instalador.cs` compilado con el `csc.exe` de .NET Framework 4 (C# 5: nada de `$""` ni `?.`).
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

## Carpetas (`rutas.py`, igual en Windows y Mac)
```
TRAILER XV AUTOMATICO/
  ARMAR TRAILERS.bat / .command    el botón
  1 MATERIAL/ FOTOS · VIDEOS · DRON
  2 VIDEOS TERMINADOS/<EVENTO>/    renders masterizados
  PROGRAMA/                        código, SKILL.md, dctl/ (DCTL + LUTs de look), docs/
    recursos/                      plantillas/EVENTOS CINEMA - PLANTILLAS.drp, audio/ (música y SFX), fuentes/
    datos/                         analisis/ (cachés), respaldos/, CLASIFICACION_EVENTO.json, venv-mac/
```
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
- `analizar_material.py`: lee la hora real de cada archivo (EXIF, iPhone, nombre DJI, cámara), la duración, los tramos negros y la **calidad por medio segundo** (nitidez, luz, temblor). Clasifica con `CLASIFICACION_EVENTO.json`.
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
- **Color por plano**: `analizar_material._color` mide en cada medio segundo la luz, el negro (p2), la saturación y el RGB de los grises. En `build_trailers.cdl_para`, cada plano recibe `SetCDL` en el nodo 1:
  - exposición al 75 % hacia la luz típica de su momento (`objetivos_de_luz`);
  - mapeo de negros lechosos;
  - balance de blancos solo si hay suficientes grises;
  - saturación normalizada: `(SAT_OBJETIVO / sat) ** 0.5` limitada a `SAT_LIMITES` (sube las lavadas o log y baja las chillonas).
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
