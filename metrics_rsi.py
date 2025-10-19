"""RSI metrics module

Provides helpers to fetch RSI for a list of coins (CoinGecko or compute from OHLCV)
and produce a Plotly scatter heatmap (marketcap vs RSI) for Streamlit.
"""
from __future__ import annotations

import time
from typing import List, Dict, Any, Optional
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

def fetch_rsi_for_symbol(symbol: str, timeframe: str = "1d", ohlcv_limit: int = 200) -> Optional[float]:
    """Attempt to compute RSI for a single symbol.
    timeframe: '4h', '1d', '7d' etc. We map these to bar sizes for OHLCV fetcher.
    Returns RSI value (0-100) or None on failure.
    """
    # Map timeframe to OKX bars
    bar_map = {
        '4h': '4h',
        '1d': '1D',
        '7d': '1D',
        '1w': '1D'
    }
    bar = bar_map.get(timeframe, '1D')
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
                        break
                except Exception:
                    continue
        if inst:
            try:
                df = _m.fetch_okx_ohlcv_oi(symbol=inst, bar=bar, limit=ohlcv_limit)
                if df is not None and not df.empty:
                    return compute_rsi_from_series(df['close'])
            except Exception:
                pass
    except Exception:
        # OKX module missing or failed — proceed to next source
        pass

    # Binance fallback
    try:
        bin_sym = map_symbol_to_binance(symbol)
        if bin_sym:
            dfb = fetch_binance_ohlcv(bin_sym, interval=map_tf_to_binance_interval(timeframe), limit=ohlcv_limit)
            if dfb is not None and not dfb.empty:
                return compute_rsi_from_series(dfb['close'])
    except Exception:
        pass

    # CoinGecko fallback: approximate RSI from price series
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
        series = dfp['price']
        return compute_rsi_from_series(series)
    except Exception:
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
    return {'4h': '4h', '1d': '1d', '7d': '1d'}.get(tf, '1d')


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


def get_rsi_for_universe(symbols: List[str], timeframe: str = '1d', ttl_seconds: int = 3600, force_refresh: bool = False) -> Dict[str, Optional[float]]:
    """Return RSI map for requested symbols using persistent cache + incremental fetch.
    Only symbols missing or expired (older than ttl_seconds) are fetched from APIs.
    """
    cache = load_rsi_cache()
    out: Dict[str, Optional[float]] = {}
    to_fetch: List[str] = []
    now = time.time()
    for s in symbols:
        entry = cache.get(s.upper())
        if not force_refresh and entry and is_fresh(entry, ttl_seconds=ttl_seconds):
            out[s] = entry.get('rsi')
        else:
            out[s] = None
            to_fetch.append(s)

    # Fetch missing/expired sequentially to respect rate limits
    if to_fetch:
        for s in to_fetch:
            try:
                val = fetch_rsi_for_symbol(s, timeframe=timeframe)
                out[s] = val
                cache[s.upper()] = {'rsi': val, 'ts': now}
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


def build_rsi_scatter(df_meta: pd.DataFrame, rsi_map: Dict[str, Optional[float]], title: str = 'Crypto RSI Heatmap'):
    """Build Plotly figure: x = marketcap (log scale), y = RSI value, color zones, bubble sizes by marketcap.
    df_meta must have columns: symbol, market_cap_usd
    rsi_map: dict symbol->rsi
    Returns plotly.graph_objects.Figure
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
    colors = []
    for v in df['rsi']:
        if v >= 70:
            colors.append('rgba(255,80,80,0.9)')
        elif v <= 30:
            colors.append('rgba(80,200,120,0.9)')
        else:
            colors.append('rgba(170,170,170,0.9)')
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['mc_log'],
        y=df['rsi'],
        mode='markers+text',
        text=df['symbol'],
        textposition='top center',
        marker=dict(size=df['size'], color=colors, line=dict(width=0.5, color='#222')),
        hovertemplate='%{text}<br>RSI: %{y:.2f}<br>MarketCap: %{customdata[0]:,}' ,
        customdata=df[['market_cap_usd']].values
    ))
    # Add horizontal bands for >70 and <30
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(255,200,200,0.2)', line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor='rgba(200,255,220,0.2)', line_width=0)
    fig.update_yaxes(title_text='Relative Strength Index (RSI)', range=[0,100])
    fig.update_xaxes(title_text='Market Cap (log10 USD)', zeroline=False)
    fig.update_layout(title=title, height=520)
    return fig


# Utility to build symbol list by marketcap using coin list in config
def get_universe_from_config(option: str = 'top30') -> List[str]:
    try:
        from config import COIN_LIST
        # COIN_LIST entries: (coingecko_id, symbol)
        ids = [c[0] for c in COIN_LIST]
        syms = [c[1] for c in COIN_LIST]
        df = pd.DataFrame({'id': ids, 'symbol': syms})
        # try to get marketcap via coingecko markets endpoint
        url = 'https://api.coingecko.com/api/v3/coins/markets'
        params = {'vs_currency':'usd','order':'market_cap_desc','per_page':250,'page':1}
        r = requests.get(url, params=params, timeout=20).json()
        dfm = pd.DataFrame(r)
        # map by symbol
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
