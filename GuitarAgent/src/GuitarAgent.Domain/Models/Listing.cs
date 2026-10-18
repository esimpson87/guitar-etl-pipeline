namespace GuitarAgent.Domain.Models;

public record Listing
{
    public string Id { get; init; } = string.Empty;
    public string Make { get; init; } = string.Empty;
    public string Model { get; init; } = string.Empty;
    public int? Year { get; init; }
    public decimal Price { get; init; }
    public string Condition { get; init; } = string.Empty;
    public DateTime CreatedAt { get; init; }
}
