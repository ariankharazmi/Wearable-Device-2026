# apps/music_pane.py
import os

from PyQt5.QtWidgets import QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from .base_pane import BasePane

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    spotipy = None

class MusicPane(BasePane):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)

        if spotipy is None:
            # spotipy not installed at all
            msg = "MusicPane unavailable\n(spotipy not installed)"
            print(f"⚠️ MusicPane disabled: spotipy missing")
            layout.addWidget(self._make_label(msg))
            return

        # attempt to get client credentials from env
        client_id     = os.getenv("SPOTIPY_CLIENT_ID")
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        redirect_uri  = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

        if not client_id or not client_secret:
            msg = "MusicPane disabled\n(set SPOTIPY_CLIENT_ID & SECRET)"
            print(f"⚠️ MusicPane disabled: missing SPOTIPY_CLIENT_ID/SECRET")
            layout.addWidget(self._make_label(msg))
            return

        # finally, try to instantiate the Spotify client
        try:
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="user-read-playback-state,user-modify-playback-state",
                open_browser=False
            )
            self.sp = spotipy.Spotify(auth_manager=auth)
            # If you want, build out your real UI here...
            layout.addWidget(self._make_label("🎵 Music Ready"))
        except Exception as e:
            msg = f"MusicPane disabled\n({e})"
            print(f"⚠️ MusicPane disabled: {e}")
            layout.addWidget(self._make_label(msg))

    def _make_label(self, text):
        lbl = QLabel(text, alignment=Qt.AlignCenter)
        lbl.setStyleSheet("color:white; font:14px;")
        return lbl


class MusicPaneUnavailable:
    pass