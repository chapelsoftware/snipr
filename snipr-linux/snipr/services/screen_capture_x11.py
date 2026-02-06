"""X11 screen capture using python-xlib and Pillow."""

from __future__ import annotations

import io

import gi

gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf
from PIL import Image


class X11ScreenCapture:
    """Screen capture backend for X11 using python-xlib."""

    def __init__(self):
        from Xlib import display as xdisplay
        self._display = xdisplay.Display()
        self._root = self._display.screen().root

    def capture_fullscreen(self) -> GdkPixbuf.Pixbuf:
        """Capture the entire screen."""
        geom = self._root.get_geometry()
        return self.capture_region(0, 0, geom.width, geom.height)

    def capture_region(self, x: int, y: int, width: int, height: int) -> GdkPixbuf.Pixbuf:
        """Capture a rectangular region of the screen."""
        raw = self._root.get_image(x, y, width, height, 2, 0xFFFFFFFF)  # ZPixmap
        image = Image.frombytes("RGBX", (width, height), raw.data, "raw", "BGRX")
        image = image.convert("RGB")
        return self._pil_to_pixbuf(image)

    def capture_window(self, window_id: int) -> GdkPixbuf.Pixbuf:
        """Capture a specific window by its X11 window ID."""
        win = self._display.create_resource_object("window", window_id)
        geom = win.get_geometry()
        # Translate to root coords
        coords = win.translate_coords(self._root, 0, 0)
        return self.capture_region(coords.x, coords.y, geom.width, geom.height)

    def capture_freeform(self, x: int, y: int, width: int, height: int,
                         points: list[tuple[int, int]]) -> GdkPixbuf.Pixbuf:
        """Capture a freeform region defined by polygon points."""
        raw = self._root.get_image(x, y, width, height, 2, 0xFFFFFFFF)
        image = Image.frombytes("RGBX", (width, height), raw.data, "raw", "BGRX")
        image = image.convert("RGBA")

        # Create polygon mask
        from PIL import ImageDraw
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        # Translate points to local coordinates
        local_points = [(px - x, py - y) for px, py in points]
        if len(local_points) >= 3:
            draw.polygon(local_points, fill=255)
        image.putalpha(mask)

        return self._pil_to_pixbuf(image)

    def capture_desktop_image(self) -> Image.Image:
        """Capture desktop as a PIL Image (for overlay backgrounds)."""
        geom = self._root.get_geometry()
        raw = self._root.get_image(0, 0, geom.width, geom.height, 2, 0xFFFFFFFF)
        image = Image.frombytes("RGBX", (geom.width, geom.height), raw.data, "raw", "BGRX")
        return image.convert("RGB")

    def get_screen_size(self) -> tuple[int, int]:
        """Get the root window size."""
        geom = self._root.get_geometry()
        return geom.width, geom.height

    @staticmethod
    def _pil_to_pixbuf(image: Image.Image) -> GdkPixbuf.Pixbuf:
        """Convert a PIL Image to a GdkPixbuf.Pixbuf."""
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(buf.read())
        loader.close()
        return loader.get_pixbuf()

    def close(self) -> None:
        self._display.close()
