import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject,
    QGraphicsOpacityEffect, QLabel
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtProperty, QRectF, QPointF, QTimer

from camera import CameraFeed
from floating_card import FloatingCard
from assistant_pill import AssistantPillIcon


class IconItem(QGraphicsObject):
    def __init__(self, pixmap, index):
        super().__init__()
        self.pixmap = pixmap
        self.index = index
        self.opacity_value = 1.0
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self):
        return QRectF(0, 0, self.pixmap.width(), self.pixmap.height())

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self.opacity_value)
        painter.drawPixmap(0, 0, self.pixmap)

    def setOpacityValue(self, value):
        self.opacity_value = value
        self.update()

    def getOpacityValue(self):
        return self.opacity_value

    opacity = pyqtProperty(float, fget=getOpacityValue, fset=setOpacityValue)

    def hoverEnterEvent(self, event):
        self.setScale(1.08)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)

    def mousePressEvent(self, event):
        print(f"App {self.index} clicked!")


class CoverFlowLauncher(QGraphicsView):
    def __init__(self, image_paths):
        super().__init__()
        self.setStyleSheet("background: transparent;")
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

    def update_icons(self, animated):
        spacing = 120
        center_x = self.width() / 2
        center_y = self.height() / 2 - 30

        for i, item in enumerate(self.icons):
            dx = (i - self.index) * spacing
            pos = QPointF(center_x + dx - item.boundingRect().width() / 2, center_y)
            opacity = 1.0 if i == self.index else 0.5

            if animated:
                anim = QPropertyAnimation(item, b"pos")
                anim.setDuration(200)
                anim.setEndValue(pos)
                anim.start()

                fade = QPropertyAnimation(item, b"opacity")
                fade.setDuration(200)
                fade.setEndValue(opacity)
                fade.start()
            else:
                item.setPos(pos)
                item.setOpacityValue(opacity)


class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(100, 100, 960, 540)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.camera = CameraFeed()
        layout.addWidget(self.camera)

        self.launcher = CoverFlowLauncher(icons)
        self.launcher.setParent(self)
        self.launcher.setGeometry(0, 0, self.width(), self.height())

        self.pill = AssistantPillIcon("../VisionAriesAssets/mic.png")
        self.pill.setParent(self)
        self.pill.show()

        self.clock_label = QLabel(self)
        self.clock_label.setStyleSheet("color: white; font-size: 11px; background: rgba(0, 0, 0, 90); padding: 4px; border-radius: 6px;")
        self.clock_label.setFont(QFont("Helvetica", 9))
        self.clock_label.setFixedWidth(300)
        self.clock_label.setAlignment(Qt.AlignLeft)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time_weather)
        self.timer.start(60000)  # every minute

        self.update_time_weather()
        self.resizeEvent(None)

    def update_time_weather(self):
        from datetime import datetime
        import pytz
        eastern = pytz.timezone('America/New_York')
        now = datetime.now(eastern)
        formatted_time = now.strftime("%I:%M %p")

        # Weather API fallback with fake data
        temp = "58°F"
        condition = "Cloudy"
        build_info = "Vision Aries — Aries OS 1.0 Alpha Build 1: May 21, 2025"

        self.clock_label.setText(f"{formatted_time} - {temp} {condition}\n{build_info}")

    def resizeEvent(self, event):
        self.launcher.setGeometry(0, 0, self.width(), self.height())
        self.pill.move(self.width() // 2 - self.pill.width() // 2, self.height() - 80)
        self.clock_label.move(10, self.height() - 55)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    icons = [
        "VisionAriesAssets/camera.png",
        "VisionAriesAssets/gps.png",
        "VisionAriesAssets/gpt.png",
        "VisionAriesAssets/settings.png"
    ]

    ui = VisionAriesUI(icons)
    ui.show()
    sys.exit(app.exec_())
