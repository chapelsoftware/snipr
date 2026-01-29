using System.Drawing;
using System.Windows;
using System.Windows.Forms;
using System.Windows.Interop;
using System.Windows.Media;

namespace SnipSnap.Helpers;

public static class ScreenHelper
{
    public static Rectangle GetVirtualScreenBounds()
    {
        int left = SystemInformation.VirtualScreen.Left;
        int top = SystemInformation.VirtualScreen.Top;
        int width = SystemInformation.VirtualScreen.Width;
        int height = SystemInformation.VirtualScreen.Height;
        return new Rectangle(left, top, width, height);
    }

    public static Rectangle GetPrimaryScreenBounds()
    {
        var screen = Screen.PrimaryScreen;
        return screen?.Bounds ?? new Rectangle(0, 0, 1920, 1080);
    }

    public static Screen[] GetAllScreens() => Screen.AllScreens;

    public static Screen GetScreenFromPoint(System.Drawing.Point point) =>
        Screen.FromPoint(point);

    public static double GetDpiScale(Visual visual)
    {
        var source = PresentationSource.FromVisual(visual);
        return source?.CompositionTarget?.TransformToDevice.M11 ?? 1.0;
    }

    public static double GetDpiScaleForScreen(Screen screen)
    {
        using var g = Graphics.FromHwnd(IntPtr.Zero);
        return g.DpiX / 96.0;
    }

    public static Rectangle ScaleRectangle(Rectangle rect, double scale)
    {
        return new Rectangle(
            (int)(rect.X * scale),
            (int)(rect.Y * scale),
            (int)(rect.Width * scale),
            (int)(rect.Height * scale));
    }

    public static System.Windows.Point ToWpfPoint(System.Drawing.Point point) =>
        new(point.X, point.Y);

    public static System.Drawing.Point ToDrawingPoint(System.Windows.Point point) =>
        new((int)point.X, (int)point.Y);

    public static Rect ToWpfRect(Rectangle rect) =>
        new(rect.X, rect.Y, rect.Width, rect.Height);

    public static Rectangle ToDrawingRect(Rect rect) =>
        new((int)rect.X, (int)rect.Y, (int)rect.Width, (int)rect.Height);
}
