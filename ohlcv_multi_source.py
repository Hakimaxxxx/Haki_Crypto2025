"""
Multi-Source OHLCV Data Fetcher

Supports fetching 3+ months of historical OHLCV data from multiple sources:
1. OKX (300 candles limit - needs pagination)
2. Binance (1000 candles per call - unlimited history)
3. CryptoCompare (2000 candles limit)

Features:
- Auto-pagination for long timeframes
- Source fallback on errors
- Unified output format
"""

import pandas as pd
import requests
import time
from typing import Optional, Literal
from datetime import datetime, timedelta


def fetch_binance_ohlcv(symbol: str, interval: str = '1h', limit: int = 1000, start_time: Optional[int] = None, end_time: Optional[int] = None) -> pd.DataFrame:
    """
    Fetch OHLCV from Binance Spot API.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        interval: Timeframe ('1m', '5m', '15m', '1h', '4h', '1d', etc.)
        limit: Number of candles (max 1000 per call)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds (for reverse pagination)
    
    Returns:
        DataFrame with columns: datetime, open, high, low, close, volume
    """
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {
            'symbol': symbol.upper(),
            'interval': interval,
            'limit': min(limit, 1000)  # Binance max = 1000
        }
        
        if end_time:
            # Use endTime for reverse pagination (most recent first)
            params['endTime'] = end_time
        elif start_time:
            params['startTime'] = start_time
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return pd.DataFrame()
        
        # Binance format: [timestamp, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        
        # Keep timestamp and convert types
        df['timestamp'] = df['timestamp'].astype('int64')
        df['open'] = df['open'].astype('float')
        df['high'] = df['high'].astype('float')
        df['low'] = df['low'].astype('float')
        df['close'] = df['close'].astype('float')
        df['volume'] = df['volume'].astype('float')
        
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df = df.sort_values('datetime')
        
        return df[['datetime', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
    except Exception as e:
        print(f"[Binance] Error fetching {symbol}: {e}")
        return pd.DataFrame()


def fetch_binance_ohlcv_extended(symbol: str, interval: str = '1h', days: int = 90) -> pd.DataFrame:
    """
    Fetch extended OHLCV from Binance with pagination.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        interval: Timeframe
        days: Number of days to fetch (e.g., 90 for 3 months)
    
    Returns:
        Combined DataFrame with all requested data
    """
    try:
        # Calculate interval in milliseconds
        interval_map = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
        }
        
        interval_ms = interval_map.get(interval.lower(), 60 * 60 * 1000)
        
        # Calculate required candles
        required_candles = int((days * 24 * 60 * 60 * 1000) / interval_ms)
        
        print(f"[Binance Extended] Fetching {required_candles} candles for {symbol} ({days} days, {interval})")
        
        # Strategy: Fetch BACKWARD from now (most recent first)
        # This ensures we always get the latest data
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        all_dfs = []
        current_end = end_time
        calls_made = 0
        
        while current_end > start_time and calls_made < 20:  # Max 20 calls (safety limit)
            # Fetch backward from current_end
            df = fetch_binance_ohlcv(symbol, interval, limit=1000, end_time=current_end)
            
            if df.empty:
                break
            
            all_dfs.append(df)
            calls_made += 1
            
            # Update end time to first candle - 1ms (for next batch)
            first_ts = df['timestamp'].min()
            current_end = first_ts - 1
            
            # Rate limiting
            time.sleep(0.2)
            
            print(f"[Binance Extended] Fetched batch {calls_made}: {len(df)} candles (total: {sum(len(d) for d in all_dfs)})")
            
            # Stop if we have enough data
            if sum(len(d) for d in all_dfs) >= required_candles:
                break
            
            # Stop if we reached the start time
            if first_ts <= start_time:
                break
        
        if not all_dfs:
            return pd.DataFrame()
        
        # Combine all DataFrames
        combined = pd.concat(all_dfs, ignore_index=True)
        combined = combined.drop_duplicates(subset=['timestamp']).sort_values('datetime')
        
        # Trim to exact timeframe (keep only data within requested days)
        combined = combined[combined['timestamp'] >= start_time]
        
        # Limit to exact number of candles requested
        if len(combined) > required_candles:
            # Keep most recent candles
            combined = combined.tail(required_candles)
        
        print(f"[Binance Extended] ✓ Total: {len(combined)} candles (trimmed to {days} days)")
        
        return combined
        
    except Exception as e:
        print(f"[Binance Extended] Error: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def fetch_cryptocompare_ohlcv(symbol: str, interval: str = '1h', limit: int = 2000) -> pd.DataFrame:
    """
    Fetch OHLCV from CryptoCompare.
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH')
        interval: 'minute', 'hour', or 'day'
        limit: Number of candles (max 2000)
    
    Returns:
        DataFrame with OHLCV data
    """
    try:
        # Map interval to CryptoCompare endpoint
        endpoint_map = {
            '1m': 'histominute',
            '5m': 'histominute',
            '15m': 'histominute',
            '1h': 'histohour',
            '4h': 'histohour',
            '1d': 'histoday'
        }
        
        endpoint = endpoint_map.get(interval.lower(), 'histohour')
        
        url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
        params = {
            'fsym': symbol.upper(),
            'tsym': 'USD',
            'limit': min(limit, 2000)  # CryptoCompare max = 2000
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('Response') != 'Success' or not data.get('Data', {}).get('Data'):
            print(f"[CryptoCompare] Error: {data.get('Message', 'Unknown')}")
            return pd.DataFrame()
        
        candles = data['Data']['Data']
        
        df = pd.DataFrame(candles)
        df = df.rename(columns={
            'time': 'timestamp',
            'volumefrom': 'volume'
        })
        
        # Convert timestamp from seconds to milliseconds
        df['timestamp'] = df['timestamp'] * 1000
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']].astype({
            'open': 'float',
            'high': 'float',
            'low': 'float',
            'close': 'float',
            'volume': 'float'
        })
        
        df = df.sort_values('datetime')
        
        print(f"[CryptoCompare] ✓ Fetched {len(df)} candles for {symbol}")
        
        return df
        
    except Exception as e:
        print(f"[CryptoCompare] Error fetching {symbol}: {e}")
        return pd.DataFrame()


def fetch_ohlcv_multi_source(
    symbol: str,
    interval: str = '1h',
    days: int = 90,
    source: Literal['auto', 'binance', 'cryptocompare', 'okx'] = 'auto'
) -> pd.DataFrame:
    """
    Fetch OHLCV data from multiple sources with auto-fallback.
    
    Args:
        symbol: Symbol format varies by source
            - Binance: 'BTCUSDT', 'ETHUSDT'
            - CryptoCompare: 'BTC', 'ETH'
            - OKX: 'BTC-USDT-SWAP'
        interval: Timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
        days: Number of days to fetch (default 90 = 3 months)
        source: Data source ('auto', 'binance', 'cryptocompare', 'okx')
    
    Returns:
        DataFrame with OHLCV data, empty if all sources fail
    """
    # Normalize symbol for different sources
    def to_binance_symbol(s):
        # BTC-USDT-SWAP -> BTCUSDT
        # BTC -> BTCUSDT
        # BTCUSDT -> BTCUSDT
        s = s.upper().replace('-USDT-SWAP', '').replace('-USDT', '').replace('-', '')
        if not s.endswith('USDT'):
            s = s + 'USDT'
        return s
    
    def to_cryptocompare_symbol(s):
        # BTC-USDT-SWAP -> BTC
        # BTCUSDT -> BTC
        return s.upper().split('-')[0].replace('USDT', '')
    
    if source == 'auto':
        # Try Binance first (best for long history)
        print(f"[Multi-Source] Trying Binance for {symbol}...")
        binance_sym = to_binance_symbol(symbol)
        df = fetch_binance_ohlcv_extended(binance_sym, interval, days)
        
        if not df.empty:
            return df
        
        # Fallback to CryptoCompare
        print(f"[Multi-Source] Binance failed, trying CryptoCompare...")
        cc_sym = to_cryptocompare_symbol(symbol)
        
        # Calculate limit based on days and interval
        interval_hours_map = {'1m': 1/60, '5m': 5/60, '15m': 15/60, '1h': 1, '4h': 4, '1d': 24}
        hours_per_candle = interval_hours_map.get(interval.lower(), 1)
        required_candles = int((days * 24) / hours_per_candle)
        
        df = fetch_cryptocompare_ohlcv(cc_sym, interval, limit=min(required_candles, 2000))
        
        if not df.empty:
            return df
        
        print(f"[Multi-Source] All sources failed for {symbol}")
        return pd.DataFrame()
    
    elif source == 'binance':
        binance_sym = to_binance_symbol(symbol)
        return fetch_binance_ohlcv_extended(binance_sym, interval, days)
    
    elif source == 'cryptocompare':
        cc_sym = to_cryptocompare_symbol(symbol)
        interval_hours_map = {'1m': 1/60, '5m': 5/60, '15m': 15/60, '1h': 1, '4h': 4, '1d': 24}
        hours_per_candle = interval_hours_map.get(interval.lower(), 1)
        required_candles = int((days * 24) / hours_per_candle)
        return fetch_cryptocompare_ohlcv(cc_sym, interval, limit=min(required_candles, 2000))
    
    else:
        print(f"[Multi-Source] Unknown source: {source}")
        return pd.DataFrame()


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Multi-Source OHLCV Fetcher")
    print("=" * 60)
    
    # Test 1: Binance extended
    print("\n1. Testing Binance Extended (BTC, 90 days, 1h)...")
    df_binance = fetch_binance_ohlcv_extended('BTCUSDT', '1h', days=90)
    print(f"   Result: {len(df_binance)} candles")
    if not df_binance.empty:
        print(f"   Date range: {df_binance['datetime'].min()} to {df_binance['datetime'].max()}")
    
    # Test 2: CryptoCompare
    print("\n2. Testing CryptoCompare (BTC, 90 days, 1d)...")
    df_cc = fetch_cryptocompare_ohlcv('BTC', '1d', limit=90)
    print(f"   Result: {len(df_cc)} candles")
    if not df_cc.empty:
        print(f"   Date range: {df_cc['datetime'].min()} to {df_cc['datetime'].max()}")
    
    # Test 3: Multi-source auto
    print("\n3. Testing Multi-Source Auto (ETH, 90 days, 4h)...")
    df_multi = fetch_ohlcv_multi_source('ETH-USDT-SWAP', '4h', days=90, source='auto')
    print(f"   Result: {len(df_multi)} candles")
    if not df_multi.empty:
        print(f"   Date range: {df_multi['datetime'].min()} to {df_multi['datetime'].max()}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
