"""Main application window with toolbar and preview."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk
import cairo

from snipr.models.capture_mode import CaptureMode
from snipr.models.capture_result import CaptureResult
from snipr.models.recording_state import RecordingState


def _dismiss_active_popup() -> None:
    """Send a synthetic Escape so any popup/menu holding a pointer grab closes.

    Called right after we've captured — the popup is already baked into the
    captured pixels, so dismissing the live window is lossless and lets
    Snipr's preview receive clicks without the dropdown's grab swallowing
    the first one.
    """
    try:
        from Xlib import X, XK, display
        from Xlib.ext import xtest
    except Exception:
        return
    try:
        d = display.Display()
    except Exception:
        return
    try:
        code = d.keysym_to_keycode(XK.XK_Escape)
        xtest.fake_input(d, X.KeyPress, code)
        d.sync()
        xtest.fake_input(d, X.KeyRelease, code)
        d.sync()
    except Exception:
        pass
    finally:
        try:
            d.close()
        except Exception:
            pass


def _crop_pixbuf(pb, x: int, y: int, w: int, h: int):
    """Crop a frozen desktop pixbuf, with coords in root (whole-desktop) space.

    The overlay snapshotted the screen before showing itself, so the
    snapshot captures transient UI (dropdowns, menus) that would close
    the moment focus leaves. Re-capturing live misses them.
    """
    if pb is None:
        return None
    sw, sh = pb.get_width(), pb.get_height()
    cx = max(0, min(x, sw))
    cy = max(0, min(y, sh))
    cw = max(0, min(w, sw - cx))
    ch = max(0, min(h, sh - cy))
    if cw <= 0 or ch <= 0:
        return None
    return pb.new_subpixbuf(cx, cy, cw, ch).copy()


def _mask_pixbuf(pb, x: int, y: int, w: int, h: int,
                 points: list[tuple[int, int]]):
    """Crop + polygon-mask a frozen pixbuf (freeform mode); coords in root space."""
    cropped = _crop_pixbuf(pb, x, y, w, h)
    if cropped is None or len(points) < 3:
        return cropped
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return cropped
    cw, ch = cropped.get_width(), cropped.get_height()
    stride = cropped.get_rowstride()
    channels = cropped.get_n_channels()
    data = bytes(cropped.get_pixels())
    mode = "RGBA" if channels == 4 else "RGB"
    img = Image.frombytes(mode, (cw, ch), data, "raw", mode, stride).convert("RGBA")
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).polygon([(px - x, py - y) for px, py in points], fill=255)
    img.putalpha(mask)
    out = img.tobytes()
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(out),
        GdkPixbuf.Colorspace.RGB, True, 8,
        cw, ch, cw * 4,
    )


AVAILABLE_MODES = [
    CaptureMode.RECTANGLE_SNIP,
    CaptureMode.WINDOW_SNIP,
    CaptureMode.FULLSCREEN_SNIP,
    CaptureMode.FREEFORM_SNIP,
    CaptureMode.RECTANGLE_VIDEO,
    CaptureMode.WINDOW_VIDEO,
    CaptureMode.FULLSCREEN_VIDEO,
]

AVAILABLE_DELAYS = [0, 1, 2, 3, 4, 5]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(
            title="Snipr",
            default_width=450,
            resizable=False,
            **kwargs,
        )
        self.set_size_request(450, -1)

        self._app = self.get_application()
        self._selected_mode = CaptureMode.RECTANGLE_SNIP
        self._delay_seconds = 0
        self._last_result: CaptureResult | None = None
        self._is_preview_visible = False
        self._recording_indicator = None
        self._active_overlay = None
        self._video_saved = False

        # Connect video service callbacks
        vs = self._app.video_service
        vs.on_state_changed = self._on_recording_state_changed
        vs.on_duration_changed = self._on_recording_duration_changed
        vs.on_recording_completed = self._on_recording_completed
        vs.on_recording_failed = self._on_recording_failed

        self._build_ui()

    def _build_ui(self):
        # Adw.ToolbarView manages header bar + content for AdwApplicationWindow
        toolbar_view = Adw.ToolbarView()

        # Header bar (title + window controls + preferences menu)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Snipr"))

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text("Menu")
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)
        pref_action = Gio.SimpleAction.new("preferences", None)
        pref_action.connect("activate", self._on_preferences)
        self.add_action(pref_action)

        toolbar_view.add_top_bar(header)

        # Toast overlay wraps content
        self._toast_overlay = Adw.ToastOverlay()

        # Main vertical box for content below header
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(self._main_box)

        # Action toolbar with buttons
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_bar.set_margin_start(8)
        action_bar.set_margin_end(8)
        action_bar.set_margin_top(6)
        action_bar.set_margin_bottom(6)

        # New button
        self._new_btn = Gtk.Button(label="New")
        self._new_btn.add_css_class("suggested-action")
        self._new_btn.connect("clicked", self._on_new_clicked)
        action_bar.append(self._new_btn)

        # Mode dropdown
        mode_names = [m.display_name for m in AVAILABLE_MODES]
        self._mode_model = Gtk.StringList.new(mode_names)
        self._mode_dropdown = Gtk.DropDown(model=self._mode_model)
        self._mode_dropdown.set_selected(0)
        self._mode_dropdown.connect("notify::selected", self._on_mode_changed)
        self._mode_dropdown.add_css_class("mode-dropdown")
        action_bar.append(self._mode_dropdown)

        # Delay dropdown
        delay_names = [f"{d}s" if d > 0 else "0s" for d in AVAILABLE_DELAYS]
        self._delay_model = Gtk.StringList.new(delay_names)
        self._delay_dropdown = Gtk.DropDown(model=self._delay_model)
        self._delay_dropdown.set_selected(0)
        self._delay_dropdown.connect("notify::selected", self._on_delay_changed)
        action_bar.append(self._delay_dropdown)

        self._main_box.append(action_bar)

        toolbar_view.set_content(self._toast_overlay)
        self.set_content(toolbar_view)

        # Preview area (hidden by default)
        self._preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._preview_box.set_visible(False)

        # Scrolled window for image preview
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._scroll.set_hexpand(True)

        self._preview_picture = Gtk.Picture()
        self._preview_picture.set_can_shrink(True)
        self._preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._preview_picture.add_css_class("preview-image")

        # Overlay a transparent DrawingArea on top so the user can drag a
        # crop rectangle. Save/Copy consult self._crop_rect to decide what
        # gets exported.
        self._preview_overlay = Gtk.Overlay()
        self._preview_overlay.set_hexpand(True)
        self._preview_overlay.set_vexpand(True)
        self._preview_overlay.set_child(self._preview_picture)

        self._crop_canvas = Gtk.DrawingArea()
        self._crop_canvas.set_draw_func(self._on_crop_canvas_draw)
        self._crop_canvas.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))
        self._preview_overlay.add_overlay(self._crop_canvas)

        crop_click = Gtk.GestureClick()
        crop_click.set_button(1)
        crop_click.connect("pressed", self._on_crop_press)
        crop_click.connect("released", self._on_crop_release)
        self._crop_canvas.add_controller(crop_click)
        crop_motion = Gtk.EventControllerMotion()
        crop_motion.connect("motion", self._on_crop_motion)
        self._crop_canvas.add_controller(crop_motion)

        self._crop_dragging = False
        self._crop_start = (0.0, 0.0)
        self._crop_rect = None  # (x, y, w, h) in canvas (overlay) coords

        self._scroll.set_child(self._preview_overlay)

        # Video player (hidden by default)
        self._video_player = Gtk.Video()
        self._video_player.set_visible(False)
        self._video_player.set_vexpand(True)

        self._preview_stack = Gtk.Stack()
        self._preview_stack.add_named(self._scroll, "image")
        self._preview_stack.add_named(self._video_player, "video")
        self._preview_stack.set_vexpand(True)
        self._preview_box.append(self._preview_stack)

        # Info bar with action buttons
        info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        info_bar.add_css_class("preview-info")
        info_bar.set_margin_start(12)
        info_bar.set_margin_end(12)
        info_bar.set_margin_top(6)
        info_bar.set_margin_bottom(6)

        self._info_label = Gtk.Label(label="")
        self._info_label.set_hexpand(True)
        self._info_label.set_halign(Gtk.Align.START)
        info_bar.append(self._info_label)

        self._reset_crop_btn = Gtk.Button(label="Clear crop")
        self._reset_crop_btn.connect("clicked", self._on_reset_crop_clicked)
        self._reset_crop_btn.set_sensitive(False)
        info_bar.append(self._reset_crop_btn)

        self._copy_btn = Gtk.Button(label="Copy")
        self._copy_btn.connect("clicked", self._on_copy_clicked)
        info_bar.append(self._copy_btn)

        self._save_btn = Gtk.Button(label="Save")
        self._save_btn.connect("clicked", self._on_save_clicked)
        info_bar.append(self._save_btn)

        discard_btn = Gtk.Button(label="Discard")
        discard_btn.add_css_class("destructive-action")
        discard_btn.connect("clicked", self._on_discard_clicked)
        info_bar.append(discard_btn)

        self._preview_box.append(info_bar)
        self._main_box.append(self._preview_box)

    def _on_preferences(self, *_args):
        pref_win = Adw.PreferencesWindow(transient_for=self, modal=True)
        pref_win.set_title("Snipr Preferences")
        pref_win.set_default_size(500, 300)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Global hotkey")

        hotkey_service = getattr(self._app, "hotkey_service", None)
        available = bool(hotkey_service and hotkey_service.available)
        if available:
            group.set_description(
                "Press this combo from anywhere to trigger a new capture. "
                "Fires without raising Snipr — ideal for dropdowns and "
                "transient menus. Empty disables. "
                "Examples: Print, <Ctrl><Shift>s, <Super>a"
            )
        else:
            group.set_description(
                "Global hotkeys unavailable on this system. Install "
                "gir1.2-keybinder-3.0 and run on X11 to enable."
            )

        row = Adw.EntryRow()
        row.set_title("Accelerator")
        row.set_text(self._app.config.get("global_hotkey", ""))
        row.set_show_apply_button(True)
        row.set_sensitive(available)

        def _on_apply(entry):
            accel = entry.get_text().strip()
            prev = self._app.config.get("global_hotkey", "")
            self._app.config["global_hotkey"] = accel
            if self._app.apply_hotkey():
                self._app.save_config()
                msg = f"Hotkey set: {accel}" if accel else "Hotkey disabled"
                self._toast_overlay.add_toast(Adw.Toast.new(msg))
            else:
                # Revert on failure (invalid or already-grabbed combo)
                self._app.config["global_hotkey"] = prev
                self._app.apply_hotkey()
                entry.set_text(prev)
                self._toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not bind: {accel}")
                )

        row.connect("apply", _on_apply)
        group.add(row)
        page.add(group)
        pref_win.add(page)
        pref_win.present()

    def _on_mode_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if 0 <= idx < len(AVAILABLE_MODES):
            self._selected_mode = AVAILABLE_MODES[idx]

    def _on_delay_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if 0 <= idx < len(AVAILABLE_DELAYS):
            self._delay_seconds = AVAILABLE_DELAYS[idx]

    def _on_new_clicked(self, _btn):
        self.start_new_capture()

    def start_new_capture(self):
        """Begin a new capture based on the selected mode."""
        if self._app.video_service.state == RecordingState.RECORDING:
            return

        self._hide_preview()

        # Hide window before capture
        self.set_visible(False)

        if self._delay_seconds > 0:
            self._start_delay_countdown(self._delay_seconds)
        else:
            # Small delay to let window hide
            GLib.timeout_add(150, self._execute_capture)

    def _start_delay_countdown(self, remaining: int):
        if remaining <= 0:
            self._execute_capture()
            return
        GLib.timeout_add(1000, self._start_delay_countdown, remaining - 1)

    def _execute_capture(self):
        mode = self._selected_mode

        if mode.requires_rectangle_selection:
            self._show_rectangle_overlay()
        elif mode.requires_window_selection:
            self._show_window_overlay()
        elif mode.requires_freeform_selection:
            self._show_freeform_overlay()
        elif mode.is_fullscreen:
            self._capture_fullscreen()

        return False  # Don't repeat GLib.timeout

    def _spawn_overlay(self, overlay_cls, on_selected, on_cancelled):
        """Create one virtual-screen-spanning overlay with a shared frozen capture."""
        frozen = self._app.capture_service.capture_fullscreen()
        self._frozen_pixbuf = frozen
        overlay = overlay_cls(
            capture_service=self._app.capture_service,
            on_selected=on_selected,
            on_cancelled=on_cancelled,
            pre_captured=frozen,
        )
        self._active_overlay = overlay
        self._active_overlays = [overlay]
        overlay.present()

    def _show_rectangle_overlay(self):
        from snipr.ui.rectangle_overlay import RectangleSelectionOverlay
        self._spawn_overlay(
            RectangleSelectionOverlay,
            self._on_rectangle_selected,
            self._on_overlay_cancelled,
        )

    def _show_window_overlay(self):
        from snipr.ui.window_overlay import WindowSelectionOverlay
        self._spawn_overlay(
            WindowSelectionOverlay,
            self._on_window_selected,
            self._on_overlay_cancelled,
        )

    def _show_freeform_overlay(self):
        from snipr.ui.freeform_overlay import FreeformSelectionOverlay
        self._spawn_overlay(
            FreeformSelectionOverlay,
            self._on_freeform_selected,
            self._on_overlay_cancelled,
        )

    def _capture_fullscreen(self):
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
                pixbuf = cs.capture_fullscreen()
                # Dismiss any live popup/menu that was in the capture so its
                # pointer grab doesn't swallow the first click in the preview.
                _dismiss_active_popup()
                self._last_result = CaptureResult(
                    mode=self._selected_mode,
                    screenshot=pixbuf,
                    capture_region=(0, 0, pixbuf.get_width(), pixbuf.get_height()),
                )
                self.set_visible(True)
                self._show_preview()
            else:
                # Fullscreen video
                self._app.video_service.start_recording_fullscreen()
                self._show_recording_indicator()
        except Exception as e:
            self.set_visible(True)
            self._show_error(f"Capture failed: {e}")

    def _on_rectangle_selected(self, x: int, y: int, w: int, h: int):
        frozen = getattr(self, "_frozen_pixbuf", None)
        self._frozen_pixbuf = None
        self._active_overlay = None
        self._active_overlays = None
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
                pixbuf = _crop_pixbuf(frozen, x, y, w, h)
                if pixbuf is None:
                    pixbuf = cs.capture_region(x, y, w, h)
                self._last_result = CaptureResult(
                    mode=self._selected_mode,
                    screenshot=pixbuf,
                    capture_region=(x, y, w, h),
                )
                self.set_visible(True)
                self._show_preview()
            else:
                # Rectangle video
                self._app.video_service.start_recording_region(x, y, w, h)
                self._show_recording_indicator()
        except Exception as e:
            self.set_visible(True)
            self._show_error(f"Capture failed: {e}")

    def _on_window_selected(self, window_info):
        frozen = getattr(self, "_frozen_pixbuf", None)
        self._frozen_pixbuf = None
        self._active_overlay = None
        self._active_overlays = None
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
                pixbuf = _crop_pixbuf(
                    frozen, window_info.x, window_info.y,
                    window_info.width, window_info.height,
                )
                if pixbuf is None:
                    if hasattr(window_info, 'window_id') and hasattr(cs, 'capture_window'):
                        pixbuf = cs.capture_window(window_info.window_id)
                    else:
                        pixbuf = cs.capture_region(
                            window_info.x, window_info.y,
                            window_info.width, window_info.height,
                        )
                self._last_result = CaptureResult(
                    mode=self._selected_mode,
                    screenshot=pixbuf,
                    capture_region=(window_info.x, window_info.y,
                                    window_info.width, window_info.height),
                )
                self.set_visible(True)
                self._show_preview()
            else:
                # Window video
                self._app.video_service.start_recording_window(
                    window_info.x, window_info.y,
                    window_info.width, window_info.height,
                )
                self._show_recording_indicator()
        except Exception as e:
            self.set_visible(True)
            self._show_error(f"Capture failed: {e}")

    def _on_freeform_selected(self, x: int, y: int, w: int, h: int,
                               points: list[tuple[int, int]]):
        frozen = getattr(self, "_frozen_pixbuf", None)
        self._frozen_pixbuf = None
        self._active_overlay = None
        self._active_overlays = None
        try:
            cs = self._app.capture_service
            pixbuf = _mask_pixbuf(frozen, x, y, w, h, points)
            if pixbuf is None:
                pixbuf = cs.capture_freeform(x, y, w, h, points)
            self._last_result = CaptureResult(
                mode=self._selected_mode,
                screenshot=pixbuf,
                capture_region=(x, y, w, h),
            )
            self.set_visible(True)
            self._show_preview()
        except Exception as e:
            self.set_visible(True)
            self._show_error(f"Capture failed: {e}")

    def _on_overlay_cancelled(self):
        self._frozen_pixbuf = None
        self._active_overlay = None
        self._active_overlays = None
        self.set_visible(True)

    def _show_preview(self):
        result = self._last_result
        if result is None:
            return

        # Fresh capture — drop any previous crop selection.
        self._reset_crop_state()

        self._video_saved = False
        new_w, new_h = 450, 400

        if result.is_screenshot and result.screenshot:
            pixbuf = result.screenshot
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            self._preview_picture.set_paintable(texture)
            self._preview_stack.set_visible_child_name("image")

            pw = pixbuf.get_width()
            ph = pixbuf.get_height()
            self._info_label.set_text(f"{pw} x {ph} pixels")

            # Resize to fit content
            display = self.get_display()
            if display:
                monitors = display.get_monitors()
                if monitors.get_n_items() > 0:
                    mon = monitors.get_item(0)
                    geom = mon.get_geometry()
                    max_w = int(geom.width * 0.8)
                    max_h = int(geom.height * 0.8)
                    aspect = pw / ph if ph else 1
                    new_w = min(pw + 32, max_w)
                    new_h = min(int((new_w - 32) / aspect + 160), max_h)
                    new_w = max(new_w, 450)

        elif result.is_video and result.video_path:
            media_file = Gtk.MediaFile.new_for_filename(result.video_path)
            self._video_player.set_media_stream(media_file)
            self._video_player.set_visible(True)
            self._preview_stack.set_visible_child_name("video")

            file_size = os.path.getsize(result.video_path)
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{file_size / 1024:.0f} KB"
            self._info_label.set_text(f"Video - {size_str}")
            new_w, new_h = 640, 480

        self._preview_box.set_visible(True)
        self._is_preview_visible = True
        self.set_resizable(True)
        self.set_size_request(-1, -1)
        self.set_default_size(new_w, new_h)

    def _hide_preview(self):
        self._preview_picture.set_paintable(None)
        self._video_player.set_media_stream(None)
        self._preview_box.set_visible(False)
        self._is_preview_visible = False
        self.set_resizable(False)
        self._reset_crop_state()
        # Force shrink back to compact size
        self.set_default_size(450, -1)
        self.set_size_request(450, -1)

        # Cleanup temp video if not saved
        if not self._video_saved and self._last_result and self._last_result.video_path:
            path = self._last_result.video_path
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    # --- Crop-in-preview ----------------------------------------------------

    @staticmethod
    def _layout_image(canvas_w: int, canvas_h: int, img_w: int, img_h: int):
        """Compute scaled image placement inside a CONTAIN-fit widget."""
        if img_w <= 0 or img_h <= 0 or canvas_w <= 0 or canvas_h <= 0:
            return 0.0, 0.0, 1.0
        scale = min(canvas_w / img_w, canvas_h / img_h)
        disp_w = img_w * scale
        disp_h = img_h * scale
        return (canvas_w - disp_w) / 2.0, (canvas_h - disp_h) / 2.0, scale

    def _crop_bounds_in_image_space(self):
        """Convert self._crop_rect from canvas coords to image/pixbuf coords.

        Returns (x, y, w, h) clamped to the pixbuf, or None if there's no
        active selection or no screenshot.
        """
        if self._crop_rect is None:
            return None
        if self._last_result is None or not self._last_result.screenshot:
            return None
        pb = self._last_result.screenshot
        pw, ph = pb.get_width(), pb.get_height()
        cw = self._crop_canvas.get_width() or 1
        ch = self._crop_canvas.get_height() or 1
        ox, oy, scale = self._layout_image(cw, ch, pw, ph)
        if scale <= 0:
            return None
        rx, ry, rw, rh = self._crop_rect
        ix = max(0, int((rx - ox) / scale))
        iy = max(0, int((ry - oy) / scale))
        iw = max(0, int(rw / scale))
        ih = max(0, int(rh / scale))
        iw = min(iw, pw - ix)
        ih = min(ih, ph - iy)
        if iw <= 0 or ih <= 0:
            return None
        return ix, iy, iw, ih

    def _effective_screenshot(self):
        """Return the pixbuf that Save/Copy should export: cropped if a
        selection is active, else the full screenshot."""
        if self._last_result is None or not self._last_result.screenshot:
            return None
        bounds = self._crop_bounds_in_image_space()
        if bounds is None:
            return self._last_result.screenshot
        ix, iy, iw, ih = bounds
        return self._last_result.screenshot.new_subpixbuf(ix, iy, iw, ih).copy()

    def _on_crop_canvas_draw(self, _area, ctx, width, height):
        if self._crop_rect is None:
            return
        x, y, w, h = self._crop_rect
        if w <= 0 or h <= 0:
            return
        # Dim outside the selection
        ctx.set_source_rgba(0, 0, 0, 0.35)
        ctx.rectangle(0, 0, width, height)
        ctx.rectangle(x, y, w, h)
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        ctx.fill()
        # Selection border
        ctx.set_source_rgba(0.2, 0.5, 1.0, 0.95)
        ctx.set_line_width(2)
        ctx.rectangle(x, y, w, h)
        ctx.stroke()
        # Dimensions label in image-space pixels
        bounds = self._crop_bounds_in_image_space()
        if bounds is not None:
            _, _, iw, ih = bounds
            label = f"{iw} x {ih}"
            ctx.set_source_rgba(1, 1, 1, 0.95)
            ctx.set_font_size(13)
            ctx.move_to(x + 4, y - 6 if y > 20 else y + h + 16)
            ctx.show_text(label)

    def _on_crop_press(self, _gesture, _n_press, x, y):
        if self._last_result is None or not self._last_result.screenshot:
            return
        self._crop_dragging = True
        self._crop_start = (x, y)
        self._crop_rect = (x, y, 0.0, 0.0)
        self._crop_canvas.queue_draw()

    def _on_crop_motion(self, _controller, x, y):
        if not self._crop_dragging:
            return
        sx, sy = self._crop_start
        self._crop_rect = (min(sx, x), min(sy, y), abs(x - sx), abs(y - sy))
        self._crop_canvas.queue_draw()

    def _on_crop_release(self, _gesture, _n_press, _x, _y):
        if not self._crop_dragging:
            return
        self._crop_dragging = False
        if self._crop_rect is not None:
            _rx, _ry, rw, rh = self._crop_rect
            if rw < 5 or rh < 5:
                self._crop_rect = None
        self._crop_canvas.queue_draw()
        self._update_crop_ui()

    def _on_reset_crop_clicked(self, _btn):
        self._crop_rect = None
        self._crop_canvas.queue_draw()
        self._update_crop_ui()

    def _update_crop_ui(self):
        active = self._crop_rect is not None
        self._reset_crop_btn.set_sensitive(active)
        bounds = self._crop_bounds_in_image_space()
        if self._last_result and self._last_result.screenshot:
            pb = self._last_result.screenshot
            pw, ph = pb.get_width(), pb.get_height()
            if bounds is not None:
                _, _, iw, ih = bounds
                self._info_label.set_text(f"{pw} x {ph} • crop {iw} x {ih}")
            else:
                self._info_label.set_text(f"{pw} x {ph} pixels")

    def _reset_crop_state(self):
        self._crop_dragging = False
        self._crop_rect = None
        if hasattr(self, "_crop_canvas"):
            self._crop_canvas.queue_draw()
            self._update_crop_ui()

    # ------------------------------------------------------------------------

    def _on_copy_clicked(self, btn):
        self.copy_to_clipboard()
        btn.set_label("Copied!")
        GLib.timeout_add(1000, lambda: (btn.set_label("Copy"), False)[1])

    def _on_save_clicked(self, _btn):
        self.save_capture()

    def _on_discard_clicked(self, _btn):
        self._hide_preview()

    def copy_to_clipboard(self):
        if self._last_result is None:
            return
        if self._last_result.screenshot:
            pb = self._effective_screenshot() or self._last_result.screenshot
            self._app.clipboard_service.copy_image(pb, self)
        elif self._last_result.video_path:
            self._app.clipboard_service.copy_file_path(self._last_result.video_path, self)

    def save_capture(self):
        if self._last_result is None:
            return

        dialog = Gtk.FileDialog()

        if self._last_result.is_screenshot:
            filter_png = Gtk.FileFilter()
            filter_png.set_name("PNG Image")
            filter_png.add_pattern("*.png")
            filter_jpg = Gtk.FileFilter()
            filter_jpg.set_name("JPEG Image")
            filter_jpg.add_pattern("*.jpg")
            filter_bmp = Gtk.FileFilter()
            filter_bmp.set_name("Bitmap Image")
            filter_bmp.add_pattern("*.bmp")

            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_png)
            filters.append(filter_jpg)
            filters.append(filter_bmp)
            dialog.set_filters(filters)

            from datetime import datetime
            dialog.set_initial_name(
                f"Screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            dialog.save(self, None, self._on_screenshot_save_response)

        elif self._last_result.is_video and self._last_result.video_path:
            filter_mp4 = Gtk.FileFilter()
            filter_mp4.set_name("MP4 Video")
            filter_mp4.add_pattern("*.mp4")

            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_mp4)
            dialog.set_filters(filters)

            from datetime import datetime
            dialog.set_initial_name(
                f"Recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            )
            dialog.save(self, None, self._on_video_save_response)

    def _on_screenshot_save_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            path = file.get_path()
            if self._last_result and self._last_result.screenshot:
                pb = self._effective_screenshot() or self._last_result.screenshot
                if self._app.clipboard_service.save_pixbuf(pb, path):
                    self._show_toast("Image saved successfully")
                else:
                    self._show_error("Failed to save image")
        except GLib.Error:
            pass  # User cancelled

    def _on_video_save_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            dest_path = file.get_path()
            if self._last_result and self._last_result.video_path:
                import shutil
                # Stop video player before copying
                self._video_player.set_media_stream(None)
                shutil.copy2(self._last_result.video_path, dest_path)
                self._video_saved = True
                # Restart playback
                media_file = Gtk.MediaFile.new_for_filename(self._last_result.video_path)
                self._video_player.set_media_stream(media_file)
                self._show_toast("Video saved successfully")
        except GLib.Error:
            pass  # User cancelled
        except Exception as e:
            self._show_error(f"Failed to save video: {e}")

    def stop_recording(self):
        if self._app.video_service.state == RecordingState.RECORDING:
            self._app.video_service.stop_recording()

    def cancel_or_quit(self) -> bool:
        """Cancel active overlay or recording. Returns True if something was cancelled."""
        if self._active_overlay:
            self._active_overlay.close()
            self._active_overlay = None
            self.set_visible(True)
            return True
        if self._app.video_service.state == RecordingState.RECORDING:
            self._app.video_service.cancel_recording()
            self._hide_recording_indicator()
            self.set_visible(True)
            return True
        if self._is_preview_visible:
            self._hide_preview()
            return True
        return False

    # --- Recording callbacks ---

    def _on_recording_state_changed(self, state: RecordingState):
        if state == RecordingState.IDLE:
            self._hide_recording_indicator()

    def _on_recording_duration_changed(self, seconds: float):
        if self._recording_indicator:
            self._recording_indicator.update_duration(seconds)

    def _on_recording_completed(self, path: str):
        self._hide_recording_indicator()
        self._last_result = CaptureResult(
            mode=self._selected_mode,
            video_path=path,
        )
        self.set_visible(True)
        self._show_preview()

    def _on_recording_failed(self, error: str):
        self._hide_recording_indicator()
        self.set_visible(True)
        self._show_error(f"Recording failed: {error}")

    def _show_recording_indicator(self):
        self._hide_recording_indicator()
        from snipr.ui.recording_indicator import RecordingIndicator
        self._recording_indicator = RecordingIndicator(
            on_stop=self.stop_recording,
        )
        self._recording_indicator.present()

    def _hide_recording_indicator(self):
        if self._recording_indicator:
            self._recording_indicator.close()
            self._recording_indicator = None

    def _show_toast(self, message: str):
        toast = Adw.Toast(title=message, timeout=2)
        self._toast_overlay.add_toast(toast)

    def _show_error(self, message: str):
        dialog = Adw.AlertDialog(
            heading="Error",
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present(self)
