import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys
import time
import threading
import struct
import enum
import logging
import subprocess
import tkinter as tk
from datetime import datetime
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
    # Raspberry Pi
    plat = platform.platform().lower()
    if "raspberrypi" in plat:
        return True
    # Radxa / Amlogic / Rockchip — check device-tree compatible string
    for dt_path in ("/proc/device-tree/compatible", "/sys/firmware/devicetree/base/compatible"):
        try:
            with open(dt_path, "rb") as f:
                compat = f.read().lower()
            if any(k in compat for k in (b"radxa", b"amlogic", b"rockchip", b"allwinner", b"broadcom")):
                return True
        except Exception:
            pass
    # Fallback: any aarch64 Linux without a full desktop display size is likely embedded
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
    BASE_ICON = 112
    SPACING = 148
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
    ("music.png",          "Music"),
    ("photo.png",          "Photo"),
    ("plugin.png",         "Plugin"),
    ("settings.png",       "Settings"),
    ("translate.png",      "Translate"),
    ("video.png",          "Video"),
    ("browser.png",        "Browser"),
    ("power.png",          "Power"),
]

BUILD_STR = "VA-OS1.1 Â· Pandora Build"

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

            # Open microphone
            if self._mic_index is not None:
                mic = sr.Microphone(device_index=self._mic_index)
            else:
                mic = sr.Microphone()

            try:
                source = mic.__enter__()
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
    BUTTON_DEBOUNCE_SEC = 0.16
    LONG_PRESS_SEC = 0.75

    PIN_SELECT = 1
    PIN_UP = 2
    PIN_LEFT = 3
    PIN_DOWN = 4
    PIN_RIGHT = 5
    EXPECTED_PRODUCT = 5740

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
        i2c_addr=0x49,
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

            product = (self._seesaw.get_version() >> 16) & 0xFFFF
            if product != self.EXPECTED_PRODUCT:
                raise RuntimeError(
                    f"Unexpected seesaw product {product}; expected {self.EXPECTED_PRODUCT}"
                )

            for pin in (
                self.PIN_SELECT,
                self.PIN_UP,
                self.PIN_LEFT,
                self.PIN_DOWN,
                self.PIN_RIGHT,
            ):
                self._seesaw.pin_mode(pin, self._seesaw.INPUT_PULLUP)

            self._buttons = {
                "select": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_SELECT),
                "up": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_UP),
                "left": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_LEFT),
                "down": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_DOWN),
                "right": seesaw_digitalio.DigitalIO(self._seesaw, self.PIN_RIGHT),
            }

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
            self.log.info("Initialized ANO seesaw encoder at I2C 0x%02X", self._addr)
            return True
        except Exception:
            self.log.exception("Failed to initialize ANO seesaw rotary via Blinka")
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
                    if product != self.EXPECTED_PRODUCT:
                        raise RuntimeError(
                            f"Unexpected seesaw product {product}; expected {self.EXPECTED_PRODUCT}"
                        )

                    try:
                        self._linux_write(self._STATUS_BASE, self._STATUS_SWRST, bytes([0xFF]), fd=fd)
                        time.sleep(0.5)
                    except Exception:
                        pass

                    for pin in (
                        self.PIN_SELECT,
                        self.PIN_UP,
                        self.PIN_LEFT,
                        self.PIN_DOWN,
                        self.PIN_RIGHT,
                    ):
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
                        "Initialized ANO seesaw encoder using Linux I2C fallback on /dev/i2c-%d @ 0x%02X",
                        bus,
                        addr,
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
        return {
            "select": not bool(value & (1 << self.PIN_SELECT)),
            "up": not bool(value & (1 << self.PIN_UP)),
            "left": not bool(value & (1 << self.PIN_LEFT)),
            "down": not bool(value & (1 << self.PIN_DOWN)),
            "right": not bool(value & (1 << self.PIN_RIGHT)),
        }

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
    TAP_MIN_SEC = 0.055             # 55ms minimum contact to count as a tap (ghost filter)
    MOVE_THRESHOLD = 4
    TAP_MAX_TRAVEL = 48             # tighter tap travel so swipes do not become accidental opens
    SWIPE_DEBOUNCE_SEC = 0.0
    RELEASE_TIMEOUT_SEC = 0.065     # 65ms release timeout (was 10ms, too short)
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
                key = (cs_pin, dr_pin)
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
        self._label = canvas.create_text(
            0, 0, text="", fill=TXT, font=(FONT, 15))

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
                self.cv.itemconfigure(self._label, text=label, fill=TXT)
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

    LETTER_TOKENS = list("abcdefghijklmnopqrstuvwxyz") + [TOK_BACK, TOK_ENTER, TOK_CAPS, TOK_SYMBOLS, TOK_SPACE]
    SYMBOL_TOKENS = list("1234567890") + ["-", "/", ":", ";", "(", ")", "$", "&", "@", '"', ".", ",", "?", "!", "+", "=", "#", "%", "*", "_"] + [TOK_BACK, TOK_ENTER, TOK_LETTERS, TOK_SPACE]
    VISIBLE_SLOTS = 7

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

    @property
    def TOKENS(self):
        return self.SYMBOL_TOKENS if self._symbol_mode else self.LETTER_TOKENS

    @property
    def LAYOUT(self):
        return [self.TOKENS]

    def ensure(self):
        if self.window is not None:
            return

        self.window = tk.Frame(
            self.app,
            bg="#050506",
            bd=1,
            highlightthickness=1,
            highlightbackground="#2C2C2E",
        )

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
                height=40,
                corner_radius=9,
                border_width=1,
                border_color="#2A2A2E",
                font=(FONT, 12, "bold"),
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
        if len(token) == 1 and token.isalpha():
            return token.upper() if self._caps_lock else token
        return token

    def _normalize_viewport(self):
        total = len(self.TOKENS)
        if total <= self.VISIBLE_SLOTS:
            self._viewport_start = 0
            return
        center = self.VISIBLE_SLOTS // 2
        self._viewport_start = max(0, min(self.sel_col - center, total - self.VISIBLE_SLOTS))

    def _clamp_selection(self):
        total = len(self.TOKENS)
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
        self.window.lift()
        self.window.tkraise()
        if hasattr(self.app, "_vf") and self.app._vf is not None:
            try:
                self.app._vf.lift()
            except Exception:
                pass
            self.window.lift(self.app._vf)
            self.window.tkraise(self.app._vf)
        self.app.lift()
        self.app.update_idletasks()
        self.refresh()

    def hide(self):
        if self.window is not None:
            self.window.place_forget()
        self.visible = False

    def _position(self, force=False):
        self.app.update_idletasks()
        app_w = max(self.app.winfo_width(), WIDTH)
        app_h = max(self.app.winfo_height(), HEIGHT)
        abs_h = 146 if app_h <= 420 else 156
        geometry = (app_w, abs_h)
        if not force and geometry == self._last_geometry:
            return
        width = min(app_w - 24, 616)
        self.window.place(
            relx=0.5,
            rely=1.0,
            anchor="s",
            width=width,
            height=abs_h,
            y=-6,
        )
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

        total = len(self.TOKENS)
        for slot, btn in enumerate(self._rail_buttons):
            idx = self._viewport_start + slot
            if idx >= total:
                btn.configure(text="", state="disabled", fg_color="#050506", hover_color="#050506",
                              border_color="#050506", text_color="#050506")
                continue
            token = self.TOKENS[idx]
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
        self.sel_col = max(0, min(len(self.TOKENS) - 1, self.sel_col + delta))
        self.refresh()

    def activate(self):
        if not self.visible:
            return
        self.press(self.TOKENS[self.sel_col])

    def _press_viewport_slot(self, slot):
        idx = self._viewport_start + slot
        if 0 <= idx < len(self.TOKENS):
            self.sel_col = idx
            self.press(self.TOKENS[idx])

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
            idx = self.TOKENS.index(token)
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
        self.title("Aries Launcher")
        self.resizable(False, False)
        self.configure(bg=BG)

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
        self.cv = ctk.CTkCanvas(self, width=WIDTH, height=HEIGHT,
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
        self.cv.create_text(
            WIDTH // 2, HEIGHT - 24, anchor="s", fill="#48484A",
            font=(FONT, 10),
            text='S Screenshot    T Timer    Enter Open    Esc Back')

        # Overlay frame â€” raw tk.Frame to avoid ghost rectangle
        self._vf = None
        self._vf_visible = False

        # State
        self.current_view = "home"
        self.assistant_chat_history = []

        self._cam_label = None
        self._cam_cap = None
        self._cam_after = None
        self._cam_running = False
        self._cam_last_frame = None
        self._cam_source_index = None
        self._cam_image = None

        self.dark_mode = True
        self.bluetooth_enabled = False
        self.notifications_enabled = True

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

        # Handlers
        self._handlers = {
            "assistant": self.show_assistant,
            "localassistant": self.show_assistant,
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
            on_up=lambda: self.after(0, lambda: self._adjust_alpha(+0.05)),
            on_down=lambda: self.after(0, lambda: self._adjust_alpha(-0.05)),
            on_left=lambda: self.after(0, lambda: self._adjust_volume(+1)),
            on_right=lambda: self.after(0, lambda: self._adjust_volume(-1)),
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
        self._home_move_residual = 0.0
        self._last_touchpad_motion_at = 0.0
        self._home_touch_started_at = 0.0
        self._home_last_deliberate_motion_at = 0.0
        self._home_hold_lock = False
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
        """Hardware thread â†’ UI thread: global select."""
        self.after(0, self._global_select)

    def _rotary_long(self):
        """Hardware thread â†’ UI thread: summon voice."""
        self.after(0, lambda: self.voice.activate() if not self._typing() else None)

    def _adjust_alpha(self, delta):
        if not hasattr(self, "_display_brightness"):
            try:
                self._display_brightness = float(self.attributes("-alpha"))
            except Exception:
                self._display_brightness = 0.92

        self._display_brightness = max(0.30, min(1.00, round(self._display_brightness + delta, 2)))

        try:
            display = os.environ.get("DISPLAY", ":0")
            xrandr_out = subprocess.check_output(
                ["xrandr", "--current"],
                env={**os.environ, "DISPLAY": display},
                stderr=subprocess.DEVNULL,
                text=True,
            )
            output_name = None
            for line in xrandr_out.splitlines():
                if " connected" in line:
                    output_name = line.split()[0]
                    break

            if output_name:
                result = subprocess.run(
                    ["xrandr", "--output", output_name, "--brightness", str(self._display_brightness)],
                    env={**os.environ, "DISPLAY": display},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    self._last_brightness_mode = f"xrandr:{output_name}"
                    self.toast.show(f"Brightness {int(self._display_brightness * 100)}%")
                    self.status.append(f"Brightness via xrandr ({output_name})")
                    return
        except Exception:
            pass

        try:
            self.attributes("-alpha", self._display_brightness)
            self._last_brightness_mode = "overlay-alpha"
            self.toast.show(f"Overlay {int(self._display_brightness * 100)}%")
            self.status.append("Brightness fallback: overlay alpha")
        except Exception as exc:
            self._last_brightness_mode = f"error:{exc}"
            self.toast.show(f"Brightness error: {exc}")

    def _adjust_volume(self, delta):
        step = "5%+" if delta > 0 else "5%-"

        if not hasattr(self, "_volume_target"):
            self._volume_target = None
            preferred_cards = ["2", "0", "1", "3"]
            preferred_names = ["Digital", "PCM", "Speaker", "Master", "Headphone", "Playback"]

            for card in preferred_cards:
                try:
                    out = subprocess.check_output(
                        ["amixer", "-c", card, "scontrols"],
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                except Exception:
                    continue

                for name in preferred_names:
                    if f"'{name}'" in out:
                        self._volume_target = (card, name)
                        break
                if self._volume_target:
                    break

        if self._volume_target:
            card, name = self._volume_target
            try:
                result = subprocess.run(
                    ["amixer", "-c", card, "sset", name, step],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    self._last_volume_mode = f"alsa card {card} {name}"
                    self.toast.show(f"Volume {'up' if delta > 0 else 'down'}")
                    self.status.append(f"Volume via {name} on card {card}")
                    return
            except Exception:
                pass

        self._last_volume_mode = "unavailable"
        self.toast.show("Volume control unavailable")
        self.status.append("Volume: no compatible ALSA mixer")

    # â”€â”€ HUD chrome â”€â”€

    def _draw_chrome(self):
        """Minimal chrome â€” just a subtle separator under the status bar."""
        self.cv.create_line(28, 38, WIDTH - 28, 38, fill="#2C2C2E")

    # â”€â”€ Key handlers â”€â”€

    def _typing(self):
        """Check if a LIVE text input widget has focus.
        After _clear_vf destroys settings/browser widgets, tkinter's
        focus tracker can still point to the dead widget. A destroyed
        tk.Entry still passes isinstance() checks, so we must verify
        the widget is alive first via winfo_exists()."""
        if self._touch_keyboard.visible and self._active_input_alive():
            return True
        f = self.focus_get()
        if f is None:
            return False
        # Verify widget hasn't been destroyed
        try:
            if not f.winfo_exists():
                return False
        except Exception:
            return False
        # Direct CTk widget check
        if isinstance(f, (ctk.CTkEntry, ctk.CTkTextbox)):
            return True
        # Inner tk widget check (what focus_get actually returns)
        if isinstance(f, (tk.Entry, tk.Text)):
            return True
        # Fallback: check widget class name string
        try:
            cls = f.winfo_class()
            if cls in ("Entry", "Text", "TEntry", "TText", "Spinbox"):
                return True
        except Exception:
            pass
        return False

    def _k_left(self, e):
        if self._touch_keyboard.visible:
            self._touchpad_swipe("left")
        elif self.current_view == "home" and not self._typing():
            self._nav(-1)

    def _k_right(self, e):
        if self._touch_keyboard.visible:
            self._touchpad_swipe("right")
        elif self.current_view == "home" and not self._typing():
            self._nav(+1)

    def _k_up(self, e):
        if self._touch_keyboard.visible:
            self._touchpad_swipe("up")

    def _k_down(self, e):
        if self._touch_keyboard.visible:
            self._touchpad_swipe("down")

    def _k_enter(self, e):
        if self._touch_keyboard.visible:
            self._touchpad_tap()
        elif self.current_view == "home" and not self._typing():
            self._open_sel()

    def _k_esc(self, e):
        if self._touch_keyboard.visible:
            self._hide_touch_keyboard()
        elif self.current_view != "home":
            self._go_home()

    def _k_wheel(self, e):
        if self.current_view == "home":
            self._nav(1 if e.delta > 0 else -1)

    def _k_v(self, e):
        # Push-to-talk â€” works from any screen unless typing
        if not self._typing():
            self.voice.activate()

    def _k_s(self, e):
        if not self._typing():
            self._screenshot()

    def _k_t(self, e):
        if not self._typing():
            self._toggle_timer()

    def _k_keypress(self, e):
        if not self._touch_keyboard.visible or not self._active_input_alive():
            return

        token = None
        if e.keysym in ("BackSpace",):
            token = TouchKeyboard.TOK_BACK
        elif e.keysym in ("Return", "KP_Enter"):
            token = TouchKeyboard.TOK_ENTER
        elif e.keysym == "space":
            token = TouchKeyboard.TOK_SPACE
        elif e.char and len(e.char) == 1 and e.char.isalpha():
            token = e.char.lower()

        if token is not None:
            self.after(0, lambda t=token: self._touch_keyboard.flash(t, persist_ms=180))

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Timer / Stopwatch
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _toggle_timer(self):
        if self._timer_running:
            self._timer_running = False
            elapsed = time.perf_counter() - self._timer_start
            m, s = divmod(int(elapsed), 60)
            self.cv.itemconfigure(self._timer_id, text=f"â± {m:02d}:{s:02d} STOPPED")
            self.toast.show(f"Timer stopped: {m:02d}:{s:02d}")
        else:
            self._timer_running = True
            self._timer_start = time.perf_counter()
            self.toast.show("Timer started â€” press [T] to stop")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Screenshot
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _screenshot(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(PHOTOS_DIR, f"screenshot_{ts}.png")
        try:
            x, y = self.winfo_rootx(), self.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + WIDTH, y + HEIGHT))
            img.save(path)
            self.toast.show("ðŸ“¸ Screenshot saved")
            self.status.append(f"Screenshot: {os.path.basename(path)}")
        except Exception as e:
            self.status.append(f"Screenshot failed: {e}")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Voice routing
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _voice_route(self, cmd):
        if self._active_input_alive():
            for prefix in ("type ", "dictate ", "enter text "):
                if cmd.startswith(prefix):
                    self._insert_into_active_input(cmd[len(prefix):])
                    return
            if cmd in {"backspace", "delete"}:
                self._backspace_active_input()
                return
            if cmd in {"clear text", "clear field"}:
                self._clear_active_input()
                return
            if cmd in {"submit", "send", "search now", "go now"}:
                self._submit_active_input()
                return

        # Strip common prefixes so "open camera" â†’ "camera"
        for prefix in ("open ", "go to ", "launch ", "start ", "show "):
            if cmd.startswith(prefix):
                cmd = cmd[len(prefix):]
                break

        # Direct website open â€” "open up X website" / "go to X site"
        for suffix in (" website", " site"):
            if cmd.endswith(suffix):
                target = cmd[:-len(suffix)].strip()
                for prefix in ("open up ", "open ", "go to ", "launch ", "start ", "show "):
                    if target.startswith(prefix):
                        target = target[len(prefix):].strip()
                        break
                if target:
                    self._browser_open_website(target)
                    return

        # Handle compound "browser and search X" / "browser search X"
        for sep in ("and search for ", "and search ", "search for ", "search "):
            if "browser" in cmd and sep in cmd:
                query = cmd.split(sep, 1)[1].strip()
                if query:
                    self._browser_search(query)
                    return

        words = set(cmd.split())

        # Explicit search â€” "search X" / "look up X" / "google X"
        for prefix in ("search for ", "look up ", "google ", "search "):
            if cmd.startswith(prefix):
                q = cmd[len(prefix):].strip()
                if q:
                    self._browser_search(q)
                return

        # Keyword routes â€” app commands
        routes = [
            ({"take", "photo"},    lambda: self._voice_capture()),
            ({"take", "picture"},  lambda: self._voice_capture()),
            ({"capture"},          lambda: self._voice_capture()),
            ({"screenshot"},       self._screenshot),
            ({"timer"},            self._toggle_timer),
            ({"stopwatch"},        self._toggle_timer),
            ({"close"},            self._go_home),
            ({"exit"},             self._go_home),
            ({"camera"},           self.show_camera),
            ({"photos"},           self.show_photos),
            ({"photo"},            self.show_photos),
            ({"gallery"},          self.show_photos),
            ({"browser"},          self.show_browser),
            ({"web"},              self.show_browser),
            ({"internet"},         self.show_browser),
            ({"assistant"},        self.show_assistant),
            ({"aries"},            self.show_assistant),
            ({"music"},            self.show_music),
            ({"settings"},         self.show_settings),
            ({"translate"},        self.show_translate),
            ({"translation"},      self.show_translate),
            ({"translator"},       self.show_translate),
            ({"bluetooth"},        self.show_bluetooth),
            ({"location"},         self.show_track),
            ({"track"},            self.show_track),
            ({"gps"},              self.show_track),
            ({"home"},             self._go_home),
            ({"back"},             self._go_home),
            ({"power", "off"},     self.show_power),
            ({"shut", "down"},     self.show_power),
            ({"shutdown"},         self.show_power),
            ({"power"},            self.show_power),
            ({"video"},            lambda: self._generic("Video")),
            ({"avatar"},           lambda: self._generic("Avatar")),
            ({"plugin"},           lambda: self._generic("Plugin")),
            ({"theme"},            lambda: self._generic("Theme")),
            ({"livestream"},       lambda: self._generic("LiveStream")),
            ({"stream"},           lambda: self._generic("LiveStream")),
        ]

        for kws, action in routes:
            if kws.issubset(words):
                action()
                return

        # No match â€” tell user
        self.toast.show(f"Unknown command: \"{cmd}\"")
        self.status.append(f"No match: \"{cmd}\"")

    def _voice_capture(self):
        if self.current_view == "camera":
            self._capture_photo()
        else:
            self.show_camera()
            self.after(700, self._capture_photo)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Navigation
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _nav(self, d):
        if self.current_view == "home":
            self.cflow.move(d)

    def _is_focusable_widget(self, widget):
        if widget is None:
            return False
        try:
            if not widget.winfo_exists() or not widget.winfo_viewable():
                return False
        except Exception:
            return False

        if not isinstance(widget, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkTextbox, tk.Button, tk.Entry, tk.Text)):
            return False

        try:
            state = widget.cget("state")
            if state == "disabled":
                return False
        except Exception:
            pass
        return True

    def _iter_focusable_widgets(self, parent):
        widgets = []
        try:
            children = parent.winfo_children()
        except Exception:
            return widgets

        for child in children:
            if self._is_focusable_widget(child):
                widgets.append(child)
            widgets.extend(self._iter_focusable_widgets(child))
        return widgets

    def _ensure_widget_visible(self, widget):
        if widget is None:
            return
        try:
            if isinstance(widget, (ctk.CTkTextbox, tk.Text)):
                widget.see("insert")
        except Exception:
            pass

    def _clear_visual_focus(self):
        widget = self._nav_focus_widget
        if widget is None:
            return
        if not self._widget_alive(widget):
            self._nav_focus_widget = None
            self._nav_focus_style = {}
            return

        styles = self._nav_focus_style
        try:
            if isinstance(widget, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkTextbox)):
                if "border_width" in styles:
                    widget.configure(border_width=styles["border_width"])
                if "border_color" in styles:
                    widget.configure(border_color=styles["border_color"])
            else:
                widget.configure(
                    highlightthickness=styles.get("highlightthickness", 0),
                    highlightbackground=styles.get("highlightbackground", BG),
                    highlightcolor=styles.get("highlightcolor", C),
                )
        except Exception:
            pass

        self._nav_focus_widget = None
        self._nav_focus_style = {}

    def _set_visual_focus(self, widget):
        if widget is None or not self._widget_alive(widget):
            return

        if widget is self._nav_focus_widget:
            self._ensure_widget_visible(widget)
            return

        self._clear_visual_focus()
        try:
            if isinstance(widget, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkTextbox)):
                style = {}
                for key in ("border_width", "border_color"):
                    try:
                        style[key] = widget.cget(key)
                    except Exception:
                        pass
                self._nav_focus_style = style
                widget.configure(border_width=max(2, int(style.get("border_width", 1) or 1)), border_color=C)
            else:
                self._nav_focus_style = {
                    "highlightthickness": widget.cget("highlightthickness"),
                    "highlightbackground": widget.cget("highlightbackground"),
                    "highlightcolor": widget.cget("highlightcolor"),
                }
                widget.configure(highlightthickness=2, highlightbackground=C, highlightcolor=C)
        except Exception:
            self._nav_focus_style = {}

        self._nav_focus_widget = widget
        self._ensure_widget_visible(widget)

    def _widget_alive(self, widget):
        try:
            return widget is not None and widget.winfo_exists()
        except Exception:
            return False

    def _focus_widget(self, widget):
        if not self._widget_alive(widget):
            return False
        try:
            widget.focus_set()
        except Exception:
            return False

        self._set_visual_focus(widget)
        if self._is_text_input_widget(widget):
            self._activate_text_input(widget)
        return True

    def _move_focus(self, delta):
        if self.current_view == "home":
            self._nav(delta)
            return

        container = self._vf if self._vf_visible and self._vf is not None else self
        focusable = self._iter_focusable_widgets(container)
        if not focusable:
            return

        current = self._resolve_text_input_widget(self.focus_get()) or self.focus_get() or self._active_input
        try:
            idx = focusable.index(current)
        except Exception:
            idx = -1

        next_idx = (idx + delta) % len(focusable)
        self._focus_widget(focusable[next_idx])

    def _global_move(self, direction):
        if self._touch_keyboard.visible:
            move_map = {
                "left": (-1, 0),
                "right": (1, 0),
                "up": (0, -1),
                "down": (0, 1),
                "prev": (-1, 0),
                "next": (1, 0),
            }
            dx, dy = move_map.get(direction, (0, 0))
            if dx or dy:
                self._touch_keyboard.move(dx=dx, dy=dy)
            return

        if self.current_view == "home":
            if direction in {"left", "prev"}:
                self._nav(-1)
            elif direction in {"right", "next"}:
                self._nav(+1)
            return

        if direction in {"left", "up", "prev"}:
            self._move_focus(-1)
        elif direction in {"right", "down", "next"}:
            self._move_focus(+1)

    def _invoke_focused_widget(self):
        widget = self.focus_get()
        if widget is None:
            return False

        resolved = self._resolve_text_input_widget(widget)
        if resolved is not None:
            self._activate_text_input(resolved)
            return True

        if isinstance(widget, ctk.CTkButton):
            try:
                widget.invoke()
                return True
            except Exception:
                return False

        try:
            widget.invoke()
            return True
        except Exception:
            pass

        try:
            widget.event_generate("<Return>")
            return True
        except Exception:
            return False

    def _global_select(self):
        if self._touch_keyboard.visible:
            self._touch_keyboard.activate()
            return
        if self.current_view == "home":
            self._open_sel()
            return
        if self._active_input_alive():
            self._activate_text_input(self._active_input)
            return
        self._invoke_focused_widget()

    def _global_back(self):
        if self._touch_keyboard.visible:
            self._hide_touch_keyboard()
            return
        if self.current_view != "home":
            self._go_home()

    def _open_sel(self):
        app = self.cflow.current()
        if not app:
            return
        self.status.append(f"Opened {app['label']}")
        h = self._handlers.get(app["id"])
        if h:
            h()
        else:
            self._generic(app["label"])

    def _go_home(self):
        self.current_view = "home"
        self._stop_camera()
        self._close_browser()
        self._clear_visual_focus()
        self._hide_touch_keyboard()
        if self._vf_visible and self._vf:
            self._vf.place_forget()
            self._vf_visible = False
        self.cv.focus_set()
        self.status.append("Home")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  View frame â€” lazy raw tk.Frame
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _ensure_vf(self):
        if self._vf is None:
            self._vf = tk.Frame(self, bg=BG, highlightthickness=0)

    def _clear_vf(self):
        self._stop_camera()
        self._active_input = None
        self._active_submit = None
        self._clear_visual_focus()
        self._hide_touch_keyboard()
        if self._vf:
            for w in self._vf.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

    def _view(self, vid, title, body="", placeholder=False):
        self.current_view = vid
        self._ensure_vf()
        self._clear_vf()

        if not self._vf_visible:
            self._vf.place(x=0, y=0, width=WIDTH, height=HEIGHT)
            self._vf.tkraise()
            self._vf_visible = True

        # Top bar â€” Apple style
        top = ctk.CTkFrame(self._vf, fg_color="transparent", height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text=f"â€¹  {title}", font=(FONT, 18),
                      text_color=C).pack(side="left", padx=24, pady=12)
        ctk.CTkLabel(top, text="Esc back",
                      font=(FONT, 10),
                      text_color="#48484A").pack(side="right", padx=24, pady=12)

        # Subtle separator
        ctk.CTkFrame(self._vf, fg_color="#2C2C2E", height=1).pack(fill="x", padx=0)

        if body:
            ctk.CTkLabel(self._vf, text=body, font=(FONT, 11),
                          text_color=TXTD, wraplength=WIDTH - 100,
                          justify="center").pack(pady=(8, 2))

        panel = ctk.CTkFrame(self._vf, corner_radius=14, fg_color=PNL,
                              border_color=PNLE, border_width=0)
        panel.pack(pady=(6, 10), padx=24, fill="both", expand=True)

        if placeholder:
            ctk.CTkLabel(panel, text=f"{title} â€” coming soon",
                          font=(FONT, 14), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
        return panel

    def _touchpad_swipe(self, direction):
        self._last_touchpad_swipe_at = time.perf_counter()
        # Home screen navigation is handled by continuous move tracking below.
        # Don't double-fire a swipe event on top of it.
        if self.current_view == "home" and not self._touch_keyboard.visible:
            return
        if self._touch_keyboard.visible and direction in {"up", "down"}:
            return
        self._global_move(direction)

    def _touchpad_move(self, x, y):
        # ── Home screen: Apple TV relative-delta model ────────────────────────
        # Each ~7mm of deliberate horizontal travel steps the carousel by 1 app.
        # Finger position on the pad does NOT map to app index (that caused
        # jumping). Instead we track delta from the anchor of the current touch.
        # Anchor resets when a new touch starts (detected by time gap).
        if self.current_view == "home" and not self._touch_keyboard.visible:
            self._home_touch_track(x, y)
            return

        if not self._touch_keyboard.visible:
            self._keyboard_drag_last_x = None
            self._keyboard_drag_accum = 0.0
            return

        # ── Keyboard deliberate horizontal drag ───────────────────────────
        try:
            if self._keyboard_drag_last_x is None:
                self._keyboard_drag_last_x = x
                self._keyboard_drag_accum = 0.0
                self._keyboard_drag_pending = 0.0
                self._keyboard_drag_started = False
                return

            dx = x - self._keyboard_drag_last_x
            self._keyboard_drag_last_x = x

            if abs(dx) <= 8:
                return

            if (dx > 0 and self._keyboard_drag_accum < 0) or (dx < 0 and self._keyboard_drag_accum > 0):
                self._keyboard_drag_accum = 0.0
                self._keyboard_drag_pending = 0.0
                self._keyboard_drag_started = False

            if not self._keyboard_drag_started:
                self._keyboard_drag_pending += dx
                if abs(self._keyboard_drag_pending) < self._KEYBOARD_DRAG_START_PX:
                    return
                self._keyboard_drag_started = True
                self._keyboard_drag_accum = self._keyboard_drag_pending
                self._keyboard_drag_pending = 0.0
            else:
                self._keyboard_drag_accum += dx

            moved = False
            while self._keyboard_drag_accum >= self._KEYBOARD_STEP_PX:
                self._keyboard_drag_accum -= self._KEYBOARD_STEP_PX
                self._touch_keyboard.sel_col = min(len(self._touch_keyboard.TOKENS) - 1, self._touch_keyboard.sel_col + 1)
                moved = True
            while self._keyboard_drag_accum <= -self._KEYBOARD_STEP_PX:
                self._keyboard_drag_accum += self._KEYBOARD_STEP_PX
                self._touch_keyboard.sel_col = max(0, self._touch_keyboard.sel_col - 1)
                moved = True

            if moved:
                self._last_touchpad_swipe_at = time.perf_counter()
                self._touch_keyboard.refresh()
        except Exception:
            pass

    # Deliberate keyboard/home drag tuning for Cirque touchpad
    _KEYBOARD_DRAG_START_PX = 150.0
    _KEYBOARD_STEP_PX = 185.0

    # Home-screen drag tuned for deliberate Apple-TV-like movement.
    _HOME_STEP_PX = 185.0
    _HOME_DRAG_START_PX = 95.0
    _HOME_ANCHOR_RESET_SEC = 0.14
    _HOME_NOISE_FLOOR = 14
    _HOME_HOLD_FREEZE_SEC = 0.26
    _HOME_IDLE_FREEZE_SEC = 0.10

    def _home_touch_track(self, x, y):
        """Track deliberate horizontal drag like an Apple TV remote strip.

        A touch must first exceed a startup travel threshold before it counts as
        a swipe. Once dragging starts, movement steps more slowly so selection is
        easier to control and taps are less likely to be misread as swipes.
        """
        now = time.perf_counter()

        if (self._home_drag_last_x is None
                or (now - self._home_drag_last_move_at) > self._HOME_ANCHOR_RESET_SEC):
            self._home_drag_last_x = x
            self._home_move_residual = 0.0
            self._home_drag_accum = 0.0
            self._home_drag_pending = 0.0
            self._home_drag_started = False
            self._home_drag_last_move_at = now
            self._home_touch_started_at = now
            self._home_last_deliberate_motion_at = now
            self._home_hold_lock = False
            return

        dx = x - self._home_drag_last_x
        self._home_drag_last_x = x
        self._home_drag_last_move_at = now

        if self._home_hold_lock:
            return

        if abs(dx) <= self._HOME_NOISE_FLOOR:
            if ((now - self._home_touch_started_at) >= self._HOME_HOLD_FREEZE_SEC
                    and (now - self._home_last_deliberate_motion_at) >= self._HOME_IDLE_FREEZE_SEC):
                self._home_hold_lock = True
            return

        self._last_touchpad_motion_at = now
        self._home_last_deliberate_motion_at = now

        if (dx > 0 and self._home_move_residual < 0) or (dx < 0 and self._home_move_residual > 0):
            self._home_move_residual = 0.0
            self._home_drag_pending = 0.0
            self._home_drag_started = False

        if not self._home_drag_started:
            self._home_drag_pending += dx
            if abs(self._home_drag_pending) < self._HOME_DRAG_START_PX:
                return
            self._home_drag_started = True
            self._home_move_residual = self._home_drag_pending
            self._home_drag_pending = 0.0
        else:
            self._home_move_residual += dx

        moved = False
        while self._home_move_residual >= self._HOME_STEP_PX:
            self.cflow.move(+1)
            self._home_move_residual -= self._HOME_STEP_PX
            moved = True
        while self._home_move_residual <= -self._HOME_STEP_PX:
            self.cflow.move(-1)
            self._home_move_residual += self._HOME_STEP_PX
            moved = True

        if moved:
            self._last_touchpad_swipe_at = now

    def _touchpad_tap(self):
        now = time.perf_counter()
        self._home_drag_anchor_x = None
        self._home_drag_last_x = None
        self._home_move_residual = 0.0
        self._home_drag_pending = 0.0
        self._home_drag_started = False
        self._keyboard_drag_last_x = None
        self._keyboard_drag_accum = 0.0
        self._keyboard_drag_pending = 0.0
        self._keyboard_drag_started = False

        self._home_hold_lock = False
        self._home_touch_started_at = 0.0
        self._home_last_deliberate_motion_at = 0.0

        if (now - getattr(self, "_last_touchpad_swipe_at", 0.0)) < 0.12:
            return
        if (now - getattr(self, "_last_touchpad_motion_at", 0.0)) < 0.06:
            return
        if self._typing() and not self._touch_keyboard.visible:
            self._show_touch_keyboard()
            return
        self._global_select()

    def _touchpad_long_press(self):
        self._global_back()

    def _register_text_input(self, widget, submit_callback=None):
        self._input_submit_map[str(widget)] = submit_callback
        widget.bind("<FocusIn>", lambda e, w=widget, cb=submit_callback: self._activate_text_input(w, cb), add="+")
        widget.bind("<Button-1>", lambda e, w=widget, cb=submit_callback: self.after(0, lambda: self._activate_text_input(w, cb)), add="+")

    def _activate_text_input(self, widget, submit_callback=None):
        widget = self._resolve_text_input_widget(widget)
        if widget is None:
            self.log.debug("Text input activation ignored: no compatible widget")
            return
        self.log.debug("Activating text input: %s (%s)", widget, widget.winfo_class())
        self._active_input = widget
        if submit_callback is None:
            submit_callback = self._input_submit_map.get(str(widget))
        self._active_submit = submit_callback
        try:
            widget.focus_set()
        except Exception:
            pass
        self._set_visual_focus(widget)
        self._show_touch_keyboard()

    def _is_text_input_widget(self, widget):
        if widget is None:
            return False
        try:
            if not widget.winfo_exists():
                return False
        except Exception:
            return False

        if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox, tk.Entry, tk.Text)):
            return True

        try:
            return widget.winfo_class() in ("Entry", "Text", "TEntry", "TText", "Spinbox")
        except Exception:
            return False

    def _resolve_text_input_widget(self, widget):
        current = widget
        depth = 0
        while current is not None and depth < 8:
            if self._is_text_input_widget(current):
                return current
            try:
                current = current.master
            except Exception:
                current = None
            depth += 1
        return None

    def _global_text_input_focus(self, e):
        raw_widget = getattr(e, "widget", None)
        self.log.debug("FocusIn received from widget: %s", raw_widget)
        widget = self._resolve_text_input_widget(raw_widget)
        if widget is not None:
            self.log.debug("FocusIn detected text widget: %s (%s)", widget, widget.winfo_class())
            self.after(0, lambda w=widget: self._activate_text_input(w))

    def _global_text_input_click(self, e):
        raw_widget = getattr(e, "widget", None)
        self.log.debug("Button-1 received from widget: %s", raw_widget)
        widget = self._resolve_text_input_widget(raw_widget)
        if widget is not None:
            self.log.debug("Button-1 detected text widget: %s (%s)", widget, widget.winfo_class())
            self.after(0, lambda w=widget: self._activate_text_input(w))

    def _active_input_alive(self):
        if self._active_input is None:
            return False
        try:
            return bool(self._active_input.winfo_exists())
        except Exception:
            return False

    def _show_touch_keyboard(self):
        self._keyboard_drag_last_x = None
        self._keyboard_drag_accum = 0.0
        if self.current_view == "home" or not self._active_input_alive():
            self.log.debug("Touch keyboard show skipped (view=%s active=%s)",
                           self.current_view, self._active_input_alive())
            return
        self.log.debug("Showing touch keyboard for input: %s", self._active_input)
        self._touch_keyboard.show()

    def _hide_touch_keyboard(self):
        self._touch_keyboard.hide()
        self._keyboard_drag_last_x = None
        self._keyboard_drag_accum = 0.0
        if self._active_input_alive():
            try:
                self._active_input.focus_set()
            except Exception:
                self._focus_root()
        else:
            self._focus_root()

    def _handle_touch_key(self, token):
        if token == TouchKeyboard.TOK_SPACE:
            self._insert_into_active_input(" ")
            return
        if token == TouchKeyboard.TOK_BACK:
            self._backspace_active_input()
            return
        if token == TouchKeyboard.TOK_ENTER:
            self._submit_active_input()
            return

        self._insert_into_active_input(token)

    def _insert_into_active_input(self, text):
        if not self._active_input_alive():
            self.toast.show("Select a text field first")
            return
        w = self._active_input
        try:
            if isinstance(w, (ctk.CTkEntry, tk.Entry)):
                w.insert(w.index("insert"), text)
            else:
                w.insert("insert", text)
            if self._touch_keyboard.visible:
                self._touch_keyboard.refresh()
            w.focus_set()
        except Exception as exc:
            self.toast.show(f"Typing failed: {exc}")

    def _backspace_active_input(self):
        if not self._active_input_alive():
            return
        w = self._active_input
        try:
            if isinstance(w, (ctk.CTkEntry, tk.Entry)):
                idx = int(w.index("insert"))
                if idx > 0:
                    w.delete(idx - 1, idx)
            else:
                idx = w.index("insert")
                if idx != "1.0":
                    w.delete(f"{idx} -1c", idx)
            if self._touch_keyboard.visible:
                self._touch_keyboard.refresh()
            w.focus_set()
        except Exception:
            pass

    def _clear_active_input(self):
        if not self._active_input_alive():
            return
        w = self._active_input
        try:
            if isinstance(w, (ctk.CTkEntry, tk.Entry)):
                w.delete(0, "end")
            else:
                w.delete("1.0", "end")
            if self._touch_keyboard.visible:
                self._touch_keyboard.refresh()
            w.focus_set()
        except Exception:
            pass

    def _submit_active_input(self):
        if self._active_submit:
            self._active_submit()
            self._hide_touch_keyboard()
            return
        if self._active_input_alive():
            try:
                self._active_input.event_generate("<Return>")
            except Exception:
                pass
        self._hide_touch_keyboard()

    def _active_input_text(self):
        if not self._active_input_alive():
            return ""
        try:
            if isinstance(self._active_input, (ctk.CTkEntry, tk.Entry)):
                return self._active_input.get()
            return self._active_input.get("1.0", "end").strip()
        except Exception:
            return ""

    def _focus_root(self):
        try:
            self.focus_set()
            self.cv.focus_set()
        except Exception:
            pass

    def _generic(self, label):
        self._view(f"app:{label}", label,
                   f"{label} is not fully implemented yet.", placeholder=True)

    
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Gemini Assistant
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_assistant(self):
        p = self._view("assistant", "Assistant",
                       "Cloud AI assistant powered by Gemini.")

        hist = ctk.CTkTextbox(
            p, font=(FONT_MONO, 13), wrap="word",
            fg_color="#0A1214", text_color=TXT
        )
        hist.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 4))
        hist.insert("end", "Aries > Hi! How can I help?\n")
        status = "Gemini READY" if getattr(self, "gemini_client", None) else "Gemini NOT CONFIGURED (using local fallback)"
        hist.insert("end", f"  ({status})\n\n")
        hist.configure(state="disabled")

        bar = ctk.CTkFrame(p, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=8, pady=8)

        ent = ctk.CTkEntry(
            bar, placeholder_text="Type a message ...",
            font=(FONT_MONO, 13), fg_color=PNL,
            text_color=TXT, border_color=CD
        )
        ent.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def send(_=None):
            msg = ent.get().strip()
            if not msg:
                return
            ent.delete(0, "end")
            hist.configure(state="normal")
            hist.insert("end", f"You > {msg}\n")
            hist.configure(state="disabled")
            hist.see("end")
            self.update_idletasks()
            _start_safe_thread(self._assistant_reply, "AssistantReply", self.log, msg, hist)

        self._btn(bar, "Send", send, True, 72)
        ent.bind("<Return>", send)
        self._register_text_input(ent, send)
        ent.focus_set()

    def _assistant_reply(self, msg, hist):
        reply = self._gemini_reply(msg)

        def _update():
            try:
                if not hist.winfo_exists():
                    return
                hist.configure(state="normal")
                hist.insert("end", f"Aries > {reply}\n\n")
                hist.configure(state="disabled")
                hist.see("end")
            except Exception:
                pass

        self.after(0, _update)

    def _gemini_reply(self, msg):
        if not getattr(self, "gemini_client", None):
            return self._local_reply(msg)

        try:
            resp = self.gemini_client.models.generate_content(
                model=getattr(self, "gemini_model", "gemini-2.0-flash"),
                contents=(
                    "You are Aries, an AI inside AR smart glasses. "
                    "Be concise and helpful.\n\n"
                    f"User: {msg}"
                ),
            )

            text = getattr(resp, "text", None)
            if text:
                return text.strip()

            self.log.warning("Gemini returned no text; using local fallback")
            return self._local_reply(msg)
        except Exception as e:
            self.log.exception("Gemini request failed")
            return f"{self._local_reply(msg)}\n[Gemini error: {e}]"

    def _local_reply(self, msg):
        import math
        import re

        try:
            expr = re.sub(r"[^0-9+\*/.()\s-]", "", msg)
            if expr and any(c.isdigit() for c in expr):
                try:
                    return f"{eval(expr, {'__builtins__': {}}, {'math': math})}"
                except Exception:
                    self.log.debug("Local calculator fallback failed for %r", expr)

            low = msg.lower()
            if "hello" in low or "hi" in low:
                return "Hello! I'm Aries, running on-device."
            if "time" in low:
                return f"It's {_time_str()}."
            return "Processed locally (MVP)."
        except Exception:
            self.log.exception("Local reply crashed")
            return "Assistant fallback hit an internal error, but Aries is still running."


    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Camera
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_camera(self):
        p = self._view("camera", "Camera",
                        "Live preview Â· Capture saves to gallery")

        self._cam_label = ctk.CTkLabel(p, text="Initializing â€¦",
                                        font=(FONT, 13), text_color=TXTD)
        self._cam_label.pack(fill="both", expand=True)

        bb = ctk.CTkFrame(self._vf, fg_color="transparent")
        bb.pack(pady=(0, 8))
        self._btn(bb, "ðŸ“· Capture", self._capture_photo, True)
        self._btn(bb, "Restart", self._restart_cam)
        self._btn(bb, "Stop", self._stop_camera)

        self._start_camera()

    def _camera_candidate_indices(self):
        indices = []
        try:
            for name in sorted(os.listdir('/dev')):
                if not name.startswith('video'):
                    continue
                suffix = name[5:]
                if suffix.isdigit():
                    indices.append(int(suffix))
        except Exception:
            pass
        if not indices:
            indices = list(range(5))
        return sorted(dict.fromkeys(indices))

    def _open_camera_capture(self, idx):
        backends = []
        if hasattr(cv2, 'CAP_V4L2'):
            backends.append(cv2.CAP_V4L2)
        backends.append(None)
        for backend in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(idx) if backend is None else cv2.VideoCapture(idx, backend)
                if not cap or not cap.isOpened():
                    if cap:
                        cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ok, _frame = cap.read()
                if ok:
                    return cap
                cap.release()
            except Exception:
                if cap:
                    try:
                        cap.release()
                    except Exception:
                        pass
        return None

    def _start_camera(self):
        if cv2 is None:
            self._cam_msg("cv2 not installed")
            return

        if self._cam_running and self._cam_cap and self._cam_cap.isOpened():
            self.log.debug("Camera already running on index %s", self._cam_source_index)
            return

        self._stop_camera(clear_message=False)
        self._cam_last_frame = None
        self._cam_image = None
        self._cam_source_index = None

        last_error = None
        for idx in self._camera_candidate_indices():
            try:
                cap = self._open_camera_capture(idx)
                if cap is not None:
                    self._cam_cap = cap
                    self._cam_source_index = idx
                    self.log.info("Camera opened on index %d", idx)
                    break
            except Exception as exc:
                last_error = exc
                self.log.exception("Camera initialization failed on index %d", idx)

        if not self._cam_cap or not self._cam_cap.isOpened():
            self._cam_cap = None
            self._cam_running = False
            if last_error:
                self._cam_msg(f"Camera unavailable: {last_error}")
            else:
                nodes = ", ".join(f"/dev/video{i}" for i in self._camera_candidate_indices())
                self._cam_msg(f"No usable camera on {nodes}")
            return
        self._cam_running = True
        self._cam_tick()

    def _cam_tick(self):
        if not self._cam_running or not self._cam_cap:
            return
        try:
            ret, frame = self._cam_cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame).resize((800, 450))
                self._cam_last_frame = img.copy()
                self._cam_image = _make_ctk_image(img, (800, 450))
                if self._cam_label:
                    self._cam_label.configure(image=self._cam_image, text="")
            else:
                self.log.warning("Camera read failed on index %s", self._cam_source_index)
        except Exception:
            self.log.exception("Camera frame update failed")
        self._cam_after = self.after(33, self._cam_tick)

    def _capture_photo(self):
        if self._cam_last_frame is None:
            self.toast.show("No frame to capture")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(PHOTOS_DIR, f"aries_{ts}.png")
        try:
            self._cam_last_frame.save(path)
            self.toast.show("ðŸ“· Photo saved!")
            self.status.append(f"Saved {os.path.basename(path)}")
        except Exception as e:
            self.toast.show(f"Save failed: {e}")

    def _stop_camera(self, clear_message=True):
        self._cam_running = False
        if self._cam_after:
            try:
                self.after_cancel(self._cam_after)
            except Exception:
                pass
            self._cam_after = None
        if self._cam_cap:
            try:
                self._cam_cap.release()
            except Exception:
                pass
            self._cam_cap = None
        self._cam_source_index = None
        self._cam_image = None
        if clear_message:
            self._cam_msg("Camera stopped.")

    def _restart_cam(self):
        self._stop_camera()
        self._start_camera()

    def _cam_msg(self, msg):
        if self._cam_label:
            try:
                self._cam_label.configure(image=None, text=msg)
            except Exception:
                pass

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Photos
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_photos(self):
        p = self._view("photos", "Photos", "Camera captures & screenshots")

        files = sorted(
            [f for f in os.listdir(PHOTOS_DIR)
             if f.lower().endswith((".png", ".jpg", ".jpeg"))],
            reverse=True)

        if not files:
            ctk.CTkLabel(p, text="No photos yet.\nUse Camera or press [S].",
                          font=(FONT, 13), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
            return

        self._pv_label = ctk.CTkLabel(p, text="", fg_color="#1C1C1E",
                                       corner_radius=12, width=520, height=280)
        self._pv_label.pack(pady=(8, 4))
        self._pv_refs = []

        self._pv_name = ctk.CTkLabel(p, text="", font=(FONT, 10),
                                      text_color=TXTD)
        self._pv_name.pack(pady=(0, 2))

        scroll = ctk.CTkScrollableFrame(p, fg_color="transparent",
                                         scrollbar_button_color="#48484A", height=130)
        scroll.pack(fill="x", padx=8, pady=(0, 4))

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x")

        for i, fname in enumerate(files):
            if i > 0 and i % 6 == 0:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=3)
            fpath = os.path.join(PHOTOS_DIR, fname)
            try:
                thumb = Image.open(fpath).convert("RGBA").resize((130, 82), Image.LANCZOS)
                ctk_img = _make_ctk_image(thumb, (130, 82))
                self._pv_refs.append(ctk_img)
                ctk.CTkButton(row, image=ctk_img, text="", width=138, height=90,
                               corner_radius=8, fg_color=PNLE, hover_color="#3A3A3C",
                               command=lambda fp=fpath, fn=fname: self._pv_show(fp, fn)
                               ).pack(side="left", padx=3)
            except Exception:
                pass

        # Bottom bar
        bb = ctk.CTkFrame(self._vf, fg_color="transparent")
        bb.pack(pady=(0, 6))
        self._pv_current = None

        def delete():
            if self._pv_current and os.path.exists(self._pv_current):
                os.remove(self._pv_current)
                self.toast.show("Photo deleted")
                self.show_photos()

        ctk.CTkButton(bb, text="Delete", width=100, corner_radius=20,
                       fg_color=RED, hover_color="#FF453A",
                       text_color="white", font=(FONT, 12),
                       command=delete).pack(side="left", padx=4)

        ctk.CTkLabel(bb, text=f"{len(files)} photo(s)",
                      font=(FONT, 11), text_color=TXTD
                      ).pack(side="left", padx=12)

        if files:
            self._pv_show(os.path.join(PHOTOS_DIR, files[0]), files[0])

    def _pv_show(self, path, name=""):
        self._pv_current = path
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((520, 280), Image.LANCZOS)
            self._pv_tk = _make_ctk_image(img, img.size)
            self._pv_label.configure(image=self._pv_tk, text="")
            if name:
                self._pv_name.configure(text=name)
        except Exception as e:
            self._pv_label.configure(image=None, text=f"Error: {e}")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Browser
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  pywebview (subprocess) = full JS, Google/YouTube work
    #  tkinterweb fallback = no JS, DuckDuckGo HTML-lite
    #
    #  Voice: "search X" / "browser search X" â†’ opens with search
    #         "close browser" / "exit" / "go home" â†’ kills browser
    #  Rotary: long press â†’ kills browser + go home
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    _browser_proc = None

    def _browser_is_open(self):
        return self._browser_proc is not None and self._browser_proc.poll() is None

    def _close_browser(self):
        """Kill the pywebview subprocess if running."""
        was_open = self._browser_is_open()
        if was_open:
            try:
                self._browser_proc.terminate()
            except Exception:
                self.log.exception("Browser terminate failed")
            self._browser_proc = None
            self.status.append("Browser closed")
            self.toast.show("Browser closed")
        if self.current_view == "browser":
            self._hide_touch_keyboard()
            self._focus_root()

    def _browser_launch(self, raw_text):
        raw_text = (raw_text or "").strip()
        if self._b_url is not None:
            self._b_url.set(raw_text)
        self._open_external_browser(self._to_google_url(raw_text))

    def _browser_open_home(self):
        self._browser_launch("")

    def show_browser(self, search_query=None):
        p = self._view("browser", "Browser")

        nav = ctk.CTkFrame(p, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(14, 8))

        self._b_url = tk.StringVar(value=(search_query or "").strip())
        ent = ctk.CTkEntry(
            nav,
            textvariable=self._b_url,
            placeholder_text="Search Google or enter URL...",
            font=(FONT, 15),
            fg_color=PNL,
            text_color=TXT,
            border_color=C,
            height=42,
        )
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._browser_entry = ent

        def go(_=None):
            self._browser_launch(self._b_url.get())

        self._btn(nav, "Open", go, True, 72)
        self._btn(nav, "Home", self._browser_open_home, w=72)
        self._btn(nav, "Close", lambda: (self._close_browser(), self._go_home()), w=72)

        card = ctk.CTkFrame(p, corner_radius=14, fg_color="#151518")
        card.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        ctk.CTkFrame(card, fg_color="transparent").place(relx=.5, rely=.42, anchor="center")
        ctk.CTkLabel(
            card,
            text="",
            font=(FONT, 1),
            text_color="#151518",
            justify="center",
            wraplength=1,
        ).place(relx=.5, rely=.7, anchor="center")

        ent.bind("<Return>", go)
        self._register_text_input(ent, go)
        self._activate_text_input(ent, go)
        self.after(50, lambda: self._activate_text_input(ent, go))
        self.after(100, self._show_touch_keyboard)
        if search_query:
            self.after(100, go)

    def _open_external_browser(self, url):
        url = self._to_google_url(url)
        try:
            import webview as _wv_check
            has_pywebview = True
        except ImportError:
            has_pywebview = False

        if not has_pywebview:
            p = self._view("browser", "Browser")
            ctk.CTkLabel(p, text="No browser available.\n\n"
                          "pip install pywebview   (full JS)\n"
                          "pip install tkinterweb  (basic HTML)",
                          font=(FONT, 13), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
            self._focus_root()
            return

        if self._browser_is_open():
            self._close_browser()

        self.toast.show("Opening full browser...", 1500)
        self.status.append(f"Browser -> {url}")
        win_x = self.winfo_rootx()
        win_y = self.winfo_rooty()
        script = (
            "import webview, sys; "
            "webview.create_window('Aries Browser', sys.argv[1], "
            f"width={WIDTH}, height={HEIGHT}, x={win_x}, y={win_y}, "
            "frameless=True, easy_drag=False, resizable=False, confirm_close=False); "
            "webview.start()"
        )
        try:
            self._browser_proc = subprocess.Popen(
                [sys.executable, "-c", script, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            def _watch():
                if self._browser_proc:
                    self._browser_proc.wait()
                self.after(0, lambda: self.status.append("Browser closed"))
                self._browser_proc = None
            _start_safe_thread(_watch, "BrowserWatch", self.log)
            self.after(100, self._focus_root)
        except Exception as exc:
            self.toast.show(f"Browser failed: {exc}")

    @staticmethod
    def _to_google_url(text):
        text = text.strip()
        if not text:
            return "https://www.google.com"
        if text.startswith(("http://", "https://")):
            return text
        if "." in text and " " not in text:
            return "https://" + text
        return "https://www.google.com/search?q=" + quote_plus(text)

    def _show_embedded_browser(self, start_url, external_url=None):
        """Fallback embedded browser - no JavaScript."""
        p = self._view("browser", "Browser")

        nav = ctk.CTkFrame(p, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(8, 4))

        self._b_url = tk.StringVar(value=start_url)
        ent = ctk.CTkEntry(nav, textvariable=self._b_url,
                            placeholder_text="Search or enter URL...",
                            font=(FONT, 13), fg_color=PNL,
                            text_color=TXT, border_color="#3A3A3C")
        ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._browser_entry = ent

        web = ctk.CTkFrame(p, corner_radius=8, fg_color="#1C1C1E")
        web.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self._html = HtmlFrame(web, horizontal_scrollbar="auto")
        self._html.pack(fill="both", expand=True)

        def go(_=None):
            raw = self._b_url.get().strip()
            if not raw:
                return
            url = self._to_url_ddg(raw)
            self._b_url.set(raw)
            self._html.load_website(url)
            self._focus_root()

        self._btn(nav, "Go", go, True, 56)
        self._btn(nav, "Back", lambda: self._safe(self._html.go_back), w=56)
        self._btn(nav, "Next", lambda: self._safe(self._html.go_forward), w=56)
        self._btn(nav, "Reload", lambda: self._safe(self._html.reload), w=60)
        if external_url:
            self._btn(nav, "Full", lambda u=external_url: self._open_external_browser(u), w=56)
        self._btn(nav, "Close", lambda: (self._close_browser(), self._go_home()), w=60)

        self._html.load_website(start_url)
        ent.bind("<Return>", go)
        self._register_text_input(ent, go)
        self._activate_text_input(ent, go)
        self._focus_root()

    @staticmethod
    def _to_url_ddg(text):
        """URL/search for embedded browser (DuckDuckGo HTML-lite)."""
        text = text.strip()
        if text.startswith(("http://", "https://")):
            return text
        if "." in text and " " not in text:
            return "https://" + text
        return "https://html.duckduckgo.com/html/?q=" + text.replace(" ", "+")

    def _browser_search(self, query):
        if not query:
            return
        self.show_browser(search_query=query)

    def _browser_open_website(self, target):
        if not target:
            return
        url = self._to_direct_website_url(target)
        self.status.append(f"Website â†’ {target}")
        self.toast.show(f"Opening {target}â€¦", 1500)
        self._open_external_browser(url)

    @staticmethod
    def _to_direct_website_url(text):
        text = text.strip().lower()
        if not text:
            return "https://www.google.com"
        if text.startswith(("http://", "https://")):
            return text

        text = text.replace("'s", "").replace(" official", "").strip()
        if text in SITE_ALIASES:
            return SITE_ALIASES[text]

        words = [w for w in text.split() if w not in {"the", "a", "an", "website", "site", "homepage", "home"}]
        if not words:
            return "https://www.google.com"

        joined = "".join(ch for ch in "".join(words) if ch.isalnum())
        dashed = "-".join("".join(ch for ch in w if ch.isalnum()) for w in words if any(ch.isalnum() for ch in w))

        candidates = []
        if "university" in words or "college" in words or "school" in words:
            if joined:
                candidates.append(f"https://www.{joined}.edu")
            if dashed:
                candidates.append(f"https://www.{dashed}.edu")
        if joined:
            candidates.append(f"https://www.{joined}.com")
        if dashed:
            candidates.append(f"https://www.{dashed}.com")

        if candidates:
            return candidates[0]
        return "https://html.duckduckgo.com/html/?q=" + quote_plus(text)

    @staticmethod
    def _to_google_lucky_url(text):
        text = text.strip()
        if not text:
            return "https://www.google.com"
        if text.startswith(("http://", "https://")):
            return text
        return "https://www.google.com/search?btnI=I&q=" + quote_plus(text)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Translate
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_translate(self):
        p = self._view("translate", "Translate",
                        "Text translation via deep-translator")

        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text="Target:", font=(FONT, 12),
                      text_color=TXT).pack(side="left", padx=(0, 6))

        langs = ["Japanese", "Spanish", "French", "Korean", "German", "Chinese"]
        lv = ctk.StringVar(value="Japanese")
        ctk.CTkOptionMenu(top, values=langs, variable=lv, fg_color=PNL,
                           button_color=CD, button_hover_color=C,
                           text_color=TXT).pack(side="left")

        src = ctk.CTkTextbox(p, height=120, font=(FONT, 13),
                              fg_color="#1C1C1E", text_color=TXT)
        src.pack(fill="x", padx=10, pady=(8, 4))
        src.insert("end", "Hello, how are you?")
        src.focus_set()

        tgt = ctk.CTkTextbox(p, height=120, font=(FONT, 13),
                              fg_color="#1C1C1E", text_color=C)
        tgt.pack(fill="x", padx=10, pady=(4, 8))
        tgt.insert("end", "Translation appears here â€¦")
        tgt.configure(state="disabled")

        def go():
            text = src.get("1.0", "end").strip()
            res = self._translate(text, lv.get())
            tgt.configure(state="normal")
            tgt.delete("1.0", "end")
            tgt.insert("end", res)
            tgt.configure(state="disabled")

        self._register_text_input(src, go)
        self._btn_c(p, "Translate", go, True)

    def _translate(self, text, lang):
        if not text:
            return ""
        if GoogleTranslator:
            codes = {"Japanese": "ja", "Spanish": "es", "French": "fr",
                     "Korean": "ko", "German": "de", "Chinese": "zh-cn"}
            try:
                return GoogleTranslator(source="auto",
                                        target=codes.get(lang, "en")).translate(text)
            except Exception as e:
                return f"Error: {e}"
        fb = {("Hello", "Japanese"): "ã“ã‚“ã«ã¡ã¯",
              ("Hello", "Spanish"): "Hola", ("Hello", "French"): "Bonjour"}
        hit = fb.get((text.split(",")[0].strip(), lang))
        return f"{hit}  (demo)" if hit else f"{text}\n\n[deep-translator not installed]"

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  Settings
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def show_settings(self):
        p = self._view("settings", "Settings", "Device + app configuration")

        sw = dict(font=(FONT, 13), text_color=TXT, progress_color=GRN)

        dm = ctk.CTkSwitch(p, text="Dark mode", **sw,
                            command=lambda: self._set_dark(dm))
        dm.select(); dm.pack(anchor="w", padx=20, pady=(12, 6))

        bt = ctk.CTkSwitch(p, text="Bluetooth", **sw,
                            command=lambda: setattr(self, 'bluetooth_enabled', bool(bt.get())))
        bt.pack(anchor="w", padx=20, pady=6)

        nf = ctk.CTkSwitch(p, text="Notifications", **sw,
                            command=lambda: setattr(self, 'notifications_enabled', bool(nf.get())))
        nf.select(); nf.pack(anchor="w", padx=20, pady=6)

        sl = dict(progress_color=C, button_color=TXT, button_hover_color=TXTD, fg_color=PNLE)

        ctk.CTkLabel(p, text="AR transparency", font=(FONT, 12),
                      text_color=TXTD).pack(anchor="w", padx=20, pady=(12, 2))
        asl = ctk.CTkSlider(p, from_=.3, to=1, number_of_steps=14, **sl,
                              command=lambda v: self._safe(
                                  lambda: self.attributes("-alpha", float(v))))
        asl.set(0.92); asl.pack(fill="x", padx=20)

        # Microphone section
        ctk.CTkFrame(p, fg_color="#2C2C2E", height=1).pack(fill="x", padx=20, pady=(12, 6))

        mic_state = "Ready" if self.voice.available else "Not installed"
        ctk.CTkLabel(p, text=f"Microphone â€” {mic_state}",
                      font=(FONT, 14, "bold"),
                      text_color=TXT).pack(anchor="w", padx=20)

        mic_box = ctk.CTkTextbox(p, height=80, font=(FONT, 11),
                                  fg_color="#1C1C1E", text_color=TXT)
        mic_box.pack(fill="x", padx=20, pady=(4, 4))

        mics = VoiceController.list_microphones()
        if not mics:
            mic_box.insert("end", "No audio devices found.\n")
        else:
            mic_box.insert("end", f"{len(mics)} device(s):\n")
            for i, name in mics:
                tag = " < ACTIVE" if i == self.voice.mic_index else ""
                if self.voice.mic_index is None and i == 0:
                    tag = " < DEFAULT"
                mic_box.insert("end", f"  [{i}] {name}{tag}\n")
        mic_box.configure(state="disabled")

        if self.voice.available:
            row = ctk.CTkFrame(p, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(2, 2))

            ctk.CTkLabel(row, text="Device #:", font=(FONT, 12),
                          text_color=TXT).pack(side="left", padx=(0, 6))

            cur = self.voice.mic_index
            iv = ctk.StringVar(value=str(cur if cur is not None else 0))
            ctk.CTkEntry(row, textvariable=iv, width=50, font=(FONT, 13),
                          fg_color=PNL, text_color=TXT, border_color="#3A3A3C"
                          ).pack(side="left", padx=(0, 6))

            def set_mic():
                try:
                    idx = int(iv.get())
                    self.voice.mic_index = idx
                    _save_config({"mic_index": idx})
                    self.toast.show(f"Mic â†’ device [{idx}] (saved)")
                except ValueError:
                    self.toast.show("Invalid number")

            self._btn(row, "Set", set_mic, True, 50)

            test_lbl = ctk.CTkLabel(p, text="", font=(FONT, 11), text_color=AMB)
            test_lbl.pack(anchor="w", padx=20)

            def test_mic():
                test_lbl.configure(text="Recording 3s â€¦")
                self.update_idletasks()
                def _t():
                    msg = ""
                    try:
                        idx = self.voice.mic_index
                        m = sr.Microphone(device_index=idx) \
                            if idx is not None else sr.Microphone()
                        rec = sr.Recognizer()
                        with m as s:
                            audio = rec.record(s, duration=3)
                        raw = audio.get_raw_data()
                        shorts = struct.unpack(f"<{len(raw)//2}h", raw)
                        rms = (sum(x*x for x in shorts) / len(shorts)) ** 0.5
                        th = VoiceController.ENERGY_THRESHOLD
                        msg = (f"âœ“ RMS: {rms:.0f} (threshold: {th}) â€” "
                               f"{'GOOD' if rms > th else 'âš  TOO QUIET'}")
                    except Exception as e:
                        msg = f"âœ— {e}"
                    def _update_lbl():
                        try:
                            if test_lbl.winfo_exists():
                                test_lbl.configure(text=msg)
                        except Exception:
                            pass
                    self.after(0, _update_lbl)
                _start_safe_thread(_t, "MicTest", self.log)

            self._btn_c(p, "ðŸŽ™ Test Mic (3s)", test_mic, True)

        # Rotary section
        if self.rotary.available:
            ctk.CTkFrame(p, fg_color="#2C2C2E", height=1).pack(fill="x", padx=20, pady=(8, 6))
            ctk.CTkLabel(p, text="Rotary Encoder â€” Connected",
                          font=(FONT, 12), text_color=GRN
                          ).pack(anchor="w", padx=20)

        self.status.append("Opened Settings")

    def _set_dark(self, sw):
        self.dark_mode = bool(sw.get())
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  System Info
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
                return
            except Exception:
                continue
        self.toast.show("No terminal app found")
        self.status.append("Dev Mode unavailable: no terminal emulator")

    def show_power(self):
        p = self._view("power", "Power")
        w = ctk.CTkFrame(p, fg_color="transparent")
        w.pack(expand=True)

        ctk.CTkButton(w, text="Power Off", fg_color=RED,
                       hover_color="#FF453A", height=44, corner_radius=12,
                       font=(FONT, 15), text_color="white",
                       command=self._system_poweroff
                       ).pack(pady=8, padx=48, fill="x")

        ctk.CTkButton(w, text="Restart", fg_color=PNLE,
                       hover_color="#3A3A3C", height=44, corner_radius=12,
                       font=(FONT, 15), text_color=TXT,
                       command=lambda: (self._on_close(),
                                        os.execl(sys.executable, sys.executable, *sys.argv))
                       ).pack(pady=8, padx=48, fill="x")

        ctk.CTkButton(w, text="Dev Mode", fg_color=PNLE,
                       hover_color="#3A3A3C", height=40, corner_radius=12,
                       font=(FONT, 13), text_color=TXT,
                       command=self._open_dev_mode).pack(pady=8, padx=48, fill="x")

        ctk.CTkButton(w, text="System Info", fg_color=PNLE,
                       hover_color="#3A3A3C", height=40, corner_radius=12,
                       font=(FONT, 13), text_color=TXT,
                       command=self.show_sysinfo).pack(pady=8, padx=48, fill="x")

        ctk.CTkButton(w, text="Cancel", fg_color="transparent",
                       hover_color=PNL, height=36, corner_radius=12,
                       font=(FONT, 13), text_color=TXTD,
                       command=self._go_home).pack(pady=16)

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
        kw = dict(text=text, command=cmd, corner_radius=20,
                  font=(FONT, 12, "bold") if primary else (FONT, 12),
                  fg_color=C if primary else PNLE,
                  hover_color=CD if primary else "#3A3A3C",
                  text_color="white")
        if w:
            kw["width"] = w
        ctk.CTkButton(parent, **kw).pack(side="left", padx=4)


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
            keyboard_token = self._touch_keyboard.LAYOUT[self._touch_keyboard.sel_row][self._touch_keyboard.sel_col]
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




