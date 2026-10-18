using GuitarAgent.Domain.Models;
using GuitarAgent.Domain.Services;

namespace GuitarEtl.Tests;

public class EraNormalizerTests
{
    [Theory]
    [InlineData("Gibson Les Paul Standard '60s Bourbon Burst", 2022, "Les Paul Standard '60s")]
    [InlineData("Les Paul Custom Ebony", 1957, "Les Paul Custom (Vintage)")]
    [InlineData("Les Paul Custom Alpine White", 1974, "Les Paul Custom (Norlin Era)")]
    [InlineData("Les Paul Custom Wine Red", 1985, "Les Paul Custom (Norlin Era)")]
    [InlineData("Les Paul Custom Shop", 2019, "Les Paul Custom (Modern)")]
    [InlineData("SG Standard '61", 2021, "SG Standard '61")]
    public void Normalize_ClassifiesGuitarEraAccurately(string rawModel, int year, string expectedCanonicalModel)
    {
        var listing = new Listing
        {
            Id = "TEST-1",
            Make = "Gibson",
            Model = rawModel,
            Year = year,
            Price = 2500m
        };

        string result = EraNormalizer.Normalize(listing);

        Assert.Equal(expectedCanonicalModel, result);
    }

    [Fact]
    public void Normalize_WhenYearIsNullForLesPaulCustom_ReturnsRawModel()
    {
        var listing = new Listing
        {
            Id = "TEST-NULL-YEAR",
            Make = "Gibson",
            Model = "Les Paul Custom",
            Year = null,
            Price = 3200m
        };

        string result = EraNormalizer.Normalize(listing);

        Assert.Equal("Les Paul Custom", result);
    }
}
