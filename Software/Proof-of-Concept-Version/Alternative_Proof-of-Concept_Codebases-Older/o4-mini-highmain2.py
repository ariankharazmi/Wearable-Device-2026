# main.py
import sys, time
import psutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplashScreen,
    QGraphicsView, QGraphicsScene, QGraphicsObject,
    QGraphicsDropShadowEffect, QStackedWidget, QLabel
)
from PyQt5.QtGui    import QPixmap, QPainter, QColor, QPainterPath
from PyQt5.QtCore   import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPointF, QRectF, pyqtProperty, QThread, pyqtSignal
)

from camera         import CameraFeed
from floating_card  import FloatingCard
from assistant_pill import AssistantPillIcon
from apps import settings_pane

# ---------------------------------------------------------
# Monkey-patch FloatingCard.setText (so notifications work)
# ---------------------------------------------------------
if not hasattr(FloatingCard, "setText"):
    def _fc_setText(self, txt):
        try:
            self.label.setText(txt)
        except AttributeError:
            self._text = txt
    FloatingCard.setText = _fc_setText


# ──────────────────────────────────────────────────────────────
#  WeatherFetcher: only runs every 5 min on a background thread
# ──────────────────────────────────────────────────────────────
class WeatherFetcher(QThread):
    weatherFetched = pyqtSignal(str)
    LAT, LON = 37.7749, -122.4194  # replace with dynamic or user‐set coords

    def run(self):
        import requests
        try:
            j = requests.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.LAT}&longitude={self.LON}"
                "&current_weather=true&timezone=auto",
                timeout=3
            ).json()["current_weather"]
            f = round(j["temperature"] * 9/5 + 32)
            cond = "Sunny" if j["weathercode"] < 3 else "Cloudy"
            txt = f"{f}°F {cond}"
        except:
            txt = "–°F"
        self.weatherFetched.emit(txt)


# ──────────────────────────────────────────────────────────────
#  StatusBar: ticks every second, shows last‐fetched weather
# ──────────────────────────────────────────────────────────────
class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(36)

        self.lbl = QLabel("", self)
        self.lbl.setStyleSheet("color:white; font:12px 'Helvetica';")
        self.lbl.setGeometry(8, 0, 600, 36)

        # clock timer (1 Hz)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

        # weather (every 5 min)
        self.weather = "–°F"
        self.fetcher = WeatherFetcher()
        self.fetcher.weatherFetched.connect(self._set_weather)
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self.fetcher.start)
        self.fetch_timer.start(5 * 60_000)
        self.fetcher.start()  # initial fetch

    def _set_weather(self, txt):
        self.weather = txt

    def _update_clock(self):
        now  = datetime.now().strftime("%I:%M %p")
        batt = psutil.sensors_battery()
        pct  = f"{int(batt.percent)}%" if batt else "–%"
        self.lbl.setText(f"{now} · {pct} · {self.weather}")


