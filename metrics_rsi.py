"""RSI metrics module

Provides helpers to fetch RSI for a list of coins (CoinGecko or compute from OHLCV)
and produce a Plotly scatter heatmap (marketcap vs RSI) for Streamlit.
"""
from __future__ import annotations

import time
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests
import pandas as pd
import numpy as np
import math

# Helper: compute RSI from close series
def compute_rsi_from_series(series: pd.Series, period: int = 14) -> Optional[float]:
    try:
        delta = series.diff().dropna()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ma_up = up.ewm(alpha=1/period, adjust=False).mean()
        ma_down = down.ewm(alpha=1/period, adjust=False).mean()
        rs = ma_up / ma_down
        rsi = 100 - (100 / (1 + rs))
        # return last value
        return float(rsi.iloc[-1])
    except Exception:
        return None

# CoinGecko doesn't provide RSI directly; we'll attempt to compute using OHLCV fetchers
# Try: use existing module metrics_ohlcv_okx if available (cached fetchers inside app)

def fetch_rsi_for_symbol(symbol: str, timeframe: str = "1d", ohlcv_limit: int = 200, return_history: bool = False) -> Optional[float | List[Dict[str, Any]]]:
    """Attempt to compute RSI for a single symbol.
    timeframe: '4h', '1d', '7d' etc. We map these to bar sizes for OHLCV fetcher.
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH')
        timeframe: Timeframe for RSI calculation
        ohlcv_limit: Number of OHLCV bars to fetch
        return_history: If True, returns list of RSI values over time (for trail lines)
    
    Returns:
        - If return_history=False: RSI value (0-100) or None on failure
        - If return_history=True: List of dicts [{'timestamp': ts, 'rsi': val}, ...] or None
    """
    # Map timeframe to OKX bars
    bar_map = {
        '15m': '15m',
        '1h': '1H',
        '4h': '4h',
        '1d': '1D',
        '7d': '1D',
        '1w': '1D'
    }
    bar = bar_map.get(timeframe, '1D')
    
    df_result = None
    
    # Try OKX first (existing project helper)
    try:
        import metrics_ohlcv_okx as _m
        # map passed symbol to an OKX instId if necessary
        inst = None
        try:
            # If caller passed an OKX-style instId already, try directly
            inst = symbol if isinstance(symbol, str) and ('-' in symbol or 'SWAP' in symbol.upper()) else None
        except Exception:
            inst = None
        if inst is None:
            # naive mapping: try SYMBOL-USDT and SYMBOL-USDT-SWAP
            for cand in (f"{symbol.upper()}-USDT", f"{symbol.upper()}-USDT-SWAP"):
                try:
                    df = _m.fetch_okx_ohlcv_oi(symbol=cand, bar=bar, limit=ohlcv_limit)
                    if df is not None and not df.empty:
                        inst = cand
                        df_result = df
                        break
                except Exception:
                    continue
        if inst and df_result is None:
            try:
                df_result = _m.fetch_okx_ohlcv_oi(symbol=inst, bar=bar, limit=ohlcv_limit)
            except Exception:
                pass
    except Exception:
        # OKX module missing or failed — proceed to next source
        pass

    # Binance fallback
    if df_result is None:
        try:
            bin_sym = map_symbol_to_binance(symbol)
            if bin_sym:
                df_result = fetch_binance_ohlcv(bin_sym, interval=map_tf_to_binance_interval(timeframe), limit=ohlcv_limit)
        except Exception:
            pass

    # CoinGecko fallback: approximate RSI from price series
    if df_result is None:
        try:
            cg_id = symbol.lower()
            days = 7 if timeframe in ('7d', '1w') else (1 if timeframe == '1d' else 2)
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
            params = {"vs_currency": "usd", "days": days}
            r = requests.get(url, params=params, timeout=12)
            if r.status_code != 200:
                return None
            j = r.json()
            prices = j.get('prices') or []
            if not prices:
                return None
            dfp = pd.DataFrame(prices, columns=['ts', 'price'])
            dfp['price'] = pd.to_numeric(dfp['price'], errors='coerce')
            dfp['timestamp'] = pd.to_datetime(dfp['ts'], unit='ms', utc=True)
            df_result = dfp[['timestamp', 'price']].rename(columns={'price': 'close'})
        except Exception:
            return None
    
    # Calculate RSI history if requested
    if df_result is not None and not df_result.empty:
        try:
            if return_history:
                # Calculate rolling RSI for trail visualization
                close_series = df_result['close']
                period = 14
                delta = close_series.diff()
                up = delta.clip(lower=0)
                down = -1 * delta.clip(upper=0)
                ma_up = up.ewm(alpha=1/period, adjust=False).mean()
                ma_down = down.ewm(alpha=1/period, adjust=False).mean()
                rs = ma_up / ma_down
                rsi_series = 100 - (100 / (1 + rs))
                
                # Get timestamps (handle both datetime column names)
                if 'timestamp' in df_result.columns:
                    timestamps = df_result['timestamp']
                elif 'datetime' in df_result.columns:
                    timestamps = df_result['datetime']
                else:
                    # Fallback: create synthetic timestamps
                    timestamps = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=len(rsi_series), freq='4h')
                
                # Build history list (last N points for trail)
                history = []
                trail_length = min(10, len(rsi_series))  # Last 10 points for trail
                for i in range(-trail_length, 0):
                    if i >= -len(rsi_series) and not pd.isna(rsi_series.iloc[i]):
                        history.append({
                            'timestamp': timestamps.iloc[i],
                            'rsi': float(rsi_series.iloc[i])
                        })
                return history if history else None
            else:
                # Return only current RSI value
                return compute_rsi_from_series(df_result['close'])
        except Exception:
            return None
    
    return None


