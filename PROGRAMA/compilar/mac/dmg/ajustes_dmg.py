# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/dmg/ajustes_dmg.py — la ventana del .dmg (dmgbuild), igual que la de CineCaptions 5.91: «Arrástralo a Aplicaciones»,
# el programa a la izquierda de la flecha y la carpeta Aplicaciones a la derecha, sin barras. Lo usa construir_mac.sh:
#   dmgbuild -s ajustes_dmg.py -D stage=<carpeta> -D fondo=<fondo.tiff> -D icono=<.icns> "<volumen>" <salida.dmg>
# El fondo (fondo.png + fondo@2x.png -> fondo.tiff con tiffutil) lo dibuja fondo_dmg.py: 600 x 360 puntos. Las coordenadas de los
# iconos son su CENTRO, en puntos, desde arriba a la izquierda. El fondo es CLARO: asi el Finder escribe los nombres en negro.
#
# Desde la 1.5.2 (la persona, 2026-11-14: «así hazlo en Mac», con la captura del disco de CineCaptions): ya no hay un .pkg que abrir
# (instalar en /Applications con un .pkg SIEMPRE pide la contrasena de la Mac). El disco trae la app y el enlace a Aplicaciones:
# arrastrar no pide contrasena. Lo que hacia el .pkg lo hace el programa al abrirse (tareas.primer_arranque).
#
# El paquete OCULTO (nombre con punto: el Finder no lo ensena) es para las Mac que instalaron con el .pkg (hasta la 1.5.1): su
# servicio de root busca un *.pkg en el disco y lo instala con `installer -target /`. Ese paquete no trae la app: su postinstall
# la copia de este mismo disco.
#
# Desde la 1.5.7 (la persona, 2026-11-16: «que funcione el instalador como este en Mac», con el de CineSlide 9.62) el disco de la
# persona es «Doble clic para instalar» (-D modo=instalador): solo la app «Instalar Trailer automatico», centrada, que abre la
# ventana nativa del instalador (compilar/mac/instalador). El de «Arrástralo a Aplicaciones» queda para el disco PÚBLICO de las
# actualizaciones: las versiones 1.5.2 a 1.5.6 buscan TrailerAutomatico.app en la raíz del disco.
import os

stage = defines['stage']                                   # noqa: F821 (lo pone dmgbuild)
MODO = defines.get('modo', 'arrastrar')                    # noqa: F821  instalador | arrastrar
# nombres SIN tildes (como CineCaptions): con tildes, HFS+ los guarda en NFD y mac_alias/.DS_Store no los casan
APP = 'TrailerAutomatico.app'
INSTALADOR = 'Instalar Trailer automatico.app'
PKG_OCULTO = '.Actualizar Trailer automatico.pkg'

format = 'UDZO'
filesystem = 'HFS+'
files = [os.path.join(stage, APP), os.path.join(stage, PKG_OCULTO)]
symlinks = {'Aplicaciones': '/Applications'}
hide_extensions = [APP]
icon = defines.get('icono') or None                        # noqa: F821
background = defines['fondo']                              # noqa: F821
window_rect = ((240, 300), (600, 388))                     # 360 del fondo + 28 de la barra del titulo (macOS 15)
default_view = 'icon-view'
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = False
arrange_by = None
icon_size = 104
text_size = 12
icon_locations = {
    APP: (185, 168),                                       # a la izquierda de la flecha (x 258-342, y 168)
    'Aplicaciones': (415, 168),                            # a la derecha
    PKG_OCULTO: (560, 250),                                # (oculto; si alguien ensena los ocultos, que no tape nada)
}

if MODO == 'instalador':                                   # «Doble clic para instalar» (fondo_instalar.png)
    files = [os.path.join(stage, INSTALADOR), os.path.join(stage, PKG_OCULTO)]
    symlinks = {}
    # SIN ocultar la extension (dmgbuild lo hace con SetFile: com.apple.FinderInfo en la app firmada); el Finder no ensena
    # «.app» de todos modos. La firma rota de la primera prueba era por los nombres con tildes en HFS+: por eso el programa va
    # en un .zip dentro del instalador (construir_mac.sh), y construir_mac.sh comprueba la firma con el disco montado.
    hide_extensions = []
    icon_size = 128
    text_size = 13
    icon_locations = {
        INSTALADOR: (300, 160),                            # en el centro del halo (fondo_dmg.dibujar_instalar)
        PKG_OCULTO: (560, 250),
    }
