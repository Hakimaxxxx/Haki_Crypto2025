"""
Test RSI Universe Fetching with CryptoCompare Fallback
"""
import sys
sys.path.insert(0, '.')

print("=" * 60)
print("Testing RSI Universe Fetching")
print("=" * 60)

from metrics_rsi import get_universe_from_config

# Test top30
print("\n1. Testing top30 universe...")
top30 = get_universe_from_config('top30')
print(f"   Result: {len(top30)} coins")
if top30:
    print(f"   Sample: {top30[:5]}")
else:
    print("   ❌ Failed to fetch top30")

# Test top50
print("\n2. Testing top50 universe...")
top50 = get_universe_from_config('top50')
print(f"   Result: {len(top50)} coins")
if top50:
    print(f"   Sample: {top50[:5]}")
else:
    print("   ❌ Failed to fetch top50")

# Test all
print("\n3. Testing all universe...")
all_coins = get_universe_from_config('all')
print(f"   Result: {len(all_coins)} coins")
if all_coins:
    print(f"   Sample: {all_coins[:5]}")
else:
    print("   ❌ Failed to fetch all")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
