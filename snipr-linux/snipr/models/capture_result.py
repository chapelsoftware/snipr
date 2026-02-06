from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gi.repository import GdkPixbuf

from snipr.models.capture_mode import CaptureMode


@dataclass
class CaptureResult:
    mode: CaptureMode
    screenshot: GdkPixbuf.Pixbuf | None = None
    video_path: str | None = None
    captured_at: datetime = field(default_factory=datetime.now)
    capture_region: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h

    @property
    def is_video(self) -> bool:
        return self.mode.is_video

    @property
    def is_screenshot(self) -> bool:
        return self.mode.is_screenshot

    @property
    def has_content(self) -> bool:
        return self.screenshot is not None or self.video_path is not None
