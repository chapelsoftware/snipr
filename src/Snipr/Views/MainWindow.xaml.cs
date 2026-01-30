using System.IO;
using System.Windows;
using System.Windows.Interop;
using Snipr.Helpers;
using Snipr.Models;
using Snipr.Services;
using Snipr.ViewModels;
using MessageBox = System.Windows.MessageBox;
using SaveFileDialog = Microsoft.Win32.SaveFileDialog;

namespace Snipr.Views;

public partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;
    private readonly IThemeService _themeService;
    private WindowSelectionOverlay? _windowOverlay;
    private RectangleSelectionOverlay? _rectangleOverlay;
    private RecordingIndicator? _recordingIndicator;

    private bool _isPreviewVisible;
    private bool _videoSaved;
    private string? _tempVideoPath;
    private double _previousWidth;
    private double _previousHeight;

    public MainWindow(MainViewModel viewModel, IThemeService themeService)
    {
        InitializeComponent();
        _viewModel = viewModel;
        _themeService = themeService;
        DataContext = viewModel;

        _viewModel.RequestWindowSelection += OnRequestWindowSelection;
        _viewModel.RequestRectangleSelection += OnRequestRectangleSelection;
        _viewModel.RequestShowPreview += OnRequestShowPreview;
        _viewModel.RequestHideMainWindow += OnRequestHideMainWindow;
        _viewModel.RequestShowMainWindow += OnRequestShowMainWindow;
        _viewModel.PropertyChanged += OnViewModelPropertyChanged;

        SourceInitialized += OnSourceInitialized;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        Win32Interop.ExcludeWindowFromCapture(hwnd);
        _themeService.Initialize(hwnd);
    }

    private void OnRequestWindowSelection(object? sender, EventArgs e)
    {
        _windowOverlay = new WindowSelectionOverlay(_viewModel);
        _windowOverlay.SelectionCompleted += OnWindowSelectionCompleted;
        _windowOverlay.Show();
    }

    private async void OnWindowSelectionCompleted(object? sender, EventArgs e)
    {
        if (_windowOverlay == null) return;

        var vm = _windowOverlay.ViewModel;
        _windowOverlay.Close();
        _windowOverlay = null;

        if (vm.IsCancelled)
        {
            Show();
            return;
        }

        if (vm.SelectedWindow != null)
        {
            await _viewModel.HandleWindowSelectionAsync(vm.SelectedWindow);
            if (_viewModel.SelectedMode.IsVideo())
            {
                ShowRecordingIndicator();
                return; // Don't show main window during video recording
            }
        }

        Show();
    }

    private void OnRequestRectangleSelection(object? sender, EventArgs e)
    {
        _rectangleOverlay = new RectangleSelectionOverlay(_viewModel);
        _rectangleOverlay.SelectionCompleted += OnRectangleSelectionCompleted;
        _rectangleOverlay.Show();
    }

    private async void OnRectangleSelectionCompleted(object? sender, EventArgs e)
    {
        if (_rectangleOverlay == null) return;

        var isCancelled = _rectangleOverlay.IsCancelled;
        var selectedRegion = _rectangleOverlay.SelectedRegion;
        _rectangleOverlay.Close();
        _rectangleOverlay = null;

        if (isCancelled)
        {
            Show();
            return;
        }

        if (!selectedRegion.IsEmpty)
        {
            await _viewModel.HandleRectangleSelectionAsync(selectedRegion);
            if (_viewModel.SelectedMode.IsVideo())
            {
                ShowRecordingIndicator();
                return; // Don't show main window during video recording
            }
        }

        Show();
    }

    private void OnRequestShowPreview(object? sender, EventArgs e)
    {
        HideRecordingIndicator();
        ShowPreview();
    }

    private void ShowPreview()
    {
        var result = _viewModel.LastCaptureResult;
        if (result == null) return;

        _videoSaved = false;
        _tempVideoPath = null;

        // Store current size before expanding
        if (!_isPreviewVisible)
        {
            _previousWidth = Width;
            _previousHeight = Height;
        }

        if (result.IsScreenshot && result.Screenshot != null)
        {
            ScreenshotImage.Source = result.Screenshot;
            ScreenshotImage.Visibility = Visibility.Visible;
            VideoPlayer.Visibility = Visibility.Collapsed;

            var pixelWidth = result.Screenshot.PixelWidth;
            var pixelHeight = result.Screenshot.PixelHeight;
            InfoText.Text = $"{pixelWidth} x {pixelHeight} pixels";

            // Resize window to fit image (with max constraints)
            var maxWidth = SystemParameters.WorkArea.Width * 0.8;
            var maxHeight = SystemParameters.WorkArea.Height * 0.8;
            var aspectRatio = (double)pixelWidth / pixelHeight;

            var newWidth = Math.Min(pixelWidth + 32, maxWidth);
            var newHeight = Math.Min((newWidth - 32) / aspectRatio + 120, maxHeight);

            Width = Math.Max(newWidth, 450);
            Height = newHeight;
        }
        else if (result.IsVideo && !string.IsNullOrEmpty(result.VideoPath))
        {
            _tempVideoPath = result.VideoPath;
            VideoPlayer.Source = new Uri(result.VideoPath);
            VideoPlayer.Visibility = Visibility.Visible;
            ScreenshotImage.Visibility = Visibility.Collapsed;

            var fileInfo = new FileInfo(result.VideoPath);
            var sizeKb = fileInfo.Length / 1024.0;
            var sizeDisplay = sizeKb > 1024
                ? $"{sizeKb / 1024:F1} MB"
                : $"{sizeKb:F0} KB";
            InfoText.Text = $"Video - {sizeDisplay}";

            // Set a reasonable size for video preview
            Width = 640;
            Height = 480;
        }

        PreviewArea.Visibility = Visibility.Visible;
        PreviewToolbar.Visibility = Visibility.Visible;
        _isPreviewVisible = true;

        // Allow resizing when previewing
        ResizeMode = ResizeMode.CanResize;

        // Center window on screen
        Left = (SystemParameters.WorkArea.Width - Width) / 2;
        Top = (SystemParameters.WorkArea.Height - Height) / 2;
    }

    private void HidePreview()
    {
        VideoPlayer.Source = null;
        ScreenshotImage.Source = null;
        ScreenshotImage.Visibility = Visibility.Collapsed;
        VideoPlayer.Visibility = Visibility.Collapsed;
        PreviewArea.Visibility = Visibility.Collapsed;
        PreviewToolbar.Visibility = Visibility.Collapsed;

        // Clean up temp video if not saved
        if (!_videoSaved && !string.IsNullOrEmpty(_tempVideoPath) && File.Exists(_tempVideoPath))
        {
            try
            {
                File.Delete(_tempVideoPath);
            }
            catch
            {
                // Ignore deletion errors
            }
        }

        _tempVideoPath = null;
        _isPreviewVisible = false;

        // Restore compact size and disable resizing
        ResizeMode = ResizeMode.NoResize;
        Width = 450;
        Height = 85;
    }

    private void OnCopyClick(object sender, RoutedEventArgs e)
    {
        _viewModel.CopyToClipboard();

        // Brief visual feedback
        var button = sender as System.Windows.Controls.Button;
        if (button != null)
        {
            var originalContent = button.Content;
            button.Content = "Copied!";
            var timer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromSeconds(1)
            };
            timer.Tick += (_, _) =>
            {
                button.Content = originalContent;
                timer.Stop();
            };
            timer.Start();
        }
    }

    private void OnSaveClick(object sender, RoutedEventArgs e)
    {
        var result = _viewModel.LastCaptureResult;
        if (result == null) return;

        if (result.IsScreenshot)
        {
            var dialog = new SaveFileDialog
            {
                Filter = "PNG Image|*.png|JPEG Image|*.jpg|Bitmap Image|*.bmp|GIF Image|*.gif",
                DefaultExt = ".png",
                FileName = $"Screenshot_{DateTime.Now:yyyyMMdd_HHmmss}"
            };

            if (dialog.ShowDialog() == true)
            {
                if (_viewModel.SaveCapture(dialog.FileName))
                {
                    MessageBox.Show("Image saved successfully!", "Saved", MessageBoxButton.OK, MessageBoxImage.Information);
                }
                else
                {
                    MessageBox.Show("Failed to save image.", "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                }
            }
        }
        else if (result.IsVideo && !string.IsNullOrEmpty(result.VideoPath))
        {
            var dialog = new SaveFileDialog
            {
                Filter = "MP4 Video|*.mp4",
                DefaultExt = ".mp4",
                FileName = $"Recording_{DateTime.Now:yyyyMMdd_HHmmss}"
            };

            if (dialog.ShowDialog() == true)
            {
                try
                {
                    VideoPlayer.Source = null;
                    File.Copy(result.VideoPath, dialog.FileName, true);
                    _videoSaved = true;
                    MessageBox.Show("Video saved successfully!", "Saved", MessageBoxButton.OK, MessageBoxImage.Information);
                    VideoPlayer.Source = new Uri(result.VideoPath);
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Failed to save video: {ex.Message}", "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                }
            }
        }
    }

    private void OnDiscardClick(object sender, RoutedEventArgs e)
    {
        HidePreview();
    }

    private void OnRequestHideMainWindow(object? sender, EventArgs e)
    {
        Hide();
    }

    private void OnRequestShowMainWindow(object? sender, EventArgs e)
    {
        Show();
        Activate();
    }

    private void OnViewModelPropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainViewModel.IsRecording))
        {
            if (!_viewModel.IsRecording)
            {
                HideRecordingIndicator();
            }
        }
    }

    private void ShowRecordingIndicator()
    {
        _recordingIndicator?.Close();
        _recordingIndicator = new RecordingIndicator(_viewModel);
        _recordingIndicator.Show();
    }

    private void HideRecordingIndicator()
    {
        _recordingIndicator?.Close();
        _recordingIndicator = null;
    }

    protected override void OnClosed(EventArgs e)
    {
        _viewModel.RequestWindowSelection -= OnRequestWindowSelection;
        _viewModel.RequestRectangleSelection -= OnRequestRectangleSelection;
        _viewModel.RequestShowPreview -= OnRequestShowPreview;
        _viewModel.RequestHideMainWindow -= OnRequestHideMainWindow;
        _viewModel.RequestShowMainWindow -= OnRequestShowMainWindow;

        _windowOverlay?.Close();
        _rectangleOverlay?.Close();
        _recordingIndicator?.Close();

        // Clean up temp video if still exists
        if (!_videoSaved && !string.IsNullOrEmpty(_tempVideoPath) && File.Exists(_tempVideoPath))
        {
            try
            {
                File.Delete(_tempVideoPath);
            }
            catch
            {
                // Ignore
            }
        }

        base.OnClosed(e);
    }
}
