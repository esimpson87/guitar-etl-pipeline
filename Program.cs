using System.ClientModel;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using DotNetEnv;
using Google.Apis.Auth.OAuth2;
using Google.Cloud.Storage.V1;
using GuitarEtl.Models;
using GuitarEtl.Services;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Logging;
using OpenAI;
using OpenAI.Chat;
using Polly;

Env.Load();

using var loggerFactory = LoggerFactory.Create(builder =>
{
    builder
        .AddJsonConsole(options =>
        {
            options.IncludeScopes = true;
            options.TimestampFormat = "yyyy-MM-ddTHH:mm:ss.fffZ";
            options.UseUtcTimestamp = true;
        })
        .SetMinimumLevel(LogLevel.Information);
});

ILogger logger = loggerFactory.CreateLogger("GuitarEtl.Pipeline");

string reverbApiKey = Environment.GetEnvironmentVariable("REVERB_API_KEY")
    ?? throw new InvalidOperationException("Missing REVERB_API_KEY environment variable.");
string sqlConnectionString = Environment.GetEnvironmentVariable("SQL_CONNECTION_STRING")
    ?? throw new InvalidOperationException("Missing SQL_CONNECTION_STRING environment variable.");
string gcpKeyPath = Environment.GetEnvironmentVariable("GCP_KEY_PATH")
    ?? throw new InvalidOperationException("Missing GCP_KEY_PATH environment variable.");

const string WikipediaEndpoint =
    "https://en.wikipedia.org/w/api.php?action=query&format=json&titles=Gibson_Les_Paul&prop=extracts&explaintext=1";
const string LiteLlmEndpoint = "http://localhost:4000/v1";
const string LiteLlmApiKey = "sk-local-dev-key";
const string TargetModel = "enterprise-chat";

const string SystemPrompt =
    """
    You are a highly accurate data extraction pipeline. Your task is to parse unstructured historical text about electric guitars and extract the specifications into a strict JSON array.

    Extract the following data points for each distinct guitar model mentioned:
    - model_name (string)
    - production_years (string)
    - body_construction (string)
    - pickups (array of strings)
    - notable_finishes (array of strings)

    Rules:
    1. If a detail is not mentioned in the text, return null for that field.
    2. Group variations of a model under the same entry if they share the primary name.
    3. Output ONLY valid JSON matching this schema: { "models": [ { "model_name": "string", "production_years": "string", "body_construction": "string", "pickups": ["string"], "notable_finishes": ["string"] } ] }
    4. If no guitar specifications are found in the text, you MUST return an empty array: { "models": [] }
    """;

var httpRetryPipeline = ResiliencePipelineFactory.CreateHttpPipeline(logger, "ExternalApiClient");
var sreService = new SreRemediationService();

try
{
    logger.LogInformation("=== Multi-Cloud Guitar Market ELT & SRE Self-Healing Pipeline starting ===");

    string wikipediaExtract = await ExtractAsync(WikipediaEndpoint, httpRetryPipeline, logger);
    string llmJson = await TransformAsync(wikipediaExtract, SystemPrompt, logger);
    GuitarCatalog rawCatalog = await DeserializeCatalogAsync(llmJson, logger);

    logger.LogInformation("Enriching {ModelCount} extracted models with secondary market pricing from Reverb...", rawCatalog.models.Count);
    foreach (var model in rawCatalog.models)
    {
        if (!string.IsNullOrWhiteSpace(model.model_name))
        {
            var pricing = await GetMarketPricingAsync("Gibson", model.model_name, reverbApiKey, httpRetryPipeline, sreService, logger);
            model.average_price_usd = pricing.average;
            model.lowest_price_usd = pricing.lowest;
            model.listing_count = pricing.count;
        }
    }

    // Execute Event-Driven SRE Self-Healing & Dead-Letter Queue Validation
    SreRemediationReport sreReport = sreService.InspectAndRemediate(rawCatalog.models);
    logger.LogInformation(
        "SRE Self-Healing completed: {CleanCount} clean models, {IncidentCount} incidents logged, {QuarantinedCount} payloads quarantined.",
        sreReport.CleanModels.Count,
        sreReport.Incidents.Count,
        sreReport.QuarantinedPayloads.Count);

    if (sreReport.QuarantinedPayloads.Count > 0)
    {
        await sreService.WriteDeadLetterQueueAsync(sreReport.QuarantinedPayloads);
        logger.LogWarning("Wrote {QuarantinedCount} poisoned payloads to sre_quarantine_dlq.jsonl", sreReport.QuarantinedPayloads.Count);
    }

    var verifiedCatalog = new GuitarCatalog { models = sreReport.CleanModels };

    await EnsureDatabaseAndTableExistAsync(sqlConnectionString, logger);
    await LoadToSqlAsync(verifiedCatalog, sqlConnectionString, logger);
    await StageToDataLakeAsync(verifiedCatalog, gcpKeyPath, logger);

    logger.LogInformation("=== ELT pipeline completed successfully ===");
}
catch (Exception ex)
{
    logger.LogCritical(ex, "Unhandled pipeline failure: {ErrorMessage}", ex.Message);
    Environment.ExitCode = 1;
}

