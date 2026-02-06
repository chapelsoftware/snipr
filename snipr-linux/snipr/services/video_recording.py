"""Video recording service using FFmpeg subprocess."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from gi.repository import GLib

from snipr.models.recording_state import RecordingState
from snipr.services.display_server import DisplayServer


class VideoRecordingService:
    def __init__(self, display_server: DisplayServer):
        self._display_server = display_server
        self._process: subprocess.Popen | None = None
        self._state = RecordingState.IDLE
        self._duration_seconds = 0.0
        self._timer_id: int | None = None
        self._current_path: str | None = None
        self._pipewire_node_id: str | None = None

        # Callbacks
        self.on_state_changed: Callable[[RecordingState], None] | None = None
        self.on_duration_changed: Callable[[float], None] | None = None
        self.on_recording_completed: Callable[[str], None] | None = None
        self.on_recording_failed: Callable[[str], None] | None = None

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def duration(self) -> float:
        return self._duration_seconds

    @property
    def current_path(self) -> str | None:
        return self._current_path

    def _set_state(self, state: RecordingState) -> None:
        if self._state != state:
            self._state = state
            if self.on_state_changed:
                self.on_state_changed(state)

    def start_recording_region(self, x: int, y: int, width: int, height: int) -> None:
        """Start recording a screen region."""
        # Ensure even dimensions for H.264
        width = width + (width % 2)
        height = height + (height % 2)
        self._start_recording(region=(x, y, width, height))

    def start_recording_fullscreen(self) -> None:
        """Start recording the full screen."""
        self._start_recording(region=None)

    def start_recording_window(self, x: int, y: int, width: int, height: int) -> None:
        """Start recording a window (captured as a region)."""
        self.start_recording_region(x, y, width, height)

    def _start_recording(self, region: tuple[int, int, int, int] | None) -> None:
        if self._state in (RecordingState.RECORDING, RecordingState.PREPARING, RecordingState.STOPPING):
            return

        self._set_state(RecordingState.PREPARING)

        # Generate temp output path
        temp_dir = Path(tempfile.gettempdir()) / "snipr"
        temp_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_path = str(temp_dir / f"Recording_{timestamp}.mp4")

        try:
            cmd = self._build_ffmpeg_command(region)
            print(f"[Snipr] Starting FFmpeg: {' '.join(cmd)}", flush=True)
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._duration_seconds = 0.0
            self._set_state(RecordingState.RECORDING)
            self._start_duration_timer()
            print(f"[Snipr] Recording started, PID={self._process.pid}", flush=True)
        except Exception as e:
            self._set_state(RecordingState.FAILED)
            if self.on_recording_failed:
                self.on_recording_failed(f"Failed to start recording: {e}")

    def _build_ffmpeg_command(self, region: tuple[int, int, int, int] | None) -> list[str]:
        cmd = ["ffmpeg", "-y"]

        if self._display_server == DisplayServer.WAYLAND and self._pipewire_node_id:
            # PipeWire source for Wayland
            cmd += ["-f", "pipewire", "-i", self._pipewire_node_id]
        else:
            # X11 grab — display must be :N not :N.S for offset syntax
            display = os.environ.get("DISPLAY", ":0")
            # Strip screen number (e.g. ":0.0" -> ":0") so "+X,Y" offset works
            if "." in display:
                display = display[:display.index(".")]
            cmd += ["-f", "x11grab", "-framerate", "30", "-draw_mouse", "0"]
            if region:
                x, y, w, h = region
                # Clamp to non-negative — FFmpeg x11grab rejects negative offsets
                x = max(0, x)
                y = max(0, y)
                cmd += ["-video_size", f"{w}x{h}", "-i", f"{display}+{x},{y}"]
            else:
                # Fullscreen - get screen size
                cmd += ["-i", display]

        # Encoding settings
        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            self._current_path,
        ]
        return cmd

    def stop_recording(self) -> None:
        """Gracefully stop the current recording."""
        if self._process is None or self._state != RecordingState.RECORDING:
            return

        self._set_state(RecordingState.STOPPING)
        self._stop_duration_timer()

        proc = self._process
        self._process = None

        import threading

        def _stop_worker():
            try:
                # communicate() sends input, drains stdout/stderr, and waits
                # This avoids deadlocks from full pipe buffers
                _, stderr_bytes = proc.communicate(input=b"q", timeout=10)
                stderr_data = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
                returncode = proc.returncode
                file_path = self._current_path
                file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else -1
                print(f"[Snipr] FFmpeg exited: code={returncode}, file={file_path}, size={file_size}", flush=True)
                if stderr_data:
                    # Print last few lines of stderr for diagnostics
                    lines = stderr_data.strip().split('\n')
                    for line in lines[-5:]:
                        print(f"[Snipr] ffmpeg: {line}", flush=True)

                def _on_done():
                    if returncode == 0 and file_path and file_size > 0:
                        self._set_state(RecordingState.COMPLETED)
                        if self.on_recording_completed:
                            self.on_recording_completed(file_path)
                    else:
                        self._set_state(RecordingState.FAILED)
                        if self.on_recording_failed:
                            self.on_recording_failed(
                                f"FFmpeg exited with code {returncode}: {stderr_data[-500:]}")

                GLib.idle_add(_on_done)

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

                def _on_timeout():
                    self._set_state(RecordingState.FAILED)
                    if self.on_recording_failed:
                        self.on_recording_failed("Recording stop timed out")

                GLib.idle_add(_on_timeout)

            except Exception as e:
                self._close_pipes(proc)
                err_msg = str(e)

                def _on_error():
                    self._set_state(RecordingState.FAILED)
                    if self.on_recording_failed:
                        self.on_recording_failed(err_msg)

                GLib.idle_add(_on_error)

        thread = threading.Thread(target=_stop_worker, daemon=True)
        thread.start()

    @staticmethod
    def _close_pipes(proc: subprocess.Popen) -> None:
        """Safely close all pipes on a process."""
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                try:
                    pipe.close()
                except Exception:
                    pass

    def cancel_recording(self) -> None:
        """Cancel and discard the current recording."""
        self._stop_duration_timer()
        if self._process:
            proc = self._process
            self._process = None
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            self._close_pipes(proc)

        # Delete incomplete file
        if self._current_path and os.path.exists(self._current_path):
            try:
                os.remove(self._current_path)
            except OSError:
                pass

        self._set_state(RecordingState.IDLE)

    def _start_duration_timer(self) -> None:
        self._duration_seconds = 0.0

        def tick():
            if self._state == RecordingState.RECORDING:
                self._duration_seconds += 0.1
                if self.on_duration_changed:
                    self.on_duration_changed(self._duration_seconds)
                return True  # Continue timer
            return False  # Stop timer

        self._timer_id = GLib.timeout_add(100, tick)

    def _stop_duration_timer(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def set_pipewire_node(self, node_id: str) -> None:
        """Set the PipeWire node ID for Wayland recording."""
        self._pipewire_node_id = node_id

    def cleanup(self) -> None:
        """Clean up resources."""
        self.cancel_recording()
