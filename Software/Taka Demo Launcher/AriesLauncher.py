import os, time
from datetime import datetime
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFilter
from tkinterweb import HtmlFrame


# Optional modules – app still runs without them
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

# Optional: local LLM + translation
try:
    import ollama
except Exception:
    ollama = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

import platform

IS_PI = (
    platform.machine().startswith(("armv7l", "armv6l", "aarch64"))
    and "raspberrypi" in platform.platform().lower()
)

if IS_PI:
    WIDTH, HEIGHT = 640, 400
    TARGET_FPS = 30
    BASE_ICON = 112
    SPACING = 148
    FLOW_LAMBDA = 18.0
    SIZE_STEP_PX = 4
    ALPHA_STEP_8 = 32

# ---------- Configuration -------------
WIDTH, HEIGHT = 1280, 720
TARGET_FPS = 144

# Match your folder name with the assets
ASSETS_DIR = os.path.join(os.getcwd(), "VA-Assets (Colored, Fall 2025)")

APPS = [
    ("assistant.png", "Assistant"),
    ("augreality.png", "AugReality"),
    ("avatar.png", "Avatar"),
    ("bluetooth.png", "Bluetooth"),
    ("camera.png", "Camera"),
    ("eyetrack.png", "EyeTrack"),
    ("gesture.png", "Gesture"),
    ("gps.png", "Track"),
    ("livestream.png", "LiveStream"),
    ("localassistant.png", "LocalAI"),
    ("music.png", "Music"),
    ("phone.png", "Phone"),
    ("photo.png", "Photo"),
    ("plugin.png", "Plugin"),
    ("settings.png", "Settings"),
    ("spatialaudio.png", "SpatialAudio"),
    ("theme.png", "Theme"),
    ("track.png", "Track"),
    ("translate.png", "Translate"),
    ("video.png", "Video"),
    ("browser.png", "Browser"),
    ("power.png", "Power"),

]

LOGO_PATH = os.path.join(ASSETS_DIR, "logonew.png")
MIC_PATH = os.path.join(ASSETS_DIR, "mic.png")

BUILD_STR = "VA-OS1.1 · Pandora Build · Oct 2025"

LABEL_COLOR = "black"
SPACING = 180
BASE_ICON = 132
SCALE_DROP = 0.14
ALPHA_DROP = 0.22
FLOW_LAMBDA = 26.0
SIZE_STEP_PX = 2
ALPHA_STEP_8 = 8


def load_image(path):
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def circle_crop_rgba(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def make_soft_glow(radius: int, alpha: int = 140) -> Image.Image:
    w = h = radius * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    layers = [
        (0.55, alpha),
        (1.15, int(alpha * 0.70)),
        (2.00, int(alpha * 0.40)),
        (3.00, int(alpha * 0.18)),
    ]
    for scale, a in layers:
        r = radius * scale
        d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=(255, 255, 255, a))
    img = img.filter(ImageFilter.GaussianBlur(int(radius * 0.30)))
    return img


def safe_batt():
    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            b = psutil.sensors_battery()
            if b:
                return f"{int(b.percent)}%"
        except Exception:
            pass
    return "–%"


def safe_cpu():
    if psutil:
        try:
            return f"{psutil.cpu_percent():.0f}%"
        except Exception:
            pass
    return "–%"


def safe_ram():
    if psutil:
        try:
            return f"{psutil.virtual_memory().percent:.0f}%"
        except Exception:
            pass
    return "–%"


def safe_time_str():
    now = datetime.now()
    try:
        return now.strftime("%-I:%M %p")  # Unix
    except ValueError:
        return now.strftime("%#I:%M %p")  # Windows


# ---------- UI building blocks ----------


