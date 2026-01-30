namespace Snipr.Services;

public class ThemeChangedEventArgs : EventArgs
{
    public bool IsDarkMode { get; }
    public System.Windows.Media.Color AccentColor { get; }

    public ThemeChangedEventArgs(bool isDarkMode, System.Windows.Media.Color accentColor)
    {
        IsDarkMode = isDarkMode;
        AccentColor = accentColor;
    }
}

public interface IThemeService
{
    bool IsDarkMode { get; }
    System.Windows.Media.Color AccentColor { get; }
    event EventHandler<ThemeChangedEventArgs>? ThemeChanged;
    void Initialize(IntPtr mainWindowHandle);
}