static async Task<string> ExtractAsync(
    string endpoint,
    ResiliencePipeline<HttpResponseMessage> resiliencePipeline,
    ILogger logger)
{
    logger.LogInformation("Requesting Gibson Les Paul extract from MediaWiki API...");

    using var httpClient = new HttpClient();
    httpClient.DefaultRequestHeaders.UserAgent.ParseAdd(
        "GuitarEtl/2.0 (Multi-Cloud .NET 8 ELT; SRE Resilient Client)");

    using HttpResponseMessage response = await resiliencePipeline.ExecuteAsync(
        async ct => await httpClient.GetAsync(endpoint, ct));

    string payload = await response.Content.ReadAsStringAsync();
    response.EnsureSuccessStatusCode();

    using JsonDocument document = JsonDocument.Parse(payload);
    JsonElement pages = document.RootElement.GetProperty("query").GetProperty("pages");

    foreach (JsonProperty page in pages.EnumerateObject())
    {
        if (page.Value.TryGetProperty("missing", out _))
        {
            throw new InvalidOperationException($"Wikipedia reported the page as missing. Page key: {page.Name}");
        }

        if (!page.Value.TryGetProperty("extract", out JsonElement extractElement))
        {
            throw new InvalidOperationException($"MediaWiki JSON did not contain an 'extract' field for page key {page.Name}.");
        }

        string? articleText = extractElement.GetString();
        if (string.IsNullOrWhiteSpace(articleText))
        {
            throw new InvalidOperationException("Wikipedia extract was empty.");
        }

        logger.LogInformation("Retrieved full Wikipedia article ({CharCount} characters).", articleText.Length);
        return articleText;
    }

    throw new InvalidOperationException("MediaWiki JSON contained no pages.");
}

static async Task<string> TransformAsync(string wikipediaText, string systemPrompt, ILogger logger)
{
    logger.LogInformation("Initializing LLM entity extraction via LiteLLM proxy ({TargetModel})...", TargetModel);

    var clientOptions = new OpenAIClientOptions
    {
        Endpoint = new Uri(LiteLlmEndpoint),
        NetworkTimeout = TimeSpan.FromSeconds(60)
    };

    var chatClient = new ChatClient(
        model: TargetModel,
        credential: new ApiKeyCredential(LiteLlmApiKey),
        options: clientOptions);

    var completionOptions = new ChatCompletionOptions
    {
        ResponseFormat = ChatResponseFormat.CreateJsonObjectFormat()
    };

    var allModels = new List<GuitarModel>();
    const int maxChunkSize = 10_000;
    int startIndex = 0;
    int chunkCounter = 1;

    while (startIndex < wikipediaText.Length)
    {
        int maxEnd = Math.Min(startIndex + maxChunkSize, wikipediaText.Length);
        int currentLength = maxEnd - startIndex;

        if (maxEnd < wikipediaText.Length)
        {
            int lastSpace = wikipediaText.LastIndexOf(' ', maxEnd - 1, currentLength);
            if (lastSpace > startIndex)
            {
                currentLength = lastSpace - startIndex;
            }
        }

        string chunk = wikipediaText.Substring(startIndex, currentLength).Trim();
        int nextStartIndex = startIndex + currentLength;

        while (nextStartIndex < wikipediaText.Length && char.IsWhiteSpace(wikipediaText[nextStartIndex]))
        {
            nextStartIndex++;
        }

        startIndex = nextStartIndex;
        if (string.IsNullOrWhiteSpace(chunk)) continue;

        logger.LogInformation("Processing text chunk {ChunkIndex} ({ChunkLength} chars)...", chunkCounter, chunk.Length);

        string userMessage =
            $"Extract the guitar specifications from this text and return ONLY a valid JSON object matching the requested schema. Do not include conversational text or markdown:\n\n{chunk}";

        var messages = new List<ChatMessage>
        {
            new SystemChatMessage(systemPrompt),
            new UserChatMessage(userMessage)
        };

        try
        {
            ChatCompletion completion = await chatClient.CompleteChatAsync(messages, completionOptions);

            if (completion.Content is not null && completion.Content.Count > 0)
            {
                string chunkJson = completion.Content[0].Text;
                GuitarCatalog? chunkCatalog = JsonSerializer.Deserialize<GuitarCatalog>(chunkJson);
                if (chunkCatalog?.models is not null && chunkCatalog.models.Count > 0)
                {
                    logger.LogInformation("Chunk {ChunkIndex} extracted {Count} model(s).", chunkCounter, chunkCatalog.models.Count);
                    allModels.AddRange(chunkCatalog.models);
                }
            }
        }
        catch (ClientResultException ex) when (ex.Status == 400)
        {
            logger.LogWarning("Chunk {ChunkIndex} returned HTTP 400 from JSON validator. Skipping chunk.", chunkCounter);
        }
        catch (JsonException ex)
        {
            logger.LogWarning(ex, "Failed to parse JSON from chunk {ChunkIndex}.", chunkCounter);
        }

        chunkCounter++;
    }

    var combinedCatalog = new GuitarCatalog { models = allModels };
    return JsonSerializer.Serialize(combinedCatalog);
}