class StatusBar:
    def __init__(self, canvas: ctk.CTkCanvas):
        self.cv = canvas
        self.console = []
        self.weather = "…"
        self.text_id = None
        self._last_update = 0.0

    def append(self, line: str):
        self.console.append(line)
        self.console = self.console[-3:]

    def tick(self):
        nowt = time.perf_counter()
        if nowt - self._last_update < 0.25:
            return
        self._last_update = nowt

        now_str = safe_time_str()
        lines = "\n".join(self.console)
        txt = (
            f"{now_str} · {safe_batt()} · {self.weather} · "
            f"CPU {safe_cpu()} · RAM {safe_ram()}\n{BUILD_STR}"
        )
        if lines:
            txt += "\n" + lines
        if self.text_id is None:
            self.text_id = self.cv.create_text(
                16, 84, anchor="nw", fill="white", font=("Helvetica", 12), text=txt
            )
        else:
            self.cv.itemconfigure(self.text_id, text=txt)


class CoverFlow:
    def __init__(self, canvas: ctk.CTkCanvas, apps, base_icon=BASE_ICON, spacing=SPACING):
        self.cv = canvas
        self.base_icon = base_icon
        self.spacing = spacing
        self.sel = 0
        self.sel_anim = 0.0

        self.icons = []
        self._img_refs = [None] * 5
        self.label_id = None

        self.apps = []
        for fn, label in apps:
            img = load_image(os.path.join(ASSETS_DIR, fn)) or Image.new(
                "RGBA", (base_icon, base_icon), (200, 200, 200, 255)
            )
            self.apps.append(
                {
                    "id": os.path.splitext(fn)[0],
                    "label": label,
                    "img": img,
                    "cache": {},
                }
            )

        glow_img = make_soft_glow(int(base_icon * 1.2), 140)
        self._glow_tk = ImageTk.PhotoImage(glow_img)
        self.glow_id = self.cv.create_image(0, 0, image=self._glow_tk, anchor="nw")

        for _ in range(5):
            self.icons.append(self.cv.create_image(0, 0, image=None, anchor="nw"))
        self.label_id = self.cv.create_text(
            0, 0, text="", fill=LABEL_COLOR, font=("Helvetica", 16, "bold")
        )

    def _get_tkimg(self, app, size_px: int, alpha: float):
        size_q = max(14, int(round(size_px / SIZE_STEP_PX) * SIZE_STEP_PX))
        a255 = int(max(0, min(255, round(alpha * 255 / ALPHA_STEP_8) * ALPHA_STEP_8)))
        key = (size_q, a255)
        cache = app["cache"]
        if key in cache:
            return cache[key]

        circ = circle_crop_rgba(app["img"], size_q)
        if a255 < 255:
            am = circ.split()[-1].point(lambda p, a=a255: int(p * a / 255))
            circ.putalpha(am)
        tkimg = ImageTk.PhotoImage(circ)
        cache[key] = tkimg
        return tkimg

    def step(self, dt):
        n = len(self.apps)
        if n == 0:
            return
        d = self.sel - self.sel_anim
        if d > n / 2:
            d -= n
        if d < -n / 2:
            d += n
        dt = max(1 / 480, dt)
        alpha = 1.0 - pow(2.718281828, -FLOW_LAMBDA * dt)
        self.sel_anim += d * alpha
        if abs(d) < 1e-4:
            self.sel_anim = round(self.sel_anim)
        self._redraw_icons()

    def update_selection(self, delta):
        if self.apps:
            self.sel = (self.sel + delta) % len(self.apps)

    def current_app(self):
        if not self.apps:
            return None
        return self.apps[self.sel % len(self.apps)]

    def _redraw_icons(self):
        midx, midy = WIDTH // 2, HEIGHT // 2 - 10
        x0 = midx - 2 * self.spacing
        frac = self.sel_anim - round(self.sel_anim)
        order = (0, 4, 1, 3, 2)

        positions = []
        for slot, i in enumerate(order):
            idx = int(round(self.sel_anim) - 2 + i) % len(self.apps)
            app = self.apps[idx]
            dist = abs(i - 2 + frac)
            scale = max(0.70, 1.0 - SCALE_DROP * dist)
            alpha = max(0.46, 1.0 - ALPHA_DROP * dist)

            size = int(self.base_icon * scale)
            tkimg = self._get_tkimg(app, size, alpha)

            cx, cy = x0 + i * self.spacing, midy
            self.cv.itemconfigure(self.icons[slot], image=tkimg)
            self.cv.coords(
                self.icons[slot],
                int(cx - tkimg.width() / 2),
                int(cy - tkimg.height() / 2),
            )
            self._img_refs[slot] = tkimg

            if i == 2:
                gx = int(cx - self._glow_tk.width() / 2)
                gy = int(cy - self._glow_tk.height() / 2 + self.base_icon * 0.03)
                self.cv.coords(self.glow_id, gx, gy)

            positions.append((cx, cy, tkimg.width(), app["label"]))

        for cx, cy, size_w, label in positions:
            if abs(cx - midx) < 2:
                self.cv.itemconfigure(self.label_id, text=label, fill=LABEL_COLOR)
                self.cv.coords(self.label_id, cx, cy + size_w / 2 + 28)
                break


