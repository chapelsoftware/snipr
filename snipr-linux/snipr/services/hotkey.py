"""Global hotkey service: runs a GTK3 sidecar that holds the key grab.

The main Snipr process is GTK4; libkeybinder3 is GTK3 and collides with
it inside one process. We therefore spawn `snipr._hotkey_daemon` as a
sidecar and let it fire the `new-capture` action via `gapplication`.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Callable, Optional


class GlobalHotkeyService:
    """Register one global hotkey. Replaces any previous binding."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._current: str = ""

    @property
    def available(self) -> bool:
        # Sidecar availability is checked by actually trying to spawn it.
        # Assume yes; set_hotkey will report failure if bind fails.
        return True

    def set_hotkey(
        self, accel: str, _callback: Callable[[], None] | None = None
    ) -> bool:
        """Bind `accel` globally. Empty string unbinds. Returns True on success.

        `_callback` is accepted for API symmetry but ignored: the sidecar
        triggers `app.new-capture` directly via `gapplication`.
        """
        self._stop()
        accel = (accel or "").strip()
        self._current = accel
        if not accel:
            return True

        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "snipr._hotkey_daemon", accel],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError:
            self._proc = None
            return False

        # The daemon exits non-zero if the bind fails — give it a short
        # moment to crash, then confirm it's still alive.
        time.sleep(0.3)
        if self._proc.poll() is not None:
            self._proc = None
            return False
        return True

    def shutdown(self) -> None:
        self._stop()

    def _stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                self._proc.kill()
            except OSError:
                pass
        except OSError:
            pass
        self._proc = None
