# Tráiler automático · CINEMA PRODUCTIONS
# compilar/mac/dmg/ajustes_dmg.py — la ventana del .dmg (dmgbuild), como la de CineCaptions: fondo con los dos pasos, donde va cada
# icono y sin barras. Lo usa construir_mac.sh:
#   dmgbuild -s ajustes_dmg.py -D stage=<carpeta> -D fondo=<fondo.tiff> -D icono=<.icns> "<volumen>" <salida.dmg>
# El fondo (fondo.png + fondo@2x.png -> fondo.tiff con tiffutil) lo dibuja fondo_dmg.py: 660 x 460 puntos. Las coordenadas de los
# iconos son su CENTRO, en puntos, desde arriba a la izquierda. El fondo es CLARO: asi el Finder escribe los nombres en negro.
import os

stage = defines['stage']                                   # noqa: F821 (lo pone dmgbuild)
PKG = 'Instalar Tráiler automático.pkg'
DESINSTALAR = 'Desinstalar Tráiler automático.command'

format = 'UDZO'
filesystem = 'HFS+'
files = [os.path.join(stage, PKG), os.path.join(stage, DESINSTALAR)]
symlinks = {'Aplicaciones': '/Applications'}
hide_extensions = [PKG, DESINSTALAR]
icon = defines.get('icono') or None                        # noqa: F821
background = defines['fondo']                              # noqa: F821
window_rect = ((200, 280), (660, 488))                     # 460 del fondo + 28 de la barra del titulo
default_view = 'icon-view'
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = False
arrange_by = None
icon_size = 72
text_size = 12
icon_locations = {
    PKG: (165, 232),                                       # tarjeta 1: «Doble clic para instalar»
    'Aplicaciones': (495, 232),                            # tarjeta 2: «Ábrelo desde Aplicaciones»
    DESINSTALAR: (575, 400),                               # pie, a la derecha de los consejos
}
