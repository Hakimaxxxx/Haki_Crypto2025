"""Quick test for ADA futures data"""
from metrics_futures_long_short import fetch_all_futures_data

print("Testing ADA + BTC fetch...")
data, success = fetch_all_futures_data(['ADA', 'BTC'], '1h')

print(f"\nSuccess: {success}")
print(f"Coins fetched: {list(data.keys())}")

for coin in data:
    ls_count = len(data[coin]['long_short'])
    taker_count = len(data[coin]['taker_volume'])
    print(f"  {coin}: L/S={ls_count} points, Taker={taker_count} points")
