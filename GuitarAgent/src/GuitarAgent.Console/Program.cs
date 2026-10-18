using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using GuitarAgent.AI.Plugins;
using GuitarAgent.Domain.Abstractions;
using GuitarAgent.Infrastructure.BigQuery;

// 1. Enable OpenTelemetry-compatible distributed tracing for Semantic Kernel tool calls
AppContext.SetSwitch("Microsoft.SemanticKernel.Experimental.GenAI.EnableOTelDiagnostics", true);
using var activityListener = new ActivityListener
{
    ShouldListenTo = source => source.Name.StartsWith("Microsoft.SemanticKernel", StringComparison.Ordinal),
    Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
    ActivityStopped = activity =>
    {
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine($"[OTel Trace] span={activity.OperationName} trace_id={activity.TraceId} duration_ms={activity.Duration.TotalMilliseconds:F1}");
        Console.ResetColor();
    }
};
ActivitySource.AddActivityListener(activityListener);

// 2. Load configuration from User Secrets and Environment Variables
var config = new ConfigurationBuilder()
    .AddUserSecrets<Program>(optional: true)
    .AddEnvironmentVariables()
    .Build();

var modelId = config["AI_MODEL_ID"] ?? "gemini-2.0-flash";
var apiKey = config["AI_API_KEY"] ?? throw new InvalidOperationException("Missing AI_API_KEY in User Secrets or Environment Variables.");
var googleProjectId = config["GOOGLE_PROJECT_ID"] ?? throw new InvalidOperationException("Missing GOOGLE_PROJECT_ID in User Secrets or Environment Variables.");
var endpointUri = config["AI_ENDPOINT_URI"] ?? "https://generativelanguage.googleapis.com/v1beta/openai/";

// 3. Initialize Semantic Kernel with structured logging & OpenAI-compatible connector
var kernelBuilder = Kernel.CreateBuilder();
kernelBuilder.Services.AddLogging(logging =>
{
    logging.AddSimpleConsole(options =>
    {
        options.SingleLine = true;
        options.TimestampFormat = "HH:mm:ss ";
    });
    logging.SetMinimumLevel(LogLevel.Warning);
});

kernelBuilder.AddOpenAIChatCompletion(
    modelId: modelId,
    endpoint: new Uri(endpointUri),
    apiKey: apiKey);

// 4. Register repository and GuitarDataPlugin tools
IGuitarMarketRepository bigQueryRepo = new BigQueryRepository(googleProjectId);
var guitarDataPlugin = new GuitarDataPlugin(bigQueryRepo);
kernelBuilder.Plugins.AddFromObject(guitarDataPlugin, nameof(GuitarDataPlugin));

var kernel = kernelBuilder.Build();

// 5. Enable autonomous agentic tool calling
var executionSettings = new OpenAIPromptExecutionSettings
{
    FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
};

var chatCompletionService = kernel.GetRequiredService<IChatCompletionService>();
var chatHistory = new ChatHistory(
    """
    You are an expert guitar market appraiser and arbitrage analyst.
    Always use your registered GuitarDataPlugin tools to normalize guitar eras, query BigQuery market statistics, and calculate fee-adjusted arbitrage ROI.
    Ground all responses strictly in the database metrics and fee calculations returned by your tools.
    """);

Console.WriteLine("=== GuitarAgent (Semantic Kernel + BigQuery + Arbitrage Engine) ===");
Console.WriteLine("Ask about guitar market comps or arbitrage ROI! (Type 'exit' to quit)");

while (true)
{
    Console.Write("\nUser > ");
    var userInput = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(userInput))
        continue;

    if (userInput.Equals("exit", StringComparison.OrdinalIgnoreCase) ||
        userInput.Equals("quit", StringComparison.OrdinalIgnoreCase))
        break;

    chatHistory.AddUserMessage(userInput);

    try
    {
        var response = await chatCompletionService.GetChatMessageContentAsync(
            chatHistory,
            executionSettings,
            kernel);

        Console.WriteLine($"\nAgent > {response.Content}");
        chatHistory.AddAssistantMessage(response.Content ?? string.Empty);
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"\n[Error]: {ex.Message}");
    }
}