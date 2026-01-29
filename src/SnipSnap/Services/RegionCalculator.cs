using System.Drawing;

namespace SnipSnap.Services;

/// <summary>
/// Calculates physical pixel coordinates for screen recording regions.
/// Extracted for testability.
/// </summary>
public static class RegionCalculator
{
    /// <summary>
    /// Validates a recording region.
    /// </summary>
    /// <param name="region">The region to validate.</param>
    /// <exception cref="ArgumentException">Thrown when region has invalid dimensions.</exception>
    public static void ValidateRegion(Rectangle region)
    {
        if (region.Width <= 0)
            throw new ArgumentException($"Region width must be positive, got {region.Width}", nameof(region));

        if (region.Height <= 0)
            throw new ArgumentException($"Region height must be positive, got {region.Height}", nameof(region));
    }

    /// <summary>
    /// Calculates the physical pixel coordinates for a region relative to its containing screen.
    /// </summary>
    /// <param name="region">The region in logical/DIP coordinates (absolute screen position).</param>
    /// <param name="screenBounds">The bounds of the screen containing the region.</param>
    /// <param name="dpiScale">The DPI scale factor of the screen.</param>
    /// <returns>A rectangle in physical pixels, relative to the screen origin.</returns>
    public static Rectangle CalculatePhysicalRegion(Rectangle region, Rectangle screenBounds, double dpiScale)
    {
        if (dpiScale <= 0)
            throw new ArgumentException($"DPI scale must be positive, got {dpiScale}", nameof(dpiScale));

        // Convert absolute screen coordinates to coordinates relative to the display
        var relativeX = region.Left - screenBounds.Left;
        var relativeY = region.Top - screenBounds.Top;

        // Scale from DIPs to physical pixels
        var physicalX = (int)(relativeX * dpiScale);
        var physicalY = (int)(relativeY * dpiScale);
        var physicalWidth = (int)(region.Width * dpiScale);
        var physicalHeight = (int)(region.Height * dpiScale);

        return new Rectangle(physicalX, physicalY, physicalWidth, physicalHeight);
    }

    /// <summary>
    /// Checks if a region is completely contained within screen bounds.
    /// </summary>
    public static bool IsRegionWithinScreen(Rectangle region, Rectangle screenBounds)
    {
        return screenBounds.Contains(region);
    }

    /// <summary>
    /// Checks if a region intersects with screen bounds.
    /// </summary>
    public static bool RegionIntersectsScreen(Rectangle region, Rectangle screenBounds)
    {
        return region.IntersectsWith(screenBounds);
    }

    /// <summary>
    /// Clips a region to fit within screen bounds.
    /// </summary>
    /// <param name="region">The region to clip.</param>
    /// <param name="screenBounds">The screen bounds to clip to.</param>
    /// <returns>The clipped region, or Rectangle.Empty if no intersection.</returns>
    public static Rectangle ClipToScreen(Rectangle region, Rectangle screenBounds)
    {
        if (!region.IntersectsWith(screenBounds))
            return Rectangle.Empty;

        var clipped = Rectangle.Intersect(region, screenBounds);
        return clipped;
    }
}
