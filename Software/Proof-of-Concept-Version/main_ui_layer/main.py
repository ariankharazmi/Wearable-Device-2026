# main.py
import sys
import os
import time
import inspect
import requests
import psutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSplashScreen, QWidget, QStackedWidget,
    QGraphicsView, QGraphicsScene, QGraphicsBlurEffect, QLabel, QVBoxLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPainterPath, QFont
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsDropShadowEffect
from PyQt5.QtCore import QPointF, QRectF, pyqtProperty, QPropertyAnimation, QEasingCurve

# core modules
from camera import CameraFeed
from floating_card import FloatingCard
from assistant_pill import AssistantPillIcon

# panepackage
from apps import (
    BasePane,
    SettingsPane, MapsPane, AssistantPane, BluetoothPane,
    PhotoPane, VideoPane, TranslatorPane, NavPane,
    MusicPane, MusicPaneUnavailable, CallPane,
    DrawingPane, PersonTrackerPane, GestureCanvasPane,
    LLMPane, ThemeManager, SharedARPane,
    SpatialAudioManager, LiveStreamPane
)

# AR & AI
from contextual_assistant import ContextualAssistant
from ar_overlay import AROverlayManager
from feedback_overlay import FeedbackOverlay

# system notifications
from notification_center import NotificationCenter

# ------------------------------------------------------------------
# Monkey-patch FloatingCard to add setText()
# ------------------------------------------------------------------
if not hasattr(FloatingCard, "setText"):
    def _fc_setText(self, txt):
        if hasattr(self, "label"):
            self.label.setText(txt)
        else:
            self._text = txt
    FloatingCard.setText = _fc_setText

# ------------------------------------------------------------------
# IconItem + CoverFlowLauncher (with labels)
# ------------------------------------------------------------------
class IconItem(QGraphicsObject):
    def __init__(self, image_path, label, index):
        super().__init__()
        self.index = index
        self.label = label
        self._scale = 1.0
        self._shine = 0.0
        self.radius = 32

        pix = QPixmap(image_path)
        if pix.isNull():
            print(f"⚠️ Missing icon: {image_path}")
            pix = QPixmap(128, 128)
            pix.fill(Qt.transparent)
        base = pix.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        w = h = 128
        self._pixmap = QPixmap(w, h)
        self._pixmap.fill(Qt.transparent)
        p = QPainter(self._pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), self.radius, self.radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, base)
        p.end()

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(40)
        glow.setColor(QColor(255, 255, 255, 200))
        glow.setOffset(0, 0)
        glow.setEnabled(False)
        self.setGraphicsEffect(glow)

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self):
        return QRectF(0, 0, 128, 128)

    def paint(self, painter, *_):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.translate(64, 64)
        painter.scale(self._scale, self._scale)
        painter.translate(-64, -64)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()
        if self._shine > 0:
            painter.setOpacity(self._shine)
            painter.fillRect(0, 0, 128, 128, QColor(255, 255, 255, 120))

    def getScale(self):
        return self._scale

    def setScale(self, v):
        self._scale = v
        self.update()

    scale = pyqtProperty(float, fget=getScale, fset=setScale)

    def getShine(self):
        return self._shine

    def setShine(self, v):
        self._shine = v
        self.update()

    shine = pyqtProperty(float, fget=getShine, fset=setShine)

    def hoverEnterEvent(self, ev):
        self.setScale(1.1)

    def hoverLeaveEvent(self, ev):
        self.setScale(1.0)

    def mousePressEvent(self, ev):
        # launch the app
        self.scene().views()[0].parent().launch_app(self.index)


