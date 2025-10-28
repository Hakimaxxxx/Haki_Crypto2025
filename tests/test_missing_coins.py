#!/usr/bin/env python3
"""
Test specific missing coins from backend
"""
import requests

def test_missing_coins():
    """Test if backend has the missing coins"""
    missing_symbols = ["AVAX", "APT", "ENA", "EIGEN", "WLD", "ONDO", "RENDER", "ETHFI", "ADA"]
    
    url = "https://hakicrypto2025.onrender.com/prices/spot"
    symbols_param = ",".join(missing_symbols)
    
    print(f"Testing missing coins: {symbols_param}")
    try:
        resp = requests.get(url, params={"symbols": symbols_param}, timeout=10)
        if resp.status_code == 200:
            js = resp.json()
            prices = js.get("prices", {})
            print(f"Backend returned {len(prices)} prices for missing coins:")
            for sym, data in prices.items():
                price = data.get("price", 0)
                coin_id = data.get("coin_id", "unknown")
                print(f"  {sym}: {coin_id} = ${price}")
        else:
            print(f"Error: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

    # Test all coins at once
    print(f"\nTesting all 17 coins...")
    from config import COIN_LIST
    all_symbols = ",".join([sym for _, sym in COIN_LIST])
    try:
        resp = requests.get(url, params={"symbols": all_symbols}, timeout=10)
        if resp.status_code == 200:
            js = resp.json()
            prices = js.get("prices", {})
            print(f"Backend returned {len(prices)} out of 17 requested coins")
            missing = [sym for _, sym in COIN_LIST if sym not in prices]
            if missing:
                print(f"Still missing: {', '.join(missing)}")
        else:
            print(f"Error: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_missing_coins()