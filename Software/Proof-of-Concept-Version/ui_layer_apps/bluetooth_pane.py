from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout
from PyQt5.QtGui     import QFont
from PyQt5.QtCore    import Qt, QTimer

class BluetoothPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #202020;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("🔗 Tether (Bluetooth)", self)
        title.setFont(QFont("SF Pro Text", 24, QFont.Medium))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)

        self.list = QListWidget(self)
        self.list.setStyleSheet(
            "background: #2C2C2C; color: #EEE; border: none; border-radius: 6px; padding: 4px;"
        )

        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect", self)
        self.disconnect_btn = QPushButton("Disconnect", self)

        for btn in (self.connect_btn, self.disconnect_btn):
            btn.setFont(QFont("SF Pro Text", 14))
            btn.setStyleSheet(
                "background: #007AFF; color: white; border: none; border-radius: 6px; padding: 8px;"
            )
            btn_layout.addWidget(btn)

        layout.addWidget(title)
        layout.addWidget(self.list, 1)
        layout.addLayout(btn_layout)

        # Comment out Bluetooth functionality for macOS development
        # self.scan_devices()
        # self.connect_btn.clicked.connect(self.connect_device)
        # self.disconnect_btn.clicked.connect(self.disconnect_device)
        #
        # self.scan_timer = QTimer(self)
        # self.scan_timer.timeout.connect(self.scan_devices)
        # self.scan_timer.start(30_000)

        # Stubbed functionality for development
        self.list.addItem("🔋 Device A (Stub)")
        self.list.addItem("🔋 Device B (Stub)")
        self.connect_btn.clicked.connect(lambda: self.list.addItem("Connecting to Device A (Stub)..."))
        self.disconnect_btn.clicked.connect(lambda: self.list.addItem("Disconnected (Stub)"))

    # Comment out these methods for now
    # def scan_devices(self):
    #     self.list.clear()
    #     try:
    #         devices = bluetooth.discover_devices(lookup_names=True, duration=3)
    #         for addr, name in devices:
    #             self.list.addItem(f"🔋 {name} ({addr})")
    #         if not devices:
    #             self.list.addItem("No devices found")
    #     except Exception as e:
    #         self.list.addItem(f"Error: {str(e)}")
    #
    # def connect_device(self):
    #     selected = self.list.currentItem()
    #     if selected and "No devices" not in selected.text():
    #         addr = selected.text().split("(")[-1].strip(")")
    #         try:
    #             self.list.addItem(f"Connecting to {addr}...")
    #         except Exception as e:
    #             self.list.addItem(f"Connection failed: {str(e)}")
    #
    # def disconnect_device(self):
    #     selected = self.list.currentItem()
    #     if selected:
    #         self.list.addItem("Disconnected (Stub)")

    # Note: To enable Bluetooth on Raspberry Pi Zero 2:
    # 1. Install BlueZ: sudo apt-get install bluetooth bluez libbluetooth-dev libudev-dev
    # 2. Install pybluez: sudo pip install pybluez
    # 3. Uncomment the above methods and remove the stubbed code