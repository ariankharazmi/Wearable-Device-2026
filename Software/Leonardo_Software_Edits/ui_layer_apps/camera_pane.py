# Software/Taka Software Edits/ui_layer_apps/camera_pane.py
# =============================================================================
# CAMERA PANE (MVP)
# -----------------------------------------------------------------------------
# What this is:
#   - Simple camera HUD pane that works with the services layer.
#   - Voice:
#       "snap photo"  -> saves a JPG to ./captures/
#       "start recording" / "stop recording" -> MP4 via OpenCV if available
#       "open launcher" -> go back home
#
# Notes:
#   - Uses ctx.camera.read() to get frames. If OpenCV isn't installed or the
#     camera isn't available, actions fail gracefully with a toast.
#   - overlay.* currently logs to console; once your renderer draws text/images,
#     the same APIs will render to the glasses display.
# =============================================================================

from __future__ import annotations
import os, sys, datetime

class SettingsPane(Pane):
    ...
    def draw(self):
        self.render()

    def handle_input(self, input_event=None):
        pass


try:
    import cv2  # optional dependency for save/record
except Exception:
    cv2 = None  # type: ignore

# Robust import of Pane base
try:
    from Leonardo_Software_Edits.main_ui_layer.pane_base import Pane
except Exception:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ML = os.path.join(BASE, "main_ui_layer")
    if ML not in sys.path:
        sys.path.insert(0, ML)
    from pane_base import Pane  # type: ignore


class CameraPane(Pane):
    id = "camera"
    title = "Camera"
    icon = "icons/icon-camera.png"

    def on_mount(self) -> None:
        self.save_dir = os.path.join(os.getcwd(), "captures")
        os.makedirs(self.save_dir, exist_ok=True)
        self.recording = False
        self._writer = None
        self._status = ""

    def on_unmount(self) -> None:
        self._stop_recording_if_needed()

    # ------------------------------ RENDER ------------------------------------
    def render(self) -> None:
        """
        Draw a minimal HUD on top of whatever background the app loop shows.
        If recording, append frames to the writer.
        """
        w, h = self.ctx.display.width, self.ctx.display.height
        self.ctx.overlay.text(self.title, 12, 12, size=18)

        # Simple crosshair using text glyphs (renderer-agnostic)
        cx, cy = int(w * 0.5), int(h * 0.5)
        self.ctx.overlay.text("+", cx, cy, size=20)
        self.ctx.overlay.text("┌", cx - 60, cy - 40, size=18)
        self.ctx.overlay.text("┐", cx + 48, cy - 40, size=18)
        self.ctx.overlay.text("└", cx - 60, cy + 28, size=18)
        self.ctx.overlay.text("┘", cx + 48, cy + 28, size=18)

        rec = "REC ●" if self.recording else "STBY ○"
        self.ctx.overlay.text(f"{rec}  |  Say: 'snap photo', 'start recording', 'stop recording'",
                              12, int(h * 0.90), size=16)
        if self._status:
            self.ctx.overlay.text(self._status, 12, int(h * 0.84), size=16)

        # Append frame if recording
        if self.recording and cv2 is not None and self._writer is not None:
            ok, frame = self.ctx.camera.read()
            if ok and frame is not None:
                try:
                    fw = int(self._writer.get(cv2.CAP_PROP_FRAME_WIDTH))
                    fh = int(self._writer.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    if frame.shape[1] != fw or frame.shape[0] != fh:
                        frame = cv2.resize(frame, (fw, fh))
                    self._writer.write(frame)
                except Exception:
                    self._stop_recording_if_needed()
                    self._status = "Recording halted (write error)."

    # ------------------------------ VOICE -------------------------------------
    def on_voice(self, text: str) -> None:
        t = (text or "").strip().lower()

        if t in ("open launcher", "go home", "open home", "launcher"):
            self.ctx.event_bus.emit("NAVIGATE", pane_id="launcher"); return

        if t in ("snap", "take photo", "snap photo", "capture photo"):
            if self.ctx.camera is None:
                self._status = "Camera not available."
                return
            ok, frame = self.ctx.camera.read()
            if ok and frame is not None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"photo_{timestamp}.jpg"
                path = os.path.join(self.save_dir, filename)
                try:
                    cv2.imwrite(path, frame)
                    self._status = f"Photo saved: {filename}"
                except Exception as e:
                    self._status = f"Failed to save photo: {e}"
            else:
                self._status = "Failed to capture photo."
            return
