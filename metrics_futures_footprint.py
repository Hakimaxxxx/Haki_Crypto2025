"""
Futures Footprint Chart - Order Flow Analysis

Footprint chart shows BID/ASK volume at each price level within a candle,
helping traders identify:
- Buy/Sell pressure zones
- Absorption (large volume with small price movement)
- Aggressive buying/selling (market orders)
- Volume imbalance (delta)

Data sources:
- Binance Futures Trades API (real-time trades with side)
- OKX Futures Trades API (backup)
- Bybit Futures Trades API (alternative)

Display:
1. Footprint heatmap (volume delta by price level)
2. Cumulative delta line (running total of buy - sell)
3. Volume profile bars (horizontal bars showing volume at each price)
4. Bid/Ask ratio indicator

Technical:
- Fetches recent trades with timestamps, prices, quantities, and sides (BUY/SELL)
- Aggregates into price bins for selected timeframe
- Calculates delta (buy_volume - sell_volume) for each bin
- Color-codes cells based on delta strength

"""

import os
import json
import time
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import requests

CACHE_FILE = 'futures_footprint_cache.json'
CACHE_TTL = 60  # 1 minute for real-time footprint

# Symbol mapping for different exchanges
SYMBOL_MAP = {
    'BTC': {'binance': 'BTCUSDT', 'okx': 'BTC-USDT-SWAP', 'bybit': 'BTCUSDT'},
    'ETH': {'binance': 'ETHUSDT', 'okx': 'ETH-USDT-SWAP', 'bybit': 'ETHUSDT'},
    'SOL': {'binance': 'SOLUSDT', 'okx': 'SOL-USDT-SWAP', 'bybit': 'SOLUSDT'},
    'BNB': {'binance': 'BNBUSDT', 'okx': 'BNB-USDT-SWAP', 'bybit': 'BNBUSDT'},
    'XRP': {'binance': 'XRPUSDT', 'okx': 'XRP-USDT-SWAP', 'bybit': 'XRPUSDT'},
    'DOGE': {'binance': 'DOGEUSDT', 'okx': 'DOGE-USDT-SWAP', 'bybit': 'DOGEUSDT'},
    'ADA': {'binance': 'ADAUSDT', 'okx': 'ADA-USDT-SWAP', 'bybit': 'ADAUSDT'},
    'AVAX': {'binance': 'AVAXUSDT', 'okx': 'AVAX-USDT-SWAP', 'bybit': 'AVAXUSDT'},
    'SHIB': {'binance': 'SHIBUSDT', 'okx': 'SHIB-USDT-SWAP', 'bybit': 'SHIBUSDT'},
    'TON': {'binance': 'TONUSDT', 'okx': 'TON-USDT-SWAP', 'bybit': 'TONUSDT'},
    'LINK': {'binance': 'LINKUSDT', 'okx': 'LINK-USDT-SWAP', 'bybit': 'LINKUSDT'},
    'DOT': {'binance': 'DOTUSDT', 'okx': 'DOT-USDT-SWAP', 'bybit': 'DOTUSDT'},
    'MATIC': {'binance': 'MATICUSDT', 'okx': 'MATIC-USDT-SWAP', 'bybit': 'MATICUSDT'},
    'UNI': {'binance': 'UNIUSDT', 'okx': 'UNI-USDT-SWAP', 'bybit': 'UNIUSDT'},
    'ARB': {'binance': 'ARBUSDT', 'okx': 'ARB-USDT-SWAP', 'bybit': 'ARBUSDT'},
    'OP': {'binance': 'OPUSDT', 'okx': 'OP-USDT-SWAP', 'bybit': 'OPUSDT'},
    'LTC': {'binance': 'LTCUSDT', 'okx': 'LTC-USDT-SWAP', 'bybit': 'LTCUSDT'},
    'ATOM': {'binance': 'ATOMUSDT', 'okx': 'ATOM-USDT-SWAP', 'bybit': 'ATOMUSDT'},
    'ETC': {'binance': 'ETCUSDT', 'okx': 'ETC-USDT-SWAP', 'bybit': 'ETCUSDT'},
    'APT': {'binance': 'APTUSDT', 'okx': 'APT-USDT-SWAP', 'bybit': 'APTUSDT'},
    'SUI': {'binance': 'SUIUSDT', 'okx': 'SUI-USDT-SWAP', 'bybit': 'SUIUSDT'},
    'NEAR': {'binance': 'NEARUSDT', 'okx': 'NEAR-USDT-SWAP', 'bybit': 'NEARUSDT'},
    'FIL': {'binance': 'FILUSDT', 'okx': 'FIL-USDT-SWAP', 'bybit': 'FILUSDT'},
    'TAO': {'binance': 'TAOUSDT', 'okx': 'TAO-USDT-SWAP', 'bybit': 'TAOUSDT'},
    'INJ': {'binance': 'INJUSDT', 'okx': 'INJ-USDT-SWAP', 'bybit': 'INJUSDT'},
    'SEI': {'binance': 'SEIUSDT', 'okx': 'SEI-USDT-SWAP', 'bybit': 'SEIUSDT'},
    'TIA': {'binance': 'TIAUSDT', 'okx': 'TIA-USDT-SWAP', 'bybit': 'TIAUSDT'},
    'WLD': {'binance': 'WLDUSDT', 'okx': 'WLD-USDT-SWAP', 'bybit': 'WLDUSDT'},
    'PEPE': {'binance': 'PEPEUSDT', 'okx': 'PEPE-USDT-SWAP', 'bybit': 'PEPEUSDT'},
    'WIF': {'binance': 'WIFUSDT', 'okx': 'WIF-USDT-SWAP', 'bybit': 'WIFUSDT'},
}


def load_cache() -> Dict:
    """Load cached footprint data."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_cache(cache: Dict):
    """Save footprint data to cache."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Cache save error: {e}")


