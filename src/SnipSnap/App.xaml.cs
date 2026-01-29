using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using Microsoft.Extensions.DependencyInjection;
using SnipSnap.Models;
using SnipSnap.Services;
using SnipSnap.ViewModels;
using SnipSnap.Views;
using Application = System.Windows.Application;
using Color = System.Windows.Media.Color;

namespace SnipSnap;

public partial class App : Application
{
    private ServiceProvider? _serviceProvider;
    private IThemeService? _themeService;

    public static IServiceProvider Services { get; private set; } = null!;

    private void OnStartup(object sender, StartupEventArgs e)
    {
        var services = new ServiceCollection();
        ConfigureServices(services);
        _serviceProvider = services.BuildServiceProvider();
        Services = _serviceProvider;

        // Initialize theme before showing any windows
        _themeService = _serviceProvider.GetRequiredService<IThemeService>();
        _themeService.ThemeChanged += OnThemeChanged;
        ApplyTheme(_themeService.IsDarkMode, _themeService.AccentColor);

        var mainWindow = _serviceProvider.GetRequiredService<MainWindow>();
        mainWindow.Show();
    }

    private static void ConfigureServices(IServiceCollection services)
    {
        // Services
        services.AddSingleton<IThemeService, ThemeService>();
        services.AddSingleton<IScreenCaptureService, ScreenCaptureService>();
        services.AddSingleton<IVideoRecordingService, VideoRecordingService>();
        services.AddSingleton<ClipboardService>();
        services.AddSingleton<WindowEnumerationService>();

        // ViewModels
        services.AddSingleton<MainViewModel>();

        // Views
        services.AddSingleton<MainWindow>();
    }

    private void OnThemeChanged(object? sender, ThemeChangedEventArgs e)
    {
        Dispatcher.Invoke(() => ApplyTheme(e.IsDarkMode, e.AccentColor));
    }

    private void ApplyTheme(bool isDarkMode, Color accentColor)
    {
        var resources = Resources;

        // Find and remove existing theme dictionary
        ResourceDictionary? existingTheme = null;
        foreach (var dict in resources.MergedDictionaries)
        {
            if (dict.Source?.OriginalString.Contains("Theme") == true)
            {
                existingTheme = dict;
                break;
            }
        }
        if (existingTheme != null)
        {
            resources.MergedDictionaries.Remove(existingTheme);
        }

        // Load appropriate theme
        var themeUri = new Uri(isDarkMode
            ? "Resources/ThemeDark.xaml"
            : "Resources/ThemeLight.xaml",
            UriKind.Relative);
        var themeDictionary = new ResourceDictionary { Source = themeUri };
        resources.MergedDictionaries.Insert(0, themeDictionary);

        // Apply dynamic accent colors
        resources["AccentBrush"] = new SolidColorBrush(accentColor);
        resources["AccentHoverBrush"] = new SolidColorBrush(
            ThemeService.AdjustBrightness(accentColor, isDarkMode ? 0.15 : -0.1));
        resources["AccentPressedBrush"] = new SolidColorBrush(
            ThemeService.AdjustBrightness(accentColor, isDarkMode ? 0.25 : -0.2));
    }

    protected override void OnExit(ExitEventArgs e)
    {
        if (_themeService != null)
        {
            _themeService.ThemeChanged -= OnThemeChanged;
        }
        _serviceProvider?.Dispose();
        base.OnExit(e);
    }
}

// Converters
public class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is true ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is Visibility.Visible;
}

public class InverseBoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is true ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is Visibility.Collapsed;
}

public class InverseBoolConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is true ? false : true;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is true ? false : true;
}

public class CaptureModeToStringConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is CaptureMode mode ? mode.GetDisplayName() : string.Empty;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        throw new NotImplementedException();
}
