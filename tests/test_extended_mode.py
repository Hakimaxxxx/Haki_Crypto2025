"""Test extended mode integration"""
import metrics_ohlcv_okx

print("=" * 60)
print("Testing Extended OHLCV Mode Integration")
print("=" * 60)

# Test 1: Standard mode (OKX only)
print("\n1. Standard Mode (OKX, limit=300)...")
df_std = metrics_ohlcv_okx.fetch_okx_ohlcv_oi('BTC-USDT-SWAP', '1h', limit=300)
print(f"   Result: {len(df_std)} candles")
if not df_std.empty:
    print(f"   Range: {df_std['datetime'].min()} → {df_std['datetime'].max()}")

# Test 2: Extended mode (multi-source)
print("\n2. Extended Mode (90 days via Binance/CryptoCompare)...")
df_ext = metrics_ohlcv_okx.fetch_okx_ohlcv_oi('BTC-USDT-SWAP', '1h', extended_days=90)
print(f"   Result: {len(df_ext)} candles")
if not df_ext.empty:
    print(f"   Range: {df_ext['datetime'].min()} → {df_ext['datetime'].max()}")
    days = (df_ext['datetime'].max() - df_ext['datetime'].min()).days
    print(f"   Coverage: {days} days")

# Test 3: Different coin
print("\n3. Testing ETH with extended mode (4H bar)...")
df_eth = metrics_ohlcv_okx.fetch_okx_ohlcv_oi('ETH-USDT-SWAP', '4h', extended_days=90)
print(f"   Result: {len(df_eth)} candles")
if not df_eth.empty:
    print(f"   Range: {df_eth['datetime'].min()} → {df_eth['datetime'].max()}")

# Comparison
print("\n" + "=" * 60)
print("Summary:")
print(f"  Standard mode: {len(df_std)} candles (~{len(df_std)/24:.1f} days if hourly)")
print(f"  Extended mode: {len(df_ext)} candles (~{len(df_ext)/24:.1f} days)")
if len(df_std) > 0:
    print(f"  Improvement:   {len(df_ext)/len(df_std):.1f}x more data")
else:
    print(f"  Improvement:   ∞ (extended mode succeeded when OKX failed!)")
print("=" * 60)
