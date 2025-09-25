# aOS1/main_ui_layer/services.py
# =============================================================================
# WHAT THIS FILE DOES (READ ME FIRST)
# -----------------------------------------------------------------------------
# 1) Loads config (screen size, assets, features) from config.yaml or defaults.
# 2) Builds a single shared "ctx" (context) object that every UI pane receives.
#    ctx is how panes access system services WITHOUT hard-coding dependencies.
#    Example: ctx.overlay, ctx.event_bus, ctx.camera, ctx.voice, ctx.notify, ...
# 3) Provides lightweight "facade" classes (Overlay, EventBus, etc.) and
#    safe fallbacks so the app can boot even if some modules aren't ready.
#
# WHY WE NEED THIS:
# - Keeps panes small and focused on UI logic.
# - Makes it easy to test panes locally (fake services) and swap hardware later.
# =============================================================================

from __future__ import annotations

import os
import queue
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

# ----------------------------- CONFIG LOADING --------------------------------
# We load config.yaml if it exists, otherwise use DEFAULT_CONFIG so devs can
# run without any setup.

try:
    import yaml  # pyyaml (in requirements.txt)
except Exception:  # If pyyaml isn't installed yet, we still run with defaults.
    yaml = None

# Default values keep us productive even before a config.yaml is added.
DEFAULT_CONFIG = {
    "display": {
        "width": 800,            # smart glasses panel width (px)
        "height": 480,           # smart glasses panel height (px)
        "ppi": 220,              # rough density; change later per device
        "safe_insets": [28, 12, 12, 12],  # top/right/bottom/left (status/pill areas)
        "fps": 30
    },
    "default_pane": "assistant",         # which pane opens on boot
    "enabled_panes": ["assistant", "bluetooth", "maps"],  # panes the OS loads
    "assets_dir": "VA-Assets",           # where icons/images live
    "model_path": "models/yolov5nu.pt",  # example ML model path
    "voice_hotword": "hey vision",       # wake phrase for voice manager
    "features": {
        "background_removal": False,     # if True: run a simple BG stripper
        "background_mode": "black"       # "black" | "blur" | "transparent" (future)
    }
}


def load_config(repo_root: Optional[str] = None) -> dict:
    """
    Try to read config.yaml at the repo root. If missing or YAML not installed,
    we log a note and continue with DEFAULT_CONFIG.
    """
    cfg = DEFAULT_CONFIG.copy()
    repo_root = repo_root or os.getcwd()
    path = os.path.join(repo_root, "config.yaml")

    if yaml and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            # Shallow merge is fine for our simple tree
            for k, v in user_cfg.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:
            print(f"[services] ⚠️  Failed to read config.yaml: {e}. Using defaults.")
    else:
        if not yaml:
            print("[services] ℹ️  pyyaml not installed yet; using DEFAULT_CONFIG.")
        else:
            print("[services] ℹ️  config.yaml not found; using DEFAULT_CONFIG.")

    return cfg


# ---------------------------- DISPLAY PROFILE --------------------------------
# This holds basic info about the physical/virtual display and a tiny dp() shim.

@dataclass
class DisplayProfile:
    width: int
    height: int
    ppi: int = 220
    safe_insets: tuple[int, int, int, int] = (28, 12, 12, 12)  # top, right, bottom, left
    fps: int = 30

    def dp(self, px: float) -> int:
        """
        Density-independent px. For now this returns int(px).
        If we switch to different screens later, adjust math here once.
        """
        return int(px)


# -------------------------------- EVENT BUS ----------------------------------
# Tiny, thread-safe FIFO queue. Everything in the system talks by posting events.
# Example events:
#   {"type": "NAVIGATE", "payload": {"pane_id": "maps"}}
#   {"type": "VOICE", "payload": {"text": "open bluetooth"}}

class EventBus:
    def __init__(self) -> None:
        import threading
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()

    def emit(self, type_: str, **payload: Any) -> None:
        self._q.put({"type": type_, "payload": payload})

    def next(self, block: bool = False, timeout: float = 0.0) -> dict:
        try:
            return self._q.get(block=block, timeout=timeout)
        except queue.Empty:
            return {"type": "NOP", "payload": {}}


# ------------------------------ ASSET LOADER ---------------------------------
# Panes should not worry about paths. They just request an icon name and we
# resolve it under VA-Assets.

class AssetLoader:
    def __init__(self, assets_dir: str) -> None:
        self.assets_dir = assets_dir

    def get_icon(self, name: str) -> str:
        """
        If a pane asks for "icon-bluetooth.png" we return "VA-Assets/icons/icon-bluetooth.png".
        If they pass a nested path already, we just join it under VA-Assets.
        """
        if os.path.sep in name:
            return os.path.join(self.assets_dir, name)
        return os.path.join(self.assets_dir, "icons", name)


# ---------------------------- OVERLAY (DRAWING) ------------------------------
# Thin façade that panes call to draw text/icons/cards/toasts. Internally we can
# implement this with your existing modules (ar_overlay, floating_card, etc.).
# For now, these methods are stubs with clear signatures so the app boots
# immediately and teammates see where to connect the real renderer.

