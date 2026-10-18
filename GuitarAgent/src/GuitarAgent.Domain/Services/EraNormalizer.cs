using GuitarAgent.Domain.Models;

namespace GuitarAgent.Domain.Services;

public static class EraNormalizer
{
    public static string Normalize(Listing listing)
    {
        if (listing.Model.Contains("Standard '60s", StringComparison.OrdinalIgnoreCase))
        {
            return "Les Paul Standard '60s";
        }

        if (listing.Model.Contains("Les Paul Custom", StringComparison.OrdinalIgnoreCase))
        {
            if (listing.Year == null)
            {
                return listing.Model;
            }
            
            return listing.Year switch
            {
                < 1970 => "Les Paul Custom (Vintage)",
                >= 1970 and <= 1985 => "Les Paul Custom (Norlin Era)",
                > 1985 => "Les Paul Custom (Modern)",
                _ => listing.Model
            };
        }

        return listing.Model;
    }
}