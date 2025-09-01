from PyQt5.QtWidgets import QWidget, QLabel, QGraphicsDropShadowEffect, QGraphicsBlurEffect
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer

class FloatingCard(QWidget):
    """
    A translucent, frosted notification card with drop shadow,
    fade-in/out, and optional blur-behind effect.
    """
    def __init__(self, text="", parent=None, radius=20, blur_behind=False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Content label
        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        # Helvetica Neue, fallback to Arial
        font = QFont("Helvetica Neue", 12)
        if not font.exactMatch():
            font = QFont("Arial", 12)
        self.label.setFont(font)
        self.label.setStyleSheet("color: #333333;")
        self.label.setAlignment(Qt.AlignCenter)

        self._radius = radius
        self._blur = None

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        # Optional blur-behind
        if blur_behind:
            blur = QGraphicsBlurEffect(self)
            blur.setBlurRadius(12)
            self._blur = blur

        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Frosted white background
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)
        painter.end()

    def showMessage(self, text, duration=3000):
        """
        Display `text` for `duration` ms with fade-in, hold, fade-out.
        """
        self.label.setText(text)
        # Resize to fit content + padding
        self.label.adjustSize()
        w = self.label.width() + 24
        h = self.label.height() + 16
        self.resize(w, h)
        self.label.move(12, 8)

        # Initial state
        self.setWindowOpacity(0.0)
        self.show()

        # Fade in
        fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        fade_in.setDuration(250)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        fade_in.start()

        # Schedule fade out
        QTimer.singleShot(duration, self._fadeOut)

    def _fadeOut(self):
        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(400)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)
        fade_out.start()
        fade_out.finished.connect(self.hide)
