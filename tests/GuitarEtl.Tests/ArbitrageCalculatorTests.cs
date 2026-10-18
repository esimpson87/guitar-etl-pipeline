using GuitarAgent.Domain.Services;

namespace GuitarEtl.Tests;

public class ArbitrageCalculatorTests
{
    [Theory]
    [InlineData("REV-LIVE-102", "Gibson Les Paul Standard ('60s)", "Reverb (IN)", 1595.00, 45.00, 2187.50, 1675.00, 179.65, 332.85, 19.87, "STRONG_BUY")]
    [InlineData("EBAY-LIVE-101", "Fender Stratocaster (Am Pro II)", "eBay (KY)", 960.00, 45.00, 1355.00, 1040.00, 111.46, 203.54, 19.57, "STRONG_BUY")]
    [InlineData("EBAY-LIVE-103", "Ibanez RG550 Genesis (MIJ)", "eBay (OH)", 590.00, 45.00, 862.50, 670.00, 71.13, 121.37, 18.11, "STRONG_BUY")]
    public void EvaluateDeal_MatchesVerifiedExecutionBenchmarks(
        string listingId,
        string canonicalModel,
        string source,
         decimal askPrice,
        decimal shipping,
        decimal avgComp,
        decimal expectedAllIn,
        decimal expectedFees,
        decimal expectedNetProfit,
        decimal expectedRoi,
        string expectedSignal)
    {
        var result = ArbitrageCalculator.EvaluateDeal(
            listingId: listingId,
            canonicalModel: canonicalModel,
            source: source,
            askPriceUsd: askPrice,
            inboundShippingUsd: shipping,
            avgSoldCompUsd: avgComp);

        Assert.Equal(expectedAllIn, result.AllInCostUsd);
        Assert.Equal(expectedFees, result.PlatformFeesUsd);
        Assert.Equal(expectedNetProfit, result.EstimatedNetProfitUsd);
        Assert.Equal(expectedRoi, result.NetRoiPercent);
        Assert.Equal(expectedSignal, result.Signal);
    }

    [Fact]
    public void EvaluateDeal_WhenMarginIsNegative_ReturnsPassSignal()
    {
        var result = ArbitrageCalculator.EvaluateDeal(
            listingId: "REV-OVERPRICED-01",
            canonicalModel: "Gibson Les Paul Studio",
            source: "Reverb",
            askPriceUsd: 1300.00m,
            inboundShippingUsd: 50.00m,
            avgSoldCompUsd: 1150.00m);

        Assert.True(result.EstimatedNetProfitUsd < 0);
        Assert.Equal("PASS", result.Signal);
    }
}
