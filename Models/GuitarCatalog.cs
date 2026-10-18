using System.Collections.Generic;

namespace GuitarEtl.Models;

public sealed class GuitarCatalog
{
    public List<GuitarModel> models { get; set; } = [];
}

public sealed class GuitarModel
{
    public string? model_name { get; set; }
    public string? production_years { get; set; }
    public string? body_construction { get; set; }
    public List<string>? pickups { get; set; }
    public List<string>? notable_finishes { get; set; }

    // Secondary market pricing enriched from Reverb API
    public decimal? average_price_usd { get; set; }
    public decimal? lowest_price_usd { get; set; }
    public int? listing_count { get; set; }
}
