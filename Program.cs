using Google.Apis.Auth.OAuth2;
using Google.Cloud.Storage.V1;
using System.IO;
using System.ClientModel;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using OpenAI;
using OpenAI.Chat;
using DotNetEnv; // Added for environment variables

// Load the .env file
Env.Load();

// Read credentials securely from the environment
string ReverbApiKey = Environment.GetEnvironmentVariable("REVERB_API_KEY") 
    ?? throw new InvalidOperationException("Missing Reverb API Key");
string SqlConnectionString = Environment.GetEnvironmentVariable("SQL_CONNECTION_STRING") 
    ?? throw new InvalidOperationException("Missing SQL Connection String");
string gcpKeyPath = Environment.GetEnvironmentVariable("GCP_KEY_PATH") 
    ?? throw new InvalidOperationException("Missing GCP Key Path");

// Non-sensitive configuration can remain hardcoded
const string WikipediaEndpoint =
    "https://en.wikipedia.org/w/api.php?action=query&format=json&titles=Gibson_Les_Paul&prop=extracts&explaintext=1";
const string LiteLlmEndpoint = "http://localhost:4000/v1";
const string LiteLlmApiKey = "sk-local-dev-key"; // Safe to leave as it is a local proxy key
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

try
{
    Console.WriteLine("=== Gibson Les Paul ETL pipeline starting ===");

    string wikipediaExtract = await ExtractAsync(WikipediaEndpoint);
    string llmJson = await TransformAsync(wikipediaExtract, SystemPrompt);
    GuitarCatalog catalog = await LoadAsync(llmJson);

    Console.WriteLine("[ENRICH] Fetching secondary market data from Reverb...");
    foreach (var model in catalog.models)
    {
        if (!string.IsNullOrWhiteSpace(model.model_name))
        {
            var pricing = await GetMarketPricingAsync("Gibson", model.model_name, ReverbApiKey);
            model.average_price_usd = pricing.average;
            model.lowest_price_usd = pricing.lowest;
            model.listing_count = pricing.count;
            
            // Artificial 1-second delay to prevent Reverb rate-limiting
            await Task.Delay(1000); 
        }
    }

    await EnsureDatabaseAndTableExistAsync();
    await LoadToSqlAsync(catalog);
    await StageToDataLakeAsync(catalog);

    Console.WriteLine("=== ETL pipeline completed ===");
}
catch (Exception ex)
{
    Console.Error.WriteLine($"[FATAL] Unhandled pipeline failure: {ex.GetType().Name}: {ex.Message}");
    Console.Error.WriteLine(ex.StackTrace);
    Environment.ExitCode = 1;
}

static async Task<string> ExtractAsync(string endpoint)
{
    Console.WriteLine("[EXTRACT] Requesting Gibson Les Paul extract from MediaWiki API...");

    try
    {
        using var httpClient = new HttpClient();
        httpClient.DefaultRequestHeaders.UserAgent.ParseAdd(
            "GuitarEtl/1.0 (local .NET 8 ETL; contact: local-dev)");

        using HttpResponseMessage response = await httpClient.GetAsync(endpoint);
        string payload = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            Console.Error.WriteLine(
                $"[EXTRACT] HTTP {(int)response.StatusCode} {response.ReasonPhrase} from MediaWiki API. Body preview: {Truncate(payload, 500)}");
            response.EnsureSuccessStatusCode();
        }

        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement pages = document.RootElement.GetProperty("query").GetProperty("pages");

        foreach (JsonProperty page in pages.EnumerateObject())
        {
            if (page.Value.TryGetProperty("missing", out _))
            {
                throw new InvalidOperationException(
                    $"[EXTRACT] Wikipedia reported the page as missing. Page key: {page.Name}");
            }

            if (!page.Value.TryGetProperty("extract", out JsonElement extractElement))
            {
                throw new InvalidOperationException(
                    $"[EXTRACT] MediaWiki JSON did not contain an 'extract' field for page key {page.Name}.");
            }

            string? articleText = extractElement.GetString();
            if (string.IsNullOrWhiteSpace(articleText))
            {
                throw new InvalidOperationException("[EXTRACT] Wikipedia extract was empty.");
            }

            Console.WriteLine($"[EXTRACT] Retrieved full article ({articleText.Length} characters).");
            return articleText;
        }

        throw new InvalidOperationException("[EXTRACT] MediaWiki JSON contained no pages.");
    }
    catch (HttpRequestException ex)
    {
        Console.Error.WriteLine($"[EXTRACT] HTTP transport failure calling MediaWiki API: {ex.Message}");
        throw;
    }
    catch (TaskCanceledException ex)
    {
        Console.Error.WriteLine($"[EXTRACT] Timed out calling MediaWiki API: {ex.Message}");
        throw;
    }
    catch (JsonException ex)
    {
        Console.Error.WriteLine($"[EXTRACT] Failed to parse MediaWiki JSON with JsonDocument: {ex.Message}");
        throw;
    }
}

