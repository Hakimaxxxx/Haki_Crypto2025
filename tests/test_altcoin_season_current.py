"""Test current Altcoin Season Index from CoinGecko API"""
from metrics_altcoin_season import fetch_altcoin_season_index

print("Fetching current Altcoin Season Index from CoinGecko...")
print("This may take 2-3 minutes due to API rate limits...")
print()

idx, data, ok = fetch_altcoin_season_index()

print(f"Success: {ok}")
print(f"Current Index: {idx:.1f}")
print(f"Outperforming: {data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 50)}")
print(f"BTC 90D Performance: {data.get('btc_performance_90d', 0):.2f}%")
print()

if data.get('top_performers'):
    print("Top 5 Performers:")
    for p in data['top_performers'][:5]:
        print(f"  {p['symbol']}: +{p['performance_90d']:.1f}%")
