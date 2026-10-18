using System;
using System.Net;
using System.Net.Http;
using Microsoft.Extensions.Logging;
using Polly;
using Polly.CircuitBreaker;
using Polly.Retry;

namespace GuitarEtl.Services;

public static class ResiliencePipelineFactory
{
    public static ResiliencePipeline<HttpResponseMessage> CreateHttpPipeline(ILogger logger, string clientName)
    {
        return new ResiliencePipelineBuilder<HttpResponseMessage>()
            .AddRetry(new RetryStrategyOptions<HttpResponseMessage>
            {
                ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
                    .Handle<HttpRequestException>()
                    .Handle<TaskCanceledException>()
                    .HandleResult(r =>
                        r.StatusCode == HttpStatusCode.TooManyRequests ||
                        (int)r.StatusCode >= 500),
                MaxRetryAttempts = 4,
                Delay = TimeSpan.FromSeconds(2),
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true,
                OnRetry = args =>
                {
                    logger.LogWarning(
                        "[Polly:{Client}] Transient failure or rate-limit (Attempt {Attempt}). Retrying in {DelayMs:F0}ms...",
                        clientName,
                        args.AttemptNumber + 1,
                        args.RetryDelay.TotalMilliseconds);
                    return ValueTask.CompletedTask;
                }
            })
            .AddCircuitBreaker(new CircuitBreakerStrategyOptions<HttpResponseMessage>
            {
                FailureRatio = 0.5,
                SamplingDuration = TimeSpan.FromSeconds(30),
                MinimumThroughput = 5,
                BreakDuration = TimeSpan.FromSeconds(15),
                OnOpened = args =>
                {
                    logger.LogError(
                        "[Polly:{Client}] Circuit breaker OPENED for {BreakSeconds}s due to downstream instability.",
                        clientName,
                        args.BreakDuration.TotalSeconds);
                    return ValueTask.CompletedTask;
                }
            })
            .Build();
    }
}
