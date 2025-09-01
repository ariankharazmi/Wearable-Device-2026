import cv2
import numpy as np
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtCore import QTimer, Qt

class CameraFeed(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("Error: Could not open camera at index 0. Trying index 1...")
            self.cap = cv2.VideoCapture(1)
            if not self.cap.isOpened():
                print("Error: No camera available.")
                self.image = QImage()
                return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        self.image = QImage()

        timer = QTimer(self)
        timer.timeout.connect(self.update_frame)
        timer.start(1000 // 30)

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            self.image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(self.image)
            if not pixmap.isNull():
                self.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                print("Error: Failed to convert QImage to QPixmap")
        else:
            print("Error: Failed to capture frame.")

    def pixmap(self):
        return QPixmap.fromImage(self.image) if not self.image.isNull() else None

    def paintEvent(self, event):
        if not self.image.isNull():
            pixmap = QPixmap.fromImage(self.image).scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter = QPainter(self)
            painter.drawPixmap(0, 0, pixmap)

    def closeEvent(self, event):
        if self.cap.isOpened():
            self.cap.release()
        super().closeEvent(event)