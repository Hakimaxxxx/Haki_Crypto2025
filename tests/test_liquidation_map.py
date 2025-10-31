"""Test Liquidation Map module"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from metrics_liquidation_map import fetch_binance_open_interest, plot_liquidation_map

print("=" * 70)
print("Testing Liquidation Map - Coinglass Style")
print("=" * 70)

# Test 1: Fetch Binance Open Interest
print("\n📊 Test 1: Fetching BTC Open Interest from Binance...")
price, long_oi, short_oi = fetch_binance_open_interest('BTCUSDT')

if price:
    print(f"✅ Success!")
    print(f"   Current Price: ${price:,.2f}")
    print(f"   Long OI: ${long_oi:,.0f}")
    print(f"   Short OI: ${short_oi:,.0f}")
    print(f"   Total OI: ${long_oi + short_oi:,.0f}")
    print(f"   Long/Short Ratio: {long_oi/short_oi:.2f}")
else:
    print("❌ Failed to fetch data")

# Test 2: Generate Liquidation Map
print("\n📈 Test 2: Generating Liquidation Map...")
fig = plot_liquidation_map('BTCUSDT', price_range_pct=10.0)

if fig:
    print("✅ Figure generated successfully!")
    print(f"   Number of traces: {len(fig.data)}")
    print(f"   Title: {fig.layout.title.text}")
    
    # Save to HTML for inspection
    try:
        fig.write_html("tests/liquidation_map_test.html")
        print("   Saved to: tests/liquidation_map_test.html")
    except Exception:
        pass
else:
    print("❌ Failed to generate figure")

print("\n" + "=" * 70)
print("✅ Test complete!")
print("=" * 70)
