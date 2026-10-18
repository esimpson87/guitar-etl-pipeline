using System.Threading.Tasks;
using GuitarAgent.Domain.Models;

namespace GuitarAgent.Domain.Abstractions;

public interface IGuitarMarketRepository
{
    Task<MarketStats> GetMarketStatsAsync(string canonicalModel);
}
