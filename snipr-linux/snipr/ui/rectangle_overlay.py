"""Fullscreen rectangle selection overlay with Cairo drawing."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
import cairo


class RectangleSelectionOverlay(Gtk.Window):
    """Fullscreen overlay for selecting a rectangular screen region.

    Shows a frozen desktop screenshot as background, draws a semi-transparent
    dim overlay, and punches through the selected rectangle.
    """

    def __init__(
        self,
        capture_service,
        on_selected: Callable[[int, int, int, int], None],
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

        self._is_selecting = False
        self._start_x = 0.0
        self._start_y = 0.0
        self._current_x = 0.0
        self._current_y = 0.0

        # Capture desktop BEFORE showing overlay
        self._desktop_pixbuf = self._capture_service.capture_fullscreen()
        self._screen_w = self._desktop_pixbuf.get_width()
        self._screen_h = self._desktop_pixbuf.get_height()

        self.fullscreen()
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))

        # Drawing area
        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_draw_func(self._on_draw)
        self.set_child(self._drawing_area)

        # Input controllers
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_press)
        click.connect("released", self._on_release)
        self._drawing_area.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self._drawing_area.add_controller(motion)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

        # Convert pixbuf to cairo surface for fast drawing
        self._desktop_surface = self._pixbuf_to_surface(self._desktop_pixbuf)

    def _pixbuf_to_surface(self, pixbuf: GdkPixbuf.Pixbuf) -> cairo.ImageSurface:
        """Convert a GdkPixbuf to a cairo ImageSurface."""
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    def _on_draw(self, area, ctx: cairo.Context, width: int, height: int):
        # Draw desktop screenshot
        ctx.set_source_surface(self._desktop_surface, 0, 0)
        ctx.paint()

        # Draw dim overlay
        ctx.set_source_rgba(0, 0, 0, 0.4)

        if self._is_selecting:
            # Punch a hole for the selection
            sx, sy, sw, sh = self._get_selection_rect()
            if sw > 0 and sh > 0:
                ctx.rectangle(0, 0, width, height)
                ctx.rectangle(sx, sy, sw, sh)
                ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                ctx.fill()

                # Draw selection border
                ctx.set_source_rgba(0.2, 0.5, 1.0, 0.9)
                ctx.set_line_width(2)
                ctx.rectangle(sx, sy, sw, sh)
                ctx.stroke()

                # Draw size label
                label = f"{int(sw)} x {int(sh)}"
                ctx.set_source_rgba(1, 1, 1, 0.9)
                ctx.set_font_size(14)
                extents = ctx.text_extents(label)
                lx = sx + (sw - extents.width) / 2
                ly = sy - 8 if sy > 25 else sy + sh + 20
                ctx.move_to(lx, ly)
                ctx.show_text(label)
                return

        # No selection - full dim
        ctx.rectangle(0, 0, width, height)
        ctx.fill()

        # Draw instruction text
        ctx.set_source_rgba(1, 1, 1, 0.8)
        ctx.set_font_size(18)
        text = "Click and drag to select a region. Press Escape to cancel."
        extents = ctx.text_extents(text)
        ctx.move_to((width - extents.width) / 2, height / 2)
        ctx.show_text(text)

    def _on_press(self, gesture, n_press, x, y):
        self._is_selecting = True
        self._start_x = x
        self._start_y = y
        self._current_x = x
        self._current_y = y

    def _on_motion(self, controller, x, y):
        if self._is_selecting:
            self._current_x = x
            self._current_y = y
            self._drawing_area.queue_draw()

    def _on_release(self, gesture, n_press, x, y):
        if not self._is_selecting:
            return
        self._is_selecting = False
        self._current_x = x
        self._current_y = y

        sx, sy, sw, sh = self._get_selection_rect()
        if sw < 5 or sh < 5:
            self._drawing_area.queue_draw()
            return

        self.close()
        self._on_selected(int(sx), int(sy), int(sw), int(sh))

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            self._on_cancelled()
            return True
        return False

    def _get_selection_rect(self) -> tuple[float, float, float, float]:
        x = min(self._start_x, self._current_x)
        y = min(self._start_y, self._current_y)
        w = abs(self._current_x - self._start_x)
        h = abs(self._current_y - self._start_y)
        return x, y, w, h