static Task<GuitarCatalog> DeserializeCatalogAsync(string llmJson, ILogger logger)
{
    GuitarCatalog? catalog = JsonSerializer.Deserialize<GuitarCatalog>(llmJson);
    if (catalog?.models is null)
    {
        throw new InvalidOperationException("Deserialization produced a null catalog or models list.");
    }

    logger.LogInformation("Deserialized {ModelCount} total guitar model(s) from LiteLLM.", catalog.models.Count);
    return Task.FromResult(catalog);
}

static async Task EnsureDatabaseAndTableExistAsync(string connectionString, ILogger logger)
{
    logger.LogInformation("Ensuring Azure SQL GuitarModels and MarketPricing tables exist...");

    await using var appConnection = new SqlConnection(connectionString);
    await appConnection.OpenAsync();

    await using var createTableCommand = appConnection.CreateCommand();
    createTableCommand.CommandText =
        """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = N'GuitarModels')
        BEGIN
            CREATE TABLE dbo.GuitarModels
            (
                Id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ModelName NVARCHAR(255) NULL,
                ProductionYears NVARCHAR(255) NULL,
                BodyConstruction NVARCHAR(MAX) NULL,
                Pickups NVARCHAR(MAX) NULL,
                NotableFinishes NVARCHAR(MAX) NULL
            );
        END
        """;
    await createTableCommand.ExecuteNonQueryAsync();

    await using var createPricingTableCommand = appConnection.CreateCommand();
    createPricingTableCommand.CommandText =
        """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = N'MarketPricing')
        BEGIN
            CREATE TABLE dbo.MarketPricing
            (
                Id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ModelName NVARCHAR(255) NOT NULL,
                AveragePriceUSD DECIMAL(10,2) NULL,
                LowestPriceUSD DECIMAL(10,2) NULL,
                ListingCount INT NULL,
                ScrapedAt DATETIME DEFAULT GETDATE()
            );
        END
        """;
    await createPricingTableCommand.ExecuteNonQueryAsync();
}

static async Task LoadToSqlAsync(GuitarCatalog catalog, string connectionString, ILogger logger)
{
    logger.LogInformation("Inserting {Count} verified guitar models into Azure SQL...", catalog.models.Count);

    int inserted = 0;
    await using var connection = new SqlConnection(connectionString);
    await connection.OpenAsync();

    foreach (GuitarModel model in catalog.models)
    {
        await using var command = connection.CreateCommand();
        command.CommandText =
            """
            INSERT INTO dbo.GuitarModels
                (ModelName, ProductionYears, BodyConstruction, Pickups, NotableFinishes)
            VALUES
                (@ModelName, @ProductionYears, @BodyConstruction, @Pickups, @NotableFinishes);
            """;

        command.Parameters.AddWithValue("@ModelName", (object?)model.model_name ?? DBNull.Value);
        command.Parameters.AddWithValue("@ProductionYears", (object?)model.production_years ?? DBNull.Value);
        command.Parameters.AddWithValue("@BodyConstruction", (object?)model.body_construction ?? DBNull.Value);
        command.Parameters.AddWithValue("@Pickups", (object?)SerializeList(model.pickups) ?? DBNull.Value);
        command.Parameters.AddWithValue("@NotableFinishes", (object?)SerializeList(model.notable_finishes) ?? DBNull.Value);

        inserted += await command.ExecuteNonQueryAsync();

        await using var pricingCommand = connection.CreateCommand();
        pricingCommand.CommandText =
            """
            INSERT INTO dbo.MarketPricing
                (ModelName, AveragePriceUSD, LowestPriceUSD, ListingCount)
            VALUES
                (@ModelName, @AveragePrice, @LowestPrice, @ListingCount);
            """;

        pricingCommand.Parameters.AddWithValue("@ModelName", (object?)model.model_name ?? DBNull.Value);
        pricingCommand.Parameters.AddWithValue("@AveragePrice", (object?)model.average_price_usd ?? DBNull.Value);
        pricingCommand.Parameters.AddWithValue("@LowestPrice", (object?)model.lowest_price_usd ?? DBNull.Value);
        pricingCommand.Parameters.AddWithValue("@ListingCount", (object?)model.listing_count ?? DBNull.Value);

        await pricingCommand.ExecuteNonQueryAsync();
    }

    logger.LogInformation("Successfully inserted {InsertedCount} row(s) into Azure SQL.", inserted);
}

