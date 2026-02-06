"""Floating recording indicator window."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk


class RecordingIndicator(Gtk.Window):
    """Small floating window that shows recording status and duration."""

    def __init__(self, on_stop: Callable[[], None]):
        super().__init__(
            title="Recording",
            decorated=False,
            resizable=False,
            default_width=220,
            default_height=48,
        )

        self._on_stop = on_stop

        # Position at top-center of screen
        # GTK4 doesn't allow arbitrary positioning on Wayland,
        # but on X11 we can use set_default_size and gravity hints
        self.add_css_class("recording-indicator")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Recording dot
        dot = Gtk.Label(label="\u25CF")  # filled circle
        dot.add_css_class("recording-dot")
        box.append(dot)

        # REC label
        rec_label = Gtk.Label(label="REC")
        rec_label.set_markup("<b>REC</b>")
        box.append(rec_label)

        # Duration
        self._duration_label = Gtk.Label(label="00:00")
        self._duration_label.add_css_class("recording-duration")
        box.append(self._duration_label)

        # Stop button
        stop_btn = Gtk.Button(label="Stop")
        stop_btn.add_css_class("destructive-action")
        stop_btn.connect("clicked", self._on_stop_clicked)
        box.append(stop_btn)

        self.set_child(box)

        # Escape to cancel
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

    def update_duration(self, seconds: float):
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        self._duration_label.set_text(f"{mins:02d}:{secs:02d}")

    def _on_stop_clicked(self, btn):
        self._on_stop()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self._on_stop()
            return True
        return False
