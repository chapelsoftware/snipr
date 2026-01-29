using System.Drawing;
using System.Windows.Forms;

namespace SnipSnap.Services;

/// <summary>
/// Abstracts screen/display information for testability.
/// </summary>
public interface IScreenProvider
{
    ScreenInfo GetScreenFromRectangle(Rectangle region);
    IReadOnlyList<ScreenInfo> GetAllScreens();
    Rectangle GetVirtualScreenBounds();
}

/// <summary>
/// Information about a display screen.
/// </summary>
public record ScreenInfo(
    string DeviceName,
    Rectangle Bounds,
    double DpiScale
);

/// <summary>
/// Default implementation using System.Windows.Forms.Screen.
/// </summary>
public class ScreenProvider : IScreenProvider
{
    public ScreenInfo GetScreenFromRectangle(Rectangle region)
    {
        var screen = Screen.FromRectangle(region);
        var dpiScale = GetDpiScaleForScreen(screen);
        return new ScreenInfo(screen.DeviceName, screen.Bounds, dpiScale);
    }

    public IReadOnlyList<ScreenInfo> GetAllScreens()
    {
        return Screen.AllScreens
            .Select(s => new ScreenInfo(s.DeviceName, s.Bounds, GetDpiScaleForScreen(s)))
            .ToList();
    }

    public Rectangle GetVirtualScreenBounds()
    {
        return SystemInformation.VirtualScreen;
    }

    private static double GetDpiScaleForScreen(Screen screen)
    {
        using var g = Graphics.FromHwnd(IntPtr.Zero);
        return g.DpiX / 96.0;
    }
}
