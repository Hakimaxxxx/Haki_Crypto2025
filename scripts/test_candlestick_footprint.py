"""
Quick test for candlestick + footprint zones chart with KLINES
"""
import sys
sys.path.insert(0, 'D:\\Crypto')

from metrics_futures_footprint import (
    fetch_binance_klines,
    convert_klines_to_footprint,
    plot_candlestick_with_footprint,
    calculate_footprint_metrics
)

print("Testing Candlestick with Footprint Zones (KLINES)...")

# Fetch klines data (7 days of 5min candles)
print("\n1. Fetching Binance klines for BTCUSDT (7 days, 5m)...")
klines_df = fetch_binance_klines('BTCUSDT', interval='5m', days=7)

if not klines_df.empty:
    print(f"   OK - Fetched {len(klines_df)} candles")
    print(f"   First: {klines_df.iloc[0]['time']} | ${klines_df.iloc[0]['close']:,.2f}")
    print(f"   Last:  {klines_df.iloc[-1]['time']} | ${klines_df.iloc[-1]['close']:,.2f}")
    
    # Convert to footprint
    print("\n2. Converting klines to footprint format...")
    footprint = convert_klines_to_footprint(klines_df)
    print(f"   OK - Created {len(footprint['candles'])} footprint candles")
    
    # Calculate metrics
    print("\n3. Calculating metrics...")
    metrics = calculate_footprint_metrics(footprint)
    print(f"   Total Volume: {metrics['total_volume']:.2f}")
    print(f"   Net Delta: {metrics['net_delta']:+.2f}")
    print(f"   Aggression Ratio: {metrics['aggression_ratio']:.2f}")
    
    # Create chart
    print("\n4. Creating candlestick chart with zones...")
    fig = plot_candlestick_with_footprint(
        footprint,
        symbol='BTC',
        exchange='binance',
        delta_threshold=0.3
    )
    
    if fig:
        print("   OK - Chart created successfully!")
        
        # Count zones
        zones_count = len([s for s in fig.layout.shapes if s.type == 'rect'])
        print(f"   Footprint zones detected: {zones_count}")
        
        print(f"\n✅ Test successful! {len(klines_df)} candles spanning ~7 days")
    else:
        print("   ERROR - Chart is None")
else:
    print("   ERROR - No klines fetched")