# ---------- Main Aries launcher with MVP functionality ----------


class VAApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry(f"{WIDTH}x{HEIGHT}")
        self.title("Aries Launcher")
        self.resizable(False, False)

        self.cv = ctk.CTkCanvas(self, width=WIDTH, height=HEIGHT, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)

        self.status = StatusBar(self.cv)
        self.cflow = CoverFlow(self.cv, APPS)

        self.view_frame = ctk.CTkFrame(self, fg_color="black")
        self.view_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.view_frame.lower()

        self.current_view = "home"

        # Assistant state
        self.assistant_history_widget = None
        self.assistant_chat_history = []
        # Use your installed Ollama model here
        self.assistant_model_name = "gemma3:4b"

        # Camera state
        self.camera_label = None
        self.camera_cap = None
        self._camera_after_id = None
        self.camera_running = False

        # Settings state
        self.dark_mode = True
        self.bluetooth_enabled = False
        self.notifications_enabled = True

        # Map app IDs to handler methods
        self.app_handlers = {
            "assistant": self.show_assistant,
            "camera": self.show_camera,
            "translate": self.show_translate,
            "settings": self.show_settings,
            "music": self.show_music,
            "bluetooth": self.show_bluetooth,
            "track": self.show_track,
            "gps": self.show_track,
            "browser": self.show_browser,
            "power": self.show_power,
        }

        # Key bindings – routed through handlers so we can ignore when typing
        self.bind("<Left>", self._on_left_key)
        self.bind("<Right>", self._on_right_key)
        self.bind("<Return>", self._on_return_key)
        self.bind("<space>", self._on_space_key)
        self.bind("<Escape>", self._on_escape_key)

        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", lambda e: self.nav(+1))
        self.bind_all("<Button-5>", lambda e: self.nav(-1))

        self._last_time = time.perf_counter()
        self._tick()

    # -------- key handlers (fully fixed typing rules) --------

    def _is_text_widget(self, widget=None):
        """Return True if ANY text widget is currently focused."""
        focused = self.focus_get()
        return isinstance(focused, (ctk.CTkEntry, ctk.CTkTextbox))

    def _on_left_key(self, event):
        if self.current_view == "home" and not self._is_text_widget():
            self.nav(-1)

    def _on_right_key(self, event):
        if self.current_view == "home" and not self._is_text_widget():
            self.nav(+1)

    def _on_return_key(self, event):
        if self.current_view == "home" and not self._is_text_widget():
            self.open_current()

    def _on_space_key(self, event):
        if self.current_view == "home" and not self._is_text_widget():
            self.open_current()

    def _on_escape_key(self, event):
    # Escape ALWAYS returns to home view
        if self.current_view != "home":
            self.go_home()


    # -------- navigation --------

    def nav(self, d: int):
        if self.current_view == "home":
            self.cflow.update_selection(d)

    def open_current(self):
        app = self.cflow.current_app()
        if not app:
            return
        self.status.append(f"Opened {app['label']}")
        handler = self.app_handlers.get(app["id"])
        if handler:
            handler()
        else:
            self.show_generic_app(app["label"])

    def go_home(self):
        self.current_view = "home"
        self._stop_camera()
        self.view_frame.lower()
        self.cv.lift()
        self.status.append("Returned to home")

    def _wheel(self, e):
        self.nav(1 if e.delta > 0 else -1)

    # -------- view helpers --------

    def _clear_view_frame(self):
        # stop camera when leaving a view
        self._stop_camera()
        for child in self.view_frame.winfo_children():
            child.destroy()

    def _show_view(self, view_id: str, title: str, body: str, placeholder_text=True):
        self.current_view = view_id
        self._clear_view_frame()
        self.view_frame.lift()

        title_label = ctk.CTkLabel(
            self.view_frame, text=title, font=("Helvetica", 28, "bold")
        )
        title_label.pack(pady=30)

        body_label = ctk.CTkLabel(
            self.view_frame,
            text=body,
            font=("Helvetica", 18),
            wraplength=WIDTH - 120,
            justify="center",
        )
        body_label.pack(pady=10)

        content_frame = ctk.CTkFrame(self.view_frame, corner_radius=18)
        content_frame.pack(pady=20, padx=40, fill="both", expand=True)

        if placeholder_text:
            content_label = ctk.CTkLabel(
                content_frame,
                text=f"[{title} UI placeholder]\nHook your real functionality here.",
                font=("Helvetica", 16),
                justify="center",
            )
            content_label.place(relx=0.5, rely=0.5, anchor="center")

        hint_label = ctk.CTkLabel(
            self.view_frame,
            text="Press ESC to return to Home",
            font=("Helvetica", 14),
        )
        hint_label.pack(pady=16)

        return content_frame

    def show_generic_app(self, label: str):
        self._show_view(
            view_id=f"app:{label}",
            title=label,
            body=f"{label} screen is not fully implemented yet,\n"
            f"but this is where its UI will live.",
        )

    # -------- Assistant --------

    def show_assistant(self):
        frame = self._show_view(
            view_id="assistant",
            title="Assistant",
            body="Voice + text assistant (local MVP demo).\n"
            "Type a message below – powered by a local Ollama model when available.",
            placeholder_text=False,
        )

        history = ctk.CTkTextbox(frame, font=("Consolas", 14), wrap="word")
        history.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 5))
        history.insert("end", "Assistant: Hi! How can I help you today?\n")
        if ollama is not None:
            history.insert("end", f"(Model: {self.assistant_model_name} via Ollama)\n\n")
        else:
            history.insert("end", "(Local math/demo fallback – Ollama not available)\n\n")
        history.configure(state="disabled")

        input_frame = ctk.CTkFrame(frame)
        input_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        entry = ctk.CTkEntry(input_frame, placeholder_text="Type your message...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        send_btn = ctk.CTkButton(
            input_frame, text="Send", command=lambda: self._assistant_send(entry, history)
        )
        send_btn.pack(side="right")

        self.assistant_history_widget = history
        entry.bind("<Return>", lambda e: self._assistant_send(entry, history))
        entry.focus_set()

    def _assistant_send(self, entry: ctk.CTkEntry, history: ctk.CTkTextbox):
        msg = entry.get().strip()
        if not msg:
            return
        entry.delete(0, "end")

        history.configure(state="normal")
        history.insert("end", f"You: {msg}\n")

        # Prefer local LLM via Ollama if available, otherwise fallback
        if ollama is not None:
            reply = self._assistant_model_reply(msg)
        else:
            reply = self._assistant_local_reply(msg)

        history.insert("end", f"Assistant: {reply}\n\n")
        history.configure(state="disabled")
        history.see("end")

    def _assistant_model_reply(self, msg: str) -> str:
        """Use local Ollama model for replies."""
        if not ollama:
            return self._assistant_local_reply(msg)

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant running locally on a pair of smart glasses. "
                        "Give short, clear answers that are easy to read on a small display."
                    ),
                }
            ]
            messages.extend(self.assistant_chat_history)
            messages.append({"role": "user", "content": msg})

            resp = ollama.chat(
                model=self.assistant_model_name,
                messages=messages,
            )
            answer = resp.get("message", {}).get("content", "").strip() or "[No response]"

            self.assistant_chat_history.append({"role": "user", "content": msg})
            self.assistant_chat_history.append({"role": "assistant", "content": answer})

            return answer
        except Exception as e:
            return f"(Local LLM error: {e})"

    def _assistant_local_reply(self, msg: str) -> str:
        # simple math handling
        import re, math

        expr = re.sub(r"[^0-9\+\-\*\/\.\(\) ]", "", msg)
        if expr and any(ch.isdigit() for ch in expr):
            try:
                result = eval(expr, {"__builtins__": {}}, {"math": math})
                return f"The result is {result} (computed locally)."
            except Exception:
                pass

        if "hello" in msg.lower():
            return "Hello! I’m running fully on-device in this demo."
        if "where" in msg.lower():
            return "I don’t have full GPS yet, but you can open the Track app to see an approximate location."
        if "time" in msg.lower():
            return f"It’s currently {safe_time_str()}."
        return (
            "I received your request and processed it locally as part of the MVP.\n"
            "(Cloud models can be connected later for richer responses.)"
        )

    # -------- Camera --------

    def show_camera(self):
        frame = self._show_view(
            view_id="camera",
            title="Camera",
            body="Live camera preview.\n"
            "If a camera is connected and OpenCV is installed, you’ll see it here.",
            placeholder_text=False,
        )

        self.camera_label = ctk.CTkLabel(
            frame, text="Initializing camera...", font=("Helvetica", 16)
        )
        self.camera_label.place(relx=0.5, rely=0.5, anchor="center")

        btn_frame = ctk.CTkFrame(self.view_frame)
        btn_frame.pack(pady=(0, 10))
        ctk.CTkButton(
            btn_frame, text="Restart Camera", command=self._restart_camera
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_frame, text="Stop Camera", command=self._stop_camera
        ).pack(side="left", padx=8)

        self._start_camera()

    def _start_camera(self):
        if cv2 is None:
            if self.camera_label:
                self.camera_label.configure(
                    text="OpenCV (cv2) not installed.\nRun: pip install opencv-python"
                )
            return
        try:
            self.camera_cap = cv2.VideoCapture(0)
        except Exception:
            self.camera_cap = None
        if not self.camera_cap or not self.camera_cap.isOpened():
            if self.camera_label:
                self.camera_label.configure(
                    text="No camera connected or access denied.\n"
                    "On your teammate’s Mac, this should show the live feed."
                )
            return

        self.camera_running = True
        self._update_camera_frame()

    def _update_camera_frame(self):
        if not self.camera_running or not self.camera_cap:
            return
        ret, frame = self.camera_cap.read()
        if not ret:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img = img.resize((800, 450))
        imgtk = ImageTk.PhotoImage(img)
        self._cam_imgtk = imgtk  # keep reference
        if self.camera_label:
            self.camera_label.configure(image=imgtk, text="")
        self._camera_after_id = self.after(33, self._update_camera_frame)

    def _stop_camera(self):
        self.camera_running = False
        if self._camera_after_id:
            try:
                self.after_cancel(self._camera_after_id)
            except Exception:
                pass
            self._camera_after_id = None
        if self.camera_cap:
            try:
                self.camera_cap.release()
            except Exception:
                pass
            self.camera_cap = None
        if self.camera_label:
            self.camera_label.configure(image=None, text="Camera stopped.")

    def _restart_camera(self):
        self._stop_camera()
        if self.camera_label:
            self.camera_label.configure(text="Restarting camera…")
        self._start_camera()

    # -------- Browser ----------

    def show_browser(self):
        frame = self._show_view(
            view_id="browser",
            title="Web Browser",
            body="Embedded on-device browser.\nTouch, keyboard, and gesture ready.",
            placeholder_text=False,
    )

    # --- Top navigation bar ---
        bar = ctk.CTkFrame(frame)
        bar.pack(fill="x", padx=16, pady=(10, 6))

        url_var = ctk.StringVar(value="https://www.google.com")

        url_entry = ctk.CTkEntry(
            bar,
            textvariable=url_var,
            placeholder_text="Enter URL or search…",
            font=("Helvetica", 14),
    )
        url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    # --- Browser container ---
        browser_frame = ctk.CTkFrame(frame, corner_radius=18)
        browser_frame.pack(fill="both", expand=True, padx=16, pady=(6, 16))

        html = HtmlFrame(browser_frame, horizontal_scrollbar="auto")
        html.pack(fill="both", expand=True)

        def normalize(text: str) -> str:
            text = text.strip()

            # Treat anything without a protocol as a Google search
            if not text.startswith(("http://", "https://")):
                return (
                    "https://www.google.com/search"
                    "?hl=en&igu=1&q="
                    + text.replace(" ", "+")
        )

            return text



        def go():
            url = normalize(url_var.get())
            html.load_website(url)
            self.status.append(f"Browser opened {url}")

    # --- Controls ---
        ctk.CTkButton(bar, text="Go", width=70, command=go).pack(side="left")
        ctk.CTkButton(bar, text="◀", width=40, command=html.go_back).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="▶", width=40, command=html.go_forward).pack(side="left")
        ctk.CTkButton(bar, text="⟳", width=40, command=html.reload).pack(side="left", padx=4)

        html.load_website("https://www.google.com")
        url_entry.bind("<Return>", lambda e: go())
        url_entry.focus_set()


    # -------- Translate --------

    def show_translate(self):
        frame = self._show_view(
            view_id="translate",
            title="Translate",
            body="Simple text translation MVP.\n"
            "Uses deep-translator (GoogleTranslator) when available.",
            placeholder_text=False,
        )

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", pady=(10, 5), padx=10)

        ctk.CTkLabel(top_frame, text="Target language:").pack(side="left", padx=(0, 8))

        languages = ["Japanese", "Spanish", "French", "Korean", "German", "Chinese"]
        lang_var = ctk.StringVar(value="Japanese")
        lang_menu = ctk.CTkOptionMenu(top_frame, values=languages, variable=lang_var)
        lang_menu.pack(side="left")

        src_box = ctk.CTkTextbox(frame, height=160, font=("Helvetica", 14))
        src_box.pack(fill="x", padx=10, pady=(10, 5))
        src_box.insert("end", "Hello, how are you?")
        src_box.focus_set()

        tgt_box = ctk.CTkTextbox(frame, height=160, font=("Helvetica", 14))
        tgt_box.pack(fill="x", padx=10, pady=(5, 10))
        tgt_box.insert("end", "Translation will appear here…")
        tgt_box.configure(state="disabled")

        def do_translate():
            text = src_box.get("1.0", "end").strip()
            lang = lang_var.get()
            result = self._local_translate(text, lang)
            tgt_box.configure(state="normal")
            tgt_box.delete("1.0", "end")
            tgt_box.insert("end", result)
            tgt_box.configure(state="disabled")

        ctk.CTkButton(frame, text="Translate", command=do_translate).pack(
            pady=(0, 10)
        )

    def _local_translate(self, text: str, lang: str) -> str:
        """
        Use deep-translator (GoogleTranslator) if installed.
        Falls back to a tiny dictionary if unavailable.
        """
        if not text.strip():
            return ""

        # Real translation path
        if GoogleTranslator is not None:
            lang_map = {
                "Japanese": "ja",
                "Spanish": "es",
                "French": "fr",
                "Korean": "ko",
                "German": "de",
                "Chinese": "zh-cn",
            }
            target_code = lang_map.get(lang, "en")
            try:
                translator = GoogleTranslator(source="auto", target=target_code)
                translated = translator.translate(text)
                return translated
            except Exception as e:
                return f"Translation error: {e}"

        # Fallback: tiny demo dictionary
        small_dict = {
            ("Hello", "Japanese"): "こんにちは",
            ("Hello", "Spanish"): "Hola",
            ("Hello", "French"): "Bonjour",
        }
        if text.strip() in ("Hello", "Hello, how are you?"):
            key = ("Hello", lang)
            base = small_dict.get(key, None)
            if base:
                return f"{base}  (local demo translation to {lang})"

        return (
            f"{text}\n\n[Demo] deep-translator is not installed.\n"
            f"Pretend this is translated into {lang}."
        )

    # -------- Settings --------

    def show_settings(self):
        frame = self._show_view(
            view_id="settings",
            title="Settings",
            body="Device + app settings for the Smart Glasses MVP.",
            placeholder_text=False,
        )

        # Dark / Light mode
        mode_switch = ctk.CTkSwitch(
            frame,
            text="Dark mode",
            command=lambda: self._toggle_dark_mode(mode_switch),
        )
        mode_switch.select()  # default dark
        mode_switch.pack(anchor="w", padx=20, pady=(20, 10))

        # Bluetooth toggle
        bt_switch = ctk.CTkSwitch(
            frame,
            text="Bluetooth enabled",
            command=lambda: self._toggle_bluetooth(bt_switch),
        )
        bt_switch.pack(anchor="w", padx=20, pady=10)

        # Notifications toggle
        notif_switch = ctk.CTkSwitch(
            frame,
            text="Notifications",
            command=lambda: self._toggle_notifications(notif_switch),
        )
        notif_switch.select()
        notif_switch.pack(anchor="w", padx=20, pady=10)

        # Fake brightness slider
        ctk.CTkLabel(frame, text="Display brightness (demo)").pack(
            anchor="w", padx=20, pady=(20, 4)
        )
        bright_var = ctk.DoubleVar(value=0.8)
        bright_slider = ctk.CTkSlider(
            frame, from_=0.2, to=1.0, number_of_steps=8, variable=bright_var
        )
        bright_slider.pack(fill="x", padx=20)

        self.status.append("Opened Settings")

    def _toggle_dark_mode(self, switch: ctk.CTkSwitch):
        self.dark_mode = bool(switch.get())
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")
        self.status.append(f"Theme set to {'dark' if self.dark_mode else 'light'}")

    def _toggle_bluetooth(self, switch: ctk.CTkSwitch):
        self.bluetooth_enabled = bool(switch.get())
        self.status.append(
            f"Bluetooth {'enabled' if self.bluetooth_enabled else 'disabled'}"
        )

    def _toggle_notifications(self, switch: ctk.CTkSwitch):
        self.notifications_enabled = bool(switch.get())
        self.status.append(
            f"Notifications {'on' if self.notifications_enabled else 'off'}"
        )
    # -------- Power -----------------------------

    def show_power(self):
        frame = self._show_view(
            view_id="power",
            title="Power",
            body="Manage device power state.",
            placeholder_text=False,
    )

        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(expand=True)

        def power_off():
            self.status.append("Powering off…")
            self.after(300, self.destroy)  # graceful shutdown

        def restart():
            self.status.append("Restarting…")
            python = os.sys.executable
            os.execl(python, python, *os.sys.argv)

        def cancel():
            self.go_home()

        ctk.CTkButton(
            button_frame,
            text="🔴 Power Off",
            fg_color="#8B0000",
            hover_color="#A00000",
            height=50,
            font=("Helvetica", 18, "bold"),
            command=power_off,
        ).pack(pady=12, padx=40, fill="x")

        ctk.CTkButton(
            button_frame,
            text="🔄 Restart",
            height=50,
            font=("Helvetica", 18),
            command=restart,
        ).pack(pady=12, padx=40, fill="x")

        ctk.CTkButton(
            button_frame,
            text="Cancel",
            height=40,
            font=("Helvetica", 16),
            command=cancel,
        ).pack(pady=20)


    # -------- Bluetooth (simulated scan) --------

    def show_bluetooth(self):
        frame = self._show_view(
            view_id="bluetooth",
            title="Bluetooth",
            body="Scan for nearby devices (simulated for MVP).\n"
            "On the real glasses this would use the Bluetooth stack.",
            placeholder_text=False,
        )

        result_box = ctk.CTkTextbox(frame, font=("Consolas", 13))
        result_box.pack(fill="both", expand=True, padx=10, pady=10)
        result_box.insert("end", "Press 'Scan' to search for devices…\n")
        result_box.configure(state="disabled")

        def scan():
            # Fake device list for demo
            import random, datetime as dt

            fake_devices = [
                "Phone – Pixel 9 Pro",
                "Laptop – MacBook Pro",
                "Earbuds – AirPods Pro",
                "Watch – Galaxy Watch",
            ]
            random.shuffle(fake_devices)
            now = dt.datetime.now().strftime("%H:%M:%S")

            result_box.configure(state="normal")
            result_box.insert("end", f"\n[{now}] Scan complete. Devices found:\n")
            for d in fake_devices:
                result_box.insert("end", f" • {d}\n")
            result_box.configure(state="disabled")
            result_box.see("end")
            self.status.append("Bluetooth scan (demo) finished")

        ctk.CTkButton(frame, text="Scan for devices", command=scan).pack(pady=(0, 10))

    # -------- Track / GPS (IP-based demo) --------

    def show_track(self):
        frame = self._show_view(
            view_id="track",
            title="Track / Location",
            body="Approximate location based on network (demo).\n"
            "Real device would use onboard GPS.",
            placeholder_text=False,
        )

        info_box = ctk.CTkTextbox(frame, font=("Consolas", 13))
        info_box.pack(fill="both", expand=True, padx=10, pady=10)
        info_box.insert("end", "Press 'Refresh location' to query IP-based geolocation.\n")
        info_box.configure(state="disabled")

        def refresh():
            info_box.configure(state="normal")
            info_box.insert("end", "\nRequesting location…\n")
            info_box.configure(state="disabled")
            self.update_idletasks()

            loc = self._fetch_ip_location()

            info_box.configure(state="normal")
            info_box.insert("end", f"{loc}\n")
            info_box.configure(state="disabled")
            info_box.see("end")

        ctk.CTkButton(frame, text="Refresh location", command=refresh).pack(
            pady=(0, 10)
        )

    def _fetch_ip_location(self) -> str:
        if not requests:
            return "requests module not available – cannot query network."
        try:
            r = requests.get("https://ipapi.co/json/", timeout=3)
            if r.status_code != 200:
                return f"Location request failed with HTTP {r.status_code}."
            data = r.json()
            city = data.get("city", "?")
            region = data.get("region", "?")
            country = data.get("country_name", "?")
            lat = data.get("latitude", "?")
            lon = data.get("longitude", "?")
            return (
                f"Approximate IP-based location:\n"
                f"  {city}, {region}, {country}\n"
                f"  Lat: {lat}  Lon: {lon}"
            )
        except Exception as e:
            return f"Location lookup failed: {e}"

    # -------- Music (fake controls) --------

    def show_music(self):
        frame = self._show_view(
            view_id="music",
            title="Music",
            body="Now Playing + basic controls (demo, no real audio).",
            placeholder_text=False,
        )

        track_label = ctk.CTkLabel(
            frame,
            text="Now Playing: Lofi Beats for Coding",
            font=("Helvetica", 18, "bold"),
        )
        track_label.pack(pady=(20, 10))

        controls = ctk.CTkFrame(frame)
        controls.pack(pady=10)

        def log(action):
            self.status.append(f"Music: {action}")

        for txt in ["⏮ Prev", "▶ Play/Pause", "⏭ Next"]:
            ctk.CTkButton(
                controls, text=txt, width=120, command=lambda t=txt: log(t)
            ).pack(side="left", padx=8)

        vol_label = ctk.CTkLabel(frame, text="Volume")
        vol_label.pack(pady=(20, 4))
        vol_slider = ctk.CTkSlider(frame, from_=0, to=100, number_of_steps=10)
        vol_slider.set(70)
        vol_slider.pack(fill="x", padx=40)

    # -------- main loop --------

    def _tick(self):
        now = time.perf_counter()
        dt = max(1e-3, now - self._last_time)
        self._last_time = now

        if self.current_view == "home":
            self.cflow.step(dt)

        self.status.tick()
        delay_ms = max(1, int(1000 / TARGET_FPS))
        self.after(delay_ms, self._tick)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = VAApp()
    app.mainloop()
