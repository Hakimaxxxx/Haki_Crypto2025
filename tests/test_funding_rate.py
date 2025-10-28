"""Test Funding Rate API"""

from metrics_futures_funding_rate import fetch_binance_funding_rate, fetch_okx_funding_rate, fetch_all_funding_rates
import json

print("=" * 60)
print("Testing Funding Rate APIs")
print("=" * 60)

# Test Binance
print("\n1. Testing Binance API for BTC...")
btc_data = fetch_binance_funding_rate('BTC')
if btc_data:
    print(f"✅ BTC Funding Rate: {btc_data['funding_rate']:.4f}%")
    print(f"   Mark Price: ${btc_data['mark_price']:,.2f}")
    print(f"   Index Price: ${btc_data['index_price']:,.2f}")
    from datetime import datetime
    print(f"   Next Funding: {datetime.fromtimestamp(btc_data['next_funding_time']/1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Historical Points: {len(btc_data['historical'])}")
    
    # Show last 3 historical rates
    if btc_data['historical']:
        print("   Last 3 rates:")
        for item in btc_data['historical'][-3:]:
            dt = datetime.fromtimestamp(item['timestamp']/1000).strftime('%Y-%m-%d %H:%M')
            print(f"     {dt}: {item['funding_rate']:.4f}%")
else:
    print("❌ Failed to fetch BTC data")

# Test OKX
print("\n2. Testing OKX API for ETH...")
eth_data = fetch_okx_funding_rate('ETH')
if eth_data:
    print(f"✅ ETH Funding Rate: {eth_data['funding_rate']:.4f}%")
    print(f"   Historical Points: {len(eth_data['historical'])}")
else:
    print("❌ Failed to fetch ETH data")

# Test multi-coin fetch
print("\n3. Testing multi-coin fetch (BTC, ETH, SOL)...")
all_data, success = fetch_all_funding_rates(['BTC', 'ETH', 'SOL'])
if success:
    print(f"✅ Success: {len(all_data)} coins fetched")
    for coin, data in all_data.items():
        exchanges = len(data['exchanges'])
        avg_rate = sum(ex['funding_rate'] for ex in data['exchanges']) / exchanges
        print(f"   {coin}: {exchanges} exchanges, avg rate: {avg_rate:.4f}%")
        for ex in data['exchanges']:
            print(f"     - {ex['exchange']}: {ex['funding_rate']:.4f}%")
else:
    print("❌ Failed to fetch data")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
