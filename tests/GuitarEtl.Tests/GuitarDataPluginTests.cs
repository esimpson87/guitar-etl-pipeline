using System.Threading.Tasks;
using GuitarAgent.AI.Plugins;
using GuitarAgent.Domain.Abstractions;
using GuitarAgent.Domain.Models;

namespace GuitarEtl.Tests;

public class GuitarDataPluginTests
{
    private sealed class StubMarketRepository : IGuitarMarketRepository
    {
        public Task<MarketStats> GetMarketStatsAsync(string canonicalModel)
        {
            return Task.FromResult(new MarketStats
            {
                CanonicalModel = canonicalModel,
                ListingCount = 42,
                AveragePrice = 2187.50m
            });
        }
    }

    [Fact]
    public async Task GetMarketStatsAsync_ReturnsFormattedGroundedMetrics()
    {
        var plugin = new GuitarDataPlugin(new StubMarketRepository());

        string response = await plugin.GetMarketStatsAsync("Les Paul Standard '60s");

        Assert.Contains("Les Paul Standard '60s", response);
        Assert.Contains("Listing Count: 42", response);
        Assert.Contains("$2,187.50", response);
    }

    [Fact]
    public async Task EvaluateArbitrageOpportunityAsync_ReturnsStrongBuyAppraisal()
    {
        var plugin = new GuitarDataPlugin(new StubMarketRepository());

        string response = await plugin.EvaluateArbitrageOpportunityAsync(
            canonicalModel: "Gibson Les Paul Standard ('60s)",
            askPriceUsd: 1595.00m,
            inboundShippingUsd: 45.00m,
            listingId: "REV-LIVE-102",
            source: "Reverb (IN)");

        Assert.Contains("REV-LIVE-102", response);
        Assert.Contains("All-In Cost: $1,675.00", response);
        Assert.Contains("Estimated Net Profit: $332.85", response);
        Assert.Contains("Net ROI: 19.87%", response);
        Assert.Contains("Signal: STRONG_BUY", response);
    }
}
