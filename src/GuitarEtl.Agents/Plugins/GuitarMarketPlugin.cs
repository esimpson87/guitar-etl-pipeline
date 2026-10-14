using System.ComponentModel;
using System.Net.Http.Json;
using Microsoft.SemanticKernel;

namespace GuitarEtlPipeline.Agents.Plugins;

public sealed class GuitarMarketPlugin(HttpClient httpClient)
{
    [KernelFunction("extract_reverb_listings")]
    [Description("Fetches active and sold guitar listings from the Reverb Developer Hub API and normalizes pricing.")]
    public async Task<string> ExtractReverbListingsAsync(
        [Description("Canonical search query, e.g., 'Fender American Professional II Stratocaster'")] string query,
        [Description("Maximum number of listings to ingest")] int limit = 25,
        CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            $"https://api.reverb.com/api/listings/all?query={Uri.EscapeDataString(query)}&per_page={limit}");
        request.Headers.Add("Accept-Version", "3.0");

        var response = await httpClient.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(ct);
    }
}
