// (1.7) El interruptor verde: la perilla se desliza con resorte y la pista se tiñe.
import QtQuick

Rectangle {
    id: i
    property real escala: 0.6
    property bool si: false
    property bool v: si             // lo que se ve: cambia al instante con el clic; si (de Python) lo pone al dia
    onSiChanged: v = si
    signal cambiado(bool si)
    function px(v) { return Math.round(v * escala) }
    width: px(96); height: px(52); radius: height / 2
    color: v ? "#22C47E" : Qt.rgba(1, 1, 1, 0.16)
    Behavior on color { ColorAnimation { duration: 200 } }
    Rectangle {
        id: perilla
        width: parent.height - px(10); height: width; radius: width / 2
        y: px(5)
        x: i.v ? i.width - width - px(5) : px(5)
        Behavior on x { SpringAnimation { spring: 4; damping: 0.32 } }
        color: "white"
        scale: zona.pressed ? 0.9 : 1
        Behavior on scale { NumberAnimation { duration: 120 } }
    }
    MouseArea { id: zona; anchors.fill: parent; cursorShape: Qt.PointingHandCursor
        onClicked: { i.v = !i.v; i.cambiado(i.v) } }
}
