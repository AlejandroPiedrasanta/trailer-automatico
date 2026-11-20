// (1.7, la persona: «QML / Qt Quick por partes») La barra del Inicio: el nombre | Plantillas | Tráiler.
// La pinta la tarjeta grafica: el foco de luz que sigue al raton, el brillo que cruza el boton verde y el resorte al
// apretar van a 60 por segundo sin repintar la ventana. Python (barra_qml.py) pone nombre, tam y radio, y escucha las
// señales nombreClic / plantillasClic / trailerClic.
import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: raiz
    property string nombre: "Pon el nombre"
    property string ayudaNombre: ""
    property string familia: "Segoe UI"
    property int tam: 18            // letra (px de piezas.px(36))
    property int radio: 20          // esquinas (dock_r)
    property int icono: 23
    // (1.8.5, la persona: «puedo seleccionar los dos, plantillas y tráiler») cada uno se ENCIENDE (vidrio verde)
    // cuando esta elegido y dice debajo que lleva; para empezar: el centro o «Empezar»
    property bool plantillasOn: false
    property string plantillasDetalle: ""
    property bool trailerOn: true
    property string trailerDetalle: ""
    signal nombreClic()
    signal plantillasClic()
    signal trailerClic()

    // entra subiendo y aclarandose
    opacity: 0
    transform: Translate { id: subir; y: 14 }
    Component.onCompleted: entrada.start()
    ParallelAnimation {
        id: entrada
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 240; easing.type: Easing.OutCubic }   // (1.8.4) 420 -> 240
        NumberAnimation { target: subir; property: "y"; to: 0; duration: 320; easing.type: Easing.OutQuint }
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
    // (1.7.8, Liquid Glass) el mismo color de siempre, con la luz y el filo del cristal encima
    // (1.8.4) sin la luz que sigue al raton: la barra ya tiene su foco y un disco desenfocado de su tamaño era caro
    Vidrio { anchors.fill: parent; radio: raiz.radio; tinteA: 0; filo: 0.7; luz: false }

    Row {
        anchors.fill: parent
        Segmento {
            width: raiz.width * 0.44; height: raiz.height
            lado: "izq"; texto: raiz.nombre; iconoNombre: "lapiz"; alinear: "izq"
            onClic: raiz.nombreClic()
        }
        Rectangle { width: 1; height: raiz.height; color: Qt.rgba(140 / 255, 215 / 255, 200 / 255, 0.30) }
        Segmento {
            width: raiz.width * 0.28 - 1; height: raiz.height
            lado: "medio"; texto: "Plantillas"; iconoNombre: "claqueta"
            verde: raiz.plantillasOn; detalle: raiz.plantillasDetalle
            onClic: raiz.plantillasClic()
        }
        Rectangle { width: 1; height: raiz.height; color: Qt.rgba(140 / 255, 215 / 255, 200 / 255, 0.30) }
        Segmento {
            width: raiz.width * 0.28 - 1; height: raiz.height
            lado: "der"; texto: "Tráiler"; iconoNombre: "play"
            verde: raiz.trailerOn; detalle: raiz.trailerDetalle
            onClic: raiz.trailerClic()
        }
    }

    component Segmento: Item {
        id: seg
        property string lado: "medio"
        property string texto: ""
        property string iconoNombre: ""
        property string iconoColor: seg.verde ? "04150D" : (seg.lado === "izq" ? "EBCB8F" : "EEF3F4")   // (1.7.8) oscuro en verde: se lee
        property string detalle: ""         // (1.8.5) lo elegido, chiquito debajo del titulo
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

            Rectangle {      // el verde del Tráiler (1.7.8: ahora es la pastilla de vidrio de abajo)
                anchors.fill: parent
                anchors.margins: 1
                radius: raiz.radio - 1
                visible: false
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

        // (1.7.8, Liquid Glass) el Tráiler: una pastilla de VIDRIO verde dentro de la barra, con su resplandor y el
        // destello que la cruza cada pocos segundos (recortado a la pastilla)
        Item {
            id: pastillaT
            // (1.8.5) se enciende y se apaga con un resorte (antes estaba siempre)
            opacity: seg.verde ? 1 : 0
            scale: seg.verde ? 1 : 0.9
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            Behavior on scale { NumberAnimation { duration: 340; easing.type: (typeof quieto !== "undefined" && quieto) ? Easing.OutQuad : Easing.OutBack; easing.overshoot: 1.8 } }
            anchors.fill: parent
            anchors.margins: Math.round(seg.height * 0.11)
            Vidrio {
                anchors.fill: parent
                radio: height / 2
                tinte: "#22C47E"; tinteA: 0.86
                brillo: "#22C47E"; brilloA: 0.55
                filo: 1.0
                encima: zona.containsMouse
                apretado: zona.pressed
            }
            Item {
                anchors.fill: parent
                layer.enabled: pastillaT.visible
                layer.effect: MultiEffect { maskEnabled: true; maskSource: mascaraT }
                Rectangle {
                    width: pastillaT.height * 0.9; height: pastillaT.height * 2.2
                    y: -pastillaT.height * 0.6
                    rotation: 18
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.38) }
                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
                    }
                    SequentialAnimation on x {
                        running: seg.verde && seg.visible && (typeof quieto === "undefined" || !quieto)   // (1.8.4)
                        loops: Animation.Infinite
                        NumberAnimation { from: -pastillaT.height * 1.5; to: pastillaT.width + pastillaT.height; duration: 1400; easing.type: Easing.InOutQuad }
                        PauseAnimation { duration: 2600 }
                    }
                }
            }
            Item { id: mascaraT; anchors.fill: parent; layer.enabled: pastillaT.visible; visible: false
                Rectangle { anchors.fill: parent; radius: height / 2 } }
        }

        // el foco de luz que sigue al raton
        Shape {
            anchors.fill: parent
            opacity: zona.containsMouse ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
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

        Row {
            id: contenido
            spacing: raiz.tam * 0.7
            anchors.verticalCenter: parent.verticalCenter
            x: seg.alinear === "izq" ? raiz.tam * 2 : (seg.width - width) / 2
            scale: zona.pressed ? 0.96 : 1.0
            Behavior on scale { NumberAnimation { duration: zona.pressed ? 90 : 300; easing.type: zona.pressed || (typeof quieto !== "undefined" && quieto) ? Easing.OutQuad : Easing.OutBack; easing.overshoot: 2.2 } }
            Image {
                anchors.verticalCenter: parent.verticalCenter
                width: raiz.icono; height: raiz.icono
                source: "image://icono/" + seg.iconoNombre + "/" + seg.iconoColor + "/" + raiz.icono
                sourceSize: Qt.size(raiz.icono * 4, raiz.icono * 4)
                smooth: true
                // el icono da un pasito al pasar el raton
                transform: Translate { x: zona.containsMouse ? (seg.verde ? 3 : 0) : 0
                    Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } } }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: raiz.tam * 0.05
                Text {
                    text: seg.texto
                    // (1.7.8, auditoria) en verde, texto oscuro; «Pon el nombre» vacio se ve como invitacion (apagado),
                    // y ya puesto, como dato
                    readonly property bool invita: seg.lado === "izq" && seg.texto.indexOf("Pon ") === 0
                    color: seg.verde ? "#04150D" : (invita ? "#8FA3A8" : "#F1F5F6")
                    Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
                    font.family: raiz.familia; font.pixelSize: raiz.tam
                    font.weight: seg.verde || (seg.lado === "izq" && !invita) ? Font.DemiBold : Font.Normal
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, seg.width - raiz.icono - raiz.tam * 4)
                }
                Text {           // (1.8.5) lo elegido: «2 plantillas», «Horizontal y vertical»
                    visible: seg.detalle !== ""
                    text: seg.detalle
                    color: seg.verde ? "#0B3A24" : "#9DB0B6"
                    Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
                    font.family: raiz.familia; font.pixelSize: Math.round(raiz.tam * 0.66)
                    font.weight: Font.Medium
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, seg.width - raiz.icono - raiz.tam * 4)
                }
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
