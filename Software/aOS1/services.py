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
        If t
