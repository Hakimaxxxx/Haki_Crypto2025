"""
Test CryptoCompare backup API
"""
print("Testing CryptoCompare Altcoin Season Index...")
print("=" * 60)

from altcoin_season_cryptocompare import fetch_altcoin_season_coinpaprika

print("\nFetching from CryptoCompare API...")
print("Expected time: ~30 seconds (50 coins × 0.5s rate limit)")
print("=" * 60 + "\n")

idx, data, ok = fetch_altcoin_season_coinpaprika()

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Success: {ok}")
print(f"Index: {idx:.1f}/100")
print(f"Outperforming: {data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 0)}")
print(f"BTC 90D: {data.get('btc_performance_90d', 0):+.2f}%")
print(f"Data Source: {data.get('data_source', 'Unknown')}")

if data.get('top_performers'):
    print("\n" + "=" * 60)
    print("TOP 5 PERFORMERS")
    print("=" * 60)
    for i, perf in enumerate(data['top_performers'][:5], 1):
        print(f"{i}. {perf['name']} ({perf['symbol']}): {perf['performance_90d']:+.2f}%")
