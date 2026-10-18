using System;
using GuitarAgent.Domain.Models;

namespace GuitarAgent.Domain.Services;

public static class ArbitrageCalculator
{
    public const decimal ReverbFeeRate = 0.0819m;
    public const decimal ReverbFixedFeeUsd = 0.49m;
    public const decimal DefaultBenchSetupUsd = 35.00m;

    public static ArbitrageAnalysis EvaluateDeal(
        string listingId,
        string canonicalModel,
        string source,
        decimal askPriceUsd,
        decimal inboundShippingUsd,
        decimal avgSoldCompUsd,
        decimal benchSetupAllowanceUsd = DefaultBenchSetupUsd)
    {
        if (askPriceUsd < 0)
            throw new ArgumentOutOfRangeException(nameof(askPriceUsd), "Ask price cannot be negative.");
        if (inboundShippingUsd < 0)
            throw new ArgumentOutOfRangeException(nameof(inboundShippingUsd), "Inbound shipping cannot be negative.");
        if (avgSoldCompUsd < 0)
            throw new ArgumentOutOfRangeException(nameof(avgSoldCompUsd), "Average sold comp cannot be negative.");

        decimal allInCost = Math.Round(askPriceUsd + inboundShippingUsd + benchSetupAllowanceUsd, 2, MidpointRounding.AwayFromZero);
        decimal platformFees = avgSoldCompUsd > 0
            ? Math.Round((avgSoldCompUsd * ReverbFeeRate) + ReverbFixedFeeUsd, 2, MidpointRounding.AwayFromZero)
            : 0m;
        decimal netProfit = Math.Round(avgSoldCompUsd - platformFees - allInCost, 2, MidpointRounding.AwayFromZero);
        decimal netRoiPercent = allInCost > 0
            ? Math.Round((netProfit / allInCost) * 100m, 2, MidpointRounding.AwayFromZero)
            : 0m;

        string signal = DetermineSignal(netRoiPercent, netProfit);

        return new ArbitrageAnalysis
        {
            ListingId = listingId,
            CanonicalModel = canonicalModel,
            Source = source,
            AskPriceUsd = askPriceUsd,
            InboundShippingUsd = inboundShippingUsd,
            BenchSetupAllowanceUsd = benchSetupAllowanceUsd,
            AllInCostUsd = allInCost,
            AvgSoldCompUsd = avgSoldCompUsd,
            PlatformFeesUsd = platformFees,
            EstimatedNetProfitUsd = netProfit,
            NetRoiPercent = netRoiPercent,
            Signal = signal
        };
    }

    private static string DetermineSignal(decimal netRoiPercent, decimal netProfitUsd)
    {
        if (netRoiPercent >= 15.0m && netProfitUsd >= 100.0m)
            return "STRONG_BUY";

        if (netRoiPercent >= 5.0m && netProfitUsd > 0m)
            return "HOLD";

        return "PASS";
    }
}
