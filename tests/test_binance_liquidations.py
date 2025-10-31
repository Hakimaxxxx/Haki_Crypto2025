"""Quick test for Binance liquidation data fetching"""
import sys
sys.path.insert(0, 'D:\\Crypto')

print("Testing Binance Liquidation API...")

import requests
from datetime import datetime

symbol = "BTCUSDT"
url = "https://fapi.binance.com/fapi/v1/forceOrders"

params = {
    'symbol': symbol,
    'limit': 10  # Just test with 10
}

print(f"\n1. Fetching recent liquidations for {symbol}...")
response = requests.get(url, params=params, timeout=10)

if response.status_code == 200:
    data = response.json()
    print(f"   ✓ Success! Got {len(data)} liquidations")
    
    if data:
        print("\n2. Sample liquidation:")
        liq = data[0]
        print(f"   Time: {datetime.fromtimestamp(liq['time']/1000)}")
        print(f"   Price: ${float(liq['price']):,.2f}")
        print(f"   Quantity: {float(liq['origQty']):,.4f} {symbol.replace('USDT','')}")
        print(f"   Side: {liq['side']} (BUY = Long liquidated, SELL = Short liquidated)")
        
        print("\n3. Statistics:")
        long_liq = sum(1 for l in data if l['side'] == 'BUY')
        short_liq = sum(1 for l in data if l['side'] == 'SELL')
        print(f"   Long liquidations (bulls killed): {long_liq}")
        print(f"   Short liquidations (bears killed): {short_liq}")
        
        total_value = sum(float(l['price']) * float(l['origQty']) for l in data)
        print(f"   Total liquidation value: ${total_value:,.2f}")
        
        print("\n✅ Binance Liquidation API is working!")
    else:
        print("   ⚠️ No recent liquidations found")
else:
    print(f"   ❌ Error: {response.status_code}")
    print(f"   Response: {response.text[:200]}")
