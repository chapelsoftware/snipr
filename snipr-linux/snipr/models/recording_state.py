from enum import Enum


class RecordingState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RECORDING = "recording"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
