// (1.7) El interruptor verde: la perilla se desliza y la pista se tiñe. (1.7.8, Liquid Glass) La pista es de VIDRIO
// (verde con resplandor encendido, cristal claro apagado) y la perilla una perla con luz arriba y sombra suave.
import QtQuick
import QtQuick.Effects

Item {
    id: i
    property real escala: 0.6
    property bool si: false
    property bool v: si             // lo que se ve: cambia al instante con el clic; si (de Python) lo pone al dia
    onSiChanged: v = si
    signal cambiado(bool si)
    function px(v) { return Math.round(v * escala) }
    width: px(96); height: px(52)

    Vidrio {
        anchors.fill: parent
        radio: height / 2
        tinte: i.v ? "#22C47E" : "white"
        tinteA: i.v ? 0.85 : 0.10
        brillo: "#22C47E"; brilloA: i.v ? 0.35 : 0
        filo: i.v ? 1.0 : 0.7
        encima: zona.containsMouse
        apretado: zona.pressed
    }
    Rectangle {
        id: perilla
        width: parent.height - px(10); height: width; radius: width / 2
        y: px(5)
        x: i.v ? i.width - width - px(5) : px(5)
        Behavior on x { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#FFFFFF" }
            GradientStop { position: 1.0; color: "#DCE4E7" }
        }
        scale: zona.pressed ? 0.9 : 1
        Behavior on scale { NumberAnimation { duration: 120 } }
        layer.enabled: true
        layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.5; shadowOpacity: 0.4; shadowVerticalOffset: 2 }
    }
    MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
        onClicked: { i.v = !i.v; i.cambiado(i.v) } }
}
