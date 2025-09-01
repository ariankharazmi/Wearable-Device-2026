from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt5.QtCore import pyqtSignal

class AssistantPane(QWidget):
    commandReceived = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#181818;color:white;")

        layout = QVBoxLayout(self)
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("background:#282828;color:white;border:none;font:14px 'SF Pro Text';")
        layout.addWidget(self.text_area)

    def commandReceived(self, command):
        self.text_area.append(f"> {command}")