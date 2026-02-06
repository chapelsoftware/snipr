"""Factory that dispatches to the appropriate screen capture backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from snipr.services.display_server import DisplayServer, get_display_server

if TYPE_CHECKING:
    from snipr.services.screen_capture_portal import PortalScreenCapture
    from snipr.services.screen_capture_x11 import X11ScreenCapture


def create_screen_capture_service() -> X11ScreenCapture | PortalScreenCapture:
    """Create the appropriate screen capture service for the current display server."""
    server = get_display_server()

    if server == DisplayServer.WAYLAND:
        from snipr.services.screen_capture_portal import PortalScreenCapture
        return PortalScreenCapture()
    else:
        from snipr.services.screen_capture_x11 import X11ScreenCapture
        return X11ScreenCapture()
