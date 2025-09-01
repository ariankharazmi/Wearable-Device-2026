import cv2, time, os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt

class VideoPane(QWidget):
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        self.recording = False
        self.writer = None
        layout = QVBoxLayout(self)
        self.rec_btn = QPushButton("● Start Recording")
        layout.addWidget(self.rec_btn)
        self.rec_btn.clicked.connect(self.toggle)
        self.status = QLabel("Not recording", alignment=Qt.AlignCenter)
        layout.addWidget(self.status,1)

    def toggle(self):
        if not self.recording:
            ts = int(time.time())
            os.makedirs("videos",exist_ok=True)
            path = f"videos/{ts}.avi"
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            size = (640,480)
            self.writer = cv2.VideoWriter(path,fourcc,20.0,size)
            self.recording = True
            self.rec_btn.setText("■ Stop Recording")
            self.status.setText(f"Recording to {path}")
        else:
            self.writer.release()
            self.recording = False
            self.rec_btn.setText("● Start Recording")
            self.status.setText("Not recording")

    def process_frame(self, frame):
        if self.recording and self.writer:
            self.writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))