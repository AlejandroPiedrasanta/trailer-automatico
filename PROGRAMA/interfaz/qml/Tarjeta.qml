// (1.7) La tarjeta de vidrio de las paginas: icono dorado, titulo, una raya y lo de adentro. Al pasar el raton el filo
// se aclara suave. Medidas de la maqueta (2048 de ancho) por `escala`.
import QtQuick

Rectangle {
    id: t
    property real escala: 0.6
    property string familia: "Segoe UI"
    property string titulo: ""
    property string icono: ""
    default property alias contenido: cuerpo.data
    function px(v) { return Math.round(v * escala) }

    radius: px(28)
    border.width: 1
    border.color: zona.containsMouse ? Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.45) : Qt.rgba(1, 1, 1, 0.12)
    Behavior on border.color { ColorAnimation { duration: 220 } }
    gradient: Gradient {
        GradientStop { position: 0; color: Qt.rgba(20 / 255, 44 / 255, 50 / 255, 0.86) }
        GradientStop { position: 1; color: Qt.rgba(8 / 255, 22 / 255, 28 / 255, 0.90) }
    }
    implicitHeight: px(40) + cab.height + px(28) + cuerpo.implicitHeight + px(40)

    // (1.8.4) entrada escalonada: la pagina llama entrar(i) al mostrarse; cada tarjeta sube y aparece 45 ms despues
    // de la anterior (con movimiento reducido no se mueve)
    transform: Translate { id: sube }
    function entrar(i) {
        if (typeof quieto !== "undefined" && quieto) return
        llega.stop(); opacity = 0; sube.y = px(22); espera.duration = 60 + i * 45; llega.start()
    }
    SequentialAnimation {
        id: llega
        PauseAnimation { id: espera; duration: 60 }
        ParallelAnimation {
            NumberAnimation { target: t; property: "opacity"; to: 1; duration: 300; easing.type: Easing.OutCubic }
            NumberAnimation { target: sube; property: "y"; to: 0; duration: 420; easing.type: Easing.OutQuint }
        }
    }

    MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }

    Row {
        id: cab
        x: px(44); y: px(40)
        spacing: px(26)
        Image {
            visible: t.icono !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: px(54); height: width
            source: t.icono ? "image://icono/" + t.icono + "/E2B04F/" + width : ""
            sourceSize: Qt.size(width * 4, height * 4)
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: t.titulo; color: "white"
            font.family: t.familia; font.pixelSize: t.px(50); font.weight: Font.Bold
        }
    }
    Rectangle { x: px(44); y: cab.y + cab.height + px(14); width: t.width - px(88); height: 1; color: Qt.rgba(1, 1, 1, 0.10) }
    Column {
        id: cuerpo
        x: px(44); y: cab.y + cab.height + px(28)
        width: t.width - px(88)
        spacing: px(18)
    }
}
