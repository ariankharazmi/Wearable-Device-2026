# apps/base_pane.py
from PyQt5.QtWidgets import QWidget, QPushButton
from PyQt5.QtCore import pyqtSignal, Qt

class BasePane(QWidget):
    """All app‐pages inherit this to get a standard Home button."""
    goHomeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Home button
        btn = QPushButton("← Home", self)
        btn.setFixedSize(80, 28)
        btn.move(12, 12)
        btn.clicked.connect(self.goHomeRequested.emit)
        # Make sure any content sits below the button
        self.setContentsMargins(0, 48, 0, 0)

    def onShow(self):
        """Called when this pane is about to be shown."""
        pass

    def onHide(self):
        """Called when this pane is about to be hidden."""
        pass