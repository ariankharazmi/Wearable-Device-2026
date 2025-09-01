import sys
import time
import requests
import psutil

from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplashScreen,
    QGraphicsView, QGraphicsScene, QGraphicsObject,
    QGraphicsDropShadowEffect, QStackedWidget, QLabel
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPainterPath
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, pyqtProperty, QPointF, QRectF
)

from camera import CameraFeed
from floating_card import FloatingCard
from assistant_pill import AssistantPillIcon
from apps import settings_pane


# ——————————————————————————————————————
#  IconItem: rounded, hover‐glow, clickable, animatable
# ——————————————————————————————————————
class IconItem(QGraphicsObject):
    def __init__(self, image_path, label, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.label = label
        self._opacity = 1.0
        self._scale = 1.0
        self.radius = 20
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

        base = QPixmap(image_path)
        if base.isNull():
            print(f"⚠️ Missing icon: {image_path}")
        self.base = base.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._make_rounded()

        # white glow on selection uses a shadow effect
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(20)
        glow.setColor(QColor(255,255,255,200))
        glow.setOffset(0,0)
        self.setGraphicsEffect(glow)

    def _make_rounded(self):
        w = h = 120
        self._pixmap = QPixmap(w, h)
        self._pixmap.fill(Qt.transparent)
        p = QPainter(self._pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0,0,w,h), self.radius, self.radius)
        p.setClipPath(path)
        p.drawPixmap(0,0, self.base)
        p.end()

    def boundingRect(self):
        return QRectF(0, 0, 120, 120)

    def paint(self, painter, option, widget):
        painter.setOpacity(self._opacity)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.translate(60, 60)
        painter.scale(self._scale, self._scale)
        painter.translate(-60, -60)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()

    def getOpacity(self):    return self._opacity
    def setOpacity(self, v): self._opacity = v; self.update()
    opacity = pyqtProperty(float, fget=getOpacity, fset=setOpacity)

    def getScale(self):    return self._scale
    def setScale(self, v): self._scale = v; self.update()
    scale = pyqtProperty(float, fget=getScale, fset=setScale)

    def hoverEnterEvent(self, ev): self.setScale(1.1)
    def hoverLeaveEvent(self, ev): self.setScale(1.0)

    def mousePressEvent(self, ev):
        # delegate to main UI
        self.scene().views()[0].parent().launch_app(self.index)
        print(f"🔹 Launched {self.label}")


# ——————————————————————————————————————
#  CoverFlowLauncher: arrow & click navigation
# ——————————————————————————————————————
class CoverFlowLauncher(QGraphicsView):
    def __init__(self, icons):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.Antialiasing)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.items = []
        self.index = 0
        for i,(path,name) in enumerate(icons):
            it = IconItem(path, name, i)
            self.scene.addItem(it)
            self.items.append(it)

        self.update_icons(animated=False)

    def keyPressEvent(self, ev):
        if ev.key()==Qt.Key_Right:
            self.index=(self.index+1)%len(self.items)
            self.update_icons(animated=True)
        elif ev.key()==Qt.Key_Left:
            self.index=(self.index-1)%len(self.items)
            self.update_icons(animated=True)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update_icons(animated=False)

    def update_icons(self, animated=True):
        count = len(self.items)
        width = self.width()
        spacing = width/(count+1)
        y = self.height()/2 - 60

        for i,item in enumerate(self.items):
            target_pos = QPointF(spacing*(i+1)-60, y)
            selected = (i==self.index)
            scale_val = 1.3 if selected else 1.0
            opacity_val = 1.0  # keep all icons fully opaque
            glow_effect = item.graphicsEffect()
            glow_effect.setEnabled(selected)

            if animated:
                for prop,end in ((b"pos",target_pos),(b"scale",scale_val),(b"opacity",opacity_val)):
                    anim = QPropertyAnimation(item, prop, self)
                    anim.setDuration(120)
                    anim.setEndValue(end)
                    anim.start()
            else:
                item.setPos(target_pos)
                item.setScale(scale_val)
                item.setOpacity(opacity_val)


