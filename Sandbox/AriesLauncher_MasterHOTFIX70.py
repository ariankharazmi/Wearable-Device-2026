import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys
import time
import threading
import struct
import enum
import logging
import subprocess
import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
import fcntl
from queue import Empty, Queue
from urllib.parse import quote_plus

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageGrab
try:
    from tkinterweb import HtmlFrame
except Exception:
    HtmlFrame = None
import platform

# Optional modules

try:
    import psutil
except Exception:
    psutil = None

try:
    import requests
except Exception:
    requests = None

try:
    import cv2
except Exception:
    cv2 = None

try:
    from google import genai
except Exception:
    genai = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import spidev
except Exception:
    spidev = None

try:
    import board
    import busio
except Exception:
    board = None
    busio = None

try:
    from adafruit_seesaw import seesaw as seesaw_module
    from adafruit_seesaw import rotaryio as seesaw_rotaryio
    from adafruit_seesaw import digitalio as seesaw_digitalio
except Exception:
    seesaw_module = None
    seesaw_rotaryio = None
    seesaw_digitalio = None

try:
    from circuitpython_cirque_pinnacle import PinnacleTouchSPI as PinnacleSPI
except Exception:
    try:
        from adafruit_cirque_pinnacle import PinnacleSPI
    except Exception:
        PinnacleSPI = None

try:
    from digitalio import DigitalInOut
except Exception:
    DigitalInOut = None

# Logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

if load_dotenv:
    load_dotenv()

# Platform

# Platform detection — covers RPi, Radxa, and other aarch64 SBCs
def _is_embedded_device():
    mach = platform.machine()
    if not mach.startswith(("armv7l", "armv6l", "aarch64")):
        return False
    # Raspberry Pi — platform string (older kernels)
    plat = platform.platform().lower()
    if "raspberrypi" in plat:
        return True
    # Check /sys/firmware/devicetree/base/model — most reliable on Pi 4/5
    for model_path in ("/sys/firmware/devicetree/base/model", "/proc/device-tree/model"):
        try:
            with open(model_path, "rb") as f:
                model = f.read().lower()
            if b"raspberry" in model:
                return True
        except Exception:
            pass
    # Check device-tree compatible string — Pi 5 uses "brcm" not "broadcom"
    for dt_path in ("/proc/device-tree/compatible", "/sys/firmware/devicetree/base/compatible"):
        try:
            with open(dt_path, "rb") as f:
                compat = f.read().lower()
            if any(k in compat for k in (
                b"radxa", b"amlogic", b"rockchip", b"allwinner",
                b"broadcom", b"brcm", b"raspberrypi",
            )):
                return True
        except Exception:
            pass
    # Hostname fallback
    try:
        import subprocess
        out = subprocess.check_output(["uname", "-n"], text=True).lower()
        if any(k in out for k in ("radxa", "rpi", "raspberry", "orangepi", "bananapi")):
            return True
    except Exception:
        pass
    return False

IS_PI = _is_embedded_device()

# Config

if IS_PI:
    WIDTH, HEIGHT = 640, 400
    TARGET_FPS = 30
    BASE_ICON = 92
    SPACING = 108
    FLOW_LAMBDA = 18.0
    SIZE_STEP_PX = 4
    ALPHA_STEP_8 = 32
else:
    WIDTH, HEIGHT = 1280, 720
    TARGET_FPS = 60
    BASE_ICON = 132
    SPACING = 180
    FLOW_LAMBDA = 26.0
    SIZE_STEP_PX = 2
    ALPHA_STEP_8 = 8

ASSETS_DIR = os.path.join(os.getcwd(), "VA-Assets (Colored, Fall 2025)")
PHOTOS_DIR = os.path.join(os.getcwd(), "AriesPhotos")
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(os.getcwd(), "aries_config.json")

_ICON_BASE_URL = (
    "https://raw.githubusercontent.com/ariankharazmi/"
    "VA1-Wearable-Device-2026/main/Sandbox/"
    "VA-Assets%20(Colored%2C%20Fall%202025)/"
)
_ICON_FILES = [
    "assistant.png", "bluetooth.png", "camera.png", "localassistant.png",
    "music.png", "photo.png", "plugin.png", "settings.png",
    "translate.png", "video.png", "browser.png", "power.png",
]

def _fetch_icons_if_missing():
    """Download missing icons from GitHub in a background thread."""
    missing = [f for f in _ICON_FILES if not os.path.exists(os.path.join(ASSETS_DIR, f))]
    if not missing:
        return
    logging.getLogger("Icons").info("Fetching %d missing icon(s) from GitHub...", len(missing))
    def _dl():
        try:
            import urllib.request
            for fname in missing:
                dest = os.path.join(ASSETS_DIR, fname)
                if os.path.exists(dest):
                    continue
                url = _ICON_BASE_URL + fname
                try:
                    urllib.request.urlretrieve(url, dest)
                    logging.getLogger("Icons").info("Downloaded %s", fname)
                except Exception as e:
                    logging.getLogger("Icons").warning("Failed to download %s: %s", fname, e)
        except Exception as e:
            logging.getLogger("Icons").warning("Icon fetch thread failed: %s", e)
    t = threading.Thread(target=_dl, name="IconFetch", daemon=True)
    t.start()
    t.join(timeout=15)  # Wait up to 15s at startup so icons appear immediately

_fetch_icons_if_missing()


HARDWARE_DEFAULTS = {
    "platform": "rpi",
    "touchpad": {
        "cs_candidates": ["CE0", "CE1", "D5"],
        "dr_candidates": ["D6", "D25", "D24"],
    },
    "rotary_gpio": {
        "clk": 17,
        "dt": 27,
        "sw": 22,
    },
}


def _hardware_config():
    cfg = _load_config()
    hw = cfg.get("hardware", {}) if isinstance(cfg, dict) else {}
    touchpad = hw.get("touchpad", {}) if isinstance(hw, dict) else {}
    rotary = hw.get("rotary_gpio", {}) if isinstance(hw, dict) else {}
    return {
        "platform": hw.get("platform", HARDWARE_DEFAULTS["platform"]),
        "touchpad": {
            "cs_candidates": touchpad.get("cs_candidates", HARDWARE_DEFAULTS["touchpad"]["cs_candidates"]),
            "dr_candidates": touchpad.get("dr_candidates", HARDWARE_DEFAULTS["touchpad"]["dr_candidates"]),
        },
        "rotary_gpio": {
            "clk": rotary.get("clk", HARDWARE_DEFAULTS["rotary_gpio"]["clk"]),
            "dt": rotary.get("dt", HARDWARE_DEFAULTS["rotary_gpio"]["dt"]),
            "sw": rotary.get("sw", HARDWARE_DEFAULTS["rotary_gpio"]["sw"]),
        },
    }


def _load_config():
    """Load saved settings from config file."""
    try:
        import json
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(data):
    """Save settings to config file."""
    try:
        import json
        existing = _load_config()
        existing.update(data)
        with open(CONFIG_PATH, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass

APPS = [
    ("assistant.png",      "Assistant"),
    ("bluetooth.png",      "Bluetooth"),
    ("camera.png",         "Camera"),
    ("localassistant.png", "Gemini"),
    ("photo.png",          "Photo"),
    ("settings.png",       "Settings"),
    ("translate.png",      "Translate"),
    ("browser.png",        "Browser"),
    ("power.png",          "Power"),
]

BUILD_STR = "VA-OS 1.4.13.26 Â· Pandora Build"

# Apple-inspired dark palette

C    = "#007AFF"       # Apple blue (accent)
CD   = "#0A84FF"       # Apple blue light
TXT  = "#FFFFFF"       # Primary text
TXTD = "#8E8E93"       # Secondary text (system gray)
BG   = "#000000"       # Pure black (AR transparent)
PNL  = "#1C1C1E"       # Apple system gray 6
PNLE = "#2C2C2E"       # Apple system gray 5
AMB  = "#FF9F0A"       # Apple orange
RED  = "#FF3B30"       # Apple red
GRN  = "#30D158"       # Apple green

# System font â€” pick best available
FONT = "Helvetica Neue"
FONT_MONO = "SF Mono"
for _f in ("SF Pro Display", "Helvetica Neue", "Segoe UI", "Helvetica"):
    FONT = _f
    break
for _f in ("SF Mono", "Menlo", FONT):
    FONT_MONO = _f
    break

SCALE_DROP = 0.14
ALPHA_DROP = 0.22

SITE_ALIASES = {
    "university of cincinnati": "https://www.uc.edu",
    "uc": "https://www.uc.edu",
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "reddit": "https://www.reddit.com",
    "github": "https://www.github.com",
}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Helpers
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _load(path):
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _make_ctk_image(img, size):
    if img is None:
        img = Image.new("RGBA", size, (0, 0, 0, 0))
    return ctk.CTkImage(light_image=img, dark_image=img, size=size)


def _start_safe_thread(target, name, log, *args, **kwargs):
    def _runner():
        try:
            target(*args, **kwargs)
        except Exception:
            log.exception("Background thread '%s' crashed", name)
    thread = threading.Thread(target=_runner, name=name, daemon=True)
    thread.start()
    return thread


def _circle(img, size):
    """Render icon as Apple-style rounded square (squircle)."""
    img = img.resize((size, size), Image.LANCZOS)
    r = int(size * 0.22)  # Corner radius ~22% like iOS
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size, size), radius=r, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _batt():
    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            b = psutil.sensors_battery()
            if b:
                return f"{int(b.percent)}%"
        except Exception:
            pass
    return "â€“%"


def _cpu():
    if psutil:
        try:
            return f"{psutil.cpu_percent(interval=0):.0f}%"
        except Exception:
            pass
    return "â€“%"


def _ram():
    if psutil:
        try:
            return f"{psutil.virtual_memory().percent:.0f}%"
        except Exception:
            pass
    return "â€“%"


