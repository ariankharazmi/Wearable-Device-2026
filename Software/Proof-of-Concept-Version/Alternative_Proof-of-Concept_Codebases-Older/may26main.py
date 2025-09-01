# main.py
import sys
import time
import requests
import psutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplashScreen,
    QGraphicsView, QGraphicsScene, QGraphicsObject,
    QGraphicsDropShadowEffect, QStackedWidget, QLabel,
    QGraphicsBlurEffect
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPainterPath, QFont
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPointF, QRectF, pyqtProperty, QEvent
)

# Core UI
from camera import CameraFeed
from floating_card import FloatingCard
from assistant_pill import AssistantPillIcon

# Built-in panes
from apps.settings_pane import SettingsPane
from apps.maps_pane import MapsPane
from apps.assistant_pane import AssistantPane
from apps.bluetooth_pane import BluetoothPane
from apps.photo_pane import PhotoPane
from apps.video_pane import VideoPane
from apps.translator_pane import TranslatorPane
from apps.nav_pane import NavPane
from apps.music_pane import MusicPane
from apps.call_pane import CallPane

# Advanced panes
from apps.person_tracker_pane import EyeTrackingPane
from apps.gesture_canvas_pane import GestureCanvasPane
from apps.llm_pane import LLMPane
from apps.theme_manager import ThemeManager
from apps.shared_ar_pane import SharedARPane
from apps.spatial_audio_manager import SpatialAudioManager
from apps.livestream_pane import LiveStreamPane

# AR & AI
from contextual_assistant import ContextualAssistant
from ar_overlay import AROverlayManager
from feedback_overlay import FeedbackOverlay

# System notifications
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
# OverlayLabel: transient speech/object overlays
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
# IconItem: rounded, hover-glow, shine
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
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), self.radius, self.radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, base)
        painter.end()

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(40)
        glow.setColor(QColor(255, 255, 255, 220))
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
        self.scene().views()[0].parent().launch_app(self.index)

