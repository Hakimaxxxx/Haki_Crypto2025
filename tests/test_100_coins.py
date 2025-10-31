"""Test current Altcoin Season Index with 100 coins"""
from metrics_altcoin_season import fetch_altcoin_season_index

print("Fetching current Altcoin Season Index (100 altcoins)...")
print("This may take 2-3 minutes due to API rate limits...")
print()

idx, data, ok = fetch_altcoin_season_index()

print(f"Success: {ok}")
print(f"Current Index: {idx:.1f}")
print(f"Outperforming: {data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 100)}")
print(f"BTC 90D Performance: {data.get('btc_performance_90d', 0):.2f}%")
print()

# Show comparison to Coinglass
coinglass_current = 41
diff = abs(idx - coinglass_current)
print(f"Coinglass shows: {coinglass_current}")
print(f"Our calculation: {idx:.1f}")
print(f"Difference: {diff:.1f} points")
print()

if diff < 10:
    print("✅ Close match! Within acceptable range.")
elif diff < 20:
    print("⚠️  Moderate difference. May be due to:")
    print("   - Different coin selection")
    print("   - Different price data timestamps")
    print("   - Coinglass may use different methodology")
else:
    print("❌ Large difference. Need to review methodology.")
