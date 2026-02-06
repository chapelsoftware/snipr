"""Wayland screen capture using XDG Desktop Portal (D-Bus)."""

from __future__ import annotations

import io
import os
import random
from urllib.parse import urlparse, unquote

import gi

gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gio, GLib, GdkPixbuf
from PIL import Image

# Portal D-Bus constants
PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"


class PortalScreenCapture:
    """Screen capture backend using XDG Desktop Portal for Wayland."""

    def __init__(self):
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._sender = self._bus.get_unique_name().replace(".", "_").lstrip(":")

    def capture_fullscreen(self) -> GdkPixbuf.Pixbuf:
        """Capture fullscreen via portal (non-interactive)."""
        uri = self._screenshot(interactive=False)
        return self._load_uri(uri)

    def capture_region(self, x: int, y: int, width: int, height: int) -> GdkPixbuf.Pixbuf:
        """Capture fullscreen then crop to region."""
        uri = self._screenshot(interactive=False)
        pixbuf = self._load_uri(uri)
        return pixbuf.new_subpixbuf(x, y, width, height)

    def capture_window(self, **kwargs) -> GdkPixbuf.Pixbuf:
        """Capture via portal with interactive window picker."""
        uri = self._screenshot(interactive=True)
        return self._load_uri(uri)

    def capture_freeform(self, x: int, y: int, width: int, height: int,
                         points: list[tuple[int, int]]) -> GdkPixbuf.Pixbuf:
        """Capture fullscreen, then apply polygon mask."""
        uri = self._screenshot(interactive=False)
        pixbuf = self._load_uri(uri)

        # Convert to PIL for freeform masking
        buf = io.BytesIO()
        success, data = pixbuf.save_to_bufferv("png", [], [])
        buf.write(data)
        buf.seek(0)
        image = Image.open(buf).convert("RGBA")

        # Crop to bounding box
        cropped = image.crop((x, y, x + width, y + height))

        # Apply polygon mask
        from PIL import ImageDraw
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        local_points = [(px - x, py - y) for px, py in points]
        if len(local_points) >= 3:
            draw.polygon(local_points, fill=255)
        cropped.putalpha(mask)

        # Convert back to pixbuf
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        out.seek(0)
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(out.read())
        loader.close()
        return loader.get_pixbuf()

    def capture_desktop_image(self) -> Image.Image:
        """Capture desktop as PIL Image (for overlay backgrounds on Wayland)."""
        uri = self._screenshot(interactive=False)
        path = self._uri_to_path(uri)
        return Image.open(path).convert("RGB")

    def get_screen_size(self) -> tuple[int, int]:
        """Get screen size - use a portal screenshot and check dimensions."""
        try:
            uri = self._screenshot(interactive=False)
            pixbuf = self._load_uri(uri)
            return pixbuf.get_width(), pixbuf.get_height()
        except Exception:
            return 1920, 1080

    def _screenshot(self, interactive: bool) -> str:
        """Call the Screenshot portal and return the file URI."""
        token = f"snipr_{random.randint(1, 999999)}"
        request_path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{token}"

        loop = GLib.MainLoop()
        result_uri = [None]
        error = [None]

        def on_response(connection, sender, path, iface, signal, params):
            response, results = params.unpack()
            if response == 0 and "uri" in results:
                result_uri[0] = results["uri"]
            else:
                error[0] = f"Portal screenshot failed with response {response}"
            loop.quit()

        sub_id = self._bus.signal_subscribe(
            PORTAL_BUS, REQUEST_IFACE, "Response",
            request_path, None, Gio.DBusSignalFlags.NONE, on_response,
        )

        options = GLib.Variant("a{sv}", {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", interactive),
        })

        self._bus.call_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENSHOT_IFACE, "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE, 30000, None,
        )

        # Run loop with a timeout
        GLib.timeout_add(30000, lambda: (loop.quit(), False)[1])
        loop.run()

        self._bus.signal_unsubscribe(sub_id)

        if error[0]:
            raise RuntimeError(error[0])
        if result_uri[0] is None:
            raise RuntimeError("No URI returned from screenshot portal")

        return result_uri[0]

    def start_screencast(self) -> str:
        """Start a screencast session and return the PipeWire node ID."""
        token = f"snipr_{random.randint(1, 999999)}"
        session_token = f"snipr_session_{random.randint(1, 999999)}"

        # Create session
        session_options = GLib.Variant("a{sv}", {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", session_token),
        })

        result = self._bus.call_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, "CreateSession",
            GLib.Variant("(a{sv})", (session_options,)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE, 30000, None,
        )

        session_handle = result.unpack()[0]

        # Select sources (monitor)
        select_options = GLib.Variant("a{sv}", {
            "handle_token": GLib.Variant("s", f"snipr_{random.randint(1, 999999)}"),
            "types": GLib.Variant("u", 1),  # 1 = monitor
        })

        self._bus.call_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, "SelectSources",
            GLib.Variant("(oa{sv})", (session_handle, select_options)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE, 30000, None,
        )

        # Start
        loop = GLib.MainLoop()
        node_id = [None]

        start_token = f"snipr_{random.randint(1, 999999)}"
        start_request_path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{start_token}"

        def on_start_response(connection, sender, path, iface, signal, params):
            response, results = params.unpack()
            if response == 0 and "streams" in results:
                streams = results["streams"]
                if streams:
                    node_id[0] = str(streams[0][0])
            loop.quit()

        sub_id = self._bus.signal_subscribe(
            PORTAL_BUS, REQUEST_IFACE, "Response",
            start_request_path, None, Gio.DBusSignalFlags.NONE, on_start_response,
        )

        start_options = GLib.Variant("a{sv}", {
            "handle_token": GLib.Variant("s", start_token),
        })

        self._bus.call_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, "Start",
            GLib.Variant("(osa{sv})", (session_handle, "", start_options)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE, 30000, None,
        )

        GLib.timeout_add(30000, lambda: (loop.quit(), False)[1])
        loop.run()

        self._bus.signal_unsubscribe(sub_id)

        if node_id[0] is None:
            raise RuntimeError("Failed to get PipeWire node from screencast portal")

        return node_id[0]

    @staticmethod
    def _uri_to_path(uri: str) -> str:
        parsed = urlparse(uri)
        return unquote(parsed.path)

    def _load_uri(self, uri: str) -> GdkPixbuf.Pixbuf:
        path = self._uri_to_path(uri)
        return GdkPixbuf.Pixbuf.new_from_file(path)

    def close(self) -> None:
        pass
