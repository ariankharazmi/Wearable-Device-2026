# Software/Taka Software Edits/ui_layer_apps/settings_pane.py
# =============================================================================
# SETTINGS PANE (MVP)
# -----------------------------------------------------------------------------
# WHAT THIS DOES
#   - Shows a handful of system toggles / values backed by ctx.store + config
#   - Voice commands to flip settings (good for hands-free)
#   - Demonstrates how panes should update shared state and give feedback
#
# VOICE EXAMPLES
#   - "toggle background removal"
#   - "set background blur"
#   - "set brightness to 70"
#   - "volume up" / "volume down"
#   - "hotword is hey vision"   (changes ctx.config['voice_hotword'])
# =============================================================================

from __future__ import annotations
from ..main_ui_layer.pane_base import Pane

def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))

class SettingsPane(Pane):
    id = "settings"
    title = "Settings"
    icon = "icons/icon-settings.png"

    def on_mount(self) -> None:
        # initialize defaults if not present
        store = self.ctx.store
        store.setdefault("brightness", 70)   # 0..100
        store.setdefault("volume", 50)       # 0..100
        # reflect features flags from config for display
        feats = self.ctx.config.get("features", {})
        self._bg_remove = bool(feats.get("background_removal", False))
        self._bg_mode = feats.get("background_mode", "black")

    def render(self) -> None:
        y = 72
        self.ctx.overlay.card(self.title, "Say 'toggle background removal' or 'volume up'")
        self.ctx.overlay.text(f"Brightness: {self.ctx.store['brightness']}%", 12, y, size=16); y += 22
        self.ctx.overlay.text(f"Volume:     {self.ctx.store['volume']}%", 12, y, size=16); y += 22
        self.ctx.overlay.text(f"Background: {'ON' if self._bg_remove else 'OFF'} ({self._bg_mode})", 12, y, size=16); y += 22
        self.ctx.overlay.text(f"Hotword:    {self.ctx.config.get('voice_hotword', 'hey vision')}", 12, y, size=16)

    def on_voice(self, text: str) -> None:
        t = (text or "").strip().lower()

        # Background removal toggle
        if "toggle background removal" in t:
            self._bg_remove = not self._bg_remove
            self.ctx.config.setdefault("features", {})["background_removal"] = self._bg_remove
            self.ctx.overlay.toast(f"Background {'ON' if self._bg_remove else 'OFF'}")
            return

        # Background blur/black
        if "set background blur" in t:
            self._bg_mode = "blur"
            self.ctx.config.setdefault("features", {})["background_mode"] = "blur"
            self.ctx.overlay.toast("Background mode: blur")
            return
        if "set background black" in t:
            self._bg_mode = "black"
            self.ctx.config.setdefault("features", {})["background_mode"] = "black"
            self.ctx.overlay.toast("Background mode: black")
            return

        # Brightness
        if t.startswith("set brightness to "):
            try:
                val = int(t.split("set brightness to ", 1)[1].strip().split("%")[0])
                self.ctx.store["brightness"] = _clamp(val, 0, 100)
                self.ctx.overlay.toast(f"Brightness {self.ctx.store['brightness']}%")
            except Exception:
                self.ctx.overlay.toast("Say: set brightness to 70")
            return

        # Volume up/down
        if "volume up" in t:
            self.ctx.store["volume"] = _clamp(self.ctx.store["volume"] + 10, 0, 100)
            self.ctx.overlay.toast(f"Volume {self.ctx.store['volume']}%")
            return
        if "volume down" in t:
            self.ctx.store["volume"] = _clamp(self.ctx.store["volume"] - 10, 0, 100)
            self.ctx.overlay.toast(f"Volume {self.ctx.store['volume']}%")
            return

        # Hotword
        if t.startswith("hotword is "):
            new_hw = text.split("hotword is ", 1)[1].strip()
            if new_hw:
                self.ctx.config["voice_hotword"] = new_hw
                self.ctx.overlay.toast(f"Hotword: {new_hw}")
            return
