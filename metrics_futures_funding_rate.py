"""
Futures Funding Rate Metric

Displays current and historical funding rates across major exchanges.
Funding rate indicates the cost/profit of holding long vs short positions.

Features:
- Current funding rate comparison across exchanges
- Historical funding rate charts
- Predicted next funding rate
- Funding rate correlation with price
- Multi-coin support

Data source: Binance, OKX, Bybit APIs

Cache: 5 minutes (updated every funding interval)
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

CACHE_FILE = 'futures_funding_rate_cache.json'
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


def fetch_binance_funding_rate(symbol: str = 'BTC') -> Optional[Dict]:
    """
    Fetch current and historical funding rate from Binance.
    
    Endpoints:
    - /fapi/v1/premiumIndex - Current funding rate
    - /fapi/v1/fundingRate - Historical funding rate
    """
    try:
        symbol_pair = f'{symbol}USDT'
        
        # Current funding rate
        current_url = 'https://fapi.binance.com/fapi/v1/premiumIndex'
        current_response = requests.get(current_url, params={'symbol': symbol_pair}, timeout=10)
        
        if current_response.status_code != 200:
            print(f"[Funding Rate] Binance {symbol}: Status {current_response.status_code}")
            return None
        
        current_data = current_response.json()
        
        # Historical funding rate (last 100 funding intervals)
        hist_url = 'https://fapi.binance.com/fapi/v1/fundingRate'
        hist_response = requests.get(hist_url, params={
            'symbol': symbol_pair,
            'limit': 100
        }, timeout=10)
        
        if hist_response.status_code != 200:
            print(f"[Funding Rate] Binance history {symbol}: Status {hist_response.status_code}")
            historical = []
        else:
            historical = hist_response.json()
        
        return {
            'exchange': 'Binance',
            'symbol': symbol,
            'funding_rate': float(current_data.get('lastFundingRate', 0)) * 100,  # Convert to %
            'mark_price': float(current_data.get('markPrice', 0)),
            'index_price': float(current_data.get('indexPrice', 0)),
            'next_funding_time': int(current_data.get('nextFundingTime', 0)),
            'funding_interval_hours': 8,  # Binance: every 8 hours
            'historical': [
                {
                    'timestamp': int(item['fundingTime']),
                    'funding_rate': float(item['fundingRate']) * 100
                }
                for item in historical
            ]
        }
    except requests.exceptions.RequestException as e:
        print(f"[Funding Rate] Binance {symbol} network error: {type(e).__name__}")
        return None
    except Exception as e:
        print(f"[Funding Rate] Binance {symbol} error: {e}")
        return None


def fetch_okx_funding_rate(symbol: str = 'BTC') -> Optional[Dict]:
    """Fetch funding rate from OKX."""
    try:
        inst_id = f'{symbol}-USDT-SWAP'
        
        # Current funding rate
        current_url = 'https://www.okx.com/api/v5/public/funding-rate'
        current_response = requests.get(current_url, params={'instId': inst_id}, timeout=10)
        
        if current_response.status_code != 200:
            print(f"[Funding Rate] OKX {symbol}: Status {current_response.status_code}")
            return None
        
        current_data = current_response.json()
        if current_data.get('code') != '0' or not current_data.get('data'):
            print(f"[Funding Rate] OKX {symbol}: No data")
            return None
        
        data = current_data['data'][0]
        
        # Historical funding rate
        hist_url = 'https://www.okx.com/api/v5/public/funding-rate-history'
        hist_response = requests.get(hist_url, params={
            'instId': inst_id,
            'limit': 100
        }, timeout=10)
        
        historical = []
        if hist_response.status_code == 200:
            hist_data = hist_response.json()
            if hist_data.get('code') == '0' and hist_data.get('data'):
                historical = [
                    {
                        'timestamp': int(item['fundingTime']),
                        'funding_rate': float(item['fundingRate']) * 100
                    }
                    for item in hist_data['data']
                ]
        
        return {
            'exchange': 'OKX',
            'symbol': symbol,
            'funding_rate': float(data.get('fundingRate', 0)) * 100,
            'next_funding_time': int(data.get('nextFundingTime', 0)),
            'funding_interval_hours': 8,
            'historical': historical
        }
    except Exception as e:
        print(f"[Funding Rate] OKX {symbol} error: {e}")
        return None


def fetch_bybit_funding_rate(symbol: str = 'BTC') -> Optional[Dict]:
    """Fetch funding rate from Bybit."""
    try:
        symbol_pair = f'{symbol}USDT'
        
        # Bybit V5 API
        url = 'https://api.bybit.com/v5/market/tickers'
        response = requests.get(url, params={
            'category': 'linear',
            'symbol': symbol_pair
        }, timeout=10)
        
        if response.status_code != 200:
            print(f"[Funding Rate] Bybit {symbol}: Status {response.status_code}")
            return None
        
        data = response.json()
        if data.get('retCode') != 0 or not data.get('result', {}).get('list'):
            print(f"[Funding Rate] Bybit {symbol}: No data")
            return None
        
        ticker = data['result']['list'][0]
        
        return {
            'exchange': 'Bybit',
            'symbol': symbol,
            'funding_rate': float(ticker.get('fundingRate', 0)) * 100,
            'next_funding_time': int(ticker.get('nextFundingTime', 0)),
            'funding_interval_hours': 8,
            'historical': []  # Would need separate API call
        }
    except Exception as e:
        print(f"[Funding Rate] Bybit {symbol} error: {e}")
        return None


def fetch_all_funding_rates(coins: List[str]) -> Tuple[Dict, bool]:
    """Fetch funding rates from all exchanges for multiple coins."""
    cache = _load_cache()
    cache_key = '-'.join(coins)
    
    if cache and cache.get('data', {}).get(cache_key):
        print(f"[Funding Rate] Loaded from cache")
        return cache['data'][cache_key], True
    
    try:
        all_data = {}
        
        for coin in coins:
            coin_data = {
                'exchanges': []
            }
            
            # Fetch from Binance
            binance_data = fetch_binance_funding_rate(coin)
            if binance_data:
                coin_data['exchanges'].append(binance_data)
                coin_data['historical'] = binance_data['historical']  # Use Binance as primary
                print(f"[Funding Rate] OK {coin} Binance: {binance_data['funding_rate']:.4f}%")
            
            # Fetch from OKX
            okx_data = fetch_okx_funding_rate(coin)
            if okx_data:
                coin_data['exchanges'].append(okx_data)
                print(f"[Funding Rate] OK {coin} OKX: {okx_data['funding_rate']:.4f}%")
            
            # Fetch from Bybit
            bybit_data = fetch_bybit_funding_rate(coin)
            if bybit_data:
                coin_data['exchanges'].append(bybit_data)
                print(f"[Funding Rate] OK {coin} Bybit: {bybit_data['funding_rate']:.4f}%")
            
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
        print(f"[Funding Rate] Error: {e}")
        return {}, False


def create_funding_rate_comparison_table(exchanges: List[Dict], coin: str) -> pd.DataFrame:
    """Create exchange comparison table for funding rates."""
    if not exchanges:
        return pd.DataFrame()
    
    rows = []
    for ex in exchanges:
        # Calculate annualized rate (funding every 8h = 3x per day)
        daily_rate = ex['funding_rate'] * (24 / ex['funding_interval_hours'])
        annual_rate = daily_rate * 365
        
        rows.append({
            'Exchange': ex['exchange'],
            'Current Rate (%)': ex['funding_rate'],
            'Daily (%)': daily_rate,
            'Annual (%)': annual_rate,
            'Next Funding': datetime.fromtimestamp(ex['next_funding_time']/1000).strftime('%H:%M') if ex.get('next_funding_time') else 'N/A'
        })
    
    df = pd.DataFrame(rows)
    
    # Sort by current rate (most positive first)
    df = df.sort_values('Current Rate (%)', ascending=False)
    df.insert(0, 'Rank', range(1, len(df) + 1))
    
    return df


def plot_funding_rate_history(historical: List[Dict], coin: str) -> go.Figure:
    """Plot historical funding rate."""
    if not historical or len(historical) == 0:
        return None
    
    df = pd.DataFrame(historical)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('datetime')
    
    # Calculate moving average
    df['ma_7'] = df['funding_rate'].rolling(window=7, min_periods=1).mean()
    
    fig = go.Figure()
    
    # Funding rate bars
    colors = ['#10b981' if x > 0 else '#ef4444' for x in df['funding_rate']]
    
    fig.add_trace(go.Bar(
        x=df['datetime'],
        y=df['funding_rate'],
        name='Funding Rate',
        marker_color=colors,
        opacity=0.7
    ))
    
    # Moving average
    fig.add_trace(go.Scatter(
        x=df['datetime'],
        y=df['ma_7'],
        name='MA(7)',
        line=dict(color='#fbbf24', width=2),
        mode='lines'
    ))
    
    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    # Extreme zones
    fig.add_hrect(y0=0.05, y1=0.1, fillcolor="green", opacity=0.1, line_width=0)
    fig.add_hrect(y0=-0.05, y1=-0.1, fillcolor="red", opacity=0.1, line_width=0)
    
    fig.update_layout(
        title=f'{coin} Funding Rate History (Last 100 Intervals)',
        xaxis_title='Time',
        yaxis_title='Funding Rate (%)',
        hovermode='x unified',
        height=450,
        showlegend=True
    )
    
    return fig


def plot_funding_vs_price(historical: List[Dict], coin: str, price_data: Optional[pd.DataFrame] = None) -> go.Figure:
    """Plot funding rate vs price movement correlation."""
    if not historical or len(historical) == 0:
        return None
    
    df = pd.DataFrame(historical)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('datetime')
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f'{coin} Funding Rate', 'Rate Interpretation'),
        row_heights=[0.7, 0.3]
    )
    
    # Funding rate
    colors = ['#10b981' if x > 0 else '#ef4444' for x in df['funding_rate']]
    fig.add_trace(
        go.Bar(x=df['datetime'], y=df['funding_rate'], marker_color=colors, name='Funding Rate'),
        row=1, col=1
    )
    
    # Interpretation zones
    df['signal'] = 'Neutral'
    df.loc[df['funding_rate'] > 0.05, 'signal'] = 'Overleveraged Long'
    df.loc[df['funding_rate'] < -0.05, 'signal'] = 'Overleveraged Short'
    
    signal_colors = {
        'Overleveraged Long': 1,
        'Neutral': 0,
        'Overleveraged Short': -1
    }
    df['signal_value'] = df['signal'].map(signal_colors)
    
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['signal_value'],
            mode='lines',
            fill='tozeroy',
            line=dict(width=0),
            fillcolor='rgba(16, 185, 129, 0.3)',
            name='Signal',
            showlegend=False
        ),
        row=2, col=1
    )
    
    # Add annotations
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
    
    fig.update_yaxes(title_text="Funding Rate (%)", row=1, col=1)
    fig.update_yaxes(title_text="Market Signal", tickvals=[-1, 0, 1], 
                     ticktext=['Short Squeeze Risk', 'Neutral', 'Long Squeeze Risk'], row=2, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    
    fig.update_layout(height=600, hovermode='x unified')
    
    return fig


def show_funding_rate_metric():
    """Display Funding Rate metric in Streamlit."""
    st.subheader("💰 Funding Rate Analysis")
    
    st.info("""
    💡 **Funding Rate** là chi phí hold position trong futures perpetual contracts.
    - **Positive rate** (xanh): Longs pay shorts → Thị trường overleveraged long
    - **Negative rate** (đỏ): Shorts pay longs → Thị trường overleveraged short
    - **Rate > 0.1%**: Extreme bullish → Có thể long squeeze
    - **Rate < -0.1%**: Extreme bearish → Có thể short squeeze
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
            key='funding_coin_select'
        )
    
    with col2:
        force_refresh = st.button("🔄 Refresh", key='funding_refresh')
    
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
    with st.spinner(f"Loading {selected_coin} funding rate..."):
        data, success = fetch_all_funding_rates([selected_coin])
    
    if not success or selected_coin not in data:
        st.error(f"❌ Failed to load funding rate for {selected_coin}")
        st.warning("Check: Binance/OKX/Bybit API availability, coin has perpetual contract")
        return
    
    coin_data = data[selected_coin]
    
    # Current rates comparison
    st.markdown("### 📊 Current Funding Rates by Exchange")
    
    exchanges_df = create_funding_rate_comparison_table(coin_data['exchanges'], selected_coin)
    
    if not exchanges_df.empty:
        # Color coding
        def color_rate(val):
            if isinstance(val, (int, float)):
                if val > 0.05:
                    return 'background-color: rgba(16, 185, 129, 0.3)'
                elif val < -0.05:
                    return 'background-color: rgba(239, 68, 68, 0.3)'
                elif val > 0:
                    return 'background-color: rgba(16, 185, 129, 0.1)'
                elif val < 0:
                    return 'background-color: rgba(239, 68, 68, 0.1)'
            return ''
        
        styled_df = exchanges_df.style.map(
            color_rate, 
            subset=['Current Rate (%)', 'Daily (%)', 'Annual (%)']
        )
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Summary stats
        avg_rate = exchanges_df['Current Rate (%)'].mean()
        avg_daily = exchanges_df['Daily (%)'].mean()
        avg_annual = exchanges_df['Annual (%)'].mean()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Avg Current Rate", f"{avg_rate:.4f}%", 
                    delta=f"{'Longs pay' if avg_rate > 0 else 'Shorts pay'}")
        col2.metric("Avg Daily Cost", f"{avg_daily:.3f}%")
        col3.metric("Annualized", f"{avg_annual:.1f}%")
    
    # Historical funding rate
    if coin_data.get('historical'):
        st.markdown("### 📈 Funding Rate History")
        
        hist_chart = plot_funding_rate_history(coin_data['historical'], selected_coin)
        if hist_chart:
            st.plotly_chart(hist_chart, use_container_width=True, config={'displaylogo': False})
        
        # Funding vs price correlation
        st.markdown("### 🔍 Market Sentiment Analysis")
        corr_chart = plot_funding_vs_price(coin_data['historical'], selected_coin)
        if corr_chart:
            st.plotly_chart(corr_chart, use_container_width=True, config={'displaylogo': False})
    
    # Interpretation guide
    with st.expander("ℹ️ How to Use Funding Rate", expanded=False):
        st.markdown("""
        **Understanding Funding Rate:**
        
        **Positive Funding (Green):**
        - Longs outnumber shorts → Bullish sentiment
        - Long positions pay shorts every 8 hours
        - Rate > 0.05%: Overleveraged longs, long squeeze risk
        - Rate > 0.1%: EXTREME - high risk of liquidation cascade
        
        **Negative Funding (Red):**
        - Shorts outnumber longs → Bearish sentiment
        - Short positions pay longs every 8 hours
        - Rate < -0.05%: Overleveraged shorts, short squeeze risk
        - Rate < -0.1%: EXTREME - shorts may get liquidated
        
        **Trading Strategies:**
        
        1. **Funding Arbitrage:**
           - High positive rate → Short + buy spot (collect funding)
           - High negative rate → Long + short spot (collect funding)
        
        2. **Contrarian Signals:**
           - Rate > 0.1% for extended period → Consider shorting
           - Rate < -0.1% for extended period → Consider longing
        
        3. **Trend Confirmation:**
           - Rising price + rising funding → Strong bull trend
           - Falling price + falling funding → Strong bear trend
           - Divergence may signal trend reversal
        
        **Cost Examples (8h interval):**
        - Rate +0.01%: Long pays $1 per $10,000 position every 8h
        - Rate -0.05%: Short pays $5 per $10,000 position every 8h
        - Annual cost: Rate × 3 (daily) × 365
        
        **Note:** Funding collected/paid at 00:00, 08:00, 16:00 UTC (Binance/OKX)
        """)


if __name__ == '__main__':
    # Test
    print("Testing Funding Rate...")
    data = fetch_binance_funding_rate('BTC')
    if data:
        print(f"BTC Funding Rate: {data['funding_rate']:.4f}%")
        print(f"Historical points: {len(data['historical'])}")
