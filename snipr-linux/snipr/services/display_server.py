from enum import Enum
import os


class DisplayServer(Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


def get_display_server() -> DisplayServer:
    """Detect the active display server at runtime."""
    # Check XDG_SESSION_TYPE first (most reliable)
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type == "wayland":
        return DisplayServer.WAYLAND
    if session_type == "x11":
        return DisplayServer.X11

    # Check GDK_BACKEND override
    gdk_backend = os.environ.get("GDK_BACKEND", "").lower()
    if gdk_backend == "wayland":
        return DisplayServer.WAYLAND
    if gdk_backend == "x11":
        return DisplayServer.X11

    # Check WAYLAND_DISPLAY
    if os.environ.get("WAYLAND_DISPLAY"):
        return DisplayServer.WAYLAND

    # Check DISPLAY (X11)
    if os.environ.get("DISPLAY"):
        return DisplayServer.X11

    return DisplayServer.UNKNOWN
