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

## Mac: disco de «Doble clic para instalar» (desde la 1.5.7; la persona, 2026-11-16: «que funcione el instalador como este en Mac», con el de CineSlide 9.62)
- **El disco de la persona** trae solo `Instalar Trailer automatico.app` (centrada en (300, 160), 128 px, fondo `dmg/fondo_instalar.png`; `ajustes_dmg.py -D modo=instalador`) y el paquete oculto. Dentro: `Contents/MacOS/instalar` (Swift, `compilar/mac/instalador/instalador_mac.swift`, lo compila `construir_mac.sh` con `swiftc`), `Resources/TrailerAutomatico.app` y las imágenes del banner de Windows.
- **La ventana** es nativa (sale al instante) y es la de Windows (`Instalador.cs`): banner con el astrolabio que gira, PASOS, % y barra. Empieza sola: cierra la versión abierta, copia con `ditto` a `/Applications` (o `~/Applications` si no se puede escribir) por «.nuevo» y cambio de nombre, quita la cuarentena, `lsregister`, la fija en el Dock (`defaults export/import com.apple.dock`; si no hay ajustes del Dock no se toca) y corre `TrailerAutomatico --tarea instalar` (avance con `PROGRESO|n|texto`; si falla es aviso: el primer arranque lo repite). Al terminar abre el programa, se cierra y expulsa el disco. Con esa versión ya instalada (y `datos/instalado.txt` igual) solo abre el programa. Solo pide contraseña si la app instalada es de root (.pkg, hasta la 1.5.1). Registro: `datos/registro/instalador_mac.log`. `instalar --demo | --demo-error` simula.
- **El disco público** (actualizaciones, sin música) sigue de arrastrar: las 1.5.2–1.5.6 buscan `TrailerAutomatico.app` en la raíz. `_instalar_mac` y el `postinstall` del paquete oculto la buscan en la raíz o dentro del instalador.
- **Compilar desde Windows:** `pwsh -File PROGRAMA/compilar/mac/construir_desde_windows.ps1` (lanza `mac.yml`, espera, baja los .dmg a `3 INSTALADORES/Mac` y las capturas de la ventana a `datos/capturas_mac`). Compila lo subido a GitHub.

## Mac: disco de «Arrástralo a Aplicaciones» (desde la 1.5.2 hasta la 1.5.6; hoy solo el disco público; la persona, 2026-11-14: «así hazlo en Mac», con la captura del disco de CineCaptions 5.91)
- **Por qué:** instalar en /Applications con un .pkg SIEMPRE pide la contraseña de la Mac; arrastrar no.
- **El disco** (`compilar/mac/dmg/ajustes_dmg.py`, dmgbuild): `TrailerAutomatico.app` en (185, 168), el enlace «Aplicaciones» en (415, 168), iconos de 104, ventana 600×388 y el fondo claro de 600×360 que dibuja `dmg/fondo_dmg.py` (título, flecha verde y el consejo de «Abrir igualmente»). A la vista solo están esas dos cosas.
- **Primer arranque** (`tareas.primer_arranque`, lo llama `_arranque` en un hilo): lo que hacía el .pkg lo hace el programa al abrirse, una vez por versión (`datos/instalado.txt`): carpetas, música guardada aparte en `/Users/Shared/TrailerAutomatico`, fuentes en `~/Library/Fonts`, color en la carpeta de LUT y el servicio de actualizaciones. Si corre desde el disco o «trasladada» por macOS (`app_de_paso`), avisa que hay que arrastrarla.
- **Actualizaciones sin contraseña** (`actualizar_fondo`): `_asegurar_agente_mac` crea el LaunchAgent del usuario (`~/Library/LaunchAgents/com.cinemaproductions.trailerautomatico.actualizar.plist`: al iniciar sesión, cada 4 h y cuando hay un pedido en `datos/actualizacion/pedidos`). `_instalar_mac` monta el .dmg comprobado y `_reemplazar_app` copia la app nueva al lado («.nuevo», con ditto) y las cambia de nombre: nunca queda a medias.
- **Mac instaladas con el .pkg (hasta la 1.5.1):** conservan su servicio de root (`servicio_mac()` da "root" y no se crea el del usuario). Su servicio busca un `*.pkg` en el disco: por eso el disco trae OCULTO `.Actualizar Trailer automatico.pkg` (`pkgbuild --nopayload`), cuyo `postinstall` rescata la música de la app vieja, copia la app del mismo disco a /Applications (de root) y hace lo de siempre.
- **Desinstalar:** `Desinstalar.command` va dentro de la app (ya no en el disco) y sirve para las dos formas; con la app arrastrada no pide contraseña.
- **Pruebas** (`compilar/mac/probar_arrastrar.sh`, la llama `probar_instalacion.sh` cuando el disco trae la app): el disco, «arrastrar» con `ditto` SIN sudo, primer arranque, servicio del usuario cargado, un pedido atendido, `--tarea instalar_dmg <dmg>` reemplaza la app, y con `PROBAR_VIEJAS=1` una Mac con la versión publicada (su .pkg y su servicio de root) se actualiza con el paquete oculto. Resultado del 2026-11-14 en Mac con chip Apple e Intel: 27 de 27, copiar 2 a 4 s, reemplazar 2 a 6 s.
- **Sin probar:** que el servicio del usuario actualice a una versión PUBLICADA de arrastrar (la publicada, 1.5.1, todavía es de .pkg; se sabrá al publicar la 1.5.2 y luego la siguiente) y el aviso de Gatekeeper al abrir por primera vez una app bajada de internet (en GitHub el .dmg no viene con cuarentena).
- En la carpeta de LUT de DaVinci (`/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT`) ya no hay un instalador de root que dé permiso: si la Mac no deja escribir ahí, el chequeo de arranque lo dice.

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

