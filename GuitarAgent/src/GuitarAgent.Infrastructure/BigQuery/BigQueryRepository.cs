using System;
using System.Threading.Tasks;
using Google.Cloud.BigQuery.V2;
using GuitarAgent.Domain.Abstractions;
using GuitarAgent.Domain.Models;

namespace GuitarAgent.Infrastructure.BigQuery;

public class BigQueryRepository : IGuitarMarketRepository
{
    private readonly BigQueryClient _client;

    public BigQueryRepository(string projectId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(projectId);
        _client = BigQueryClient.Create(projectId);
    }

    public async Task<MarketStats> GetMarketStatsAsync(string canonicalModel)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(canonicalModel);

        const string sql = @"
            SELECT 
                CAST(IFNULL(average_price, 0) AS FLOAT64) AS AveragePrice,
                CAST(IFNULL(listing_count, 0) AS INT64) AS ListingCount
            FROM `analytics.fact_market_pricing`
            WHERE REGEXP_REPLACE(LOWER(guitar_model), r'[^a-z0-9]', '') 
             LIKE REGEXP_REPLACE(LOWER(@searchTerm), r'[^a-z0-9%]', '')
            ORDER BY LENGTH(guitar_model) ASC, snapshot_timestamp DESC
            LIMIT 1";

        var parameters = new[]
        {
            new BigQueryParameter("searchTerm", BigQueryDbType.String, $"%{canonicalModel}%")
        };

        var results = await _client.ExecuteQueryAsync(sql, parameters);

        int listingCount = 0;
        decimal averagePrice = 0m;

        foreach (var row in results)
        {
            listingCount = Convert.ToInt32(row["ListingCount"]);
            averagePrice = Convert.ToDecimal(row["AveragePrice"]);
        }

        return new MarketStats
        {
            CanonicalModel = canonicalModel,
            ListingCount = listingCount,
            AveragePrice = averagePrice
        };
    }
}
