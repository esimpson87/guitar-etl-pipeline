using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using GuitarEtl.Models;

namespace GuitarEtl.Services;

public sealed partial class SreRemediationService
{
    public const decimal MinimumValidGibsonPriceUsd = 50.00m;
    private int _incidentSequence = 1000;

    [GeneratedRegex(@"[^0-9.\-]")]
    private static partial Regex NonNumericCurrencyRegex();

    public decimal? CoerceCurrencyDrift(string? rawPriceText, string modelName, List<SreIncidentRecord> incidents)
    {
        if (string.IsNullOrWhiteSpace(rawPriceText))
            return null;

        string trimmed = rawPriceText.Trim();
        if (decimal.TryParse(trimmed, NumberStyles.Number, CultureInfo.InvariantCulture, out decimal cleanValue))
            return cleanValue;

        string stripped = NonNumericCurrencyRegex().Replace(trimmed, string.Empty);
        if (decimal.TryParse(stripped, NumberStyles.AllowDecimalPoint | NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out decimal coercedValue))
        {
            incidents.Add(new SreIncidentRecord
            {
                IncidentId = NextIncidentId(),
                RawModelName = modelName,
                AnomalyType = "CURRENCY_SCHEMA_DRIFT",
                RemediationStatus = "AUTO_HEALED",
                RawAveragePrice = coercedValue,
                ResolutionSummary = $"Coerced non-numeric currency string '{trimmed}' to decimal {coercedValue:F2}."
            });
            return coercedValue;
        }

        return null;
    }

    public SreRemediationReport InspectAndRemediate(IEnumerable<GuitarModel> rawModels)
    {
        ArgumentNullException.ThrowIfNull(rawModels);

        var report = new SreRemediationReport();
        var seenModels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var model in rawModels)
        {
            if (string.IsNullOrWhiteSpace(model.model_name))
            {
                var quarantine = new SreIncidentRecord
                {
                    IncidentId = NextIncidentId(),
                    RawModelName = "<NULL_OR_EMPTY>",
                    AnomalyType = "MISSING_PRIMARY_KEY",
                    RemediationStatus = "QUARANTINED",
                    RawAveragePrice = model.average_price_usd,
                    RawLowestPrice = model.lowest_price_usd,
                    RawListingCount = model.listing_count,
                    ResolutionSummary = "Record missing canonical model_name; routed to Dead-Letter Queue."
                };
                report.Incidents.Add(quarantine);
                report.QuarantinedPayloads.Add(quarantine);
                continue;
            }

            string normalizedName = model.model_name.Trim();
            if (normalizedName != model.model_name)
            {
                model.model_name = normalizedName;
            }

            // Detect counterfeit or negative price anomalies
            if ((model.average_price_usd.HasValue && model.average_price_usd.Value < 0) ||
                (model.lowest_price_usd.HasValue && model.lowest_price_usd.Value < 0) ||
                (model.average_price_usd.HasValue && model.average_price_usd.Value > 0 && model.average_price_usd.Value < MinimumValidGibsonPriceUsd))
            {
                var quarantine = new SreIncidentRecord
                {
                    IncidentId = NextIncidentId(),
                    RawModelName = normalizedName,
                    AnomalyType = "PRICE_FLOOR_OR_NEGATIVE_ANOMALY",
                    RemediationStatus = "QUARANTINED",
                    RawAveragePrice = model.average_price_usd,
                    RawLowestPrice = model.lowest_price_usd,
                    RawListingCount = model.listing_count,
                    ResolutionSummary = $"Anomalous pricing detected (Avg={model.average_price_usd}, Low={model.lowest_price_usd}); routed to DLQ."
                };
                report.Incidents.Add(quarantine);
                report.QuarantinedPayloads.Add(quarantine);
                continue;
            }

            // Deduplicate identical model entries within the same batch
            if (!seenModels.Add(normalizedName))
            {
                report.Incidents.Add(new SreIncidentRecord
                {
                    IncidentId = NextIncidentId(),
                    RawModelName = normalizedName,
                    AnomalyType = "DUPLICATE_ENTITY_RECORD",
                    RemediationStatus = "AUTO_HEALED",
                    RawAveragePrice = model.average_price_usd,
                    RawLowestPrice = model.lowest_price_usd,
                    RawListingCount = model.listing_count,
                    ResolutionSummary = $"Deduplicated redundant chunk extraction for '{normalizedName}'."
                });
                continue;
            }

            // Auto-heal inverted lowest_price_usd > average_price_usd
            if (model.lowest_price_usd.HasValue &&
                model.average_price_usd.HasValue &&
                model.lowest_price_usd.Value > model.average_price_usd.Value)
            {
                (model.lowest_price_usd, model.average_price_usd) = (model.average_price_usd, model.lowest_price_usd);
                report.Incidents.Add(new SreIncidentRecord
                {
                    IncidentId = NextIncidentId(),
                    RawModelName = normalizedName,
                    AnomalyType = "INVERTED_PRICE_BOUNDS_DRIFT",
                    RemediationStatus = "AUTO_HEALED",
                    RawAveragePrice = model.average_price_usd,
                    RawLowestPrice = model.lowest_price_usd,
                    RawListingCount = model.listing_count,
                    ResolutionSummary = "Swapped inverted lowest_price_usd and average_price_usd bounds."
                });
            }

            report.CleanModels.Add(model);
        }

        return report;
    }

    public async Task WriteDeadLetterQueueAsync(
        IEnumerable<SreIncidentRecord> quarantinedRecords,
        string dlqFilePath = "sre_quarantine_dlq.jsonl")
    {
        await using var writer = new StreamWriter(dlqFilePath, append: false);
        foreach (var record in quarantinedRecords)
        {
            string line = JsonSerializer.Serialize(record);
            await writer.WriteLineAsync(line);
        }
    }

    private string NextIncidentId()
    {
        int id = ++_incidentSequence;
        return $"INC-SRE-{id}";
    }
}