## Todo por dentro y «EVENTO TERMINADO» (desde la 1.5.7; la persona, 2026-11-16)
- **Pedido:** «la ruta de instalación debe ser interna… el usuario no debe tener nada a la vista, solo la carpeta que se crea cuando termina el video»; «creas una carpeta que diga evento terminado y adentro 2 carpetas: video terminado y plantilla de los videos (las de DaVinci, por si hay que corregir algo)»; «los nombres: final con su tiempo; si son verticales, video final vertical con su tiempo»; «se vuelva a arrastrar otra carpeta: solo la unes al análisis».
- **Instalado:** `rutas.BASE` = `DATOS/trabajo` (1 MATERIAL por dentro). A la vista solo `rutas.SALIDA` (Escritorio, o `config.carpeta_terminados` desde Ajustes › Eventos terminados) / `EVENTO TERMINADO - <evento>/` con `VIDEO TERMINADO/` y `PLANTILLAS DE LOS VIDEOS/`. En código (desarrollo) BASE y SALIDA son la carpeta del proyecto.
- **Nombres:** `rutas.nombre_video`: `VIDEO FINAL 1 MIN`, `VIDEO FINAL 30 MIN`, `VIDEO FINAL VERTICAL 1 MIN`; el `.drt` se llama igual que su video. Lo usan `build_trailers` (CustomName y EDITABLE) y `motor.encolar_render` / `guardar_editable`.
- **Soltar:** sin la pregunta «¿Es un evento nuevo?»: se une al evento. Tras un render con al menos un video bueno, `motor.marcar_terminado` pone `estado.terminado = evento`; con eso `motor.es_evento_nuevo()` hace que lo siguiente que se suelte empiece otro evento (`archivar_material` → `1 MATERIAL/ANTERIORES`, por dentro). Sin terminar (o render fallido) se sigue uniendo.
- **Lo de antes:** `rutas.pasar_adentro` (en `tareas.instalar`, o sea al instalar en Windows y en Mac) mueve `1 MATERIAL` adentro y `2 VIDEOS TERMINADOS/<ev>` y `3 PLANTILLAS EDITABLES/<ev>` a su `EVENTO TERMINADO - <ev>` (los videos viejos conservan su nombre); quita la carpeta vieja si queda vacía y borra `config.carpeta_trabajo`. La carpeta que tiene `PROGRAMA/` (la del proyecto) nunca se toca. El análisis no se repite: su caché va por nombre y tamaño del archivo.
- **Probado** (2026-11-16): arnés que simula el instalado con un perfil de mentira (rutas, nombres, pasar adentro, proyecto intacto, unir / evento nuevo) y `probar_arrastre.py` normal y `--dos-eventos` (evento viejo ya terminado → nuevo sin preguntar). Sin probar todavía: un render de verdad con DaVinci (nombres del .mov y del .drt).

## Carpeta del proyecto: solo PROGRAMA y 3 INSTALADORES (1.5.8; 2026-11-16, noche)
- **Pedido:** «en la carpeta solo déjame 2 carpetas: 1 del programa y el otro del instalador».
- **Movido (nada se borró):** `1 MATERIAL` (42 GB) → `PROGRAMA/datos/trabajo/1 MATERIAL`; `2 VIDEOS TERMINADOS/<evento>` y `3 PLANTILLAS EDITABLES/<evento>` → Escritorio `EVENTO TERMINADO - <evento>/VIDEO TERMINADO` y `/PLANTILLAS DE LOS VIDEOS` (BODA 2026-11-07 y XV 2026-11-08, como hace `pasar_adentro` en el instalado); `ARMAR TRAILERS.bat/.command` → `PROGRAMA/herramientas` (`git mv`); el `LEEME.txt` de la raíz era una copia vieja del de `PROGRAMA/config` (`git rm`). `CLAUDE.md` y `.gitignore` con atributo oculto (el Edit le quita el atributo a `CLAUDE.md`: volver a ponerlo).
- **Código:** `rutas._base` desde el código = `PROGRAMA/datos/trabajo` (antes la raíz) y `_salida` = el Escritorio como instalado (antes la raíz). Los lanzadores entran a `PROGRAMA` estén en `herramientas` o junto a `PROGRAMA` (paquete público de Mac); `empaquetar.py` toma la raíz del proyecto de `dirname(rutas.PROGRAMA)` (antes de `rutas.BASE`) y los lanzadores y el LEEME de su nuevo sitio. Los scripts de compilar ya calculaban la raíz por su cuenta.
- Las líneas viejas de DaVinci que usaban `1 MATERIAL` en la raíz quedan con medios sin conexión hasta reenlazar (`motor.reenlazar` busca por nombre en `rutas.fuentes()`).

## Estabilizador propio y enfoque de cine con la IA de profundidad (1.5.7; 2026-11-16, noche)
- **Pedido:** «mira esta opción para estabilizar en Fusion» (`Stabilize-Tracker-Transform-v2.1.1.zip`, script de A. Cooper Video) → «¿sirve o mejor crea algo mejor tú?»; «aprovecha todas las funciones de DaVinci Resolve Studio»; «puedes usar Magic Mask v2 para algunas tomas».
- **Ese script no sirve aquí:** es manual (en cada toma hay que poner el cuadro del tracker o dibujar la forma y apretar sus botones) y su licencia prohíbe incluirlo en otro programa. Se tomó la idea, no el código.
- **`armado/estabilizar.py` (propio, solo numpy):** `calcular` lee el tramo del plano (±0,5 s) chico y en gris con ffmpeg; `movimiento`: 12 tejas, correlación de fase (FFT) en cada una y ajuste robusto de desplazamiento + giro (las tejas que no concuerdan, como la gente que baila, se descartan); camino suavizado con gaussiana de 1 s (`SUAVES_S`: si el zoom no alcanza, 0,6 y 0,35 s; si aun así no, se corrige una parte) y zoom mínimo exacto (`zoom_para`, esquinas del cuadro) hasta `ZOOM_MAX` 1,08. `aplicar`: Transform de Fusion «ESTABILIZADOR» entre MediaIn y MediaOut, Center con XYPath (X e Y con BezierSpline: si no, cada valor pisa al anterior) y Angle con un keyframe por cuadro, Size fijo. Probado sin DaVinci (sintético: desplazamiento y giro exactos; 6 planos reales: temblor 0,18–0,44 → 0,04–0,13 con zoom 4–8 %). `build_trailers.estabilizar(puestos, fps)` mide en paralelo (`ESTAB_PARALELO`) y pone en Fusion; la cámara lenta no se toca (ya se elige firme). Reemplaza a `TimelineItem.Stabilize()`.
- **Probado en DaVinci 21.2:** render de un solo plano y temblor medido cuadro a cuadro sobre el render: 0,159 → 0,018 y 0,257 → 0,076 (zoom 6–7 %). Los clips de 29,97 fps en la línea de 24 van al **80,08 %** (`GetSpeed()`: cada cuadro de la línea es un cuadro de la toma): `estabilizar.velocidad` y el tiempo de cada keyframe = ini + cuadro × velocidad / fps de la línea. El cuadro 0 del comp es el primero del plano; el rango de render que dice Fusion al crearlo no coincide con el plano (0–27 en uno de 37, 0–51 en uno de 45): se ponen keys en todo el plano ±2. **DaVinci reusa lo ya renderizado de un clip**: un comp creado o cambiado por script DESPUÉS de renderizar ese clip no se ve en el siguiente render (ni un zoom simple); en el armado los comps se ponen antes del primer render.
- **«Conformado» no es cámara lenta:** `CONFORMAR_30_A_24` pone `p["vel"] = 0,8` y `p["conformado"]` a las tomas de 29,97 fps (van cuadro a cuadro). Tratarlas como lentas dejó la primera corrida con 0 planos estabilizados y un encadenado en cada corte (34 en el de 1 min): `_lento_de_verdad(p)` en el estabilizador, las transiciones y el enfoque de cine. Con eso: 25 planos estabilizados en el de 1 min (temblor 0,31 → 0,03, zoom medio 5 %) y 20 transiciones.
- **Estorbo según la versión:** en 1 y 3 min el estorbo es duro (`ESTORBO_DURO_HASTA_S` 180, `Planificador.poner_estorbo_duro` limpia las cachés de `vista` y del puntaje): el de 1 min tenía cabezas borrosas tapando una esquina en 0:36. En 15 y 30 min es blando con `PESO_ESTORBO` 0,12 (con 0,35 el de 15 min metía 9 veces en un minuto el hombro borroso con huipil); con 0,12 queda bajo `UMBRAL_PLANO` y se prefiere repetir una toma buena.
- **Rehacer los proyectos por video:** `DeleteProject` da False si el proyecto está cargado, y DaVinci deja cargados en memoria los que se abrieron en la sesión: al rehacer las plantillas no se reemplazaban («no se pudo crear el proyecto»). Ahora cada uno se cierra (`CloseProject`) al exportarlo y `_borrar_proyecto` abre, cierra y borra el que quedó cargado.
- **Proxies:** `editable.proxies_y_cache` dejaba fuera los clips «Video + Audio» (filtro `"audio" not in tipo`): solo hizo 1 de 73 (el dron sin sonido). Ahora solo se saltan los de tipo «Audio».
- **Imagen final:** en 9:16 una foto horizontal se recorta al centro (en la boda salió el padre sin los novios) y la única vertical era una mesa de botanas. `foto_final`: en vertical solo fotos verticales, y si la IA miró las fotos y en ninguna salen los novios ni la festejada (ni DaVinci reconoció a la persona festejada), la imagen final es el mejor plano de video en cámara lenta (`heroe`; en la boda, los novios cortando el pastel).
- **Revisión final:** los cuadros a mitad de una disolvencia (dos imágenes encimadas) salen como «algo pegado al lente»: no es una toma mala.
- **Límite del material (boda 7-nov):** en la iglesia solo hay dos ángulos útiles (el padre leyendo y el altar): en el de 15 min la ceremonia (~4 min) alterna sobre todo esas dos tomas. Más ángulos en la iglesia = ceremonia más variada.
- **Keyframes en bloque:** con un keyframe por llamada (~300 llamadas por plano) el proceso murió sin aviso al estabilizar los ~180 planos del de 15 min (DaVinci seguía vivo). `BezierSpline.SetKeyFrames({cuadro: {1: valor}}, True)`: cada curva de una vez (40 keys en 0,002 s, leídos bien).
- **`repartir_zonas` sin holgura:** con la revisión estricta a ningún momento le sobraba material y la función devolvía el reparto de la plantilla: el de 30 min salía con un capítulo MAQUILLAJE de 52 planos de la fiesta. Ahora el momento sin nada desaparece igual y su tiempo va a los que tienen algo según su material (30 min: MAQUILLAJE 324 → 0, IGLESIA 540 → 639, FIESTA 684 → 909 s).
- **Magic Mask:** no se puede automatizar: sus puntos solo se ponen a mano en el visor (la referencia de Fusion lo dice; `Strokes` no tiene forma de script). **Depth Map:** `armado/profundidad.py` (fondo desenfocado y un poco más oscuro en las tomas protagonistas) queda **apagado** (`ENFOQUE_CINE` False): en DaVinci 21.2 un comp de clip con la herramienta Depth Map no se renderiza (sale el clip sin el comp; ni con el mapa directo a la salida, en modo Better o Faster).
- **Ya se usaban de Studio:** IntelliSearch (caras), transcripción, Speed Warp, Smart Reframe, aislamiento de voz y nivelador de diálogo, reducción de ruido.

