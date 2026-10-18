using System.Collections.Generic;
using GuitarEtl.Models;
using GuitarEtl.Services;

namespace GuitarEtl.Tests;

public class SreRemediationServiceTests
{
    [Theory]
    [InlineData("$925.00 USD", 925.00)]
    [InlineData("USD 1,595.50", 1595.50)]
    [InlineData("  2187.50 ", 2187.50)]
    public void CoerceCurrencyDrift_ParsesFormattedCurrencyAndLogsAutoHeal(string rawInput, decimal expectedPrice)
    {
        var service = new SreRemediationService();
        var incidents = new List<SreIncidentRecord>();

        decimal? result = service.CoerceCurrencyDrift(rawInput, "Les Paul Standard '60s", incidents);

        Assert.NotNull(result);
        Assert.Equal(expectedPrice, result.Value);
    }

    [Fact]
    public void InspectAndRemediate_QuarantinesPoisonedPayloadsAndHealsDrift()
    {
        var service = new SreRemediationService();
        var rawBatch = new List<GuitarModel>
        {
            // 1. Valid record
            new()
            {
                model_name = "Les Paul Standard '50s",
                average_price_usd = 2250.00m,
                lowest_price_usd = 1899.00m,
                listing_count = 24
            },
            // 2. Duplicate entity record (should be deduplicated & auto-healed)
            new()
            {
                model_name = "Les Paul Standard '50s",
                average_price_usd = 2250.00m,
                lowest_price_usd = 1899.00m,
                listing_count = 24
            },
            // 3. Inverted price bounds drift (lowest > average -> should swap & auto-heal)
            new()
            {
                model_name = "Les Paul Custom",
                average_price_usd = 2900.00m,
                lowest_price_usd = 3500.00m,
                listing_count = 12
            },
            // 4. Counterfeit / negative price anomaly (should be quarantined to DLQ)
            new()
            {
                model_name = "Chibson Fake Les Paul",
                average_price_usd = -45.00m,
                lowest_price_usd = -100.00m,
                listing_count = 1
            },
            // 5. Missing primary key (should be quarantined to DLQ)
            new()
            {
                model_name = "   ",
                average_price_usd = 1200.00m,
                lowest_price_usd = 900.00m,
                listing_count = 3
            }
        };

        SreRemediationReport report = service.InspectAndRemediate(rawBatch);

        Assert.Equal(2, report.CleanModels.Count);
        Assert.Equal(2, report.QuarantinedPayloads.Count);
        Assert.Equal(4, report.Incidents.Count);

        // Verify inverted bounds were swapped on Les Paul Custom
        var custom = Assert.Single(report.CleanModels, m => m.model_name == "Les Paul Custom");
        Assert.Equal(3500.00m, custom.average_price_usd);
        Assert.Equal(2900.00m, custom.lowest_price_usd);

        // Verify incident IDs follow INC-SRE-* schema
        Assert.All(report.Incidents, inc => Assert.StartsWith("INC-SRE-", inc.IncidentId));
    }
}
