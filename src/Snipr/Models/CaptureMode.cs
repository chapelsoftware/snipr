namespace Snipr.Models;

public enum CaptureMode
{
    WindowSnip,
    RectangleSnip,
    FullscreenSnip,
    WindowVideo,
    RectangleVideo,
    FullscreenVideo
}

public static class CaptureModeExtensions
{
    public static bool IsVideo(this CaptureMode mode) =>
        mode is CaptureMode.WindowVideo or CaptureMode.RectangleVideo or CaptureMode.FullscreenVideo;

    public static bool IsScreenshot(this CaptureMode mode) =>
        mode is CaptureMode.WindowSnip or CaptureMode.RectangleSnip or CaptureMode.FullscreenSnip;

    public static bool RequiresWindowSelection(this CaptureMode mode) =>
        mode is CaptureMode.WindowSnip or CaptureMode.WindowVideo;

    public static bool RequiresRectangleSelection(this CaptureMode mode) =>
        mode is CaptureMode.RectangleSnip or CaptureMode.RectangleVideo;

    public static bool IsFullscreen(this CaptureMode mode) =>
        mode is CaptureMode.FullscreenSnip or CaptureMode.FullscreenVideo;

    public static string GetDisplayName(this CaptureMode mode) => mode switch
    {
        CaptureMode.WindowSnip => "Window Snip",
        CaptureMode.RectangleSnip => "Rectangle Snip",
        CaptureMode.FullscreenSnip => "Full-screen Snip",
        CaptureMode.WindowVideo => "Window Video",
        CaptureMode.RectangleVideo => "Rectangle Video",
        CaptureMode.FullscreenVideo => "Full-screen Video",
        _ => mode.ToString()
    };
}
