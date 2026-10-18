using System;
using System.ComponentModel;
using System.Globalization;
using System.Threading.Tasks;
using Microsoft.SemanticKernel;
using GuitarAgent.Domain.Abstractions;
using GuitarAgent.Domain.Models;
using GuitarAgent.Domain.Services;

namespace GuitarAgent.AI.Plugins;

public class GuitarDataPlugin
{
    private readonly IGuitarMarketRepository _repository;

    public GuitarDataPlugin(IGuitarMarketRepository repository)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
    }

    [KernelFunction, Description("Retrieves market statistics (average price, listing count) for a specific guitar model from BigQuery.")]
    public async Task<string> GetMarketStatsAsync(
        [Description("The canonical model name of the guitar (e.g., 'Les Paul Standard ''60s', 'Les Paul Custom (Vintage)', 'Les Paul Custom (Norlin Era)', 'Les Paul Custom (Modern)')")]
        string canonicalModel)
    {
        var stats = await _repository.GetMarketStatsAsync(canonicalModel);

        return string.Create(CultureInfo.InvariantCulture, $"""
            Market Stats for {stats.CanonicalModel}:
            - Listing Count: {stats.ListingCount}
            - Average Price: ${stats.AveragePrice:N2}
            """);
    }

    [KernelFunction, Description("Evaluates a live secondary-market guitar listing for fee-adjusted resale ROI and returns an arbitrage signal (STRONG_BUY, HOLD, or PASS).")]
    public async Task<string> EvaluateArbitrageOpportunityAsync(
        [Description("The canonical guitar model name")] string canonicalModel,
        [Description("The seller's asking price in USD")] decimal askPriceUsd,
        [Description("Inbound shipping cost in USD (defaults to $45.00)")] decimal inboundShippingUsd = 45.00m,
        [Description("Listing identifier (e.g., 'REV-LIVE-102')")] string listingId = "LIVE-EVAL",
        [Description("Marketplace source (e.g., 'Reverb', 'eBay')")] string source = "Reverb")
    {
        var stats = await _repository.GetMarketStatsAsync(canonicalModel);
        var analysis = ArbitrageCalculator.EvaluateDeal(
            listingId: listingId,
            canonicalModel: stats.CanonicalModel,
            source: source,
            askPriceUsd: askPriceUsd,
            inboundShippingUsd: inboundShippingUsd,
            avgSoldCompUsd: stats.AveragePrice);

        return string.Create(CultureInfo.InvariantCulture, $"""
            Arbitrage Appraisal [{analysis.ListingId}] — {analysis.CanonicalModel} ({analysis.Source}):
            - Ask + Inbound Ship: ${(analysis.AskPriceUsd + analysis.InboundShippingUsd):N2}
            - Bench Setup Allowance: ${analysis.BenchSetupAllowanceUsd:N2}
            - All-In Cost: ${analysis.AllInCostUsd:N2}
            - Star Schema Avg Comp: ${analysis.AvgSoldCompUsd:N2}
            - Reverb Fees (8.19% + $0.49): ${analysis.PlatformFeesUsd:N2}
            - Estimated Net Profit: ${analysis.EstimatedNetProfitUsd:N2}
            - Net ROI: {analysis.NetRoiPercent:N2}%
            - Signal: {analysis.Signal}
            """);
    }

    [KernelFunction, Description("Normalizes a guitar make, model, and production year into its canonical market era classification (e.g., Vintage, Norlin Era, Modern).")]
    public string NormalizeGuitarEra(
        [Description("Guitar brand/manufacturer (e.g., 'Gibson')")] string make,
        [Description("Raw model name (e.g., 'Les Paul Custom')")] string model,
        [Description("Optional 4-digit production year (e.g., 1974)")] int? productionYear = null)
    {
        var listing = new Listing
        {
            Make = make,
            Model = model,
            Year = productionYear
        };

        return EraNormalizer.Normalize(listing);
    }
}
