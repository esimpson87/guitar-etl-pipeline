namespace GuitarAgent.Domain.Models;

public record ArbitrageAnalysis
{
    public string ListingId { get; init; } = string.Empty;
    public string CanonicalModel { get; init; } = string.Empty;
    public string Source { get; init; } = string.Empty;
    public decimal AskPriceUsd { get; init; }
    public decimal InboundShippingUsd { get; init; }
    public decimal BenchSetupAllowanceUsd { get; init; }
    public decimal AllInCostUsd { get; init; }
    public decimal AvgSoldCompUsd { get; init; }
    public decimal PlatformFeesUsd { get; init; }
    public decimal EstimatedNetProfitUsd { get; init; }
    public decimal NetRoiPercent { get; init; }
    public string Signal { get; init; } = "PASS";
}