static async Task<string> TransformAsync(string wikipediaText, string systemPrompt)
{
    Console.WriteLine("[TRANSFORM] Initializing transformation with LiteLLM proxy (enterprise-chat)...");

    try
    {
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

            Console.WriteLine($"[TRANSFORM] Processing chunk {chunkCounter} ({chunk.Length} chars)...");

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
                    Console.WriteLine($"[TRANSFORM] Received {chunkJson.Length} characters of JSON from chunk {chunkCounter}.");

                    GuitarCatalog? chunkCatalog = JsonSerializer.Deserialize<GuitarCatalog>(chunkJson);
                    if (chunkCatalog?.models is not null && chunkCatalog.models.Count > 0)
                    {
                        Console.WriteLine($"[TRANSFORM] Chunk {chunkCounter} extracted {chunkCatalog.models.Count} model(s).");
                        allModels.AddRange(chunkCatalog.models);
                    }
                    else
                    {
                        Console.WriteLine($"[TRANSFORM] Chunk {chunkCounter} contained no guitar models.");
                    }
                }
            }
            catch (ClientResultException ex) when (ex.Status == 400)
            {
                // Catch JSON validation crashes for empty/irrelevant chunks and continue the loop
                Console.Error.WriteLine($"[TRANSFORM] Chunk {chunkCounter} failed JSON validation (likely no models in this section). Skipping. Error: {ex.Message}");
            }
            catch (JsonException ex)
            {
                Console.Error.WriteLine($"[TRANSFORM] Failed to parse JSON from chunk {chunkCounter}: {ex.Message}");
            }

            chunkCounter++;

            if (startIndex < wikipediaText.Length)
            {
                Console.WriteLine("[RATE LIMIT] Pausing 22 seconds to respect Groq TPM constraints...");
                await Task.Delay(TimeSpan.FromSeconds(22));
            }
        }

        var combinedCatalog = new GuitarCatalog { models = allModels };
        return JsonSerializer.Serialize(combinedCatalog);
    }
    catch (Exception ex) when (ex is not ClientResultException || ((ClientResultException)ex).Status != 400)
    {
        Console.Error.WriteLine($"[TRANSFORM] Fatal API error: {ex.Message}");
        throw;
    }
}

static Task<GuitarCatalog> LoadAsync(string llmJson)
{
    Console.WriteLine("[LOAD] Deserializing LiteLLM JSON into GuitarCatalog...");

    try
    {
        GuitarCatalog? catalog = JsonSerializer.Deserialize<GuitarCatalog>(llmJson);
        if (catalog?.models is null)
        {
            throw new InvalidOperationException("[LOAD] Deserialization produced a null catalog or models list.");
        }

        Console.WriteLine($"[LOAD] Deserialized {catalog.models.Count} total guitar model(s).");
        PrintCatalog(catalog);
        return Task.FromResult(catalog);
    }
    catch (JsonException ex)
    {
        Console.Error.WriteLine($"[LOAD] Failed to deserialize LiteLLM JSON into GuitarCatalog: {ex.Message}");
        throw;
    }
}

static void PrintCatalog(GuitarCatalog catalog)
{
    Console.WriteLine();
    Console.WriteLine("=== Structured guitar catalog ===");

    int index = 1;
    foreach (GuitarModel model in catalog.models)
    {
        Console.WriteLine($"--- Model {index++} ---");
        Console.WriteLine($"  model_name:         {FormatValue(model.model_name)}");
        Console.WriteLine($"  production_years:   {FormatValue(model.production_years)}");
        Console.WriteLine($"  body_construction:  {FormatValue(model.body_construction)}");
        Console.WriteLine($"  pickups:            {FormatList(model.pickups)}");
        Console.WriteLine($"  notable_finishes:   {FormatList(model.notable_finishes)}");
    }

    Console.WriteLine();
}

