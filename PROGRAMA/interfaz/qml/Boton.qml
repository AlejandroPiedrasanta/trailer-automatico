// (1.7) Boton de borde dorado (o verde si es el principal) con icono opcional: se aclara al pasar el raton, se hunde
// al apretar y el icono da una vuelta si `girar`.
import QtQuick

Rectangle {
    id: b
    property real escala: 0.6
    property string familia: "Segoe UI"
    property string texto: ""
    property string icono: ""
    property bool principal: false
    property bool girar: false
    property bool activo: true
    signal clic()
    function px(v) { return Math.round(v * escala) }
    implicitWidth: fila.implicitWidth + px(60)
    implicitHeight: px(84)
    radius: px(14)
    opacity: activo ? 1 : 0.5
    color: principal ? "transparent" : (zona.containsMouse ? Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.14) : Qt.rgba(1, 1, 1, 0.04))
    Behavior on color { ColorAnimation { duration: 160 } }
    border.width: 1
    border.color: principal ? "#44D894" : (zona.containsMouse ? "#F1CB7A" : Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.6))
    gradient: principal ? verde : null
    Gradient { id: verde
        GradientStop { position: 0; color: zona.containsMouse ? "#3BE3A0" : "#2BD08C" }
        GradientStop { position: 1; color: zona.containsMouse ? "#16A068" : "#118A57" } }
    scale: zona.pressed ? 0.97 : 1
    Behavior on scale { SpringAnimation { spring: 5; damping: 0.3 } }
    Row {
        id: fila
        anchors.centerIn: parent
        spacing: px(16)
        Image {
            id: ic
            visible: b.icono !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: px(44); height: width
            source: b.icono ? "image://icono/" + b.icono + "/F1F5F6/" + width : ""
            sourceSize: Qt.size(width * 4, height * 4)
            RotationAnimation on rotation { id: vuelta; running: false; from: 0; to: 360; duration: 650; easing.type: Easing.InOutCubic }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: b.texto; color: "#F1F5F6"
            font.family: b.familia; font.pixelSize: b.px(34); font.weight: b.principal ? Font.Bold : Font.Normal
        }
    }
    MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; enabled: b.activo
        cursorShape: Qt.PointingHandCursor
        onClicked: { if (b.girar) vuelta.restart(); b.clic() } }
}
