// (1.7.7) Fondo vivo del programa: la nebulosa esmeralda (nebulosa.frag) en la tarjeta de video.
// La ventana (Python) pone «cuadros» (30 en uso, 10 sin foco, 0 minimizada). A resolucion completa: a media las
// estrellas de un pixel se borraban (visto en la captura) y a 30 cuadros la tarjeta casi no lo nota.
import QtQuick

Item {
    id: raiz
    property int cuadros: 30
    property real brillo: 1.0
    property real tiempo: 0

    ShaderEffect {
        anchors.fill: parent
        property real t: raiz.tiempo
        property real aspecto: raiz.height > 0 ? raiz.width / raiz.height : 1.6
        property real brillo: raiz.brillo
        fragmentShader: "nebulosa.frag.qsb"
    }

    // por TIEMPO, no por pasos: el mismo movimiento a 10 o a 30 cuadros
    property double _ultimo: 0
    Timer {
        interval: raiz.cuadros > 0 ? Math.round(1000 / raiz.cuadros) : 1000
        running: raiz.cuadros > 0 && raiz.visible
        repeat: true
        onTriggered: {
            var ahora = Date.now()
            if (raiz._ultimo > 0)
                raiz.tiempo += Math.min(0.2, (ahora - raiz._ultimo) / 1000)
            raiz._ultimo = ahora
        }
        onRunningChanged: raiz._ultimo = 0
    }
}
