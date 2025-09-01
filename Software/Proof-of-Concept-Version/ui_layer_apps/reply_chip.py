from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt

class ReplyChip(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            background-color: rgba(255, 255, 255, 20);
            color: white;
            font-size: 13px;
            padding: 6px 14px;
            border-radius: 16px;
        """)
        self.setAlignment(Qt.AlignCenter)
        self.adjustSize()
        self.setCursor(Qt.PointingHandCursor)
