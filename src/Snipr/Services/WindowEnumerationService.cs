using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using Snipr.Helpers;

namespace Snipr.Services;

public record WindowInfo(IntPtr Handle, string Title, Rectangle Bounds, string ClassName);

public class WindowEnumerationService
{
    private readonly List<WindowInfo> _windows = [];
    private readonly uint _currentProcessId;

    public WindowEnumerationService()
    {
        _currentProcessId = (uint)Process.GetCurrentProcess().Id;
    }

    public IReadOnlyList<WindowInfo> GetVisibleWindows()
    {
        _windows.Clear();

        Win32Interop.EnumWindows((hWnd, _) =>
        {
            if (!Win32Interop.IsWindowVisible(hWnd))
                return true;

            // Skip cloaked windows (virtual desktops)
            if (Win32Interop.DwmGetWindowAttribute(hWnd, Win32Interop.DWMWA_CLOAKED,
                out bool cloaked, Marshal.SizeOf<bool>()) == 0 && cloaked)
                return true;

            var titleLength = Win32Interop.GetWindowTextLength(hWnd);
            if (titleLength == 0)
                return true;

            var titleBuilder = new StringBuilder(titleLength + 1);
            Win32Interop.GetWindowText(hWnd, titleBuilder, titleBuilder.Capacity);
            var title = titleBuilder.ToString();

            // Get class name
            var classBuilder = new StringBuilder(256);
            Win32Interop.GetClassName(hWnd, classBuilder, classBuilder.Capacity);
            var className = classBuilder.ToString();

            // Skip certain system windows
            if (className is "Progman" or "WorkerW" or "Shell_TrayWnd" or "Shell_SecondaryTrayWnd")
                return true;

            // Get window bounds using DWM for accurate bounds (includes shadows)
            Rectangle bounds;
            if (Win32Interop.DwmGetWindowAttribute(hWnd, Win32Interop.DWMWA_EXTENDED_FRAME_BOUNDS,
                out Win32Interop.RECT dwmRect, Marshal.SizeOf<Win32Interop.RECT>()) == 0)
            {
                bounds = dwmRect.ToRectangle();
            }
            else
            {
                Win32Interop.GetWindowRect(hWnd, out var rect);
                bounds = rect.ToRectangle();
            }

            // Skip windows with zero size
            if (bounds.Width <= 0 || bounds.Height <= 0)
                return true;

            _windows.Add(new WindowInfo(hWnd, title, bounds, className));
            return true;
        }, IntPtr.Zero);

        return _windows;
    }

    public WindowInfo? GetWindowAtPoint(Point point)
    {
        // Get all visible windows first, excluding our own process
        var visibleWindows = GetVisibleWindowsExcludingSelf();

        // Find the topmost window that contains this point
        foreach (var window in visibleWindows)
        {
            if (window.Bounds.Contains(point))
            {
                return window;
            }
        }

        return null;
    }

    private List<WindowInfo> GetVisibleWindowsExcludingSelf()
    {
        var windows = new List<WindowInfo>();

        Win32Interop.EnumWindows((hWnd, _) =>
        {
            if (!Win32Interop.IsWindowVisible(hWnd))
                return true;

            // Skip windows from our own process
            Win32Interop.GetWindowThreadProcessId(hWnd, out uint processId);
            if (processId == _currentProcessId)
                return true;

            // Skip cloaked windows (virtual desktops)
            if (Win32Interop.DwmGetWindowAttribute(hWnd, Win32Interop.DWMWA_CLOAKED,
                out bool cloaked, Marshal.SizeOf<bool>()) == 0 && cloaked)
                return true;

            var titleLength = Win32Interop.GetWindowTextLength(hWnd);
            if (titleLength == 0)
                return true;

            var titleBuilder = new StringBuilder(titleLength + 1);
            Win32Interop.GetWindowText(hWnd, titleBuilder, titleBuilder.Capacity);
            var title = titleBuilder.ToString();

            // Get class name
            var classBuilder = new StringBuilder(256);
            Win32Interop.GetClassName(hWnd, classBuilder, classBuilder.Capacity);
            var className = classBuilder.ToString();

            // Skip certain system windows
            if (className is "Progman" or "WorkerW" or "Shell_TrayWnd" or "Shell_SecondaryTrayWnd")
                return true;

            // Get window bounds using DWM for accurate bounds (includes shadows)
            Rectangle bounds;
            if (Win32Interop.DwmGetWindowAttribute(hWnd, Win32Interop.DWMWA_EXTENDED_FRAME_BOUNDS,
                out Win32Interop.RECT dwmRect, Marshal.SizeOf<Win32Interop.RECT>()) == 0)
            {
                bounds = dwmRect.ToRectangle();
            }
            else
            {
                Win32Interop.GetWindowRect(hWnd, out var rect);
                bounds = rect.ToRectangle();
            }

            // Skip windows with zero size
            if (bounds.Width <= 0 || bounds.Height <= 0)
                return true;

            windows.Add(new WindowInfo(hWnd, title, bounds, className));
            return true;
        }, IntPtr.Zero);

        return windows;
    }
}
