"""
Multi-Source Price Service
Optimizes price fetching with fallback sources to avoid CoinGecko rate limits.

Priority:
1. OKX API (fastest, most reliable for major coins)
2. Binance API (backup for majors)
3. CoinGecko (fallback, free tier)

Features:
- Parallel fetching from multiple sources
- Automatic fallback on failure
- Aggressive caching (5 min TTL)
- Response under 1 second for cached data
"""

import requests
import time
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st

# Price cache with TTL
_PRICE_CACHE = {
    'data': {},
    'timestamp': 0,
    'ttl': 300  # 5 minutes
}

# Symbol mapping for different exchanges
SYMBOL_MAP = {
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'binancecoin': 'BNB',
    'solana': 'SOL',
    'ripple': 'XRP',
    'cardano': 'ADA',
    'avalanche-2': 'AVAX',
    'polkadot': 'DOT',
    'chainlink': 'LINK',
    'uniswap': 'UNI',
    'sui': 'SUI',
    'arbitrum': 'ARB',
    'optimism': 'OP',
    'cosmos': 'ATOM',
    'near': 'NEAR',
    'aptos': 'APT',
    'starknet': 'STRK',
    'celestia': 'TIA',
    'sei-network': 'SEI',
    'ethena': 'ENA',
    'ether-fi': 'ETHFI',
    'eigenlayer': 'EIGEN',
    'ondo-finance': 'ONDO',
    'mantra-dao': 'OM',
}


def fetch_okx_prices(symbols: List[str]) -> Dict[str, Dict]:
    """
    Fetch prices from OKX - Very fast and reliable.
    
    Args:
        symbols: List of trading symbols (e.g., ['BTC', 'ETH'])
    
    Returns:
        Dict with price data: {symbol: {'price': float, 'change_24h': float}}
    """
    results = {}
    
    try:
        # OKX batch ticker endpoint
        url = 'https://www.okx.com/api/v5/market/tickers?instType=SPOT'
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == '0':
                tickers = {item['instId']: item for item in data.get('data', [])}
                
                for symbol in symbols:
                    inst_id = f'{symbol}-USDT'
                    if inst_id in tickers:
                        ticker = tickers[inst_id]
                        # OKX may use different field names
                        change_pct = float(ticker.get('changeUtc0Utc8', ticker.get('change24h', 0))) * 100
                        
                        results[symbol] = {
                            'price': float(ticker['last']),
                            'change_24h': change_pct,
                            'volume': float(ticker.get('volCcy24h', ticker.get('vol24h', 0))),
                            'source': 'okx'
                        }
    except Exception as e:
        print(f"OKX fetch error: {e}")
    
    return results


def fetch_binance_prices(symbols: List[str]) -> Dict[str, Dict]:
    """
    Fetch prices from Binance - Backup source.
    
    Args:
        symbols: List of trading symbols (e.g., ['BTC', 'ETH'])
    
    Returns:
        Dict with price data
    """
    results = {}
    
    try:
        # Binance 24hr ticker for all symbols
        url = 'https://api.binance.com/api/v3/ticker/24hr'
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            tickers = {item['symbol']: item for item in data}
            
            for symbol in symbols:
                ticker_symbol = f'{symbol}USDT'
                if ticker_symbol in tickers:
                    ticker = tickers[ticker_symbol]
                    results[symbol] = {
                        'price': float(ticker['lastPrice']),
                        'change_24h': float(ticker['priceChangePercent']),
                        'volume': float(ticker['volume']),
                        'source': 'binance'
                    }
    except Exception as e:
        print(f"Binance fetch error: {e}")
    
    return results


def fetch_coingecko_prices(coin_ids: List[str]) -> Dict[str, Dict]:
    """
    Fetch prices from CoinGecko - Fallback (slow, rate limited).
    
    Args:
        coin_ids: List of CoinGecko IDs (e.g., ['bitcoin', 'ethereum'])
    
    Returns:
        Dict with price data
    """
    results = {}
    
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ",".join(coin_ids),
            "price_change_percentage": "1h,24h,7d"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            for item in data:
                coin_id = item['id']
                results[coin_id] = {
                    'price': item.get('current_price', 0),
                    'change_1h': item.get('price_change_percentage_1h_in_currency', 0),
                    'change_24h': item.get('price_change_percentage_24h', 0),
                    'change_7d': item.get('price_change_percentage_7d_in_currency', 0),
                    'image': item.get('image', ''),
                    'volume': item.get('total_volume', 0),
                    'source': 'coingecko'
                }
        elif resp.status_code == 429:
            print("CoinGecko rate limit hit (429)")
    except Exception as e:
        print(f"CoinGecko fetch error: {e}")
    
    return results


