#!/usr/bin/env python3
"""
Test script to verify price mapping from backend
"""
import requests
import json
from config import COIN_LIST

def test_backend_price_mapping():
    """Test if backend price mapping works correctly"""
    try:
        # Get backend response
        url = "https://hakicrypto2025.onrender.com/prices/spot"
        symbols_param = ",".join([sym for _, sym in COIN_LIST])
        
        print(f"Requesting: {url}?symbols={symbols_param}")
        resp = requests.get(url, params={"symbols": symbols_param}, timeout=5)
        
        if resp.status_code != 200:
            print(f"❌ Backend error: {resp.status_code}")
            return
            
        js = resp.json()
        backend_prices_block = js.get("prices") or {}
        
        print(f"\n📊 Backend returned {len(backend_prices_block)} prices:")
        for symbol_key, v in backend_prices_block.items():
            coin_id = v.get("coin_id", "unknown")
            price = v.get("price", 0)
            print(f"  {symbol_key}: {coin_id} = ${price}")
        
        # Test mapping logic
        print(f"\n🔄 Testing mapping logic:")
        symbol_to_coin_id = {sym: coin_id for coin_id, sym in COIN_LIST}
        
        prices_new = {}
        for symbol_key, v in backend_prices_block.items():
            coin_id_for_key = symbol_to_coin_id.get(symbol_key, symbol_key.lower())
            price = v.get("price", 0)
            prices_new[coin_id_for_key] = price
            print(f"  {symbol_key} -> {coin_id_for_key}: ${price}")
        
        # Check for zero prices
        coins = [c[0] for c in COIN_LIST]  # coin_ids
        zero_coins = [c for c in coins if float(prices_new.get(c, 0.0)) == 0.0]
        
        if zero_coins:
            print(f"\n❌ Zero-priced coins: {', '.join(zero_coins)}")
        else:
            print(f"\n✅ All coins have prices!")
            
        print(f"\n📋 Final prices mapping:")
        for coin_id in coins:
            price = prices_new.get(coin_id, 0.0)
            symbol = dict(COIN_LIST).get(coin_id, coin_id.upper())
            status = "✅" if price > 0 else "❌"
            print(f"  {status} {coin_id} ({symbol}): ${price}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_backend_price_mapping()