"""Test if extended mode fetches LATEST data (not old data)"""
from ohlcv_multi_source import fetch_binance_ohlcv_extended
from datetime import datetime, timezone

print("=" * 70)
print("Testing Latest Data Fetch (Reverse Pagination)")
print("=" * 70)

# Test BTC 7 days
print("\n1. Fetching BTC 7 days (1H bar)...")
df = fetch_binance_ohlcv_extended('BTCUSDT', '1h', days=7)

if not df.empty:
    print(f"   ✓ Total: {len(df)} candles")
    print(f"   ✓ Oldest: {df['datetime'].min()}")
    print(f"   ✓ Latest: {df['datetime'].max()}")
    
    # Calculate how fresh the data is
    now = datetime.now(timezone.utc)
    latest_dt = df['datetime'].max()
    hours_ago = (now - latest_dt).total_seconds() / 3600
    
    print(f"\n   📊 Data freshness: {hours_ago:.1f} hours old")
    
    if hours_ago < 2:
        print("   ✅ PASS: Data is recent (< 2 hours old)")
    else:
        print(f"   ❌ FAIL: Data is too old ({hours_ago:.1f} hours)")
    
    # Check date range
    days_coverage = (df['datetime'].max() - df['datetime'].min()).days
    print(f"   📅 Coverage: {days_coverage} days")
    
    # Show last 5 candles
    print("\n   Last 5 candles:")
    print(df[['datetime', 'close']].tail(5).to_string(index=False))
else:
    print("   ❌ FAIL: No data returned")

print("\n" + "=" * 70)
print("Expected: Latest candle should be within 1-2 hours of now")
print(f"Current time (UTC): {datetime.now(timezone.utc)}")
print("=" * 70)
