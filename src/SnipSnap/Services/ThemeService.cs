using System.Windows.Interop;
using SnipSnap.Helpers;
using Application = System.Windows.Application;
using Color = System.Windows.Media.Color;

namespace SnipSnap.Services;

public class ThemeService : IThemeService
{
    private IntPtr _hwndSource;
    private HwndSource? _source;

    public bool IsDarkMode { get; private set; }
    public System.Windows.Media.Color AccentColor { get; private set; }

    public event EventHandler<ThemeChangedEventArgs>? ThemeChanged;

    public ThemeService()
    {
        // Initialize with current system settings
        IsDarkMode = Win32Interop.IsWindowsDarkModeEnabled();
        AccentColor = Win32Interop.GetWindowsAccentColor();
    }

    public void Initialize(IntPtr mainWindowHandle)
    {
        _hwndSource = mainWindowHandle;
        _source = HwndSource.FromHwnd(mainWindowHandle);
        _source?.AddHook(WndProc);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        switch (msg)
        {
            case Win32Interop.WM_SETTINGCHANGE:
                // Check if theme changed
                var newDarkMode = Win32Interop.IsWindowsDarkModeEnabled();
                if (newDarkMode != IsDarkMode)
                {
                    IsDarkMode = newDarkMode;
                    OnThemeChanged();
                }
                break;

            case Win32Interop.WM_DWMCOLORIZATIONCOLORCHANGED:
                // Accent color changed
                var newAccentColor = Win32Interop.GetWindowsAccentColor();
                if (newAccentColor != AccentColor)
                {
                    AccentColor = newAccentColor;
                    OnThemeChanged();
                }
                break;
        }

        return IntPtr.Zero;
    }

    private void OnThemeChanged()
    {
        Application.Current?.Dispatcher.Invoke(() =>
        {
            ThemeChanged?.Invoke(this, new ThemeChangedEventArgs(IsDarkMode, AccentColor));
        });
    }

    public static Color AdjustBrightness(Color color, double factor)
    {
        // Convert to HSL-like adjustment
        double r = color.R / 255.0;
        double g = color.G / 255.0;
        double b = color.B / 255.0;

        if (factor > 0)
        {
            // Lighten
            r = r + (1 - r) * factor;
            g = g + (1 - g) * factor;
            b = b + (1 - b) * factor;
        }
        else
        {
            // Darken
            r = r * (1 + factor);
            g = g * (1 + factor);
            b = b * (1 + factor);
        }

        return Color.FromArgb(
            color.A,
            (byte)Math.Clamp(r * 255, 0, 255),
            (byte)Math.Clamp(g * 255, 0, 255),
            (byte)Math.Clamp(b * 255, 0, 255));
    }
}