## Tomas que no sirven: revisión cuadro por cuadro y «si sale gente, se le ve la cara» (1.5.7; 2026-11-16, tarde)
- **Pedido:** «necesito que el análisis sea mucho mejor: hay tomas que no se ve nada, apuntan al techo; las transiciones tienen un efecto raro, se ven feo; hay tomas que no apuntan a nada, tal vez el error es al estabilizarlo… me estás entregando videos muy mediocres». Y la regla: «si sale un humano debe verse la cara; si sale sin cabeza o algo raro, descartar».
- **Lo que se vio** (hoja de contacto del VIDEO FINAL 1 MIN, 2 cuadros/s, y `rastrear` de cada plano a su toma): 0:29–0:32 `VIDEO VERTICAL 008` = 104 s grabados de cabeza contra el techo (la IA, con 3 cuadros, dijo «decoración floral en escaleras»); 0:35–0:37 un torso con huipil sin cabeza; 0:37–0:43 y 0:51–0:53 bailes del iPhone de noche, barridos y de espaldas, metidos en el horizontal con los lados rellenos (Blanking Fill); disolvencia en cada corte (doble imagen).
- **Por qué pasaban:** la nitidez se medía contra el típico de CADA cámara (el iPhone de noche: 13,7; la cámara principal: 35,7): lo borroso del celular era «normal». `TEMBLOR_MAX` 5 dejaba pasar una de cada diez tomas muy movidas y el estabilizador (desde 0,35: casi todo) recortaba y deformaba. La IA veía 3 cuadros por toma.
- **Revisión cuadro por cuadro** (`vision_ia.INSTANTES_V` 4): TODAS las tomas, un cuadro cada 3 s (`INSTANTES_CADA_S`), respuesta cerrada (`FORMATO_INSTANTE`, «structured outputs» de Ollama): `apunta` (personas | detalle | techo | piso | pared | tapado | equipo | nada), `de_cabeza`, `cara` (se ve la cara de alguien, de frente o de perfil), `sin_cabeza` (persona sin cabeza, solo cuerpo o de espaldas) y `etiquetas`. `motivo_cuadro`: personas sin cara o sin cabeza, de cabeza o cualquier `apunta` que no sea personas/detalle → no sirve. Al dron no se le piden caras (`SOLO_CARAS`). Probado en los cuadros reales del de 1 min: fuera el techo, el huipil y los bailes de espaldas; las buenas pasan. ~0,5–1 s por cuadro (448 px; a 336 px confundía «de cabeza»; de 4 en 4 no es más rápido).
- **En el análisis:** si no sirve la mitad de una toma corta (≤ `TOMA_CORTA_S` 30 s) o el 80 % de una larga, fuera la toma entera (`PARTE_MALA_TOMA` / `PARTE_MALA_LARGA`); como mucho `PARTE_IA_MAX` de los archivos (si no, solo los peores). Con la GPU ocupada por DaVinci no se hace (aviso: cerrar DaVinci antes de ▶).
- **En el armado** (`Planificador.vista`): los tramos que la IA vio malos (medio paso antes y después de cada cuadro) quedan fuera como lo desenfocado; nitidez también contra la MEJOR cámara del evento (`_enfoque_evento`, sin dron): `FOCO_ABS_MIN` 0,55 (`FOCO_ABS_VERTICAL` 0,75 para lo vertical dentro del horizontal); `TEMBLOR_MAX` 5 → 3, `BARRIDO_MAX` 8 → 6, `PESO_TEMBLOR` 0,6; el estabilizador solo entre 0,35 y `TEMBLOR_ESTABILIZAR_MAX` 2,5; `PESO_VERTICAL` 0,85 → 0,5.
- **Cámara lenta:** con Speed Warp (24–30 fps) solo en tomas muy firmes (`LENTO_TEMBLOR_WARP` 0,8, `LENTO_BARRIDO_WARP` 2): con movimiento, los cuadros inventados deforman la imagen.
- **Transiciones:** dentro de cada momento, corte al ritmo; encadenado solo al entrar o salir de una cámara lenta o una foto y entre planos con un salto de luz de `SALTO_LUZ` 0,15 o más; fundido a color entre momentos; `suaves_en` vacío.
- **Revisión final** (`revision_ia`): la misma pregunta y la misma regla; el aviso dice el motivo («0:30 apunta al techo»).
- **Estorbo** (`INSTANTES_V` 5): un hombro con huipil desenfocado tapaba el tercio derecho de `VIDEO HORIZONTAL 014` (salía 4 veces en el de 1 min) y pasaba porque se veía la cara de la señora del micrófono: campo `estorbo` (algo muy cerca del lente, desenfocado, tapando ~¼ o más). Probado: 4 de 5 cuadros del hombro marcados, 8 de 8 limpios pasan. Las etiquetas de cada cuadro quedan solo en `MOMENTOS_CLAVE` (la lista entera alargaba la respuesta: «vestido, traje, zapatos» en todo).
- **Calibración** (muestra al azar de 24 cuadros tirados y 12 aceptados, mirados uno por uno): lo tirado era malo (flash y cámara tapando, jeans, techo, de espaldas, al piso) salvo el dron visto desde arriba («piso»: ahora no cuenta para el dron); lo aceptado, bien.
- **Para revisar a mano:** `python PROGRAMA/herramientas/storyboard.py 1min sb.jpg` (un cuadro de cada plano del plan, sin DaVinci, con los cuadros malos de cada tramo) y la hoja de contacto del video final (`ffmpeg -vf fps=2,scale=240:-2,tile=8x8`).