# ——————————————————————————————————————
#  StatusBar: live clock, batt, weather
# ——————————————————————————————————————
class StatusBar(QWidget):
    LAT=37.7749; LON=-122.4194

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(36)
        self.lbl = QLabel("", self)
        self.lbl.setStyleSheet("color:white; font:12px 'Helvetica';")
        self.lbl.setGeometry(8,0,600,36)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(1000)
        self._update()

    def _update(self):
        now = datetime.now().strftime("%I:%M %p")
        batt = psutil.sensors_battery()
        pct = f"{int(batt.percent)}%" if batt else "–%"
        weather = self._weather()
        self.lbl.setText(f"{now} · {pct} · {weather}")

    def _weather(self):
        try:
            res = requests.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.LAT}&longitude={self.LON}"
                "&current_weather=true&timezone=auto",timeout=2
            ).json()["current_weather"]
            ftemp = round(res["temperature"]*9/5+32)
            cond = "Sunny" if res["weathercode"]<3 else "Cloudy"
            return f"{ftemp}°F {cond}"
        except:
            return "–°F"


# ——————————————————————————————————————
#  VisionAriesUI: glues it all together
# ——————————————————————————————————————
class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(50,50,960,540)

        # 1) Splash
        splash = QSplashScreen(QPixmap("VisionAriesAssets/VisionAriesLogo.png"))
        splash.show()
        QApplication.processEvents()
        time.sleep(0.5)
        splash.close()

        # 2) Camera background
        self.camera = CameraFeed()  # no parent
        self.setCentralWidget(self.camera)

        # 3) CoverFlow overlay
        self.launcher = CoverFlowLauncher(icons)
        self.launcher.setParent(self)
        self.launcher.setGeometry(self.rect())
        self.launcher.raise_()

        # 4) StatusBar (bottom-left)
        self.status = StatusBar(self)
        self.status.setParent(self)
        self.status.move(0, self.height()-40)
        self.status.raise_()

        # 5) Assistant pill (center-bottom)
        self.pill = AssistantPillIcon("../VisionAriesAssets/mic.png")
        self.pill.setParent(self)
        self.pill.move(self.width()//2 - 32, self.height()-90)
        self.pill.raise_()

        # 6) “No notifications” frosted card
        self.notif = FloatingCard("No new notifications", None)
        self.notif.setParent(self)
        self.notif.resize(260, 40)
        self.notif.move(self.width()-280, self.height()-80)
        # override its stylesheet for a translucent white
        self.notif.setStyleSheet(
            "background-color: rgba(255,255,255,0.25);"
            "color: #333333;"
            "border-radius: 20px;"
        )
        self.notif.raise_()

        # 7) App stack (Camera + Settings)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.camera)
        self.stack.addWidget(settings.SettingsPane())
        self.stack.setGeometry(self.rect())
        self.stack.raise_()
        self.app_map = {0: 0, 3: 1}  # index→page

        # 8) 60 FPS repaint loop
        fps = QTimer(self)
        fps.timeout.connect(self.update)
        fps.start(int(1000/60))

        self.show()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.launcher.setGeometry(self.rect())
        self.status.move(0, self.height()-40)
        self.pill.move(self.width()//2 - 32, self.height()-90)
        self.notif.move(self.width()-280, self.height()-80)
        self.stack.setGeometry(self.rect())

    def launch_app(self, idx):
        page = self.app_map.get(idx, 0)
        self.stack.setCurrentIndex(page)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_list = [
        ("VisionAriesAssets/camera.png",   "Camera"),
        ("VisionAriesAssets/gps.png",      "Maps"),
        ("VisionAriesAssets/gpt.png",      "Assistant"),
        ("VisionAriesAssets/settings.png", "Settings"),
    ]

    win = VisionAriesUI(icon_list)
    sys.exit(app.exec_())
