"""
Altcoin Season Index Metric

Measures market sentiment: Are altcoins outperforming Bitcoin?
- Index: % of top 50 altcoins that outperformed BTC in last 90 days
- 0-25: Bitcoin Season
- 25-75: Neutral
- 75-100: Altcoin Season

Data source: CoinGecko API (top 100 coins by market cap)
Calculation: Compare 90-day performance of each altcoin vs BTC
Cache: 3600s (1 hour)
"""

import os
import json
import time
from typing import Optional, Dict, Tuple, List
from datetime import datetime, timedelta

import pandas as pd
import requests

# Lazy imports for Streamlit/Plotly (only when needed)
try:
    import plotly.graph_objects as go
    import streamlit as st
    HAS_UI_LIBS = True
except ImportError:
    HAS_UI_LIBS = False

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


def fetch_altcoin_season_index() -> Tuple[float, Dict, bool]:
    """Calculate altcoin season index using CoinGecko API with CoinPaprika fallback.
    
    Methodology:
    1. Try CoinGecko first (primary source)
    2. If CoinGecko fails (rate limit/error), fallback to CoinPaprika
    3. Filter out Bitcoin and stablecoins → get top 50 altcoins
    4. Compare each altcoin's 90-day performance vs BTC
    5. Index = (number of altcoins outperforming BTC / 50) * 100
    
    Returns:
        (index, data, success): index 0-100, raw data dict, success flag
    """
    cache = _load_cache()
    if cache:
        return cache.get('index', 50), cache.get('data', {}), True
    
    # Try CoinGecko first
    print("[Altcoin Season] Attempting CoinGecko API...")
    index, data, success = _fetch_from_coingecko()
    
    if success:
        data['data_source'] = 'CoinGecko'
        _save_cache({'index': index, 'data': data})
        return index, data, True
    
    # Fallback to CryptoCompare
    print("[Altcoin Season] CoinGecko failed, trying CryptoCompare fallback...")
    try:
        from altcoin_season_cryptocompare import fetch_altcoin_season_coinpaprika
        index, data, success = fetch_altcoin_season_coinpaprika()
        
        if success:
            _save_cache({'index': index, 'data': data})
            return index, data, True
    except Exception as e:
        print(f"[Altcoin Season] CoinPaprika fallback failed: {e}")
    
    return 50, {}, False


def _fetch_from_coingecko() -> Tuple[float, Dict, bool]:
    """Fetch altcoin season index from CoinGecko API.
    
    Returns:
        (index, data, success): index 0-100, raw data dict, success flag
    """
    
    try:
        # Fetch historical prices for BTC (90 days)
        btc_history_url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        btc_params = {'vs_currency': 'usd', 'days': '90', 'interval': 'daily'}
        btc_response = requests.get(btc_history_url, params=btc_params, timeout=15)
        btc_response.raise_for_status()
        btc_data = btc_response.json()
        
        # Calculate BTC 90-day performance
        if not btc_data.get('prices') or len(btc_data['prices']) < 2:
            print("[Altcoin Season] Insufficient BTC historical data")
            return 50, {}, False
        
        btc_price_90d_ago = btc_data['prices'][0][1]
        btc_price_now = btc_data['prices'][-1][1]
        btc_performance = ((btc_price_now - btc_price_90d_ago) / btc_price_90d_ago) * 100
        
        # Fetch top 100 coins
        markets_url = "https://api.coingecko.com/api/v3/coins/markets"
        markets_params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 100,
            'page': 1,
            'sparkline': False
        }
        markets_response = requests.get(markets_url, params=markets_params, timeout=15)
        markets_response.raise_for_status()
        all_coins = markets_response.json()
        
        # Filter altcoins (exclude BTC and major stablecoins)
        stablecoins = {
            'tether', 'usd-coin', 'binance-usd', 'dai', 'frax', 
            'true-usd', 'paxos-standard', 'first-digital-usd', 'usdd',
            'gemini-dollar', 'paypal-usd', 'tether-gold'
        }
        altcoins = [c for c in all_coins if c['id'] not in {'bitcoin'} | stablecoins][:50]
        
        # Fetch 90-day performance for each altcoin
        outperforming_count = 0
        altcoin_performances: List[Dict] = []
        
        print(f"[Altcoin Season] Analyzing {len(altcoins)} altcoins vs BTC ({btc_performance:+.2f}%)")
        print(f"[Altcoin Season] Rate limiting: ~3 seconds per coin to avoid 429 errors")
        
        for i, alt in enumerate(altcoins):
            try:
                alt_history_url = f"https://api.coingecko.com/api/v3/coins/{alt['id']}/market_chart"
                alt_params = {'vs_currency': 'usd', 'days': '90', 'interval': 'daily'}
                
                # Aggressive rate limiting: CoinGecko free tier = 10-50 calls/minute
                # Use 3 second delay = 20 calls/minute to be safe
                time.sleep(3.2)
                
                alt_response = requests.get(alt_history_url, params=alt_params, timeout=15)
                alt_response.raise_for_status()
                alt_data = alt_response.json()
                
                if alt_data.get('prices') and len(alt_data['prices']) >= 2:
                    alt_price_90d_ago = alt_data['prices'][0][1]
                    alt_price_now = alt_data['prices'][-1][1]
                    alt_performance = ((alt_price_now - alt_price_90d_ago) / alt_price_90d_ago) * 100
                    
                    altcoin_performances.append({
                        'name': alt['name'],
                        'symbol': alt['symbol'].upper(),
                        'performance_90d': alt_performance,
                        'outperforms_btc': alt_performance > btc_performance
                    })
                    
                    if alt_performance > btc_performance:
                        outperforming_count += 1
                    
                    print(f"[Altcoin Season] {i+1}/{len(altcoins)}: {alt['symbol'].upper()} = {alt_performance:+.2f}%")
                    
            except Exception as e:
                print(f"[Altcoin Season] Error fetching {alt['id']}: {e}")
                # On rate limit, wait even longer
                if "429" in str(e) or "Too Many Requests" in str(e):
                    print(f"[Altcoin Season] Rate limited! Waiting 10 seconds...")
                    time.sleep(10)
                continue
        
        # Calculate index
        total_analyzed = len(altcoin_performances)
        if total_analyzed == 0:
            print("[Altcoin Season] No altcoins analyzed successfully")
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
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        # Cache result
        _save_cache({'index': index, 'data': data})
        
        print(f"[Altcoin Season] ✅ Index: {index:.1f} ({outperforming_count}/{total_analyzed} outperforming)")
        
        return index, data, True
        
    except Exception as e:
        print(f"[Altcoin Season] Error fetching from API: {e}")
        import traceback
        traceback.print_exc()
        return 50, {}, False


