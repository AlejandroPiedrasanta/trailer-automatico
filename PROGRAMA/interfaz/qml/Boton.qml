// (1.7) Boton con icono opcional: se aclara al pasar el raton, se hunde al apretar y el icono da una vuelta si `girar`.
// (1.7.8, la persona: «botones Liquid Glass modernos») De VIDRIO (Vidrio.qml), en pastilla: el principal es vidrio
// verde con su resplandor y texto oscuro; los demas, cristal claro con filo de luz. La misma API de siempre.
import QtQuick

Item {
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
    // (1.7.8) del ancho NATURAL del texto (no del de la fila: el texto se acorta con el boton y eso era un circulo)
    implicitWidth: (ic.visible ? ic.width + fila.spacing : 0) + txt.implicitWidth + px(64)
    implicitHeight: px(84)
    opacity: activo ? 1 : 0.5
    scale: zona.pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

    Vidrio {
        anchors.fill: parent
        radio: height / 2
        tinte: b.principal ? "#22C47E" : "white"
        tinteA: b.principal ? 0.80 : 0.07
        brillo: "#22C47E"; brilloA: b.principal ? 0.45 : 0
        filo: b.principal ? 1.0 : 0.8
        encima: zona.containsMouse
        apretado: zona.pressed
    }
    Row {
        id: fila
        anchors.centerIn: parent
        spacing: px(16)
        Image {
            id: ic
            visible: b.icono !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: px(44); height: width
            source: b.icono ? "image://icono/" + b.icono + (b.principal ? "/04150D/" : "/F1F5F6/") + width : ""
            sourceSize: Qt.size(width * 4, height * 4)
            RotationAnimation on rotation { id: vuelta; running: false; from: 0; to: 360; duration: 650; easing.type: Easing.InOutCubic }
        }
        Text {
            id: txt
            anchors.verticalCenter: parent.verticalCenter
            // (1.7.8) nunca mas ancho que el boton: «Buscar actualizaciones» tocaba el borde
            width: Math.min(implicitWidth, b.width - b.px(64) - (ic.visible ? ic.width + fila.spacing : 0))
            // (1.7.9) si no cabe, primero se achica la letra (hasta px(26)); solo despues se corta con «…»
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: b.px(24)
            elide: Text.ElideNone           // (con «…» el corte ganaba al achicado)
            text: b.texto; color: b.principal ? "#04150D" : "#F1F5F6"
            font.family: b.familia; font.pixelSize: b.px(34); font.weight: b.principal ? Font.Bold : Font.DemiBold
        }
    }
    MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; enabled: b.activo
        cursorShape: Qt.PointingHandCursor
        onClicked: { if (b.girar) vuelta.restart(); b.clic() } }
}
