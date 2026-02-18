# Software/Taka Software Edits/ui_layer_apps/launcher_pane.py
# =============================================================================
# LAUNCHER PANE (Pi-friendly)
# -----------------------------------------------------------------------------
# What this is:
#   - Lightweight "home screen" pane that lets the user switch to other panes.
#   - Uses text-first UI via ctx.overlay so it runs on low-power hardware.
#   - Voice examples: "next", "previous", "open wifi", "open camera", "open settings".
#
# How it integrates:
#   - Inherits from Pane (pane_base.py).
#   - Emits ctx.event_bus NAVIGATE events so main.py can switch panes.
#   - Appears as id="launcher" so you can make it the default_pane in config.yaml.
# =============================================================================

from __future__ import annotations
import os, sys

from Leonardo_Software_Edits.main_ui_layer.pane_base import Pane

class SettingsPane(Pane):
    ...
    def draw(self):
        self.render()

    def handle_input(self, input_event=None):
        pass


# Robust import (works when registry loads by path)
try:
    from ..main_ui_layer.pane_base import Pane
except Exception:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ML = os.path.join(BASE, "main_ui_layer")
    if ML not in sys.path:
        sys.path.insert(0, ML)
    from pane_base import Pane  # type: ignore


class LauncherPane(Pane):
    id = "launcher"
    title = "Launcher"
    icon = "icons/icon-launcher.png"  # optional: add icon to VA-Assets/icons

    def on_mount(self) -> None:
        """
        Build a small app list. Each row: (Display Label, pane_id, icon_path)
        - pane_id must match the .id of the target pane class.
        - You can add/remove rows freely.
        """
        self.apps = [
            ("Wi-Fi",     "wifi",     "icons/icon-wifi.png"),
            ("Settings",  "settings", "icons/icon-settings.png"),
            ("Camera",    "camera",   "icons/icon-camera.png"),
        ]
        self.sel = 0
        self._hint = "Say: 'next', 'previous', 'open wifi', 'open camera', 'open settings'"

    # ----------------------------- RENDER -------------------------------------
    def render(self) -> None:
        """
        Draw the launcher: a center selection with neighbors on each side.
        (We stick to text so this runs well on the Pi; icons are optional.)
        """
        w, h = self.ctx.display.width, self.ctx.display.height
        cx, cy = int(w * 0.5), int(h * 0.45)

        # Title + hint
        self.ctx.overlay.card(self.title, self._hint, x=12, y=None)

        # Show up to 5 items around current selection
        indices = range(self.sel - 2, self.sel + 3)
        for i, idx in enumerate(indices):
            label, _pid, _icon = self._get(idx)
            is_center = (i == 2)
            size = 30 if is_center else 22
            offset = (i - 2) * 170  # horizontal spacing
            # If you later implement overlay.icon(), you can draw icons here.
            # self.ctx.overlay.icon(_icon, cx + offset - 16, cy - 42, size=32)
            txt = f"▶ {label}" if is_center else label
            self.ctx.overlay.text(txt, cx + offset - (12 if is_center else 0), cy, size=size)

        # Status footer
        status = "Connected" if self.ctx.store.get("wifi_connected") else "Disconnected"
        self.ctx.overlay.text(f"Wi-Fi: {status}", 12, int(h * 0.88), size=16)

    # -------------------------- INPUT (VOICE) ---------------------------------
    def on_voice(self, text: str) -> None:
        """
        Minimal intents:
          • "next" / "previous"
          • "open <pane>", e.g. "open wifi" / "open settings" / "open camera"
        """
        t = (text or "").strip().lower()

        if t in ("next", "right", "go right"):
            self._move(+1); return
        if t in ("previous", "prev", "left", "go left"):
            self._move(-1); return

        if t.startswith("open "):
            name = t.split("open ", 1)[1].strip()
            pid = self._resolve_pane_id(name)
            if pid:
                self._open(pid)
            else:
                self.toast(f"Pane '{name}' not found")

    # ---------------------------- HELPERS -------------------------------------
    def _get(self, i: int):
        return self.apps[i % len(self.apps)]

    def _move(self, d: int) -> None:
        self.sel = (self.sel + d) % len(self.apps)

    def _resolve_pane_id(self, name: str) -> str | None:
        name = name.replace(" ", "").lower()
        for (label, pid, _icon) in self.apps:
            if pid == name or label.replace(" ", "").lower() == name:
                return pid
        return None

    def _open(self, pane_id: str) -> None:
        # Ask the main app loop to switch panes
        self.ctx.event_bus.emit("NAVIGATE", pane_id=pane_id)
        self.toast(f"Opening {pane_id}")
