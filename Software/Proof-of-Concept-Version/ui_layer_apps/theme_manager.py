from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QApplication
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt

class ThemeManager(QWidget):
    """
    Pane to toggle between light/dark/adaptive themes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.btn = QPushButton("Toggle Theme", self)
        layout.addWidget(self.btn)
        self.dark = False
        self.btn.clicked.connect(self.toggle)

    def toggle(self):
        app = QApplication.instance()
        p = app.palette()
        if not self.dark:
            p.setColor(QPalette.Window, QColor(30,30,30))
            p.setColor(QPalette.WindowText, Qt.white)
        else:
            p.setColor(QPalette.Window, Qt.white)
            p.setColor(QPalette.WindowText, Qt.black)
        app.setPalette(p)
        self.dark = not self.dark
        self.btn.setText("Dark Mode" if not self.dark else "Light Mode")
