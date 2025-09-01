from PyQt5.QtWidgets import QWidget, QVBoxLayout, QListWidget, QPushButton, QLabel
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import bleak

class CallPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self)
        font=QFont("Helvetica Neue",14)
        if not font.exactMatch(): font=QFont("Arial",14)
        self.list = QListWidget(); self.list.setFont(font)
        self.call_btn = QPushButton("📞 Call")
        layout.addWidget(QLabel("Select device:",alignment=Qt.AlignLeft))
        layout.addWidget(self.list)
        layout.addWidget(self.call_btn)
        self.call_btn.clicked.connect(self._dial)
        self._scan()

    def _scan(self):
        # placeholder scan
        self.list.addItem("+1 555 123 4567 (Example")

    def _dial(self):
        num = self.list.currentItem().text()
        # integrate HFP commands here
        print(f"Dialing {num}")