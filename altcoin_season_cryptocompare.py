"""
Altcoin Season Index using CryptoCompare API (Backup/Fallback)

CryptoCompare advantages:
- Free tier: 100,000 calls/month
- No API key needed for basic calls
- Historical data available
- Good uptime and rate limits

API Docs: https://min-api.cryptocompare.com/
"""

import time
import requests
from typing import List, Dict, Tuple
from datetime import datetime, timedelta


def fetch_cryptocompare_historical(symbol: str, days: int = 90) -> List[Dict]:
    """
    Fetch historical daily data from CryptoCompare.
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH')
        days: Number of days to fetch (max 2000)
    
    Returns:
        List of daily data: [{'time': timestamp, 'close': price}, ...]
    """
    try:
        url = "https://min-api.cryptocompare.com/data/v2/histoday"
        params = {
            'fsym': symbol,
            'tsym': 'USD',
            'limit': days
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('Response') == 'Success' and data.get('Data', {}).get('Data'):
            return data['Data']['Data']
        
        return []
        
    except Exception as e:
        print(f"[CryptoCompare] Error fetching {symbol}: {e}")
        return []


def calculate_performance_90d(historical_data: List[Dict]) -> float:
    """Calculate 90-day performance from historical data."""
    if not historical_data or len(historical_data) < 2:
        return 0.0
    
    try:
        # Data is already sorted by time from CryptoCompare
        price_start = historical_data[0].get('close', 0)
        price_end = historical_data[-1].get('close', 0)
        
        if price_start > 0:
            return ((price_end - price_start) / price_start) * 100
        return 0.0
        
    except Exception as e:
        print(f"[CryptoCompare] Error calculating performance: {e}")
        return 0.0


def fetch_altcoin_season_coinpaprika() -> Tuple[float, Dict, bool]:
    """
    Calculate Altcoin Season Index using CryptoCompare API.
    
    Returns:
        (index, data, success): index 0-100, raw data dict, success flag
    """
    try:
        print("[CryptoCompare] Fetching top coins by volume (sorted by market cap)...")
        
        # Use CryptoCompare's top by volume endpoint (more reliable)
        toplist_url = "https://min-api.cryptocompare.com/data/top/totalvolfull"
        toplist_params = {
            'limit': 100,
            'tsym': 'USD'
        }
        
        response = requests.get(toplist_url, params=toplist_params, timeout=15)
        response.raise_for_status()
        toplist_data = response.json()
        
        # CryptoCompare returns Message="Success" (not Response field)
        if toplist_data.get('Message') != 'Success' or not toplist_data.get('Data'):
            print(f"[CryptoCompare] Error fetching top list: {toplist_data.get('Message', 'Unknown error')}")
            return 50, {}, False
        
        all_coins = toplist_data.get('Data', [])
        
        # Filter altcoins (exclude BTC and stablecoins) and get market cap
        stablecoin_symbols = {
            'USDT', 'USDC', 'BUSD', 'DAI', 'FRAX',
            'TUSD', 'USDP', 'USDD', 'GUSD', 'PYUSD', 'FDUSD'
        }
        
        # Build list with market cap for sorting
        coins_with_mktcap = []
        for c in all_coins:
            symbol = c['CoinInfo']['Name']
            if symbol in {'BTC'} | stablecoin_symbols:
                continue
            market_cap = c.get('RAW', {}).get('USD', {}).get('MKTCAP', 0)
            if market_cap > 0:
                coins_with_mktcap.append({
                    'coin': c,
                    'symbol': symbol,
                    'market_cap': market_cap
                })
        
        # Sort by market cap descending and take top 50
        coins_with_mktcap.sort(key=lambda x: x['market_cap'], reverse=True)
        altcoins = [c['coin'] for c in coins_with_mktcap[:50]]
        
        print(f"[CryptoCompare] Fetching historical data for BTC and {len(altcoins)} altcoins...")
        
        # Fetch BTC 90-day performance
        btc_data = fetch_cryptocompare_historical('BTC', days=90)
        btc_performance = calculate_performance_90d(btc_data)
        
        print(f"[CryptoCompare] BTC 90D Performance: {btc_performance:+.2f}%")
        
        # Analyze altcoins
        outperforming_count = 0
        altcoin_performances = []
        
        for i, coin_data in enumerate(altcoins):
            try:
                # Rate limiting: Be conservative (0.5s per call)
                if i > 0:
                    time.sleep(0.5)
                
                symbol = coin_data['CoinInfo']['Name']
                coin_name = coin_data['CoinInfo']['FullName']
                
                alt_data = fetch_cryptocompare_historical(symbol, days=90)
                
                if alt_data and len(alt_data) >= 2:
                    alt_performance = calculate_performance_90d(alt_data)
                    
                    altcoin_performances.append({
                        'name': coin_name,
                        'symbol': symbol,
                        'performance_90d': alt_performance,
                        'outperforms_btc': alt_performance > btc_performance
                    })
                    
                    if alt_performance > btc_performance:
                        outperforming_count += 1
                    
                    print(f"[CryptoCompare] {i+1}/{len(altcoins)}: {symbol} = {alt_performance:+.2f}%")
                else:
                    print(f"[CryptoCompare] {i+1}/{len(altcoins)}: {symbol} - No data")
                
            except Exception as e:
                print(f"[CryptoCompare] Error analyzing coin: {e}")
                continue
        
        # Calculate index
        total_analyzed = len(altcoin_performances)
        if total_analyzed == 0:
            print("[CryptoCompare] No altcoins analyzed successfully")
            return 50, {}, False
        
        index = (outperforming_count / total_analyzed) * 100
        
        # Sort by performance
        altcoin_performances.sort(key=lambda x: x['performance_90d'], reverse=True)
        
        # Prepare data
        data = {
            'index': index,
            'btc_performance_90d': btc_performance,
            'altcoins_outperforming': outperforming_count,
            'altcoins_total': total_analyzed,
            'timestamp': int(time.time()),
            'top_performers': altcoin_performances[:10],
            'worst_performers': altcoin_performances[-10:],
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'data_source': 'CryptoCompare'
        }
        
        print(f"[CryptoCompare] ✓ Index: {index:.1f} ({outperforming_count}/{total_analyzed} outperforming)")
        
        return index, data, True
        
    except Exception as e:
        print(f"[CryptoCompare] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 50, {}, False


if __name__ == "__main__":
    print("Testing CryptoCompare Altcoin Season Index...")
    idx, data, ok = fetch_altcoin_season_coinpaprika()
    print(f"\nIndex: {idx:.1f}")
    print(f"Success: {ok}")
    if data:
        print(f"Outperforming: {data.get('altcoins_outperforming')}/{data.get('altcoins_total')}")
        print(f"BTC 90D: {data.get('btc_performance_90d'):+.2f}%")
        print(f"Data Source: {data.get('data_source')}")
