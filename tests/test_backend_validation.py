#!/usr/bin/env python3
"""
Test backend validation system
"""
import httpx
import time

def test_backend_vs_coingecko():
    print("=== Backend vs CoinGecko Price Validation Test ===")
    
    # Test backend prices
    try:
        print("\n1. Testing Backend API...")
        backend_resp = httpx.get(
            'https://hakicrypto2025.onrender.com/prices/spot',
            params={'symbols': 'BTC,ETH'},
            timeout=10
        )
        
        if backend_resp.status_code == 200:
            backend_data = backend_resp.json()
            backend_btc = backend_data.get('prices', {}).get('BTC', {}).get('price', 0)
            backend_eth = backend_data.get('prices', {}).get('ETH', {}).get('price', 0)
            print(f"   Backend BTC: ${backend_btc:,.2f}")
            print(f"   Backend ETH: ${backend_eth:,.2f}")
        else:
            print(f"   Backend Error: {backend_resp.status_code}")
            return
            
    except Exception as e:
        print(f"   Backend Exception: {e}")
        return
    
    # Test CoinGecko prices
    try:
        print("\n2. Testing CoinGecko API...")
        cg_resp = httpx.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'bitcoin,ethereum', 'vs_currencies': 'usd'},
            timeout=10
        )
        
        if cg_resp.status_code == 200:
            cg_data = cg_resp.json()
            cg_btc = cg_data.get('bitcoin', {}).get('usd', 0)
            cg_eth = cg_data.get('ethereum', {}).get('usd', 0)
            print(f"   CoinGecko BTC: ${cg_btc:,.2f}")
            print(f"   CoinGecko ETH: ${cg_eth:,.2f}")
        else:
            print(f"   CoinGecko Error: {cg_resp.status_code}")
            return
            
    except Exception as e:
        print(f"   CoinGecko Exception: {e}")
        return
    
    # Compare prices
    print("\n3. Price Comparison & Validation...")
    
    if backend_btc > 0 and cg_btc > 0:
        btc_diff_pct = abs(backend_btc - cg_btc) / cg_btc * 100
        print(f"   BTC Difference: {btc_diff_pct:.1f}%")
        if btc_diff_pct > 10:
            print(f"   ❌ BTC VALIDATION FAILED: {btc_diff_pct:.1f}% > 10% threshold")
        else:
            print(f"   ✅ BTC VALIDATION PASSED: {btc_diff_pct:.1f}% < 10% threshold")
    
    if backend_eth > 0 and cg_eth > 0:
        eth_diff_pct = abs(backend_eth - cg_eth) / cg_eth * 100
        print(f"   ETH Difference: {eth_diff_pct:.1f}%")
        if eth_diff_pct > 10:
            print(f"   ❌ ETH VALIDATION FAILED: {eth_diff_pct:.1f}% > 10% threshold")
        else:
            print(f"   ✅ ETH VALIDATION PASSED: {eth_diff_pct:.1f}% < 10% threshold")
    
    # Final recommendation
    print("\n4. Final Recommendation...")
    backend_valid = True
    if backend_btc > 0 and cg_btc > 0:
        btc_diff_pct = abs(backend_btc - cg_btc) / cg_btc * 100
        if btc_diff_pct > 10:
            backend_valid = False
    
    if backend_eth > 0 and cg_eth > 0:
        eth_diff_pct = abs(backend_eth - cg_eth) / cg_eth * 100
        if eth_diff_pct > 10:
            backend_valid = False
    
    if backend_valid:
        print("   ✅ BACKEND VALIDATION PASSED - Use backend prices")
    else:
        print("   ❌ BACKEND VALIDATION FAILED - Use CoinGecko fallback")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_backend_vs_coingecko()