## Textos, transiciones, estabilidad, SFX, plantilla por video, tiempo estimado y proxies (1.5.7; 2026-11-16)
- **Pedido:** «los captions pasan muy rápido y no están bien distribuidos; las transiciones muy bruscas; mejora la estabilidad; mejora los sfx; si abro la plantilla solo me tiene que dar esa línea de tiempo; que el análisis sea el mejor; que me diga en cuánto tiempo va a estar listo; al entregar, haz los videos en proxy y aplica los render caches».
- **Textos:** `DUR_CAPITULO/FRASE/GRACIAS` 5 / 6 / 6,5 s (antes 3,2 / 4 / 4,5), `SEPARACION_TEXTOS` 4 s, `CADA_FRASE` con menos frases; las frases se reparten en lo que queda del momento DESPUÉS de su capítulo y entran `TRAS_CORTE_S` después del corte.
- **Transiciones:** `VERSIONES[..]["tr"]`: disolvencia en TODOS los cortes de los momentos (`ZONAS_TODAS`; 7/12/18/20 cuadros según la versión), cortita en la apertura (3–6) y fundido a color más largo al cambiar de momento (14–32).
- **Estabilidad:** `UMBRAL_TEMBLOR` 0,6 → 0,35 (se estabiliza mucho más), `PESO_TEMBLOR` en `vista` (las tomas firmes ganan), tope de tiempo del estabilizador `max(300, 4 × planos)`. La API no deja cambiar la fuerza del estabilizador (solo `Stabilize()`).
- **SFX:** objetivos de `mezcla.py` 2–3 dB más bajos (acompañan, no tapan la música); el whoosh entra y sale con fundido.
- **Análisis:** `vision_ia.VERSION` 3 / `INSTANTES_V` 3: la IA responde aparte `equipo` → `util = false` (toma entera o, en las largas, ±4 s con `ia_tramos`). En la boda se colaba la cámara del camarógrafo en 0:28 del de 1 min. La v2 («equipo en primer plano») tiraba 20 tomas buenas (los votos, la salida de la iglesia) por una cámara al fondo o el celular de un invitado; la v3 solo cuenta el equipo PEGADO al lente que tapa buena parte de la imagen o la pantalla de una cámara, y «ante la duda, útil».
- **Tiempo estimado:** `motor.estimar_segundos` (medido en la boda: ~60 min para 73 videos / 29 GB / 4 versiones + vertical) y `texto_tiempo`; la ventana lo dice al soltar la carpeta («estará listo en unos 61 min (listo a las 18:15)») y mientras trabaja (`_poner_eta`: al principio lo calculado, luego cada vez más lo real).
- **Proxies, caché y plantilla por video:** `entrega/editable.py` (lo llama `motor.preparar_edicion` al final de `armar_todo` y de `renderizar_editado`): proxies H.264 de 540 de alto con la GPU (NVENC/VideoToolbox/AMF/QSV, si no x264) por dentro en `BASE/PROXIES`, enlazados con `LinkProxyMedia`; proyecto con `perfProxyMediaMode=1`, `perfRenderCacheMode=smart` y caché automática; y un proyecto por video (export → import con otro nombre en la carpeta <evento> de la base → borrar las demás líneas y los clips que no usa → `VIDEO FINAL 1 MIN.drp` en PLANTILLAS DE LOS VIDEOS, en lugar del .drt). DaVinci vuelve a EVENTOS CINEMA en Edición.
- **GPU compartida:** con DaVinci abierto, la IA local queda en el procesador (5–10 veces más lenta): `vision_ia.en_gpu()`; los instantes se dejan para después y la revisión final mira 30 cuadros en vez de 180. `NUM_CTX` 8192 (Ollama cargaba con 64 mil = 10 GB).