class CoverFlowLauncher(QGraphicsView):
    def __init__(self, icons, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.items = []
        self.index = 0

        for i, (path, name) in enumerate(icons):
            it = IconItem(path, name, i)
            self.scene.addItem(it)
            self.items.append(it)

        self.update_icons(animated=False)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Right:
            self.index = (self.index + 1) % len(self.items)
            self.update_icons(animated=True)
        elif ev.key() == Qt.Key_Left:
            self.index = (self.index - 1) % len(self.items)
            self.update_icons(animated=True)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update_icons(animated=False)

    def update_icons(self, animated):
        spacing = 200
        mid_x = self.width() / 2 - 64
        mid_y = self.height() / 2 - 64

        for i, it in enumerate(self.items):
            x = (i - self.index) * spacing + mid_x
            sel = (i == self.index)
            it.graphicsEffect().setEnabled(sel)

            if sel and animated:
                shine = QPropertyAnimation(it, b"shine", self)
                shine.setDuration(300)
                shine.setKeyValueAt(0, 0.8)
                shine.setKeyValueAt(0.5, 0.0)
                shine.setEndValue(0.0)
                shine.start()

            for prop, end in (
                (b"pos", QPointF(x, mid_y)),
                (b"scale", 1.4 if sel else 1.0),
            ):
                if animated:
                    a = QPropertyAnimation(it, prop, self)
                    a.setDuration(80)
                    a.setEasingCurve(QEasingCurve.InOutCubic)
                    a.setEndValue(end)
                    a.start()
                else:
                    if prop == b"pos":
                        it.setPos(end)
                    else:
                        it.setScale(end)

# ------------------------------------------------------------------
# StatusBar: time · batt · weather · CPU · RAM · build · console log
# ------------------------------------------------------------------
class StatusBar(QWidget):
    LAT, LON = 37.7749, -122.4194

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(48)

        self.lbl = QLabel(self)
        f = QFont("Arial", 10)
        self.lbl.setFont(f)
        self.lbl.setStyleSheet("color: white;")
        self.lbl.setGeometry(8, 0, parent.width() - 16, 48)

        self._console = []
        self._update()
        t = QTimer(self)
        t.timeout.connect(self._update)
        t.start(30_000)

    def append(self, line):
        self._console.append(line)
        if len(self._console) > 3:
            self._console.pop(0)
        self._update()

    def _get_weather(self):
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.LAT}&longitude={self.LON}"
                "&current_weather=true&timezone=auto"
            )
            j = requests.get(url, timeout=2).json()["current_weather"]
            ft = round(j["temperature"] * 9 / 5 + 32)
            icon = "☀️" if j["weathercode"] < 3 else "☁️"
            return f"{ft}°F {icon}"
        except:
            return "–°F"

    def _update(self):
        now = datetime.now().strftime("%-I:%M %p")
        batt = psutil.sensors_battery()
        bp = f"{int(batt.percent)}%" if batt else "–%"
        weather = self._get_weather()
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        build = "Aries OS 1.0 α·Bld1 · May 21 2025"

        lines = "\n".join(self._console)
        txt = (
            f"{now} · {bp} · {weather} · CPU {cpu:.0f}% · RAM {ram:.0f}%\n"
            f"{build}"
        )
        if lines:
            txt += "\n" + lines

        self.lbl.setText(txt)

