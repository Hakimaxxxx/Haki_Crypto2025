"""Test ETF Flow Auto-Update Logic"""

from metrics_etf_flow import _fetch_etf_flows_from_csv, fetch_etf_flows
import pandas as pd
from datetime import datetime
import os

print("=" * 60)
print("Testing ETF Flow Auto-Update")
print("=" * 60)

# Test 1: Initial CSV creation or load
print("\n1. Loading/Creating ETF flow data...")
df = _fetch_etf_flows_from_csv()

if df is not None and not df.empty:
    print(f"✅ Loaded {len(df)} days of data")
    
    # Ensure date column is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])
    
    # Show date range
    first_date = df['date'].min().date() if hasattr(df['date'].min(), 'date') else df['date'].min()
    last_date = df['date'].max().date() if hasattr(df['date'].max(), 'date') else df['date'].max()
    today = datetime.now().date()
    
    print(f"   First date: {first_date}")
    print(f"   Last date: {last_date}")
    print(f"   Today: {today}")
    
    days_behind = (today - last_date).days
    print(f"   Days behind: {days_behind}")
    
    # Show latest data
    latest = df.iloc[-1]
    print(f"\n   Latest data ({last_date}):")
    print(f"     BTC Flow: ${latest['btc_flow_usd']:,.0f}")
    print(f"     ETH Flow: ${latest['eth_flow_usd']:,.0f}")
    print(f"     BTC AUM: ${latest['btc_aum_usd']:,.0f}")
    print(f"     ETH AUM: ${latest['eth_aum_usd']:,.0f}")
    
    # Show last 5 days
    print(f"\n   Last 5 days:")
    for idx, row in df.tail(5).iterrows():
        date = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
        btc_flow = row['btc_flow_usd'] / 1_000_000
        eth_flow = row['eth_flow_usd'] / 1_000_000
        print(f"     {date}: BTC {btc_flow:+.1f}M | ETH {eth_flow:+.1f}M")
else:
    print("❌ Failed to load data")

# Test 2: Cache behavior
print("\n2. Testing cache...")
df_cached, success = fetch_etf_flows()
if success:
    print(f"✅ Cache working - {len(df_cached)} days")
else:
    print("❌ Cache failed")

# Test 3: Show CSV location
print("\n3. CSV file location:")
from metrics_etf_flow import _get_csv_path
csv_path = _get_csv_path()
print(f"   Path: {csv_path}")
print(f"   Exists: {os.path.exists(csv_path)}")
if os.path.exists(csv_path):
    size = os.path.getsize(csv_path)
    print(f"   Size: {size:,} bytes")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
print("\nℹ️  Auto-update behavior:")
print("   - CSV is checked every time data is loaded")
print("   - If today's date is missing, new days are auto-generated")
print("   - Sample data is used (random flows within realistic ranges)")
print("   - Cache TTL: 24 hours")
