using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using GuitarEtlPipeline.Agents.Plugins;

var builder = Kernel.CreateBuilder();

// Route Semantic Kernel through the local LiteLLM Proxy gateway for unified model routing & observability
builder.AddOpenAIChatCompletion(
    modelId: "reasoning-bedrock-sonnet",
    apiKey: Environment.GetEnvironmentVariable("LITELLM_PROXY_KEY") ?? "sk-litellm-local",
    endpoint: new Uri("http://localhost:4000/v1"));

builder.Services.AddHttpClient<GuitarMarketPlugin>();
builder.Plugins.AddFromType<GuitarMarketPlugin>("GuitarMarket");

Kernel kernel = builder.Build();
var chatService = kernel.GetRequiredService<IChatCompletionService>();

var settings = new OpenAIPromptExecutionSettings
{
    ToolCallBehavior = ToolCallBehavior.AutoInvokeKernelFunctions,
    Temperature = 0.1
};

var history = new ChatHistory(
    "You are an autonomous Data & Market Intelligence Agent. Always query the Star Schema mart " +
    "and verify data quality assertions before issuing acquisition recommendations.");

history.AddUserMessage(
    "Ingest the latest Fender Stratocaster and Gibson Les Paul listings, verify zero schema drift, " +
    "and return any active listings with >= 15% net ROI after Reverb fees.");

var response = await chatService.GetChatMessageContentAsync(history, settings, kernel);
Console.WriteLine(response.Content);
