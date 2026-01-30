using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using Snipr.Helpers;
using Snipr.ViewModels;

namespace Snipr.Views;

public partial class RecordingIndicator : Window
{
    public RecordingIndicator(MainViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;

        // Position in top-right corner
        var workArea = SystemParameters.WorkArea;
        Left = workArea.Right - Width - 20;
        Top = workArea.Top + 20;

        SourceInitialized += OnSourceInitialized;

        // Close when recording stops
        viewModel.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(MainViewModel.IsRecording) && !viewModel.IsRecording)
            {
                Close();
            }
        };
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        Win32Interop.ExcludeWindowFromCapture(hwnd);
    }

    private void OnDragMove(object sender, MouseButtonEventArgs e)
    {
        if (e.LeftButton == MouseButtonState.Pressed)
        {
            DragMove();
        }
    }
}
