"""Test Open Interest API"""

from metrics_futures_open_interest import (
    fetch_binance_open_interest, 
    fetch_okx_open_interest,
    fetch_bybit_open_interest,
    fetch_all_open_interest
)
import json

print("=" * 60)
print("Testing Open Interest APIs")
print("=" * 60)

# Test Binance
print("\n1. Testing Binance API for BTC...")
btc_data = fetch_binance_open_interest('BTC')
if btc_data:
    print(f"✅ BTC Open Interest: {btc_data['open_interest']:,.0f} contracts")
    print(f"   Historical Points: {len(btc_data['historical'])}")
    
    # Show latest historical data
    if btc_data['historical']:
        latest = btc_data['historical'][-1]
        from datetime import datetime
        dt = datetime.fromtimestamp(latest['timestamp']/1000).strftime('%Y-%m-%d %H:%M')
        print(f"   Latest ({dt}):")
        print(f"     OI: {latest['open_interest']:,.0f}")
        print(f"     OI Value: ${latest['open_interest_value']:,.0f}")
        
        # Show trend (last 10 points)
        recent_10 = btc_data['historical'][-10:]
        oi_start = recent_10[0]['open_interest']
        oi_end = recent_10[-1]['open_interest']
        change_pct = ((oi_end - oi_start) / oi_start) * 100
        print(f"   Trend (last 10 intervals): {change_pct:+.2f}%")
else:
    print("❌ Failed to fetch BTC data")

# Test OKX
print("\n2. Testing OKX API for ETH...")
eth_data = fetch_okx_open_interest('ETH')
if eth_data:
    print(f"✅ ETH Open Interest: {eth_data['open_interest']:,.0f} contracts")
    if eth_data.get('open_interest_value'):
        print(f"   OI Value: ${eth_data['open_interest_value']:,.0f}")
else:
    print("❌ Failed to fetch ETH data")

# Test Bybit
print("\n3. Testing Bybit API for SOL...")
sol_data = fetch_bybit_open_interest('SOL')
if sol_data:
    print(f"✅ SOL Open Interest: {sol_data['open_interest']:,.0f} contracts")
    print(f"   Historical Points: {len(sol_data['historical'])}")
else:
    print("❌ Failed to fetch SOL data")

# Test multi-coin aggregation
print("\n4. Testing multi-coin fetch (BTC, ETH)...")
all_data, success = fetch_all_open_interest(['BTC', 'ETH'])
if success:
    print(f"✅ Success: {len(all_data)} coins fetched")
    for coin, data in all_data.items():
        exchanges = len(data['exchanges'])
        total_oi = data['total_oi']
        total_usd = data['total_oi_usd']
        print(f"\n   {coin}:")
        print(f"     Total OI: {total_oi:,.0f} contracts")
        print(f"     Total USD: ${total_usd:,.0f}")
        print(f"     Exchanges: {exchanges}")
        for ex in data['exchanges']:
            print(f"       - {ex['exchange']}: {ex['open_interest']:,.0f}")
else:
    print("❌ Failed to fetch data")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
