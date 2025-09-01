from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt

class SharedARPane(QWidget):
    """
    Pane to host or join collaborative AR annotation sessions.
    Stub implementation using WebRTC or socket.io would go here.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.status = QLabel("No session", alignment=Qt.AlignCenter)
        layout.addWidget(self.status)
        self.host_btn = QPushButton("Host Session", self)
        self.join_btn = QPushButton("Join Session", self)
        layout.addWidget(self.host_btn)
        layout.addWidget(self.join_btn)
        self.host_btn.clicked.connect(self.host_session)
        self.join_btn.clicked.connect(self.join_session)

    def host_session(self):
        # TODO: start WebRTC host
        self.status.setText("Hosting AR Session (stub)")

    def join_session(self):
        # TODO: connect to host
        self.status.setText("Joined AR Session (stub)")
