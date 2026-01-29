using System.Drawing;
using System.Drawing.Drawing2D;
using CommunityToolkit.Mvvm.ComponentModel;
using SnipSnap.Models;
using SnipSnap.Services;

namespace SnipSnap.ViewModels;

public partial class SelectionViewModel : ViewModelBase
{
    private readonly WindowEnumerationService _windowService;

    [ObservableProperty]
    private CaptureMode _captureMode;

    [ObservableProperty]
    private WindowInfo? _hoveredWindow;

    [ObservableProperty]
    private WindowInfo? _selectedWindow;

    [ObservableProperty]
    private Rectangle _selectedRegion;

    [ObservableProperty]
    private GraphicsPath? _freeformPath;

    [ObservableProperty]
    private bool _isSelectionComplete;

    [ObservableProperty]
    private bool _isCancelled;

    public SelectionViewModel(WindowEnumerationService windowService)
    {
        _windowService = windowService;
    }

    public void UpdateHoveredWindow(Point screenPoint)
    {
        HoveredWindow = _windowService.GetWindowAtPoint(screenPoint);
    }

    public void SelectCurrentWindow()
    {
        if (HoveredWindow != null)
        {
            SelectedWindow = HoveredWindow;
            SelectedRegion = HoveredWindow.Bounds;
            IsSelectionComplete = true;
        }
    }

    public void SetFreeformSelection(GraphicsPath path, Rectangle bounds)
    {
        FreeformPath = path;
        SelectedRegion = bounds;
        IsSelectionComplete = true;
    }

    public void Cancel()
    {
        IsCancelled = true;
        IsSelectionComplete = true;
    }

    public void Reset()
    {
        HoveredWindow = null;
        SelectedWindow = null;
        SelectedRegion = Rectangle.Empty;
        FreeformPath?.Dispose();
        FreeformPath = null;
        IsSelectionComplete = false;
        IsCancelled = false;
    }
}
