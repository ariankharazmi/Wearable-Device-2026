# apps/person_tracker_pane.py
import cv2
from PyQt5.QtWidgets import QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from .base_pane import BasePane

class PersonTrackerPane(BasePane):
    """
    Shows live camera with bounding boxes for “person” and
    follows the label around.
    """
    def __init__(self, camera_feed, ctx_assistant, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        self.ctx    = ctx_assistant

        layout = QVBoxLayout(self)
        self.lbl = QLabel(alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl)

        # Every time ContextualAssistant emits a new overlay frame:
        self.ctx.frameOverlay.connect(self._update_frame)

    def _update_frame(self, pixmap):
        # draw your bounding‐box overlay out of the pixmap
        self.lbl.setPixmap(
            pixmap.scaled(
                self.lbl.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def onShow(self):
        pass