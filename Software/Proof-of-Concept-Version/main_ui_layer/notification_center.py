# notification_center.py
import time
from PyQt5.QtCore import QThread, pyqtSignal

class NotificationCenter(QThread):
    notificationReceived = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notifications = [
            "🟢 Meeting in 5 min",
            "📬 New email from Alice",
            "⚙️ Update available",
            "📍 Arrival at GPS: 2 min"
        ]
        self.idx = 0

    def run(self):
        while True:
            time.sleep(15)
            msg = self.notifications[self.idx % len(self.notifications)]
            self.idx += 1
            self.notificationReceived.emit(msg)