static string? SerializeList(List<string>? values) =>
    values is null ? null : JsonSerializer.Serialize(values);

static async Task<(decimal? average, decimal? lowest, int count)> GetMarketPricingAsync(
    string make,
    string modelName,
    string token,
    ResiliencePipeline<HttpResponseMessage> resiliencePipeline,
    SreRemediationService sreService,
    ILogger logger)
{
    using var httpClient = new HttpClient();
    httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}");
    httpClient.DefaultRequestHeaders.Add("Accept-Version", "3.0");
    httpClient.DefaultRequestHeaders.Add("Accept", "application/hal+json");
    httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("GuitarEtl/2.0");

    string query = Uri.EscapeDataString(modelName);
    string endpoint = $"https://api.reverb.com/api/listings/all?make={make}&query={query}&condition=used&per_page=50";

    try
    {
        using HttpResponseMessage response = await resiliencePipeline.ExecuteAsync(
            async ct => await httpClient.GetAsync(endpoint, ct));
        response.EnsureSuccessStatusCode();

        string payload = await response.Content.ReadAsStringAsync();
        using JsonDocument document = JsonDocument.Parse(payload);

        if (!document.RootElement.TryGetProperty("listings", out JsonElement listings))
        {
            return (null, null, 0);
        }

        int count = listings.GetArrayLength();
        if (count == 0) return (null, null, 0);

        decimal total = 0;
        decimal lowest = decimal.MaxValue;
        int validPrices = 0;
        var driftIncidents = new List<SreIncidentRecord>();

        foreach (JsonElement listing in listings.EnumerateArray())
        {
            if (listing.TryGetProperty("price", out JsonElement priceNode) &&
                priceNode.TryGetProperty("amount", out JsonElement amountNode))
            {
                decimal? parsedPrice = sreService.CoerceCurrencyDrift(amountNode.GetString(), modelName, driftIncidents);
                if (parsedPrice.HasValue && parsedPrice.Value > 0)
                {
                    total += parsedPrice.Value;
                    validPrices++;
                    if (parsedPrice.Value < lowest) lowest = parsedPrice.Value;
                }
            }
        }

        if (validPrices == 0) return (null, null, 0);

        decimal average = Math.Round(total / validPrices, 2);
        logger.LogInformation(
            "Reverb pricing for {Make} {Model}: {Count} listings, Avg=${Avg:F2}, Low=${Low:F2}",
            make, modelName, validPrices, average, lowest);

        return (average, lowest, validPrices);
    }
    catch (Exception ex)
    {
        logger.LogWarning(ex, "Failed to pull Reverb data for {ModelName}.", modelName);
        return (null, null, 0);
    }
}

static async Task StageToDataLakeAsync(GuitarCatalog catalog, string gcpKeyPath, ILogger logger)
{
    const string localFilePath = "raw_extract.jsonl";
    const string bucketName = "guitar-etl-raw-landing";

    await using (var file = new StreamWriter(localFilePath))
    {
        foreach (var model in catalog.models)
        {
            var record = new
            {
                Model = model,
                ExtractedAt = DateTime.UtcNow
            };

            string jsonLine = JsonSerializer.Serialize(record);
            await file.WriteLineAsync(jsonLine);
        }
    }

    string jsonCreds = await File.ReadAllTextAsync(gcpKeyPath);
    var credential = CredentialFactory.FromJson<ServiceAccountCredential>(jsonCreds).ToGoogleCredential();
    using var storageClient = await StorageClient.CreateAsync(credential);

    string objectName = $"raw/guitar_market_{DateTime.UtcNow:yyyyMMdd_HHmmss}.jsonl";

    await using (var fileStream = File.OpenRead(localFilePath))
    {
        await storageClient.UploadObjectAsync(
            bucketName,
            objectName,
            "application/json",
            fileStream);
    }

    logger.LogInformation("Successfully staged {ObjectName} to GCS bucket {BucketName}.", objectName, bucketName);
}