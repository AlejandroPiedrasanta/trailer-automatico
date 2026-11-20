// (1.7, la persona: «QML / Qt Quick por partes») La barra del Inicio: el nombre | Plantillas | Tráiler.
// La pinta la tarjeta grafica: el foco de luz que sigue al raton, el brillo que cruza el boton verde y el resorte al
// apretar van a 60 por segundo sin repintar la ventana. Python (barra_qml.py) pone nombre, tam y radio, y escucha las
// señales nombreClic / plantillasClic / trailerClic.
import QtQuick
import QtQuick.Shapes

Item {
    id: raiz
    property string nombre: "Pon el nombre"
    property string ayudaNombre: ""
    property string familia: "Segoe UI"
    property int tam: 18            // letra (px de piezas.px(36))
    property int radio: 20          // esquinas (dock_r)
    property int icono: 23
    signal nombreClic()
    signal plantillasClic()
    signal trailerClic()

    // entra subiendo y aclarandose
    opacity: 0
    transform: Translate { id: subir; y: 14 }
    Component.onCompleted: entrada.start()
    ParallelAnimation {
        id: entrada
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
        NumberAnimation { target: subir; property: "y"; to: 0; duration: 520; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
    }

    // el vidrio de la barra (igual al panel de antes: degradado verde noche y filo claro)
    Rectangle {
        id: fondo
        anchors.fill: parent
        radius: raiz.radio
        border.width: 1
        border.color: Qt.rgba(140 / 255, 215 / 255, 200 / 255, 0.38)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(24 / 255, 56 / 255, 60 / 255, 0.92) }
            GradientStop { position: 1.0; color: Qt.rgba(10 / 255, 28 / 255, 34 / 255, 0.92) }
        }
    }

    Row {
        anchors.fill: parent
        Segmento {
            width: raiz.width * 0.44; height: raiz.height
            lado: "izq"; texto: raiz.nombre; iconoNombre: "lapiz"; iconoColor: "EBCB8F"; alinear: "izq"
            onClic: raiz.nombreClic()
        }
        Rectangle { width: 1; height: raiz.height; color: Qt.rgba(140 / 255, 215 / 255, 200 / 255, 0.30) }
        Segmento {
            width: raiz.width * 0.28 - 1; height: raiz.height
            lado: "medio"; texto: "Plantillas"; iconoNombre: "claqueta"; iconoColor: "EEF3F4"
            onClic: raiz.plantillasClic()
        }
        Rectangle { width: 1; height: raiz.height; color: Qt.rgba(140 / 255, 215 / 255, 200 / 255, 0.30) }
        Segmento {
            width: raiz.width * 0.28 - 1; height: raiz.height
            lado: "der"; texto: "Tráiler"; iconoNombre: "play"; iconoColor: "FFFFFF"; verde: true
            onClic: raiz.trailerClic()
        }
    }

    component Segmento: Item {
        id: seg
        property string lado: "medio"
        property string texto: ""
        property string iconoNombre: ""
        property string iconoColor: "FFFFFF"
        property string alinear: "centro"
        property bool verde: false
        signal clic()
        clip: true

        // la forma: las esquinas redondas solo hacia afuera de la barra (lo de dentro sigue en el vecino)
        Item {
            id: forma
            x: seg.lado === "izq" ? 0 : -raiz.radio
            width: seg.width + (seg.lado === "medio" ? 2 * raiz.radio : raiz.radio)
            height: seg.height

            Rectangle {      // el verde del Tráiler
                anchors.fill: parent
                anchors.margins: 1
                radius: raiz.radio - 1
                visible: seg.verde
                gradient: Gradient {
                    GradientStop { position: 0.0; color: zona.containsMouse ? "#4FE6A1" : "#44D894" }
                    GradientStop { position: 1.0; color: zona.containsMouse ? "#22B97A" : "#1FA971" }
                }
            }
            Rectangle {      // al pasar el raton: el segmento se aclara suave
                anchors.fill: parent
                anchors.margins: 1
                radius: raiz.radio - 1
                color: "white"
                opacity: zona.containsMouse ? (seg.verde ? 0.0 : 0.045) : 0.0
                Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            }
        }

        // el foco de luz que sigue al raton
        Shape {
            anchors.fill: parent
            opacity: zona.containsMouse ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 260 } }
            ShapePath {
                strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: zona.mouseX; centerY: zona.mouseY
                    focalX: zona.mouseX; focalY: zona.mouseY
                    centerRadius: seg.height * 1.6; focalRadius: 0
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, seg.verde ? 0.20 : 0.10) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
                }
                PathRectangle { x: 0; y: 0; width: seg.width; height: seg.height }
            }
        }

        // el brillo que cruza el boton verde cada pocos segundos
        Rectangle {
            id: brillo
            visible: seg.verde
            width: seg.height * 0.9; height: seg.height * 2.2
            y: -seg.height * 0.6
            rotation: 18
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.30) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
            SequentialAnimation on x {
                running: seg.verde && seg.visible
                loops: Animation.Infinite
                NumberAnimation { from: -seg.height * 1.5; to: seg.width + seg.height; duration: 1400; easing.type: Easing.InOutQuad }
                PauseAnimation { duration: 2600 }
            }
        }

        Row {
            id: contenido
            spacing: raiz.tam * 0.7
            anchors.verticalCenter: parent.verticalCenter
            x: seg.alinear === "izq" ? raiz.tam * 2 : (seg.width - width) / 2
            scale: zona.pressed ? 0.96 : 1.0
            Behavior on scale { SpringAnimation { spring: 5; damping: 0.28 } }
            Image {
                anchors.verticalCenter: parent.verticalCenter
                width: raiz.icono; height: raiz.icono
                source: "image://icono/" + seg.iconoNombre + "/" + seg.iconoColor + "/" + raiz.icono
                sourceSize: Qt.size(raiz.icono * 4, raiz.icono * 4)
                smooth: true
                // el icono da un pasito al pasar el raton
                transform: Translate { x: zona.containsMouse ? (seg.verde ? 3 : 0) : 0
                    Behavior on x { SpringAnimation { spring: 4; damping: 0.3 } } }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: seg.texto
                color: "#F1F5F6"
                font.family: raiz.familia; font.pixelSize: raiz.tam
                font.weight: seg.verde ? Font.DemiBold : Font.Normal
                elide: Text.ElideRight
                width: Math.min(implicitWidth, seg.width - raiz.icono - raiz.tam * 4)
            }
        }

        MouseArea {
            id: zona
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: seg.clic()
        }
    }
}
