using System.Drawing;
using CommunityToolkit.Mvvm.ComponentModel;
using Snipr.Models;
using Snipr.Services;

namespace Snipr.ViewModels;

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
        IsSelectionComplete = false;
        IsCancelled = false;
    }
}
