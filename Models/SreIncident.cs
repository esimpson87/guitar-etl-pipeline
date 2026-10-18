using System;
using System.Collections.Generic;

namespace GuitarEtl.Models;

public sealed record SreIncidentRecord
{
    public string IncidentId { get; init; } = string.Empty;
    public string RawModelName { get; init; } = string.Empty;
    public string AnomalyType { get; init; } = string.Empty;
    public string RemediationStatus { get; init; } = string.Empty; // AUTO_HEALED or QUARANTINED
    public decimal? RawAveragePrice { get; init; }
    public decimal? RawLowestPrice { get; init; }
    public int? RawListingCount { get; init; }
    public string ResolutionSummary { get; init; } = string.Empty;
    public DateTime OccurredAtUtc { get; init; } = DateTime.UtcNow;
}

public sealed class SreRemediationReport
{
    public List<GuitarModel> CleanModels { get; init; } = [];
    public List<SreIncidentRecord> Incidents { get; init; } = [];
    public List<SreIncidentRecord> QuarantinedPayloads { get; init; } = [];
}
