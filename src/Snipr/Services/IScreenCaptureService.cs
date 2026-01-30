using System.Drawing;
using System.Windows.Media.Imaging;

namespace Snipr.Services;

public interface IScreenCaptureService
{
    BitmapSource CaptureRegion(Rectangle region);
    BitmapSource CaptureWindow(IntPtr windowHandle);
    BitmapSource CaptureFullScreen();
    BitmapSource CaptureFreeform(Rectangle bounds, System.Drawing.Drawing2D.GraphicsPath clipPath);
    Bitmap CaptureDesktopBitmap();
}
