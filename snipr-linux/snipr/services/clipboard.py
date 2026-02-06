"""Clipboard service using GTK4's Gdk.Clipboard (works on both X11 and Wayland)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gio, Gtk


class ClipboardService:
    def copy_image(self, pixbuf: GdkPixbuf.Pixbuf, window: Gtk.Window) -> None:
        """Copy a pixbuf image to the system clipboard."""
        clipboard = window.get_display().get_clipboard()
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        content = Gdk.ContentProvider.new_for_value(texture)
        clipboard.set_content(content)

    def copy_file_path(self, path: str, window: Gtk.Window) -> None:
        """Copy a file path to the system clipboard."""
        clipboard = window.get_display().get_clipboard()
        content = Gdk.ContentProvider.new_for_value(path)
        clipboard.set_content(content)

    @staticmethod
    def save_pixbuf(pixbuf: GdkPixbuf.Pixbuf, path: str) -> bool:
        """Save a pixbuf to a file. Format is inferred from extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "png"
        fmt_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "bmp": "bmp", "gif": "gif"}
        fmt = fmt_map.get(ext, "png")
        try:
            pixbuf.savev(path, fmt, [], [])
            return True
        except Exception:
            return False
