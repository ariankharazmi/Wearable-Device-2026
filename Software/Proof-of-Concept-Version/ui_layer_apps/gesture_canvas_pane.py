import cv2
import numpy as np
import mediapipe as mp
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QTimer

class GestureCanvasPane(QWidget):
    """
    Pane that overlays gesture-based drawing on top of the camera feed.
    Pinch (index-thumb) draws on a persistent canvas.
    """
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        self.view = QLabel(self)
        self.view.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.view)

        # Canvas for drawing
        self.canvas = None
        self.drawing = False
        self.prev_pt = None

        # MediaPipe Hands
        try:
            self.hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.6
            )
            self.mp_draw = mp.solutions.drawing_utils
            self.gesture_enabled = True
        except Exception:
            self.hands = None
            self.gesture_enabled = False

        # Update loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def update_frame(self):
        pix = self.camera.pixmap()
        if pix is None or pix.isNull():
            return
        # Convert to CV
        img = self.qpixmap_to_cv(pix)
        h, w, _ = img.shape

        if self.canvas is None:
            self.canvas = np.zeros_like(img)

        if self.gesture_enabled:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            res = self.hands.process(rgb)
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                # get tip of index finger and thumb
                tip_i = lm.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
                tip_t = lm.landmark[mp.solutions.hands.HandLandmark.THUMB_TIP]
                pt_i = (int(tip_i.x*w), int(tip_i.y*h))
                pt_t = (int(tip_t.x*w), int(tip_t.y*h))
                # distance
                d = np.hypot(pt_i[0]-pt_t[0], pt_i[1]-pt_t[1]) / max(w,h)
                # pinch threshold
                if d < 0.05:
                    if self.prev_pt:
                        cv2.line(self.canvas, self.prev_pt, pt_i, (0,255,0), 4)
                    self.prev_pt = pt_i
                else:
                    self.prev_pt = None

        # Overlay canvas on frame
        overlay = cv2.addWeighted(img, 1.0, self.canvas, 0.7, 0)
        qpix = self.cv_to_qpixmap(overlay)
        self.view.setPixmap(qpix.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        ))

    def qpixmap_to_cv(self, pix):
        img = pix.toImage().convertToFormat(QImage.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.constBits(); ptr.setsize(img.byteCount())
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

    def cv_to_qpixmap(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)
