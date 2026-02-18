# Software/Taka Software Edits/main_ui_layer/pane_wrappers.py
from __future__ import annotations
import types
from typing import Callable, Optional
from .pane_base import Pane

RenderFn = Callable[["Ctx", "Pane"], None]
VoiceFn = Callable[["Ctx", "Pane", str], None]
MountFn = Callable[["Ctx", "Pane"], None]
UnmountFn = Callable[["Ctx", "Pane"], None]

def make_functional_pane(
    pane_id: str,
    title: str,
    icon: str | None,
    render_fn: RenderFn,
    on_voice_fn: Optional[VoiceFn] = None,
    on_mount_fn: Optional[MountFn] = None,
    on_unmount_fn: Optional[UnmountFn] = None,
):
    """Wrap simple functions into a concrete Pane subclass (for quick prototypes)."""
    assert pane_id and title, "pane_id and title are required"
    attrs = {"id": pane_id, "title": title, "icon": icon or ""}

    def _on_mount(self):
        if on_mount_fn: on_mount_fn(self.ctx, self)
    def _on_unmount(self):
        if on_unmount_fn: on_unmount_fn(self.ctx, self)
    def _render(self):
        render_fn(self.ctx, self)
    def _on_voice(self, text: str):
        if on_voice_fn: on_voice_fn(self.ctx, self, text or "")

    attrs.update({
        "on_mount": _on_mount,
        "on_unmount": _on_unmount,
        "render": _render,
        "on_voice": _on_voice,
    })

    cls_name = f"FunctionalPane_{pane_id.capitalize()}"
    return types.new_class(cls_name, (Pane,), {}, lambda ns: ns.update(attrs))
