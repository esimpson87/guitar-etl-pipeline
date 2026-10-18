namespace GuitarAgent.Domain.Models;

public record MarketStats
{
    public string CanonicalModel { get; init; } = string.Empty;
    public int ListingCount { get; init; }
    public decimal AveragePrice { get; init; }
}