def get_multi_source_prices(coin_ids: List[str], force: bool = False) -> Tuple[Dict, Dict, bool, str]:
    """
    Fetch prices from multiple sources with intelligent fallback.
    
    Priority:
    1. Check cache (5 min TTL)
    2. Try OKX for mapped symbols (fast)
    3. Try Binance for unmapped symbols
    4. Fallback to CoinGecko for remaining
    
    Args:
        coin_ids: List of CoinGecko coin IDs
        force: Force refresh, bypass cache
    
    Returns:
        (prices_dict, changes_dict, success, message)
    """
    global _PRICE_CACHE
    
    # Check cache first
    now = time.time()
    if not force and (now - _PRICE_CACHE['timestamp']) < _PRICE_CACHE['ttl']:
        cached_data = _PRICE_CACHE['data']
        if all(cid in cached_data for cid in coin_ids):
            # Extract prices and changes
            prices = {cid: cached_data[cid]['price'] for cid in coin_ids}
            changes = {cid: {
                'change_1h': cached_data[cid].get('change_1h', 0),
                'change_24h': cached_data[cid].get('change_24h', 0),
                'change_7d': cached_data[cid].get('change_7d', 0),
            } for cid in coin_ids}
            return prices, changes, True, "Cached (TTL valid)"
    
    # Prepare symbol lists
    symbols_to_fetch = []
    coinid_to_symbol = {}
    symbol_to_coinid = {}
    unmapped_coins = []
    
    for coin_id in coin_ids:
        if coin_id in SYMBOL_MAP:
            symbol = SYMBOL_MAP[coin_id]
            symbols_to_fetch.append(symbol)
            coinid_to_symbol[coin_id] = symbol
            symbol_to_coinid[symbol] = coin_id
        else:
            unmapped_coins.append(coin_id)
    
    # Fetch from multiple sources in parallel
    results = {}
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        
        # Submit OKX fetch
        if symbols_to_fetch:
            futures['okx'] = executor.submit(fetch_okx_prices, symbols_to_fetch)
        
        # Submit Binance fetch (backup)
        if symbols_to_fetch:
            futures['binance'] = executor.submit(fetch_binance_prices, symbols_to_fetch)
        
        # Submit CoinGecko for unmapped + all (fallback)
        if unmapped_coins or symbols_to_fetch:
            futures['coingecko'] = executor.submit(fetch_coingecko_prices, coin_ids)
        
        # Collect results
        for source, future in futures.items():
            try:
                source_results = future.result(timeout=8)
                results[source] = source_results
            except Exception as e:
                print(f"Error fetching from {source}: {e}")
                results[source] = {}
    
    # Merge results with priority: OKX > Binance > CoinGecko
    final_data = {}
    
    # First, get OKX data (highest priority)
    for symbol, data in results.get('okx', {}).items():
        coin_id = symbol_to_coinid.get(symbol)
        if coin_id:
            final_data[coin_id] = data
    
    # Fill gaps with Binance
    for symbol, data in results.get('binance', {}).items():
        coin_id = symbol_to_coinid.get(symbol)
        if coin_id and coin_id not in final_data:
            final_data[coin_id] = data
    
    # Fill remaining gaps with CoinGecko
    for coin_id, data in results.get('coingecko', {}).items():
        if coin_id not in final_data:
            final_data[coin_id] = data
    
    # Update cache
    _PRICE_CACHE['data'] = final_data
    _PRICE_CACHE['timestamp'] = now
    
    # Extract prices and changes
    prices = {}
    changes = {}
    
    for coin_id in coin_ids:
        if coin_id in final_data:
            data = final_data[coin_id]
            prices[coin_id] = data.get('price', 0)
            changes[coin_id] = {
                'change_1h': data.get('change_1h', data.get('change_24h', 0) / 24),  # Estimate
                'change_24h': data.get('change_24h', 0),
                'change_7d': data.get('change_7d', 0),
                'image': data.get('image', ''),
                'volume': data.get('volume', 0),
                'source': data.get('source', 'unknown')
            }
        else:
            # Missing data
            prices[coin_id] = 0
            changes[coin_id] = {'change_1h': 0, 'change_24h': 0, 'change_7d': 0}
    
    # Calculate success rate
    success_count = sum(1 for p in prices.values() if p > 0)
    success_rate = success_count / len(coin_ids) if coin_ids else 0
    
    # Source breakdown for message
    source_counts = {}
    for data in final_data.values():
        source = data.get('source', 'unknown')
        source_counts[source] = source_counts.get(source, 0) + 1
    
    message = f"Fetched {success_count}/{len(coin_ids)} coins. Sources: {source_counts}"
    
    return prices, changes, success_rate > 0.5, message


@st.cache_data(ttl=300, show_spinner=False)
def get_prices_cached(coin_ids: List[str]) -> Dict:
    """
    Streamlit-cached wrapper for price fetching.
    
    Args:
        coin_ids: List of CoinGecko coin IDs
    
    Returns:
        Combined dict with prices and changes
    """
    prices, changes, success, msg = get_multi_source_prices(coin_ids, force=False)
    
    # Combine into single dict like CoinGecko format
    result = {}
    for coin_id in coin_ids:
        price = prices.get(coin_id, 0)
        change_data = changes.get(coin_id, {})
        
        result[coin_id] = {
            'price': price,
            'change_1h': change_data.get('change_1h', 0),
            'change_1d': change_data.get('change_24h', 0),
            'change_7d': change_data.get('change_7d', 0),
            'image': change_data.get('image', ''),
            'volume': change_data.get('volume', 0),
            'source': change_data.get('source', 'unknown')
        }
    
    return result


if __name__ == '__main__':
    # Test
    test_coins = ['bitcoin', 'ethereum', 'solana', 'sui', 'arbitrum']
    
    print("Testing multi-source price fetching...")
    start = time.time()
    
    prices, changes, success, msg = get_multi_source_prices(test_coins, force=True)
    
    elapsed = time.time() - start
    
    print(f"\n✅ Completed in {elapsed:.2f}s")
    print(f"Status: {msg}")
    print("\nResults:")
    for coin_id in test_coins:
        price = prices.get(coin_id, 0)
        change = changes.get(coin_id, {})
        source = change.get('source', 'unknown')
        print(f"  {coin_id:15s} ${price:10,.2f}  24h: {change.get('change_24h', 0):6.2f}%  [{source}]")
