"""Rectangle selection overlay that fullscreens across the virtual (multi-monitor) screen.

GTK4's ``fullscreen_on_monitor`` is deprecated and ignored by xfwm4, so
instead we set the EWMH ``_NET_WM_FULLSCREEN_MONITORS`` property via raw
Xlib, then request fullscreen. xfwm4 reads that property and extends the
fullscreen across the specified RANDR monitor range, which gives us a
single input area spanning every physical display.
"""

from __future__ import annotations

from typing import Callable, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkX11", "4.0")

from gi.repository import Gdk, GdkPixbuf, GdkX11, Gtk  # noqa: E402
import cairo  # noqa: E402


def _virtual_bounds_and_fs_range() -> Tuple[int, int, int, int, Tuple[int, int, int, int]]:
    """Compute (x, y, w, h, (top, bottom, left, right)) for the virtual screen.

    ``top/bottom/left/right`` are monitor indices (matching GDK ordering,
    which under X11 maps to RANDR output ordering) for use in the
    ``_NET_WM_FULLSCREEN_MONITORS`` property.
    """
    monitors = Gdk.Display.get_default().get_monitors()
    n = monitors.get_n_items()
    rects = []
    for i in range(n):
        g = monitors.get_item(i).get_geometry()
        rects.append((i, g.x, g.y, g.x + g.width, g.y + g.height))
    if not rects:
        return 0, 0, 1920, 1080, (0, 0, 0, 0)
    vx = min(r[1] for r in rects)
    vy = min(r[2] for r in rects)
    vw = max(r[3] for r in rects) - vx
    vh = max(r[4] for r in rects) - vy
    top = min(rects, key=lambda r: r[2])[0]
    bottom = max(rects, key=lambda r: r[4])[0]
    left = min(rects, key=lambda r: r[1])[0]
    right = max(rects, key=lambda r: r[3])[0]
    return vx, vy, vw, vh, (top, bottom, left, right)


def _xlib_set_fs_monitors(xid: int, top: int, bottom: int, left: int, right: int) -> None:
    """Set ``_NET_WM_FULLSCREEN_MONITORS`` so the WM extends fullscreen across monitors."""
    from Xlib import X, Xatom, display
    d = display.Display()
    try:
        atom = d.intern_atom("_NET_WM_FULLSCREEN_MONITORS")
        win = d.create_resource_object("window", xid)
        win.change_property(
            atom, Xatom.CARDINAL, 32,
            [int(top), int(bottom), int(left), int(right)],
            mode=X.PropModeReplace,
        )
        d.sync()
    finally:
        d.close()


class RectangleSelectionOverlay(Gtk.Window):
    """Virtual-screen-spanning overlay with a drag-to-select rectangle."""

    def __init__(
        self,
        capture_service,
        on_selected: Callable[[int, int, int, int], None],
        on_cancelled: Callable[[], None],
        pre_captured=None,
        **_legacy_kwargs,
    ):
        super().__init__(title="", decorated=False, modal=True)
        self._capture_service = capture_service
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled

        self._is_selecting = False
        self._start_x = 0.0
        self._start_y = 0.0
        self._current_x = 0.0
        self._current_y = 0.0

        vx, vy, vw, vh, fs_range = _virtual_bounds_and_fs_range()
        self._origin_x, self._origin_y = vx, vy
        self._fs_range = fs_range

        self._desktop_pixbuf = (
            pre_captured if pre_captured is not None
            else self._capture_service.capture_fullscreen()
        )
        self._screen_w = self._desktop_pixbuf.get_width()
        self._screen_h = self._desktop_pixbuf.get_height()

        self.set_default_size(self._screen_w, self._screen_h)
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))

        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_draw_func(self._on_draw)
        self.set_child(self._drawing_area)

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

        # Set the fullscreen-monitors property BEFORE requesting fullscreen,
        # so the WM extends across all monitors instead of picking one.
        self.connect("map", self._on_mapped)

    def _on_mapped(self, _widget) -> None:
        surface = self.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return
        try:
            xid = surface.get_xid()
            _xlib_set_fs_monitors(xid, *self._fs_range)
        except Exception as e:
            print(f"[snipr-debug] fs-monitors failed: {e}", flush=True)
        # Request fullscreen; the WM reads the property above and spans
        # across every monitor in the range.
        self.fullscreen()

    def _pixbuf_to_surface(self, pixbuf: GdkPixbuf.Pixbuf) -> cairo.ImageSurface:
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    def _on_draw(self, area, ctx: cairo.Context, width: int, height: int):
        ctx.set_source_surface(self._desktop_surface, 0, 0)
        ctx.paint()
        ctx.set_source_rgba(0, 0, 0, 0.4)

        if self._is_selecting:
            sx, sy, sw, sh = self._get_selection_rect()
            if sw > 0 and sh > 0:
                ctx.rectangle(0, 0, width, height)
                ctx.rectangle(sx, sy, sw, sh)
                ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                ctx.fill()

                ctx.set_source_rgba(0.2, 0.5, 1.0, 0.9)
                ctx.set_line_width(2)
                ctx.rectangle(sx, sy, sw, sh)
                ctx.stroke()

                label = f"{int(sw)} x {int(sh)}"
                ctx.set_source_rgba(1, 1, 1, 0.9)
                ctx.set_font_size(14)
                extents = ctx.text_extents(label)
                lx = sx + (sw - extents.width) / 2
                ly = sy - 8 if sy > 25 else sy + sh + 20
                ctx.move_to(lx, ly)
                ctx.show_text(label)
                return

        ctx.rectangle(0, 0, width, height)
        ctx.fill()
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
        self._on_selected(
            int(sx + self._origin_x),
            int(sy + self._origin_y),
            int(sw),
            int(sh),
        )

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