def fetch_binance_ohlcv(symbol='BTCUSDT', interval='4h', limit=500):
    """Fetch OHLCV from Binance public API and return DataFrame with datetime & close."""
    try:
        url = 'https://api.binance.com/api/v3/klines'
        params = {'symbol': symbol.upper(), 'interval': interval, 'limit': int(limit)}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        df = pd.DataFrame(data, columns=[
            'open_time','open','high','low','close','volume','close_time',
            'quote_asset_volume','num_trades','taker_base_vol','taker_quote_vol','ignore'
        ])
        df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        return df.sort_values('datetime')
    except Exception:
        return None


def map_symbol_to_binance(sym: str) -> Optional[str]:
    """Naive mapping: try <SYM>USDT, <SYM>BUSD etc. Returns first candidate that exists (no exchangeInfo ping for speed)."""
    if not sym:
        return None
    s = sym.upper()
    # quick heuristics: try USDT, then BUSD
    for suf in ('USDT','BUSD'):
        cand = f"{s}{suf}"
        # don't validate symbol here to avoid extra API calls; caller will fail and move on
        return cand
    return None


def map_tf_to_binance_interval(tf: str) -> str:
    return {
        '15m': '15m',
        '1h': '1h',
        '4h': '4h',
        '1d': '1d',
        '7d': '1d'
    }.get(tf, '1d')


def fetch_bulk_rsi(symbols: List[str], timeframe: str = '1d') -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for s in symbols:
        try:
            out[s] = fetch_rsi_for_symbol(s, timeframe=timeframe)
            # be polite to external APIs
            time.sleep(0.5)
        except Exception:
            out[s] = None
    return out


# ------------------ Persistent cache helpers ------------------
import json
from pathlib import Path

RSI_CACHE_PATH = Path("rsi_cache.json")

