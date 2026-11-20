// (1.7, parte 4) Pagina Plantillas: las plantillas de video (Reels, TikTok, CapCut). (1.7.8, la persona: «aplica lo
// mismo para Plantilla», como el carrusel de Tráilers) Las portadas 9:16 en CARRUSEL: la del centro es la que se mira
// (clic en una de los lados, arrastrar o la rueda) y debajo dice su nombre, sus planos y «Usar en el tráiler» / «Usada».
// Se pueden usar VARIAS (cada una sale como un video mas): las usadas llevan su palomita aunque esten a un lado.
// Soltar un video encima = convertirlo en plantilla. Python (PaginaQML) pone d = {lista: [{nombre, portada, dur,
// planos}], marcadas, opciones: [{clave, texto, si}]} y hace accion("marcar"|"opcion"|"agregar").
import QtQuick

Item {
    id: raiz
    // (1.8.4, auditoria) la pagina se ve (barra_qml.PaginaQML.sincronizar): sin esto sus animaciones infinitas
    // seguian con la pestaña escondida
    property bool activa: true
    property real escala: 0.6
    property string familia: "Segoe UI"
    property var d: ({})
    signal accion(string nombre, var valor)
    signal soltado(var urls)
    // las listas solo se renuevan si cambian (si no, el carrusel rehace las portadas)
    property var listaL: []
    property var opcionesL: []
    onDChanged: {
        if (JSON.stringify(d.lista || []) !== JSON.stringify(listaL)) listaL = d.lista || []
        if (JSON.stringify(d.opciones || []) !== JSON.stringify(opcionesL)) opcionesL = d.opciones || []
    }
    function px(v) { return Math.round(v * escala) }
    // (1.8.4) con movimiento reducido entra solo fundiendose (sin deslizar); «entro» avisa a las piezas que
    // escalonan su entrada (antes se animaban al crearse la pagina, escondida, y nunca se veia)
    signal entro()
    onEntro: if (carrusel.visible) carrusel.forceActiveFocus()     // (1.8.5) las flechas mueven el carrusel
    function entrar(dx) { var q = typeof quieto !== "undefined" && quieto
        opacity = 0; baja.x = q ? 0 : (dx || 0) * px(60); baja.y = (q || dx) ? 0 : px(14); entra.restart(); entro() }   // (1.7.8) dx: +1 entra desde la derecha (pestaña de mas adelante), -1 desde la izquierda
    transform: Translate { id: baja }
    ParallelAnimation { id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 280; easing.type: Easing.OutQuint }
        NumberAnimation { target: baja; property: "x"; to: 0; duration: 300; easing.type: Easing.OutQuint } }

    readonly property var lista: listaL
    readonly property var marcadas: d.marcadas || []
    function usada(i) { return i >= 0 && i < lista.length && marcadas.indexOf(lista[i].nombre) >= 0 }
    function nombreBonito(n) { return (n || "").replace(/_/g, " ") }
    implicitHeight: col.implicitHeight + px(30)

    Column {
        id: col
        width: Math.min(parent.width - px(120), px(1700))
        anchors.horizontalCenter: parent.horizontalCenter
        y: px(24)
        spacing: px(12)

        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Plantillas de video"; color: "white"
            font.family: raiz.familia; font.pixelSize: px(72); font.weight: Font.Bold }
        Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#9DB0B6"
            text: raiz.lista.length
                  ? "Opcional: cada plantilla que uses sale como un video más, con sus cortes y su música."
                  : "Opcional: suelta aquí un Reel, TikTok o CapCut y sale un video más con sus cortes y su música."
            font.family: raiz.familia; font.pixelSize: px(30) }
        // el rotulo, las opciones y «Agregar plantilla»
        Item {
            width: col.width; height: agregar.height
            Seccion { anchors.verticalCenter: parent.verticalCenter; texto: "Tus plantillas"; icono: "pelicula" }
            Boton {
                id: agregar
                anchors.right: parent.right
                escala: raiz.escala; familia: raiz.familia
                texto: "Agregar plantilla"; icono: "carpeta"; principal: true
                onClic: raiz.accion("agregar", 0)
            }
        }
        Flow {
            width: col.width
            spacing: px(40)
            visible: raiz.lista.length > 0          // (auditoria) sin plantillas, las opciones aun no sirven
            Repeater {
                model: raiz.opcionesL
                Row {
                    spacing: px(18)
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.texto; color: "#F1F5F6"
                        font.family: raiz.familia; font.pixelSize: px(32) }
                    Interruptor { anchors.verticalCenter: parent.verticalCenter; escala: raiz.escala; si: modelData.si
                        onCambiado: (si) => raiz.accion("opcion", { "clave": modelData.clave, "si": si }) }
                }
            }
            Text { text: "Todo apagado: la plantilla tal cual."; color: "#9DB0B6"
                font.family: raiz.familia; font.pixelSize: px(28); height: px(52); verticalAlignment: Text.AlignVCenter }
        }

        // ---------------------------------------------------------------- sin plantillas: la invitacion a soltar
        Rectangle {
            id: zonaVacia
            visible: raiz.lista.length === 0
            width: col.width; height: px(520)
            radius: px(32); color: soltar.containsDrag ? Qt.rgba(59 / 255, 238 / 255, 159 / 255, 0.06) : Qt.rgba(1, 1, 1, 0.02)
            Behavior on color { ColorAnimation { duration: 220 } }
            border.width: px(3); border.color: soltar.containsDrag ? "#3BEE9F" : Qt.rgba(1, 1, 1, 0.10 + 0.08 * zonaVacia.resp)
            Behavior on border.color { ColorAnimation { duration: 200 } }
            // (1.8.4) el borde respira despacio mientras espera; al arrastrar un video encima, la zona crece con resorte
            readonly property bool _quieto: typeof quieto !== "undefined" && quieto
            property real resp: 0
            SequentialAnimation on resp { loops: Animation.Infinite; running: raiz.activa && zonaVacia.visible && !zonaVacia._quieto
                NumberAnimation { to: 1; duration: 1800; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0; duration: 1800; easing.type: Easing.InOutSine } }
            scale: soltar.containsDrag && !_quieto ? 1.015 : 1
            Behavior on scale { SpringAnimation { spring: 3.5; damping: 0.32; epsilon: 0.0005 } }
            Column {
                anchors.centerIn: parent
                spacing: px(22)
                Image { anchors.horizontalCenter: parent.horizontalCenter; width: px(100); height: width
                    source: "image://icono/pelicula/" + (soltar.containsDrag ? "3BEE9F" : "9DB0B6") + "/" + width
                    sourceSize: Qt.size(width * 4, height * 4)
                    // (1.8.4) flota con Translate: animar «y» dentro de una Column choca con la Column (se quedaba quieta)
                    transform: Translate { id: flota; y: 0 }
                    SequentialAnimation { loops: Animation.Infinite; running: raiz.activa && zonaVacia.visible && !zonaVacia._quieto
                        NumberAnimation { target: flota; property: "y"; to: -px(10); duration: 1400; easing.type: Easing.InOutSine }
                        NumberAnimation { target: flota; property: "y"; to: 0; duration: 1400; easing.type: Easing.InOutSine } } }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#F1F5F6"
                    text: "Suelta aquí un video"; font.family: raiz.familia; font.pixelSize: px(40); font.weight: Font.DemiBold }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#9DB0B6"
                    text: "Reel, TikTok o CapCut: se copian sus cortes y su música"
                    font.family: raiz.familia; font.pixelSize: px(30) }
            }
        }

        // ---------------------------------------------------------------- el carrusel de portadas 9:16
        // (1.8.5, la persona: «el slider más grande») portadas de 350 x 622 (antes 290 x 516; mas grandes ya no cabe
        // la pagina en la ventana de 1240 x 860 y salia barra de desplazamiento) y las de los lados
        // mas presentes; las flechas del teclado ya llegan (el carrusel toma el foco al tocarlo o al entrar)
        PathView {
            id: carrusel
            objectName: "carrusel"
            visible: raiz.lista.length > 0
            width: col.width; height: visible ? px(650) : 0
            focus: true
            activeFocusOnTab: true
            model: raiz.lista
            // (1.8.5) siempre un numero impar a la vista: con 4, la del centro y una a cada lado (con 4 a la vista
            // quedaba chueco: dos a la izquierda, una a la derecha)
            pathItemCount: count >= 5 ? 5 : (count === 4 ? 3 : Math.max(1, count))
            preferredHighlightBegin: 0.5; preferredHighlightEnd: 0.5
            highlightRangeMode: PathView.StrictlyEnforceRange
            highlightMoveDuration: 320
            interactive: count > 1
            function ir(i) { forceActiveFocus(); if (i >= 0 && i < count && i !== currentIndex) currentIndex = i }
            Keys.onLeftPressed: ir((currentIndex - 1 + count) % count)
            Keys.onRightPressed: ir((currentIndex + 1) % count)
            // (1.8.5) Enter o espacio: usar / dejar la del centro
            Keys.onReturnPressed: raiz.accion("marcar", (raiz.lista[currentIndex] || {}).nombre || "")
            Keys.onEnterPressed: raiz.accion("marcar", (raiz.lista[currentIndex] || {}).nombre || "")
            Keys.onSpacePressed: raiz.accion("marcar", (raiz.lista[currentIndex] || {}).nombre || "")

            // (1.8.5) con 3 a la vista, el camino mas corto: las de los lados junto a la del centro (no en las orillas)
            readonly property real orilla: pathItemCount >= 5 ? 0 : width * 0.16
            path: Path {
                startX: carrusel.orilla; startY: carrusel.height / 2
                PathAttribute { name: "esc"; value: 0.70 }
                PathAttribute { name: "opa"; value: 0.42 }
                PathAttribute { name: "capa"; value: 0 }
                PathLine { x: carrusel.width / 2; y: carrusel.height / 2 }
                PathAttribute { name: "esc"; value: 1.0 }
                PathAttribute { name: "opa"; value: 1.0 }
                PathAttribute { name: "capa"; value: 10 }
                PathLine { x: carrusel.width - carrusel.orilla; y: carrusel.height / 2 }
                PathAttribute { name: "esc"; value: 0.70 }
                PathAttribute { name: "opa"; value: 0.42 }
                PathAttribute { name: "capa"; value: 0 }
            }
            delegate: Portada {
                dato: modelData
                centro: PathView.isCurrentItem
                usada: raiz.marcadas.indexOf(modelData.nombre) >= 0
                scale: PathView.esc === undefined ? 1 : PathView.esc
                opacity: PathView.opa === undefined ? 1 : PathView.opa
                z: PathView.capa === undefined ? 0 : PathView.capa
                onTocar: { carrusel.forceActiveFocus(); if (centro) raiz.accion("marcar", modelData.nombre); else carrusel.ir(index) }
            }
        }

        // lo de la del centro: nombre, planos y usarla o dejarla
        Item {
            visible: raiz.lista.length > 0
            id: infoCentro
            width: col.width; height: visible ? px(120) : 0
            readonly property var actual: raiz.lista[carrusel.currentIndex] || ({})
            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: px(8)
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: px(26)
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: raiz.nombreBonito(infoCentro.actual.nombre); color: "white"
                            font.family: raiz.familia; font.pixelSize: px(40); font.weight: Font.Bold
                            font.capitalization: Font.Capitalize; elide: Text.ElideRight; width: Math.min(implicitWidth, col.width * 0.5) }
                        Text { text: (infoCentro.actual.planos || 0) + " planos · "
                                     + Math.round(infoCentro.actual.dur || 0) + " s"
                            color: "#9DB0B6"; font.family: raiz.familia; font.pixelSize: px(28) }
                    }
                    Boton {
                        anchors.verticalCenter: parent.verticalCenter
                        escala: raiz.escala; familia: raiz.familia
                        principal: raiz.usada(carrusel.currentIndex)
                        icono: raiz.usada(carrusel.currentIndex) ? "palomita" : "check"
                        texto: raiz.usada(carrusel.currentIndex) ? "Usada en el tráiler" : "Usar en el tráiler"
                        onClic: raiz.accion("marcar", (raiz.lista[carrusel.currentIndex] || {}).nombre || "")
                    }
                }
            }
        }

        // los puntos: donde esta la del centro (y en verde las usadas)
        Row {
            visible: raiz.lista.length > 1
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: px(12)
            Repeater {
                model: carrusel.count
                Rectangle {
                    height: px(12); radius: height / 2
                    width: index === carrusel.currentIndex ? px(44) : px(12)
                    color: index === carrusel.currentIndex ? "#3BEE9F"
                         : (raiz.usada(index) ? Qt.rgba(59 / 255, 238 / 255, 159 / 255, 0.55) : Qt.rgba(1, 1, 1, 0.25))
                    Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                    Behavior on color { ColorAnimation { duration: 220 } }
                    MouseArea { anchors.fill: parent; anchors.margins: -px(8); cursorShape: Qt.PointingHandCursor
                        onClicked: carrusel.ir(index) }
                }
            }
        }
    }

    // la rueda, sobre el carrusel (solo la rueda: el arrastre y los clics siguen llegando a las portadas)
    MouseArea {
        visible: carrusel.visible
        x: col.x + carrusel.x; y: col.y + carrusel.y
        width: carrusel.width; height: carrusel.height
        acceptedButtons: Qt.NoButton
        property real _acum: 0
        onWheel: function(ev) {
            _acum += ev.angleDelta.y !== 0 ? ev.angleDelta.y : -ev.angleDelta.x
            if (Math.abs(_acum) < 120) return
            var paso = _acum > 0 ? -1 : 1
            _acum = 0
            carrusel.ir((carrusel.currentIndex + paso + carrusel.count) % carrusel.count)
        }
    }

    // soltar videos en cualquier parte de la pagina: se convierten en plantillas
    DropArea {
        id: soltar
        anchors.fill: parent
        onDropped: (drop) => { if (drop.hasUrls) { raiz.soltado(drop.urls); drop.accept() } }
    }
    Rectangle {
        anchors.fill: parent; anchors.margins: px(30)
        radius: px(40); color: Qt.rgba(34 / 255, 196 / 255, 126 / 255, 0.10)
        border.width: px(4); border.color: "#3BEE9F"
        opacity: soltar.containsDrag ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Text { anchors.centerIn: parent; text: "Suelta para convertirlo en plantilla"; color: "white"
            font.family: raiz.familia; font.pixelSize: px(48); font.weight: Font.Bold }
    }

    component Seccion: Row {
        property string texto: ""
        property string icono: ""
        spacing: px(18)
        Image { anchors.verticalCenter: parent.verticalCenter; width: px(34); height: width
            source: "image://icono/" + parent.icono + "/E2B04F/" + width; sourceSize: Qt.size(width * 4, height * 4) }
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.texto; color: "#E2B04F"
            font.family: raiz.familia; font.pixelSize: px(30); font.weight: Font.DemiBold
            font.capitalization: Font.AllUppercase; font.letterSpacing: px(4) }
    }

    // ------------------------------------------------------------------ una plantilla: portada 9:16
    component Portada: Item {
        id: c
        property var dato: ({})
        property bool centro: false
        property bool usada: false
        signal tocar()
        width: px(350); height: px(622)
        HoverHandler { id: hvP }

        Item {
            id: incl
            anchors.fill: parent
            // (1.7.8) se inclina hacia el raton (perspectiva) y vuelve suave al salir
            property real _ry: hvP.hovered && !_quieto ? (hvP.point.position.x / Math.max(1, width) - 0.5) * -14 : 0
            property real _rx: hvP.hovered && !_quieto ? (hvP.point.position.y / Math.max(1, height) - 0.5) * 10 : 0
            readonly property bool _quieto: typeof quieto !== "undefined" && quieto
            Behavior on _ry { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            Behavior on _rx { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            transform: [
                // (1.8.0) con el id: dentro de Rotation `_ry` a secas no existe (no se inclinaba nunca)
                Rotation { origin.x: incl.width / 2; origin.y: incl.height / 2; axis { x: 0; y: 1; z: 0 } angle: incl._ry },
                Rotation { origin.x: incl.width / 2; origin.y: incl.height / 2; axis { x: 1; y: 0; z: 0 } angle: incl._rx }
            ]
            y: zona.containsMouse && !c.centro ? -px(8) : 0
            Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            scale: zona.pressed ? 0.98 : 1
            Behavior on scale { NumberAnimation { duration: zona.pressed ? 90 : 300; easing.type: zona.pressed || (typeof quieto !== "undefined" && quieto) ? Easing.OutQuad : Easing.OutBack; easing.overshoot: 2.2 } }

            // el halo de la del centro (verde si se usa, dorado si solo se mira)
            Rectangle { anchors.fill: parent; anchors.margins: -px(14); radius: px(40); color: "transparent"
                border.width: px(14); border.color: c.usada ? "#22C47E" : "#E2B04F"
                opacity: c.centro ? 0.20 : 0; Behavior on opacity { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } } }

            Rectangle {
                anchors.fill: parent
                radius: px(28)
                color: "#0B1A1F"
                clip: true
                border.width: c.usada ? px(5) : (c.centro ? px(3) : 1)
                border.color: c.usada ? "#3BEE9F" : (c.centro ? "#E2B04F" : Qt.rgba(1, 1, 1, 0.16))
                Behavior on border.color { ColorAnimation { duration: 200 } }
                Image {
                    anchors.fill: parent; anchors.margins: parent.border.width
                    source: c.dato.portada || ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    // la del centro se acerca muy despacio (como si corriera el video)
                    scale: c.centro && !incl._quieto ? 1.06 : 1     // (1.8.5) con movimiento reducido, quieta
                    Behavior on scale { NumberAnimation { duration: 6000; easing.type: Easing.InOutSine } }
                }
                // (1.7.8) el reflejo que cruza la portada siguiendo al cursor
                Rectangle {
                    width: parent.width * 0.5; height: parent.height * 2
                    y: -parent.height * 0.5; rotation: 22
                    x: (hvP.hovered ? hvP.point.position.x : -parent.width) - width / 2
                    Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                    opacity: hvP.hovered ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.16) }
                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) } }
                }
                // sin portada: el icono
                Image {
                    visible: !c.dato.portada
                    anchors.centerIn: parent; width: px(90); height: width
                    source: "image://icono/pelicula/9DB0B6/" + width; sourceSize: Qt.size(width * 4, height * 4)
                }
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: parent.height * 0.35
                    gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.7) } }
                }
                Text {
                    x: px(24); width: parent.width - px(48)
                    anchors.bottom: parent.bottom; anchors.bottomMargin: px(22)
                    text: raiz.nombreBonito(c.dato.nombre); elide: Text.ElideRight; color: "white"
                    font.family: raiz.familia; font.pixelSize: px(30); font.weight: Font.DemiBold; font.capitalization: Font.Capitalize
                    opacity: c.centro ? 0 : 1              // en la del centro el nombre va debajo, en grande
                    Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }
            }
            // la palomita de las usadas (tambien a los lados)
            Rectangle {
                x: parent.width - width - px(18); y: px(18)
                width: px(52); height: width; radius: width / 2
                color: "#22C47E"; border.width: px(3); border.color: "#04150D"
                scale: c.usada ? 1 : 0.6; opacity: c.usada ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
                Image { anchors.centerIn: parent; width: px(32); height: width
                    source: "image://icono/palomita/04150D/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            }
        }
        MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: c.tocar() }
    }
}
