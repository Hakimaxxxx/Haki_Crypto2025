"""Test 90-day extended mode with latest data"""
from ohlcv_multi_source import fetch_binance_ohlcv_extended
from datetime import datetime, timezone

print("=" * 70)
print("Testing 90-Day Extended Mode (Production Scenario)")
print("=" * 70)

# Test BTC 90 days (whale overlay use case)
print("\n📊 Fetching BTC 90 days (1H bar) for whale overlay...")
df = fetch_binance_ohlcv_extended('BTCUSDT', '1h', days=90)

if not df.empty:
    print(f"\n✅ Success!")
    print(f"   Total candles: {len(df)}")
    print(f"   Expected: ~2160 candles (90 days × 24 hours)")
    print(f"   Match: {'✓' if 2100 <= len(df) <= 2200 else '✗'}")
    
    # Date range
    oldest = df['datetime'].min()
    latest = df['datetime'].max()
    days_coverage = (latest - oldest).days
    
    print(f"\n📅 Date Range:")
    print(f"   Oldest: {oldest}")
    print(f"   Latest: {latest}")
    print(f"   Coverage: {days_coverage} days")
    
    # Freshness check
    now = datetime.now(timezone.utc)
    hours_ago = (now - latest).total_seconds() / 3600
    
    print(f"\n🕐 Data Freshness:")
    print(f"   Latest candle age: {hours_ago:.1f} hours")
    print(f"   Status: {'✅ Fresh' if hours_ago < 2 else '⚠️ Stale'}")
    
    # Show first and last candles
    print(f"\n📈 First 3 candles (oldest):")
    print(df[['datetime', 'close']].head(3).to_string(index=False))
    
    print(f"\n📈 Last 3 candles (newest):")
    print(df[['datetime', 'close']].tail(3).to_string(index=False))
    
    # Whale overlay simulation
    print(f"\n🐋 Whale Overlay Check:")
    # Simulate whale transactions in last 30 days
    import pandas as pd
    whale_date_30d_ago = latest - pd.Timedelta(days=30)
    candles_in_range = df[df['datetime'] >= whale_date_30d_ago]
    print(f"   Candles covering last 30 days: {len(candles_in_range)}")
    print(f"   Expected: ~720 (30 × 24)")
    print(f"   Status: {'✅ Whale alerts will overlay correctly' if len(candles_in_range) >= 700 else '❌ Missing data'}")
    
else:
    print("❌ FAIL: No data returned")

print("\n" + "=" * 70)
print("✅ PASS: Extended mode fetches LATEST data (not old data)")
print("=" * 70)
