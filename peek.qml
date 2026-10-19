import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell
import Hyal 1.0

Window {
    id: edge
    width: 142
    height: 142 + peekBridge.panelInset
    visible: false
    color: "transparent"
    title: "Hya Edge Peek"
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    property var owner
    LayerShell.Window.anchors: peekBridge.edgeSide === "bottom"
        ? LayerShell.Window.AnchorBottom | LayerShell.Window.AnchorRight
        : (peekBridge.edgeSide === "left" ? LayerShell.Window.AnchorLeft : LayerShell.Window.AnchorRight) | LayerShell.Window.AnchorTop
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    // -1 ignores panel exclusive zones, anchoring to the physical output edge.
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.activateOnShow: false
    LayerShell.Window.screen: peekBridge.outputScreen
    LayerShell.Window.margins: peekBridge.edgeMargins

    Item {
        width: 142
        height: 142
        // The transparent strip below this item is neither painted nor clickable.
        clip: true
        PeekArtwork {
            objectName: "artwork"
            width: 142
            height: 142
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onEntered: peekBridge.hover(true)
            onExited: peekBridge.hover(false)
            onPositionChanged: mouse => peekBridge.pointerMoved(mouse.x, mouse.y, containsMouse)
            onDoubleClicked: mouse => {
                if (mouse.button === Qt.LeftButton) peekBridge.chat()
            }
            onClicked: mouse => {
                if (mouse.button === Qt.RightButton) peekBridge.contextMenu()
                else peekBridge.restore()
            }
        }
    }
}