def _time_str():
    now = datetime.now()
    try:
        return now.strftime("%-I:%M %p")
    except ValueError:
        return now.strftime("%#I:%M %p")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  StatusBar
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class StatusBar:
    """Apple-style minimal status bar â€” time left, system right."""
    def __init__(self, canvas):
        self.cv = canvas
        self._lines = []
        self._time_id = canvas.create_text(
            28, 18, anchor="nw", fill=TXT,
            font=(FONT, 13, "bold"), text="")
        self._sys_id = canvas.create_text(
            WIDTH - 28, 18, anchor="ne", fill=TXTD,
            font=(FONT, 11), text="")
        self._msg_id = canvas.create_text(
            WIDTH // 2, 18, anchor="n", fill=TXTD,
            font=(FONT, 10), text="")
        self._last = 0.0

    def append(self, msg):
        self._lines = (self._lines + [msg])[-1:]

    def tick(self):
        now = time.perf_counter()
        if now - self._last < 0.5:
            return
        self._last = now
        self.cv.itemconfigure(self._time_id, text=_time_str())
        self.cv.itemconfigure(self._sys_id,
                              text=f"BAT {_batt()}  CPU {_cpu()}  RAM {_ram()}")
        msg = self._lines[0] if self._lines else ""
        self.cv.itemconfigure(self._msg_id, text=msg)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Notification Toast
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Toast:
    """Apple-style pill notification."""
    def __init__(self, canvas):
        self.cv = canvas
        self._bg = canvas.create_rectangle(0, 0, 0, 0,
            fill=PNLE, outline="", width=0, state="hidden")
        self._txt = canvas.create_text(0, 0, text="", fill=TXT, anchor="n",
                                        font=(FONT, 12), state="hidden")
        self._after = None

    def show(self, msg, duration=2500):
        w = min(len(msg) * 8 + 48, WIDTH - 120)
        x = WIDTH // 2
        y = HEIGHT - 70
        self.cv.coords(self._bg, x - w // 2, y - 2, x + w // 2, y + 28)
        self.cv.coords(self._txt, x, y + 2)
        self.cv.itemconfigure(self._txt, text=msg)
        self.cv.itemconfigure(self._bg, state="normal")
        self.cv.itemconfigure(self._txt, state="normal")
        self.cv.tag_raise(self._bg)
        self.cv.tag_raise(self._txt)
        if self._after:
            self.cv.after_cancel(self._after)
        self._after = self.cv.after(duration, self.hide)

    def hide(self):
        self.cv.itemconfigure(self._bg, state="hidden")
        self.cv.itemconfigure(self._txt, state="hidden")




class DebugOverlay:
    """Hidden diagnostics HUD toggled on demand."""
    def __init__(self, canvas):
        self.cv = canvas
        self.visible = False
        self._bg = canvas.create_rectangle(
            14, 52, 274, 188, fill="#000000", outline="#2C2C2E", width=1, state="hidden"
        )
        self._txt = canvas.create_text(
            26, 64, anchor="nw", fill=TXT, font=(FONT_MONO, 10), text="", state="hidden"
        )

    def update(self, lines):
        self.cv.itemconfigure(self._txt, text="\n".join(lines))
        state = "normal" if self.visible else "hidden"
        self.cv.itemconfigure(self._bg, state=state)
        self.cv.itemconfigure(self._txt, state=state)
        if self.visible:
            self.cv.tag_raise(self._bg)
            self.cv.tag_raise(self._txt)

    def toggle(self):
        self.visible = not self.visible
        state = "normal" if self.visible else "hidden"
        self.cv.itemconfigure(self._bg, state=state)
        self.cv.itemconfigure(self._txt, state=state)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  VoiceController â€” demo-ready state machine
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#
#  States:  IDLE â†’ LISTENING â†’ PROCESSING â†’ IDLE
#
#  - No recording unless explicitly activated (push-to-talk via activate())
#  - Single worker thread per session, guarded by state lock
#  - Automatic stop after command recognized
#  - Debounce: ignores rapid re-activation within cooldown window
#  - Duplicate command filter within dedup window
#  - Clean shutdown via shutdown() â€” no stuck threads
#  - All UI updates dispatched through a callback, never touches tk directly
#

class VoiceState(enum.Enum):
    IDLE       = "IDLE"
    LISTENING  = "LISTENING"
    PROCESSING = "PROCESSING"


class VoiceController:
    """Modular push-to-talk voice controller with state machine."""

    COOLDOWN_SEC      = 1.5   # Min gap between activations
    DEDUP_SEC         = 2.0   # Ignore duplicate commands within this window
    LISTEN_TIMEOUT    = 6     # Seconds to wait for speech start
    PHRASE_LIMIT      = 10    # Max phrase recording length
    ENERGY_THRESHOLD  = 100   # Fixed low threshold (no dynamic adjustment)
    PAUSE_THRESHOLD   = 1.0   # Silence duration to end phrase

    def __init__(self, on_result=None, on_state=None, on_error=None,
                 mic_index=None):
        self.log = logging.getLogger("Voice")

        # Callbacks (all called from worker thread â€” caller must dispatch to UI)
        self._on_result = on_result   # fn(text: str)
        self._on_state  = on_state    # fn(state: VoiceState)
        self._on_error  = on_error    # fn(msg: str)

        # State
        self._state = VoiceState.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._last_activate = 0.0
        self._last_cmd = ""
        self._last_cmd_time = 0.0
        self._mic_index = mic_index
        self._shutdown = False

        # Recognizer setup
        self._recognizer = None
        if sr:
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = self.ENERGY_THRESHOLD
            self._recognizer.dynamic_energy_threshold = False
            self._recognizer.pause_threshold = self.PAUSE_THRESHOLD
            self.log.info("Recognizer ready (threshold=%d)", self.ENERGY_THRESHOLD)
        else:
            self.log.warning("speech_recognition not available")

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._recognizer is not None

    @property
    def mic_index(self):
        return self._mic_index

    @mic_index.setter
    def mic_index(self, val):
        self._mic_index = val
        self.log.info("Mic index set to %s", val)

    def _set_state(self, new_state):
        old = self._state
        self._state = new_state
        self.log.info("State: %s â†’ %s", old.value, new_state.value)
        if self._on_state:
            self._on_state(new_state)

    def activate(self):
        """Push-to-talk trigger. Call from UI thread."""
        if self._shutdown:
            return False

        if not self._recognizer:
            if self._on_error:
                self._on_error("Need: pip install SpeechRecognition pyaudio")
            return False

        # Debounce â€” ignore rapid re-activation
        now = time.perf_counter()
        if now - self._last_activate < self.COOLDOWN_SEC:
            self.log.debug("Activation debounced (%.1fs since last)",
                           now - self._last_activate)
            return False

        # Only activate from IDLE
        with self._lock:
            if self._state != VoiceState.IDLE:
                self.log.debug("Activation ignored â€” state is %s", self._state.value)
                return False
            self._set_state(VoiceState.LISTENING)

        self._last_activate = now
        self._stop_event.clear()

        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._worker, name="VoiceWorker", daemon=True)
        self._worker_thread.start()
        return True

    def cancel(self):
        """Cancel current listening session."""
        self._stop_event.set()
        self.log.info("Cancel requested")

    def shutdown(self):
        """Clean shutdown â€” stops any active session, prevents new ones."""
        self._shutdown = True
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)
            if self._worker_thread.is_alive():
                self.log.warning("Worker thread did not exit cleanly")
        with self._lock:
            self._set_state(VoiceState.IDLE)
        self.log.info("Shutdown complete")

    def _worker(self):
        """Background thread â€” records audio, runs STT, returns result."""
        text = ""
        source = None
        mic = None
        try:
            # Check for cancellation before opening mic
            if self._stop_event.is_set():
                return

            # Open microphone (configured → auto-detect → default)
            try:
                mic, source = self._open_microphone()
            except Exception as e:
                self.log.error("Microphone open failed: %s", e)
                if self._on_error:
                    self._on_error(f"Mic open failed: {e}")
                return

            # Check again after mic open
            if self._stop_event.is_set():
                return

            self.log.info("Listening (timeout=%ds, limit=%ds)",
                          self.LISTEN_TIMEOUT, self.PHRASE_LIMIT)
            audio = self._recognizer.listen(
                source,
                timeout=self.LISTEN_TIMEOUT,
                phrase_time_limit=self.PHRASE_LIMIT,
            )

            # Transition to PROCESSING
            with self._lock:
                if self._stop_event.is_set():
                    return
                self._set_state(VoiceState.PROCESSING)

            # Run Google STT
            self.log.info("Sending audio to Google STT â€¦")
            text = self._recognizer.recognize_google(audio)
            self.log.info("Recognized: '%s'", text)

        except sr.WaitTimeoutError:
            self.log.info("Timeout â€” no speech detected")
            if self._on_error:
                self._on_error("No speech â€” try again")

        except sr.UnknownValueError:
            self.log.info("Could not understand audio")
            if self._on_error:
                self._on_error("Couldn't understand â€” try again")

        except sr.RequestError as e:
            self.log.error("Google STT request failed: %s", e)
            if self._on_error:
                self._on_error(f"STT error: {e}")

        except OSError as e:
            self.log.error("Microphone OS error: %s", e)
            if self._on_error:
                self._on_error(f"Mic error: {e}")

        except Exception as e:
            self.log.error("Unexpected error: %s", e, exc_info=True)
            if self._on_error:
                self._on_error(f"Error: {e}")

        finally:
            if source is not None and mic is not None:
                try:
                    mic.__exit__(None, None, None)
                except Exception:
                    pass

            # Always return to IDLE
            with self._lock:
                self._set_state(VoiceState.IDLE)

            # Deliver result if we got one (with dedup check)
            if text and not self._stop_event.is_set():
                now = time.perf_counter()
                normalized = text.lower().strip()

                # Dedup â€” ignore identical command within window
                if (normalized == self._last_cmd
                        and now - self._last_cmd_time < self.DEDUP_SEC):
                    self.log.info("Duplicate command filtered: '%s'", normalized)
                    return

                self._last_cmd = normalized
                self._last_cmd_time = now

                if self._on_result:
                    self._on_result(text)

    @staticmethod
    def list_microphones():
        """Return list of (index, name) for available mics."""
        if not sr:
            return []
        try:
            names = sr.Microphone.list_microphone_names()
            return list(enumerate(names))
        except Exception:
            return []

    @staticmethod
    def auto_detect_mic():
        """Find the best microphone index, or None for system default."""
        for i, name in VoiceController.list_microphones():
            low = name.lower()
            if any(k in low for k in ("usb", "headset", "webcam",
                                       "microphone", "mic", "input")):
                return i
        return None

    def _open_microphone(self):
        """Prefer the configured mic, but gracefully fall back to auto/default."""
        candidates = []
        if self._mic_index is not None:
            candidates.append(self._mic_index)
        auto_idx = self.auto_detect_mic()
        if auto_idx is not None and auto_idx not in candidates:
            candidates.append(auto_idx)
        candidates.append(None)

        last_exc = None
        for idx in candidates:
            try:
                mic = sr.Microphone(device_index=idx) if idx is not None else sr.Microphone()
                source = mic.__enter__()
                if idx != self._mic_index:
                    self.log.info("Microphone fallback selected: %s", idx if idx is not None else "default")
                    self._mic_index = idx
                return mic, source
            except Exception as exc:
                last_exc = exc
        raise last_exc if last_exc else OSError("No working microphone found")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  RotaryController â€” GPIO click wheel input
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#
#  Hardware: Rotary encoder with push button (CLK, DT, SW)
#  - Clockwise rotation â†’ on_rotate(+1)
#  - Counter-clockwise â†’ on_rotate(-1)
#  - Short press (< 1s) â†’ on_click()
#  - Long press (â‰¥ 1s) â†’ on_long_press()
#  - All callbacks fire from GPIO interrupt thread
#  - Time-based debounce on both rotation and button
#  - Graceful fallback when GPIO unavailable (desktop dev)
#

class RotaryController:
    """GPIO rotary encoder with push button, debounced."""

    # Default pin assignments (BCM numbering)
    DEFAULT_CLK = 17
    DEFAULT_DT  = 27
    DEFAULT_SW  = 22

    # Timing
    ROTATE_DEBOUNCE_MS  = 5     # Debounce for rotation edges
    BUTTON_DEBOUNCE_MS  = 200   # Debounce for button press
    LONG_PRESS_SEC      = 1.0   # Hold time for long press

    def __init__(self, on_rotate=None, on_click=None, on_long_press=None,
                 clk_pin=None, dt_pin=None, sw_pin=None):
        self.log = logging.getLogger("Rotary")

        self._on_rotate     = on_rotate      # fn(direction: int)  +1 or -1
        self._on_click      = on_click        # fn()
        self._on_long_press = on_long_press   # fn()

        hw_cfg = _hardware_config()
        rotary_cfg = hw_cfg.get("rotary_gpio", {})
        self._clk = clk_pin or rotary_cfg.get("clk", self.DEFAULT_CLK)
        self._dt  = dt_pin  or rotary_cfg.get("dt", self.DEFAULT_DT)
        self._sw  = sw_pin  or rotary_cfg.get("sw", self.DEFAULT_SW)

        self._last_rotate_time  = 0.0
        self._button_down_time  = 0.0
        self._button_handled    = False
        self._active = False

        if not GPIO:
            self.log.info("RPi.GPIO not available â€” rotary disabled (desktop mode)")
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            GPIO.setup(self._clk, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self._dt,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self._sw,  GPIO.IN, pull_up_down=GPIO.PUD_UP)

            self._clk_last = GPIO.input(self._clk)

            # Edge detection for rotation
            GPIO.add_event_detect(
                self._clk, GPIO.BOTH,
                callback=self._rotation_callback,
                bouncetime=self.ROTATE_DEBOUNCE_MS,
            )

            # Edge detection for button
            GPIO.add_event_detect(
                self._sw, GPIO.BOTH,
                callback=self._button_callback,
                bouncetime=self.BUTTON_DEBOUNCE_MS,
            )

            self._active = True
            self.log.info("Initialized (CLK=%d, DT=%d, SW=%d)",
                          self._clk, self._dt, self._sw)

        except Exception as e:
            self.log.error("GPIO setup failed: %s", e)
            self._active = False

    @property
    def available(self):
        return self._active

    def _rotation_callback(self, channel):
        """Called on CLK edge â€” reads DT to determine direction."""
        now = time.perf_counter()
        if now - self._last_rotate_time < self.ROTATE_DEBOUNCE_MS / 1000.0:
            return
        self._last_rotate_time = now

        clk_state = GPIO.input(self._clk)
        dt_state  = GPIO.input(self._dt)

        if clk_state != self._clk_last:
            direction = 1 if dt_state != clk_state else -1
            self.log.debug("Rotate: %+d", direction)
            if self._on_rotate:
                self._on_rotate(direction)

        self._clk_last = clk_state

    def _button_callback(self, channel):
        """Called on button edge â€” tracks press/release for long press."""
        pressed = GPIO.input(self._sw) == GPIO.LOW

        if pressed:
            self._button_down_time = time.perf_counter()
            self._button_handled = False
        else:
            if self._button_handled:
                return
            self._button_handled = True

            hold = time.perf_counter() - self._button_down_time

            if hold >= self.LONG_PRESS_SEC:
                self.log.info("Long press (%.1fs)", hold)
                if self._on_long_press:
                    self._on_long_press()
            else:
                self.log.info("Click (%.2fs)", hold)
                if self._on_click:
                    self._on_click()

    def shutdown(self):
        """Clean up GPIO resources."""
        if self._active and GPIO:
            try:
                GPIO.remove_event_detect(self._clk)
                GPIO.remove_event_detect(self._sw)
                GPIO.cleanup([self._clk, self._dt, self._sw])
                self.log.info("GPIO cleaned up")
            except Exception as e:
                self.log.warning("GPIO cleanup error: %s", e)
        self._active = False