# ------------------------------------------------------------------
# CoverFlowLauncher: arrow & click nav with shine animation
# ------------------------------------------------------------------
class CoverFlowLauncher(QGraphicsView):
    def __init__(self, icons, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.items = []
        self.index = 0

        for i, (path, name) in enumerate(icons):
            item = IconItem(path, name, i)
            self.scene.addItem(item)
            self.items.append(item)

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
# StatusBar: live clock · batt · weather · CPU · RAM · build info
# ------------------------------------------------------------------
class StatusBar(QWidget):
    LAT, LON = 37.7749, -122.4194

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(48)

        self.lbl = QLabel(self)
        f = QFont("Helvetica Neue", 10)
        if not f.exactMatch():
            f = QFont("Arial", 10)
        self.lbl.setFont(f)
        self.lbl.setStyleSheet("color: white;")
        self.lbl.setGeometry(8, 0, parent.width() - 16, 48)

        self._update()
        timer = QTimer(self)
        timer.timeout.connect(self._update)
        timer.start(30000)

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
        bpct = f"{int(batt.percent)}%" if batt else "–%"
        weather = self._get_weather()
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        build = "Aries OS 1.0 α·Bld1 · May 21 2025"
        self.lbl.setText(
            f"{now} · {bpct} · {weather} · CPU {cpu:.0f}% · RAM {ram:.0f}%\n"
            f"{build}"
        )

# ------------------------------------------------------------------
# Main Application Window
# ------------------------------------------------------------------
class VisionAriesUI(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.setWindowTitle("Vision Aries OS")
        self.setGeometry(50, 50, 960, 540)
        self.high_contrast = False

        # Splash screen
        logo = QPixmap("VisionAriesAssets/VisionAriesLogo.png")
        if logo.isNull():
            logo = QPixmap(960, 540)
            logo.fill(Qt.black)
            print("⚠️ Missing splash logo, using blank")
        splash = QSplashScreen(logo)
        splash.showMessage(
            "Empowering Visionaries",
            Qt.AlignBottom | Qt.AlignCenter,
            Qt.white
        )
        splash.show()
        QApplication.processEvents()
        time.sleep(0.4)
        splash.close()

        # Camera feed as central widget
        self.camera = CameraFeed()
        self.setCentralWidget(self.camera)

        # Contextual assistant (text/object/gesture detection)
        self.ctx = ContextualAssistant(self.camera)
        self.ctx.frameOverlay.connect(self.update_camera_feed)
        self.ctx.start()

        # Speech overlay
        self.speech_ol = OverlayLabel(
            self, font_size=12, bg="rgba(30,30,30,0.8)"
        )
        self.ctx.voiceCommandProcessed.connect(
            lambda cmd, resp: self.speech_ol.show_timed(f"> {cmd}\n{resp}", 3000)
        )

        # CoverFlow launcher overlay
        self.launcher = CoverFlowLauncher(icons, self)
        self.launcher.setGeometry(self.rect())
        self.launcher.raise_()

        # Stacked pages
        self.pages = QStackedWidget(self)
        pane_list = [
            self.camera,
            MapsPane(),
            AssistantPane(),
            SettingsPane(),
            BluetoothPane(),
            PhotoPane(self.camera),
            VideoPane(self.camera),
            TranslatorPane(self.camera),
            NavPane(),
        ]
        # Music pane with credential guard
        try:
            music = MusicPane()
        except Exception as e:
            print(f"⚠️ MusicPane init failed: {e}")
            stub = QLabel("Music disabled (no credentials)", alignment=Qt.AlignCenter)
            stub.setStyleSheet("color:white; font:14px;")
            music = stub
        pane_list += [music, CallPane()]

        # Advanced feature panes
        pane_list += [
            EyeTrackingPane(self.camera),
            GestureCanvasPane(self.camera),
            LLMPane(),
            ThemeManager(),
            SharedARPane(),
            SpatialAudioManager(),
            LiveStreamPane(self.camera),
        ]

        for p in pane_list:
            self.pages.addWidget(p)
        self.pages.setGeometry(self.rect())
        self.pages.lower()

        # AR overlay manager
        self.ar = AROverlayManager(self.camera, self.ctx, self)
        self.ar.overlayUpdated.connect(self.update_camera_feed)

        # Feedback suggestions overlay
        fb = FeedbackOverlay(self.ctx, self)
        fb.suggestionReady.connect(lambda msg: self.notif.showMessage(msg, 2000))

        # Status bar
        self.status = StatusBar(self)
        self.status.raise_()

        # Assistant mic pill
        self.pill_bg = QWidget(self)
        self.pill_bg.setFixedSize(56, 56)
        self.pill_bg.setStyleSheet("background:rgba(255,255,255,0.2);border-radius:28px;")
        self.pill = AssistantPillIcon("../VisionAriesAssets/mic.png")
        self.pill.setParent(self.pill_bg)
        self.pill.move(12, 12)
        self.pill.installEventFilter(self)
        self.pill_bg.raise_()

        # Notification card with blur-behind
        self.notif = FloatingCard(parent=self, blur_behind=True)
        self.notif.setParent(self)
        self.notif.raise_()

        # System notification simulator
        self.nc = NotificationCenter(self)
        self.nc.notificationReceived.connect(
            lambda msg: self.notif.showMessage(msg, 5000)
        )
        self.nc.start()

        # 60 FPS update loop
        self._fps = QTimer(self)
        self._fps.timeout.connect(self.update)
        self._fps.start(16)

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
        target = min(idx, self.pages.count() - 1)
        if target != self.pages.currentIndex():
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(12)
            self.camera.setGraphicsEffect(blur)
            self._slide_to(target)
            QTimer.singleShot(200, lambda: self.camera.setGraphicsEffect(None))

    def _slide_to(self, tgt):
        cur = self.pages.currentIndex()
        direction = 1 if tgt > cur else -1
        w = self.width()
        # animate out
        anim_out = QPropertyAnimation(self.pages, b"geometry", self)
        anim_out.setDuration(180)
        anim_out.setEasingCurve(QEasingCurve.InOutCubic)
        anim_out.setStartValue(self.pages.geometry())
        anim_out.setEndValue(self.pages.geometry().translated(-direction * w, 0))
        anim_out.start()
        # switch page
        self.pages.setCurrentIndex(tgt)
        # animate in
        anim_in = QPropertyAnimation(self.pages, b"geometry", self)
        anim_in.setDuration(180)
        anim_in.setEasingCurve(QEasingCurve.InOutCubic)
        anim_in.setStartValue(self.pages.geometry().translated(direction * w, 0))
        anim_in.setEndValue(self.pages.geometry())
        anim_in.start()

    def update_camera_feed(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.camera.setPixmap(pixmap)

    def eventFilter(self, obj, ev):
        if obj is self.pill and ev.type() == QEvent.MouseButtonPress:
            # mic pressed → blur + voice command
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
        ("VisionAriesAssets/eyetrack.png",      "EyeTrack"),
        ("VisionAriesAssets/gesture.png",  "Gesture"),
        ("VisionAriesAssets/llm.png",      "LLM"),
        ("VisionAriesAssets/theme.png",    "Theme"),
        ("VisionAriesAssets/sharear.png",    "ShareAR"),
        ("VisionAriesAssets/spatialaudio.png",    "SpatialAudio"),
        ("VisionAriesAssets/livestream.png",   "LiveStream"),
    ]
    win = VisionAriesUI(icons)
    sys.exit(app.exec_())
