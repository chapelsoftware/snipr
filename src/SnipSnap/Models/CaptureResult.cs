using System.Drawing;
using System.Windows.Media.Imaging;

namespace SnipSnap.Models;

public class CaptureResult
{
    public CaptureMode Mode { get; init; }
    public BitmapSource? Screenshot { get; init; }
    public string? VideoPath { get; init; }
    public DateTime CapturedAt { get; init; } = DateTime.Now;
    public System.Drawing.Rectangle CaptureRegion { get; init; }

    public bool IsVideo => Mode.IsVideo();
    public bool IsScreenshot => Mode.IsScreenshot();
    public bool HasContent => Screenshot != null || !string.IsNullOrEmpty(VideoPath);
}
