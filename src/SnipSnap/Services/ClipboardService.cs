using System.IO;
using System.Windows;
using System.Windows.Media.Imaging;
using Clipboard = System.Windows.Clipboard;

namespace SnipSnap.Services;

public class ClipboardService
{
    public void CopyImage(BitmapSource image)
    {
        Clipboard.SetImage(image);
    }

    public void CopyFilePath(string filePath)
    {
        var files = new System.Collections.Specialized.StringCollection { filePath };
        Clipboard.SetFileDropList(files);
    }

    public bool SaveImage(BitmapSource image, string filePath)
    {
        try
        {
            var extension = Path.GetExtension(filePath).ToLowerInvariant();
            BitmapEncoder encoder = extension switch
            {
                ".jpg" or ".jpeg" => new JpegBitmapEncoder { QualityLevel = 95 },
                ".gif" => new GifBitmapEncoder(),
                ".bmp" => new BmpBitmapEncoder(),
                _ => new PngBitmapEncoder()
            };

            encoder.Frames.Add(BitmapFrame.Create(image));

            using var stream = File.Create(filePath);
            encoder.Save(stream);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public string GetDefaultSavePath(bool isVideo)
    {
        var folder = isVideo
            ? Environment.GetFolderPath(Environment.SpecialFolder.MyVideos)
            : Environment.GetFolderPath(Environment.SpecialFolder.MyPictures);

        var subFolder = Path.Combine(folder, "SnipSnap");
        Directory.CreateDirectory(subFolder);

        var timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        var extension = isVideo ? ".mp4" : ".png";
        return Path.Combine(subFolder, $"Capture_{timestamp}{extension}");
    }
}