# ──────────────────────────────────────────────────────────────
#  IconItem: rounded, hover‐glow, clickable
# ──────────────────────────────────────────────────────────────
class IconItem(QGraphicsObject):
    def __init__(self, image_path, label, index):
        super().__init__()
        self.index = index
        self.label = label
        self._opacity = 1.0
        self._scale   = 1.0
        self.radius   = 20
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

        base = QPixmap(image_path)
        if base.isNull():
            print(f"⚠️ Missing icon: {image_path}")
        base = base.scaled(120,120, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        w = h = 120
        self._pixmap = QPixmap(w,h)
        self._pixmap.fill(Qt.transparent)
        p = QPainter(self._pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(0,0,w,h), self.radius, self.radius)
        p.setClipPath(path)
        p.drawPixmap(0,0, base)
        p.end()

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(QColor(255,255,255,180))
        glow.setOffset(0,0)
        glow.setEnabled(False)
        self.setGraphicsEffect(glow)

    def boundingRect(self):
        return QRectF(0, 0, 120, 120)

    def paint(self, painter, option, widget):
        painter.setOpacity(self._opacity)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.translate(60,60)
        painter.scale(self._scale, self._scale)
        painter.translate(-60,-60)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()

    def getOpacity(self):    return self._opacity
    def setOpacity(self, v): self._opacity = v; self.update()
    opacity = pyqtProperty(float, fget=getOpacity, fset=setOpacity)

    def getScale(self):      return self._scale
    def setScale(self, v):   self._scale = v; self.update()
    scale = pyqtProperty(float, fget=getScale, fset=setScale)

    def hoverEnterEvent(self, ev): self.setScale(1.1)
    def hoverLeaveEvent(self, ev): self.setScale(1.0)

    def mousePressEvent(self, ev):
        view = self.scene().views()[0]
        view.parent().launch_app(self.index)


# ──────────────────────────────────────────────────────────────
#  CoverFlowLauncher: arrow & click nav, fixed spacing
# ──────────────────────────────────────────────────────────────
class CoverFlowLauncher(QGraphicsView):
    def __init__(self, icons, parent=None):
        super().__init__(parent)
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
            self.index = (self.index+1)%len(self.items)
            self.update_icons(True)
        elif ev.key()==Qt.Key_Left:
            self.index = (self.index-1)%len(self.items)
            self.update_icons(True)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update_icons(False)

    def update_icons(self, animated=True):
        cx     = self.width()/2
        y      = self.height()/2 - 60
        offset = 180
        for i,item in enumerate(self.items):
            dx       = (i-self.index)*offset
            target   = QPointF(cx+dx-60, y)
            selected = (i==self.index)
            item.graphicsEffect().setEnabled(selected)
            scale_val = 1.3 if selected else 1.0
            if animated:
                for prop,end in ((b"pos",target),(b"scale",scale_val)):
                    a=QPropertyAnimation(item,prop,self)
                    a.setDuration(120); a.setEasingCurve(QEasingCurve.InOutCubic)
                    a.setEndValue(end); a.start()
            else:
                item.setPos(target); item.setScale(scale_val)


# ──────────────────────────────────────────────────────────────
#  VisionAriesUI: glues it all together
# ──────────────────────────────────────────────────────────────
class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(50,50,960,540)

        # splash
        splash = QSplashScreen(QPixmap("VisionAriesAssets/VisionAriesLogo.png"))
        splash.show(); QApplication.processEvents()
        time.sleep(0.4)
        splash.finish(self)

        # camera
        self.camera = CameraFeed()
        self.setCentralWidget(self.camera)

        # coverflow
        self.launcher = CoverFlowLauncher(icons, parent=self)
        self.launcher.setGeometry(self.rect())
        self.launcher.raise_()

        # status bar
        self.status = StatusBar(self)
        self.status.move(0, self.height()-36)
        self.status.raise_()

        # mic pill
        self.pill = AssistantPillIcon("../VisionAriesAssets/mic.png")
        self.pill.setParent(self)
        self.pill.move(self.width()//2-32, self.height()-90)
        self.pill.raise_()

        # notifications
        self.notif = FloatingCard("No new notifications", None)
        self.notif.setParent(self)
        self.notif.resize(260,40)
        self.notif.move(self.width()-280, self.height()-80)
        self.notif.setStyleSheet(
            "background-color: rgba(255,255,255,0.25);"
            "color: #333333; border-radius: 20px;"
        )
        self.notif.raise_()

        # app stack (camera + settings)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.camera)
        self.stack.addWidget(settings_pane.SettingsPane())
        self.stack.setGeometry(self.rect())
        self.stack.lower()
        self.app_map = {0:0, 3:1}

        # 60 fps repaint
        loop = QTimer(self)
        loop.timeout.connect(self.update)
        loop.start(int(1000/60))

        self.show()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.launcher.setGeometry(self.rect())
        self.status.move(0, self.height()-36)
        self.pill.move(self.width()//2-32, self.height()-90)
        self.notif.move(self.width()-280, self.height()-80)
        self.stack.setGeometry(self.rect())

    def launch_app(self, idx):
        target = self.app_map.get(idx, 0)
        if target != self.stack.currentIndex():
            self._slide_to(target)

    def _slide_to(self, page_index):
        cur = self.stack.currentIndex()
        dir = 1 if page_index>cur else -1
        w = self.width()

        out = QPropertyAnimation(self.stack, b"geometry", self)
        out.setDuration(180); out.setEasingCurve(QEasingCurve.InOutCubic)
        out.setStartValue(self.stack.geometry())
        out.setEndValue(self.stack.geometry().translated(-dir*w,0))
        out.start()

        self.stack.setCurrentIndex(page_index)

        inn = QPropertyAnimation(self.stack, b"geometry", self)
        inn.setDuration(180); inn.setEasingCurve(QEasingCurve.InOutCubic)
        inn.setStartValue(self.stack.geometry().translated(dir*w,0))
        inn.setEndValue(self.stack.geometry())
        inn.start()


if __name__=="__main__":
    app = QApplication(sys.argv)

    icons = [
        ("VisionAriesAssets/camera.png",   "Camera"),
        ("VisionAriesAssets/gps.png",      "Maps"),
        ("VisionAriesAssets/gpt.png",      "Assistant"),
        ("VisionAriesAssets/settings.png", "Settings"),
    ]

    window = VisionAriesUI(icons)
    sys.exit(app.exec_())
