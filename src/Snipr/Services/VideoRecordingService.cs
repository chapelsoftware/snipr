using System.Drawing;
using System.IO;
using System.Windows.Threading;
using ScreenRecorderLib;
using Snipr.Models;

namespace Snipr.Services;

public class VideoRecordingService : IVideoRecordingService, IDisposable
{
    private readonly IScreenProvider _screenProvider;
    private Recorder? _recorder;
    private DispatcherTimer? _durationTimer;
    private DateTime _recordingStartTime;
    private string? _currentPath;
    private bool _disposed;
    private readonly Dispatcher _dispatcher;

    public RecordingState State { get; private set; } = RecordingState.Idle;
    public TimeSpan Duration { get; private set; }
    public string? CurrentRecordingPath => _currentPath;

    public event EventHandler<RecordingState>? StateChanged;
    public event EventHandler<TimeSpan>? DurationChanged;
    public event EventHandler<string>? RecordingCompleted;
    public event EventHandler<string>? RecordingFailed;

    public VideoRecordingService() : this(new ScreenProvider())
    {
    }

    public VideoRecordingService(IScreenProvider screenProvider)
    {
        _screenProvider = screenProvider;
        _dispatcher = Dispatcher.CurrentDispatcher;
    }

    public Task StartRecordingRegionAsync(Rectangle region)
    {
        // Validate input
        RegionCalculator.ValidateRegion(region);

        // Get the screen containing the region
        var screenInfo = _screenProvider.GetScreenFromRectangle(region);

        // Validate region is within virtual screen bounds
        var virtualBounds = _screenProvider.GetVirtualScreenBounds();
        if (!RegionCalculator.RegionIntersectsScreen(region, virtualBounds))
        {
            throw new ArgumentException(
                $"Region {region} is completely outside virtual screen bounds {virtualBounds}",
                nameof(region));
        }

        // Calculate physical pixel coordinates
        var physicalRegion = RegionCalculator.CalculatePhysicalRegion(
            region,
            screenInfo.Bounds,
            screenInfo.DpiScale);

        var displaySource = new DisplayRecordingSource(screenInfo.DeviceName);

        // Ensure dimensions are even (required for H.264)
        var rectWidth = physicalRegion.Width % 2 == 0 ? physicalRegion.Width : physicalRegion.Width + 1;
        var rectHeight = physicalRegion.Height % 2 == 0 ? physicalRegion.Height : physicalRegion.Height + 1;

        // Set the source rectangle to capture only our region
        displaySource.SourceRect = new ScreenRect(
            physicalRegion.X,
            physicalRegion.Y,
            rectWidth,
            rectHeight);

        var sources = new List<RecordingSourceBase> { displaySource };

        // Explicit output size is required (auto-detect fails with "parameter is incorrect")
        var outputRect = new Rectangle(0, 0, rectWidth, rectHeight);
        return StartRecordingAsync(sources, outputRect);
    }

    public Task StartRecordingWindowAsync(IntPtr windowHandle, Rectangle bounds)
    {
        if (windowHandle == IntPtr.Zero)
            throw new ArgumentException("Window handle cannot be zero", nameof(windowHandle));

        // Use the same approach as region recording - capture the window's bounds from the display
        // WindowRecordingSource with auto-detect output size fails with "parameter is incorrect"

        // Get the screen containing the window
        var screenInfo = _screenProvider.GetScreenFromRectangle(bounds);

        // Calculate physical pixel coordinates
        var physicalRegion = RegionCalculator.CalculatePhysicalRegion(
            bounds,
            screenInfo.Bounds,
            screenInfo.DpiScale);

        var displaySource = new DisplayRecordingSource(screenInfo.DeviceName);

        // Ensure dimensions are even (required for H.264)
        var rectWidth = physicalRegion.Width % 2 == 0 ? physicalRegion.Width : physicalRegion.Width + 1;
        var rectHeight = physicalRegion.Height % 2 == 0 ? physicalRegion.Height : physicalRegion.Height + 1;

        // Set the source rectangle to capture the window's region
        displaySource.SourceRect = new ScreenRect(
            physicalRegion.X,
            physicalRegion.Y,
            rectWidth,
            rectHeight);

        var sources = new List<RecordingSourceBase> { displaySource };

        // Explicit output size is required
        var outputRect = new Rectangle(0, 0, rectWidth, rectHeight);
        return StartRecordingAsync(sources, outputRect);
    }

    public Task StartRecordingFullScreenAsync()
    {
        var screens = _screenProvider.GetAllScreens();
        if (screens.Count == 0)
            throw new InvalidOperationException("No screens available for recording");

        var sources = new List<RecordingSourceBase>();
        foreach (var screen in screens)
        {
            sources.Add(new DisplayRecordingSource(screen.DeviceName));
        }
        return StartRecordingAsync(sources, null);
    }

