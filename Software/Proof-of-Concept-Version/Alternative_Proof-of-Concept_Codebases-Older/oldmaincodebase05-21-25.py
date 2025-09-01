import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QGraphicsView, QGraphicsScene, QGraphicsItemGroup, QGraphicsObject,
    QGraphicsOpacityEffect, QGraphicsPixmapItem, QGraphicsItem
)
from PyQt5.QtGui import QPixmap, QPainter, QTransform, QBrush, QColor, QPainterPath
from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtProperty, QRectF, QPointF

from camera import CameraFeed
from floating_card import FloatingCard
from assistant_pill import AssistantPillIcon


# --------------------------------------
# Custom Icon Item with Animations & Hover
# --------------------------------------
class IconItem(QGraphicsObject):
    def __init__(self, pixmap, index, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self.index = index
        self._opacity = 1.0
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self):
        return QRectF(0, 0, self._pixmap.width(), self._pixmap.height())

    def paint(self, painter, option, widget):
        painter.setOpacity(self._opacity)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self._pixmap)

    def setOpacity(self, opacity):
        self._opacity = opacity
        self.update()

    def getOpacity(self):
        return self._opacity

    opacity = pyqtProperty(float, fget=getOpacity, fset=setOpacity)

    def hoverEnterEvent(self, event):
        self.setScale(1.1)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)

    def mousePressEvent(self, event):
        print(f"App {self.index} clicked!")


# --------------------------------------
# CoverFlow Launcher Widget
# --------------------------------------
class CoverFlowLauncher(QGraphicsView):
    def __init__(self, image_paths):
        super().__init__()
        self.setStyleSheet("background-color: transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.Antialiasing)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.icons = []
        self.index = 0

        for i, path in enumerate(image_paths):
            pixmap = QPixmap(path)
            if pixmap.isNull():
                print(f"⚠️ Missing icon: {path}")
                continue
            pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = IconItem(pixmap, i)
            self.scene.addItem(item)
            self.icons.append(item)

        self.update_icons(animated=False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.index = (self.index + 1) % len(self.icons)
            self.update_icons(animated=True)
        elif event.key() == Qt.Key_Left:
            self.index = (self.index - 1) % len(self.icons)
            self.update_icons(animated=True)

    def update_icons(self, animated=True):
        spacing = 120
        center_x = self.width() / 2
        center_y = self.height() / 2 - 30

        for i, item in enumerate(self.icons):
            dx = (i - self.index) * spacing
            pos = QPointF(center_x + dx - item.boundingRect().width()/2, center_y)

            if animated:
                anim = QPropertyAnimation(item, b"pos")
                anim.setDuration(250)
                anim.setEndValue(pos)
                anim.start()

                fade = QPropertyAnimation(item, b"opacity")
                fade.setDuration(250)
                fade.setEndValue(1.0 if i == self.index else 0.6)
                fade.start()
            else:
                item.setPos(pos)
                item.setOpacity(1.0 if i == self.index else 0.6)


# --------------------------------------
# Vision Aries OS Main Window
# --------------------------------------
class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(100, 100, 960, 540)

        # Core layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Camera feed background
        self.camera = CameraFeed()
        layout.addWidget(self.camera)

        # Launcher overlay
        self.launcher = CoverFlowLauncher(icons)
        self.launcher.setParent(self)
        self.launcher.setGeometry(0, 0, self.width(), self.height())
        self.launcher.raise_()

        # Notification card
        self.card = FloatingCard("Sasha: Hey, just got here and grabbed a table :)", "../VisionAriesAssets/avatar.png")
        self.card.setParent(self)
        self.card.resize(420, 40)
        self.card.show()

        # Assistant icon
        self.pill = AssistantPillIcon("../VisionAriesAssets/mic.png")
        self.pill.setParent(self)
        self.pill.show()

        self.resizeEvent(None)

    def resizeEvent(self, event):
        # Notification card: bottom right
        self.card.move(self.width() - self.card.width() - 40, self.height() - self.card.height() - 40)

        # Assistant icon: center bottom
        self.pill.move(self.width() // 2 - self.pill.width() // 2, self.height() - 100)

        # Launcher
        self.launcher.setGeometry(0, 0, self.width(), self.height())


# --------------------------------------
# Entry Point
# --------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)

    icons = [
        "VisionAriesAssets/camera.png",
        "VisionAriesAssets/gps.png",
        "VisionAriesAssets/gpt.png"
    ]

    ui = VisionAriesUI(icons)
    ui.show()
    sys.exit(app.exec_())
