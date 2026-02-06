"""X11 window enumeration service using python-xlib."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowInfo:
    window_id: int
    title: str
    x: int
    y: int
    width: int
    height: int


class WindowEnumerationService:
    """Enumerate visible windows on X11 via _NET_CLIENT_LIST."""

    def get_windows(self) -> list[WindowInfo]:
        try:
            return self._get_windows_xlib()
        except Exception:
            return []

    def _get_windows_xlib(self) -> list[WindowInfo]:
        from Xlib import X, display as xdisplay

        d = xdisplay.Display()
        root = d.screen().root

        # Get _NET_CLIENT_LIST
        net_client_list = d.intern_atom("_NET_CLIENT_LIST")
        net_wm_name = d.intern_atom("_NET_WM_NAME")
        utf8_string = d.intern_atom("UTF8_STRING")
        net_frame = d.intern_atom("_NET_FRAME_EXTENTS")

        prop = root.get_full_property(net_client_list, X.AnyPropertyType)
        if prop is None:
            d.close()
            return []

        window_ids = prop.value
        windows = []

        for wid in window_ids:
            try:
                win = d.create_resource_object("window", wid)
                geom = win.get_geometry()

                # Walk parent chain to get absolute position —
                # translate_coords is unreliable on composited desktops
                abs_x, abs_y = 0, 0
                w = win
                while True:
                    g = w.get_geometry()
                    abs_x += g.x
                    abs_y += g.y
                    parent = w.query_tree().parent
                    if parent.id == root.id or parent.id == 0:
                        break
                    w = parent

                # Get window title
                title = ""
                name_prop = win.get_full_property(net_wm_name, utf8_string)
                if name_prop and name_prop.value:
                    val = name_prop.value
                    title = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)
                if not title:
                    wm_name = win.get_wm_name()
                    if wm_name:
                        title = wm_name.decode("utf-8", errors="replace") if isinstance(wm_name, bytes) else str(wm_name)

                if not title:
                    continue

                # Get frame extents for accurate geometry
                frame_prop = win.get_full_property(net_frame, X.AnyPropertyType)
                left = top = right = bottom = 0
                if frame_prop and len(frame_prop.value) >= 4:
                    left, right, top, bottom = frame_prop.value[:4]

                x = abs_x - left
                y = abs_y - top
                width = geom.width + left + right
                height = geom.height + top + bottom

                if width > 1 and height > 1:
                    windows.append(WindowInfo(
                        window_id=wid,
                        title=title,
                        x=x, y=y,
                        width=width, height=height,
                    ))
            except Exception:
                continue

        d.close()
        return windows

    def get_window_at_position(self, x: int, y: int) -> WindowInfo | None:
        """Get the topmost window at the given screen coordinates."""
        windows = self.get_windows()
        # Iterate in reverse to get topmost window first
        for win in reversed(windows):
            if (win.x <= x <= win.x + win.width and
                    win.y <= y <= win.y + win.height):
                return win
        return None
