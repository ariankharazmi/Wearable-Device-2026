# aOS1/main_ui_layer/pane_base.py
# Base class for all panes (Bluetooth, Maps, Assistant, etc.)
# Keep panes lightweight: they receive a shared `ctx` with services
# (overlay, event_bus, camera, voice, notify, assets, store, config, display).

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional

class Pane(ABC):
    """
    Minimal lifecycle & event surface for a UI pane.

    Subclass this in ui_layer_apps, e.g.:
        class BluetoothPane(Pane):
            id = "bluetooth"
            title = "Bluetooth"
            icon = "icons/icon-bluetooth.png"

            def render(self):
                self.ctx.overlay.card(self.title, "Say 'pair device' or 'disconnect'")

            def on_voice(self, text: str):
                if "pair" in text:
                    self.ctx.bluetooth.pair_mode()
                    self.ctx.overlay.toast("Pairing…")
    """

    # Unique identity for routing/telemetry
    id: str = "pane"
    # Short title for headers/cards
    title: str = "Pane"
    # Relative icon path inside VA-Assets (optional)
    icon: Optional[str] = None

    def __init__(self) -> None:
        self.ctx: Any = None            # populated by mount()
        self._mounted: bool = False

    # ----- Lifecycle ---------------------------------------------------------

    def mount(self, ctx: Any) -> None:
        """Called when the pane becomes active."""
        self.ctx = ctx
        self._mounted = True
        self.on_mount()

    def unmount(self) -> None:
        """Called when the pane is deactivated."""
        try:
            self.on_unmount()
        finally:
            self._mounted = False
            self.ctx = None

    def on_mount(self) -> None:
        """Optional: init resources, subscribe to events, warm caches."""
        pass

    def on_unmount(self) -> None:
        """Optional: release resources, unsubscribe, stop timers."""
        pass

    # ----- Draw loop ---------------------------------------------------------

    @abstractmethod
    def render(self) -> None:
        """Draw the pane each frame. Use ctx.overlay.* helpers."""
        raise NotImplementedError

    # ----- Inputs / events ---------------------------------------------------

    def on_voice(self, text: str) -> None:
        """Normalized voice transcript for this pane."""
        pass

    def on_gesture(self, name: str, data: Any | None = None) -> None:
        """High-level gesture events (e.g., 'tap', 'swipe_left')."""
        pass

    def on_action(self, name: str, **payload: Any) -> None:
        """Generic actions routed from the system (e.g., notifications)."""
        pass

    # ----- Helpers -----------------------------------------------------------

    def ensure_mounted(self) -> None:
        if not self._mounted:
            raise RuntimeError(f"{self.id} not mounted before use")

    def toast(self, msg: str) -> None:
        """Quick user feedback helper."""
        self.ensure_mounted()
        self.ctx.overlay.toast(msg)