class SeesawRotaryController:
    """Adafruit ANO rotary navigation encoder over seesaw/I2C.

    Preferred path:
      - Existing Blinka/Adafruit seesaw stack
    Linux fallback:
      - Raw /dev/i2c-* access for Radxa/Linux when Blinka dependencies are unavailable
    """

    POLL_SEC = 0.03
    ROTATE_DEBOUNCE_SEC = 0.02
    BUTTON_DEBOUNCE_SEC = 0.08
    LONG_PRESS_SEC = 0.60

    PIN_SELECT = 24  # Adafruit rotary breakout push switch
    PIN_UP = 2
    PIN_LEFT = 3
    PIN_DOWN = 4
    PIN_RIGHT = 5
    EXPECTED_PRODUCT = 5740
    SIMPLE_ROTARY_ADDRS = {0x36}

    _STATUS_BASE = 0x00
    _GPIO_BASE = 0x01
    _ENCODER_BASE = 0x11

    _STATUS_VERSION = 0x02
    _STATUS_SWRST = 0x7F

    _GPIO_DIRCLR_BULK = 0x03
    _GPIO_BULK = 0x04
    _GPIO_BULK_SET = 0x05
    _GPIO_PULLENSET = 0x0B

    _ENCODER_POSITION = 0x30

    _INPUT_PULLUP = 0x02
    _I2C_SLAVE = 0x0703

    def __init__(
        self,
        on_rotate=None,
        on_select=None,
        on_select_long=None,
        on_up=None,
        on_down=None,
        on_left=None,
        on_right=None,
        i2c_addr=0x36,
    ):
        self.log = logging.getLogger("RotaryI2C")
        self._on_rotate = on_rotate
        self._on_select = on_select
        self._on_select_long = on_select_long
        self._on_up = on_up
        self._on_down = on_down
        self._on_left = on_left
        self._on_right = on_right
        self._addr = i2c_addr

        self._active = False
        self._stop_event = threading.Event()
        self._thread = None
        self._encoder = None
        self._position = 0
        self._last_rotate_time = 0.0

        self._buttons = {}
        self._states = {}
        self._down_time = {}
        self._last_release_time = {}

        self._backend = None
        self._linux_fd = None
        self._linux_bus = None
        self._linux_addr = None

        if self._init_blinka_backend():
            return
        if self._init_linux_i2c_backend():
            return

        self.log.info("Seesaw rotary unavailable on this platform")

    @property
    def available(self):
        return self._active

    def _init_blinka_backend(self):
        if not all((board, seesaw_module, seesaw_rotaryio, seesaw_digitalio)):
            self.log.info("Seesaw I2C rotary dependencies unavailable")
            return False

        try:
            i2c = board.I2C()
            self._seesaw = seesaw_module.Seesaw(i2c, addr=self._addr)

            product = None
            try:
                product = (self._seesaw.get_version() >> 16) & 0xFFFF
            except Exception:
                pass

            simple_mode = self._addr in self.SIMPLE_ROTARY_ADDRS

            if product is not None and (product != self.EXPECTED_PRODUCT) and not simple_mode:
                raise RuntimeError(
                    f"Unexpected seesaw product {product}; expected {self.EXPECTED_PRODUCT}"
                )

            button_pins = [self.PIN_SELECT] if simple_mode else [
                self.PIN_SELECT, self.PIN_UP, self.PIN_LEFT, self.PIN_DOWN, self.PIN_RIGHT
            ]

            for pin in button_pins:
                self._seesaw.pin_mode(pin, self._seesaw.INPUT_PULLUP)

            self._buttons = {
                "select": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_SELECT),
            }
            if not simple_mode:
                self._buttons.update({
                    "up": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_UP),
                    "left": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_LEFT),
                    "down": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_DOWN),
                    "right": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_RIGHT),
                })

            self._encoder = seesaw_rotaryio.IncrementalEncoder(self._seesaw)
            self._position = self._encoder.position

            now = time.perf_counter()
            for name, btn in self._buttons.items():
                pressed = not bool(btn.value)
                self._states[name] = pressed
                self._down_time[name] = now if pressed else 0.0
                self._last_release_time[name] = 0.0

            self._backend = "blinka"
            self._active = True
            self._thread = _start_safe_thread(self._poll, "SeesawRotary", self.log)
            self.log.info(
                "Initialized seesaw rotary at I2C 0x%02X%s",
                self._addr,
                " (simple breakout mode)" if simple_mode else "",
            )
            return True
        except Exception:
            self.log.exception("Failed to initialize seesaw rotary via Blinka")
            self._active = False
            return False

    def _candidate_buses(self):
        candidates = []
        cfg = _load_config()
        hw = cfg.get("hardware", {}) if isinstance(cfg, dict) else {}
        rotary_i2c = hw.get("rotary_i2c", {}) if isinstance(hw, dict) else {}
        if isinstance(rotary_i2c.get("bus_candidates"), list):
            for value in rotary_i2c["bus_candidates"]:
                try:
                    candidates.append(int(value))
                except Exception:
                    pass
        for fallback in (1, 0, 2, 3):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _candidate_addrs(self):
        addrs = []
        cfg = _load_config()
        hw = cfg.get("hardware", {}) if isinstance(cfg, dict) else {}
        rotary_i2c = hw.get("rotary_i2c", {}) if isinstance(hw, dict) else {}
        if isinstance(rotary_i2c.get("addr_candidates"), list):
            for value in rotary_i2c["addr_candidates"]:
                try:
                    addrs.append(int(value, 0) if isinstance(value, str) else int(value))
                except Exception:
                    pass
        for fallback in (self._addr, 0x36, 0x49):
            if fallback not in addrs:
                addrs.append(fallback)
        return addrs

    def _open_linux_i2c(self, bus, addr):
        if fcntl is None:
            raise RuntimeError("fcntl unavailable")
        path = f"/dev/i2c-{bus}"
        fd = os.open(path, os.O_RDWR)
        try:
            fcntl.ioctl(fd, self._I2C_SLAVE, addr)
            return fd
        except Exception:
            os.close(fd)
            raise

    def _linux_write(self, reg_base, reg, data=b"", fd=None):
        if fd is None:
            fd = self._linux_fd
        payload = bytes([reg_base & 0xFF, reg & 0xFF]) + bytes(data)
        os.write(fd, payload)

    def _linux_read(self, reg_base, reg, length, delay=0.008, fd=None):
        if fd is None:
            fd = self._linux_fd
        self._linux_write(reg_base, reg, b"", fd=fd)
        time.sleep(delay)
        return os.read(fd, length)

    def _linux_read_u32_be(self, reg_base, reg, fd=None, delay=0.008):
        data = self._linux_read(reg_base, reg, 4, delay=delay, fd=fd)
        if len(data) != 4:
            raise RuntimeError(f"Short I2C read ({len(data)} bytes)")
        return struct.unpack(">I", data)[0]

    def _linux_read_i32_be(self, reg_base, reg, fd=None, delay=0.008):
        data = self._linux_read(reg_base, reg, 4, delay=delay, fd=fd)
        if len(data) != 4:
            raise RuntimeError(f"Short I2C read ({len(data)} bytes)")
        return struct.unpack(">i", data)[0]

    def _linux_pin_mode_input_pullup(self, pin):
        pins = 1 << pin
        cmd = struct.pack(">I", pins)
        self._linux_write(self._GPIO_BASE, self._GPIO_DIRCLR_BULK, cmd)
        self._linux_write(self._GPIO_BASE, self._GPIO_PULLENSET, cmd)
        self._linux_write(self._GPIO_BASE, self._GPIO_BULK_SET, cmd)

    def _init_linux_i2c_backend(self):
        if fcntl is None:
            self.log.info("Linux I2C fallback unavailable (fcntl missing)")
            return False

        last_error = None
        for bus in self._candidate_buses():
            dev = f"/dev/i2c-{bus}"
            if not os.path.exists(dev):
                continue
            for addr in self._candidate_addrs():
                fd = None
                try:
                    fd = self._open_linux_i2c(bus, addr)
                    version = self._linux_read_u32_be(self._STATUS_BASE, self._STATUS_VERSION, fd=fd)
                    product = (version >> 16) & 0xFFFF
                    simple_mode = addr in self.SIMPLE_ROTARY_ADDRS
                    if (product != self.EXPECTED_PRODUCT) and not simple_mode:
                        raise RuntimeError(
                            f"Unexpected seesaw product {product}; expected {self.EXPECTED_PRODUCT}"
                        )

                    try:
                        self._linux_write(self._STATUS_BASE, self._STATUS_SWRST, bytes([0xFF]), fd=fd)
                        time.sleep(0.5)
                    except Exception:
                        pass

                    button_pins = [self.PIN_SELECT] if simple_mode else [
                        self.PIN_SELECT, self.PIN_UP, self.PIN_LEFT, self.PIN_DOWN, self.PIN_RIGHT
                    ]
                    for pin in button_pins:
                        self._linux_pin_mode_input_pullup(pin)

                    self._linux_fd = fd
                    self._linux_bus = bus
                    self._linux_addr = addr
                    self._position = self._linux_read_i32_be(self._ENCODER_BASE, self._ENCODER_POSITION)
                    now = time.perf_counter()
                    button_states = self._linux_read_button_states()
                    for name, pressed in button_states.items():
                        self._states[name] = pressed
                        self._down_time[name] = now if pressed else 0.0
                        self._last_release_time[name] = 0.0

                    self._backend = "linux_i2c"
                    self._active = True
                    self._thread = _start_safe_thread(self._poll, "SeesawRotary", self.log)
                    self.log.info(
                        "Initialized seesaw rotary using Linux I2C fallback on /dev/i2c-%d @ 0x%02X%s",
                        bus,
                        addr,
                        " (simple breakout mode)" if simple_mode else "",
                    )
                    return True
                except Exception as exc:
                    last_error = exc
                    if fd is not None:
                        try:
                            os.close(fd)
                        except Exception:
                            pass
                finally:
                    if fd is not None and fd is not self._linux_fd:
                        try:
                            os.close(fd)
                        except Exception:
                            pass

        if last_error is not None:
            self.log.info("Linux I2C rotary fallback unavailable: %s", last_error)
        return False

    def _linux_read_button_states(self):
        value = self._linux_read_u32_be(self._GPIO_BASE, self._GPIO_BULK)
        states = {
            "select": not bool(value & (1 << self.PIN_SELECT)),
        }
        if self._linux_addr not in self.SIMPLE_ROTARY_ADDRS:
            states.update({
                "up": not bool(value & (1 << self.PIN_UP)),
                "left": not bool(value & (1 << self.PIN_LEFT)),
                "down": not bool(value & (1 << self.PIN_DOWN)),
                "right": not bool(value & (1 << self.PIN_RIGHT)),
            })
        return states

    def _read_position(self):
        if self._backend == "linux_i2c":
            return self._linux_read_i32_be(self._ENCODER_BASE, self._ENCODER_POSITION)
        return self._encoder.position

    def _read_button_states(self):
        if self._backend == "linux_i2c":
            return self._linux_read_button_states()
        return {name: (not bool(btn.value)) for name, btn in self._buttons.items()}

    def _emit_button(self, name, hold):
        if name == "select":
            if hold >= self.LONG_PRESS_SEC:
                if self._on_select_long:
                    self._on_select_long()
            elif hold >= self.BUTTON_DEBOUNCE_SEC:
                if self._on_select:
                    self._on_select()
            return

        if hold < self.BUTTON_DEBOUNCE_SEC:
            return

        if name == "up" and self._on_up:
            self._on_up()
        elif name == "down" and self._on_down:
            self._on_down()
        elif name == "left" and self._on_left:
            self._on_left()
        elif name == "right" and self._on_right:
            self._on_right()

    def _poll(self):
        while not self._stop_event.is_set():
            try:
                now = time.perf_counter()

                pos = self._read_position()
                if pos != self._position and (now - self._last_rotate_time) >= self.ROTATE_DEBOUNCE_SEC:
                    step = pos - self._position
                    self._position = pos
                    self._last_rotate_time = now
                    direction = 1 if step > 0 else -1
                    for _ in range(abs(step)):
                        if self._on_rotate:
                            self._on_rotate(direction)

                states = self._read_button_states()
                for name, pressed in states.items():
                    was_pressed = self._states.get(name, False)

                    if pressed and not was_pressed:
                        self._states[name] = True
                        self._down_time[name] = now

                    elif not pressed and was_pressed:
                        self._states[name] = False

                        if (now - self._last_release_time.get(name, 0.0)) < self.BUTTON_DEBOUNCE_SEC:
                            continue

                        self._last_release_time[name] = now
                        hold = now - self._down_time.get(name, now)
                        self._emit_button(name, hold)

                time.sleep(self.POLL_SEC)
            except Exception:
                self.log.exception("ANO seesaw polling failed; disabling controller")
                self._active = False
                self._stop_event.set()

    def shutdown(self):
        self._stop_event.set()
        self._active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._linux_fd is not None:
            try:
                os.close(self._linux_fd)
            except Exception:
                pass
            self._linux_fd = None


