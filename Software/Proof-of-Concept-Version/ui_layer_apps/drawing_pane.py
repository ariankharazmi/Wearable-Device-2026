# drawing_pane.py

import cv2, numpy as np
import mediapipe as mp
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor

class DrawingPane(QWidget):
    """
    Air-drawing canvas: track your index fingertip
    and draw a freehand stroke in 2D.
    """
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAutoFillBackground(False)

        # Mediapipe hand tracker
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.path = []  # list of QPointF

        # throttle to 15fps
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(66)

    def step(self):
        pix = self.camera.pixmap()
        if pix is None or pix.isNull():
            return

        # convert to RGB numpy
        img = pix.toImage().convertToFormat(pix.toImage().Format_RGB888)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.byteCount())
        arr = np.frombuffer(ptr, np.uint8).reshape(h,w,3)
        rgb = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        # detect hand + index fingertip
        res = self.hands.process(rgb)
        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
            x = int(lm.x * self.width())
            y = int(lm.y * self.height())
            self.path.append((x,y))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        pen = QPen(QColor(0,255,0,200), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        for i in range(1, len(self.path)):
            p.drawLine(self.path[i-1][0], self.path[i-1][1],
                       self.path[i][0], self.path[i][1])
        p.end()