## «Aplica todo» (1.5.7; la persona, 2026-11-16: las 11 mejoras sugeridas)
- **Reenlazar tras renombrar:** `motor.nombres_de_hoy()` sigue toda la lista `nombres.json` (vez por vez, a la vez); `reenlazar` usa `ReplaceClip` con el nombre de hoy y busca también en las carpetas del evento. **Restaurar:** botón «Nombres originales» (Ajustes) → `motor.restaurar_nombres` (vuelve al nombre con que llegó cada archivo; `estado.sin_renombrar` hasta el próximo evento).
- **Cámara reconocida tras renombrar:** `_camara` usa `nombre_original` (lo anota `renombrar_cache` y lo completa `_nombres_originales` desde `nombres.json`): renombrados, todos empezaban con «VIDEO».
- **Reloj por el sonido:** `_sincronizar_por_audio` compara el nivel del audio (medio segundo; `_envolvente`, `_cruce`: correlación ≥ 0,6 con pico claro y ≥ 12 s juntas) de las tomas de reloj dudoso con las de reloj bueno; con 2 que coinciden (±60 s) la cámara entera se pone en hora (`reloj = "audio"`). Boda 7-nov: la cámara en 2018 quedó en hora. Además `simultaneas` (otras cámaras al mismo tiempo; `audio: True` si el sonido lo confirma).
- **Zonas según el material:** `Planificador.capacidad_f` (planos distintos que da el material de un momento con ese corte) y `repartir_zonas`: una zona sin material se achica y lo que sobra va a las que tienen de sobra; un momento sin nada desaparece. Boda: 30 min IGLESIA 540→364 s, FIESTA 684→1184 s; repetidas 104→56.
- **Instantes:** `vision_ia.instantes` (un cuadro cada 8 s de las tomas de más de 20 s; caché `ia.instantes`); `emocion` sube ±3 s alrededor de un instante clave; `ia_tramos` baja ±4 s donde la IA vio algo inútil.
- **Multicámara:** `Planificador.multicamara`: un plano emotivo con otra cámara confirmada por el sonido se parte en dos ángulos en el mismo instante real (máx. 3 por zona); `al_ritmo` corre el segundo ángulo lo mismo que mueve el corte.
- **Foto final e intro:** `foto_final` prefiere la foto donde la IA ve a los DOS novios (o la festejada) y un momento clave; `intro` deja fuera lo inútil y prefiere a los novios si alcanzan.
- **Revisión final:** `entrega/revision_ia.py`: tras el render, la IA mira un cuadro cada 3 s (máx. 180) del video final; lo que no debería ir va al registro y como marcador ROJO «REVISAR (IA)» en la línea de DaVinci.
- **IA local en Ajustes:** recuadro con `vision_ia.estado()`; «Instalar el modelo» (`instalar_modelo`, `ollama pull` por la API) o «Descargar Ollama» (abre ollama.com/download).
- **Líneas = nombre del video:** `rutas.nombre_linea` → «BODA 7 NOVIEMBRE - VIDEO FINAL 1 MIN»; `rutas.etiqueta_de` entiende el nombre de antes y el nuevo (todo lo que leía «1min» pasa por ahí); al rearmar se borra la versión con el nombre de antes.
- **DaVinci trabado en IntelliSearch:** `escenas_ia._con_limite`: si `AnalyzeForIntellisearch` no contesta (90 s + 0,6 × duración), se sigue sin las caras de lo que falta (el 16-nov quedó trabado en «Índice de archivos - Inicializando…» y ni «Cancelar» respondía: hubo que reiniciar DaVinci).

## IA local que VE cada toma (1.5.7; la persona, 2026-11-16)
- **Pedido:** «mejora el análisis: si es iglesia, identifícalo; maquillaje es una mujer maquillándola o tomas del vestido o traje del novio; después ya sería iglesia con familia o en grupos»; «mejora las IAs locales»; «busca en internet el mejor modelo y úsalo»; «que use el máximo rendimiento»; «que entregue un resultado increíble».
- **Por qué:** el análisis por hora y color SIEMPRE repartía tres momentos. En la boda del 7-nov (sin preparativos y con el reloj de la cámara en 2018) la ceremonia salió MAQUILLAJE y el primer baile IGLESIA. La API de Resolve solo da las caras de IntelliSearch: los objetos y escenas no salen al script.
- **Modelo:** Qwen3-VL 8B en Ollama (2026: el más recomendado para correr en la PC; ya instalado: `qwen3-vl:8b-instruct`). `vision_ia.modelo()` elige el mejor modelo con `capabilities: vision` (Qwen3-VL primero), enciende Ollama si está apagado; `TRAILER_VISION_MODELO` lo fuerza. Sin Ollama: todo sigue por hora y color.
- **Qué mira:** 3 cuadros por video (25/50/75 %, 448 px) o la foto (Pillow: con ffmpeg y `-ss` una foto sale vacía). Responde JSON: momento (PREPARATIVOS→MAQUILLAJE, IGLESIA, FIESTA, OTRO), escena, etiquetas (anillos, beso, votos, primer_baile, pastel, brindis, novia, novio…) y `util`. ~4 s por toma en la RTX 5070 Ti (GPU al 93 %): 3 en paralelo para que ffmpeg saque cuadros mientras la GPU mira. Cache «ia» por archivo (sobrevive al renombrado). Más de 200 fotos: solo los videos.
- **Cómo manda:** `clasificar` → `_segun_lo_que_ve` → `_en_orden`: por secuencia (reloj bueno: por hora; reloj dudoso: en el orden de su cámara) el etiquetado MAQUILLAJE ≤ IGLESIA ≤ FIESTA que menos contradice a la IA (contradecirla cuesta 1; cambiar una toma que no vio, 0,3). Si ninguna toma de preparativos se confirma, el evento no tiene MAQUILLAJE (antes el dron sobre la iglesia caía ahí por hora). Lo de reloj dudoso se reparte de nuevo dentro de su momento. `util=false` (piso, pantalla de la cámara, borrosa, a oscuras) → `descartar` (si no es más de la mitad).
- **En el armado:** `Planificador.lo_que_ve` (×1,35 momentos clave, ×1,12 novios/festejada, ×0,3 inútil); `textos_extra` no pone capítulo ni frases de un momento que el evento no tiene. Capturas de la intro: el doble de candidatas y `_quedarse_con_las_mejores` (la IA mira cada una; novios y momentos clave; 2 por momento; las demás a `CAPTURAS/.descartadas`).
- **Resultado en la boda:** 0 maquillaje (no había), 14 iglesia (con el dron), 53 fiesta; 6 tomas inútiles fuera; capturas de votos, salida de la iglesia y novios bailando.