class TouchpadController:
    """Cirque GlidePoint touchpad with safe fallback when hardware is absent.

    Preferred path:
      - Existing CircuitPython Pinnacle driver when available
    Radxa fallback:
      - Raw spidev register polling using the known-good SPI bring-up path
    """

    POLL_SEC = 0.005
    TAP_WINDOW_SEC = 0.35           # 350ms tap window (more forgiving)
    TAP_MIN_SEC = 0.035             # 35ms minimum contact to count as a tap (easier taps)
    MOVE_THRESHOLD = 4
    TAP_MAX_TRAVEL = 80             # allow natural finger wobble during taps (was 60)
    SWIPE_DEBOUNCE_SEC = 0.0
    RELEASE_TIMEOUT_SEC = 0.055     # slightly faster tap release handling
    JITTER_FLOOR = 6                # Ignore sub-6-unit jitter (was 1, too noisy)
    JUMP_THRESHOLD = 1800
    SWIPE_DISTANCE = 280            # ~6mm swipe (was 34 = 0.7mm, way too sensitive)
    SWIPE_RESET_RATIO = 0.40
    STABLE_READS_FOR_MOVE = 1      # emit movement immediately for remote-like responsiveness

    def __init__(self, on_swipe=None, on_tap=None, on_move=None, chip_select=None):
        self.log = logging.getLogger("Touchpad")
        self._on_swipe = on_swipe
        self._on_tap = on_tap
        self._on_move = on_move
        self._chip_select = chip_select
        self._active = False
        self._stop_event = threading.Event()
        self._thread = None
        self._touchpad = None
        self._last_x = None
        self._last_y = None
        self._start_x = None
        self._start_y = None
        self._touch_started = 0.0
        self._last_swipe_at = 0.0
        self._last_contact_at = 0.0
        self._swiped_this_touch = False
        self._max_travel = 0
        self._stable_read_count = 0
        self._stable_read_count = 0
        self._backend = None
        self._raw_spi = None
        self._raw_error_streak = 0

        if self._init_pinnacle_driver():
            return
        if self._init_raw_spi():
            return

        self.log.info("Pinnacle touchpad unavailable on this platform")

    @property
    def available(self):
        return self._active

    def _init_pinnacle_driver(self):
        if not all((PinnacleSPI, board, busio, DigitalInOut)):
            self.log.info("Pinnacle touchpad dependencies unavailable")
            return False

        try:
            spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

            def _pin(name):
                return getattr(board, name, None)

            hw_cfg = _hardware_config()
            cs_names = hw_cfg.get("touchpad", {}).get("cs_candidates", ["CE0", "CE1", "D5"])
            dr_names = hw_cfg.get("touchpad", {}).get("dr_candidates", ["D6", "D25", "D24"])

            pin_candidates = []
            explicit_cs = self._chip_select
            if explicit_cs is not None:
                for dr_name in dr_names:
                    pin_candidates.append((explicit_cs, _pin(dr_name), f"explicit/{dr_name}"))

            for cs_name in cs_names:
                for dr_name in dr_names:
                    pin_candidates.append((_pin(cs_name), _pin(dr_name), f"{cs_name}/{dr_name}"))

            attempted = []
            seen = set()
            for cs_pin, dr_pin, label in pin_candidates:
                if cs_pin is None or dr_pin is None:
                    continue
                key = (repr(cs_pin), repr(dr_pin))
                if key in seen:
                    continue
                seen.add(key)
                attempted.append(label)
                try:
                    self._touchpad = PinnacleSPI(spi, DigitalInOut(cs_pin), DigitalInOut(dr_pin))
                    if hasattr(self._touchpad, "absolute_mode"):
                        self._touchpad.absolute_mode = True
                    self._backend = "pinnacle"
                    self._active = True
                    self._thread = _start_safe_thread(self._poll, "TouchpadPoll", self.log)
                    self.log.info("Cirque touchpad initialized using %s", label)
                    return True
                except Exception:
                    self._touchpad = None

            raise RuntimeError(
                "Cirque Pinnacle ASIC not responding on attempted pin pairs: " + ", ".join(attempted)
            )
        except Exception:
            self.log.exception("Touchpad initialization via Pinnacle driver failed")
            self._active = False
            return False

    def _init_raw_spi(self):
        if spidev is None:
            self.log.info("spidev not available; raw touchpad fallback disabled")
            return False

        try:
            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.max_speed_hz = 1_000_000
            spi.mode = 1
            self._raw_spi = spi

            fw = self._raw_read_reg(0x00)
            if fw != 0x07:
                self._raw_write_reg(0x03, 0x01)
                time.sleep(0.5)
                self._raw_write_reg(0x04, 0x03)
                self._raw_write_reg(0x02, 0x00)
                fw = self._raw_read_reg(0x00)

            if fw != 0x07:
                raise RuntimeError(f"Unexpected Cirque firmware ID: 0x{fw:02x}")

            self._raw_write_reg(0x03, 0x01)
            time.sleep(0.5)
            self._raw_write_reg(0x04, 0x03)
            self._raw_write_reg(0x02, 0x00)

            self._backend = "raw_spi"
            self._active = True
            self._thread = _start_safe_thread(self._poll, "TouchpadPoll", self.log)
            self.log.info("Cirque touchpad initialized using raw spidev fallback")
            return True
        except Exception:
            self.log.exception("Touchpad raw SPI fallback failed")
            if self._raw_spi is not None:
                try:
                    self._raw_spi.close()
                except Exception:
                    pass
            self._raw_spi = None
            self._active = False
            return False

    def _raw_write_reg(self, reg, val):
        if self._raw_spi is None:
            raise RuntimeError("Raw SPI not initialized")
        self._raw_spi.xfer2([0x80 | (reg & 0xFF), val & 0xFF])
        time.sleep(0.002)  # 2ms is sufficient; 10ms caused ~45Hz effective poll rate

    def _raw_read_reg(self, reg):
        if self._raw_spi is None:
            raise RuntimeError("Raw SPI not initialized")
        resp = self._raw_spi.xfer2([0xA0 | (reg & 0xFF), 0xFB, 0xFB, 0x00])
        time.sleep(0.002)
        return resp[3]

    def _read_packet(self):
        if hasattr(self._touchpad, "read"):
            return self._touchpad.read()
        if hasattr(self._touchpad, "read_data"):
            return self._touchpad.read_data()
        raise RuntimeError("Unsupported Pinnacle touchpad API")

    def _handle_touch_point(self, x, y, now):
        if self._last_x is None:
            self._last_x, self._last_y = x, y
            self._start_x, self._start_y = x, y
            self._touch_started = now
            self._last_contact_at = now
            self._swiped_this_touch = False
            self._max_travel = 0
            self._stable_read_count = 1
            if self._on_move:
                self._on_move(x, y)
            return

        dx = x - self._last_x
        dy = y - self._last_y

        if abs(dx) > self.JUMP_THRESHOLD or abs(dy) > self.JUMP_THRESHOLD:
            self._last_x, self._last_y = x, y
            self._start_x, self._start_y = x, y
            self._last_contact_at = now
            self._stable_read_count = 0
            return

        self._last_contact_at = now

        if abs(dx) <= self.JITTER_FLOOR and abs(dy) <= self.JITTER_FLOOR:
            return

        self._stable_read_count += 1
        total_dx = x - self._start_x
        total_dy = y - self._start_y
        self._max_travel = max(self._max_travel, abs(total_dx), abs(total_dy))

        self._last_x, self._last_y = x, y

        if self._on_move and self._stable_read_count >= self.STABLE_READS_FOR_MOVE:
            self._on_move(x, y)

        if self._stable_read_count < 2:
            return

        direction = None
        if abs(total_dx) >= max(self.SWIPE_DISTANCE, abs(total_dy) + 4):
            direction = "right" if total_dx > 0 else "left"
        elif abs(total_dy) >= max(self.SWIPE_DISTANCE, abs(total_dx) + 4):
            direction = "down" if total_dy > 0 else "up"

        if direction and (now - self._last_swipe_at) >= self.SWIPE_DEBOUNCE_SEC:
            self._last_swipe_at = now
            self._swiped_this_touch = True
            if self._on_swipe:
                self._on_swipe(direction)

            # Reset swipe anchor so a continuous finger motion can emit another swipe quickly.
            self._start_x = x
            self._start_y = y
            self._stable_read_count = 1


    def _reset_touch(self):
        self._last_x = None
        self._last_y = None
        self._start_x = None
        self._start_y = None
        self._touch_started = 0.0
        self._last_contact_at = 0.0
        self._swiped_this_touch = False
        self._max_travel = 0
        self._stable_read_count = 0

    def _finish_touch_if_needed(self, now):
        if self._last_x is None:
            return
        if now - self._last_contact_at < self.RELEASE_TIMEOUT_SEC:
            return

        if (
            not self._swiped_this_touch
            and (now - self._touch_started) >= self.TAP_MIN_SEC
            and (now - self._touch_started) <= self.TAP_WINDOW_SEC
            and self._max_travel <= self.TAP_MAX_TRAVEL
        ):
            if self._on_tap:
                self._on_tap()

        self._reset_touch()

    def _poll_pinnacle(self, now):
        packet = self._read_packet()
        touched = bool(getattr(packet, "touched", False) or getattr(packet, "touchDown", False))
        x = getattr(packet, "x", None)
        y = getattr(packet, "y", None)

        if touched and x is not None and y is not None:
            self._handle_touch_point(int(x), int(y), now)
        else:
            self._finish_touch_if_needed(now)

    def _poll_raw_spi(self, now):
        status = self._raw_read_reg(0x02)
        if status & 0x04:
            x_lo = self._raw_read_reg(0x14)
            x_hi = self._raw_read_reg(0x15)
            y_lo = self._raw_read_reg(0x16)
            y_hi = self._raw_read_reg(0x17)
            _z = self._raw_read_reg(0x18)

            x = ((x_hi & 0x0F) << 8) | x_lo
            y = ((y_hi & 0x0F) << 8) | y_lo

            try:
                self._raw_write_reg(0x02, 0x00)
            except Exception:
                pass

            if x != 0xFBFB and y != 0xFBFB and 0 < x < 4096 and 0 < y < 4096:
                self._handle_touch_point(x, y, now)
                return

        self._finish_touch_if_needed(now)

    def _poll(self):
        while not self._stop_event.is_set():
            try:
                now = time.perf_counter()
                if self._backend == "raw_spi":
                    self._poll_raw_spi(now)
                else:
                    self._poll_pinnacle(now)
                self._raw_error_streak = 0
                time.sleep(self.POLL_SEC)
            except Exception:
                self._raw_error_streak += 1
                if self._raw_error_streak <= 3:
                    self.log.exception("Touchpad polling failed")
                if self._raw_error_streak >= 25:
                    self.log.exception("Touchpad polling disabled after repeated failures")
                    self._active = False
                    self._stop_event.set()
                    break
                time.sleep(0.05)

    def shutdown(self):
        self._stop_event.set()
        self._active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._raw_spi is not None:
            try:
                self._raw_spi.close()
            except Exception:
                pass
            self._raw_spi = None


