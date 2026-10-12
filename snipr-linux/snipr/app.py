import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gio, GLib

from snipr.services import config as snipr_config
from snipr.services.display_server import get_display_server
from snipr.services.hotkey import GlobalHotkeyService
from snipr.services.screen_capture import create_screen_capture_service
from snipr.services.clipboard import ClipboardService
from snipr.services.video_recording import VideoRecordingService


class SniprApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.snipr.Snipr",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.display_server = get_display_server()
        self.capture_service = None
        self.clipboard_service = None
        self.video_service = None
        self.hotkey_service: GlobalHotkeyService | None = None
        self.config: dict = snipr_config.load()
        self._main_window = None
        self._fullscreen_on_activate = False
        self.add_main_option(
            "fullscreen", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            "Take a full-screen screenshot now and show it in the preview", None,
        )

    def do_handle_local_options(self, options):
        if not options.contains("fullscreen"):
            return -1
        # A running Snipr takes the capture; otherwise this process becomes
        # Snipr and captures as soon as its window exists.
        self.register(None)
        if self.get_is_remote():
            self.activate_action("fullscreen-snip", None)
            return 0
        self._fullscreen_on_activate = True
        return -1

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._setup_actions()
        self._setup_theme()
        self._load_css()

    def do_shutdown(self):
        if self.hotkey_service is not None:
            self.hotkey_service.shutdown()
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        self._ensure_main_window()
        if self._fullscreen_on_activate:
            self._fullscreen_on_activate = False
            self._main_window.start_fullscreen_capture()
            return
        self._main_window.present()

    def _ensure_main_window(self):
        if self._main_window is None:
            self.capture_service = create_screen_capture_service()
            self.clipboard_service = ClipboardService()
            self.video_service = VideoRecordingService(self.display_server)
            self.hotkey_service = GlobalHotkeyService()
            self.apply_hotkey()

            from snipr.ui.main_window import MainWindow
            self._main_window = MainWindow(application=self)

    def apply_hotkey(self) -> bool:
        """(Re-)bind the global hotkey from config. Returns True on success."""
        if self.hotkey_service is None:
            return False
        return self.hotkey_service.set_hotkey(
            self.config.get("global_hotkey", ""),
            self._on_global_hotkey,
        )

    def save_config(self) -> None:
        snipr_config.save(self.config)

    def _on_global_hotkey(self) -> None:
        # Hotkey fires without raising the main window — perfect for
        # capturing dropdowns and other transient UI that would close
        # when another window takes focus.
        if self._main_window is not None:
            self._main_window.start_new_capture()

    def _setup_actions(self):
        actions = [
            ("new-capture", self._on_new_capture, "<Control>n"),
            ("stop-recording", self._on_stop_recording, "<Control><Shift>q"),
            ("copy", self._on_copy, "<Control>c"),
            ("save", self._on_save, "<Control>s"),
            ("quit", self._on_quit, "Escape"),
        ]
        for name, callback, accel in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", [accel])

        fullscreen = Gio.SimpleAction.new("fullscreen-snip", None)
        fullscreen.connect("activate", self._on_fullscreen_snip)
        self.add_action(fullscreen)

    def _setup_theme(self):
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_LIGHT)

    def _load_css(self):
        import importlib.resources
        from gi.repository import Gtk, Gdk
        css_provider = Gtk.CssProvider()
        try:
            css_path = importlib.resources.files("snipr.resources").joinpath("snipr.css")
            css_provider.load_from_string(css_path.read_text())
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        except Exception:
            pass  # CSS is optional polish

    def _on_new_capture(self, action, param):
        if self._main_window:
            self._main_window.start_new_capture()

    def _on_fullscreen_snip(self, action, param):
        self._ensure_main_window()
        self._main_window.start_fullscreen_capture()

    def _on_stop_recording(self, action, param):
        if self._main_window:
            self._main_window.stop_recording()

    def _on_copy(self, action, param):
        if self._main_window:
            self._main_window.copy_to_clipboard()

    def _on_save(self, action, param):
        if self._main_window:
            self._main_window.save_capture()

    def _on_quit(self, action, param):
        if self._main_window:
            if self._main_window.cancel_or_quit():
                return  # Cancelled an overlay/recording, don't quit
        self.quit()
