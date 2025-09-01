from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt5.QtGui     import QFont, QPixmap
from PyQt5.QtCore    import Qt

class MapsPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #121212;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("🗺️ Maps", self)
        title.setFont(QFont("SF Pro Text", 24, QFont.Medium))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)

        self.map_view = QGraphicsView(self)
        self.map_scene = QGraphicsScene(self)
        self.map_view.setScene(self.map_scene)
        self.map_view.setStyleSheet("background: #1A1A1A; border: none; border-radius: 8px;")

        map_pixmap = QPixmap("VisionAriesAssets/map_placeholder.png")
        if map_pixmap.isNull():
            map_pixmap = QPixmap(400, 300)
            map_pixmap.fill(Qt.gray)
        map_item = QGraphicsPixmapItem(map_pixmap)
        self.map_scene.addItem(map_item)

        route_label = QLabel("🚨 Evacuation Route: Exit 500m North", self.map_view)
        route_label.setFont(QFont("SF Pro Text", 14))
        route_label.setStyleSheet("color: #FF5555; background: rgba(0,0,0,0.7); padding: 8px;")
        route_label.move(10, 10)

        layout.addWidget(title)
        layout.addWidget(self.map_view, 1)