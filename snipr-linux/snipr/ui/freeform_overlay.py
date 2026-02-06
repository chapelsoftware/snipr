"""Fullscreen freeform selection overlay with Cairo drawing."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GdkPixbuf, Gtk
import cairo


class FreeformSelectionOverlay(Gtk.Window):
    """Fullscreen overlay for drawing a freeform selection polygon.

    Shows the desktop screenshot and lets the user draw a freeform shape.
    The enclosed region is captured with transparency outside the shape.
    """

    def __init__(
        self,
        capture_service,
        on_selected: Callable[[int, int, int, int, list[tuple[int, int]]], None],
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

        self._is_drawing = False
        self._points: list[tuple[float, float]] = []

        # Capture desktop
        self._desktop_pixbuf = self._capture_service.capture_fullscreen()

        self.fullscreen()
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))

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

        if len(self._points) >= 3:
            # Draw dim with hole for freeform shape
            ctx.rectangle(0, 0, width, height)
            ctx.new_sub_path()
            ctx.move_to(*self._points[0])
            for px, py in self._points[1:]:
                ctx.line_to(px, py)
            ctx.close_path()
            ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.fill()

            # Draw the freeform path outline
            ctx.set_source_rgba(0.2, 0.5, 1.0, 0.9)
            ctx.set_line_width(2)
            ctx.move_to(*self._points[0])
            for px, py in self._points[1:]:
                ctx.line_to(px, py)
            if not self._is_drawing:
                ctx.close_path()
            ctx.stroke()
        elif len(self._points) > 0:
            # Just the line so far
            ctx.rectangle(0, 0, width, height)
            ctx.fill()

            ctx.set_source_rgba(0.2, 0.5, 1.0, 0.9)
            ctx.set_line_width(2)
            ctx.move_to(*self._points[0])
            for px, py in self._points[1:]:
                ctx.line_to(px, py)
            ctx.stroke()
        else:
            # Full dim with instructions
            ctx.rectangle(0, 0, width, height)
            ctx.fill()

            ctx.set_source_rgba(1, 1, 1, 0.8)
            ctx.set_font_size(18)
            text = "Click and drag to draw a freeform selection. Press Escape to cancel."
            extents = ctx.text_extents(text)
            ctx.move_to((width - extents.width) / 2, height / 2)
            ctx.show_text(text)

    def _on_press(self, gesture, n_press, x, y):
        self._is_drawing = True
        self._points = [(x, y)]

    def _on_motion(self, controller, x, y):
        if self._is_drawing:
            self._points.append((x, y))
            self._drawing_area.queue_draw()

    def _on_release(self, gesture, n_press, x, y):
        if not self._is_drawing:
            return
        self._is_drawing = False
        self._points.append((x, y))

        if len(self._points) < 3:
            self._points.clear()
            self._drawing_area.queue_draw()
            return

        # Calculate bounding box
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        bx = int(min(xs))
        by = int(min(ys))
        bw = int(max(xs) - bx)
        bh = int(max(ys) - by)

        if bw < 5 or bh < 5:
            self._points.clear()
            self._drawing_area.queue_draw()
            return

        int_points = [(int(px), int(py)) for px, py in self._points]
        self.close()
        self._on_selected(bx, by, bw, bh, int_points)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            self._on_cancelled()
            return True
        return False