class VoiceCommandLoop:
    """Continuous non-blocking speech command loop with robust error handling."""

    LISTEN_TIMEOUT = 2
    PHRASE_LIMIT = 4
    IDLE_PAUSE_SEC = 0.4

    def __init__(self, on_command=None, on_error=None, mic_index=None):
        self.log = logging.getLogger("VoiceLoop")
        self._on_command = on_command
        self._on_error = on_error
        self._mic_index = mic_index
        self._thread = None
        self._stop_event = threading.Event()
        self._recognizer = None
        self._last_error = ""
        if sr:
            self._recognizer = sr.Recognizer()
            self._recognizer.dynamic_energy_threshold = True
        else:
            self.log.info("SpeechRecognition unavailable; background voice loop disabled")

    @property
    def available(self):
        return self._recognizer is not None

    def start(self):
        if not self.available or (self._thread and self._thread.is_alive()):
            return
        self._stop_event.clear()
        self._thread = _start_safe_thread(self._run, "VoiceCommandLoop", self.log)

    def shutdown(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _emit_error(self, msg):
        if msg != self._last_error and self._on_error:
            self._last_error = msg
            self._on_error(msg)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                mic = sr.Microphone(device_index=self._mic_index) if self._mic_index is not None else sr.Microphone()
                with mic as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                    audio = self._recognizer.listen(
                        source,
                        timeout=self.LISTEN_TIMEOUT,
                        phrase_time_limit=self.PHRASE_LIMIT,
                    )
                text = self._recognizer.recognize_google(audio).strip()
                if text and self._on_command:
                    self._on_command(text)
                self._last_error = ""
            except sr.WaitTimeoutError:
                time.sleep(self.IDLE_PAUSE_SEC)
            except sr.UnknownValueError:
                time.sleep(self.IDLE_PAUSE_SEC)
            except OSError as exc:
                self.log.error("Voice loop microphone error: %s", exc)
                self._emit_error(f"Voice loop unavailable: {exc}")
                time.sleep(2.0)
            except sr.RequestError as exc:
                self.log.error("Voice loop speech service error: %s", exc)
                self._emit_error(f"Voice service error: {exc}")
                time.sleep(2.0)
            except Exception as exc:
                self.log.exception("Voice loop failed")
                self._emit_error(f"Voice loop error: {exc}")
                time.sleep(2.0)


class TTSController:
    """Queued pyttsx3 wrapper using system-default audio output."""

    def __init__(self):
        self.log = logging.getLogger("TTS")
        self._queue = Queue()
        self._stop_event = threading.Event()
        self._engine = None
        self.available = False
        if not pyttsx3:
            self.log.info("pyttsx3 unavailable")
            return
        try:
            self._engine = pyttsx3.init()
            self.available = True
            self._thread = _start_safe_thread(self._worker, "TTSWorker", self.log)
        except Exception:
            self.log.exception("TTS initialization failed")

    def speak(self, text):
        if self.available and text:
            self._queue.put(text)

    def shutdown(self):
        self._stop_event.set()
        if self.available:
            self._queue.put(None)

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                continue
            try:
                self._engine.say(item)
                self._engine.runAndWait()
            except Exception:
                self.log.exception("TTS playback failed")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CoverFlow
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class CoverFlow:
    def __init__(self, canvas, apps):
        self.cv = canvas
        self.sel = 0
        self.sel_anim = 0.0
        self._refs = [None] * 5

        self.apps = []
        for fn, label in apps:
            img = _load(os.path.join(ASSETS_DIR, fn))
            if img is None:
                img = Image.new("RGBA", (BASE_ICON, BASE_ICON), (200, 200, 200, 255))
            self.apps.append({"id": os.path.splitext(fn)[0],
                              "label": label, "img": img, "cache": {}})

        self._icon_widgets = [
            ctk.CTkLabel(canvas.master, text="", fg_color="transparent")
            for _ in range(5)
        ]
        self._icons = [canvas.create_window(0, 0, window=w, anchor="center")
                       for w in self._icon_widgets]
        self.text_color = TXT
        self._label = canvas.create_text(
            0, 0, text="", fill=self.text_color, font=(FONT, 17))

    def _ctkimg(self, app, sz, alpha):
        sq = max(14, round(sz / SIZE_STEP_PX) * SIZE_STEP_PX)
        a8 = int(max(0, min(255, round(alpha * 255 / ALPHA_STEP_8) * ALPHA_STEP_8)))
        key = (sq, a8)
        if key in app["cache"]:
            return app["cache"][key]
        circ = _circle(app["img"], sq)
        if a8 < 255:
            am = circ.split()[-1].point(lambda p, _a=a8: int(p * _a / 255))
            circ.putalpha(am)
        ctk_img = _make_ctk_image(circ, (sq, sq))
        app["cache"][key] = ctk_img
        return ctk_img

    def step(self, dt):
        n = len(self.apps)
        if not n:
            return
        d = self.sel - self.sel_anim
        if d > n / 2:   d -= n
        if d < -n / 2:  d += n
        dt = max(1 / 480, dt)
        a = 1.0 - pow(2.718281828, -FLOW_LAMBDA * dt)
        self.sel_anim += d * a
        if abs(d) < 1e-4:
            self.sel_anim = round(self.sel_anim)
        self._redraw()

    def move(self, delta):
        if self.apps:
            self.sel = (self.sel + delta) % len(self.apps)

    def current(self):
        return self.apps[self.sel % len(self.apps)] if self.apps else None

    def _redraw(self):
        mx, my = WIDTH // 2, HEIGHT // 2 - 10
        x0 = mx - 2 * SPACING
        frac = self.sel_anim - round(self.sel_anim)
        positions = []
        for slot, i in enumerate((0, 4, 1, 3, 2)):
            idx = int(round(self.sel_anim) - 2 + i) % len(self.apps)
            app = self.apps[idx]
            dist = abs(i - 2 + frac)
            scale = max(0.70, 1.0 - SCALE_DROP * dist)
            alpha = max(0.46, 1.0 - ALPHA_DROP * dist)
            sz = int(BASE_ICON * scale)
            ctk_img = self._ctkimg(app, sz, alpha)
            cx, cy = x0 + i * SPACING, my
            self._icon_widgets[slot].configure(image=ctk_img)
            self.cv.coords(self._icons[slot], int(cx), int(cy))
            self._refs[slot] = ctk_img
            positions.append((cx, cy, sz, app["label"]))
        for cx, cy, w, label in positions:
            if abs(cx - mx) < 2:
                self.cv.itemconfigure(self._label, text=label, fill=self.text_color)
                self.cv.coords(self._label, cx, cy + w / 2 + 28)
                break



class TouchKeyboard:
    """Apple TV-style one-line swipe keyboard docked at the bottom."""

    TOK_SPACE = "__SPACE__"
    TOK_BACK = "__BACKSPACE__"
    TOK_ENTER = "__ENTER__"
    TOK_CAPS = "__CAPS__"
    TOK_SYMBOLS = "__SYMBOLS__"
    TOK_LETTERS = "__LETTERS__"
    TOK_BROWSER_BACK = "__BROWSER_BACK__"
    TOK_BROWSER_FORWARD = "__BROWSER_FORWARD__"
    TOK_BROWSER_CLEAR = "__BROWSER_CLEAR__"
    TOK_TRANS = "__TRANS__"
    TOK_DELETE = "__DELETE__"

    LETTER_TOKENS = list("abcdefghijklmnopqrstuvwxyz") + [TOK_BACK, TOK_ENTER, TOK_CAPS, TOK_SYMBOLS, TOK_SPACE]
    SYMBOL_TOKENS = list("1234567890") + ["-", "/", ":", ";", "(", ")", "$", "&", "@", '"', ".", ",", "?", "!", "+", "=", "#", "%", "*", "_"] + [TOK_BACK, TOK_ENTER, TOK_LETTERS, TOK_SPACE]
    VISIBLE_SLOTS = 5

    def __init__(self, app):
        self.app = app
        self.window = None
        self.visible = False
        self.sel_row = 0
        self.sel_col = 0
        self._preview_var = None
        self._flash_token = None
        self._flash_after = None
        self._last_geometry = None
        self._rail_buttons = []
        self._viewport_start = 0
        self._symbol_mode = False
        self._caps_lock = False


    def _tokens(self):
        base = list(self.SYMBOL_TOKENS if self._symbol_mode else self.LETTER_TOKENS)
        if getattr(self.app, "current_view", "") == "browser" and getattr(self.app, "_browser_typing_mode", False):
            insert_after = self.TOK_CAPS if not self._symbol_mode else self.TOK_LETTERS
            try:
                idx = base.index(insert_after) + 1
            except ValueError:
                idx = len(base)
            base[idx:idx] = [
                self.TOK_BROWSER_BACK,
                self.TOK_BROWSER_FORWARD,
                self.TOK_BROWSER_CLEAR,
            ]
        elif getattr(self.app, "current_view", "") == "translate":
            base += [self.TOK_TRANS]
        elif getattr(self.app, "current_view", "") == "photos":
            base = [self.TOK_DELETE]
        return base

    def LAYOUT(self):
        return [self._tokens()]

    def ensure(self):
        if self.window is not None:
            return

        self.window = tk.Toplevel(self.app)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(
            bg="#050506",
            bd=1,
            highlightthickness=1,
            highlightbackground="#2C2C2E",
            cursor="none",
        )
        try:
            self.window.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.window.transient(self.app)
        except Exception:
            pass

        shell = ctk.CTkFrame(self.window, fg_color="#050506", corner_radius=0)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(shell, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 2))
        ctk.CTkLabel(
            hdr,
            text="Keyboard",
            font=(FONT, 13, "bold"),
            text_color=TXT,
        ).pack(side="left")

        self._preview_var = tk.StringVar(value="")
        preview = ctk.CTkFrame(shell, corner_radius=10, fg_color="#101013")
        preview.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        preview.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            preview,
            textvariable=self._preview_var,
            font=(FONT, 12),
            text_color=TXTD,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=6)

        rail = ctk.CTkFrame(shell, fg_color="transparent")
        rail.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        for col in range(self.VISIBLE_SLOTS):
            rail.grid_columnconfigure(col, weight=1, uniform="vk")

        self._rail_buttons = []
        for col in range(self.VISIBLE_SLOTS):
            btn = ctk.CTkButton(
                rail,
                text="",
                command=lambda c=col: self._press_viewport_slot(c),
                height=44 if WIDTH <= 640 or HEIGHT <= 400 else 40,
                corner_radius=9,
                border_width=1,
                border_color="#2A2A2E",
                font=(FONT, 15, "bold"),
                fg_color="#0A0A0B",
                hover_color="#171719",
                text_color=TXT,
            )
            btn.grid(row=0, column=col, padx=3, pady=2, sticky="ew")
            self._rail_buttons.append(btn)

    def _label(self, token):
        if token == self.TOK_SPACE:
            return "Space"
        if token == self.TOK_BACK:
            return "⌫"
        if token == self.TOK_ENTER:
            return "Enter"
        if token == self.TOK_CAPS:
            return "CAPS" if not self._caps_lock else "Caps✓"
        if token == self.TOK_SYMBOLS:
            return "#+="
        if token == self.TOK_LETTERS:
            return "ABC"
        if token == self.TOK_BROWSER_BACK:
            return "←"
        if token == self.TOK_BROWSER_FORWARD:
            return "→"
        if token == self.TOK_BROWSER_CLEAR:
            return "Clear"
        if token == self.TOK_TRANS:
            return "Trans"
        if token == self.TOK_DELETE:
            return "Delete"
        if len(token) == 1 and token.isalpha():
            return token.upper() if self._caps_lock else token
        return token

    def _normalize_viewport(self):
        total = len(self._tokens())
        if total <= self.VISIBLE_SLOTS:
            self._viewport_start = 0
            return
        center = self.VISIBLE_SLOTS // 2
        self._viewport_start = max(0, min(self.sel_col - center, total - self.VISIBLE_SLOTS))

    def _clamp_selection(self):
        total = len(self._tokens())
        if total <= 0:
            self.sel_col = 0
        else:
            self.sel_col = max(0, min(total - 1, self.sel_col))

    def show(self):
        self.ensure()
        was_visible = self.visible
        self.visible = True
        if not was_visible:
            self.sel_row = 0
            self.sel_col = 0
            self._viewport_start = 0
        self._clamp_selection()
        self._position(force=True)
        try:
            self.window.deiconify()
        except Exception:
            pass
        self.window.lift()
        self.window.tkraise()
        self.app.update_idletasks()
        self.refresh()

    def hide(self):
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass
        self.visible = False

    def _position(self, force=False):
        self.app.update_idletasks()
        root_x = self.app.winfo_rootx()
        root_y = self.app.winfo_rooty()
        app_w = max(self.app.winfo_width(), WIDTH)
        app_h = max(self.app.winfo_height(), HEIGHT)
        abs_h = 112 if (WIDTH <= 640 or HEIGHT <= 400) else (146 if app_h <= 420 else 156)
        width = min(app_w - 68, 490) if (WIDTH <= 640 or HEIGHT <= 400) else min(app_w - 24, 616)
        x = int(root_x + (app_w - width) / 2)
        y = int(root_y + app_h - abs_h - 6)
        geometry = (x, y, width, abs_h)
        if not force and geometry == self._last_geometry:
            return
        self.window.geometry(f"{width}x{abs_h}+{x}+{y}")
        self._last_geometry = geometry
        self.window.lift()
        self.window.tkraise()

    def refresh(self):
        if self.window is None:
            return
        self._clamp_selection()
        self._normalize_viewport()
        if self._preview_var is not None:
            self._preview_var.set(self.app._active_input_text())

        total = len(self._tokens())
        for slot, btn in enumerate(self._rail_buttons):
            idx = self._viewport_start + slot
            if idx >= total:
                btn.configure(text="", state="disabled", fg_color="#050506", hover_color="#050506",
                              border_color="#050506", text_color="#050506")
                continue
            token = self._tokens()[idx]
            selected = idx == self.sel_col
            flashing = token == self._flash_token
            btn.configure(
                state="normal",
                text=self._label(token),
                fg_color=AMB if flashing else (C if selected else "#0A0A0B"),
                hover_color=AMB if flashing else (CD if selected else "#171719"),
                border_width=2 if selected or flashing else 1,
                border_color=AMB if flashing else (C if selected else "#2A2A2E"),
                text_color=BG if selected or flashing else TXT,
            )

    def move(self, dx=0, dy=0):
        if not self.visible:
            return
        delta = 0
        if dx < 0 or dy < 0:
            delta = -1
        elif dx > 0 or dy > 0:
            delta = 1
        if delta == 0:
            return
        self.sel_col = max(0, min(len(self._tokens()) - 1, self.sel_col + delta))
        self.refresh()

    def activate(self):
        if not self.visible:
            return
        self.press(self._tokens()[self.sel_col])

    def _press_viewport_slot(self, slot):
        idx = self._viewport_start + slot
        if 0 <= idx < len(self._tokens()):
            self.sel_col = idx
            self.press(self._tokens()[idx])

    def press(self, token):
        if token == self.TOK_CAPS:
            self._caps_lock = not self._caps_lock
            self.flash(token, persist_ms=140)
            self.refresh()
            return
        if token == self.TOK_SYMBOLS:
            self._symbol_mode = True
            self.sel_col = 0
            self.flash(token, persist_ms=140)
            self.refresh()
            return
        if token == self.TOK_LETTERS:
            self._symbol_mode = False
            self.sel_col = 0
            self.flash(token, persist_ms=140)
            self.refresh()
            return
        if token == self.TOK_BROWSER_BACK:
            self.flash(token, persist_ms=140)
            self.app._browser_go_back()
            self.refresh()
            return
        if token == self.TOK_BROWSER_FORWARD:
            self.flash(token, persist_ms=140)
            self.app._browser_go_forward()
            self.refresh()
            return
        if token == self.TOK_BROWSER_CLEAR:
            self.flash(token, persist_ms=140)
            self.app._browser_clear_entry()
            self.refresh()
            return
        if token == self.TOK_TRANS:
            self.flash(token, persist_ms=140)
            self.app._translate_target_button()
            self.refresh()
            return
        if token == self.TOK_DELETE:
            self.flash(token, persist_ms=140)
            self.app._photo_delete_current()
            self.refresh()
            return
        self.flash(token, persist_ms=140)
        self.app._handle_touch_key(token.upper() if (self._caps_lock and len(token) == 1 and token.isalpha()) else token)
        self.refresh()

    def flash(self, token, persist_ms=140):
        if not self.visible:
            return
        pos = self._find_token(token)
        if pos is not None:
            self.sel_row, self.sel_col = pos
        self._flash_token = token
        if self._flash_after and self.window is not None:
            try:
                self.window.after_cancel(self._flash_after)
            except Exception:
                pass
        if self.window is not None:
            self._flash_after = self.window.after(persist_ms, self._clear_flash)
            self.window.after_idle(self.refresh)
        else:
            self.refresh()

    def _clear_flash(self):
        self._flash_after = None
        self._flash_token = None
        self.refresh()

    def _find_token(self, token):
        try:
            idx = self._tokens().index(token)
            return (0, idx)
        except ValueError:
            return None


