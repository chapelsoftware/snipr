"""Main application window with toolbar and preview."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from snipr.models.capture_mode import CaptureMode
from snipr.models.capture_result import CaptureResult
from snipr.models.recording_state import RecordingState


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
            default_height=85,
            resizable=False,
            **kwargs,
        )

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
        # Toast overlay wraps everything
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        # Main vertical box
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(self._main_box)

        # Header bar
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Snipr"))

        # New button
        self._new_btn = Gtk.Button(label="New")
        self._new_btn.add_css_class("suggested-action")
        self._new_btn.connect("clicked", self._on_new_clicked)
        header.pack_start(self._new_btn)

        # Mode dropdown
        mode_names = [m.display_name for m in AVAILABLE_MODES]
        self._mode_model = Gtk.StringList.new(mode_names)
        self._mode_dropdown = Gtk.DropDown(model=self._mode_model)
        self._mode_dropdown.set_selected(0)
        self._mode_dropdown.connect("notify::selected", self._on_mode_changed)
        self._mode_dropdown.add_css_class("mode-dropdown")
        header.pack_start(self._mode_dropdown)

        # Delay dropdown
        delay_names = [f"{d}s" if d > 0 else "0s" for d in AVAILABLE_DELAYS]
        self._delay_model = Gtk.StringList.new(delay_names)
        self._delay_dropdown = Gtk.DropDown(model=self._delay_model)
        self._delay_dropdown.set_selected(0)
        self._delay_dropdown.connect("notify::selected", self._on_delay_changed)
        header.pack_start(self._delay_dropdown)

        self._main_box.append(header)

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
        self._scroll.set_child(self._preview_picture)

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

    def _show_rectangle_overlay(self):
        from snipr.ui.rectangle_overlay import RectangleSelectionOverlay
        self._active_overlay = RectangleSelectionOverlay(
            capture_service=self._app.capture_service,
            on_selected=self._on_rectangle_selected,
            on_cancelled=self._on_overlay_cancelled,
        )
        self._active_overlay.present()

    def _show_window_overlay(self):
        from snipr.ui.window_overlay import WindowSelectionOverlay
        self._active_overlay = WindowSelectionOverlay(
            capture_service=self._app.capture_service,
            on_selected=self._on_window_selected,
            on_cancelled=self._on_overlay_cancelled,
        )
        self._active_overlay.present()

    def _show_freeform_overlay(self):
        from snipr.ui.freeform_overlay import FreeformSelectionOverlay
        self._active_overlay = FreeformSelectionOverlay(
            capture_service=self._app.capture_service,
            on_selected=self._on_freeform_selected,
            on_cancelled=self._on_overlay_cancelled,
        )
        self._active_overlay.present()

    def _capture_fullscreen(self):
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
                pixbuf = cs.capture_fullscreen()
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
        self._active_overlay = None
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
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
        self._active_overlay = None
        try:
            cs = self._app.capture_service
            if self._selected_mode.is_screenshot:
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
        self._active_overlay = None
        try:
            cs = self._app.capture_service
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
        self._active_overlay = None
        self.set_visible(True)

    def _show_preview(self):
        result = self._last_result
        if result is None:
            return

        self._video_saved = False

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
                    new_h = min(int((new_w - 32) / aspect + 120), max_h)
                    self.set_default_size(max(new_w, 450), new_h)

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

            self.set_default_size(640, 480)

        self._preview_box.set_visible(True)
        self._is_preview_visible = True
        self.set_resizable(True)

    def _hide_preview(self):
        self._preview_picture.set_paintable(None)
        self._video_player.set_media_stream(None)
        self._preview_box.set_visible(False)
        self._is_preview_visible = False
        self.set_resizable(False)
        self.set_default_size(450, 85)

        # Cleanup temp video if not saved
        if not self._video_saved and self._last_result and self._last_result.video_path:
            path = self._last_result.video_path
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

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
            self._app.clipboard_service.copy_image(self._last_result.screenshot, self)
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
                if self._app.clipboard_service.save_pixbuf(self._last_result.screenshot, path):
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
