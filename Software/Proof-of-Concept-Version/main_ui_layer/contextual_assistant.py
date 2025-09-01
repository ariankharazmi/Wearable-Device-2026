# contextual_assistant.py
import sys
import threading
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap

class ContextualAssistant(QObject):
    # emits every time we want to overlay a new camera frame
    frameOverlay = pyqtSignal(QPixmap)
    # emits text suggestions / notifications
    suggestionReady = pyqtSignal(str)
    # emits (command, response) when voice is processed
    voiceCommandProcessed = pyqtSignal(str, str)

    def __init__(self, camera_widget):
        """
        camera_widget: your CameraFeed instance (a QLabel/QWidget that holds a QPixmap)
        """
        super().__init__()
        self.camera = camera_widget

        # fire a timer to grab whatever pixmap the camera is currently showing
        self._timer = QTimer(self)
        self._timer.setInterval(100)   # 10fps
        self._timer.timeout.connect(self._grab_and_emit)
        # note: .start() is called in main.py

    def _grab_and_emit(self):
        """Pull the current QPixmap from the camera widget and re-emit it."""
        try:
            pix = self.camera.pixmap()
            if isinstance(pix, QPixmap) and not pix.isNull():
                self.frameOverlay.emit(pix)
        except Exception:
            # camera widget may not have .pixmap() yet
            pass

    def start(self):
        """Begin relaying frames."""
        self._timer.start()

    def stop(self):
        """Stop relaying frames."""
        self._timer.stop()

    def process_voice_command(self):
        """
        Stub for voice-command processing.
        You can replace this with actual Vosk/TTS calls later.
        """
        # for now, immediately echo back a canned response
        cmd = "Aries, hello"
        resp = "Hello, visionary."
        # emit exactly after a brief pause to simulate work
        QTimer.singleShot(200, lambda: self.voiceCommandProcessed.emit(cmd, resp))
        # also surface a suggestion
        QTimer.singleShot(400, lambda: self.suggestionReady.emit("Tip: say “Aries, open Maps”"))