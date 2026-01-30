using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Snipr.Helpers;
using Snipr.Models;
using Snipr.Services;
using Snipr.ViewModels;
using KeyEventArgs = System.Windows.Input.KeyEventArgs;
using MouseEventArgs = System.Windows.Input.MouseEventArgs;

namespace Snipr.Views;

public partial class FreeformSelectionOverlay : Window
{
    private readonly SelectionViewModel _viewModel;
    private readonly MainViewModel _mainViewModel;
    private readonly IScreenCaptureService _captureService;
    private readonly List<System.Windows.Point> _points = [];
    private bool _isDrawing;
    private Bitmap? _desktopBitmap;
    private System.Drawing.Rectangle _virtualBounds;

    public SelectionViewModel ViewModel => _viewModel;
    public event EventHandler? SelectionCompleted;

    public FreeformSelectionOverlay(MainViewModel mainViewModel)
    {
        _mainViewModel = mainViewModel;
        _captureService = new ScreenCaptureService();
        _viewModel = new SelectionViewModel(new WindowEnumerationService())
        {
            CaptureMode = mainViewModel.SelectedMode
        };

        // Capture desktop BEFORE showing overlay
        _virtualBounds = ScreenHelper.GetVirtualScreenBounds();
        _desktopBitmap = _captureService.CaptureDesktopBitmap();

        InitializeComponent();

        DataContext = _viewModel;

        // Set window to cover all screens
        Left = _virtualBounds.Left;
        Top = _virtualBounds.Top;
        Width = _virtualBounds.Width;
        Height = _virtualBounds.Height;
        WindowState = WindowState.Normal;

        // Show desktop screenshot as background
        DesktopImage.Source = ConvertBitmapToBitmapSource(_desktopBitmap);

        SourceInitialized += OnSourceInitialized;
        KeyDown += OnKeyDown;
        Loaded += OnLoaded;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        Win32Interop.ExcludeWindowFromCapture(hwnd);
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Position the desktop image to account for virtual screen offset
        Canvas.SetLeft(DesktopImage, 0);
        Canvas.SetTop(DesktopImage, 0);
    }

    private void OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        _isDrawing = true;
        _points.Clear();
        _points.Add(e.GetPosition(DrawingCanvas));
        DrawingCanvas.CaptureMouse();
        UpdateSelectionPath();
    }

    private void OnMouseMove(object sender, MouseEventArgs e)
    {
        if (!_isDrawing) return;

        var currentPoint = e.GetPosition(DrawingCanvas);

        // Only add point if it's far enough from the last point
        if (_points.Count == 0 || Distance(_points[^1], currentPoint) > 3)
        {
            _points.Add(currentPoint);
            UpdateSelectionPath();
        }
    }

    private void OnMouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        if (!_isDrawing) return;

        _isDrawing = false;
        DrawingCanvas.ReleaseMouseCapture();

        if (_points.Count < 3)
        {
            _points.Clear();
            UpdateSelectionPath();
            return;
        }

        // Close the path
        _points.Add(_points[0]);
        UpdateSelectionPath();

        // Create GraphicsPath from points
        var path = new GraphicsPath();
        var drawingPoints = _points.Select(p =>
            new System.Drawing.Point(
                (int)p.X + _virtualBounds.Left,
                (int)p.Y + _virtualBounds.Top))
            .ToArray();
        path.AddPolygon(drawingPoints);

        var bounds = System.Drawing.Rectangle.Round(path.GetBounds());

        _viewModel.SetFreeformSelection(path, bounds);
        SelectionCompleted?.Invoke(this, EventArgs.Empty);
    }

    private void UpdateSelectionPath()
    {
        if (_points.Count < 2)
        {
            SelectionPath.Data = null;
            return;
        }

        var geometry = new PathGeometry();
        var figure = new PathFigure { StartPoint = _points[0] };

        for (int i = 1; i < _points.Count; i++)
        {
            figure.Segments.Add(new LineSegment(_points[i], true));
        }

        geometry.Figures.Add(figure);
        SelectionPath.Data = geometry;
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            _viewModel.Cancel();
            SelectionCompleted?.Invoke(this, EventArgs.Empty);
        }
    }

    private static double Distance(System.Windows.Point a, System.Windows.Point b)
    {
        var dx = a.X - b.X;
        var dy = a.Y - b.Y;
        return Math.Sqrt(dx * dx + dy * dy);
    }

    private static BitmapSource ConvertBitmapToBitmapSource(Bitmap bitmap)
    {
        using var memory = new MemoryStream();
        bitmap.Save(memory, System.Drawing.Imaging.ImageFormat.Bmp);
        memory.Position = 0;

        var bitmapImage = new BitmapImage();
        bitmapImage.BeginInit();
        bitmapImage.StreamSource = memory;
        bitmapImage.CacheOption = BitmapCacheOption.OnLoad;
        bitmapImage.EndInit();
        bitmapImage.Freeze();

        return bitmapImage;
    }

    protected override void OnClosed(EventArgs e)
    {
        _desktopBitmap?.Dispose();
        base.OnClosed(e);
    }
}