def plot_altcoin_season_gauge(index: float):
    """Create gauge chart for altcoin season index."""
    if not HAS_UI_LIBS:
        return None
    
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
    if not HAS_UI_LIBS:
        print("Error: Streamlit and Plotly required for UI display")
        return
    
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
    
    with st.spinner("Analyzing top 50 altcoins vs Bitcoin (90 days)... This may take 1-2 minutes."):
        index, data, success = fetch_altcoin_season_index()
    
    if not success:
        st.error("❌ Failed to calculate Altcoin Season Index. API rate limit or connection issue.")
        return
    
    # Display gauge
    fig = plot_altcoin_season_gauge(index)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False})
    
    # KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Index", f"{index:.0f}/100")
    with col2:
        st.metric("Altcoins Outperforming", f"{data.get('altcoins_outperforming', 0)}/{data.get('altcoins_total', 50)}")
    with col3:
        btc_perf = data.get('btc_performance_90d', 0)
        st.metric("BTC 90D Performance", f"{btc_perf:+.1f}%")
    with col4:
        calc_date = data.get('calculation_date', 'N/A')
        st.metric("Calculated At", calc_date.split()[0] if ' ' in calc_date else calc_date)
    with col5:
        data_source = data.get('data_source', 'Unknown')
        source_emoji = "🦎" if data_source == "CoinGecko" else "📊" if data_source == "CoinPaprika" else "❓"
        st.metric("Data Source", f"{source_emoji} {data_source}")
    
    # Interpretation
    st.markdown("---")
    st.markdown("""
    **Cách đọc:**
    - **0-25**: Bitcoin Season - BTC outperform hầu hết altcoin
    - **25-75**: Neutral - Thị trường hỗn hợp
    - **75-100**: Altcoin Season - Altcoin outperform BTC
    
    **Ý nghĩa:** Index cao → vốn đang rotate sang altcoin → thời điểm tốt để trade alt
    
    **Phương pháp tính:**
    - Lấy top 50 altcoin theo market cap (loại trừ BTC và stablecoin)
    - So sánh performance 90 ngày của mỗi altcoin vs BTC
    - Index = (số altcoin outperform / 50) × 100
    
    **Nguồn dữ liệu:** 
    - Primary: CoinGecko API (historical prices, 90 days)
    - Fallback: CoinPaprika API (if CoinGecko rate limited)
    - Auto-fallback khi gặp 429 Too Many Requests
    """)
    
    # Top performers
    col_left, col_right = st.columns(2)
    
    with col_left:
        with st.expander("🏆 Top 10 Performers (90 days)", expanded=False):
            if data.get('top_performers'):
                df = pd.DataFrame(data['top_performers'])
                df['outperforms'] = df['outperforms_btc'].apply(lambda x: '✅' if x else '❌')
                st.dataframe(
                    df[['name', 'symbol', 'performance_90d', 'outperforms']]
                    .rename(columns={
                        'name': 'Name', 
                        'symbol': 'Symbol', 
                        'performance_90d': '90D %',
                        'outperforms': 'vs BTC'
                    })
                    .style.format({'90D %': '{:+.2f}%'}),
                    hide_index=True,
                    use_container_width=True
                )
    
    with col_right:
        with st.expander("📉 Worst 10 Performers (90 days)", expanded=False):
            if data.get('worst_performers'):
                df = pd.DataFrame(data['worst_performers'])
                df['outperforms'] = df['outperforms_btc'].apply(lambda x: '✅' if x else '❌')
                st.dataframe(
                    df[['name', 'symbol', 'performance_90d', 'outperforms']]
                    .rename(columns={
                        'name': 'Name', 
                        'symbol': 'Symbol', 
                        'performance_90d': '90D %',
                        'outperforms': 'vs BTC'
                    })
                    .style.format({'90D %': '{:+.2f}%'}),
                    hide_index=True,
                    use_container_width=True
                )


if __name__ == "__main__":
    print("Testing Altcoin Season Index...")
    idx, dat, ok = fetch_altcoin_season_index()
    print(f"Index: {idx:.1f}, Success: {ok}")
    if dat:
        print(f"BTC Performance: {dat.get('bitcoin_performance'):.2f}%")
        print(f"Outperforming: {dat.get('altcoins_outperforming')}/{dat.get('altcoins_total')}")
        print(f"Month: {dat.get('month')}")
        print(f"History points: {len(dat.get('history', []))}")
