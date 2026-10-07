using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows;
using System.Windows.Media.Imaging;
using Snipr.Helpers;

namespace Snipr.Services;

public class ScreenCaptureService : IScreenCaptureService
{
    public BitmapSource CaptureRegion(Rectangle region)
    {
        if (region.Width <= 0 || region.Height <= 0)
            throw new ArgumentException("Region must have positive dimensions");

        using var bitmap = new Bitmap(region.Width, region.Height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.CopyFromScreen(region.Location, System.Drawing.Point.Empty, region.Size, CopyPixelOperation.SourceCopy);
        return ConvertToBitmapSource(bitmap);
    }

    public BitmapSource CaptureWindow(IntPtr windowHandle)
    {
        if (!Win32Interop.GetWindowRect(windowHandle, out var rect))
            throw new InvalidOperationException("Failed to get window bounds");

        var bounds = rect.ToRectangle();

        // Try DWM bounds first for accurate capture
        if (Win32Interop.DwmGetWindowAttribute(windowHandle, Win32Interop.DWMWA_EXTENDED_FRAME_BOUNDS,
            out Win32Interop.RECT dwmRect, System.Runtime.InteropServices.Marshal.SizeOf<Win32Interop.RECT>()) == 0)
        {
            bounds = dwmRect.ToRectangle();
        }

        using var bitmap = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(bitmap);

        // Try PrintWindow first for better window capture
        var hdc = graphics.GetHdc();
        bool success = Win32Interop.PrintWindow(windowHandle, hdc, Win32Interop.PW_RENDERFULLCONTENT);
        graphics.ReleaseHdc(hdc);

        if (!success)
        {
            // Fall back to screen capture
            graphics.CopyFromScreen(bounds.Location, System.Drawing.Point.Empty, bounds.Size, CopyPixelOperation.SourceCopy);
        }

        return ConvertToBitmapSource(bitmap);
    }

    public BitmapSource CaptureFullScreen()
    {
        var bounds = ScreenHelper.GetVirtualScreenBounds();
        return CaptureRegion(bounds);
    }

    public Bitmap CaptureDesktopBitmap()
    {
        var bounds = ScreenHelper.GetVirtualScreenBounds();
        var bitmap = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.CopyFromScreen(bounds.Location, System.Drawing.Point.Empty, bounds.Size, CopyPixelOperation.SourceCopy);
        return bitmap;
    }

    private static BitmapSource ConvertToBitmapSource(Bitmap bitmap)
    {
        using var memory = new MemoryStream();
        bitmap.Save(memory, ImageFormat.Png);
        memory.Position = 0;

        var bitmapImage = new BitmapImage();
        bitmapImage.BeginInit();
        bitmapImage.StreamSource = memory;
        bitmapImage.CacheOption = BitmapCacheOption.OnLoad;
        bitmapImage.EndInit();
        bitmapImage.Freeze();

        return bitmapImage;
    }
}
