# ar_overlay.py
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
import cv2

class AROverlayManager(QObject):
    overlayUpdated = pyqtSignal(object)    # QPixmap
    commandReceived = pyqtSignal(str)

    def __init__(self, camera_widget, ctx_assistant, parent=None):
        super().__init__(parent)
        self.camera = camera_widget
        self.ctx = ctx_assistant
        # connect to frameOverlay for follow-me annotation
        self.ctx.frameOverlay.connect(self._on_frame)

    def _on_frame(self, pixmap):
        # Emit directly back for main to update
        self.overlayUpdated.emit(pixmap)

    # Existing gesture or voice events can emit via commandReceived
    # No extra QGraphicsScene drawing here, handled in main