class Overlay:
    def __init__(self, assets: AssetLoader, display: DisplayProfile) -> None:
        self.assets = assets
        self.display = display
        # Optional: import your real modules; if missing we keep stubs
        try:
            from . import ar_overlay  # noqa: F401
            self._has_ar = True
        except Exception:
            self._has_ar = False

    def begin_frame(self) -> None:
        """Called once per frame before drawing. Hook renderer start here."""
        pass

    def end_frame(self) -> None:
        """Called once per frame after drawing. Hook buffer swap here."""
        pass

    def draw_base(self, frame) -> None:
        """
        Draw a base image (e.g., camera frame after background removal).
        If the renderer handles camera elsewhere, this is a no-op.
        """
        _ = frame  # placeholder to avoid lints

    def text(self, s: str, x: int, y: int, size: int = 16, weight: str = "regular") -> None:
        """Draw text at (x, y). Implement with your renderer later."""
        _ = (s, x, y, size, weight)

    def icon(self, name: str, x: int, y: int, size: int = 24) -> None:
        """Draw an icon by logical name."""
        path = self.assets.get_icon(name)
        _ = (path, x, y, size)

    def card(self, title: str, body: str, x: int = 12, y: Optional[int] = None) -> None:
        """Standard card component (title + small body)."""
        _ = (title, body, x, y)

    def toast(self, s: str) -> None:
        """Quick feedback banner/snackbar."""
        _ = s


# -------------------------- DEVICE / SERVICE STUBS ---------------------------
# We try to import your existing managers. If not found, we provide minimal
# fallbacks so panes can run locally.

def _import_or_none(modpath: str) -> Optional[Any]:
    try:
        import importlib
        return importlib.import_module(modpath)
    except Exception:
        return None


class CameraManager:
    """
    Wraps camera access. If aOS1.main_ui_layer.camera.CameraManager exists,
    we use it. Otherwise, we fall back to OpenCV so everyone can develop.
    """
    def __init__(self) -> None:
        mod = _import_or_none("aOS1.main_ui_layer.camera") or _import_or_none("camera")
        if mod and hasattr(mod, "CameraManager"):
            self._impl = mod.CameraManager()  # use the project's real impl
            self._cv2 = None
            self._cap = None
        else:
            self._impl = None
            try:
                import cv2
                self._cv2 = cv2
                self._cap = cv2.VideoCapture(0)
            except Exception:
                self._cv2 = None
                self._cap = None

    def read(self):
        """Return (ok, frame). Always safe to call; will just return (False, None) if unavailable."""
        if self._impl:
            return self._impl.read()
        if self._cv2 and self._cap:
            ok, frame = self._cap.read()
            return ok, frame
        return False, None


class VoiceManager:
    """
    Minimal voice manager: in production this would use your real voice code.
    For now, we expose a method for the system to push transcripts into the bus.
    """
    def __init__(self, event_bus: EventBus, hotword: str) -> None:
        self.event_bus = event_bus
        self.hotword = hotword

    def push_transcript(self, text: str) -> None:
        """System/dev can call this to simulate voice input."""
        self.event_bus.emit("VOICE", text=text)


class NotificationCenter:
    """Simple wrapper so panes can show user feedback and we can also log."""
    def __init__(self, overlay: Overlay) -> None:
        self.overlay = overlay

    def info(self, msg: str) -> None:
        self.overlay.toast(msg)

    def error(self, msg: str) -> None:
        # We could style errors differently later
        self.overlay.toast(f"Error: {msg}")


# ---------------------------- OPTIONAL PROCESSORS ----------------------------
# Background removal: keep this simple so it runs on Pi. We can plug in a more
# advanced model later (e.g., Mediapipe segmentation or Coral TPU).

def simple_background_removal(frame, mode: str = "black"):
    """
    Very basic placeholder: returns a frame with the background darkened/black.
    This is intentionally naive so it runs everywhere. Replace later as needed.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return frame  # If OpenCV not available yet, just return the original

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Simple threshold; tune 90..140 depending on lighting
    _, mask = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY)
    fg = cv2.bitwise_and(frame, frame, mask=mask)

    if mode == "blur":
        blurred = cv2.GaussianBlur(frame, (21, 21), 0)
        bg = cv2.bitwise_and(blurred, blurred, mask=cv2.bitwise_not(mask))
    else:
        bg = np.zeros_like(frame)  # black

    return cv2.add(fg, bg)


# ------------------------------- FACTORY -------------------------------------
# This is the single function the app calls to build the shared context.

def make_services(repo_root: Optional[str] = None) -> Any:
    """
    Build and return the shared context (ctx). All panes receive this object
    in their `mount(ctx)` method.
    """
    # 1) Load config
    config = load_config(repo_root)

    # 2) Build display profile
    d = config["display"]
    display = DisplayProfile(
        width=int(d.get("width", 800)),
        height=int(d.get("height", 480)),
        ppi=int(d.get("ppi", 220)),
        safe_insets=tuple(d.get("safe_insets", [28, 12, 12, 12])),
        fps=int(d.get("fps", 30)),
    )

    # 3) Core services
    event_bus = EventBus()
    assets = AssetLoader(config["assets_dir"])
    overlay = Overlay(assets, display)
    camera = CameraManager()
    voice = VoiceManager(event_bus, config.get("voice_hotword", "hey vision"))
    notify = NotificationCenter(overlay)

    # 4) Optional placeholders (future wiring)
    ocr = _import_or_none("aOS1.main_ui_layer.ocr_manager") or _import_or_none("ocr_manager")
    detector = _import_or_none("aOS1.main_ui_layer.tpu_detector") or _import_or_none("tpu_detector")

    # 5) Simple global key-value store for tiny bits of shared state
    store = {"battery": 100, "net": "wifi", "gps": False}

    # 6) Return a single namespace with everything panes need
    ctx = SimpleNamespace(
        # Core
        event_bus=event_bus,
        overlay=overlay,
        assets=assets,
        display=display,
        config=config,
        store=store,
        # Devices/services
        camera=camera,
        voice=voice,
        notify=notify,
        ocr=ocr,
        detector=detector,
        # Utilities
        background_remove=simple_background_removal,
    )

    return ctx