## Material en su carpeta, renombrado, solo JPG, capturas y vertical solo (1.5.7; la persona, 2026-11-16)
- **Pedido:** «solo imágenes JPG; las demás no las tomes en cuenta»; «si hay videos verticales, automáticamente activas las plantillas verticales de un minuto»; «si te arrastran la carpeta, es la ruta donde está: simplemente renombras todos los archivos: dron, video vertical, video horizontal y entre paréntesis maquillaje, ceremonia o fiesta; nunca borres ningún archivo»; «si no hay fotos para la intro, tomas capturas del video». Práctica: `D:\BODA 7 NOVIEMBRE` (73 videos, 2 JPG, 1376 RAW/DNG).
- **En su carpeta:** `Copia.run` con carpetas → `motor.usar_carpeta` (lista en `estado.carpetas`; se une, o empieza evento nuevo si el anterior está terminado). `rutas.fuentes()` = esas carpetas + `rutas.CAPTURAS`; `am.listar` las recorre (sin `ANTERIORES` ni ocultos) y clasifica con `am.tipo_de_archivo`. `am.huella` usa la ruta completa si está en otro disco.
- **Renombrar:** `motor.renombrar_material` en `armar` (tras analizar, antes del plan y de DaVinci): por tipo, numerado por hora, momento IGLESIA → «CEREMONIA». Dos pasos (`~renombrando n`) para poder intercambiar números; un archivo ajeno con ese nombre no se pisa («(2)»). `am.renombrar_cache` mueve lo medido a la clave nueva (nombre|tamaño): no se vuelve a leer ningún video. Nombres viejos en `datos/analisis/nombres.json` (se escribe ANTES de renombrar).
- **Capturas:** con menos de `FOTOS_INTRO` (9) JPG, `motor.capturas_intro` elige por video el medio segundo más nítido (contra el enfoque típico de su cámara) sin quemar, sin barrido, sin temblor y con luz, reparte por turnos maquillaje/ceremonia/fiesta y saca el cuadro con ffmpeg a `CAPTURAS/CAPTURA 001 (CEREMONIA).jpg` con la hora en EXIF (306) y en la fecha del archivo; luego se analiza otra vez (solo las capturas son nuevas).
- **Celular acostado = horizontal** (la persona: «si hay tomas grabadas como horizontal en el móvil, lo pasas como video horizontal, junto con las tomas de la cámara»): `_info_video` decide por ancho, alto y giro (`rotacion` ±90 cambia el sentido), no por el aparato; esas tomas se llaman «VIDEO HORIZONTAL…» y el armado horizontal las usa igual que las de cámara (solo cambia su carpeta del media pool: CELULAR). En la boda del 7 de noviembre los 42 MOV del iPhone eran de pie (3840x2160, giro -90).
- **Vertical solo:** `armar_todo(auto_vertical=True)`: tras el pase horizontal, si `am.leer_ultimo()` tiene videos verticales sin descartar, suma el pase VERTICAL 1min.
- **Probado:** `probar_arrastre.py` normal y `--dos-eventos` (en su carpeta sin copiar, solo JPG, 46 renombrados, ningún archivo borrado, plan de las 4).

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
  - **Ruido de DaVinci (ajuste guardado por la persona)**: la reducción de ruido propia de DaVinci (temporal) limpia mucho más, pero no se puede configurar por API: `TimelineItem.AddEffect("ofx", ...)` agrega «Reducción de ruido» con valores de fábrica, que no hacen nada, y `Effect` no tiene parámetros; un `.drx` lleva el grado en protobuf comprimido (zstd), sin nombres.
    - Solución: la persona deja el ruido a su gusto en un clip (página Color) y pulsa **Ajustes › Ruido de DaVinci › «Guardar el del clip actual»**. `ruido.capturar_de_resolve` toma el clip bajo el cursor (`GetCurrentVideoItem`), captura su grado (`GrabStill` + `ExportStills` a drx, y borra la captura de la galería) y lo guarda en `datos/ruido_davinci/ruido.drx` con un `ruido.json` (clip, fecha y herramientas vistas con `GetToolsInNode`).
    - Al armar, `ruido.aplicar(item, intensidad, medida, drx)` pone ese grado en cada toma (`ApplyGradeFromDRX(drx, 0)`), deja el DCTL del nodo 1 transparente (`XV_RUIDO_N0.dctl`, etiqueta «RUIDO DE DAVINCI») y el armado vuelve a poner el CDL de cada plano (el grado guardado trae el del clip donde se capturó; sin «Igualar», CDL neutro). No se mide el ruido de los videos.
    - «Quitar» borra el ajuste y las tomas vuelven al filtro del programa. Con el ajuste guardado, `motor.aplicar_ruido` no toca las líneas: el cambio llega al volver a armar.
    - Probado en una copia de la línea de 1 min (2026-11-13): el grado de un clip se traslada entero a otro (visto con saturación 0.15), no cambia escala ni zoom y la galería queda como estaba. Falta probarlo con un ajuste de ruido real de la persona y medir el tiempo de render.
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

## Calidad del montaje (1.5.3; la persona, 2026-11-14, tras ver los videos del XV)
Lo que pidió: «hay tomas muy quemadas», «tomas que apuntan al piso», «tomas que nada que ver», «me saturas demasiado los colores», «los cortes entre tomas no es nada fluido», «entre canciones mejora los fundidos», «pule la voz original», «solo los audios importantes… no sonidos y voces randoms», «rellena con fotos para el de 30 minutos o con tomas con dron».
- **Tomas malas** (`analizar_material._vista_cuadros` → `Planificador.vista`): el puntaje `calidad` es relativo al propio video, así que un video entero malo puntuaba como bueno. `vista` trae medidas absolutas por medio segundo: enfoque (contra lo típico de ESA cámara), luces quemadas, cámara torcida o al piso (histograma de orientaciones: `giro` ≥ 25°, `pico` ≥ 0,20, `eje` ≤ 0,16), barrido y temblor. Un video con menos del 15 % útil es accidental y no entra. Los umbrales se validaron mirando hojas de contacto de cada regla.
- **Cada versión elige de todo el material** (`plan.usados = {}` por versión). Antes la de 30 min usaba solo lo que no habían tomado las otras.
- **Relleno**: dron libre → fotos del momento (solo 30 min; zoom dinámico y encadenado) → repetir. Tope del 15 % de dron por zona.
- **Mismo encuadre**: no hay forma fiable de saber por imagen que dos planos son «la misma escena» (probado con dHash y con color por zonas: las distancias de la misma escena y de escenas distintas se solapan). Lo que sí funciona: cuando un video 4K se usa varias veces en una zona, se alterna abierto / acercado ×1,28 (`marcar_acercados`), como dos cámaras.
- **Fluidez**: 30 c/s en línea de 24 → cada plano al 80 % (un cuadro de fuente por cuadro de línea, sin saltos). Los planos con voz sincronizada van al 100 %.
- **Color**: nunca más saturación que la cámara. Medido en el XV: mediana ×0,92 (antes ×1,02 y hasta ×1,30 en dron por el look). Sobreexpuestas: gamma, no pendiente.
- **Voz original**: pasajes de habla de corrido (`escenas_ia.pasajes_de`), pulidos por clip con aislamiento de voz y nivelador de diálogo; la música baja en rampa con una copia en fase en la pista «MUSICA BAJA (voz)». Se comprobó «oyendo» la mezcla final con un transcriptor local: lo elegido era la oración, la lectura bíblica, el brindis y los agradecimientos.
- **Cambio de canción** (`cruces_de_musica`, midiendo el sonido con ffmpeg): si la que sale sigue sonando hasta el corte, se alarga 2,5 s y se apaga en 4 s mientras la que entra sube en 2,5 s (con dos fundidos iguales de 2 s el volumen hacía un hueco de 3 dB). Si la que sale **se acaba antes** (termina sola, se va apagando o es más corta que su sitio en la plantilla) quedaban huecos casi en silencio de 3 a 6 s, uno de 4 s en silencio total en el de 30 min: se retrasa entera para que termine donde entra la otra. Se hace de la última a la primera, así el retraso se acumula hacia atrás, la primera canción (le sobra música) se alarga y la entrada de la música de fiesta no se mueve de su marcador. Adelantar las canciones no sirve: al adelantarse también se adelanta su final y el hueco reaparece en el siguiente cambio.