# ═══════════════════════════════════════
#  Main App
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class VAApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger("App")
        self.geometry(f"{WIDTH}x{HEIGHT}")
        if WIDTH <= 640 or HEIGHT <= 400:
            try:
                ctk.set_widget_scaling(0.88)  # slightly larger than 0.82 for readability
                self.tk.call("tk", "scaling", 1.0)
            except Exception:
                pass
        self.title("VA-OS 1.4.13.26")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.configure(cursor="none")

        try:
            self.attributes("-transparentcolor", "#000000")
        except Exception:
            pass
        try:
            self.attributes("-alpha", 0.92)
        except Exception:
            pass

        # Home canvas
        self.hardware_cfg = _hardware_config()
        self.cv = ctk.CTkCanvas(self, width=WIDTH, height=HEIGHT, cursor="none",
                                highlightthickness=0, bg=BG)
        self.cv.pack(fill="both", expand=True)
        self._draw_chrome()
        self.status = StatusBar(self.cv)
        self.toast = Toast(self.cv)
        self.debug_overlay = DebugOverlay(self.cv)
        self.cflow = CoverFlow(self.cv, APPS)

        self._mic_id = self.cv.create_text(
            WIDTH - 28, HEIGHT - 24, text="", anchor="se",
            fill=TXTD, font=(FONT, 11))
        self._hint_id = self.cv.create_text(
            WIDTH // 2, HEIGHT - 24, anchor="s", fill="#48484A",
            font=(FONT, 10),
            text='1 click open/enter    2 clicks open keyboard    1 long click go back')
        self._swipe_hint_id = self.cv.create_text(
            WIDTH // 2, HEIGHT - 46, anchor="s", fill=TXTD,
            font=(FONT, 11, "bold"), text="")
        self._swipe_hint_after = None

        # Overlay frame â€” raw tk.Frame to avoid ghost rectangle
        self._vf = None
        self._vf_visible = False

        # State
        self.current_view = "home"
        self.assistant_chat_history = []

        self._cam_label = None
        self._cam_capture_btn = None
        self._cam_capture_reset_after = None
        self._cam_cap = None
        self._cam_after = None
        self._cam_running = False
        self._cam_last_frame = None
        self._cam_source_index = None
        self._cam_image = None
        if self._cam_capture_reset_after:
            try:
                self.after_cancel(self._cam_capture_reset_after)
            except Exception:
                pass
            self._cam_capture_reset_after = None
        if self._widget_alive(self._cam_capture_btn):
            try:
                self._cam_capture_btn.configure(text="Capture")
            except Exception:
                pass

        self.dark_mode = True
        self.bluetooth_enabled = False
        self.notifications_enabled = True
        self._light_text = False
        self._translate_target_menu_var = None
        self._wifi_password_entry = None

        # Timer
        self._timer_running = False
        self._timer_start = 0
        self._timer_id = self.cv.create_text(
            WIDTH - 28, 40, text="", anchor="ne", fill=TXT,
            font=(FONT, 13, "bold"))

        # â”€â”€ Voice controller â”€â”€
        cfg = _load_config()
        saved_mic = cfg.get("mic_index", None)
        if saved_mic is not None:
            mic_idx = int(saved_mic)
        else:
            mic_idx = VoiceController.auto_detect_mic()

        self.voice = VoiceController(
            on_result=self._voice_on_result,
            on_state=self._voice_on_state,
            on_error=self._voice_on_error,
            mic_index=mic_idx,
        )
        if saved_mic is not None:
            self.log.info("Loaded saved mic index: %d", mic_idx)

    
            # â”€â”€ Gemini Assistant (Google GenAI SDK) â”€â”€
        self.gemini_client = None
        self.gemini_enabled = False
        self.gemini_model = "gemini-2.0-flash"
        self.tts = TTSController()
        self.voice_loop = VoiceCommandLoop(
            on_command=self._voice_on_result,
            on_error=self._voice_on_error,
            mic_index=mic_idx,
        )
        # self.voice_loop.start()

        if genai:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                try:
                    self.gemini_client = genai.Client(api_key=api_key)
                    self.gemini_enabled = True
                    self.log.info("Gemini client initialized")
                except Exception:
                    self.log.exception("Gemini client initialization failed")
            else:
                self.log.warning("No GEMINI_API_KEY found")
        else:
            self.log.warning("google-genai SDK not installed")

        # Browser refs
        self._html = None
        self._b_url = None
        self._browser_entry = None
        self._browser_typing_mode = False
        self._translate_target_var = None
        self._last_rotary_click_at = 0.0
        self._settings_brightness_var = None
        self._settings_volume_var = None
        self._active_input = None
        self._active_submit = None
        self._input_submit_map = {}
        self._nav_focus_widget = None
        self._nav_focus_style = {}
        self._last_brightness_mode = "overlay"
        self._last_volume_mode = "none"
        self._touch_keyboard = TouchKeyboard(self)
        self._keyboard_drag_last_x = None
        self._keyboard_drag_accum = 0.0
        self._keyboard_ignore_until = 0.0
        self._keyboard_tap_ignore_until = 0.0
        self._keyboard_last_move_at = 0.0
        self._keyboard_last_move_at = 0.0
        self._home_last_move_at = 0.0

        # Handlers
        self._handlers = {
            "assistant": self.show_assistant,
            "localassistant": self.show_gemini,
            "camera":    self.show_camera,
            "photo":     self.show_photos,
            "translate": self.show_translate,
            "settings":  self.show_settings,
            "music":     self.show_music,
            "bluetooth": self.show_bluetooth,
            "track":     self.show_track,
            "gps":       self.show_track,
            "browser":   self.show_browser,
            "power":     self.show_power,
        }

        # â”€â”€ Rotary encoder (GPIO) â”€â”€
        self.rotary = SeesawRotaryController(
            on_rotate=self._rotary_rotate,
            on_select=self._rotary_click,
            on_select_long=self._rotary_long,
            on_up=None,
            on_down=None,
            on_left=None,
            on_right=None,
        )
        if not self.rotary.available:
            self.rotary = RotaryController(
                on_rotate=self._rotary_rotate,
                on_click=self._rotary_click,
                on_long_press=self._rotary_long,
            )
        self._last_touchpad_swipe_at = 0.0
        self._home_drag_anchor_x = None
        self._home_drag_accum = 0.0
        self._home_drag_last_move_at = 0.0
        self._home_drag_last_x = None
        self._home_drag_last_y = None
        self._home_move_residual = 0.0
        self._last_touchpad_motion_at = 0.0
        self._home_touch_started_at = 0.0
        self._home_last_deliberate_motion_at = 0.0
        self._home_hold_lock = False
        self._home_axis_lock = None
        self._keyboard_axis_lock = None
        self._home_drag_started = False
        self._home_drag_pending = 0.0
        self._keyboard_drag_started = False
        self._keyboard_drag_pending = 0.0
        self.touchpad = TouchpadController(
            on_swipe=lambda direction: self.after(0, lambda d=direction: self._touchpad_swipe(d)),
            on_tap=lambda: self.after(0, self._touchpad_tap),
            on_move=lambda x, y: self.after(0, lambda tx=x, ty=y: self._touchpad_move(tx, ty)),
        )

        # Keys â€” V, S, T work globally
        self.bind("<Left>",   self._k_left)
        self.bind("<Right>",  self._k_right)
        self.bind("<Up>",     self._k_up)
        self.bind("<Down>",   self._k_down)
        self.bind("<Return>", self._k_enter)
        self.bind("<Escape>", self._k_esc)
        self.bind("<v>",      self._k_v)
        self.bind("<V>",      self._k_v)
        self.bind("<s>",      self._k_s)
        self.bind("<S>",      self._k_s)
        self.bind("<t>",      self._k_t)
        self.bind("<T>",      self._k_t)
        self.bind_all("<KeyPress>", self._k_keypress, add="+")
        self.bind_all("<MouseWheel>", self._k_wheel)
        self.bind_all("<Button-4>", lambda e: self._nav(+1))
        self.bind_all("<Button-5>", lambda e: self._nav(-1))
        self.bind_all("<FocusIn>", self._global_text_input_focus, add="+")
        self.bind_all("<Button-1>", self._global_text_input_click, add="+")
        self.bind("<Control-q>", lambda e: self._on_close())
        self.bind("<Control-Escape>", lambda e: self._go_home())
        self.bind("<F12>", lambda e: self._toggle_debug_overlay())

        # Clean exit
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._apply_theme_palette()
        self._last_time = time.perf_counter()
        self._tick()

    def _on_close(self):
        """Clean shutdown â€” release all resources."""
        self.log.info("Shutting down â€¦")
        self.voice.shutdown()
        self.voice_loop.shutdown()
        self.rotary.shutdown()
        self.touchpad.shutdown()
        self.tts.shutdown()
        self._stop_camera()
        self._close_browser()
        self.destroy()

    def _system_poweroff(self):
        """Request a real system shutdown instead of only closing the app."""
        self.toast.show("Shutting downâ€¦", 1200)
        self.status.append("System poweroff requested")
        self.after(300, lambda: subprocess.Popen(["sudo", "shutdown", "-h", "now"]))

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Voice callbacks (called from worker thread â€” must dispatch to UI)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _voice_on_result(self, text):
        """Called from voice worker thread with recognized text."""
        self.after(0, lambda: self._voice_handle_result(text))

    def _voice_on_state(self, state):
        """Called from voice worker thread on state transition."""
        self.after(0, lambda: self._voice_handle_state(state))

    def _voice_on_error(self, msg):
        """Called from voice worker thread on error."""
        self.after(0, lambda: self.toast.show(msg))

    def _voice_handle_result(self, text):
        """UI-thread handler for recognized speech."""
        self.toast.show(f'"{text}"', 2000)
        self.status.append(f'Heard: "{text}"')
        self._voice_route(text.lower().strip())

    def _voice_handle_state(self, state):
        """UI-thread handler for voice state changes."""
        if state == VoiceState.LISTENING:
            self.cv.itemconfigure(self._mic_id, text="Listeningâ€¦", fill=AMB)
            self.toast.show("Speak nowâ€¦")
        elif state == VoiceState.PROCESSING:
            self.cv.itemconfigure(self._mic_id, text="Processingâ€¦", fill=C)
            self.toast.show("Processingâ€¦", 1500)
        elif state == VoiceState.IDLE:
            self.cv.itemconfigure(self._mic_id, text="", fill=TXTD)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Rotary callbacks (called from GPIO thread)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _rotary_rotate(self, direction):
        """Hardware thread â†’ UI thread: global navigation move."""
        self.after(0, lambda d=direction: self._global_move("next" if d > 0 else "prev"))

    def _rotary_click(self):
        """Hardware thread â†’ UI thread: global select / browser double-click keyboard."""
        self.after(0, self._handle_rotary_click)


    def _handle_rotary_click(self):
        now = time.perf_counter()

        # In browser mode, delay single-click activation briefly so a quick
        # second click can open the keyboard instead of activating the page.
        if self.current_view == "browser" and self._browser_is_open() and not self._touch_keyboard.visible:
            pending = getattr(self, "_pending_rotary_browser_single", None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except Exception:
                    pass
                self._pending_rotary_browser_single = None
                self._last_rotary_click_at = 0.0
                self._browser_show_type_keyboard()
                return

            self._last_rotary_click_at = now
            self._pending_rotary_browser_single = self.after(260, self._commit_pending_rotary_browser_click)
            return

        last = getattr(self, "_last_rotary_click_at", 0.0)
        double = (now - last) <= 0.45 and last > 0.0

        if double:
            self._last_rotary_click_at = 0.0
            if self.current_view == "photos" and not self._touch_keyboard.visible:
                self._show_photo_delete_keyboard()
            elif self._active_input_alive():
                self._show_touch_keyboard()
            elif self._touch_keyboard.visible:
                self._hide_touch_keyboard()
            return

        self._last_rotary_click_at = now
        self._global_select()


    def _commit_pending_rotary_browser_click(self):
        self._pending_rotary_browser_single = None
        if self.current_view == "browser" and self._browser_is_open() and not self._touch_keyboard.visible:
            self._global_select()


    def _rotary_long(self):
        """Hardware thread → UI thread: global back/exit."""
        def _cb():
            pending = getattr(self, "_pending_rotary_browser_single", None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except Exception:
                    pass
                self._pending_rotary_browser_single = None
            self._global_back()
        self.after(0, _cb)

    def _adjust_alpha(self, delta):
        current = getattr(self, "_display_brightness", None)
        if current is None:
            current = 1.0
        self._display_brightness = max(0.20, min(1.00, round(current + delta, 2)))

        applied = False
        for backlight_dir in Path('/sys/class/backlight').glob('*'):
            try:
                max_b = int((backlight_dir / 'max_brightness').read_text().strip())
                value = max(1, int(round(max_b * self._display_brightness)))
                subprocess.run(['sudo', 'sh', '-lc', f"echo {value} > {backlight_dir / 'brightness'}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                applied = True
            except Exception:
                pass
        try:
            display = os.environ.get("DISPLAY", ":0")
            xrandr_out = subprocess.check_output(["xrandr", "--current"], env={**os.environ, "DISPLAY": display}, stderr=subprocess.DEVNULL, text=True)
            outputs = [line.split()[0] for line in xrandr_out.splitlines() if " connected" in line]
            for output_name in outputs:
                result = subprocess.run(["xrandr", "--output", output_name, "--brightness", str(self._display_brightness)], env={**os.environ, "DISPLAY": display}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode == 0:
                    applied = True
        except Exception:
            pass

        if applied:
            self._last_brightness_mode = "system"
            self.toast.show(f"Brightness {int(self._display_brightness * 100)}%")
            self.status.append("Brightness applied")
            return

        try:
            self.attributes("-alpha", self._display_brightness)
            self._last_brightness_mode = "overlay-alpha"
            self.toast.show(f"Brightness {int(self._display_brightness * 100)}%")
            self.status.append("Brightness fallback applied")
        except Exception as exc:
            self._last_brightness_mode = f"error:{exc}"
            self.toast.show(f"Brightness error: {exc}")

    def _speaker_hw_device(self):
        cached = getattr(self, "_speaker_hw_cache", None)
        if cached:
            return cached
        try:
            out = subprocess.check_output(["aplay", "-l"], stderr=subprocess.DEVNULL, text=True)
            for line in out.splitlines():
                low = line.lower()
                if "max98357a" in low:
                    m = re.search(r"card\s+(\d+):.*device\s+(\d+):", line, re.IGNORECASE)
                    if m:
                        card = m.group(1)
                        dev = m.group(2)
                        self._speaker_card_cache = card
                        self._speaker_dev_cache = dev
                        self._speaker_hw_cache = f"plughw:{card},{dev}"
                        return self._speaker_hw_cache
        except Exception:
            pass
        self._speaker_card_cache = "2"
        self._speaker_dev_cache = "0"
        self._speaker_hw_cache = "plughw:2,0"
        return self._speaker_hw_cache

    def _speaker_sink_id(self):
        cached = getattr(self, "_speaker_sink_cache", None)
        if cached is not None:
            return cached
        preferred = None
        fallback = None
        try:
            out = subprocess.check_output(["wpctl", "status"], stderr=subprocess.DEVNULL, text=True)
            in_sinks = False
            for raw in out.splitlines():
                line = raw.strip()
                if line.startswith("├─ Sinks:") or line.startswith("└─ Sinks:"):
                    in_sinks = True
                    continue
                if in_sinks and line.startswith("├─ Sources:"):
                    break
                if not in_sinks or not line:
                    continue
                m = re.search(r"([\*\s]*)?(\d+)\.\s+(.+?)\s+\[vol:", line)
                if not m:
                    continue
                sink_id = m.group(2)
                desc = m.group(3).lower()
                if "hdmi" in desc:
                    continue
                if any(k in desc for k in ("speaker", "analog", "stereo")) and fallback is None:
                    fallback = sink_id
                if any(k in desc for k in ("speaker", "analog")):
                    preferred = sink_id
                    break
            self._speaker_sink_cache = preferred or fallback
            return self._speaker_sink_cache
        except Exception:
            pass
        self._speaker_sink_cache = None
        return None

    def _ensure_speaker_sink(self):
        sink_id = self._speaker_sink_id()
        if sink_id:
            try:
                subprocess.run(["wpctl", "set-default", str(sink_id)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                self._last_volume_mode = f"wpctl sink {sink_id}"
                return sink_id
            except Exception:
                pass
        return None

    def _speaker_card_index(self):
        card = getattr(self, "_speaker_card_cache", None)
        if card:
            return str(card)
        _ = self._speaker_hw_device()
        return str(getattr(self, "_speaker_card_cache", "2"))

    def _speaker_volume_targets(self):
        cached = getattr(self, "_speaker_volume_targets_cache", None)
        if cached is not None:
            return cached
        targets = []
        card = self._speaker_card_index()
        preferred_names = ["PCM", "Digital", "Speaker", "Master", "Playback", "Headphone"]
        try:
            out = subprocess.check_output(["amixer", "-c", card, "scontrols"], stderr=subprocess.DEVNULL, text=True)
            for name in preferred_names:
                if f"'{name}'" in out:
                    targets.append((card, name))
        except Exception:
            pass
        dedup = []
        seen = set()
        for item in targets:
            if item not in seen:
                seen.add(item)
                dedup.append(item)
        self._speaker_volume_targets_cache = dedup
        return dedup

    def _find_volume_target(self):
        targets = self._speaker_volume_targets()
        if targets:
            return targets[0]
        return None

    def _run_speaker_test(self):
        device = self._speaker_hw_device()
        self._ensure_speaker_sink()
        self.toast.show("Speaker test", 900)
        self.status.append(f"Speaker test -> {device}")
        def _worker():
            try:
                subprocess.run(["speaker-test", "-D", device, "-c", "2", "-t", "wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.5, check=False)
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                self.after(0, lambda e=exc: self.toast.show(f"Speaker test failed: {e}", 1400))
        _start_safe_thread(_worker, "SpeakerTest", self.log)

    def _adjust_volume(self, delta):
        sink_id = self._ensure_speaker_sink()
        step = "5%+" if delta > 0 else "5%-"
        applied = False

        for card, name in self._speaker_volume_targets():
            try:
                cmd = ["amixer", "-c", str(card), "sset", name, step, "unmute"]
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode == 0:
                    self._volume_target = (card, name)
                    self._last_volume_mode = f"alsa card {card} {name}"
                    applied = True
                    break
            except Exception:
                pass

        if sink_id:
            try:
                result = subprocess.run(["wpctl", "set-volume", str(sink_id), step], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode == 0:
                    self._last_volume_mode = f"{self._last_volume_mode} + wpctl sink {sink_id}" if applied else f"wpctl sink {sink_id}"
                    applied = True
            except Exception:
                pass

        if applied:
            self.toast.show(f"Volume {self._query_volume_pct() or ''}%".strip())
            self.status.append("Volume applied")
            return

        self._last_volume_mode = "unavailable"
        self.toast.show("Volume control unavailable")
        self.status.append("Volume: no compatible mixer")

    def _brightness_pct(self):
        level = getattr(self, "_display_brightness", None)
        if level is None:
            try:
                level = float(self.attributes("-alpha"))
            except Exception:
                level = 1.0
            self._display_brightness = level
        return int(round(level * 100))

    def _query_volume_pct(self):
        for card, name in self._speaker_volume_targets():
            try:
                out = subprocess.check_output(["amixer", "-c", str(card), "sget", name], stderr=subprocess.DEVNULL, text=True)
                m = re.search(r"\[(\d{1,3})%\]", out)
                if m:
                    self._volume_target = (card, name)
                    return int(m.group(1))
            except Exception:
                pass
        sink_id = self._ensure_speaker_sink()
        wp_targets = [["wpctl", "get-volume", str(sink_id)]] if sink_id else []
        wp_targets.append(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]) 
        for cmd in wp_targets:
            try:
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
                m = re.search(r"(\d+(?:\.\d+)?)", out)
                if m:
                    return int(round(float(m.group(1)) * 100))
            except Exception:
                pass
        return None

    def _refresh_settings_status(self):
        if self._settings_brightness_var is not None:
            try:
                self._settings_brightness_var.set(f"Brightness: {self._brightness_pct()}%")
            except Exception:
                pass
        if self._settings_volume_var is not None:
            try:
                pct = self._query_volume_pct()
                self._settings_volume_var.set(f"Volume: {pct if pct is not None else '--'}%")
            except Exception:
                pass

    def show_sysinfo(self):
        p = self._view("sysinfo", "System Info", "Device diagnostics")
        box = ctk.CTkTextbox(p, font=(FONT, 12), fg_color="#1C1C1E", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)

        info = [
            f"Platform: {platform.platform()}",
            f"Machine:  {platform.machine()}",
            f"Python:   {sys.version.split()[0]}",
            f"Display:  {WIDTH}x{HEIGHT} @ {TARGET_FPS}fps",
            f"Pi mode:  {IS_PI}",
            f"OpenCV:   {'âœ“' if cv2 else 'âœ—'}",
            f"STT:      {'âœ“' if sr else 'âœ—'}",
            f"GPIO:     {'âœ“' if GPIO else 'âœ—'}",
            f"Rotary:   {'âœ“ active' if self.rotary.available else 'âœ— inactive'}",
            f"Voice:    {self.voice.state.value}",
            f"Photos:   {len(os.listdir(PHOTOS_DIR))} files",
        ]
        if psutil:
            info.append(f"CPU:      {psutil.cpu_count()} cores")
            info.append(f"RAM:      {psutil.virtual_memory().total // (1024**3)} GB")

        box.insert("end", "\n".join(info))
        box.configure(state="disabled")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Power
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _open_dev_mode(self):
        candidates = [
            ["x-terminal-emulator"],
            ["xterm"],
            ["lxterminal"],
            ["xfce4-terminal"],
            ["gnome-terminal"],
            ["konsole"],
        ]
        for cmd in candidates:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.toast.show("Dev Mode opened")
                self.status.append(f"Dev Mode -> {' '.join(cmd)}")
                self.after(180, self._on_close)
                return
            except Exception:
                continue
        self.toast.show("No terminal app found")
        self.status.append("Dev Mode unavailable: no terminal emulator")

    def show_power(self):
        p = self._view("power", "Power")
        w = ctk.CTkFrame(p, fg_color="transparent")
        w.pack(expand=True)

        power_btn = ctk.CTkButton(w, text="Power Off", fg_color=RED,
                       hover_color="#FF453A", height=44, corner_radius=12,
                       font=(FONT, 15), text_color="white",
                       command=self._system_poweroff)
        power_btn.pack(pady=8, padx=48, fill="x")

        restart_btn = ctk.CTkButton(w, text="Restart", fg_color=PNLE,
                       hover_color="#3A3A3C", height=44, corner_radius=12,
                       font=(FONT, 15), text_color=TXT,
                       command=lambda: (self._on_close(),
                                        os.execl(sys.executable, sys.executable, *sys.argv)))
        restart_btn.pack(pady=8, padx=48, fill="x")

        dev_btn = ctk.CTkButton(w, text="Dev Mode", fg_color=PNLE,
                       hover_color="#3A3A3C", height=40, corner_radius=12,
                       font=(FONT, 13), text_color=TXT,
                       command=self._open_dev_mode)
        dev_btn.pack(pady=8, padx=48, fill="x")

        info_btn = ctk.CTkButton(w, text="System Info", fg_color=PNLE,
                       hover_color="#3A3A3C", height=40, corner_radius=12,
                       font=(FONT, 13), text_color=TXT,
                       command=self.show_sysinfo)
        info_btn.pack(pady=8, padx=48, fill="x")

        cancel_btn = ctk.CTkButton(w, text="Cancel", fg_color="transparent",
                       hover_color=PNL, height=36, corner_radius=12,
                       font=(FONT, 13), text_color=TXTD,
                       command=self._go_home)
        cancel_btn.pack(pady=16)

        self._prime_focus(power_btn)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  WiFi
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _wifi_scan(self):
        networks = []
        try:
            out = subprocess.check_output(["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi", "list"], stderr=subprocess.DEVNULL, text=True)
            seen = set()
            for line in out.splitlines():
                parts = line.split(":")
                if len(parts) >= 3:
                    ssid = parts[0].strip() or "<Hidden>"
                    sec = parts[1].strip()
                    sig = parts[2].strip()
                    key = (ssid, sec)
                    if key in seen:
                        continue
                    seen.add(key)
                    networks.append((ssid, sec, sig))
        except Exception:
            pass
        if not networks:
            networks = [("No networks found", "", "")]
        return networks


    def _open_captive_portal(self):
        self.status.append("WiFi -> Captive Portal")
        self.toast.show("Opening captive portal…", 1200)
        self._open_external_browser("http://neverssl.com")

    def show_wifi(self):
        p = self._view("wifi", "WiFi", "Available networks")
        self._wifi_networks = self._wifi_scan()
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        captive_btn = ctk.CTkButton(top, text="Captive Portal", anchor="center",
                                    fg_color=C, hover_color=CD, text_color="white",
                                    command=self._open_captive_portal)
        captive_btn.pack(fill="x")
        box = ctk.CTkScrollableFrame(p, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=8, pady=8)
        first_btn = captive_btn
        for ssid, sec, sig in self._wifi_networks:
            label = f"{ssid}  {sig}%" if sig else ssid
            btn = ctk.CTkButton(box, text=label, anchor="w",
                                fg_color=PNLE, hover_color="#3A3A3C", text_color="white",
                                command=lambda s=ssid, secu=sec: self._show_wifi_join(s, secu))
            btn.pack(fill="x", pady=4)
            if first_btn is None:
                first_btn = btn
        if first_btn is not None:
            self._prime_focus(first_btn)

    def _show_wifi_join(self, ssid, security):
        p = self._view("wifi_join", f"WiFi · {ssid}", "Enter password to join")
        ctk.CTkLabel(p, text=f"Security: {security or 'Open'}", font=(FONT, 12), text_color=TXTD).pack(pady=(8, 4))
        ent = ctk.CTkEntry(p, placeholder_text="WiFi password", font=(FONT_MONO, 13), fg_color=PNL, text_color=TXT, border_color=CD)
        ent.pack(fill="x", padx=10, pady=(4, 8))
        self._wifi_password_entry = ent

        def join(_=None):
            pwd = ent.get().strip()
            try:
                if security:
                    result = subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", pwd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    result = subprocess.run(["nmcli", "dev", "wifi", "connect", ssid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode == 0:
                    self.toast.show("WiFi connected")
                    self.status.append(f"WiFi -> {ssid}")
                    self.after(250, self._open_captive_portal)
                    self.show_wifi()
                else:
                    self.toast.show("WiFi join failed")
            except Exception as exc:
                self.toast.show(f"WiFi error: {exc}")

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(pady=(4, 8))
        join_btn = ctk.CTkButton(row, text="Join", command=join, fg_color=C, hover_color=CD, text_color="white")
        join_btn.pack(side="left", padx=4)
        captive_btn = ctk.CTkButton(row, text="Captive Portal", command=self._open_captive_portal, fg_color=PNLE, hover_color="#3A3A3C", text_color="white")
        captive_btn.pack(side="left", padx=4)
        cancel_btn = ctk.CTkButton(row, text="Back", command=self.show_wifi, fg_color=PNLE, hover_color="#3A3A3C", text_color="white")
        cancel_btn.pack(side="left", padx=4)
        ent.bind("<Return>", join)
        self._register_text_input(ent, join)
        self.after(120, lambda: self._activate_text_input(ent, join))

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Bluetooth
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_bluetooth(self):
        p = self._view("bluetooth", "Bluetooth", "Nearby device scan (simulated)")

        box = ctk.CTkTextbox(p, font=(FONT, 13),
                              fg_color="#1C1C1E", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", "Press Scan to search â€¦\n")
        box.configure(state="disabled")

        def scan():
            import random
            devs = ["Phone â€“ Pixel 9 Pro", "Laptop â€“ MacBook Pro",
                    "Earbuds â€“ AirPods Pro", "Watch â€“ Galaxy Watch",
                    "Speaker â€“ JBL Flip 6", "Controller â€“ PS5 DualSense"]
            random.shuffle(devs)
            now = datetime.now().strftime("%H:%M:%S")
            box.configure(state="normal")
            box.insert("end", f"\n[{now}] Found {len(devs)} devices:\n")
            for d in devs:
                box.insert("end", f"  â–¸ {d}\n")
            box.configure(state="disabled")
            box.see("end")

        self._btn_c(p, "Scan", scan, True)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Track / GPS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_track(self):
        p = self._view("track", "Track / Location",
                        "IP geolocation demo Â· real device uses GPS")

        box = ctk.CTkTextbox(p, font=(FONT, 13),
                              fg_color="#1C1C1E", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", "Press Refresh to locate â€¦\n")
        box.configure(state="disabled")

        def go():
            box.configure(state="normal")
            box.insert("end", "\nLocating â€¦\n")
            box.configure(state="disabled")
            self.update_idletasks()
            def _loc():
                loc = self._ip_loc()
                self.after(0, lambda: _show(loc))
            def _show(loc):
                try:
                    if not box.winfo_exists():
                        return
                    box.configure(state="normal")
                    box.insert("end", loc + "\n")
                    box.configure(state="disabled")
                    box.see("end")
                except Exception:
                    pass
            _start_safe_thread(_loc, "IPLocation", self.log)

        self._btn_c(p, "Refresh", go, True)

    def _ip_loc(self):
        if not requests:
            return "requests not available."
        try:
            r = requests.get("https://ipapi.co/json/", timeout=5)
            if r.status_code != 200:
                return f"HTTP {r.status_code}"
            d = r.json()
            return (f"  {d.get('city','?')}, {d.get('region','?')}, "
                    f"{d.get('country_name','?')}\n"
                    f"  Lat {d.get('latitude','?')}  Â·  Lon {d.get('longitude','?')}")
        except Exception as e:
            return f"Failed: {e}"

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Music
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_music(self):
        p = self._view("music", "Music")

        ctk.CTkLabel(p, text="Lofi Beats for Coding",
                      font=(FONT, 18, "bold"),
                      text_color=TXT).pack(pady=(24, 2))
        ctk.CTkLabel(p, text="Chillhop Records",
                      font=(FONT, 12), text_color=TXTD).pack(pady=(0, 20))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(pady=8)
        for t, sym in [("Prev", "â®"), ("Play", ">"), ("Next", "â­")]:
            ctk.CTkButton(row, text=sym, width=56, height=56, corner_radius=28,
                           fg_color=PNLE, hover_color="#3A3A3C",
                           text_color=TXT, font=(FONT, 18),
                           command=lambda x=t: self.status.append(f"Music: {x}")
                           ).pack(side="left", padx=12)

        ctk.CTkLabel(p, text="Volume", font=(FONT, 11),
                      text_color=TXTD).pack(pady=(24, 4))
        vol = ctk.CTkSlider(p, from_=0, to=100, number_of_steps=10,
                             progress_color=C, button_color=TXT,
                             button_hover_color=TXTD, fg_color=PNLE)
        vol.set(70); vol.pack(fill="x", padx=48)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Shared helpers
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _btn(self, parent, text, cmd, primary=False, w=None):
        compact = WIDTH <= 640 or HEIGHT <= 400
        kw = dict(text=text, command=cmd, corner_radius=14 if compact else 20,
                  height=26 if compact else 32,
                  font=(FONT, 9, "bold") if (primary and compact) else ((FONT, 12, "bold") if primary else ((FONT, 9) if compact else (FONT, 12))),
                  fg_color=C if primary else PNLE,
                  hover_color=CD if primary else "#3A3A3C",
                  text_color="white")
        if w:
            kw["width"] = w
        ctk.CTkButton(parent, **kw).pack(side="left", padx=2 if compact else 4)


    def _toggle_debug_overlay(self):
        self.debug_overlay.toggle()

    def _debug_lines(self):
        focus = self.focus_get()
        focus_desc = "-"
        try:
            if focus is not None and focus.winfo_exists():
                focus_desc = f"{focus.winfo_class()}"
        except Exception:
            focus_desc = "-"
        selected = self.cflow.current()["label"] if self.cflow.current() else "-"
        keyboard_token = "-"
        if self._touch_keyboard.visible:
            keyboard_token = self._touch_keyboard.LAYOUT()[self._touch_keyboard.sel_row][self._touch_keyboard.sel_col]
        return [
            f"view: {self.current_view}",
            f"selected: {selected}",
            f"focus: {focus_desc}",
            f"typing: {self._typing()}",
            f"kbd: {'on' if self._touch_keyboard.visible else 'off'} {keyboard_token}",
            f"touchpad: {'yes' if self.touchpad.available else 'no'}",
            f"rotary: {'yes' if self.rotary.available else 'no'}",
            f"voice: {self.voice.state.value}",
            f"bright: {self._last_brightness_mode}",
            f"volume: {self._last_volume_mode}",
        ]

    def _btn_c(self, parent, text, cmd, primary=False):
        ctk.CTkButton(parent, text=text, command=cmd, width=180, height=38,
                       corner_radius=20,
                       font=(FONT, 13, "bold") if primary else (FONT, 13),
                       fg_color=C if primary else PNLE,
                       hover_color=CD if primary else "#3A3A3C",
                       text_color="white").pack(pady=(0, 10))

    @staticmethod
    def _safe(fn):
        try:
            fn()
        except Exception:
            pass

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Main loop
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _tick(self):
        now = time.perf_counter()
        dt = max(1e-3, now - self._last_time)
        self._last_time = now
        if self.current_view == "home":
            self.cflow.step(dt)
        self.status.tick()

        # Timer display
        if self._timer_running:
            elapsed = now - self._timer_start
            m, s = divmod(int(elapsed), 60)
            self.cv.itemconfigure(self._timer_id, text=f"â± {m:02d}:{s:02d}")

        self.debug_overlay.update(self._debug_lines())
        self.after(max(1, int(1000 / TARGET_FPS)), self._tick)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    VAApp().mainloop()




