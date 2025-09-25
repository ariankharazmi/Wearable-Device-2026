# Software/Taka Software Edits/main_ui_layer/services.py
# =============================================================================
# SERVICES MODULE
# -----------------------------------------------------------------------------
# WHAT THIS FILE DOES:
#   - Loads settings from config.yaml or uses default values.
#   - Builds a shared context object (ctx) that contains:
#       * overlay   ? for drawing UI elements
#       * event_bus ? messaging between components
#       * camera    ? camera access
#       * voice     ? voice command system
#       * notify    ? toast notifications
#       * config    ? system-wide settings
#       * store     ? small key-value state storage
#   - Provides fallback implementations for hardware that may not exist yet
#     so the app can still run on developer machines.
#
# WHY WE NEED THIS:
#   - Separates hardware and services from UI code.
#   - Every pane can access the same tools without knowing how they're built.
#   - Example:
#         ctx = make_services()
#         wifi_pane.mount(ctx)
# =============================================================================

from __future__ import annotations
import os
import queue
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

# ---------------------------- CONFIG LOADING ----------------------------
try:
    import yaml  # for reading config.yaml
except ImportError:
    yaml = None  # will still run with defaults if pyyaml isn't installed

DEFAULT_CONFIG = {
    "display": {
        "width": 800,
        "height": 480,
        "ppi": 220,
        "safe_insets": [28, 12, 12, 12],
        "fps": 30
    },
    "default_pane": "launcher",
    "enabled_panes": ["launcher", "wifi", "settings"],
    "assets_dir": "VA-Assets",
    "voice_hotword": "hey vision",
    "features": {
        "background_removal": False,
        "background_mode": "black"
    }
}

def load_config(repo_root: Optional[str] = None) -> dict:
    """
    Loads config.yaml from the repo root if present.
    Otherwise falls back to DEFAULT_CONFIG.
    """
    cfg = DEFAULT_CONFIG.copy()
    repo_root = repo_root or os.getcwd()
    config_path = os.path.join(repo_root, "config.yaml")

    if yaml and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            # Merge user config into default
            for key, val in user_cfg.items():
                if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(val)
                else:
                    cfg[key] = val
        except Exception as e:
            print(f"[services] ?? Failed to read config.yaml: {e}")
    else:
        if not yaml:
            print("[services] ?? PyYAML not installed; using default config.")
        else:
            print("[services] ?? No config.yaml found; using default config.")
    return cfg

# ---------------------------- DISPLAY PROFILE ----------------------------
@dataclass
class DisplayProfile:
    """Represents display settings like size and density."""
    width: int
    height: int
    ppi: int = 220
    safe_insets: tuple[int, int, int, int] = (28, 12, 12, 12)
    fps: int = 30

    def dp(self, px: float) -> int:
        """Simple scaling helper for density-independent pixels."""
        return int(px)

# ---------------------------- EVENT BUS ---------------------------------
class EventBus:
    """Thread-safe queue for passing messages between parts of the app."""
    def __init__(self) -> None:
        self._q: "queue.Queue[dict]" = queue.Queue()

    def emit(self, type_: str, **payload: Any) -> None:
        self._q.put({"type": type_, "payload": payload})

    def next(self, block: bool = False, timeout: float = 0.0) -> dict:
        try:
            return self._q.get(block=block, timeout=timeout)
        except queue.Empty:
            return {"type": "NOP", "payload": {}}

# ---------------------------- ASSET LOADER -------------------------------
class AssetLoader:
    """Helps panes find images/icons inside VA-Assets directory."""
    def __init__(self, assets_dir: str) -> None:
        self.assets_dir = assets_dir

    def get_icon(self, name: str) -> str:
        if os.path.sep in name:
            return os.path.join(self.assets_dir, name)
        return os.path.join(self.assets_dir, "icons", name)

# ---------------------------- OVERLAY (UI DRAWING) -----------------------
class Overlay:
    """
    Provides a stable interface for drawing UI:
      - text()   ? draw text
      - icon()   ? draw icon
      - card()   ? draw info card
      - toast()  ? quick popup message
    """
    def __init__(self, assets: AssetLoader, display: DisplayProfile) -> None:
        self.assets = assets
        self.display = display

    def begin_frame(self): pass
    def end_frame(self): pass
    def draw_base(self, frame): pass

    def text(self, s: str, x: int, y: int, size: int = 16):
        print(f"[overlay] Draw text '{s}' at ({x},{y}) size {size}")

    def icon(self, name: str, x: int, y: int, size: int = 24):
        print(f"[overlay] Draw icon {name} at ({x},{y}) size {size}")

    def card(self, title: str, body: str, x: int = 12, y: Optional[int] = None):
        print(f"[overlay] Draw card {title}: {body}")

    def toast(self, s: str):
        print(f"[overlay] Toast: {s}")

# ---------------------------- CAMERA MANAGER -----------------------------
class CameraManager:
    """Manages camera input. Falls back to OpenCV if no custom camera module exists."""
    def __init__(self) -> None:
        try:
            import cv2
            self._cv2 = cv2
            self._cap = cv2.VideoCapture(0)
        except Exception:
            self._cv2 = None
            self._cap = None

    def read(self):
        if self._cv2 and self._cap:
            return self._cap.read()
        return False, None

# ---------------------------- VOICE MANAGER ------------------------------
class VoiceManager:
    """Manages voice commands (simulated for now)."""
    def __init__(self, event_bus: EventBus, hotword: str) -> None:
        self.event_bus = event_bus
        self.hotword = hotword

    def push_transcript(self, text: str):
        """Simulate receiving a voice command."""
        self.event_bus.emit("VOICE", text=text)

# ---------------------------- NOTIFICATION CENTER -----------------------
class NotificationCenter:
    """Simplifies sending notifications via overlay."""
    def __init__(self, overlay: Overlay) -> None:
        self.overlay = overlay

    def info(self, msg: str):
        self.overlay.toast(msg)

    def error(self, msg: str):
        self.overlay.toast(f"Error: {msg}")

# ---------------------------- MAKE SERVICES ------------------------------
def make_services(repo_root: Optional[str] = None) -> Any:
    """
    Creates and returns the shared context (ctx).
    This ctx is passed to every pane at mount() time.
    """
    config = load_config(repo_root)
    d = config["display"]

    display = DisplayProfile(
        width=d["width"],
        height=d["height"],
        ppi=d["ppi"],
        safe_insets=tuple(d["safe_insets"]),
        fps=d["fps"]
    )

    event_bus = EventBus()
    assets = AssetLoader(config["assets_dir"])
    overlay = Overlay(assets, display)
    camera = CameraManager()
    voice = VoiceManager(event_bus, config["voice_hotword"])
    notify = NotificationCenter(overlay)

    # A simple store for global state like battery %, WiFi status, etc.
    store = {
        "battery": 100,
        "wifi_connected": False,
        "volume": 50
    }

    # Bundle everything together in a SimpleNamespace
    ctx = SimpleNamespace(
        event_bus=event_bus,
        overlay=overlay,
        assets=assets,
        display=display,
        config=config,
        store=store,
        camera=camera,
        voice=voice,
        notify=notify
    )

    return ctx
