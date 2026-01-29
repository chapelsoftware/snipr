using System.Drawing;
using SnipSnap.Models;

namespace SnipSnap.Services;

public interface IVideoRecordingService
{
    RecordingState State { get; }
    TimeSpan Duration { get; }
    string? CurrentRecordingPath { get; }

    event EventHandler<RecordingState>? StateChanged;
    event EventHandler<TimeSpan>? DurationChanged;
    event EventHandler<string>? RecordingCompleted;
    event EventHandler<string>? RecordingFailed;

    Task StartRecordingRegionAsync(Rectangle region);
    Task StartRecordingWindowAsync(IntPtr windowHandle, Rectangle bounds);
    Task StartRecordingFullScreenAsync();
    Task StopRecordingAsync();
    void CancelRecording();
}
