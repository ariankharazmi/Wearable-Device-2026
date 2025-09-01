import time, os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt

class PhotoPane(QWidget):
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,20)
        self.capture_btn = QPushButton("⦿ Capture Photo")
        font = QFont("Helvetica Neue", 14)
        if not font.exactMatch(): font = QFont("Arial",14)
        self.capture_btn.setFont(font)
        layout.addWidget(self.capture_btn)
        self.thumb = QLabel(alignment=Qt.AlignCenter)
        layout.addWidget(self.thumb,1)
        self.capture_btn.clicked.connect(self._capture)

    def _capture(self):
        pix = self.camera.pixmap()
        if not pix or pix.isNull(): return
        ts = int(time.time())
        path = f"photos/{ts}.png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pix.save(path)
        self.thumb.setPixmap(pix.scaled(200,200,Qt.KeepAspectRatio))