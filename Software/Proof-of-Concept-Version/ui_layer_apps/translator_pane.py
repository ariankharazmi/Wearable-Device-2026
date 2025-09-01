import pytesseract
from googletrans import Translator
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

class TranslatorPane(QWidget):
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        self.translator = Translator()
        layout = QVBoxLayout(self)
        font = QFont("Helvetica Neue",14)
        if not font.exactMatch(): font = QFont("Arial",14)
        self.src_label = QLabel("[Original Text]", alignment=Qt.AlignCenter)
        self.src_label.setFont(font)
        self.dst_label = QLabel("[Translation]", alignment=Qt.AlignCenter)
        self.dst_label.setFont(font)
        layout.addWidget(self.src_label)
        layout.addWidget(self.dst_label)

    def translate_current(self, text):
        self.src_label.setText(text)
        res = self.translator.translate(text, dest='en')
        self.dst_label.setText(res.text)