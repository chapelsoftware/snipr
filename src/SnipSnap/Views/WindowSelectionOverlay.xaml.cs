using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using SnipSnap.Helpers;
using SnipSnap.Models;
using SnipSnap.Services;
using SnipSnap.ViewModels;
using KeyEventArgs = System.Windows.Input.KeyEventArgs;
using MouseEventArgs = System.Windows.Input.MouseEventArgs;

namespace SnipSnap.Views;

public partial class WindowSelectionOverlay : Window
{
    private readonly SelectionViewModel _viewModel;
    private readonly MainViewModel _mainViewModel;

    public SelectionViewModel ViewModel => _viewModel;
    public event EventHandler? SelectionCompleted;

    public WindowSelectionOverlay(MainViewModel mainViewModel)
    {
        InitializeComponent();

        _mainViewModel = mainViewModel;
        _viewModel = new SelectionViewModel(new WindowEnumerationService())
        {
            CaptureMode = mainViewModel.SelectedMode
        };

        DataContext = _viewModel;

        // Set window to cover all screens
        var bounds = ScreenHelper.GetVirtualScreenBounds();
        Left = bounds.Left;
        Top = bounds.Top;
        Width = bounds.Width;
        Height = bounds.Height;
        WindowState = WindowState.Normal;

        SourceInitialized += OnSourceInitialized;
        KeyDown += OnKeyDown;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        Win32Interop.ExcludeWindowFromCapture(hwnd);
    }

    private void OnMouseMove(object sender, MouseEventArgs e)
    {
        var screenPoint = PointToScreen(e.GetPosition(this));
        var drawingPoint = new System.Drawing.Point((int)screenPoint.X, (int)screenPoint.Y);

        _viewModel.UpdateHoveredWindow(drawingPoint);

        if (_viewModel.HoveredWindow != null)
        {
            var bounds = _viewModel.HoveredWindow.Bounds;
            var virtualBounds = ScreenHelper.GetVirtualScreenBounds();

            // Convert to local coordinates
            Canvas.SetLeft(HighlightBorder, bounds.Left - virtualBounds.Left);
            Canvas.SetTop(HighlightBorder, bounds.Top - virtualBounds.Top);
            HighlightBorder.Width = bounds.Width;
            HighlightBorder.Height = bounds.Height;
            HighlightBorder.Visibility = Visibility.Visible;
        }
        else
        {
            HighlightBorder.Visibility = Visibility.Collapsed;
        }
    }

    private void OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        _viewModel.SelectCurrentWindow();

        if (_viewModel.IsSelectionComplete)
        {
            SelectionCompleted?.Invoke(this, EventArgs.Empty);
        }
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            _viewModel.Cancel();
            SelectionCompleted?.Invoke(this, EventArgs.Empty);
        }
    }
}
