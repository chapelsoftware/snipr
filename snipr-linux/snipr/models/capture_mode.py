from enum import Enum


class CaptureMode(Enum):
    RECTANGLE_SNIP = "Rectangle Snip"
    WINDOW_SNIP = "Window Snip"
    FULLSCREEN_SNIP = "Full-screen Snip"
    FREEFORM_SNIP = "Freeform Snip"
    RECTANGLE_VIDEO = "Rectangle Video"
    WINDOW_VIDEO = "Window Video"
    FULLSCREEN_VIDEO = "Full-screen Video"

    @property
    def display_name(self) -> str:
        return self.value

    @property
    def is_video(self) -> bool:
        return self in (
            CaptureMode.RECTANGLE_VIDEO,
            CaptureMode.WINDOW_VIDEO,
            CaptureMode.FULLSCREEN_VIDEO,
        )

    @property
    def is_screenshot(self) -> bool:
        return not self.is_video

    @property
    def requires_window_selection(self) -> bool:
        return self in (CaptureMode.WINDOW_SNIP, CaptureMode.WINDOW_VIDEO)

    @property
    def requires_rectangle_selection(self) -> bool:
        return self in (CaptureMode.RECTANGLE_SNIP, CaptureMode.RECTANGLE_VIDEO)

    @property
    def requires_freeform_selection(self) -> bool:
        return self == CaptureMode.FREEFORM_SNIP

    @property
    def is_fullscreen(self) -> bool:
        return self in (CaptureMode.FULLSCREEN_SNIP, CaptureMode.FULLSCREEN_VIDEO)
