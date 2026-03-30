import os
import sys
import time
import threading
import struct
import enum
import logging
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageGrab
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
    import pyttsx3
except Exception:
    pyttsx3 = None
    
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


# Logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Platform

IS_PI = (
    platform.machine().startswith(("armv7l", "armv6l", "aarch64"))
    and "raspberrypi" in platform.platform().lower()
)

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

CONFIG_PATH = os.path.join(os.getcwd(), "aries_config.json")


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
    ("augreality.png",     "AugReality"),
    ("avatar.png",         "Avatar"),
    ("bluetooth.png",      "Bluetooth"),
    ("camera.png",         "Camera"),
    ("eyetrack.png",       "EyeTrack"),
    ("gesture.png",        "Gesture"),
    ("gps.png",            "Track"),
    ("livestream.png",     "LiveStream"),
    ("localassistant.png", "Gemini"),
    ("music.png",          "Music"),
    ("phone.png",          "Phone"),
    ("photo.png",          "Photo"),
    ("plugin.png",         "Plugin"),
    ("settings.png",       "Settings"),
    ("spatialaudio.png",   "SpatialAudio"),
    ("theme.png",          "Theme"),
    ("track.png",          "Track"),
    ("translate.png",      "Translate"),
    ("video.png",          "Video"),
    ("browser.png",        "Browser"),
    ("power.png",          "Power"),
]

BUILD_STR = "VA-OS1.1 · Pandora Build · Oct 2025"

# HUD palette

C    = "#00E5FF"
CD   = "#007A8C"
TXT  = "#E0F7FA"
TXTD = "#80CBC4"
BG   = "#000000"
PNL  = "#0D1B1E"
PNLE = "#1A3A40"
AMB  = "#FF6D00"
RED  = "#D50000"

SCALE_DROP = 0.14
ALPHA_DROP = 0.22


# ═══════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════

def _load(path):
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _circle(img, size):
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _glow(radius, alpha=140, color=(0, 229, 255)):
    w = h = radius * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for sc, a in [(0.55, alpha), (1.15, int(alpha * .7)),
                  (2.0, int(alpha * .4)), (3.0, int(alpha * .18))]:
        r = radius * sc
        cx, cy = w / 2, h / 2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, a))
    return img.filter(ImageFilter.GaussianBlur(int(radius * .3)))


def _batt():
    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            b = psutil.sensors_battery()
            if b:
                return f"{int(b.percent)}%"
        except Exception:
            pass
    return "–%"


def _cpu():
    if psutil:
        try:
            return f"{psutil.cpu_percent(interval=0):.0f}%"
        except Exception:
            pass
    return "–%"


def _ram():
    if psutil:
        try:
            return f"{psutil.virtual_memory().percent:.0f}%"
        except Exception:
            pass
    return "–%"


def _time_str():
    now = datetime.now()
    try:
        return now.strftime("%-I:%M %p")
    except ValueError:
        return now.strftime("%#I:%M %p")


# ═══════════════════════════════════════
#  StatusBar
# ═══════════════════════════════════════

class StatusBar:
    def __init__(self, canvas):
        self.cv = canvas
        self._lines = []
        self._tid = None
        self._last = 0.0
        for dx, dy in [(0, 14), (14, 0)]:
            canvas.create_line(16, 12, 16 + dx, 12 + dy, fill=CD)

    def append(self, msg):
        self._lines = (self._lines + [msg])[-3:]

    def tick(self):
        now = time.perf_counter()
        if now - self._last < 0.5:
            return
        self._last = now
        body = (f"{_time_str()}  ·  BAT {_batt()}  ·  CPU {_cpu()}"
                f"  ·  RAM {_ram()}\n{BUILD_STR}")
        if self._lines:
            body += "\n" + "\n".join(self._lines)
        if self._tid is None:
            self._tid = self.cv.create_text(
                32, 30, anchor="nw", fill=TXTD,
                font=("Consolas", 11), text=body)
        else:
            self.cv.itemconfigure(self._tid, text=body)


# ═══════════════════════════════════════
#  Notification Toast
# ═══════════════════════════════════════