def fetch_binance_klines(
    symbol: str = 'BTCUSDT',
    interval: str = '5m',
    days: int = 7
) -> pd.DataFrame:
    """
    Fetch historical klines (candlestick) data from Binance Futures.
    
    API: GET /fapi/v1/klines
    Returns: DataFrame with OHLCV + taker buy/sell volume
    
    This gives us much longer history (up to 1000 candles = 7 days for 5m)
    compared to aggTrades which only gives recent minutes.
    """
    try:
        url = 'https://fapi.binance.com/fapi/v1/klines'
        
        # Calculate limit based on days and interval
        interval_minutes = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '1d': 1440
        }
        minutes_per_candle = interval_minutes.get(interval, 5)
        limit = min(int(days * 24 * 60 / minutes_per_candle), 1000)  # Binance max 1000
        
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[Binance Klines] Error {response.status_code}: {response.text}")
            return pd.DataFrame()
        
        data = response.json()
        
        if not data:
            print(f"[Binance Klines] No data for {symbol}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        # Kline format: [OpenTime, Open, High, Low, Close, Volume, CloseTime, QuoteVolume, Trades, TakerBuyBase, TakerBuyQuote, Ignore]
        candles = []
        for k in data:
            candles.append({
                'time': pd.to_datetime(k[0], unit='ms'),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'taker_buy_volume': float(k[9]),  # Taker buy base asset volume
                'taker_sell_volume': float(k[5]) - float(k[9]),  # Total - TakerBuy = TakerSell
                'num_trades': int(k[8])
            })
        
        df = pd.DataFrame(candles)
        print(f"[Binance Klines] Fetched {len(df)} candles for {symbol} ({interval}, ~{days} days)")
        return df
        
    except requests.Timeout:
        print(f"[Binance Klines] Timeout for {symbol}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[Binance Klines] Error: {e}")
        return pd.DataFrame()


def fetch_binance_trades(symbol: str = 'BTCUSDT', limit: int = 1000) -> pd.DataFrame:
    """
    Fetch recent trades from Binance Futures (for real-time analysis).
    
    API: GET /fapi/v1/aggTrades
    Returns: DataFrame with columns [time, price, qty, side]
    
    NOTE: This only gives recent trades (last few minutes).
    For longer history, use fetch_binance_klines() instead.
    
    Side determination:
    - If buyer is maker: side = SELL (taker sold into bid)
    - If buyer is taker: side = BUY (taker bought from ask)
    """
    try:
        url = 'https://fapi.binance.com/fapi/v1/aggTrades'
        params = {
            'symbol': symbol,
            'limit': limit  # Max 1000
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[Binance Trades] Error {response.status_code}: {response.text}")
            return pd.DataFrame()
        
        data = response.json()
        
        if not data:
            print(f"[Binance Trades] No data for {symbol}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        trades = []
        for trade in data:
            trades.append({
                'time': pd.to_datetime(trade['T'], unit='ms'),
                'price': float(trade['p']),
                'qty': float(trade['q']),
                'side': 'BUY' if trade['m'] == False else 'SELL',  # m=False means buyer is taker (BUY)
                'trade_id': trade['a']
            })
        
        df = pd.DataFrame(trades)
        print(f"[Binance Trades] Fetched {len(df)} trades for {symbol}")
        return df
        
    except requests.Timeout:
        print(f"[Binance Trades] Timeout for {symbol}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[Binance Trades] Error: {e}")
        return pd.DataFrame()


def fetch_okx_trades(symbol: str = 'BTC-USDT-SWAP', limit: int = 100) -> pd.DataFrame:
    """
    Fetch recent trades from OKX Futures.
    
    API: GET /api/v5/market/trades
    Returns: DataFrame with columns [time, price, qty, side]
    """
    try:
        url = 'https://www.okx.com/api/v5/market/trades'
        params = {
            'instId': symbol,
            'limit': limit  # Max 100
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[OKX Trades] Error {response.status_code}: {response.text}")
            return pd.DataFrame()
        
        result = response.json()
        
        if result.get('code') != '0':
            print(f"[OKX Trades] API error: {result.get('msg')}")
            return pd.DataFrame()
        
        data = result.get('data', [])
        
        if not data:
            print(f"[OKX Trades] No data for {symbol}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        trades = []
        for trade in data:
            trades.append({
                'time': pd.to_datetime(int(trade['ts']), unit='ms'),
                'price': float(trade['px']),
                'qty': float(trade['sz']),
                'side': trade['side'].upper(),  # 'buy' or 'sell'
                'trade_id': trade['tradeId']
            })
        
        df = pd.DataFrame(trades)
        print(f"[OKX Trades] Fetched {len(df)} trades for {symbol}")
        return df
        
    except requests.Timeout:
        print(f"[OKX Trades] Timeout for {symbol}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[OKX Trades] Error: {e}")
        return pd.DataFrame()


def convert_klines_to_footprint(klines_df: pd.DataFrame) -> Dict:
    """
    Convert klines DataFrame to footprint format.
    
    Since klines already have OHLC and taker buy/sell volumes,
    we can directly create footprint structure without aggregating trades.
    
    Args:
        klines_df: DataFrame with columns [time, open, high, low, close, volume, taker_buy_volume, taker_sell_volume]
    
    Returns:
        Dict with footprint structure (same as aggregate_footprint_data)
    """
    if klines_df.empty:
        return {'candles': []}
    
    candles = []
    
    for _, row in klines_df.iterrows():
        buy_volume = row['taker_buy_volume']
        sell_volume = row['taker_sell_volume']
        total_volume = row['volume']
        delta = buy_volume - sell_volume
        
        # Create simplified price levels (since we don't have tick-by-tick data)
        # We'll use OHLC as 4 price levels
        price_levels = []
        
        # Distribute volume across OHLC levels
        # This is an approximation since we don't have real tick data
        for price in [row['open'], row['high'], row['low'], row['close']]:
            level_buy = buy_volume / 4
            level_sell = sell_volume / 4
            
            price_levels.append({
                'price': price,
                'buy_vol': level_buy,
                'sell_vol': level_sell,
                'delta': level_buy - level_sell,
                'total_vol': (level_buy + level_sell)
            })
        
        candles.append({
            'start_time': row['time'],
            'end_time': row['time'],  # Same as start for klines
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'total_volume': total_volume,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'delta': delta,
            'price_levels': price_levels
        })
    
    return {'candles': candles}


def aggregate_footprint_data(
    df: pd.DataFrame,
    timeframe: str = '5min',
    price_bins: int = 50
) -> Dict:
    """
    Aggregate trade data into footprint format.
    
    Args:
        df: DataFrame with columns [time, price, qty, side]
        timeframe: Candle timeframe (1min, 5min, 15min, 1h)
        price_bins: Number of price levels to display
    
    Returns:
        Dict with structure:
        {
            'candles': [
                {
                    'start_time': datetime,
                    'end_time': datetime,
                    'open': float,
                    'high': float,
                    'low': float,
                    'close': float,
                    'total_volume': float,
                    'buy_volume': float,
                    'sell_volume': float,
                    'delta': float,
                    'price_levels': [
                        {
                            'price': float,
                            'buy_vol': float,
                            'sell_vol': float,
                            'delta': float
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    if df.empty:
        return {'candles': []}
    
    # Convert timeframe to pandas frequency
    freq_map = {
        '1min': '1min',
        '5min': '5min',
        '15min': '15min',
        '30min': '30min',
        '1h': '1h',
        '4h': '4h'
    }
    freq = freq_map.get(timeframe, '5min')
    
    # Group by time bins
    df = df.sort_values('time')
    df['time_bin'] = df['time'].dt.floor(freq)
    
    candles = []
    
    for time_bin, group in df.groupby('time_bin'):
        # OHLC calculation
        prices = group['price'].values
        open_price = group.iloc[0]['price']
        high_price = group['price'].max()
        low_price = group['price'].min()
        close_price = group.iloc[-1]['price']
        
        # Volume calculations
        buy_trades = group[group['side'] == 'BUY']
        sell_trades = group[group['side'] == 'SELL']
        
        buy_volume = buy_trades['qty'].sum()
        sell_volume = sell_trades['qty'].sum()
        total_volume = group['qty'].sum()
        delta = buy_volume - sell_volume
        
        # Price level binning
        price_range = high_price - low_price
        if price_range == 0:
            bin_size = 0.01  # Minimal bin size
        else:
            bin_size = price_range / price_bins
        
        # Create price bins
        price_levels = []
        for i in range(price_bins):
            bin_low = low_price + i * bin_size
            bin_high = bin_low + bin_size
            bin_mid = (bin_low + bin_high) / 2
            
            # Filter trades in this price bin
            bin_trades = group[(group['price'] >= bin_low) & (group['price'] < bin_high)]
            
            if not bin_trades.empty:
                bin_buy = bin_trades[bin_trades['side'] == 'BUY']['qty'].sum()
                bin_sell = bin_trades[bin_trades['side'] == 'SELL']['qty'].sum()
                bin_delta = bin_buy - bin_sell
                
                price_levels.append({
                    'price': bin_mid,
                    'buy_vol': bin_buy,
                    'sell_vol': bin_sell,
                    'delta': bin_delta,
                    'total_vol': bin_buy + bin_sell
                })
        
        candles.append({
            'start_time': time_bin,
            'end_time': time_bin + pd.Timedelta(freq),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'total_volume': total_volume,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'delta': delta,
            'price_levels': price_levels
        })
    
    return {'candles': candles}


def plot_candlestick_with_footprint(
    footprint_data: Dict,
    symbol: str = 'BTC',
    exchange: str = 'binance',
    delta_threshold: float = 0.15,
    debug: bool = False,
    max_zones: int = 100  # Limit number of zones to display
) -> Optional[go.Figure]:
    """
    Create candlestick chart with footprint zones overlay (like TradingView).
    
    Features:
    1. OHLC candlesticks (main chart)
    2. Footprint zones highlighted (green for buy pressure, red for sell pressure)
    3. Volume bars below (color-coded by delta)
    4. Smart zone invalidation (if price revisits, zone disappears)
    
    Args:
        footprint_data: Aggregated footprint data
        symbol: Trading symbol
        exchange: Exchange name
        delta_threshold: Minimum delta ratio to show zone (0-1)
        debug: Show debug information about zones
    
    Returns:
        Plotly figure with candlestick + footprint overlay
    """
    candles = footprint_data.get('candles', [])
    
    # Debug: Store zone detection info
    debug_info = {
        'total_candles': len(candles),
        'checked_candles': 0,
        'potential_zones': 0,
        'valid_zones': 0,
        'invalidated_zones': 0
    }
    
    if not candles:
        return None
    
    # Create subplots: Candlestick (70%) + Volume (30%)
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        subplot_titles=(f'{symbol} Footprint Analysis - {exchange.upper()}', 'Volume Delta'),
        vertical_spacing=0.05,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
    )
    
    # Extract OHLC data
    times = [c['start_time'] for c in candles]
    opens = [c['open'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    closes = [c['close'] for c in candles]
    volumes = [c['total_volume'] for c in candles]
    deltas = [c['delta'] for c in candles]
    
    # Add candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=times,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name='Price',
            increasing_line_color='#10b981',
            decreasing_line_color='#ef4444',
            showlegend=False
        ),
        row=1, col=1
    )
    
    # Identify significant footprint zones
    # OPTIMIZED: Collect all potential zones first, then sort and limit
    potential_zones = []
    
    for i, candle in enumerate(candles):
        total_vol = candle['total_volume']
        if total_vol == 0:
            continue
        
        debug_info['checked_candles'] += 1
        delta = candle['delta']
        delta_ratio = abs(delta) / total_vol
        
        # Collect zones above threshold
        if delta_ratio >= delta_threshold:
            # Calculate zone height based on candle body (not fixed %)
            candle_open = candle['open']
            candle_close = candle['close']
            candle_body_height = abs(candle_close - candle_open)
            
            # Use body height, with minimum height for doji candles
            zone_height = max(candle_body_height, candle['high'] - candle['low']) * 0.5
            
            potential_zones.append({
                'index': i,
                'price': candle['close'],
                'open': candle_open,
                'close': candle_close,
                'high': candle['high'],
                'low': candle['low'],
                'time': candle['start_time'],
                'type': 'BUY' if delta > 0 else 'SELL',
                'delta': delta,
                'delta_ratio': delta_ratio,
                'zone_height': zone_height
            })
    
    debug_info['potential_zones'] = len(potential_zones)
    
    # Sort by delta_ratio (strongest first) and limit to max_zones
    potential_zones.sort(key=lambda x: x['delta_ratio'], reverse=True)
    potential_zones = potential_zones[:max_zones]
    
    # Now find end times for selected zones only (much faster)
    footprint_zones = []
    
    for zone_data in potential_zones:
        i = zone_data['index']
        zone_price = zone_data['price']
        zone_start_time = zone_data['time']
        zone_type = zone_data['type']
        zone_height = zone_data['zone_height']
        
        # Define zone boundaries
        zone_top = zone_price + zone_height
        zone_bottom = zone_price - zone_height
        
        # Find where zone ends (smart invalidation)
        zone_end_time = times[-1]
        tested = False
        tolerance = zone_price * 0.02
        
        # Optimized: Only check candles after this zone
        for j in range(i + 1, len(candles)):
            future_candle = candles[j]
            future_close = future_candle['close']
            future_open = future_candle['open']
            future_low = future_candle['low']
            future_high = future_candle['high']
            
            # Calculate future candle type
            is_future_bullish = future_close > future_open
            is_future_bearish = future_close < future_open
            
            # Smart invalidation logic:
            # Zone only disappears if candle CLOSES through it with opposite direction
            
            # For BUY zones (green):
            if zone_type == 'BUY':
                # Only invalidate if bearish candle closes BELOW zone
                if is_future_bearish and future_close < zone_bottom:
                    zone_end_time = future_candle['start_time']
                    tested = True
                    debug_info['invalidated_zones'] += 1
                    break
            
            # For SELL zones (red):
            else:  # SELL
                # Only invalidate if bullish candle closes ABOVE zone
                if is_future_bullish and future_close > zone_top:
                    zone_end_time = future_candle['start_time']
                    tested = True
                    debug_info['invalidated_zones'] += 1
                    break
        
        debug_info['valid_zones'] += 1
        footprint_zones.append({
            'start_time': zone_start_time,
            'end_time': zone_end_time,
            'price': zone_price,
            'zone_height': zone_height,
            'type': zone_data['type'],
            'delta': zone_data['delta'],
            'delta_ratio': zone_data['delta_ratio'],
            'candle_index': i,
            'tested': tested
        })
    
    # Add footprint zone markers
    # OPTIMIZED: Limit annotations to top zones only
    for idx, zone in enumerate(footprint_zones):
        color = '#10b981' if zone['type'] == 'BUY' else '#ef4444'
        
        # Base opacity - higher for stronger zones
        base_opacity = min(0.5 + zone['delta_ratio'] * 0.4, 0.85)
        
        # Use dynamic zone height (based on candle body)
        zone_height = zone['zone_height']
        
        # Add filled rectangle for zone
        fig.add_shape(
            type="rect",
            x0=zone['start_time'],
            x1=zone['end_time'],
            y0=zone['price'] - zone_height,
            y1=zone['price'] + zone_height,
            fillcolor=color,
            opacity=base_opacity,
            line=dict(color=color, width=2),
            row=1, col=1
        )
        
        # Add horizontal line - only for top 30 zones to avoid clutter
        if idx < 30:
            fig.add_shape(
                type="line",
                x0=zone['start_time'],
                x1=zone['end_time'],
                y0=zone['price'],
                y1=zone['price'],
                line=dict(color=color, width=2, dash='solid'),
                opacity=base_opacity,
                row=1, col=1
            )
        
        # Add text annotation - only for top 15 strongest zones
        if idx < 15:
            annotation_text = f"{zone['delta_ratio']*100:.0f}%"
            
            fig.add_annotation(
                x=zone['end_time'],
                y=zone['price'],
                text=annotation_text,
                showarrow=False,
                bgcolor=color,
                opacity=0.9,
                font=dict(size=9, color='white', family='Arial Black'),
                bordercolor='white',
                borderwidth=1,
                borderpad=2,
                row=1, col=1
            )
    
    # Volume bars (color-coded by delta)
    volume_colors = ['#10b981' if d > 0 else '#ef4444' for d in deltas]
    
    fig.add_trace(
        go.Bar(
            x=times,
            y=volumes,
            name='Volume',
            marker_color=volume_colors,
            opacity=0.6,
            showlegend=False,
            hovertemplate='Time: %{x}<br>Volume: %{y:.2f}<br>Delta: %{customdata:+.2f}<extra></extra>',
            customdata=deltas
        ),
        row=2, col=1
    )
    
    # Layout
    fig.update_layout(
        height=800,
        showlegend=True,
        hovermode='x unified',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=60, r=40, t=80, b=60),
        xaxis_rangeslider_visible=False
    )
    
    # Update axes
    fig.update_xaxes(title_text='', row=1, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.1)')
    fig.update_xaxes(title_text='Time', row=2, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.1)')
    fig.update_yaxes(title_text='Price ($)', row=1, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(title_text='Volume', row=2, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    
    # Return both figure and debug info
    if debug:
        return fig, debug_info
    else:
        return fig


def plot_footprint_chart(
    footprint_data: Dict,
    symbol: str = 'BTC',
    exchange: str = 'binance',
    show_cumulative_delta: bool = True
) -> Optional[go.Figure]:
    """
    Create interactive footprint chart with:
    1. Heatmap showing bid/ask volume at each price level
    2. Cumulative delta line overlay
    3. Volume profile bars
    """
    candles = footprint_data.get('candles', [])
    
    if not candles:
        return None
    
    # Create subplots: footprint heatmap + cumulative delta
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.75, 0.25],
        subplot_titles=(
            f'{symbol} Footprint Chart - {exchange.upper()}',
            'Cumulative Delta'
        ),
        vertical_spacing=0.08,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
    )
    
    # Prepare data for heatmap
    all_prices = []
    all_times = []
    all_deltas = []
    all_volumes = []
    
    for candle in candles:
        time_str = candle['start_time'].strftime('%H:%M')
        
        for level in candle['price_levels']:
            all_times.append(time_str)
            all_prices.append(level['price'])
            all_deltas.append(level['delta'])
            all_volumes.append(level['total_vol'])
    
    # Create DataFrame for easier plotting
    if all_prices:
        heatmap_df = pd.DataFrame({
            'time': all_times,
            'price': all_prices,
            'delta': all_deltas,
            'volume': all_volumes
        })
        
        # Pivot for heatmap
        pivot = heatmap_df.pivot_table(
            index='price',
            columns='time',
            values='delta',
            aggfunc='sum',
            fill_value=0
        )
        
        # Add heatmap trace
        fig.add_trace(
            go.Heatmap(
                z=pivot.values,
                x=pivot.columns,
                y=pivot.index,
                colorscale=[
                    [0, '#ef4444'],      # Strong sell (red)
                    [0.4, '#fca5a5'],    # Weak sell (light red)
                    [0.5, '#ffffff'],    # Neutral (white)
                    [0.6, '#86efac'],    # Weak buy (light green)
                    [1, '#10b981']       # Strong buy (green)
                ],
                zmid=0,
                colorbar=dict(
                    title='Delta',
                    x=1.15
                ),
                hovertemplate='Time: %{x}<br>Price: $%{y:.2f}<br>Delta: %{z:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # Cumulative delta
    if show_cumulative_delta:
        cum_delta = []
        times = []
        running_delta = 0
        
        for candle in candles:
            running_delta += candle['delta']
            cum_delta.append(running_delta)
            times.append(candle['start_time'])
        
        # Determine color based on trend
        delta_colors = ['#10b981' if d > 0 else '#ef4444' for d in cum_delta]
        
        fig.add_trace(
            go.Scatter(
                x=times,
                y=cum_delta,
                mode='lines+markers',
                name='Cumulative Delta',
                line=dict(color='#3b82f6', width=2),
                marker=dict(size=6, color=delta_colors),
                fill='tozeroy',
                fillcolor='rgba(59, 130, 246, 0.1)',
                hovertemplate='Time: %{x}<br>Cum. Delta: %{y:.2f}<extra></extra>'
            ),
            row=2, col=1
        )
    
    # Layout
    fig.update_layout(
        height=800,
        showlegend=True,
        hovermode='closest',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=80, r=120, t=80, b=60)
    )
    
    # Update axes
    fig.update_xaxes(title_text='Time', row=1, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.1)')
    fig.update_xaxes(title_text='Time', row=2, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.1)')
    fig.update_yaxes(title_text='Price ($)', row=1, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(title_text='Cumulative Delta', row=2, col=1, showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    
    return fig


def plot_volume_profile(footprint_data: Dict, symbol: str = 'BTC') -> Optional[go.Figure]:
    """
    Create horizontal volume profile chart showing volume distribution by price.
    """
    candles = footprint_data.get('candles', [])
    
    if not candles:
        return None
    
    # Aggregate all price levels across all candles
    price_volume_map = defaultdict(lambda: {'buy': 0, 'sell': 0})
    
    for candle in candles:
        for level in candle['price_levels']:
            price = round(level['price'], 2)  # Round to avoid floating point issues
            price_volume_map[price]['buy'] += level['buy_vol']
            price_volume_map[price]['sell'] += level['sell_vol']
    
    # Convert to lists
    prices = sorted(price_volume_map.keys())
    buy_volumes = [price_volume_map[p]['buy'] for p in prices]
    sell_volumes = [price_volume_map[p]['sell'] for p in prices]
    
    # Create figure
    fig = go.Figure()
    
    # Buy volume (green, positive direction)
    fig.add_trace(go.Bar(
        y=prices,
        x=buy_volumes,
        orientation='h',
        name='Buy Volume',
        marker_color='#10b981',
        opacity=0.7,
        hovertemplate='Price: $%{y:.2f}<br>Buy Volume: %{x:.2f}<extra></extra>'
    ))
    
    # Sell volume (red, negative direction)
    fig.add_trace(go.Bar(
        y=prices,
        x=[-v for v in sell_volumes],  # Negative for left side
        orientation='h',
        name='Sell Volume',
        marker_color='#ef4444',
        opacity=0.7,
        hovertemplate='Price: $%{y:.2f}<br>Sell Volume: %{x:.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        title=f'{symbol} Volume Profile - Horizontal Distribution',
        xaxis_title='Volume',
        yaxis_title='Price ($)',
        barmode='overlay',
        height=600,
        showlegend=True,
        hovermode='y unified',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=80, r=40, t=80, b=60)
    )
    
    fig.update_xaxes(showgrid=True, gridcolor='rgba(128,128,128,0.1)', zeroline=True, zerolinecolor='white')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)')
    
    return fig


def calculate_footprint_metrics(footprint_data: Dict) -> Dict:
    """
    Calculate key metrics from footprint data:
    - Total buy/sell volume
    - Net delta
    - Absorption zones (high volume, low price movement)
    - Aggression ratio (buy volume / sell volume)
    """
    candles = footprint_data.get('candles', [])
    
    if not candles:
        return {}
    
    total_buy = sum(c['buy_volume'] for c in candles)
    total_sell = sum(c['sell_volume'] for c in candles)
    total_volume = total_buy + total_sell
    net_delta = total_buy - total_sell
    
    # Aggression ratio
    aggression_ratio = total_buy / total_sell if total_sell > 0 else 0
    
    # Find POC (Point of Control) - price level with highest volume
    all_levels = []
    for candle in candles:
        all_levels.extend(candle['price_levels'])
    
    if all_levels:
        poc_level = max(all_levels, key=lambda x: x['total_vol'])
        poc_price = poc_level['price']
    else:
        poc_price = 0
    
    # Latest candle delta
    latest_delta = candles[-1]['delta'] if candles else 0
    
    return {
        'total_buy_volume': total_buy,
        'total_sell_volume': total_sell,
        'total_volume': total_volume,
        'net_delta': net_delta,
        'aggression_ratio': aggression_ratio,
        'poc_price': poc_price,
        'latest_candle_delta': latest_delta,
        'num_candles': len(candles)
    }


def show_futures_footprint_metric():
    """Display Futures Footprint metric in Streamlit."""
    st.markdown("## 👣 Futures Footprint Chart - Order Flow Analysis")
    
    st.markdown("""
    **Footprint Chart** hiển thị chi tiết buy/sell volume tại từng price level trong mỗi candle, 
    giúp bạn nhìn thấy:
    - 🟢 **Buyer pressure zones** (aggressive buying)
    - 🔴 **Seller pressure zones** (aggressive selling)
    - ⚖️ **Volume imbalance** (delta) tại mỗi mức giá
    - 📊 **Absorption zones** (high volume but small price movement)
    """)
    
    # Settings Row 1
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        coins = list(SYMBOL_MAP.keys())
        selected_coin = st.selectbox('Select Coin', coins, index=0, key='footprint_coin')
    
    with col2:
        exchanges = ['binance', 'okx']
        selected_exchange = st.selectbox('Exchange', exchanges, index=0, key='footprint_exchange')
    
    with col3:
        timeframes = ['1m', '5m', '15m', '30m', '1h', '4h']
        selected_timeframe = st.selectbox('Timeframe', timeframes, index=1, key='footprint_tf')
    
    with col4:
        history_days = [1, 3, 7, 14, 30]
        selected_days = st.selectbox('History (days)', history_days, index=2, key='footprint_days')
    
    with col5:
        chart_types = ['Candlestick + Zones', 'Footprint Heatmap', 'Volume Profile']
        chart_type = st.selectbox('Chart Type', chart_types, index=0, key='footprint_chart_type')
    
    # Settings Row 2 (for Candlestick chart)
    if chart_type == 'Candlestick + Zones':
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            delta_threshold = st.slider(
                'Delta Threshold',
                min_value=0.05,
                max_value=0.9,
                value=0.15,
                step=0.05,
                key='footprint_delta_threshold',
                help='Minimum delta ratio để hiển thị zone (càng cao = ít zone hơn, chỉ signal mạnh)'
            )
        with col_b:
            max_zones = st.slider(
                'Max Zones',
                min_value=20,
                max_value=200,
                value=80,
                step=20,
                key='footprint_max_zones',
                help='Số zones tối đa hiển thị (giảm để load nhanh hơn)'
            )
        with col_c:
            st.metric('Threshold', f'{delta_threshold*100:.0f}%', 
                     delta='Delta filter')
        with col_d:
            # Show estimated candles
            interval_to_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240}
            minutes = interval_to_minutes.get(selected_timeframe, 5)
            estimated_candles = min(int(selected_days * 24 * 60 / minutes), 1000)
            st.metric('Est. Candles', f'{estimated_candles}', delta=f'{selected_days}d history')
    
    # Fetch button
    if st.button('🔄 Fetch Footprint Data', key='fetch_footprint'):
        st.session_state['footprint_refresh'] = time.time()
    
    # Fetch data - Use KLINES for historical data (better for longer timeframes)
    with st.spinner(f'Fetching {selected_days} days of {selected_timeframe} data from {selected_exchange.upper()}...'):
        symbol_map = SYMBOL_MAP.get(selected_coin, {})
        exchange_symbol = symbol_map.get(selected_exchange)
        
        if not exchange_symbol:
            st.error(f'{selected_coin} not available on {selected_exchange}')
            return
        
        # Initialize variables
        raw_data_df = pd.DataFrame()  # For displaying in expander
        footprint_data = {'candles': []}
        
        # Fetch klines (better for historical data)
        if selected_exchange == 'binance':
            klines_df = fetch_binance_klines(
                exchange_symbol,
                interval=selected_timeframe,
                days=selected_days
            )
            
            if not klines_df.empty:
                # Convert klines to footprint format
                footprint_data = convert_klines_to_footprint(klines_df)
                raw_data_df = klines_df  # For display
            else:
                st.warning('No kline data available. Try different settings.')
                return
                
        elif selected_exchange == 'okx':
            # OKX fallback - still use trades for now (can add klines later)
            trades_df = fetch_okx_trades(exchange_symbol, limit=100)
            
            if not trades_df.empty:
                footprint_data = aggregate_footprint_data(
                    trades_df,
                    timeframe=selected_timeframe,
                    price_bins=50
                )
                raw_data_df = trades_df  # For display
            else:
                st.warning('No trade data available. Try Binance.')
                return
        else:
            st.error('Exchange not supported')
            return
        
        # Calculate metrics
        metrics = calculate_footprint_metrics(footprint_data)
    
    # Display KPIs
    st.markdown("### 📊 Footprint Metrics")
    
    kpi_cols = st.columns(5)
    
    with kpi_cols[0]:
        st.metric(
            'Total Volume',
            f"{metrics.get('total_volume', 0):.2f}",
            delta=None
        )
    
    with kpi_cols[1]:
        net_delta = metrics.get('net_delta', 0)
        st.metric(
            'Net Delta',
            f"{net_delta:+.2f}",
            delta='Bullish' if net_delta > 0 else 'Bearish',
            delta_color='normal' if net_delta > 0 else 'inverse'
        )
    
    with kpi_cols[2]:
        aggr_ratio = metrics.get('aggression_ratio', 0)
        st.metric(
            'Aggression Ratio',
            f"{aggr_ratio:.2f}",
            delta='Buy Pressure' if aggr_ratio > 1 else 'Sell Pressure'
        )
    
    with kpi_cols[3]:
        st.metric(
            'POC Price',
            f"${metrics.get('poc_price', 0):,.2f}",
            delta=None
        )
    
    with kpi_cols[4]:
        latest_delta = metrics.get('latest_candle_delta', 0)
        st.metric(
            'Latest Candle Δ',
            f"{latest_delta:+.2f}",
            delta='Buying' if latest_delta > 0 else 'Selling'
        )
    
    # Chart Selection
    if chart_type == 'Candlestick + Zones':
        st.markdown("### 📊 Candlestick with Footprint Zones")
        st.caption("🟢 Green zones = Strong buy pressure | 🔴 Red zones = Strong sell pressure | Faded zones = Already tested by price")
        
        # Add explanation expander
        with st.expander("ℹ️ Cách đọc Footprint Zones & Metrics", expanded=False):
            st.markdown("""
            ### 📈 **Số % trên chart** (VD: 38%, 25%, 19%)
            
            **Delta Ratio** = `|Buy Volume - Sell Volume| / Total Volume`
            
            **Ví dụ thực tế**:
            - **38% 🟢**: Trong candle này, lực mua áp đảo lực bán 38%
            - **25% 🔴**: Trong candle này, lực bán áp đảo lực mua 25%
            
            **Công thức**:
            ```
            Candle có:
            - Buy Volume: 1000 BTC
            - Sell Volume: 600 BTC
            - Total: 1600 BTC
            
            Delta = 1000 - 600 = 400 BTC
            Delta Ratio = 400 / 1600 = 25%
            → Zone xanh với label "25%"
            ```
            
            ---
            
            ### 🎯 **Debug Metrics giải thích**:
            
            1. **Total Candles**: Tổng số nến trên chart (VD: 7 ngày × 15m = 672 nến)
            
            2. **Analyzed**: Số nến đã phân tích để tìm zones (thường = Total Candles)
            
            3. **Potential Zones**: Số zones có Delta Ratio ≥ Threshold
               - VD: 560 nến có delta ≥ 5%
               - Chưa filter theo độ mạnh, chỉ filter theo threshold
            
            4. **Tested Zones**: Zones mà giá đã quay lại test
               - Zones này ngắn hơn (dừng khi giá chạm vào)
               - Cho thấy zones đã được "confirm" bởi price action
            
            5. **Total Zones**: Số zones hiển thị trên chart
               - Hệ thống chọn N zones **mạnh nhất** từ Potential Zones
               - Giới hạn này tránh lag (điều chỉnh bằng Max Zones slider)
            
            ---
            
            ### 💡 **Cách trade với Footprint Zones**:
            
            **🟢 Green Zones (Buy Pressure)**:
            - Ở **bottom**: Support zone - Xem xét LONG khi giá test lại
            - Ở **top**: Breakout zone - Bulls đang kiểm soát
            - **Zone chỉ biến mất khi**: Nến đỏ đóng cửa **DƯỚI** zone (sellers take control)
            - **Zone tồn tại khi**: Nến xanh test lại nhưng close **TRÊN** zone (buyers defend)
            
            **🔴 Red Zones (Sell Pressure)**:
            - Ở **top**: Resistance zone - Xem xét SHORT khi giá test lại
            - Ở **bottom**: Breakdown zone - Bears đang kiểm soát
            - **Zone chỉ biến mất khi**: Nến xanh đóng cửa **TRÊN** zone (buyers take control)
            - **Zone tồn tại khi**: Nến đỏ test lại nhưng close **DƯỚI** zone (sellers defend)
            
            **📏 Zone Height**:
            - **Tự động điều chỉnh** theo chiều cao thân nến
            - Zones lớn = Momentum mạnh (large candle body)
            - Zones nhỏ = Momentum yếu (small candle body)
            
            **⚙️ Settings Tips**:
            - **Delta Threshold 5-10%**: Nhiều zones, nhiều tín hiệu
            - **Delta Threshold 20-30%**: Ít zones, chỉ signals cực mạnh
            - **Max Zones 40-60**: Load nhanh, ít zones
            - **Max Zones 100-150**: Nhiều zones, có thể lag
            """)
        
        result = plot_candlestick_with_footprint(
            footprint_data,
            symbol=selected_coin,
            exchange=selected_exchange,
            delta_threshold=delta_threshold,
            debug=True,
            max_zones=max_zones
        )
        
        if result:
            # Unpack result (can be either figure only or (figure, debug_info))
            if isinstance(result, tuple):
                candlestick_chart, debug_info = result
                
                # Display debug info
                debug_cols = st.columns(5)
                with debug_cols[0]:
                    st.metric('Total Candles', debug_info['total_candles'])
                with debug_cols[1]:
                    st.metric('Analyzed', debug_info['checked_candles'])
                with debug_cols[2]:
                    st.metric('Potential Zones', debug_info['potential_zones'], 
                             delta=f">{delta_threshold*100:.0f}% delta")
                with debug_cols[3]:
                    st.metric('Tested Zones', debug_info['invalidated_zones'],
                             delta='Price tested', delta_color='inverse')
                with debug_cols[4]:
                    st.metric('✅ Total Zones', debug_info['valid_zones'],
                             delta='Shown on chart', delta_color='normal')
                
                if debug_info['valid_zones'] == 0:
                    st.warning(f"⚠️ **Không tìm thấy zone nào!** Thử giảm Delta Threshold xuống {max(0.05, delta_threshold-0.05):.2f} hoặc thấp hơn.")
            else:
                candlestick_chart = result
            
            st.plotly_chart(candlestick_chart, use_container_width=True, config={'displaylogo': False})
        else:
            st.info('Not enough data to generate candlestick chart')
    
    elif chart_type == 'Footprint Heatmap':
        st.markdown("### 🔥 Footprint Heatmap")
        st.caption("Color-coded delta at each price level - Green = Buy, Red = Sell")
        
        footprint_chart = plot_footprint_chart(
            footprint_data,
            symbol=selected_coin,
            exchange=selected_exchange,
            show_cumulative_delta=True
        )
        
        if footprint_chart:
            st.plotly_chart(footprint_chart, use_container_width=True, config={'displaylogo': False})
        else:
            st.info('Not enough data to generate footprint chart')
    
    elif chart_type == 'Volume Profile':
        st.markdown("### 📊 Volume Profile (Horizontal)")
        st.caption("Volume distribution by price - Green = Buy volume, Red = Sell volume")
        
        profile_chart = plot_volume_profile(footprint_data, symbol=selected_coin)
        
        if profile_chart:
            st.plotly_chart(profile_chart, use_container_width=True, config={'displaylogo': False})
        else:
            st.info('Not enough data to generate volume profile')
    
    # Interpretation Guide
    with st.expander("ℹ️ How to Read Footprint Charts", expanded=False):
        st.markdown("""
        **Chart Types:**
        
        ### 1. Candlestick + Zones (Recommended for Trading)
        - **OHLC Candles**: Standard price action
        - **🟢 Green Zones**: Horizontal lines tại giá có strong BUY pressure
        - **🔴 Red Zones**: Horizontal lines tại giá có strong SELL pressure
        - **Smart Invalidation**: Nếu giá quay lại zone → Zone biến mất (không còn valid)
        - **Volume Bars**: Dưới chart, green = buy delta, red = sell delta
        
        **Cách dùng:**
        - Zone càng đậm màu = Signal càng mạnh
        - Green zone = Potential support (buyers stepped in)
        - Red zone = Potential resistance (sellers stepped in)
        - Nếu giá break zone → Momentum mạnh
        - Nếu giá bounce tại zone → Reversal signal
        
        ### 2. Footprint Heatmap (Advanced Analysis)
        - **Heatmap**: Mỗi cell = delta tại 1 price level trong 1 candle
        - **Color Scale**: Dark green (strong buy) → White (neutral) → Dark red (strong sell)
        - **Cumulative Delta**: Chart dưới, running total of buy - sell
        - **Best For**: Nhìn chi tiết order flow, tìm divergence
        
        ### 3. Volume Profile (S/R Identification)
        - **Horizontal Bars**: Volume tại mỗi mức giá
        - **POC**: Thanh dài nhất = Point of Control (strongest S/R)
        - **High Volume Node**: Acceptance zone (nhiều giao dịch)
        - **Low Volume Node**: Rejection zone (ít giao dịch, giá di chuyển nhanh)
        
        ---
        
        **Trading Signals:**
        
        **Bullish Signals:**
        - ✅ Green zone at lows (buying the dip)
        - ✅ Price bounces at green zone (support holding)
        - ✅ Volume bars mostly green (sustained buying)
        - ✅ Cumulative delta rising
        
        **Bearish Signals:**
        - ❌ Red zone at highs (selling the rally)
        - ❌ Price rejects at red zone (resistance holding)
        - ❌ Volume bars mostly red (sustained selling)
        - ❌ Cumulative delta falling
        
        **Reversal Signals:**
        - 🔄 Green zone forms at strong support → Long setup
        - 🔄 Red zone forms at strong resistance → Short setup
        - 🔄 Price breaks zone with high volume → Trend continuation
        - 🔄 Zone disappears (price revisited) → Signal invalidated
        
        ---
        
        **Delta Threshold Explained:**
        - **0.1-0.2**: Show nhiều zones (sensitive, có thể nhiễu)
        - **0.3-0.4**: Balanced (recommended for most traders)
        - **0.5-0.7**: Chỉ zones rất mạnh (ít zones, tín hiệu rõ ràng)
        - **0.8-0.9**: Extremely selective (chỉ extreme signals)
        
        **Formula:**
        ```
        Delta Ratio = |Buy Volume - Sell Volume| / Total Volume
        
        Example:
        Buy: 100 BTC, Sell: 30 BTC
        Delta Ratio = |100 - 30| / 130 = 0.54 (54% imbalance)
        → Zone will show if threshold ≤ 0.54
        ```
        
        ---
        
        **Color Coding:**
        - 🟢 **Green zones**: More BUY volume (buyers aggressive)
        - 🔴 **Red zones**: More SELL volume (sellers aggressive)
        - ⚪ **White/Neutral**: Balanced buy/sell
        
        **2. Delta Analysis:**
        - **Positive Delta (+)**: Buy volume > Sell volume → Bullish pressure
        - **Negative Delta (-)**: Sell volume > Buy volume → Bearish pressure
        - **Cumulative Delta Rising**: Sustained buying → Trend continuation likely
        - **Cumulative Delta Falling**: Sustained selling → Downtrend
        
        **3. Volume Profile:**
        - **POC (Point of Control)**: Price level with highest volume → Strong S/R level
        - **High Volume Node**: Areas with lots of trading → Acceptance zone
        - **Low Volume Node**: Thin areas → Price moves through quickly
        
        **4. Trading Signals:**
        
        **Bullish Signals:**
        - ✅ Large green delta at lows (buying the dip)
        - ✅ Cumulative delta rising while price consolidates
        - ✅ High volume green candle breaking resistance
        - ✅ Absorption: Large buy volume, small price drop
        
        **Bearish Signals:**
        - ❌ Large red delta at highs (selling the rally)
        - ❌ Cumulative delta falling while price holds
        - ❌ High volume red candle breaking support
        - ❌ Absorption: Large sell volume, small price rise
        
        **5. Advanced Patterns:**
        
        **Absorption:**
        - Large volume BUT small price movement
        - Example: Price drops $100, but 1000 BTC bought → Strong support
        - → Reversal likely
        
        **Exhaustion:**
        - Delta turns opposite to price direction
        - Example: Price rising but delta negative (selling into rally)
        - → Trend weakness
        
        **Iceberg Orders:**
        - Repeated large volume at same price level
        - → Institutional accumulation/distribution
        
        **6. Best Practices:**
        - Use with price action for confirmation
        - Look for divergences (price vs delta)
        - Focus on high-volume price levels
        - Combine with support/resistance zones
        - Watch cumulative delta for trend strength
        
        **⚠️ Limitations:**
        - Works best on liquid markets (BTC, ETH)
        - Short timeframes (1m-15m) can be noisy
        - Doesn't predict price, only shows current flow
        - Wash trading can distort readings
        """)
    
    # Data table (optional)
    with st.expander("📋 Raw Data", expanded=False):
        if not raw_data_df.empty:
            st.dataframe(
                raw_data_df.tail(100),
                use_container_width=True,
                height=300
            )
        else:
            st.info('No raw data loaded')
            st.info('No trade data loaded')


if __name__ == '__main__':
    # Standalone test
    print("Testing Futures Footprint...")
    
    # Test Binance
    print("\n1. Fetching Binance trades...")
    df = fetch_binance_trades('BTCUSDT', limit=1000)
    
    if not df.empty:
        print(f"   ✓ Fetched {len(df)} trades")
        print(f"   Latest trade: {df.iloc[-1]['time']} | ${df.iloc[-1]['price']:,.2f} | {df.iloc[-1]['side']}")
        
        # Aggregate
        print("\n2. Aggregating footprint data (5min)...")
        footprint = aggregate_footprint_data(df, timeframe='5min', price_bins=50)
        print(f"   ✓ Created {len(footprint['candles'])} candles")
        
        # Metrics
        print("\n3. Calculating metrics...")
        metrics = calculate_footprint_metrics(footprint)
        print(f"   Total Volume: {metrics['total_volume']:.2f}")
        print(f"   Net Delta: {metrics['net_delta']:+.2f}")
        print(f"   Aggression Ratio: {metrics['aggression_ratio']:.2f}")
        print(f"   POC Price: ${metrics['poc_price']:,.2f}")
        
        print("\n✅ Footprint test successful!")
    else:
        print("   ✗ No data")