# ------------------------------------------------------------------
# Transient overlay for speech & object labels
# ------------------------------------------------------------------
class OverlayLabel(QLabel):
    def __init__(self, parent=None, font_size=14, bg="rgba(0,0,0,0.6)"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet(f"""
            color: white;
            background: {bg};
            padding: 4px 8px;
            border-radius: 6px;
        """)
        f = QFont("Helvetica Neue", font_size)
        if not f.exactMatch():
            f = QFont("Arial", font_size)
        self.setFont(f)
        self.hide()

    def show_timed(self, text, timeout=2000):
        self.setText(text)
        self.adjustSize()
        self.show()
        QTimer.singleShot(timeout, self.hide)

# ------------------------------------------------------------------
# Main Window
# ------------------------------------------------------------------
class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(50, 50, 960, 540)

        # Splash
        logo = QPixmap("VisionAriesAssets/VisionAriesLogo.png")
        if logo.isNull():
            logo = QPixmap(960, 540)
            logo.fill(Qt.black)
        sp = QSplashScreen(logo)
        sp.showMessage("Empowering Visionaries",
                       Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        sp.show(); QApplication.processEvents()
        time.sleep(0.5)
        sp.close()

        # Central Camera
        self.camera = CameraFeed()
        self.setCentralWidget(self.camera)

        # Contextual AI
        self.ctx = ContextualAssistant(self.camera)
        self.ctx.frameOverlay.connect(self.update_camera_feed)
        self.ctx.suggestionReady.connect(lambda m: self.notif.showMessage(m, 3000))
        self.ctx.start()

        # Speech / object overlay
        self.speech_ol = OverlayLabel(self, font_size=12, bg="rgba(0,0,0,0.7)")
        self.ctx.voiceCommandProcessed.connect(
            lambda cmd, resp: self.speech_ol.show_timed(f"> {cmd}\n{resp}", 3000)
        )

        # Cover-flow launcher
        self.launcher = CoverFlowLauncher(icons, self)
        self.launcher.setGeometry(self.rect())
        self.launcher.raise_()

        # Stacked panes
        self.pages = QStackedWidget(self)
        pane_classes = [
            SettingsPane, MapsPane, AssistantPane, BluetoothPane,
            PhotoPane, VideoPane, TranslatorPane, NavPane,
            MusicPane, CallPane,
            DrawingPane, PersonTrackerPane, GestureCanvasPane,
            LLMPane, ThemeManager, SharedARPane,
            SpatialAudioManager, LiveStreamPane
        ]

        for cls in pane_classes:
            sig = inspect.signature(cls.__init__)
            params = set(sig.parameters) - {"self"}
            args, kwargs = [], {}
            if "camera_feed" in params:
                args.append(self.camera)
            if "ctx_assistant" in params:
                args.append(self.ctx)
            if "parent" in params:
                kwargs["parent"] = self

            try:
                page = cls(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ failed to instantiate {cls.__name__}: {e}")
                continue

            # wire up Home button
            if hasattr(page, "goHomeRequested"):
                page.goHomeRequested.connect(lambda _=None: self.launch_app(0))

            self.pages.addWidget(page)

        self.pages.setGeometry(self.rect())
        self.pages.lower()

        # AR Overlay
        self.ar = AROverlayManager(self.camera, self.ctx, self)
        self.ar.overlayUpdated.connect(self.update_camera_feed)

        # System notifications
        self.notif = FloatingCard(parent=self, blur_behind=True)
        self.notif.raise_()
        self.sys_notif = NotificationCenter(self)
        self.sys_notif.notificationReceived.connect(
            lambda m: self.notif.showMessage(m, 5000))
        self.sys_notif.start()

        # Status bar
        self.status = StatusBar(self)
        self.status.raise_()

        # Mic pill
        self.pill_bg = QWidget(self)
        self.pill_bg.setFixedSize(56, 56)
        self.pill_bg.setStyleSheet(
            "background:rgba(255,255,255,0.2);border-radius:28px;")
        self.pill = AssistantPillIcon("VisionAriesAssets/mic.png")
        self.pill.setParent(self.pill_bg)
        self.pill.move(12, 12)
        self.pill.installEventFilter(self)
        self.pill_bg.raise_()

        # 60FPS update loop
        self._upd = QTimer(self)
        self._upd.timeout.connect(self.update)
        self._upd.start(16)

        self.show()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        r = self.rect()
        self.launcher.setGeometry(r)
        self.pages.setGeometry(r)
        self.status.move(8, self.height() - self.status.height() - 80)
        self.pill_bg.move((self.width() - 56) // 2, self.height() - 72)
        self.notif.move(self.width() - 320, self.height() - 88)
        if self.speech_ol.isVisible():
            self.speech_ol.move(
                (self.width() - self.speech_ol.width()) // 2,
                self.height() - 80 - self.speech_ol.height()
            )

    def launch_app(self, idx):
        """Switch to page idx; hide icons on any pane, show on home."""
        self.pages.setCurrentIndex(idx)
        if idx == 0:
            self.launcher.show()
        else:
            self.launcher.hide()

    def update_camera_feed(self, pix):
        if pix and not pix.isNull():
            self.camera.setPixmap(pix)

    def eventFilter(self, obj, ev):
        if obj is self.pill and ev.type() == ev.MouseButtonPress:
            self.camera.setGraphicsEffect(QGraphicsBlurEffect())
            self.ctx.process_voice_command()
            QTimer.singleShot(200, lambda: self.camera.setGraphicsEffect(None))
        return super().eventFilter(obj, ev)

    def closeEvent(self, ev):
        self.ctx.stop()
        super().closeEvent(ev)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    icons = [
        ("VisionAriesAssets/camera.png",   "Camera"),
        ("VisionAriesAssets/gps.png",      "Maps"),
        ("VisionAriesAssets/gpt.png",      "Assistant"),
        ("VisionAriesAssets/settings.png", "Settings"),
        ("VisionAriesAssets/bluetooth.png","Tether"),
        ("VisionAriesAssets/photo.png",    "Photos"),
        ("VisionAriesAssets/video.png",    "Video"),
        ("VisionAriesAssets/translate.png","Translate"),
        ("VisionAriesAssets/nav.png",      "Nav"),
        ("VisionAriesAssets/music.png",    "Music"),
        ("VisionAriesAssets/call.png",     "Call"),
        ("VisionAriesAssets/draw.png",     "Draw"),
        ("VisionAriesAssets/person.png",   "Track"),
        ("VisionAriesAssets/gesture.png",  "Gesture"),
        ("VisionAriesAssets/llm.png",      "LLM"),
        ("VisionAriesAssets/theme.png",    "Theme"),
        ("VisionAriesAssets/sharear.png",  "ShareAR"),
        ("VisionAriesAssets/spatialaudio.png","SpatialAudio"),
        ("VisionAriesAssets/livestream.png","LiveStream"),
    ]

    win = VisionAriesUI(icons)
    sys.exit(app.exec_())