    private Task StartRecordingAsync(List<RecordingSourceBase> sources, Rectangle? outputSize)
    {
        // Allow starting from Idle, Completed, or Failed states
        if (State == RecordingState.Recording || State == RecordingState.Preparing || State == RecordingState.Stopping)
            throw new InvalidOperationException("Recording already in progress");

        SetState(RecordingState.Preparing);

        // Generate temp output path - video will be moved to permanent location when user saves
        var tempFolder = Path.Combine(Path.GetTempPath(), "Snipr");
        Directory.CreateDirectory(tempFolder);
        _currentPath = Path.Combine(tempFolder, $"Recording_{DateTime.Now:yyyyMMdd_HHmmss}.mp4");

        try
        {
            var frameSize = outputSize.HasValue
                ? new ScreenSize(outputSize.Value.Width, outputSize.Value.Height)
                : new ScreenSize(0, 0); // Auto-detect

            var options = new RecorderOptions
            {
                SourceOptions = new SourceOptions
                {
                    RecordingSources = sources
                },
                OutputOptions = new OutputOptions
                {
                    RecorderMode = RecorderMode.Video,
                    OutputFrameSize = frameSize,
                    Stretch = StretchMode.Uniform
                },
                VideoEncoderOptions = new VideoEncoderOptions
                {
                    Encoder = new H264VideoEncoder
                    {
                        BitrateMode = H264BitrateControlMode.CBR,
                        EncoderProfile = H264Profile.Main
                    },
                    Bitrate = 8000 * 1000,
                    Framerate = 30,
                    IsFixedFramerate = false,
                    IsFragmentedMp4Enabled = true,
                    IsLowLatencyEnabled = false,
                    IsHardwareEncodingEnabled = true
                },
                AudioOptions = new AudioOptions
                {
                    IsAudioEnabled = false,
                    IsInputDeviceEnabled = false,
                    IsOutputDeviceEnabled = false
                },
                MouseOptions = new MouseOptions
                {
                    IsMousePointerEnabled = false,
                    IsMouseClicksDetected = false
                }
            };

            _recorder = Recorder.CreateRecorder(options);
            _recorder.OnRecordingComplete += OnRecordingComplete;
            _recorder.OnRecordingFailed += OnRecordingFailed;
            _recorder.OnStatusChanged += OnStatusChanged;

            _recorder.Record(_currentPath);
        }
        catch (Exception ex)
        {
            SetState(RecordingState.Failed);
            RecordingFailed?.Invoke(this, $"Failed to start recording: {ex.Message}");
        }

        return Task.CompletedTask;
    }

    public async Task StopRecordingAsync()
    {
        if (_recorder == null || State != RecordingState.Recording)
            return;

        SetState(RecordingState.Stopping);
        _recorder.Stop();

        // Wait for completion with timeout
        var timeout = DateTime.Now.AddSeconds(10);
        while (State == RecordingState.Stopping && DateTime.Now < timeout)
        {
            await Task.Delay(100);
        }
    }

    public void CancelRecording()
    {
        StopDurationTimer();
        _recorder?.Stop();

        // Delete the incomplete file
        if (!string.IsNullOrEmpty(_currentPath) && File.Exists(_currentPath))
        {
            try
            {
                File.Delete(_currentPath);
            }
            catch
            {
                // Ignore deletion errors
            }
        }

        CleanupRecorder();
        SetState(RecordingState.Idle);
    }

    private void OnRecordingComplete(object? sender, RecordingCompleteEventArgs e)
    {
        _dispatcher.BeginInvoke(() =>
        {
            StopDurationTimer();
            CleanupRecorder();
            SetState(RecordingState.Completed);
            RecordingCompleted?.Invoke(this, e.FilePath);
        });
    }

    private void OnRecordingFailed(object? sender, RecordingFailedEventArgs e)
    {
        _dispatcher.BeginInvoke(() =>
        {
            StopDurationTimer();
            CleanupRecorder();
            SetState(RecordingState.Failed);
            RecordingFailed?.Invoke(this, e.Error);
        });
    }

    private void OnStatusChanged(object? sender, RecordingStatusEventArgs e)
    {
        _dispatcher.BeginInvoke(() =>
        {
            switch (e.Status)
            {
                case RecorderStatus.Recording:
                    SetState(RecordingState.Recording);
                    StartDurationTimer();
                    break;
                case RecorderStatus.Paused:
                    break;
                case RecorderStatus.Finishing:
                    SetState(RecordingState.Stopping);
                    break;
            }
        });
    }

    private void StartDurationTimer()
    {
        _recordingStartTime = DateTime.Now;
        Duration = TimeSpan.Zero;

        _durationTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(100)
        };
        _durationTimer.Tick += (_, _) =>
        {
            Duration = DateTime.Now - _recordingStartTime;
            DurationChanged?.Invoke(this, Duration);
        };
        _durationTimer.Start();
    }

    private void StopDurationTimer()
    {
        _durationTimer?.Stop();
        _durationTimer = null;
    }

    private void CleanupRecorder()
    {
        if (_recorder != null)
        {
            _recorder.OnRecordingComplete -= OnRecordingComplete;
            _recorder.OnRecordingFailed -= OnRecordingFailed;
            _recorder.OnStatusChanged -= OnStatusChanged;
            _recorder.Dispose();
            _recorder = null;
        }
    }

    private void SetState(RecordingState state)
    {
        if (State != state)
        {
            State = state;
            StateChanged?.Invoke(this, state);
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        StopDurationTimer();
        CleanupRecorder();
    }
}
