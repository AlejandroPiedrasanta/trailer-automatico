// (1.7.8, la persona: «mantén el mismo diseño, solo aplica a los botones Liquid Glass modernos», con referencias de
// botones de vidrio estilo Apple) El fondo de VIDRIO de un boton: cuerpo translucido (deja ver la nebulosa), luz que
// entra arriba y se junta abajo (el grosor del cristal), un filo de luz brillante arriba y abajo, resplandor de color
// en los principales y, al apretar, se oscurece y se hunde. Va DEBAJO del texto y el icono de cada boton.
// Uso: Vidrio { anchors.fill: parent; radio: height / 2; tinte: "#22C47E"; tinteA: 0.82; brillo: "#22C47E"; ... }
import QtQuick
import QtQuick.Effects

Item {
    id: v
    property real radio: height / 2
    property color tinte: "white"
    property real tinteA: 0.07          // cuanto color tiene el cristal (0 = transparente)
    property real filo: 0.85            // fuerza del filo de luz
    property color brillo: "transparent"
    property real brilloA: 0            // resplandor de color alrededor (los principales)
    property bool encima: false         // raton encima: un poco mas de luz
    property bool apretado: false       // apretado: se oscurece por dentro
    property bool ocupado: false        // (1.8.4) trabajando: cristal esmerilado con una luz que lo recorre despacio
    readonly property bool _quieto: typeof quieto !== "undefined" && quieto

    // resplandor de color (debajo del cristal)
    Rectangle { id: halo; anchors.fill: parent; radius: v.radio; color: v.brillo; visible: false }
    MultiEffect {
        anchors.fill: parent; source: halo
        visible: opacity > 0.001                  // (1.8.4) se apaga fundiendose, no de golpe
        blurEnabled: true; blur: 1.0; blurMax: 40; autoPaddingEnabled: true
        opacity: Math.min(1, v.brilloA * (v.encima ? 1.35 : 1) * (v.apretado ? 0.7 : 1))
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    // el cuerpo: color del cristal + luz interior (el degradado ya queda dentro de las esquinas redondas)
    Rectangle {
        anchors.fill: parent; radius: v.radio
        color: v.tinte
        Behavior on color { ColorAnimation { duration: 170; easing.type: Easing.OutCubic } }   // (1.8.4) sin salto verde/blanco
        opacity: Math.min(1, v.tinteA + (v.encima ? 0.06 : 0))
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    }
    Rectangle {
        anchors.fill: parent; radius: v.radio
        gradient: Gradient {
            GradientStop { position: 0.00; color: Qt.rgba(1, 1, 1, 0.30) }
            GradientStop { position: 0.42; color: Qt.rgba(1, 1, 1, 0.04) }
            GradientStop { position: 0.70; color: Qt.rgba(1, 1, 1, 0.00) }
            GradientStop { position: 1.00; color: Qt.rgba(1, 1, 1, 0.14) }
        }
    }
    // el reflejo de la lente: una franja curva arriba, por dentro del borde
    Rectangle {
        x: Math.max(2, v.radio * 0.45); y: 2
        width: v.width - 2 * x; height: v.height * 0.36
        radius: Math.min(v.radio, height / 2)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.26) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.00) }
        }
    }
    // (1.8.4, la persona: «pule más los botones y la fluidez») el GROSOR del cristal: la luz se junta abajo por dentro
    Rectangle {
        anchors.fill: parent; radius: v.radio
        gradient: Gradient {
            GradientStop { position: 0.55; color: Qt.rgba(0, 0, 0, 0.0) }
            GradientStop { position: 1.00; color: Qt.rgba(0, 0, 0, 0.16) }
        }
    }
    // (1.7.8) la luz que SIGUE al raton por el cristal y la onda de luz al apretar (recortadas a la forma)
    HoverHandler { id: hv }
    property real _ox: width / 2
    property real _oy: height / 2
    onApretadoChanged: if (apretado) { _ox = hv.point.position.x || width / 2; _oy = hv.point.position.y || height / 2; onda.restart() }
    // (1.8.4, fluidez) la capa con mascara y desenfoque EXISTE solo mientras hace falta (raton encima, onda, ocupado):
    // antes cada boton tenia su textura fuera de pantalla todo el tiempo
    property bool luz: true             // (1.8.4) la luz que sigue al raton (la barra de Inicio no la usa)
    readonly property bool _luz: (v.luz && hv.hovered) || onda.running || v.ocupado
    Item {
        anchors.fill: parent
        visible: v._luz || brillo.opacity > 0.01
        layer.enabled: visible
        layer.effect: MultiEffect { maskEnabled: true; maskSource: forma }
        // el reflejo que sigue al cursor
        Rectangle {
            id: brillo
            width: Math.max(v.height * 2.2, v.width * 0.6); height: width; radius: width / 2
            x: hv.point.position.x - width / 2; y: hv.point.position.y - height / 2
            opacity: v.luz && hv.hovered && !v._quieto ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            gradient: Gradient {        // un disco de luz: se arma con un degradado radial de mentira (anillos)
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.0) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
            }
            Rectangle { anchors.centerIn: parent; width: parent.width * 0.75; height: width; radius: width / 2; color: Qt.rgba(1, 1, 1, 0.05) }
            Rectangle { anchors.centerIn: parent; width: parent.width * 0.45; height: width; radius: width / 2; color: Qt.rgba(1, 1, 1, 0.06) }
            Rectangle { anchors.centerIn: parent; width: parent.width * 0.22; height: width; radius: width / 2; color: Qt.rgba(1, 1, 1, 0.07) }
            layer.enabled: opacity > 0.01
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 32 }
        }
        // (1.8.4) ocupado: una franja de luz cruza el cristal despacio (se anima por fraccion, no por pixeles)
        Rectangle {
            id: franja
            property real f: 0
            visible: v.ocupado && !v._quieto
            width: v.height * 1.6; height: v.height * 2; y: -v.height / 2
            x: -width + f * (v.width + width)
            rotation: 18
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.0) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.22) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
            }
            NumberAnimation on f { running: franja.visible; from: 0; to: 1; duration: 1600; loops: Animation.Infinite; easing.type: Easing.InOutSine }
        }
        // la onda al apretar
        Rectangle {
            id: ondaR
            x: v._ox - width / 2; y: v._oy - height / 2
            width: 0; height: width; radius: width / 2
            color: Qt.rgba(1, 1, 1, 0.30)
            opacity: 0
        }
        ParallelAnimation {
            id: onda
            NumberAnimation { target: ondaR; property: "width"; from: v.height * 0.4; to: Math.max(v.width, v.height) * 2.4; duration: 520; easing.type: Easing.OutCubic }
            NumberAnimation { target: ondaR; property: "opacity"; from: 0.9; to: 0; duration: 520; easing.type: Easing.OutQuad }
        }
    }
    Item { id: forma; anchors.fill: parent; layer.enabled: v._luz || brillo.opacity > 0.01; visible: false
        Rectangle { anchors.fill: parent; radius: v.radio; antialiasing: true } }

    // apretado: la luz se va hacia adentro
    Rectangle {
        anchors.fill: parent; radius: v.radio
        color: "black"
        opacity: v.apretado ? 0.14 : 0
        Behavior on opacity { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    }
    // el filo de luz: brillante arriba, se apaga al medio, vuelve abajo
    Rectangle {
        anchors.fill: parent; radius: v.radio
        opacity: v.filo * (v.encima ? 1 : 0.85)
        gradient: Gradient {
            GradientStop { position: 0.00; color: Qt.rgba(1, 1, 1, 0.95) }
            GradientStop { position: 0.32; color: Qt.rgba(1, 1, 1, 0.22) }
            GradientStop { position: 0.68; color: Qt.rgba(1, 1, 1, 0.10) }
            GradientStop { position: 1.00; color: Qt.rgba(1, 1, 1, 0.60) }
        }
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: anillo }
    }
    Item {
        id: anillo; anchors.fill: parent; layer.enabled: true; visible: false
        Rectangle { anchors.fill: parent; radius: v.radio; color: "transparent"; border.width: 1.5; border.color: "white"; antialiasing: true }
    }
}