class Toast:
    def __init__(self, canvas):
        self.cv = canvas
        self._bg = canvas.create_rectangle(0, 0, 0, 0, fill=PNL, outline=CD, width=1,
                                            state="hidden")
        self._txt = canvas.create_text(0, 0, text="", fill=TXT, anchor="n",
                                        font=("Consolas", 12), state="hidden")
        self._after = None

    def show(self, msg, duration=3000):
        w = min(len(msg) * 9 + 40, WIDTH - 100)
        x = WIDTH // 2
        self.cv.coords(self._bg, x - w // 2, 90, x + w // 2, 122)
        self.cv.coords(self._txt, x, 96)
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


# ═══════════════════════════════════════
#  VoiceController — demo-ready state machine
# ═══════════════════════════════════════
#
#  States:  IDLE → LISTENING → PROCESSING → IDLE
#
#  - No recording unless explicitly activated (push-to-talk via activate())
#  - Single worker thread per session, guarded by state lock
#  - Automatic stop after command recognized
#  - Debounce: ignores rapid re-activation within cooldown window
#  - Duplicate command filter within dedup window
#  - Clean shutdown via shutdown() — no stuck threads
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

        # Callbacks (all called from worker thread — caller must dispatch to UI)
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
        self.log.info("State: %s → %s", old.value, new_state.value)
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

        # Debounce — ignore rapid re-activation
        now = time.perf_counter()
        if now - self._last_activate < self.COOLDOWN_SEC:
            self.log.debug("Activation debounced (%.1fs since last)",
                           now - self._last_activate)
            return False

        # Only activate from IDLE
        with self._lock:
            if self._state != VoiceState.IDLE:
                self.log.debug("Activation ignored — state is %s", self._state.value)
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
        """Clean shutdown — stops any active session, prevents new ones."""
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
        """Background thread — records audio, runs STT, returns result."""
        text = ""
        try:
            # Check for cancellation before opening mic
            if self._stop_event.is_set():
                return

            # Open microphone
            if self._mic_index is not None:
                mic = sr.Microphone(device_index=self._mic_index)
            else:
                mic = sr.Microphone()

            with mic as source:
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
            self.log.info("Sending audio to Google STT …")
            text = self._recognizer.recognize_google(audio)
            self.log.info("Recognized: '%s'", text)

        except sr.WaitTimeoutError:
            self.log.info("Timeout — no speech detected")
            if self._on_error:
                self._on_error("No speech — try again")

        except sr.UnknownValueError:
            self.log.info("Could not understand audio")
            if self._on_error:
                self._on_error("Couldn't understand — try again")

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
            # Always return to IDLE
            with self._lock:
                self._set_state(VoiceState.IDLE)

            # Deliver result if we got one (with dedup check)
            if text and not self._stop_event.is_set():
                now = time.perf_counter()
                normalized = text.lower().strip()

                # Dedup — ignore identical command within window
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


# ═══════════════════════════════════════
#  RotaryController — GPIO click wheel input
# ═══════════════════════════════════════
#
#  Hardware: Rotary encoder with push button (CLK, DT, SW)
#  - Clockwise rotation → on_rotate(+1)
#  - Counter-clockwise → on_rotate(-1)
#  - Short press (< 1s) → on_click()
#  - Long press (≥ 1s) → on_long_press()
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

        self._clk = clk_pin or self.DEFAULT_CLK
        self._dt  = dt_pin  or self.DEFAULT_DT
        self._sw  = sw_pin  or self.DEFAULT_SW

        self._last_rotate_time  = 0.0
        self._button_down_time  = 0.0
        self._button_handled    = False
        self._active = False

        if not GPIO:
            self.log.info("RPi.GPIO not available — rotary disabled (desktop mode)")
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
        """Called on CLK edge — reads DT to determine direction."""
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
        """Called on button edge — tracks press/release for long press."""
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


# ═══════════════════════════════════════
#  CoverFlow
# ═══════════════════════════════════════

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

        g = _glow(int(BASE_ICON * 1.2), 140)
        self._glow_tk = ImageTk.PhotoImage(g)
        self._glow_id = canvas.create_image(0, 0, image=self._glow_tk, anchor="nw")
        self._icons = [canvas.create_image(0, 0, image=None, anchor="nw")
                       for _ in range(5)]
        self._label = canvas.create_text(
            0, 0, text="", fill=C, font=("Consolas", 16, "bold"))

    def _tkimg(self, app, sz, alpha):
        sq = max(14, round(sz / SIZE_STEP_PX) * SIZE_STEP_PX)
        a8 = int(max(0, min(255, round(alpha * 255 / ALPHA_STEP_8) * ALPHA_STEP_8)))
        key = (sq, a8)
        if key in app["cache"]:
            return app["cache"][key]
        circ = _circle(app["img"], sq)
        if a8 < 255:
            am = circ.split()[-1].point(lambda p, _a=a8: int(p * _a / 255))
            circ.putalpha(am)
        tk = ImageTk.PhotoImage(circ)
        app["cache"][key] = tk
        return tk

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
            tk = self._tkimg(app, sz, alpha)
            cx, cy = x0 + i * SPACING, my
            self.cv.itemconfigure(self._icons[slot], image=tk)
            self.cv.coords(self._icons[slot],
                           int(cx - tk.width() / 2), int(cy - tk.height() / 2))
            self._refs[slot] = tk
            if i == 2:
                self.cv.coords(self._glow_id,
                               int(cx - self._glow_tk.width() / 2),
                               int(cy - self._glow_tk.height() / 2 + BASE_ICON * .03))
            positions.append((cx, cy, tk.width(), app["label"]))
        for cx, cy, w, label in positions:
            if abs(cx - mx) < 2:
                self.cv.itemconfigure(self._label, text=label, fill=C)
                self.cv.coords(self._label, cx, cy + w / 2 + 28)
                break


# ═══════════════════════════════════════
#  Main App
# ═══════════════════════════════════════

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
        self.cv = ctk.CTkCanvas(self, width=WIDTH, height=HEIGHT,
                                highlightthickness=0, bg=BG)
        self.cv.pack(fill="both", expand=True)
        self._draw_chrome()
        self.status = StatusBar(self.cv)
        self.toast = Toast(self.cv)
        self.cflow = CoverFlow(self.cv, APPS)

        self._mic_id = self.cv.create_text(
            WIDTH - 30, HEIGHT - 30, text="🎙", anchor="se",
            fill=TXTD, font=("Consolas", 18))
        self.cv.create_text(
            WIDTH // 2, HEIGHT - 22, anchor="s", fill=CD,
            font=("Consolas", 10),
            text='[V] Voice  ·  [S] Screenshot  ·  [T] Timer  ·  [Enter] Open  ·  [Esc] Back')

        # Overlay frame — raw tk.Frame to avoid ghost rectangle
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

        self.dark_mode = True
        self.bluetooth_enabled = False
        self.notifications_enabled = True

        # Timer
        self._timer_running = False
        self._timer_start = 0
        self._timer_id = self.cv.create_text(
            WIDTH - 30, 30, text="", anchor="ne", fill=C,
            font=("Consolas", 14, "bold"))

        # ── Voice controller ──
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

    
        # ── Gemini Assistant (google-genai) ──
        self.gemini_client = None

        if genai:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self.gemini_client = genai.Client(api_key=api_key)
                self.log.info("Gemini client initialized")
            else:
                self.log.warning("No GEMINI_API_KEY found")
        else:
            self.log.warning("google-genai SDK not installed")

        # ── Text-to-speech ──
        self.tts_engine = None
        self.tts_enabled = True

        if pyttsx3:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty("rate", 185)
                self.tts_engine.setProperty("volume", 1.0)
                self.log.info("TTS engine initialized")
            except Exception as e:
                self.log.warning("TTS init failed: %s", e)
                self.tts_engine = None
        else:
            self.log.warning("pyttsx3 not installed")

        # Browser refs
        self._html = None
        self._b_url = None

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

        # ── Rotary encoder (GPIO) ──
        self.rotary = RotaryController(
            on_rotate=self._rotary_rotate,
            on_click=self._rotary_click,
            on_long_press=self._rotary_long,
        )

        # Keys — V, S, T work globally
        self.bind("<Left>",   self._k_left)
        self.bind("<Right>",  self._k_right)
        self.bind("<Return>", self._k_enter)
        self.bind("<Escape>", self._k_esc)
        self.bind("<v>",      self._k_v)
        self.bind("<V>",      self._k_v)
        self.bind("<s>",      self._k_s)
        self.bind("<S>",      self._k_s)
        self.bind("<t>",      self._k_t)
        self.bind("<T>",      self._k_t)
        self.bind_all("<MouseWheel>", self._k_wheel)
        self.bind_all("<Button-4>", lambda e: self._nav(+1))
        self.bind_all("<Button-5>", lambda e: self._nav(-1))

        # Clean exit
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._last_time = time.perf_counter()
        self._tick()

    def _on_close(self):
        """Clean shutdown — release all resources."""
        self.log.info("Shutting down …")
        self.voice.shutdown()
        self.rotary.shutdown()
        self._stop_camera()
        self.destroy()

    # ═══════════════════════════════════════
    #  Voice callbacks (called from worker thread — must dispatch to UI)
    # ═══════════════════════════════════════

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
            self.cv.itemconfigure(self._mic_id, fill=AMB)
            self.toast.show("🎙 Speak now …")
        elif state == VoiceState.PROCESSING:
            self.cv.itemconfigure(self._mic_id, fill=C)
            self.toast.show("Processing …", 1500)
        elif state == VoiceState.IDLE:
            self.cv.itemconfigure(self._mic_id, fill=TXTD)

    # ═══════════════════════════════════════
    #  Rotary callbacks (called from GPIO thread)
    # ═══════════════════════════════════════

    def _rotary_rotate(self, direction):
        """GPIO thread → UI thread: rotate coverflow."""
        self.after(0, lambda: self._nav(direction))

    def _rotary_click(self):
        """GPIO thread → UI thread: select/open."""
        self.after(0, self._open_sel)

    def _rotary_long(self):
        """GPIO thread → UI thread: go home."""
        self.after(0, self._go_home)

    # ── HUD chrome ──

    def _draw_chrome(self):
        c, p, b = CD, 8, 40
        for x1, y1, x2, y2, x3, y3 in [
            (p, p, p+b, p, p, p+b),
            (WIDTH-p, p, WIDTH-p-b, p, WIDTH-p, p+b),
            (p, HEIGHT-p, p+b, HEIGHT-p, p, HEIGHT-p-b),
            (WIDTH-p, HEIGHT-p, WIDTH-p-b, HEIGHT-p, WIDTH-p, HEIGHT-p-b)]:
            self.cv.create_line(x1, y1, x2, y2, fill=c)
            self.cv.create_line(x1, y1, x3, y3, fill=c)
        self.cv.create_line(32, 82, 400, 82, fill=PNLE)

    # ── Key handlers ──

    def _typing(self):
        """Check if a LIVE text input widget has focus.
        After _clear_vf destroys settings/browser widgets, tkinter's
        focus tracker can still point to the dead widget. A destroyed
        tk.Entry still passes isinstance() checks, so we must verify
        the widget is alive first via winfo_exists()."""
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
        if self.current_view == "home" and not self._typing():
            self._nav(-1)

    def _k_right(self, e):
        if self.current_view == "home" and not self._typing():
            self._nav(+1)

    def _k_enter(self, e):
        if self.current_view == "home" and not self._typing():
            self._open_sel()

    def _k_esc(self, e):
        if self.current_view != "home":
            self._go_home()

    def _k_wheel(self, e):
        if self.current_view == "home":
            self._nav(1 if e.delta > 0 else -1)

    def _k_v(self, e):
        # Push-to-talk — works from any screen unless typing
        if not self._typing():
            self.voice.activate()

    def _k_s(self, e):
        if not self._typing():
            self._screenshot()

    def _k_t(self, e):
        if not self._typing():
            self._toggle_timer()

    # ═══════════════════════════════════════
    #  Timer / Stopwatch
    # ═══════════════════════════════════════

    def _toggle_timer(self):
        if self._timer_running:
            self._timer_running = False
            elapsed = time.perf_counter() - self._timer_start
            m, s = divmod(int(elapsed), 60)
            self.cv.itemconfigure(self._timer_id, text=f"⏱ {m:02d}:{s:02d} STOPPED")
            self.toast.show(f"Timer stopped: {m:02d}:{s:02d}")
        else:
            self._timer_running = True
            self._timer_start = time.perf_counter()
            self.toast.show("Timer started — press [T] to stop")

    # ═══════════════════════════════════════
    #  Screenshot
    # ═══════════════════════════════════════

    def _screenshot(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(PHOTOS_DIR, f"screenshot_{ts}.png")
        try:
            x, y = self.winfo_rootx(), self.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + WIDTH, y + HEIGHT))
            img.save(path)
            self.toast.show("📸 Screenshot saved")
            self.status.append(f"Screenshot: {os.path.basename(path)}")
        except Exception as e:
            self.status.append(f"Screenshot failed: {e}")

    # ═══════════════════════════════════════
    #  Voice routing
    # ═══════════════════════════════════════

    def _voice_route(self, cmd):
        # Strip common prefixes so "open camera" → "camera"
        for prefix in ("open ", "go to ", "launch ", "start ", "show "):
            if cmd.startswith(prefix):
                cmd = cmd[len(prefix):]
                break

        words = set(cmd.split())

        # Explicit search — ONLY when user says "search ..."
        for prefix in ("search for ", "look up ", "google ", "search "):
            if cmd.startswith(prefix):
                q = cmd[len(prefix):].strip()
                if q:
                    self._browser_search(q)
                return

        # Keyword routes — app commands
        routes = [
            ({"take", "photo"},    lambda: self._voice_capture()),
            ({"take", "picture"},  lambda: self._voice_capture()),
            ({"capture"},          lambda: self._voice_capture()),
            ({"screenshot"},       self._screenshot),
            ({"timer"},            self._toggle_timer),
            ({"stopwatch"},        self._toggle_timer),
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

        # No match — tell user instead of auto-searching
        self.toast.show(f"Unknown command: \"{cmd}\"")
        self.status.append(f"No match: \"{cmd}\"")

    def _voice_capture(self):
        if self.current_view == "camera":
            self._capture_photo()
        else:
            self.show_camera()
            self.after(700, self._capture_photo)

    # ═══════════════════════════════════════
    #  Navigation
    # ═══════════════════════════════════════

    def _nav(self, d):
        if self.current_view == "home":
            self.cflow.move(d)

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
        if self._vf_visible and self._vf:
            self._vf.place_forget()
            self._vf_visible = False
        # Reset focus to canvas — prevents dead widget focus after leaving apps
        self.cv.focus_set()
        self.status.append("Home")

    # ═══════════════════════════════════════
    #  View frame — lazy raw tk.Frame
    # ═══════════════════════════════════════

    def _ensure_vf(self):
        if self._vf is None:
            self._vf = tk.Frame(self, bg=BG, highlightthickness=0)

    def _clear_vf(self):
        self._stop_camera()
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

        # Top bar
        top = ctk.CTkFrame(self._vf, fg_color="transparent", height=50)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text=f"◂  {title}", font=("Consolas", 20, "bold"),
                      text_color=C).pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(top, text="[ESC] back  ·  [V] voice  ·  [S] screenshot",
                      font=("Consolas", 10),
                      text_color=TXTD).pack(side="right", padx=20, pady=10)

        ctk.CTkFrame(self._vf, fg_color=CD, height=1).pack(fill="x", padx=20)

        if body:
            ctk.CTkLabel(self._vf, text=body, font=("Consolas", 12),
                          text_color=TXTD, wraplength=WIDTH - 100,
                          justify="center").pack(pady=(6, 2))

        panel = ctk.CTkFrame(self._vf, corner_radius=10, fg_color=PNL,
                              border_color=PNLE, border_width=1)
        panel.pack(pady=(4, 6), padx=28, fill="both", expand=True)

        if placeholder:
            ctk.CTkLabel(panel, text=f"[{title} — not yet implemented]",
                          font=("Consolas", 13), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
        return panel

    def _generic(self, label):
        self._view(f"app:{label}", label,
                   f"{label} is not fully implemented yet.", placeholder=True)

    
    # ═══════════════════════════════════════
    #  Gemini Assistant
    # ═══════════════════════════════════════

    def show_assistant(self):
        p = self._view("assistant", "Gemini",
                       "AI assistant interface")

        # Background glow / header panel
               # HUD header
        header = ctk.CTkFrame(
            p,
            fg_color="#061018",
            corner_radius=18,
            border_color="#00F5FF",
            border_width=1
        )
        header.pack(fill="x", padx=12, pady=(10, 10))

        top_strip = ctk.CTkFrame(header, fg_color="transparent")
        top_strip.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            top_strip,
            text="◉ ARIES // GEMINI CORE",
            font=("Consolas", 22, "bold"),
            text_color=C
        ).pack(side="left")

        online = bool(getattr(self, "gemini_client", None))
        status_text = "ONLINE" if online else "LOCAL MODE"
        status_color = "#00F5FF" if online else "#FF9B3D"

        self._assistant_status_chip = ctk.CTkLabel(
            top_strip,
            text=status_text,
            font=("Consolas", 11, "bold"),
            text_color="#021014",
            fg_color=status_color,
            corner_radius=12,
            padx=12,
            pady=5
        )
        self._assistant_status_chip.pack(side="right")

        ctk.CTkLabel(
            header,
            text="Gemini 2.5 flash assistant • Aries glasses HUD • live reasoning interface",
            font=("Consolas", 11),
            text_color=TXTD
        ).pack(anchor="w", padx=14, pady=(0, 4))

        ctk.CTkLabel(
            header,
            text="VOICE [V]  •  TYPE  •  CLOUD RESPONSE  •  TTS PLAYBACK",
            font=("Consolas", 10, "bold"),
            text_color="#5BC9D7"
        ).pack(anchor="w", padx=14, pady=(0, 12))

            # Live system status row
        status_row = ctk.CTkFrame(
            p,
            fg_color="#07131A",
            corner_radius=14,
            border_color="#123844",
            border_width=1
        )
        status_row.pack(fill="x", padx=12, pady=(0, 10))

        self._mic_status_lbl = ctk.CTkLabel(
            status_row,
            text="MIC: STANDBY",
            font=("Consolas", 11, "bold"),
            text_color="#7EE7F7"
        )
        self._mic_status_lbl.pack(side="left", padx=14, pady=10)

        self._thinking_status_lbl = ctk.CTkLabel(
            status_row,
            text="CORE: IDLE",
            font=("Consolas", 11, "bold"),
            text_color="#7EE7F7"
        )
        self._thinking_status_lbl.pack(side="right", padx=14, pady=10)


        # Chat display frame
        chat_shell = ctk.CTkFrame(
            p,
            fg_color="#040B10",
            corner_radius=18,
            border_color="#103844",
            border_width=1
        )
        chat_shell.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        chat_top = ctk.CTkFrame(chat_shell, fg_color="transparent")
        chat_top.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            chat_top,
            text="LIVE SESSION",
            font=("Consolas", 12, "bold"),
            text_color=C
        ).pack(side="left")

        ctk.CTkLabel(
            chat_top,
            text="AR HUD FEED",
            font=("Consolas", 10),
            text_color=TXTD
        ).pack(side="right")

        hist = ctk.CTkTextbox(
            chat_shell,
            font=("Consolas", 13),
            wrap="word",
            fg_color="#071018",
            text_color=TXT,
            corner_radius=12,
            border_width=0
        )
        hist.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        hist.insert("end", "Aries ▸ Gemini link established.\n")
        if getattr(self, "gemini_client", None):
            hist.insert("end", "System ▸ Cloud reasoning online.\n")
        else:
            hist.insert("end", "System ▸ Local fallback active.\n")
        hist.insert("end", "System ▸ Awaiting user input.\n\n")
        hist.configure(state="disabled")

        # Bottom control area
        controls = ctk.CTkFrame(
            p,
            fg_color="#061018",
            corner_radius=18,
            border_color="#103844",
            border_width=1
        )
        controls.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            controls,
            text="COMMAND INPUT",
            font=("Consolas", 10, "bold"),
            text_color=C
        ).pack(anchor="w", padx=12, pady=(10, 4))

        input_row = ctk.CTkFrame(controls, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=(0, 8))

        ent = ctk.CTkEntry(
            input_row,
            placeholder_text="Ask Gemini something...",
            font=("Consolas", 13),
            fg_color="#0A161D",
            text_color=TXT,
            border_color=C,
            corner_radius=14,
            height=42
        )
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        thinking_lbl = ctk.CTkLabel(
            controls,
            text="",
            font=("Consolas", 11),
            text_color="#7EE7F7"
        )
        thinking_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        btn_row = ctk.CTkFrame(controls, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 12))

        def set_thinking(text=""):
            try:
                if thinking_lbl.winfo_exists():
                    thinking_lbl.configure(text=text)
                if hasattr(self, "_thinking_status_lbl") and self._thinking_status_lbl.winfo_exists():
                    self._thinking_status_lbl.configure(
                        text=f"CORE: {text.upper()}" if text else "CORE: IDLE"
                    )
            except Exception:
                pass

        def send(_=None):
            msg = ent.get().strip()
            if not msg:
                return

            ent.delete(0, "end")
            hist.configure(state="normal")
            hist.insert("end", f"You ▸ {msg}\n")
            hist.configure(state="disabled")
            hist.see("end")
            set_thinking("Gemini is thinking...")

            self.update_idletasks()

            def _task():
                reply = self._gemini_reply(msg)

                def _update():
                    try:
                        if not hist.winfo_exists():
                            return
                        hist.configure(state="normal")
                        hist.insert("end", f"Aries ▸ {reply}\n\n")
                        hist.configure(state="disabled")
                        hist.see("end")
                        set_thinking("")
                    except Exception:
                        pass

                self.after(0, _update)

                if hasattr(self, "_speak_text"):
                    self._speak_text(reply)

            threading.Thread(target=_task, daemon=True).start()

        def clear_chat():
            hist.configure(state="normal")
            hist.delete("1.0", "end")
            hist.insert("end", "Aries ▸ Conversation cleared.\n\n")
            hist.configure(state="disabled")
            set_thinking("")

        def talk_now():
            self.toast.show("Push-to-talk active")
            self.voice.activate()

        btn_row = ctk.CTkFrame(controls, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self._btn(btn_row, "Send", send, True, 80)
        self._btn(btn_row, "Talk", talk_now, False, 80)
        self._btn(btn_row, "Clear", clear_chat, False, 80)

        ent.bind("<Return>", send)
        ent.focus_set()

    def _gemini_reply(self, msg):
        print("DEBUG: entering _gemini_reply")

        if not getattr(self, "gemini_client", None):
            return self._local_reply(msg)

        try:
            print("DEBUG: sending request to Gemini")
            resp = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=(
                    "You are Aries, an AI inside AR smart glasses. "
                    "Be concise and helpful.\n\n"
                    f"User: {msg}"
                ),
            )
            print("DEBUG: Gemini response received")

            text = getattr(resp, "text", None)
            if text:
                return text.strip()

            return "[No response]"

        except Exception as e:
            return f"(Gemini error: {e})"

    # ═══════════════════════════════════════
    #  Camera
    # ═══════════════════════════════════════

    def show_camera(self):
        p = self._view("camera", "Camera",
                        "Live preview · Capture saves to gallery")

        self._cam_label = ctk.CTkLabel(p, text="Initializing …",
                                        font=("Consolas", 13), text_color=TXTD)
        self._cam_label.pack(fill="both", expand=True) 

        ctk.CTkLabel(p, text="● LIVE", font=("Consolas", 11, "bold"),
                      text_color=AMB).place(relx=.97, rely=.03, anchor="ne")

        count = len([f for f in os.listdir(PHOTOS_DIR)
                     if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        ctk.CTkLabel(p, text=f"📷 {count}", font=("Consolas", 10),
                      text_color=TXTD).place(relx=.03, rely=.03, anchor="nw")

        bb = ctk.CTkFrame(self._vf, fg_color="transparent")
        bb.pack(pady=(0, 8))
        self._btn(bb, "📷 Capture", self._capture_photo, True)
        self._btn(bb, "Restart", self._restart_cam)
        self._btn(bb, "Stop", self._stop_camera)

        self._start_camera()

    def _start_camera(self):
        if cv2 is None:
            self._cam_msg("cv2 not installed")
            return
        try:
            self._cam_cap = cv2.VideoCapture(0)
        except Exception:
            self._cam_cap = None
        if not self._cam_cap or not self._cam_cap.isOpened():
            self._cam_msg("No camera detected.")
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
                tk_img = ImageTk.PhotoImage(img)
                self._cam_tk = tk_img
                if self._cam_label:
                    self._cam_label.configure(image=tk_img, text="")
        except Exception:
            pass
        self._cam_after = self.after(33, self._cam_tick)

    def _capture_photo(self):
        if self._cam_last_frame is None:
            self.toast.show("No frame to capture")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(PHOTOS_DIR, f"aries_{ts}.png")
        try:
            self._cam_last_frame.save(path)
            self.toast.show("📷 Photo saved!")
            self.status.append(f"Saved {os.path.basename(path)}")
        except Exception as e:
            self.toast.show(f"Save failed: {e}")

    def _stop_camera(self):
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

    # ═══════════════════════════════════════
    #  Photos
    # ═══════════════════════════════════════

    def show_photos(self):
        p = self._view("photos", "Photos", "Camera captures & screenshots")

        files = sorted(
            [f for f in os.listdir(PHOTOS_DIR)
             if f.lower().endswith((".png", ".jpg", ".jpeg"))],
            reverse=True)

        if not files:
            ctk.CTkLabel(p, text="No photos yet.\nUse Camera or press [S].",
                          font=("Consolas", 13), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
            return

        self._pv_label = ctk.CTkLabel(p, text="", fg_color="#0A1214",
                                       corner_radius=6, width=520, height=280)
        self._pv_label.pack(pady=(8, 4))
        self._pv_refs = []

        self._pv_name = ctk.CTkLabel(p, text="", font=("Consolas", 10),
                                      text_color=TXTD)
        self._pv_name.pack(pady=(0, 2))

        scroll = ctk.CTkScrollableFrame(p, fg_color="transparent",
                                         scrollbar_button_color=CD, height=130)
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
                tk_img = ImageTk.PhotoImage(thumb)
                self._pv_refs.append(tk_img)
                ctk.CTkButton(row, image=tk_img, text="", width=138, height=90,
                               corner_radius=4, fg_color=PNLE, hover_color=CD,
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

        ctk.CTkButton(bb, text="🗑 Delete", width=100, corner_radius=6,
                       fg_color=RED, hover_color="#FF1744",
                       text_color="white", font=("Consolas", 12),
                       command=delete).pack(side="left", padx=4)

        ctk.CTkLabel(bb, text=f"{len(files)} photo(s)",
                      font=("Consolas", 11), text_color=TXTD
                      ).pack(side="left", padx=12)

        if files:
            self._pv_show(os.path.join(PHOTOS_DIR, files[0]), files[0])

    def _pv_show(self, path, name=""):
        self._pv_current = path
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((520, 280), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._pv_tk = tk_img
            self._pv_label.configure(image=tk_img, text="")
            if name:
                self._pv_name.configure(text=name)
        except Exception as e:
            self._pv_label.configure(image=None, text=f"Error: {e}")

    # ═══════════════════════════════════════
    #  Browser
    # ═══════════════════════════════════════
    #
    #  Uses DuckDuckGo HTML-lite for search — it renders cleanly
    #  in tkinterweb's basic HTML engine (Google/Bing need JavaScript).
    #  Typing a URL goes directly; typing words searches DDG.
    #

    SEARCH_ENGINES = {
        "DuckDuckGo": "https://html.duckduckgo.com/html/?q=",
        "Google":     "https://www.google.com/search?q=",
        "Wikipedia":  "https://en.wikipedia.org/w/index.php?search=",
    }

    def show_browser(self):
        p = self._view("browser", "Browser")

        if HtmlFrame is None:
            ctk.CTkLabel(p, text="tkinterweb not installed.\npip install tkinterweb",
                          font=("Consolas", 13), text_color=TXTD,
                          justify="center").place(relx=.5, rely=.5, anchor="center")
            return

        nav = ctk.CTkFrame(p, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(8, 4))

        # Search engine selector
        self._b_engine = ctk.StringVar(value="DuckDuckGo")
        ctk.CTkOptionMenu(nav, values=list(self.SEARCH_ENGINES.keys()),
                           variable=self._b_engine, width=120,
                           fg_color=PNL, button_color=CD,
                           button_hover_color=C, text_color=TXT,
                           font=("Consolas", 11)).pack(side="left", padx=(0, 6))

        self._b_url = ctk.StringVar(value="")
        ent = ctk.CTkEntry(nav, textvariable=self._b_url,
                            placeholder_text="Search anything or enter URL …",
                            font=("Consolas", 13), fg_color=PNL,
                            text_color=TXT, border_color=CD)
        ent.pack(side="left", fill="x", expand=True, padx=(0, 6))

        web = ctk.CTkFrame(p, corner_radius=6, fg_color="#0A1214")
        web.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self._html = HtmlFrame(web, horizontal_scrollbar="auto")
        self._html.pack(fill="both", expand=True)

        def go(_=None):
            raw = self._b_url.get().strip()
            if not raw:
                return
            url = self._to_url(raw)
            self._b_url.set(raw)
            self._html.load_website(url)
            self.status.append(f"Browser → {raw[:50]}")

        self._btn(nav, "Go", go, True, 56)
        self._btn(nav, "◀", lambda: self._safe(self._html.go_back), w=38)
        self._btn(nav, "▶", lambda: self._safe(self._html.go_forward), w=38)
        self._btn(nav, "⟳", lambda: self._safe(self._html.reload), w=38)
        self._btn(nav, "🎙", lambda: self.voice.activate(), w=38)

        # Start on DuckDuckGo homepage (lightweight, renders well)
        self._html.load_website("https://html.duckduckgo.com/")
        ent.bind("<Return>", go)
        ent.focus_set()

    def _to_url(self, text):
        """Smart URL/search detection."""
        text = text.strip()
        # Already a full URL
        if text.startswith(("http://", "https://")):
            return text
        # Looks like a domain name (has dot, no spaces)
        if "." in text and " " not in text:
            return "https://" + text
        # Everything else — search with selected engine
        engine = getattr(self, '_b_engine', None)
        name = engine.get() if engine else "DuckDuckGo"
        base = self.SEARCH_ENGINES.get(name, self.SEARCH_ENGINES["DuckDuckGo"])
        return base + text.replace(" ", "+")

    def _browser_search(self, query):
        if not query:
            return
        if HtmlFrame is None:
            self.toast.show("Browser not available (tkinterweb)")
            return
        self.show_browser()
        url = self._to_url(query)
        self._b_url.set(query)
        self.after(400, lambda: self._html.load_website(url))
        self.status.append(f"Searching: {query[:50]}")

    # ═══════════════════════════════════════
    #  Translate
    # ═══════════════════════════════════════

    def show_translate(self):
        p = self._view("translate", "Translate",
                        "Text translation via deep-translator")

        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text="Target:", font=("Consolas", 12),
                      text_color=TXT).pack(side="left", padx=(0, 6))

        langs = ["Japanese", "Spanish", "French", "Korean", "German", "Chinese"]
        lv = ctk.StringVar(value="Japanese")
        ctk.CTkOptionMenu(top, values=langs, variable=lv, fg_color=PNL,
                           button_color=CD, button_hover_color=C,
                           text_color=TXT).pack(side="left")

        src = ctk.CTkTextbox(p, height=120, font=("Consolas", 13),
                              fg_color="#0A1214", text_color=TXT)
        src.pack(fill="x", padx=10, pady=(8, 4))
        src.insert("end", "Hello, how are you?")
        src.focus_set()

        tgt = ctk.CTkTextbox(p, height=120, font=("Consolas", 13),
                              fg_color="#0A1214", text_color=C)
        tgt.pack(fill="x", padx=10, pady=(4, 8))
        tgt.insert("end", "Translation appears here …")
        tgt.configure(state="disabled")

        def go():
            text = src.get("1.0", "end").strip()
            res = self._translate(text, lv.get())
            tgt.configure(state="normal")
            tgt.delete("1.0", "end")
            tgt.insert("end", res)
            tgt.configure(state="disabled")

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
        fb = {("Hello", "Japanese"): "こんにちは",
              ("Hello", "Spanish"): "Hola", ("Hello", "French"): "Bonjour"}
        hit = fb.get((text.split(",")[0].strip(), lang))
        return f"{hit}  (demo)" if hit else f"{text}\n\n[deep-translator not installed]"

    # ═══════════════════════════════════════
    #  Settings
    # ═══════════════════════════════════════

    def show_settings(self):
        p = self._view("settings", "Settings", "Device + app configuration")

        sw = dict(font=("Consolas", 13), text_color=TXT, progress_color=C)

        dm = ctk.CTkSwitch(p, text="Dark mode", **sw,
                            command=lambda: self._set_dark(dm))
        dm.select(); dm.pack(anchor="w", padx=20, pady=(12, 6))

        bt = ctk.CTkSwitch(p, text="Bluetooth", **sw,
                            command=lambda: setattr(self, 'bluetooth_enabled', bool(bt.get())))
        bt.pack(anchor="w", padx=20, pady=6)

        nf = ctk.CTkSwitch(p, text="Notifications", **sw,
                            command=lambda: setattr(self, 'notifications_enabled', bool(nf.get())))
        nf.select(); nf.pack(anchor="w", padx=20, pady=6)

        sl = dict(progress_color=C, button_color=C, button_hover_color="#00FFD5")

        ctk.CTkLabel(p, text="AR transparency", font=("Consolas", 12),
                      text_color=TXTD).pack(anchor="w", padx=20, pady=(12, 2))
        asl = ctk.CTkSlider(p, from_=.3, to=1, number_of_steps=14, **sl,
                              command=lambda v: self._safe(
                                  lambda: self.attributes("-alpha", float(v))))
        asl.set(0.92); asl.pack(fill="x", padx=20)

        # Microphone section
        ctk.CTkFrame(p, fg_color=CD, height=1).pack(fill="x", padx=20, pady=(12, 6))

        mic_state = "✓ Ready" if self.voice.available else "✗ Not installed"
        ctk.CTkLabel(p, text=f"🎙 Voice Control ({mic_state})",
                      font=("Consolas", 14, "bold"),
                      text_color=C).pack(anchor="w", padx=20)

        mic_box = ctk.CTkTextbox(p, height=80, font=("Consolas", 11),
                                  fg_color="#0A1214", text_color=TXT)
        mic_box.pack(fill="x", padx=20, pady=(4, 4))

        mics = VoiceController.list_microphones()
        if not mics:
            mic_box.insert("end", "No audio devices found.\n")
        else:
            mic_box.insert("end", f"{len(mics)} device(s):\n")
            for i, name in mics:
                tag = " ◀ ACTIVE" if i == self.voice.mic_index else ""
                if self.voice.mic_index is None and i == 0:
                    tag = " ◀ DEFAULT"
                mic_box.insert("end", f"  [{i}] {name}{tag}\n")
        mic_box.configure(state="disabled")

        if self.voice.available:
            row = ctk.CTkFrame(p, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(2, 2))

            ctk.CTkLabel(row, text="Device #:", font=("Consolas", 12),
                          text_color=TXT).pack(side="left", padx=(0, 6))

            cur = self.voice.mic_index
            iv = ctk.StringVar(value=str(cur if cur is not None else 0))
            ctk.CTkEntry(row, textvariable=iv, width=50, font=("Consolas", 13),
                          fg_color=PNL, text_color=TXT, border_color=CD
                          ).pack(side="left", padx=(0, 6))

            def set_mic():
                try:
                    idx = int(iv.get())
                    self.voice.mic_index = idx
                    _save_config({"mic_index": idx})
                    self.toast.show(f"Mic → device [{idx}] (saved)")
                except ValueError:
                    self.toast.show("Invalid number")

            self._btn(row, "Set", set_mic, True, 50)

            test_lbl = ctk.CTkLabel(p, text="", font=("Consolas", 11), text_color=AMB)
            test_lbl.pack(anchor="w", padx=20)

            def test_mic():
                test_lbl.configure(text="Recording 3s …")
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
                        msg = (f"✓ RMS: {rms:.0f} (threshold: {th}) — "
                               f"{'GOOD' if rms > th else '⚠ TOO QUIET'}")
                    except Exception as e:
                        msg = f"✗ {e}"
                    def _update_lbl():
                        try:
                            if test_lbl.winfo_exists():
                                test_lbl.configure(text=msg)
                        except Exception:
                            pass
                    self.after(0, _update_lbl)
                threading.Thread(target=_t, daemon=True).start()

            self._btn_c(p, "🎙 Test Mic (3s)", test_mic, True)

        # Rotary section
        if self.rotary.available:
            ctk.CTkFrame(p, fg_color=CD, height=1).pack(fill="x", padx=20, pady=(8, 6))
            ctk.CTkLabel(p, text="🎛 Rotary Encoder: Connected",
                          font=("Consolas", 12), text_color=C
                          ).pack(anchor="w", padx=20)

        self.status.append("Opened Settings")

    def _set_dark(self, sw):
        self.dark_mode = bool(sw.get())
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")

    # ═══════════════════════════════════════
    #  System Info
    # ═══════════════════════════════════════

    def show_sysinfo(self):
        p = self._view("sysinfo", "System Info", "Device diagnostics")
        box = ctk.CTkTextbox(p, font=("Consolas", 12), fg_color="#0A1214", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)

        info = [
            f"Platform: {platform.platform()}",
            f"Machine:  {platform.machine()}",
            f"Python:   {sys.version.split()[0]}",
            f"Display:  {WIDTH}x{HEIGHT} @ {TARGET_FPS}fps",
            f"Pi mode:  {IS_PI}",
            f"OpenCV:   {'✓' if cv2 else '✗'}",
            f"Gemini SDK: {'✓' if genai else '✗'}",
            f"STT:      {'✓' if sr else '✗'}",
            f"GPIO:     {'✓' if GPIO else '✗'}",
            f"Rotary:   {'✓ active' if self.rotary.available else '✗ inactive'}",
            f"Voice:    {self.voice.state.value}",
            f"Photos:   {len(os.listdir(PHOTOS_DIR))} files",
        ]
        if psutil:
            info.append(f"CPU:      {psutil.cpu_count()} cores")
            info.append(f"RAM:      {psutil.virtual_memory().total // (1024**3)} GB")

        box.insert("end", "\n".join(info))
        box.configure(state="disabled")

    # ═══════════════════════════════════════
    #  Power
    # ═══════════════════════════════════════

    def show_power(self):
        p = self._view("power", "Power", "Device power options")
        w = ctk.CTkFrame(p, fg_color="transparent")
        w.pack(expand=True)

        ctk.CTkButton(w, text="⏻  Power Off", fg_color=RED,
                       hover_color="#FF1744", height=48,
                       font=("Consolas", 15, "bold"), text_color="white",
                       command=self._on_close
                       ).pack(pady=10, padx=36, fill="x")

        ctk.CTkButton(w, text="↻  Restart", fg_color=PNL,
                       hover_color=CD, height=48,
                       font=("Consolas", 15), text_color=TXT,
                       command=lambda: (self._on_close(),
                                        os.execl(sys.executable, sys.executable, *sys.argv))
                       ).pack(pady=10, padx=36, fill="x")

        ctk.CTkButton(w, text="ℹ  System Info", fg_color=PNL,
                       hover_color=CD, height=40,
                       font=("Consolas", 13), text_color=TXT,
                       command=self.show_sysinfo).pack(pady=10, padx=36, fill="x")

        ctk.CTkButton(w, text="Cancel", fg_color="transparent",
                       hover_color=PNL, height=36,
                       font=("Consolas", 13), text_color=TXTD,
                       command=self._go_home).pack(pady=16)

    # ═══════════════════════════════════════
    #  Bluetooth
    # ═══════════════════════════════════════

    def show_bluetooth(self):
        p = self._view("bluetooth", "Bluetooth", "Nearby device scan (simulated)")

        box = ctk.CTkTextbox(p, font=("Consolas", 13),
                              fg_color="#0A1214", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", "Press Scan to search …\n")
        box.configure(state="disabled")

        def scan():
            import random
            devs = ["Phone – Pixel 9 Pro", "Laptop – MacBook Pro",
                    "Earbuds – AirPods Pro", "Watch – Galaxy Watch",
                    "Speaker – JBL Flip 6", "Controller – PS5 DualSense"]
            random.shuffle(devs)
            now = datetime.now().strftime("%H:%M:%S")
            box.configure(state="normal")
            box.insert("end", f"\n[{now}] Found {len(devs)} devices:\n")
            for d in devs:
                box.insert("end", f"  ▸ {d}\n")
            box.configure(state="disabled")
            box.see("end")

        self._btn_c(p, "Scan", scan, True)

    # ═══════════════════════════════════════
    #  Track / GPS
    # ═══════════════════════════════════════

    def show_track(self):
        p = self._view("track", "Track / Location",
                        "IP geolocation demo · real device uses GPS")

        box = ctk.CTkTextbox(p, font=("Consolas", 13),
                              fg_color="#0A1214", text_color=TXT)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("end", "Press Refresh to locate …\n")
        box.configure(state="disabled")

        def go():
            box.configure(state="normal")
            box.insert("end", "\nLocating …\n")
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
            threading.Thread(target=_loc, daemon=True).start()

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
                    f"  Lat {d.get('latitude','?')}  ·  Lon {d.get('longitude','?')}")
        except Exception as e:
            return f"Failed: {e}"

    # ═══════════════════════════════════════
    #  Music
    # ═══════════════════════════════════════

    def show_music(self):
        p = self._view("music", "Music", "Now playing · demo controls")

        ctk.CTkLabel(p, text="♫  Lofi Beats for Coding",
                      font=("Consolas", 17, "bold"),
                      text_color=C).pack(pady=(18, 2))
        ctk.CTkLabel(p, text="Chillhop Records",
                      font=("Consolas", 12), text_color=TXTD).pack(pady=(0, 14))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(pady=8)
        for t in ["⏮ Prev", "▶ Play", "⏭ Next"]:
            ctk.CTkButton(row, text=t, width=100, height=36, corner_radius=6,
                           fg_color=PNLE, hover_color=CD,
                           text_color=TXT, font=("Consolas", 13),
                           command=lambda x=t: self.status.append(f"Music: {x}")
                           ).pack(side="left", padx=5)

        ctk.CTkLabel(p, text="Volume", font=("Consolas", 11),
                      text_color=TXTD).pack(pady=(18, 2))
        vol = ctk.CTkSlider(p, from_=0, to=100, number_of_steps=10,
                             progress_color=C, button_color=C)
        vol.set(70); vol.pack(fill="x", padx=36)

    # ═══════════════════════════════════════
    #  Shared helpers
    # ═══════════════════════════════════════

    def _btn(self, parent, text, cmd, primary=False, w=None):
        kw = dict(text=text, command=cmd, corner_radius=6,
                  font=("Consolas", 12, "bold") if primary else ("Consolas", 12),
                  fg_color=CD if primary else PNL,
                  hover_color=C if primary else PNLE,
                  text_color="black" if primary else TXT)
        if w:
            kw["width"] = w
        ctk.CTkButton(parent, **kw).pack(side="left", padx=3)

    def _btn_c(self, parent, text, cmd, primary=False):
        ctk.CTkButton(parent, text=text, command=cmd, width=160, corner_radius=6,
                       font=("Consolas", 13, "bold") if primary else ("Consolas", 13),
                       fg_color=CD if primary else PNL,
                       hover_color=C if primary else PNLE,
                       text_color="black" if primary else TXT).pack(pady=(0, 8))

    @staticmethod
    def _safe(fn):
        try:
            fn()
        except Exception:
            pass

    # ═══════════════════════════════════════
    #  Main loop
    # ═══════════════════════════════════════

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
            self.cv.itemconfigure(self._timer_id, text=f"⏱ {m:02d}:{s:02d}")

        self.after(max(1, int(1000 / TARGET_FPS)), self._tick)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    VAApp().mainloop()
