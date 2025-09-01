import threading
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt

class LiveStreamPane(QWidget):
    """
    Pane to start/stop live video streaming over network.
    Stub implementation for RTSP/WebRTC.
    """
    def __init__(self, camera_feed, parent=None):
        super().__init__(parent)
        self.camera = camera_feed
        layout = QVBoxLayout(self)
        self.btn = QPushButton("Start Live Stream", self)
        self.status = QLabel("Stream stopped", alignment=Qt.AlignCenter)
        layout.addWidget(self.btn)
        layout.addWidget(self.status)
        self.btn.clicked.connect(self.toggle)
        self.streaming = False
        self.thread = None

    def toggle(self):
        if not self.streaming:
            self.streaming = True
            self.btn.setText("Stop Live Stream")
            self.status.setText("Streaming to rtsp://<your-ip>:8554/stream")
            # TODO: spawn thread to push frames
            self.thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.thread.start()
        else:
            self.streaming = False
            self.btn.setText("Start Live Stream")
            self.status.setText("Stream stopped")

    def _stream_loop(self):
        # Stub: grab frames and push to RTSP/WebRTC server
        while self.streaming:
            pix = self.camera.pixmap()
            # convert to CV and push...
            pass
