"""Sidecar process that holds a global hotkey and fires a Snipr capture.

Runs under GTK3 + libkeybinder3. We can't load Keybinder (GTK3) inside
the main Snipr process (GTK4) — the GDK types collide — so we spawn
this helper and talk back via `gapplication action`.

Usage: python3 -m snipr._hotkey_daemon <accelerator>
"""

from __future__ import annotations

import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Keybinder", "3.0")
from gi.repository import GLib, Gtk, Keybinder  # noqa: E402


APP_ID = "com.snipr.Snipr"
ACTION = "new-capture"


def _trigger(_keystring=None, _user_data=None):
    try:
        subprocess.Popen(
            ["gapplication", "action", APP_ID, ACTION],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: _hotkey_daemon <accelerator>", file=sys.stderr)
        return 2
    accel = sys.argv[1].strip()
    Keybinder.init()
    if not Keybinder.bind(accel, _trigger):
        print(f"keybinder: bind failed for {accel!r}", file=sys.stderr)
        return 3
    # Shut down cleanly on SIGTERM/SIGINT so the parent can restart us.
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, 15, Gtk.main_quit)  # SIGTERM
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, 2, Gtk.main_quit)   # SIGINT
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
