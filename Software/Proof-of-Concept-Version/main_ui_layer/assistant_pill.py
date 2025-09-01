from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

class AssistantPillIcon(QLabel):
    def __init__(self, icon_path, parent=None):
        super().__init__(parent)
        pixmap = QPixmap(icon_path)
        if pixmap.isNull():
            print(f"⚠️ AssistantPillIcon failed to load image: {icon_path}")
            self.setStyleSheet("background-color: rgba(255, 255, 255, 20); border-radius: 35px;")
            self.setFixedSize(70, 70)
            return

        self.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 20); border-radius: 35px;")
        self.setFixedSize(70, 70)