async Task EnsureDatabaseAndTableExistAsync()
{
    Console.WriteLine("[SQL] Ensuring GuitarModels and MarketPricing tables exist...");

    try
    {
        await using var appConnection = new SqlConnection(SqlConnectionString);
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

        Console.WriteLine("[SQL] Tables are ready.");
    }
    catch (SqlException ex)
    {
        Console.Error.WriteLine(
            $"[SQL] Failed while creating tables. Number={ex.Number} Server={ex.Server} Message={ex.Message}");
        throw;
    }
}

async Task LoadToSqlAsync(GuitarCatalog catalog)
{
    Console.WriteLine("[SQL] Inserting guitar models with parameterized SQL...");

    int inserted = 0;

    try
    {
        await using var connection = new SqlConnection(SqlConnectionString);
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

            // Add the new MarketPricing insert
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

        Console.WriteLine($"[SQL] Successfully inserted {inserted} row(s) into GuitarModels.");
    }
    catch (SqlException ex)
    {
        Console.Error.WriteLine(
            $"[SQL] Insert failed after {inserted} successful row(s). Number={ex.Number} Message={ex.Message}");
        throw;
    }
}

static string? SerializeList(List<string>? values) =>
    values is null ? null : JsonSerializer.Serialize(values);

static string FormatValue(string? value) => value ?? "null";

static string FormatList(List<string>? values) =>
    values is null ? "null" : string.Join(", ", values);

static string Truncate(string value, int maxLength) =>
    value.Length <= maxLength ? value : value[..maxLength] + "...";

async Task<(decimal? average, decimal? lowest, int count)> GetMarketPricingAsync(string make, string modelName, string token)
{
    Console.WriteLine($"[PRICING] Querying Reverb API for {make} {modelName}...");
    
    using var httpClient = new HttpClient();
    httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}");
    httpClient.DefaultRequestHeaders.Add("Accept-Version", "3.0");
    httpClient.DefaultRequestHeaders.Add("Accept", "application/hal+json");
    httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("GuitarEtl/1.0");

    string query = Uri.EscapeDataString(modelName);
    string endpoint = $"https://api.reverb.com/api/listings/all?make={make}&query={query}&condition=used&per_page=50";

    try
    {
        using HttpResponseMessage response = await httpClient.GetAsync(endpoint);
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

        foreach (JsonElement listing in listings.EnumerateArray())
        {
            if (listing.TryGetProperty("price", out JsonElement priceNode) && 
                priceNode.TryGetProperty("amount", out JsonElement amountNode) &&
                decimal.TryParse(amountNode.GetString(), out decimal price))
            {
                total += price;
                if (price < lowest) lowest = price;
            }
        }

        decimal average = Math.Round(total / count, 2);
        Console.WriteLine($"[PRICING] Found {count} active listings. Avg: ${average}, Low: ${lowest}");
        
        return (average, lowest, count);
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"[PRICING] Failed to pull Reverb data for {modelName}: {ex.Message}");
        return (null, null, 0);
    }
}

async Task StageToDataLakeAsync(GuitarCatalog catalog)
{
    Console.WriteLine("[DATALAKE] Serializing payload to JSON Lines...");
    
    string localFilePath = "raw_extract.jsonl";
    string bucketName = "guitar-etl-raw-landing"; // Replace with your bucket name

    // 1. Write the combined data to a local .jsonl file
    using (StreamWriter file = new StreamWriter(localFilePath))
    {
        // For simplicity, we are saving the unified view as a single JSON object per line
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

    Console.WriteLine("[DATALAKE] Uploading to Google Cloud Storage...");

    // 2. Authenticate and Upload to GCS using the updated method
    string jsonCreds = await File.ReadAllTextAsync(gcpKeyPath);
    var credential = GoogleCredential.FromJson(jsonCreds);
    using var storageClient = await StorageClient.CreateAsync(credential);
    
    // Create a unique filename with a timestamp partition
    string objectName = $"raw/guitar_market_{DateTime.UtcNow:yyyyMMdd_HHmmss}.jsonl";
    
    await using (var fileStream = File.OpenRead(localFilePath))
    {
        await storageClient.UploadObjectAsync(
            bucketName,
            objectName,
            "application/json",
            fileStream
        );
    }

    Console.WriteLine($"[DATALAKE] Successfully staged {objectName} to bucket {bucketName}.");
}

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
    
    // New fields for Reverb market data
    public decimal? average_price_usd { get; set; }
    public decimal? lowest_price_usd { get; set; }
    public int? listing_count { get; set; }
}