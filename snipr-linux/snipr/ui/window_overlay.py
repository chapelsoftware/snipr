"""Fullscreen window selection overlay (X11 only)."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GdkPixbuf, Gtk
import cairo

from snipr.services.window_enum import WindowEnumerationService, WindowInfo


class WindowSelectionOverlay(Gtk.Window):
    """Fullscreen overlay for selecting a window.

    Shows the desktop screenshot with window highlights as the cursor
    moves over different windows.
    """

    def __init__(
        self,
        capture_service,
        on_selected: Callable[[WindowInfo], None],
        on_cancelled: Callable[[], None],
    ):
        super().__init__(
            title="",
            decorated=False,
            modal=True,
        )
        self._capture_service = capture_service
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled

        self._window_enum = WindowEnumerationService()
        self._windows = self._window_enum.get_windows()
        self._hovered_window: WindowInfo | None = None

        # Capture desktop
        self._desktop_pixbuf = self._capture_service.capture_fullscreen()

        self.fullscreen()
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))

        # Drawing area
        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_draw_func(self._on_draw)
        self.set_child(self._drawing_area)

        # Input controllers
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self._drawing_area.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self._drawing_area.add_controller(motion)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

        self._desktop_surface = self._pixbuf_to_surface(self._desktop_pixbuf)

    def _pixbuf_to_surface(self, pixbuf: GdkPixbuf.Pixbuf) -> cairo.ImageSurface:
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    def _on_draw(self, area, ctx: cairo.Context, width: int, height: int):
        # Draw desktop
        ctx.set_source_surface(self._desktop_surface, 0, 0)
        ctx.paint()

        # Dim overlay
        ctx.set_source_rgba(0, 0, 0, 0.4)

        if self._hovered_window:
            win = self._hovered_window
            # Punch hole for hovered window
            ctx.rectangle(0, 0, width, height)
            ctx.rectangle(win.x, win.y, win.width, win.height)
            ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.fill()

            # Highlight border
            ctx.set_source_rgba(0.2, 0.5, 1.0, 0.9)
            ctx.set_line_width(3)
            ctx.rectangle(win.x, win.y, win.width, win.height)
            ctx.stroke()

            # Window title label
            title = win.title[:60] + "..." if len(win.title) > 60 else win.title
            ctx.set_source_rgba(1, 1, 1, 0.9)
            ctx.set_font_size(14)
            extents = ctx.text_extents(title)
            lx = win.x + (win.width - extents.width) / 2
            ly = win.y - 8 if win.y > 25 else win.y + win.height + 20
            lx = max(4, min(lx, width - extents.width - 4))
            ctx.move_to(lx, ly)
            ctx.show_text(title)
        else:
            ctx.rectangle(0, 0, width, height)
            ctx.fill()

            ctx.set_source_rgba(1, 1, 1, 0.8)
            ctx.set_font_size(18)
            text = "Click on a window to select it. Press Escape to cancel."
            extents = ctx.text_extents(text)
            ctx.move_to((width - extents.width) / 2, height / 2)
            ctx.show_text(text)

    def _on_motion(self, controller, x, y):
        # Find window under cursor
        prev = self._hovered_window
        self._hovered_window = None
        for win in reversed(self._windows):
            if (win.x <= x <= win.x + win.width and
                    win.y <= y <= win.y + win.height):
                self._hovered_window = win
                break
        if self._hovered_window != prev:
            self._drawing_area.queue_draw()

    def _on_click(self, gesture, n_press, x, y):
        if self._hovered_window:
            self.close()
            self._on_selected(self._hovered_window)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            self._on_cancelled()
            return True
        return False
