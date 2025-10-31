"""
Quick test for Altcoin Season Index
"""
from metrics_altcoin_season import fetch_altcoin_season_index

print("=" * 60)
print("Testing Altcoin Season Index Calculation")
print("=" * 60)
print("\nFetching data from CoinGecko API...")
print("This will analyze top 50 altcoins vs BTC (90 days)")
print("Expected time: 1-2 minutes (rate limiting)\n")

idx, data, ok = fetch_altcoin_season_index()

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Success: {ok}")
print(f"Index: {idx:.1f}/100")
print(f"Altcoins Outperforming BTC: {data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 0)}")
print(f"BTC 90-Day Performance: {data.get('btc_performance_90d', 0):+.2f}%")
print(f"Calculation Date: {data.get('calculation_date', 'N/A')}")

if data.get('top_performers'):
    print("\n" + "=" * 60)
    print("TOP 5 PERFORMERS (90 days)")
    print("=" * 60)
    for i, perf in enumerate(data['top_performers'][:5], 1):
        outperform = "✅" if perf['outperforms_btc'] else "❌"
        print(f"{i}. {perf['name']} ({perf['symbol']}): {perf['performance_90d']:+.2f}% {outperform}")

if data.get('worst_performers'):
    print("\n" + "=" * 60)
    print("WORST 5 PERFORMERS (90 days)")
    print("=" * 60)
    for i, perf in enumerate(data['worst_performers'][:5], 1):
        outperform = "✅" if perf['outperforms_btc'] else "❌"
        print(f"{i}. {perf['name']} ({perf['symbol']}): {perf['performance_90d']:+.2f}% {outperform}")

print("\n" + "=" * 60)
print("Interpretation:")
if idx >= 75:
    print("🌙 ALTCOIN SEASON - Altcoins are outperforming Bitcoin!")
elif idx <= 25:
    print("₿ BITCOIN SEASON - Bitcoin is dominating the market!")
else:
    print("⚖️ NEUTRAL - Mixed market conditions")
print("=" * 60)
