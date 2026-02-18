# Software/Taka Software Edits/main_ui_layer/trial_app.py
from __future__ import annotations
import time
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from services import make_services
from pane_base import Pane
from pane_wrappers import make_functional_pane

# import real panes (adjust names if your files differ)
from Leonardo_Software_Edits.ui_layer_apps.launcher_pane import LauncherPane
from Leonardo_Software_Edits.ui_layer_apps.wifi_pane import WiFiPane
from Leonardo_Software_Edits.ui_layer_apps.settings_pane import SettingsPane
from Leonardo_Software_Edits.ui_layer_apps.camera_pane import CameraPane

def _make_demo_pane():
    def render(ctx, self):
        ctx.overlay.card("Demo", "Functional pane via wrapper")
        ctx.overlay.text("Say: 'open wifi' or 'open launcher'", 12, 120, size=18)
    def on_voice(ctx, self, text: str):
        t = (text or "").strip().lower()
        if t.startswith("open "):
            ctx.event_bus.emit("NAVIGATE", pane_id=t.split("open ",1)[1].strip())
        else:
            ctx.notify.info(f"heard: {t}")
    return make_functional_pane("demo","Demo","icons/icon-demo.png",render,on_voice)

def run():
    # Pi-friendly profile
    config = {
        "display": {"width": 800, "height": 480, "fps": 30},
        "default_pane": "launcher",
        "enabled_panes": ["launcher","wifi","settings","camera","demo"],
        "assets_dir": "VA-Assets",
        "features": {"background_removal": False, "background_mode": "black"},
        "voice_hotword": "hey vision",
    }
    ctx = make_services()

    demo_cls = _make_demo_pane()
    panes: dict[str, Pane] = {
        "launcher": LauncherPane(ctx),
        "wifi":     WiFiPane(ctx),
        "settings": SettingsPane(ctx),
        "camera":   CameraPane(ctx),
        "demo":     demo_cls(ctx),
    }

    current = panes[config.get("default_pane","launcher")]
    current.mount(ctx)
    last = time.perf_counter()

    try:
        while True:
            now = time.perf_counter(); dt = now - last; last = now
            for evt in list(ctx.event_bus.poll()):
                if evt["type"] == "NAVIGATE":
                    pid = evt.get("pane_id")
                    if pid in panes and panes[pid] is not current:
                        current.unmount(); current = panes[pid]; current.mount(ctx)
                elif evt["type"] == "VOICE":
                    current.on_voice(evt.get("text",""))

            ctx.overlay.begin_frame()
            current.render()
            ctx.overlay.end_frame()

            fps = max(10, int(ctx.display.fps))
            time.sleep(max(0.0, (1/fps) - (time.perf_counter() - now)))
    except KeyboardInterrupt:
        pass
    finally:
        try: current.unmount()
        except: pass
        ctx.shutdown()

if __name__ == "__main__":
    run()
