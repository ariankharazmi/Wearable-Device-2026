import requests
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

class NavPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        font = QFont("Helvetica Neue",14)
        if not font.exactMatch(): font = QFont("Arial",14)
        self.start = QLineEdit(placeholderText="Start address")
        self.dest  = QLineEdit(placeholderText="Destination")
        self.go    = QPushButton("Start Navigation")
        for w in (self.start,self.dest,self.go): w.setFont(font)
        self.steps = QLabel("", alignment=Qt.AlignLeft)
        self.steps.setFont(font)
        layout.addWidget(self.start)
        layout.addWidget(self.dest)
        layout.addWidget(self.go)
        layout.addWidget(self.steps,1)
        self.go.clicked.connect(self._route)

    def _route(self):
        s = self.start.text(); d = self.dest.text()
        # placeholder: show dummy steps
        self.steps.setText(f"1. Head north from {s}\n2. Arrive at {d}")