## IA de DaVinci + la propia (1.5.4; la persona: «utiliza las IAs de DaVinci Resolve Studio en combinación con las tuyas»)
- **Personas** (`escenas_ia.reconocer`): `MediaPoolItem.AnalyzeForIntellisearch(True, False)` SÍ devuelve datos: deja en el metadato «People» las caras del clip o la foto («Rostro 3, Rostro 6»), con el mismo nombre de un archivo a otro. Antes se creía que IntelliSearch no devolvía nada al script. 0,7 s por foto, ~1 s por cada 5 s de video; una vez por evento (caché `datos/analisis/personas.json`).
- **Qué se hace con eso** (`aplicar_personas`, `Planificador.gente`): la festejada es la cara que sale en más archivos (en boda, las dos primeras). Sus tomas pesan ×1,25; las que no tienen a nadie de frente ×0,72 (piso, espaldas, detalles) y pasan a accidentales si sirven menos del 35 %. La intro, el relleno y la foto final se eligen entre las fotos donde sale ella.
- **Quién habla**: cada segmento de la transcripción trae `speaker`. Un pasaje es de quien más habla en él y vale más si esa voz es la que más habla en todo el evento (el pastor, quien da el discurso).
- **Final** (`foto_final`): la mejor foto de ella con zoom lento y la tarjeta en el tercio inferior. **Textos**: velo bajo los títulos de la plantilla (son macros, no se pueden rediseñar). **SFX propios** sintetizados (`herramientas/hacer_sfx.py`) en la pista «SFX MOMENTOS».
- **Verticales** (Ajustes): entran recortados y `TimelineItem.SmartReframe()` sigue a la persona. Sin probar con material real (el XV de prueba no tenía verticales).
- **Revisar sin ver el video entero**: `python PROGRAMA/herramientas/revisar_video.py hoja|cuadros|audio`.
- **Ojo**: el scratchpad se borra si la PC se reinicia (pasó a media sesión con una actualización de Windows): lo que se vaya a volver a usar va en `herramientas/`.

## Formatos horizontal y vertical (1.5.5; la persona, 2026-11-16: «que acepte videos verticales y horizontales, y créale otro apartado solo para videos verticales con los mismos tiempos que solo acepte verticales»)
- **Inicio**: dos filas de pastillas, `HORIZONTAL` y `VERTICAL`, cada una con 1, 3, 15, 30 min y «Todas». Siempre queda al menos una pastilla encendida entre las dos filas. Estado: `versiones` (horizontal; puede ir vacía), `versiones_vertical`, `usar_verticales`.
- **Horizontal (16:9)**: entran los videos horizontales y los verticales (de fábrica; Ajustes › «En el formato horizontal, usar también los videos verticales» lo apaga). El vertical entra **entero** (ajustado al alto) con los lados llenos de su propia imagen ampliada y desenfocada: `vestir_verticales` le pone el ResolveFX Blanking Fill con `TimelineItem.AddEffect("ofx", id)` (API de la 21) y `Scaling = SCALE_FIT`; a esos planos no se les acerca ni se les estabiliza. Recortado para llenar (lo de antes) perdía 2/3 de la imagen y dejaba primerísimos planos. El id y el nombre del efecto cambian con el idioma («Resolve FX/ResolveFX – Estilizado/Relleno» en español): se busca por nombre (`RELLENO_LADOS`); si no está, queda recortado + Smart Reframe. A igual toma gana la horizontal (`PESO_VERTICAL`). Si casi todas las fotos son verticales, la intro se completa con ellas.
- **Vertical (9:16)**: `motor.armar(formato="vertical")` → `FORMATO` en `build_trailers`. Solo videos con `horizontal=False`; fotos verticales (si no llegan a 9, se completan con horizontales recortadas). Hace falta al menos tanto video vertical como dura la versión (`VERTICAL_MATERIAL_MIN = 1.0`; medido: con 17 min de video la de 30 repetía la mitad de los planos): si no alcanza, esa versión no se arma y lo dice en el plan previo, sin abrir DaVinci.
- **Línea**: `«<evento> - VERTICAL 1min»` = duplicado de la misma plantilla, puesto en 1080×1920 con ajustes propios (`poner_vertical`: `useCustomSettings`, resolución y salida, `scaleToCrop`). Plantillas y proyecto no cambian. Los textos nuevos van sobre `TEXTO_VERTICAL.png` (1080×1920) para componerse ya en 9:16.
- **Títulos de la plantilla en 9:16** (`titulos_a_vertical`): las macros mWedding («MIS XV», las frases de la intro) llevan un `mLetterbox`; con `Mode = 1` (llenar) salen tres veces más grandes y cortados por los lados, con `Mode = 0` (ajustar) caben. En la línea vertical se pasan todos a 0 y el clip se agranda ×1,5 (`ZOOM_TITULO_VERTICAL`). Solo se pide a Fusion `GetToolList(False, "Letterbox")`.
- **Render**: `armar_todo` hace un pase por formato y un solo render con las etiquetas armadas (`"1min"`, `"VERTICAL 1min"`); el trabajo vertical lleva `FormatWidth/FormatHeight` de la línea y después la página Entrega vuelve al tamaño horizontal.
- **Prueba**: la de arrastre comprueba que el video vertical se reconoce, que con uno solo el formato vertical avisa, y que con todo en vertical planifica `VERTICAL 1min`. `revisar_video.py` hace hojas de videos verticales.

## Plantilla editable (1.5.5; la persona, 2026-11-16: «en cada proyecto terminado me dejes la plantilla editable por si no me gusta algo»)
- **Dónde queda**: las líneas del evento siguen en el proyecto `EVENTOS CINEMA` (`02 EVENTOS/<evento>`); al terminar —con o sin render— DaVinci queda en la página Edición con la más corta abierta (`motor.dejar_editable`). Además, una copia por versión en `3 PLANTILLAS EDITABLES/<evento>/<línea>.drt` con un `LEEME.txt` — carpeta propia de la carpeta de trabajo (`rutas.EDITABLES`), aparte de `2 VIDEOS TERMINADOS` (la persona, 2026-11-16: «una carpeta con los videos finales y otra con las plantillas editables»); `rutas.crear_carpetas()` la crea desde el primer arranque, en Windows y en Mac — (se importa con Archivo › Importar › Línea de tiempo).
- **Editar en DaVinci** (botón de Inicio): `motor.abrir_editable` abre DaVinci en esa línea y lo trae al frente.
- **Renderizar lo editado** (botón de Inicio): `motor.renderizar_editado` vuelve a poner en cola cada línea tal como está (`encolar_render`; las verticales, del tamaño de la línea), renderiza, masteriza a −14 LUFS y actualiza el `.drt`. No arma nada: lo retocado a mano se conserva (probado el 2026-11-16 apagando un título a mano: salió sin él y lo demás igual).
- **Tramo que se renderiza**: tras un render la línea no conserva marcas (`GetMarkInOut()` devuelve `{'video': {}, 'audio': {}}`), así que sin marcas sale la duración de siempre de esa versión (`motor.SEGUNDOS`, o hasta el final si la persona acortó la línea); si la persona pone entrada y salida (I / O), se respeta eso.
- **▶ rearma desde cero** y reemplaza las líneas. Por eso, si el evento ya está armado con el mismo material (`estado.huella == motor.huella()`), ▶ pregunta: «Renderizar lo editado» (por defecto), «Volver a armar» o «Cancelar». El armado automático tras soltar material nuevo no pregunta.
- Los dos botones se ven siempre que haya un evento armado (`_chips_editable`), no solo al acabar.

