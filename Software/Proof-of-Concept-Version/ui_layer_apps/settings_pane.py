# apps/settings_pane.py
from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QTabWidget, QLabel, QCheckBox, QListWidget
)
from .base_pane import BasePane

class SettingsPane(BasePane):
    """Settings with 3 tabs: General, Bluetooth, About."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._bluetooth_tab(), "Bluetooth")
        tabs.addTab(self._about_tab(),   "About")

    def _general_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        contrast = QCheckBox("High-Contrast Mode")
        # you can hook this into VisionAriesUI.high_contrast later
        l.addWidget(contrast)
        l.addStretch()
        return w

    def _bluetooth_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Paired Devices:"))
        dev_list = QListWidget()
        # stub entries
        dev_list.addItems(["Keyboard", "Mouse", "Headset"])
        l.addWidget(dev_list)
        l.addStretch()
        return w

    def _about_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Vision Aries OS\nVersion 1.0 α·Build 1"))
        l.addWidget(QLabel("© 2025 Vision Aries Inc."))
        l.addStretch()
        return w