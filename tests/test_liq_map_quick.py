"""Quick test for liquidation map"""
import sys
sys.path.insert(0, 'D:\\Crypto')

from metrics_liquidation_map import plot_liquidation_map

print("Testing Liquidation Map for BTC...")
fig = plot_liquidation_map('BTCUSDT', timeframe='1 hour')

if fig:
    print("✅ Successfully generated liquidation map!")
    print("Opening in browser...")
    fig.show()
else:
    print("❌ Failed to generate liquidation map")
