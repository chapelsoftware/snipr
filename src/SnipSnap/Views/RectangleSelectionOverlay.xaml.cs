using System.Drawing;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SnipSnap.Helpers;
using SnipSnap.Services;
using SnipSnap.ViewModels;
using KeyEventArgs = System.Windows.Input.KeyEventArgs;
using MouseEventArgs = System.Windows.Input.MouseEventArgs;
using Point = System.Windows.Point;
using Rectangle = System.Drawing.Rectangle;

namespace SnipSnap.Views;

public partial class RectangleSelectionOverlay : Window
{
    private readonly MainViewModel _mainViewModel;
    private readonly IScreenCaptureService _captureService;
    private Bitmap? _desktopBitmap;
    private Rectangle _virtualBounds;

    private bool _isSelecting;
    private Point _startPoint;
    private Point _currentPoint;

    public Rectangle SelectedRegion { get; private set; }
    public bool IsCancelled { get; private set; }

    public event EventHandler? SelectionCompleted;

    public RectangleSelectionOverlay(MainViewModel mainViewModel)
    {
        _mainViewModel = mainViewModel;
        _captureService = new ScreenCaptureService();

        // Capture desktop BEFORE showing overlay
        _virtualBounds = ScreenHelper.GetVirtualScreenBounds();
        _desktopBitmap = _captureService.CaptureDesktopBitmap();

        InitializeComponent();

        // Set window to cover all screens
        Left = _virtualBounds.Left;
        Top = _virtualBounds.Top;
        Width = _virtualBounds.Width;
        Height = _virtualBounds.Height;
        WindowState = WindowState.Normal;

        // Show desktop screenshot as background
        DesktopImage.Source = ConvertBitmapToBitmapSource(_desktopBitmap);

        // Initial full-screen dim
        UpdateDimOverlay(null);

        SourceInitialized += OnSourceInitialized;
        KeyDown += OnKeyDown;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        Win32Interop.ExcludeWindowFromCapture(hwnd);
    }

    private void OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        _isSelecting = true;
        _startPoint = e.GetPosition(DimCanvas);
        _currentPoint = _startPoint;
        DimCanvas.CaptureMouse();

        SelectionBorder.Visibility = Visibility.Visible;
        UpdateSelection();
    }

    private void OnMouseMove(object sender, MouseEventArgs e)
    {
        if (!_isSelecting) return;

        _currentPoint = e.GetPosition(DimCanvas);
        UpdateSelection();
    }

    private void OnMouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        if (!_isSelecting) return;

        _isSelecting = false;
        DimCanvas.ReleaseMouseCapture();

        // Calculate final selection rectangle
        var rect = GetSelectionRect();

        if (rect.Width < 5 || rect.Height < 5)
        {
            // Selection too small, cancel
            SelectionBorder.Visibility = Visibility.Collapsed;
            UpdateDimOverlay(null);
            return;
        }

        // Convert to screen coordinates (in DIPs/virtualized coordinates)
        SelectedRegion = new Rectangle(
            (int)rect.X + _virtualBounds.Left,
            (int)rect.Y + _virtualBounds.Top,
            (int)rect.Width,
            (int)rect.Height);

        SelectionCompleted?.Invoke(this, EventArgs.Empty);
    }

    private void UpdateSelection()
    {
        var rect = GetSelectionRect();

        Canvas.SetLeft(SelectionBorder, rect.X);
        Canvas.SetTop(SelectionBorder, rect.Y);
        SelectionBorder.Width = rect.Width;
        SelectionBorder.Height = rect.Height;

        UpdateDimOverlay(rect);
    }

    private Rect GetSelectionRect()
    {
        double x = Math.Min(_startPoint.X, _currentPoint.X);
        double y = Math.Min(_startPoint.Y, _currentPoint.Y);
        double width = Math.Abs(_currentPoint.X - _startPoint.X);
        double height = Math.Abs(_currentPoint.Y - _startPoint.Y);

        return new Rect(x, y, width, height);
    }

    private void UpdateDimOverlay(Rect? selectionRect)
    {
        var screenRect = new Rect(0, 0, Width, Height);

        if (selectionRect == null || selectionRect.Value.Width < 1 || selectionRect.Value.Height < 1)
        {
            // Full screen dim
            DimPath.Data = new RectangleGeometry(screenRect);
        }
        else
        {
            // Create a combined geometry: full screen minus selection rectangle
            var fullScreenGeometry = new RectangleGeometry(screenRect);
            var selectionGeometry = new RectangleGeometry(selectionRect.Value);

            DimPath.Data = new CombinedGeometry(
                GeometryCombineMode.Exclude,
                fullScreenGeometry,
                selectionGeometry);
        }
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            IsCancelled = true;
            SelectionCompleted?.Invoke(this, EventArgs.Empty);
        }
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
