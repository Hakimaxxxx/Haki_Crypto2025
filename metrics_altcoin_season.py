"""
Altcoin Season Index Metric

Measures market sentiment: Are altcoins outperforming Bitcoin?
- Index: % of top 50 altcoins that outperformed BTC in last 90 days
- 0-25: Bitcoin Season
- 25-75: Neutral
- 75-100: Altcoin Season

Data source: CoinGecko top 50 coins
Cache: 3600s (1 hour)
"""

import os
import json
import time
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import requests

CACHE_FILE = "altcoin_season_cache.json"
CACHE_TTL = 3600  # 1 hour


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


def calculate_altcoin_season_index() -> Tuple[float, Dict, bool]:
    """Calculate altcoin season index.
    
    Returns:
        (index, data, success): index 0-100, raw data dict, success flag
    """
    cache = _load_cache()
    if cache:
        return cache.get('index', 50), cache.get('data', {}), True
    
    try:
        # Fetch top 100 coins by market cap
        # Note: CoinGecko only supports 1h,24h,7d,14d,30d,200d,1y for price_change_percentage
        # We use 30d as proxy for 90d (CoinGecko free tier limitation)
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 100,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '30d'
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        coins = response.json()
        
        # Filter out Bitcoin and stablecoins
        stablecoins = ['tether', 'usd-coin', 'binance-usd', 'dai', 'frax', 'true-usd', 'paxos-standard', 'first-digital-usd']
        altcoins = [c for c in coins if c['id'] not in ['bitcoin'] + stablecoins][:50]
        
        # Get BTC performance
        btc = next((c for c in coins if c['id'] == 'bitcoin'), None)
        if not btc:
            return 50, {}, False
        
        btc_change_30d = btc.get('price_change_percentage_30d_in_currency', 0) or 0
        
        # Count altcoins outperforming BTC
        outperforming = 0
        for alt in altcoins:
            alt_change = alt.get('price_change_percentage_30d_in_currency', 0) or 0
            if alt_change > btc_change_30d:
                outperforming += 1
        
        # Calculate index
        index = (outperforming / len(altcoins)) * 100 if altcoins else 50
        
        # Prepare data
        data = {
            'btc_change_30d': btc_change_30d,
            'altcoins_total': len(altcoins),
            'altcoins_outperforming': outperforming,
            'top_performers': sorted(
                [{'name': a['name'], 'symbol': a['symbol'].upper(), 'change_30d': a.get('price_change_percentage_30d_in_currency', 0) or 0}
                 for a in altcoins],
                key=lambda x: x['change_30d'],
                reverse=True
            )[:10]
        }
        
        # Cache result
        _save_cache({'index': index, 'data': data})
        
        return index, data, True
        
    except Exception as e:
        print(f"[Altcoin Season] Error: {e}")
        return 50, {}, False


def plot_altcoin_season_gauge(index: float) -> Optional[go.Figure]:
    """Create gauge chart for altcoin season index."""
    try:
        # Determine status and color
        if index < 25:
            status = "Bitcoin Season"
            color = "#F7931A"  # Bitcoin orange
        elif index > 75:
            status = "Altcoin Season"
            color = "#00D395"  # Green
        else:
            status = "Neutral"
            color = "#6C757D"  # Gray
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=index,
            number={'suffix': "/100", 'font': {'size': 40}},
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"<b>{status}</b>", 'font': {'size': 24}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkgray"},
                'bar': {'color': color, 'thickness': 0.75},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 25], 'color': 'rgba(247, 147, 26, 0.2)'},  # BTC season
                    {'range': [25, 75], 'color': 'rgba(108, 117, 125, 0.2)'},  # Neutral
                    {'range': [75, 100], 'color': 'rgba(0, 211, 149, 0.2)'}  # Alt season
                ],
                'threshold': {
                    'line': {'color': color, 'width': 4},
                    'thickness': 0.75,
                    'value': index
                }
            }
        ))
        
        fig.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=80, b=20),
            font={'color': "darkgray", 'family': "Arial"}
        )
        
        return fig
    except Exception as e:
        print(f"[Altcoin Season] Error creating gauge: {e}")
        return None


def show_altcoin_season_metric():
    """Display altcoin season metric in Streamlit."""
    st.subheader("🌙 Altcoin Season Index")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        force_refresh = st.button("🔄 Refresh", key="altseason_refresh")
    
    if force_refresh:
        try:
            if os.path.exists(_get_cache_path()):
                os.remove(_get_cache_path())
        except Exception:
            pass
    
    with st.spinner("Calculating Altcoin Season Index..."):
        index, data, success = calculate_altcoin_season_index()
    
    if not success:
        st.error("❌ Failed to calculate Altcoin Season Index. Please try again.")
        return
    
    # Display gauge
    fig = plot_altcoin_season_gauge(index)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False})
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Index", f"{index:.1f}/100")
    with col2:
        st.metric("Altcoins Outperforming BTC", f"{data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 50)}")
    with col3:
        btc_change = data.get('btc_change_30d', 0)
        st.metric("BTC 30D Change", f"{btc_change:+.1f}%")
    
    # Interpretation
    st.markdown("---")
    st.markdown("""
    **Cách đọc:**
    - **0-25**: Bitcoin Season - BTC outperform hầu hết altcoin
    - **25-75**: Neutral - Thị trường hỗn hợp
    - **75-100**: Altcoin Season - Altcoin outperform BTC
    
    **Ý nghĩa:** Index cao → vốn đang rotate sang altcoin → thời điểm tốt để trade alt
    
    **Lưu ý:** Index tính dựa trên 30 ngày (CoinGecko API limitation)
    """)
    
    # Top performers
    with st.expander("🏆 Top 10 Altcoins (30 ngày)", expanded=False):
        if data.get('top_performers'):
            df = pd.DataFrame(data['top_performers'])
            st.dataframe(
                df.style.format({'change_30d': '{:+.2f}%'}),
                hide_index=True,
                use_container_width=True
            )


if __name__ == "__main__":
    print("Testing Altcoin Season Index...")
    idx, dat, ok = calculate_altcoin_season_index()
    print(f"Index: {idx:.1f}, Success: {ok}")
    if dat:
        print(f"BTC 30d: {dat.get('btc_change_30d'):.2f}%")
        print(f"Outperforming: {dat.get('altcoins_outperforming')}/{dat.get('altcoins_total')}")