## Abrir al instante (1.5.3; la persona: «le di instalar y tardó bastante… todo debe ser inmediato»)
- **Instalador**: con el programa (560 MB) pegado al .exe, el antivirus de Windows lo revisaba entero antes de dejarlo arrancar: 7,7 s sin ver nada. Ahora el .exe pesa 1 MB (ventana a los 0,7 s) y el programa va en el `.dat` de al lado. Sin autoprueba ni espera al terminar: abre el programa y se queda hasta que se ve.
- **Programa**: Qt tarda ~1 s en su primera ventana (arma la lista de fuentes de la PC). `trailer_xv._portada_nativa` pone `recursos/portada.bmp` con una ventanita de Windows (clase STATIC, ctypes) antes de cargar Qt: se ve a los 0,3 s. `TRAILER_TIEMPOS=1` anota cada fase del arranque en el registro.
- **Ojo en Git Bash**: `/silencioso` y `/noabrir` se convierten en rutas (`C:/Program Files/Git/silencioso`) y el instalador corre con ventana. Lanzarlo desde PowerShell.

## Arranque y fluidez (1.5.6; la persona, 2026-11-16: «que no tenga tiempo de carga y máxima fluidez en la interfaz y al arrancar»)
Medido en esta PC (628 familias de fuentes), con `TRAILER_TIEMPOS=1` (marcas `_tiempo` en el registro) y arneses en el scratchpad:
- **Librerías**: ya estaban al día (Python 3.14, PySide6 6.12, numpy 2.5, Pillow 13, PyInstaller 6.22, ffmpeg 9); solo había tres parches menores. El tiempo de carga no era de versiones.
- **Fuentes: era casi todo el tiempo de carga.** La primera vez que Qt mide un texto arma la lista de fuentes (0,2 s). Y si un estilo pide una **lista** de familias o un texto trae un símbolo que su fuente no tiene (✓ ☰ ✕ ▶ ⤓ ⚠ ✎, emojis), prepara todas las de reserva (0,4 s más). Lo disparaban el panel de registro —oculto— por su `font-family: "Cascadia Mono", "Consolas", …` y los símbolos de la barra y las pastillas.
  - El estilo lleva **una** familia: `primera_que_hay()` elige con `QFontDatabase.hasFamily` la primera de la lista que existe (lo mismo que resolvía la lista).
  - Al abrir no se pinta ningún símbolo de esos: palomita y lápiz dibujados (`icono_trazo`), y `≡ × ► ↓`, que sí están en Segoe UI. Para saber si un carácter está: `QRawFont.fromFont(f).supportsCharacter(ord(c))` (con `str` siempre dice que no).
  - `calentar_fuentes()` prepara la lista y las de reserva en un hilo que llama a Qt **por ctypes** (`QFontMetrics::horizontalAdvance(QChar)` de `Qt6Gui.dll`): desde Python (`QFontMetrics`, `QFontDatabase.families()`) el hilo retiene el candado y la ventana se para igual. Las de reserva se piden con la ventana ya visible.
  - No se usó el motor `fontengine=gdi` (lista en 0,008 s): cambia el grosor de las negritas de Segoe UI Variable.
- **Antes de la ventana**: `numpy` y Pillow se cargan al primer uso (`_AlUsar` en `analizar_material`; el motor los importaba al abrir: 80 ms). El icono de la ventana se lee de `recursos/icono.ico` (lo hace `hacer_portada.py`; dibujarlo en 7 tamaños costaba 0,12 s). Mientras cargan las fuentes se importa el código de la escena.
- **Ojo**: `widget.setVisible(True)` sobre un widget que aún no está en una ventana crea una ventanita suelta (0,15 s y un parpadeo). Los botones nacen ocultos y se muestran al final de `__init__`.
- **Fluidez**: en Material la línea del día (388 archivos) se redibujaba entera 13 veces por segundo porque el cielo de fondo parpadea y arrastra a lo que tiene encima. Ahora `LineaDia` se pinta una vez en una imagen (`_imagen`, se rehace al cambiar datos, tamaño, límites o ratón) y `Cielo` guarda su fondo (`_fondo`). El análisis se lee de un resumen ligero (`material_ventana.json`, `leer_ultimo`) y `revisar_material` corre en otro hilo.
- **Abrirlo dos veces**: trae al frente la ventana que ya hay (`_traer_la_abierta`), sin cuadro «ya está abierto».
- **Resultado (código, en caliente)**: ventana visible 1,08 → 0,63 s; primer cuadro 1,21 → 0,78 s; portada 0,13 → 0,09 s. Tirones > 25 ms en Material 5 → 2, al revisar material 3 → 0, al cargar la organización 5 → 1.
- **Lo que queda**: mostrar la ventana (pulir ~200 widgets, 0,16 s) y el primer cuadro de la escena (texturas, 0,14 s; código de CineCaptions, no se toca). Maximizada, la escena se pinta por software y cada cuadro cuesta más.

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
- **No recorrer las composiciones Fusion de los títulos de la plantilla (macros mWedding, MultiText: miles de herramientas) desde el `run_script` del MCP de DaVinci**, que corta a los 10–60 s: visto el 2026-11-16, al cortarse a media llamada DaVinci quedó sin responder más de 25 min (hubo que cerrarlo a mano), y además era en una línea que no era la activa. Eso se hace desde un proceso propio (`motor.conectar_resolve`), con la línea activa y pidiendo solo el tipo de herramienta que hace falta (`GetToolList(False, "TextPlus")`).
- Las fotos entran con duración fija: colócalas una a una y recórtalas con `SetRightOffset`. Los videos de 29.97 fps quedan 1 frame cortos: ajústalos después de colocarlos.
- `ImportMedia` con una lista simple de rutas.
- Las transiciones aparecen como elementos de la pista: fíltralas con `GetMediaPoolItem() is None`.
- `get_image` tiene un límite de 10 s. Si falla, revisa la VRAM con `nvidia-smi` y el registro `ResolveDebug.txt`.
- Otras sesiones o programas (Premiere) pueden estar usando la GPU y Resolve al mismo tiempo.
- Si lanzas el armado mientras Resolve todavía está arrancando con el Organizador de proyectos, `LoadProject` puede abrir el proyecto y aun así dejar colgado al script (proceso sin CPU). Espera a que Resolve muestre el proyecto o ábrelo antes; si el registro no avanza en 5 min, mata el proceso y relánzalo con `python -u ... *> log`.
- El velo de los títulos usa `EllipseMask` con SoftEdge moderado (0.16), que no causa problemas. Lo peligroso es solo la herramienta Shadow.