def load_rsi_cache() -> Dict[str, Dict[str, Any]]:
    try:
        if RSI_CACHE_PATH.exists():
            return json.loads(RSI_CACHE_PATH.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

def save_rsi_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    try:
        RSI_CACHE_PATH.write_text(json.dumps(cache), encoding='utf-8')
    except Exception:
        pass

def is_fresh(entry: Dict[str, Any], ttl_seconds: int = 3600) -> bool:
    try:
        ts = float(entry.get('ts', 0))
        return (time.time() - ts) < float(ttl_seconds)
    except Exception:
        return False


def get_rsi_for_universe(symbols: List[str], timeframe: str = '1d', ttl_seconds: int = 3600, force_refresh: bool = False, with_history: bool = False) -> Dict[str, Optional[float | List[Dict]]]:
    """Return RSI map for requested symbols using persistent cache + incremental fetch.
    Only symbols missing or expired (older than ttl_seconds) are fetched from APIs.
    
    Args:
        symbols: List of coin symbols
        timeframe: RSI timeframe ('4h', '1d', '7d')
        ttl_seconds: Cache TTL in seconds
        force_refresh: Force refresh all data
        with_history: If True, fetch RSI history for trail lines
    
    Returns:
        Dict mapping symbol -> RSI value (or RSI history list if with_history=True)
    """
    cache = load_rsi_cache()
    out: Dict[str, Optional[float | List[Dict]]] = {}
    to_fetch: List[str] = []
    now = time.time()
    
    # Check cache
    for s in symbols:
        cache_key = f"{s.upper()}_{timeframe}_{'history' if with_history else 'current'}"
        entry = cache.get(cache_key)
        if not force_refresh and entry and is_fresh(entry, ttl_seconds=ttl_seconds):
            out[s] = entry.get('rsi') if not with_history else entry.get('history')
        else:
            out[s] = None
            to_fetch.append(s)

    # Fetch missing/expired sequentially to respect rate limits
    if to_fetch:
        for s in to_fetch:
            try:
                val = fetch_rsi_for_symbol(s, timeframe=timeframe, return_history=with_history)
                out[s] = val
                cache_key = f"{s.upper()}_{timeframe}_{'history' if with_history else 'current'}"
                cache[cache_key] = {
                    'rsi' if not with_history else 'history': val, 
                    'ts': now
                }
                # small delay between calls
                time.sleep(0.4)
            except Exception:
                out[s] = None

        # persist updated cache
        try:
            save_rsi_cache(cache)
        except Exception:
            pass

    return out


def rsi_cache_info() -> Dict[str, Any]:
    cache = load_rsi_cache()
    if not cache:
        return {'count': 0, 'last_updated': None}
    ts_vals = [v.get('ts', 0) for v in cache.values() if isinstance(v, dict) and v.get('ts')]
    last = max(ts_vals) if ts_vals else None
    return {'count': len(cache), 'last_updated': last}


def build_rsi_scatter(df_meta: pd.DataFrame, rsi_map: Dict[str, Optional[float]], title: str = 'Crypto RSI Heatmap', rsi_history_map: Dict[str, List[Dict]] = None):
    """Build Plotly figure: x = marketcap (log scale), y = RSI value, color zones, bubble sizes by marketcap.
    
    Args:
        df_meta: DataFrame with columns: symbol, market_cap_usd
        rsi_map: Dict mapping symbol -> current RSI value
        title: Chart title
        rsi_history_map: Dict mapping symbol -> RSI history (for trail lines)
    
    Returns:
        plotly.graph_objects.Figure with trail lines showing RSI movement over time
    """
    import plotly.graph_objects as go
    df = df_meta.copy()
    df['rsi'] = df['symbol'].map(lambda s: rsi_map.get(s))
    df = df.dropna(subset=['rsi'])
    if df.empty:
        return None
    
    # log marketcap for x
    df['mc_log'] = df['market_cap_usd'].apply(lambda v: math.log10(float(v)) if v and v>0 else 0)
    
    # sizes
    mc_min, mc_max = df['market_cap_usd'].min(), df['market_cap_usd'].max()
    def size_from_mc(v):
        try:
            return 8 + 40 * ((v - mc_min) / (mc_max - mc_min + 1e-9))
        except Exception:
            return 8
    df['size'] = df['market_cap_usd'].apply(size_from_mc)
    
    # Color function
    def get_rsi_color(v, alpha=0.9):
        if v >= 70:
            return f'rgba(220,38,38,{alpha})'  # Deep Red - Overbought
        elif v >= 60:
            return f'rgba(239,68,68,{alpha})'  # Red - Strong
        elif v >= 50:
            return f'rgba(156,163,175,{alpha})'  # Gray - Neutral
        elif v >= 40:
            return f'rgba(134,239,172,{alpha})'  # Light Green - Neutral
        elif v >= 30:
            return f'rgba(34,197,94,{alpha})'  # Green - Weak
        else:
            return f'rgba(22,163,74,{alpha})'  # Deep Green - Oversold
    
    colors = [get_rsi_color(v) for v in df['rsi']]
    
    fig = go.Figure()
    
    # Add trail lines if history available
    if rsi_history_map:
        for idx, row in df.iterrows():
            sym = row['symbol']
            history = rsi_history_map.get(sym, [])
            if history and len(history) >= 2:
                # Extract historical RSI values
                hist_rsi = [h['rsi'] for h in history]
                hist_x = [row['mc_log']] * len(hist_rsi)  # Same marketcap (x position)
                
                # Draw trail line (dashed)
                fig.add_trace(go.Scatter(
                    x=hist_x,
                    y=hist_rsi,
                    mode='lines+markers',
                    line=dict(
                        color=get_rsi_color(row['rsi'], alpha=0.4),
                        width=1.5,
                        dash='dot'
                    ),
                    marker=dict(
                        size=4,
                        color=get_rsi_color(row['rsi'], alpha=0.3),
                        line=dict(width=0)
                    ),
                    showlegend=False,
                    hoverinfo='skip',
                    name=f'{sym}_trail'
                ))
    
    # Add main scatter (current RSI positions)
    fig.add_trace(go.Scatter(
        x=df['mc_log'],
        y=df['rsi'],
        mode='markers+text',
        text=df['symbol'],
        textposition='top center',
        textfont=dict(size=10, color='white'),
        marker=dict(
            size=df['size'], 
            color=colors, 
            line=dict(width=1.5, color='white'),
            opacity=1.0
        ),
        hovertemplate='<b>%{text}</b><br>RSI: %{y:.2f}<br>MarketCap: $%{customdata[0]:,}<extra></extra>',
        customdata=df[['market_cap_usd']].values,
        name='Current RSI'
    ))
    
    # Add horizontal bands for >70 and <30
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(220,38,38,0.15)', line_width=0, annotation_text="OVERBOUGHT", annotation_position="top right")
    fig.add_hrect(y0=0, y1=30, fillcolor='rgba(22,163,74,0.15)', line_width=0, annotation_text="OVERSOLD", annotation_position="bottom right")
    
    # Add reference lines at 30, 50, 70
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(220,38,38,0.5)", line_width=1)
    fig.add_hline(y=50, line_dash="dash", line_color="rgba(156,163,175,0.5)", line_width=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(22,163,74,0.5)", line_width=1)
    
    fig.update_yaxes(title_text='RSI (Relative Strength Index)', range=[0, 100])
    fig.update_xaxes(title_text='Market Cap (log10 USD)', zeroline=False)
    fig.update_layout(
        title=title, 
        height=600,
        plot_bgcolor='#0f172a',
        paper_bgcolor='#0f172a',
        font=dict(color='white'),
        hovermode='closest'
    )
    return fig


# Utility to build symbol list by marketcap using coin list in config
def get_universe_from_config(option: str = 'top30') -> List[str]:
    """
    Get list of coins by market cap.
    
    Primary source: CoinGecko
    Fallback source: CryptoCompare (if CoinGecko fails/rate limited)
    
    Args:
        option: 'top30', 'top50', 'portfolio', or 'all'
    
    Returns:
        List of dicts with 'symbol' and 'market_cap_usd' keys
    """
    try:
        from config import COIN_LIST
        # COIN_LIST entries: (coingecko_id, symbol)
        ids = [c[0] for c in COIN_LIST]
        syms = [c[1] for c in COIN_LIST]
        df = pd.DataFrame({'id': ids, 'symbol': syms})
        
        # Try CoinGecko first
        dfm = None
        try:
            url = 'https://api.coingecko.com/api/v3/coins/markets'
            params = {'vs_currency':'usd','order':'market_cap_desc','per_page':250,'page':1}
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            r_json = r.json()
            
            # Check if response is valid
            if isinstance(r_json, list) and len(r_json) > 0:
                dfm = pd.DataFrame(r_json)
                print("[RSI Universe] OK Fetched from CoinGecko")
            else:
                print(f"[RSI Universe] CoinGecko returned unexpected format: {type(r_json)}")
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("[RSI Universe] CoinGecko rate limited (429), trying CryptoCompare fallback...")
            else:
                print(f"[RSI Universe] CoinGecko HTTP error: {e}")
        except Exception as e:
            print(f"[RSI Universe] CoinGecko failed: {e}")
        
        # Fallback to CryptoCompare if CoinGecko failed
        if dfm is None or dfm.empty:
            try:
                print("[RSI Universe] Fetching from CryptoCompare fallback...")
                
                # CryptoCompare doesn't have a good "top by market cap" endpoint
                # Use top by volume instead (includes BTC, ETH, etc.)
                toplist_url = "https://min-api.cryptocompare.com/data/top/totalvolfull"
                toplist_params = {'limit': 100, 'tsym': 'USD'}
                
                r_cc = requests.get(toplist_url, params=toplist_params, timeout=15)
                r_cc.raise_for_status()
                cc_data = r_cc.json()
                
                if cc_data.get('Message') == 'Success' and cc_data.get('Data'):
                    coins_cc = cc_data['Data']
                    records_cc = []
                    
                    for coin in coins_cc:
                        symbol = coin['CoinInfo']['Name']
                        # Get market cap from RAW.USD.MKTCAP
                        market_cap = coin.get('RAW', {}).get('USD', {}).get('MKTCAP', 0)
                        # Skip coins without market cap data
                        if market_cap > 0:
                            records_cc.append({
                                'symbol': symbol,
                                'market_cap': market_cap
                            })
                    
                    dfm = pd.DataFrame(records_cc)
                    # Sort by market cap descending
                    dfm = dfm.sort_values('market_cap', ascending=False).reset_index(drop=True)
                    print(f"[RSI Universe] OK Fetched {len(dfm)} coins from CryptoCompare (by volume, sorted by mktcap)")
                else:
                    print(f"[RSI Universe] CryptoCompare error: {cc_data.get('Message', 'Unknown')}")
                    
            except Exception as e_cc:
                print(f"[RSI Universe] CryptoCompare fallback failed: {e_cc}")
        
        # If both sources failed, return empty
        if dfm is None or dfm.empty:
            print("[RSI Universe] WARNING Both CoinGecko and CryptoCompare failed")
            return []
        
        # Process the dataframe (works for both CoinGecko and CryptoCompare)
        dfm['symbol'] = dfm['symbol'].str.upper()
        dfm = dfm[~dfm['symbol'].str.contains('USD|USDT|USDC|DAI|BUSD', na=False, case=False)]
        if option == 'top30':
            dfm = dfm.head(30)
        elif option == 'top50':
            dfm = dfm.head(50)
        elif option == 'portfolio':
            # read portfolio coins from portfolio data
            try:
                from app_init import get_portfolio_data
                holdings, _ = get_portfolio_data()
                coins = list(holdings.keys())
                # If app not initialized (empty cache), try loading local DATA_FILE directly
                if not coins:
                    try:
                        from config import DATA_FILE
                        import json
                        if Path(DATA_FILE).exists():
                            with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                                data = json.load(fh)
                                if isinstance(data, dict):
                                    coins = list(data.keys())
                    except Exception:
                        # last resort try data.json
                        try:
                            import json
                            if Path('data.json').exists():
                                with open('data.json', 'r', encoding='utf-8') as fh:
                                    data = json.load(fh)
                                    if isinstance(data, dict):
                                        coins = list(data.keys())
                        except Exception:
                            coins = []
                # holdings keys may be coingecko ids (e.g., 'ethereum') or symbols (e.g., 'ETH')
                # Build mapping from coin id -> symbol using COIN_LIST
                id_to_symbol = {coin_id: sym.upper() for coin_id, sym in COIN_LIST}
                # Normalize incoming keys: if key matches a coin_id, map to its symbol; otherwise treat as symbol
                normalized_syms = []
                for c in coins:
                    if not isinstance(c, str):
                        continue
                    if c in id_to_symbol:
                        normalized_syms.append(id_to_symbol[c])
                    else:
                        normalized_syms.append(c.upper())
                # Filter market list by normalized symbols
                dfm = dfm[dfm['symbol'].isin(normalized_syms)]
                # If no matches (e.g., CoinGecko request failed or holdings not present in markets),
                # build universe from holdings using COIN_LIST mapping so portfolio coins are returned.
                if dfm.empty:
                    records = []
                    # reverse mapping coin_id -> symbol already in id_to_symbol
                    for c in coins:
                        if c in id_to_symbol:
                            records.append({'symbol': id_to_symbol[c], 'market_cap_usd': 0})
                        else:
                            records.append({'symbol': str(c).upper(), 'market_cap_usd': 0})
                    # convert to DataFrame-like record list for downstream code
                    return records
            except Exception:
                dfm = dfm.head(30)
        else:
            dfm = dfm
        return dfm[['symbol','market_cap']].rename(columns={'market_cap':'market_cap_usd'}).to_dict(orient='records')
    except Exception:
        return []
