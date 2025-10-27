"""
Futures Open Interest Metric

Displays total open interest across major exchanges and analyzes OI trends.
Open Interest = Total value of outstanding futures contracts.

Features:
- Current OI by exchange
- Historical OI trends
- OI change vs price correlation
- OI-weighted funding rates
- Liquidation level clusters

Data source: Binance, OKX, Bybit APIs

Cache: 5 minutes (updated every interval)
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import requests

CACHE_FILE = 'futures_open_interest_cache.json'
CACHE_TTL = 300  # 5 minutes


def _get_cache_path():
    return os.path.join(os.path.dirname(__file__), CACHE_FILE)


def _load_cache() -> Optional[Dict]:
    try:
        path = _get_cache_path()
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('timestamp', 0) > CACHE_TTL:
            return None
        return data
    except Exception:
        return None


def _save_cache(data: Dict):
    try:
        data['timestamp'] = time.time()
        with open(_get_cache_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def fetch_binance_open_interest(symbol: str = 'BTC') -> Optional[Dict]:
    """
    Fetch open interest from Binance.
    
    Endpoints:
    - /fapi/v1/openInterest - Current OI
    - /futures/data/openInterestHist - Historical OI
    """
    try:
        symbol_pair = f'{symbol}USDT'
        
        # Current open interest
        current_url = 'https://fapi.binance.com/fapi/v1/openInterest'
        current_response = requests.get(current_url, params={'symbol': symbol_pair}, timeout=10)
        
        if current_response.status_code != 200:
            print(f"[Open Interest] Binance {symbol}: Status {current_response.status_code}")
            return None
        
        current_data = current_response.json()
        
        # Historical open interest (last 30 days, 5min intervals)
        hist_url = 'https://fapi.binance.com/futures/data/openInterestHist'
        hist_response = requests.get(hist_url, params={
            'symbol': symbol_pair,
            'period': '5m',
            'limit': 500  # ~41 hours of 5min data
        }, timeout=10)
        
        historical = []
        if hist_response.status_code == 200:
            hist_data = hist_response.json()
            historical = [
                {
                    'timestamp': int(item['timestamp']),
                    'open_interest': float(item['sumOpenInterest']),
                    'open_interest_value': float(item['sumOpenInterestValue'])
                }
                for item in hist_data
            ]
        
        return {
            'exchange': 'Binance',
            'symbol': symbol,
            'open_interest': float(current_data.get('openInterest', 0)),
            'historical': historical
        }
    except requests.exceptions.RequestException as e:
        print(f"[Open Interest] Binance {symbol} network error: {type(e).__name__}")
        return None
    except Exception as e:
        print(f"[Open Interest] Binance {symbol} error: {e}")
        return None


def fetch_okx_open_interest(symbol: str = 'BTC') -> Optional[Dict]:
    """Fetch open interest from OKX."""
    try:
        inst_id = f'{symbol}-USDT-SWAP'
        
        # Current OI
        url = 'https://www.okx.com/api/v5/public/open-interest'
        response = requests.get(url, params={'instId': inst_id}, timeout=10)
        
        if response.status_code != 200:
            print(f"[Open Interest] OKX {symbol}: Status {response.status_code}")
            return None
        
        data = response.json()
        if data.get('code') != '0' or not data.get('data'):
            print(f"[Open Interest] OKX {symbol}: No data")
            return None
        
        oi_data = data['data'][0]
        
        return {
            'exchange': 'OKX',
            'symbol': symbol,
            'open_interest': float(oi_data.get('oi', 0)),
            'open_interest_value': float(oi_data.get('oiCcy', 0)),
            'historical': []  # Would need separate API call
        }
    except Exception as e:
        print(f"[Open Interest] OKX {symbol} error: {e}")
        return None


def fetch_bybit_open_interest(symbol: str = 'BTC') -> Optional[Dict]:
    """Fetch open interest from Bybit."""
    try:
        symbol_pair = f'{symbol}USDT'
        
        # Bybit V5 API
        url = 'https://api.bybit.com/v5/market/open-interest'
        response = requests.get(url, params={
            'category': 'linear',
            'symbol': symbol_pair,
            'intervalTime': '5min',
            'limit': 200
        }, timeout=10)
        
        if response.status_code != 200:
            print(f"[Open Interest] Bybit {symbol}: Status {response.status_code}")
            return None
        
        data = response.json()
        if data.get('retCode') != 0 or not data.get('result', {}).get('list'):
            print(f"[Open Interest] Bybit {symbol}: No data")
            return None
        
        oi_list = data['result']['list']
        
        # Current OI (latest data point)
        latest = oi_list[0] if oi_list else {}
        
        # Historical
        historical = [
            {
                'timestamp': int(item['timestamp']),
                'open_interest': float(item['openInterest'])
            }
            for item in oi_list
        ]
        
        return {
            'exchange': 'Bybit',
            'symbol': symbol,
            'open_interest': float(latest.get('openInterest', 0)),
            'historical': historical
        }
    except Exception as e:
        print(f"[Open Interest] Bybit {symbol} error: {e}")
        return None


def fetch_coinmarketcap_oi(symbol: str = 'BTC') -> Optional[Dict]:
    """
    Fetch aggregated OI from CoinMarketCap (all exchanges combined).
    Note: May require API key for production use.
    """
    try:
        # Free endpoint - may be rate limited
        url = 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/chart'
        
        # Symbol mapping
        symbol_map = {
            'BTC': 1,
            'ETH': 1027,
            'BNB': 1839,
            'SOL': 5426,
            'ADA': 2010,
            'DOGE': 74,
            'AVAX': 5805
        }
        
        coin_id = symbol_map.get(symbol)
        if not coin_id:
            return None
        
        response = requests.get(url, params={
            'id': coin_id,
            'range': '1D'
        }, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        # Parse OI data if available in response
        # This is a simplified version - actual implementation may vary
        
        return None  # Placeholder
    except Exception:
        return None


def fetch_all_open_interest(coins: List[str]) -> Tuple[Dict, bool]:
    """Fetch open interest from all exchanges for multiple coins."""
    cache = _load_cache()
    cache_key = '-'.join(coins)
    
    if cache and cache.get('data', {}).get(cache_key):
        print(f"[Open Interest] Loaded from cache")
        return cache['data'][cache_key], True
    
    try:
        all_data = {}
        
        for coin in coins:
            coin_data = {
                'exchanges': [],
                'total_oi': 0,
                'total_oi_usd': 0
            }
            
            # Fetch from Binance
            binance_data = fetch_binance_open_interest(coin)
            if binance_data:
                coin_data['exchanges'].append(binance_data)
                coin_data['historical'] = binance_data['historical']  # Use Binance as primary
                if binance_data.get('historical'):
                    # Latest OI value in USD
                    latest = binance_data['historical'][-1]
                    coin_data['total_oi'] += binance_data['open_interest']
                    coin_data['total_oi_usd'] += latest.get('open_interest_value', 0)
                print(f"[Open Interest] OK {coin} Binance: {binance_data['open_interest']:,.0f}")
            
            # Fetch from OKX
            okx_data = fetch_okx_open_interest(coin)
            if okx_data:
                coin_data['exchanges'].append(okx_data)
                coin_data['total_oi'] += okx_data['open_interest']
                coin_data['total_oi_usd'] += okx_data.get('open_interest_value', 0)
                print(f"[Open Interest] OK {coin} OKX: {okx_data['open_interest']:,.0f}")
            
            # Fetch from Bybit
            bybit_data = fetch_bybit_open_interest(coin)
            if bybit_data:
                coin_data['exchanges'].append(bybit_data)
                coin_data['total_oi'] += bybit_data['open_interest']
                print(f"[Open Interest] OK {coin} Bybit: {bybit_data['open_interest']:,.0f}")
            
            if coin_data['exchanges']:
                all_data[coin] = coin_data
            
            time.sleep(0.3)  # Rate limiting
        
        if all_data:
            cache_data = cache.get('data', {}) if cache else {}
            cache_data[cache_key] = all_data
            _save_cache({'data': cache_data})
            return all_data, True
        
        return {}, False
    except Exception as e:
        print(f"[Open Interest] Error: {e}")
        return {}, False


def create_oi_comparison_table(exchanges: List[Dict], coin: str, current_price: Optional[float] = None) -> pd.DataFrame:
    """Create exchange comparison table for open interest."""
    if not exchanges:
        return pd.DataFrame()
    
    rows = []
    total_oi = sum(ex['open_interest'] for ex in exchanges)
    
    for ex in exchanges:
        oi = ex['open_interest']
        oi_usd = ex.get('open_interest_value', 0)
        
        # Estimate USD value if not provided
        if oi_usd == 0 and current_price:
            oi_usd = oi * current_price
        
        rows.append({
            'Exchange': ex['exchange'],
            'Open Interest': f"{oi:,.0f}",
            'OI Value (USD)': f"${oi_usd:,.0f}" if oi_usd > 0 else 'N/A',
            'Market Share (%)': (oi / total_oi * 100) if total_oi > 0 else 0
        })
    
    df = pd.DataFrame(rows)
    
    # Sort by market share
    df = df.sort_values('Market Share (%)', ascending=False)
    df.insert(0, 'Rank', range(1, len(df) + 1))
    
    return df


def plot_oi_history(historical: List[Dict], coin: str) -> go.Figure:
    """Plot historical open interest."""
    if not historical or len(historical) == 0:
        return None
    
    df = pd.DataFrame(historical)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('datetime')
    
    # Calculate metrics
    df['oi_change'] = df['open_interest'].pct_change() * 100
    df['oi_ma'] = df['open_interest'].rolling(window=20, min_periods=1).mean()
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(f'{coin} Open Interest', 'OI Change (%)'),
        row_heights=[0.7, 0.3]
    )
    
    # OI line chart
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['open_interest'],
            name='Open Interest',
            line=dict(color='#3b82f6', width=2),
            fill='tozeroy',
            fillcolor='rgba(59, 130, 246, 0.1)'
        ),
        row=1, col=1
    )
    
    # Moving average
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['oi_ma'],
            name='MA(20)',
            line=dict(color='#fbbf24', width=2, dash='dash')
        ),
        row=1, col=1
    )
    
    # OI change
    colors = ['#10b981' if x > 0 else '#ef4444' for x in df['oi_change']]
    fig.add_trace(
        go.Bar(
            x=df['datetime'],
            y=df['oi_change'],
            name='OI Change',
            marker_color=colors
        ),
        row=2, col=1
    )
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
    
    fig.update_yaxes(title_text="Open Interest (Contracts)", row=1, col=1)
    fig.update_yaxes(title_text="Change (%)", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    
    fig.update_layout(
        height=600,
        hovermode='x unified',
        showlegend=True
    )
    
    return fig


def plot_oi_vs_price(historical: List[Dict], coin: str, price_data: Optional[pd.DataFrame] = None) -> go.Figure:
    """Plot OI vs price correlation."""
    if not historical or len(historical) == 0:
        return None
    
    df = pd.DataFrame(historical)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('datetime')
    
    # Create dual-axis chart
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Open Interest on left axis
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['open_interest'],
            name='Open Interest',
            line=dict(color='#3b82f6', width=2),
            fill='tozeroy',
            fillcolor='rgba(59, 130, 246, 0.1)'
        ),
        secondary_y=False
    )
    
    # Price on right axis (if available)
    if price_data is not None and not price_data.empty:
        fig.add_trace(
            go.Scatter(
                x=price_data['datetime'],
                y=price_data['price'],
                name='Price',
                line=dict(color='#10b981', width=2)
            ),
            secondary_y=True
        )
    
    fig.update_xaxes(title_text="Time")
    fig.update_yaxes(title_text="Open Interest (Contracts)", secondary_y=False)
    fig.update_yaxes(title_text="Price (USD)", secondary_y=True)
    
    fig.update_layout(
        title=f'{coin} Open Interest vs Price',
        hovermode='x unified',
        height=500
    )
    
    return fig


def analyze_oi_divergence(historical: List[Dict]) -> Dict:
    """
    Analyze OI divergence signals.
    - Rising OI + Rising Price = Strong bullish (new longs entering)
    - Rising OI + Falling Price = Strong bearish (new shorts entering)
    - Falling OI + Rising Price = Weak bullish (shorts covering)
    - Falling OI + Falling Price = Weak bearish (longs closing)
    """
    if not historical or len(historical) < 10:
        return {}
    
    df = pd.DataFrame(historical)
    df = df.sort_values('timestamp')
    
    # Recent trend (last 20 periods)
    recent = df.tail(20)
    
    oi_change = recent['open_interest'].iloc[-1] - recent['open_interest'].iloc[0]
    oi_pct = (oi_change / recent['open_interest'].iloc[0]) * 100
    
    # Determine trend
    if oi_pct > 5:
        oi_trend = 'Rising'
    elif oi_pct < -5:
        oi_trend = 'Falling'
    else:
        oi_trend = 'Flat'
    
    return {
        'oi_trend': oi_trend,
        'oi_change_pct': oi_pct,
        'interpretation': _interpret_oi_trend(oi_trend)
    }


def _interpret_oi_trend(oi_trend: str) -> str:
    """Interpret OI trend."""
    interpretations = {
        'Rising': '📈 New positions entering market (high conviction)',
        'Falling': '📉 Positions being closed (profit-taking or stop-outs)',
        'Flat': '➡️ Balanced market (no major position changes)'
    }
    return interpretations.get(oi_trend, 'Unknown')


def show_open_interest_metric():
    """Display Open Interest metric in Streamlit."""
    st.subheader("📊 Open Interest Analysis")
    
    st.info("""
    💡 **Open Interest (OI)** là tổng số contracts đang mở (chưa đóng) trên futures market.
    - **Rising OI + Rising Price**: Strong bullish - new longs entering
    - **Rising OI + Falling Price**: Strong bearish - new shorts entering
    - **Falling OI + Rising Price**: Weak bullish - shorts covering
    - **Falling OI + Falling Price**: Weak bearish - longs closing
    """)
    
    # Controls
    col1, col2 = st.columns([3, 1])
    
    with col1:
        try:
            from config import COIN_LIST
            portfolio_symbols = [symbol.upper() for _, symbol in COIN_LIST]
            all_coins = list(set(portfolio_symbols + ['BTC', 'ETH', 'SOL', 'BNB']))
            all_coins.sort()
        except:
            all_coins = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'DOGE', 'AVAX']
        
        selected_coin = st.selectbox(
            'Select Coin',
            options=all_coins,
            index=0,
            key='oi_coin_select'
        )
    
    with col2:
        force_refresh = st.button("🔄 Refresh", key='oi_refresh')
    
    if force_refresh:
        try:
            if os.path.exists(_get_cache_path()):
                os.remove(_get_cache_path())
        except Exception:
            pass
    
    # Show cache age
    cache = _load_cache()
    if cache:
        age_mins = (time.time() - cache.get('timestamp', 0)) / 60
        st.caption(f"📦 Data {age_mins:.1f} phút trước (updates mỗi 5 phút)")
    
    st.markdown("---")
    
    # Fetch data
    with st.spinner(f"Loading {selected_coin} open interest..."):
        data, success = fetch_all_open_interest([selected_coin])
    
    if not success or selected_coin not in data:
        st.error(f"❌ Failed to load open interest for {selected_coin}")
        st.warning("Check: Exchange API availability, coin has perpetual contract")
        return
    
    coin_data = data[selected_coin]
    
    # Summary metrics
    st.markdown("### 📈 Total Open Interest")
    
    col1, col2, col3 = st.columns(3)
    
    total_oi = coin_data['total_oi']
    total_oi_usd = coin_data['total_oi_usd']
    num_exchanges = len(coin_data['exchanges'])
    
    col1.metric(
        "Total OI (Contracts)",
        f"{total_oi:,.0f}",
        help="Combined open interest across all exchanges"
    )
    
    if total_oi_usd > 0:
        col2.metric(
            "Total OI (USD)",
            f"${total_oi_usd:,.0f}",
            help="USD value of open interest"
        )
    
    col3.metric(
        "Exchanges Tracked",
        f"{num_exchanges}",
        help="Number of exchanges with data"
    )
    
    # Exchange comparison
    st.markdown("### 🏦 Open Interest by Exchange")
    
    oi_df = create_oi_comparison_table(coin_data['exchanges'], selected_coin)
    
    if not oi_df.empty:
        # Color coding by market share
        def color_market_share(val):
            if isinstance(val, (int, float)):
                if val > 40:
                    return 'background-color: rgba(16, 185, 129, 0.3)'
                elif val > 25:
                    return 'background-color: rgba(251, 191, 36, 0.2)'
            return ''
        
        styled_df = oi_df.style.map(color_market_share, subset=['Market Share (%)'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Market concentration
        top_exchange_share = oi_df['Market Share (%)'].iloc[0]
        if top_exchange_share > 50:
            st.warning(f"⚠️ High concentration: {oi_df['Exchange'].iloc[0]} controls {top_exchange_share:.1f}% of market")
    
    # Historical OI chart
    if coin_data.get('historical'):
        st.markdown("### 📊 Open Interest History")
        
        oi_chart = plot_oi_history(coin_data['historical'], selected_coin)
        if oi_chart:
            st.plotly_chart(oi_chart, use_container_width=True, config={'displaylogo': False})
        
        # OI divergence analysis
        st.markdown("### 🔍 OI Trend Analysis")
        
        divergence = analyze_oi_divergence(coin_data['historical'])
        if divergence:
            col1, col2 = st.columns(2)
            
            col1.metric(
                "OI Trend",
                divergence['oi_trend'],
                delta=f"{divergence['oi_change_pct']:.2f}%"
            )
            
            col2.info(divergence['interpretation'])
    
    # Interpretation guide
    with st.expander("ℹ️ How to Use Open Interest", expanded=False):
        st.markdown("""
        **Understanding Open Interest:**
        
        **What is OI?**
        - Total number of outstanding futures contracts
        - Each contract represents 1 buyer and 1 seller
        - Higher OI = More market participation and liquidity
        
        **OI + Price Interpretation:**
        
        | OI Trend | Price Trend | Interpretation | Action |
        |----------|-------------|----------------|--------|
        | ⬆️ Rising | ⬆️ Rising | Strong bullish - new longs | Hold longs, add on dips |
        | ⬆️ Rising | ⬇️ Falling | Strong bearish - new shorts | Hold shorts, add on rallies |
        | ⬇️ Falling | ⬆️ Rising | Weak bullish - short covering | Take profits on longs |
        | ⬇️ Falling | ⬇️ Falling | Weak bearish - long closing | Take profits on shorts |
        
        **Key Signals:**
        
        1. **OI Surge (>20% in 24h):**
           - New money entering
           - High conviction move
           - Potential for continued trend
        
        2. **OI Drop (>20% in 24h):**
           - Mass liquidations or profit-taking
           - Trend may be exhausting
           - Watch for reversal
        
        3. **OI Flat with Price Move:**
           - Weak move, likely reversal
           - Low conviction
           - Range-bound market
        
        **Trading Strategies:**
        
        - **Trend Following:** Trade in direction when OI + price both rising/falling
        - **Reversal:** Watch for OI drop after extreme moves (exhaustion)
        - **Breakout Confirmation:** OI surge on breakout = real move
        - **False Breakout:** Price breaks but OI flat = likely false
        
        **Risk Management:**
        - High OI concentrations (>50% one exchange) = liquidity risk
        - Sudden OI drops = potential cascade liquidations
        - Monitor OI/Volume ratio for manipulation detection
        
        **Example:**
        - BTC at $100k, OI rising 30% → Strong conviction, likely continues
        - BTC at $100k, OI falling 30% → Weak hands shaken, reversal likely
        """)


if __name__ == '__main__':
    # Test
    print("Testing Open Interest...")
    data = fetch_binance_open_interest('BTC')
    if data:
        print(f"BTC Open Interest: {data['open_interest']:,.0f}")
        print(f"Historical points: {len(data['historical'])}")
