"""Test Liquidations API"""

from metrics_futures_liquidations import (
    fetch_coinglass_liquidations,
    fetch_binance_liquidation_orders,
    fetch_all_liquidations
)
import json

print("=" * 60)
print("Testing Liquidations APIs")
print("=" * 60)

# Test Coinglass
print("\n1. Testing Coinglass API for BTC (24h)...")
btc_data = fetch_coinglass_liquidations('BTC', '24h')
if btc_data:
    print(f"✅ BTC Liquidations (24h):")
    print(f"   Total: ${btc_data['total_liquidations']:,.0f}")
    print(f"   Long: ${btc_data['long_liquidations']:,.0f} ({btc_data['long_percentage']:.1f}%)")
    print(f"   Short: ${btc_data['short_liquidations']:,.0f} ({btc_data['short_percentage']:.1f}%)")
    
    if btc_data['long_percentage'] > 60:
        print(f"   🔴 Sentiment: Bearish (Bulls getting liquidated)")
    elif btc_data['long_percentage'] < 40:
        print(f"   🟢 Sentiment: Bullish (Bears getting liquidated)")
    else:
        print(f"   🟡 Sentiment: Neutral")
else:
    print("❌ Failed to fetch BTC data (may require API key)")

# Test different timeframes
print("\n2. Testing different timeframes for ETH...")
for tf in ['1h', '4h', '12h', '24h']:
    eth_data = fetch_coinglass_liquidations('ETH', tf)
    if eth_data:
        print(f"   {tf}: ${eth_data['total_liquidations']:,.0f} (L:{eth_data['long_percentage']:.0f}% S:{eth_data['short_percentage']:.0f}%)")
    else:
        print(f"   {tf}: Failed")

# Test Binance liquidation orders
print("\n3. Testing Binance liquidation orders for BTC...")
binance_liqs = fetch_binance_liquidation_orders('BTC', limit=100)
if binance_liqs:
    print(f"✅ Fetched {len(binance_liqs)} liquidation events")
    
    # Analyze
    from datetime import datetime
    total_value = sum(liq['value'] for liq in binance_liqs)
    long_value = sum(liq['value'] for liq in binance_liqs if liq['side'] == 'SELL')
    short_value = sum(liq['value'] for liq in binance_liqs if liq['side'] == 'BUY')
    
    print(f"   Total Value: ${total_value:,.0f}")
    print(f"   Long Liqs: ${long_value:,.0f} ({long_value/total_value*100:.1f}%)")
    print(f"   Short Liqs: ${short_value:,.0f} ({short_value/total_value*100:.1f}%)")
    
    # Show recent events
    print(f"   Recent 3 events:")
    for liq in binance_liqs[:3]:
        dt = datetime.fromtimestamp(liq['timestamp']/1000).strftime('%Y-%m-%d %H:%M')
        side_label = "Long" if liq['side'] == 'SELL' else "Short"
        print(f"     {dt} | {side_label:5} | ${liq['value']:10,.0f} @ ${liq['price']:,.2f}")
else:
    print("❌ Failed to fetch Binance liquidations")

# Test aggregation
print("\n4. Testing aggregation for multiple coins...")
all_data, success = fetch_all_liquidations(['BTC', 'ETH'], '24h')
if success:
    print(f"✅ Success: {len(all_data)} coins")
    for coin, data in all_data.items():
        print(f"\n   {coin}:")
        if data.get('summary'):
            s = data['summary']
            print(f"     Total: ${s['total_liquidations']:,.0f}")
            print(f"     Long: {s['long_percentage']:.1f}%")
        if data.get('events'):
            print(f"     Events: {len(data['events'])}")
        if data.get('hourly'):
            print(f"     Hourly data: {len(data['hourly'])} intervals")
else:
    print("❌ Failed to aggregate data")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
print("\nNote: Coinglass API may be rate-limited or require API key.")
print("      Binance liquidation orders are publicly available.")
