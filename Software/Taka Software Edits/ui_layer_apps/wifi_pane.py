# Software/Taka Software Edits/ui_layer_apps/wifi_pane.py
# =============================================================================
# WiFi PANE (MVP)
# -----------------------------------------------------------------------------
# WHAT THIS DOES
#   - Lists available Wi-Fi networks (Linux/Raspberry Pi: via `nmcli` if present)
#   - Lets you attempt a connection with a stored SSID/PASSWORD (demo flow)
#   - Shows current connection status from ctx.store["wifi_connected"]
#
# DEV NOTES
#   - On Windows dev machines without nmcli, this pane runs in "simulated mode":
#       - SCAN shows fake SSIDs
#       - CONNECT toggles status in ctx.store
#   - On Raspberry Pi OS / Debian, install NetworkManager (nmcli) for real ops:
#       sudo apt update && sudo apt install network-manager -y
#   - Keep UI minimal for smart glasses (text + toasts).
# =============================================================================

from __future__ import annotations
import os
import subprocess
from typing import Any, List, Tuple

from ..main_ui_layer.pane_base import Pane  # import by relative path is fine when registry imports by path

def _has_nmcli() -> bool:
    """Detect nmcli (Linux/NetworkManager)."""
    try:
        subprocess.run(["nmcli", "-v"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return True
    except Exception:
        return False

def _scan_nmcli() -> List[Tuple[str, int]]:
    """
    Return list of (SSID, SIGNAL) using nmcli.
    SIGNAL is 0..100. Hidden SSIDs are filtered out.
    """
    out = subprocess.run(
        ["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True
    ).stdout.strip()
    networks = []
    for line in out.splitlines():
        try:
            ssid, sig = line.split(":")
            ssid = ssid.strip()
            if not ssid:  # skip hidden
                continue
            sig = int(sig or "0")
            networks.append((ssid, sig))
        except Exception:
            continue
    # sort by signal desc
    networks.sort(key=lambda x: x[1], reverse=True)
    return networks

def _connect_nmcli(ssid: str, password: str) -> Tuple[bool, str]:
    """
    Attempt to connect to SSID with PASSWORD using nmcli.
    Returns (ok, message).
    """
    try:
        # save a connection profile; NM may prompt; we capture output
        cmd = ["nmcli", "d", "wifi", "connect", ssid, "password", password]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode == 0:
            return True, res.stdout.strip() or "Connected."
        else:
            return False, res.stderr.strip() or "Failed to connect."
    except Exception as e:
        return False, f"Error: {e}"

class WiFiPane(Pane):
    id = "wifi"
    title = "Wi-Fi"
    icon = "icons/icon-wifi.png"

    def on_mount(self) -> None:
        """
        Initialize pane state. Keep it tiny—this is wearable UI.
        """
        self.networks: List[Tuple[str, int]] = []  # list of (ssid, signal)
        self.simulated = not _has_nmcli()
        if self.simulated:
            self.ctx.notify.info("Wi-Fi (simulated): nmcli not found")
        else:
            self.ctx.notify.info("Wi-Fi ready")
        # Demo creds you can replace later or prompt by voice
        self._last_ssid = ""
        self._last_password = ""

    def render(self) -> None:
        """
        Minimal text-driven UI. We rely on voice or dev keys to trigger actions.
        """
        self.ctx.overlay.card(self.title, "Say 'scan networks' or 'connect to <ssid>'")
        # show up to 5 networks
        y = 80
        shown = 0
        for ssid, sig in self.networks[:5]:
            self.ctx.overlay.text(f"{ssid}  ({sig}%)", 12, y, size=16)
            y += 22
            shown += 1
        if shown == 0:
            self.ctx.overlay.text("No networks yet. Say 'scan networks'.", 12, y, size=16)

        # status
        status = "Connected" if self.ctx.store.get("wifi_connected") else "Disconnected"
        self.ctx.overlay.text(f"Status: {status}", 12, y + 28, size=16)

    def on_voice(self, text: str) -> None:
        """
        Very simple intent parsing for MVP:
          - "scan networks"
          - "connect to <ssid>"
          - "disconnect wifi"
        For protected networks, set password first by:
          - "password is <your password>"
        """
        t = (text or "").strip().lower()

        if "scan" in t:
            self._do_scan()
            return

        if t.startswith("password is "):
            self._last_password = text.split("password is ", 1)[1].strip()
            self.ctx.overlay.toast("Password stored")
            return

        if t.startswith("connect to "):
            ssid = text.split("connect to ", 1)[1].strip()
            self._last_ssid = ssid
            self._do_connect(ssid, self._last_password)
            return

        if "disconnect" in t:
            self._do_disconnect()
            return

    # --------------------- actions ---------------------

    def _do_scan(self) -> None:
        if self.simulated:
            # fake data for dev machines
            self.networks = [("CampusWiFi", 82), ("Lab-5G", 68), ("Guest", 40)]
            self.ctx.overlay.toast("Scanned (simulated)")
        else:
            nets = _scan_nmcli()
            self.networks = nets
            self.ctx.overlay.toast(f"Found {len(nets)} networks")

    def _do_connect(self, ssid: str, password: str) -> None:
        if not ssid:
            self.ctx.overlay.toast("No SSID provided")
            return

        if self.simulated:
            self.ctx.store["wifi_connected"] = True
            self.ctx.overlay.toast(f"Connected to {ssid} (simulated)")
            return

        ok, msg = _connect_nmcli(ssid, password)
        self.ctx.store["wifi_connected"] = bool(ok)
        self.ctx.overlay.toast(msg)

    def _do_disconnect(self) -> None:
        if self.simulated:
            self.ctx.store["wifi_connected"] = False
            self.ctx.overlay.toast("Disconnected (simulated)")
            return
        # With nmcli we can deactivate the active connection:
        try:
            subprocess.run(["nmcli", "con", "down", "id", self._last_ssid],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.ctx.store["wifi_connected"] = False
            self.ctx.overlay.toast("Disconnected")
        except Exception as e:
            self.ctx.overlay.toast(f"Error: {e}")
