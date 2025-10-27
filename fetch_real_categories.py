"""
Fetch REAL category data from CoinGecko API with proper rate limiting.

This script will:
1. Fetch 19 categories with 50 coins each
2. Use 2-second delay between requests (safe for free tier)
3. Save to cache file for 3-hour reuse
4. Show progress and handle errors gracefully

Estimated time: ~40 seconds total
"""

import sys
import os
os.chdir(r'd:\Crypto')
sys.path.insert(0, r'd:\Crypto')

from metrics_category_treemap import fetch_all_categories, FEATURED_CATEGORIES

print("=" * 70)
print("FETCHING REAL CRYPTOCURRENCY DATA FROM COINGECKO")
print("=" * 70)
print(f"\nCategories to fetch: {len(FEATURED_CATEGORIES)}")
print(f"Coins per category: 20 (top by market cap)")
print(f"Estimated time: ~{len(FEATURED_CATEGORIES) * 2} seconds\n")
print("This will include REAL coins like:")
print("  - Layer 1: Bitcoin, Ethereum, Solana, Cardano, etc.")
print("  - DeFi: Uniswap, Aave, Maker, Curve, etc.")
print("  - Meme: Dogecoin, Shiba Inu, Pepe, etc.")
print("  - AI: Fetch.ai, Render, The Graph, etc.")
print("\nData updates every 1 hour (not realtime)")
print("Top 20 coins per category (đại diện cho sector)\n")
print("=" * 70)

# Fetch data
data, success = fetch_all_categories()

print("\n" + "=" * 70)
if success and data:
    total_coins = sum(len(coins) for coins in data.values())
    print(f"SUCCESS!")
    print(f"  Categories loaded: {len(data)}")
    print(f"  Total real coins: {total_coins}")
    print(f"\nSample coins from each category:")
    for cat_id, coins in list(data.items())[:5]:
        top_3 = [c['symbol'].upper() for c in coins[:3]]
        print(f"  - {cat_id}: {', '.join(top_3)}, ...")
    print(f"\nCache saved for 3 hours. Run Streamlit app now!")
else:
    print(f"FAILED - likely rate limited by CoinGecko")
    print(f"  Please wait 10 minutes and try again")
    print(f"  Or use the Streamlit app 🔄 Refresh button after waiting")

print("=" * 70)
