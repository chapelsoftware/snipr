using System.Drawing;
using System.Windows.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Snipr.Models;
using Snipr.Services;
using CaptureMode = Snipr.Models.CaptureMode;

namespace Snipr.ViewModels;

public partial class MainViewModel : ViewModelBase
{
    private readonly IScreenCaptureService _captureService;
    private readonly IVideoRecordingService _recordingService;
    private readonly ClipboardService _clipboardService;
    private readonly WindowEnumerationService _windowService;

    [ObservableProperty]
    private CaptureMode _selectedMode = CaptureMode.RectangleSnip;

    [ObservableProperty]
    private int _delaySeconds;

    [ObservableProperty]
    private bool _isRecording;

    [ObservableProperty]
    private string _recordingDuration = "00:00";

    [ObservableProperty]
    private RecordingState _recordingState = RecordingState.Idle;

    [ObservableProperty]
    private CaptureResult? _lastCaptureResult;

    [ObservableProperty]
    private bool _isDelayCountdownActive;

    [ObservableProperty]
    private int _countdownRemaining;

    public IReadOnlyList<CaptureMode> AvailableModes { get; } =
    [
        CaptureMode.RectangleSnip,
        CaptureMode.WindowSnip,
        CaptureMode.FullscreenSnip,
        CaptureMode.RectangleVideo,
        CaptureMode.WindowVideo,
        CaptureMode.FullscreenVideo
    ];

    public IReadOnlyList<int> AvailableDelays { get; } = [0, 1, 2, 3, 4, 5];

    public event EventHandler? RequestWindowSelection;
    public event EventHandler? RequestRectangleSelection;
    public event EventHandler? RequestShowPreview;
    public event EventHandler? RequestHideMainWindow;
    public event EventHandler? RequestShowMainWindow;

    public MainViewModel(
        IScreenCaptureService captureService,
        IVideoRecordingService recordingService,
        ClipboardService clipboardService,
        WindowEnumerationService windowService)
    {
        _captureService = captureService;
        _recordingService = recordingService;
        _clipboardService = clipboardService;
        _windowService = windowService;

        _recordingService.StateChanged += OnRecordingStateChanged;
        _recordingService.DurationChanged += OnRecordingDurationChanged;
        _recordingService.RecordingCompleted += OnRecordingCompleted;
        _recordingService.RecordingFailed += OnRecordingFailed;
    }

    [RelayCommand]
    private async Task NewCaptureAsync()
    {
        if (IsRecording)
            return;

        RequestHideMainWindow?.Invoke(this, EventArgs.Empty);

        // Apply delay if set
        if (DelaySeconds > 0)
        {
            IsDelayCountdownActive = true;
            for (int i = DelaySeconds; i > 0; i--)
            {
                CountdownRemaining = i;
                await Task.Delay(1000);
            }
            IsDelayCountdownActive = false;
        }

        // Start capture based on mode
        if (SelectedMode.RequiresWindowSelection())
        {
            RequestWindowSelection?.Invoke(this, EventArgs.Empty);
        }
        else if (SelectedMode.RequiresRectangleSelection())
        {
            RequestRectangleSelection?.Invoke(this, EventArgs.Empty);
        }
        else if (SelectedMode.IsFullscreen())
        {
            await CaptureFullscreenAsync();
        }
    }

    [RelayCommand]
    private async Task StopRecordingAsync()
    {
        if (!IsRecording)
            return;

        await _recordingService.StopRecordingAsync();
    }

    [RelayCommand]
    private void CancelCapture()
    {
        if (IsRecording)
        {
            _recordingService.CancelRecording();
        }
        RequestShowMainWindow?.Invoke(this, EventArgs.Empty);
    }

    public async Task HandleWindowSelectionAsync(WindowInfo window)
    {
        if (SelectedMode.IsScreenshot())
        {
            var screenshot = _captureService.CaptureWindow(window.Handle);
            LastCaptureResult = new CaptureResult
            {
                Mode = SelectedMode,
                Screenshot = screenshot,
                CaptureRegion = window.Bounds
            };
            RequestShowPreview?.Invoke(this, EventArgs.Empty);
        }
        else
        {
            await _recordingService.StartRecordingWindowAsync(window.Handle, window.Bounds);
        }
    }

    public async Task HandleRectangleSelectionAsync(Rectangle bounds)
    {
        if (SelectedMode.IsScreenshot())
        {
            var screenshot = _captureService.CaptureRegion(bounds);
            LastCaptureResult = new CaptureResult
            {
                Mode = SelectedMode,
                Screenshot = screenshot,
                CaptureRegion = bounds
            };
            RequestShowPreview?.Invoke(this, EventArgs.Empty);
        }
        else
        {
            await _recordingService.StartRecordingRegionAsync(bounds);
        }
    }

    private async Task CaptureFullscreenAsync()
    {
        // Small delay to let window hide
        await Task.Delay(150);

        if (SelectedMode.IsScreenshot())
        {
            var screenshot = _captureService.CaptureFullScreen();
            LastCaptureResult = new CaptureResult
            {
                Mode = SelectedMode,
                Screenshot = screenshot,
                CaptureRegion = Helpers.ScreenHelper.GetVirtualScreenBounds()
            };
            RequestShowMainWindow?.Invoke(this, EventArgs.Empty);
            RequestShowPreview?.Invoke(this, EventArgs.Empty);
        }
        else
        {
            await _recordingService.StartRecordingFullScreenAsync();
            RequestShowMainWindow?.Invoke(this, EventArgs.Empty);
        }
    }

    public void CopyToClipboard()
    {
        if (LastCaptureResult?.Screenshot != null)
        {
            _clipboardService.CopyImage(LastCaptureResult.Screenshot);
        }
        else if (!string.IsNullOrEmpty(LastCaptureResult?.VideoPath))
        {
            _clipboardService.CopyFilePath(LastCaptureResult.VideoPath);
        }
    }

    public bool SaveCapture(string filePath)
    {
        if (LastCaptureResult?.Screenshot != null)
        {
            return _clipboardService.SaveImage(LastCaptureResult.Screenshot, filePath);
        }
        return false;
    }

    private void OnRecordingStateChanged(object? sender, RecordingState state)
    {
        RecordingState = state;
        IsRecording = state == RecordingState.Recording;
    }

    private void OnRecordingDurationChanged(object? sender, TimeSpan duration)
    {
        RecordingDuration = duration.ToString(@"mm\:ss");
    }

    private void OnRecordingCompleted(object? sender, string filePath)
    {
        LastCaptureResult = new CaptureResult
        {
            Mode = SelectedMode,
            VideoPath = filePath,
            CaptureRegion = Rectangle.Empty
        };
        RequestShowPreview?.Invoke(this, EventArgs.Empty);
    }

    private void OnRecordingFailed(object? sender, string error)
    {
        System.Windows.MessageBox.Show($"Recording failed: {error}", "Error",
            System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Error);
        RequestShowMainWindow?.Invoke(this, EventArgs.Empty);
    }
}
