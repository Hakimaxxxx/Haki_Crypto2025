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
        # Get top 100 altcoins (like Coinglass)
        altcoins = [c for c in all_coins if c['id'] not in {'bitcoin'} | stablecoins][:100]
        
        # Fetch 90-day performance for each altcoin
        outperforming_count = 0
        altcoin_performances: List[Dict] = []
        
        print(f"[Altcoin Season] Analyzing {len(altcoins)} altcoins vs BTC ({btc_performance:+.2f}%)")
        print(f"[Altcoin Season] Rate limiting: ~3 seconds per coin to avoid 429 errors")
        print(f"[Altcoin Season] WARNING: This will take ~5 minutes for 100 coins")
        
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


def load_altcoin_season_history_from_db(days: int = 365):
    """Load Altcoin Season Index historical data from MongoDB.
    
    Returns DataFrame with columns: timestamp, index_value, outperforming_count, total_count
    """
    try:
        from cloud_db import db
        
        if not db.available():
            print("[Altcoin Season Timeline] DB not available")
            return None
        
        collection = db.get_collection("altcoin_season_history")
        
        # Calculate date range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # Query documents
        query = {
            "timestamp": {
                "$gte": start_time.isoformat(),
                "$lte": end_time.isoformat()
            }
        }
        
        docs = list(collection.find(query).sort("timestamp", 1))
        
        if not docs:
            print("[Altcoin Season Timeline] No history data in DB")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(docs)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        print(f"[Altcoin Season Timeline] Loaded {len(df)} records from DB")
        return df
        
    except Exception as e:
        print(f"[Altcoin Season Timeline] DB load error: {e}")
        return None


def load_altcoin_season_history_from_csv():
    """Load Altcoin Season Index history from CSV backup."""
    try:
        from pathlib import Path
        csv_path = Path("altcoin_season_history.csv")
        
        if not csv_path.exists():
            print("[Altcoin Season Timeline] CSV not found")
            return None
        
        df = pd.read_csv(csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        print(f"[Altcoin Season Timeline] Loaded {len(df)} records from CSV")
        return df
        
    except Exception as e:
        print(f"[Altcoin Season Timeline] CSV load error: {e}")
        return None


def plot_altcoin_season_timeline(days: int = 365, width: int = 1200, height: int = 500):
    """Create Coinglass-style Altcoin Season Index timeline chart.
    
    Features matching the reference image:
    - Large timeline with Bitcoin Season (orange) and Altcoin Season (blue) zones
    - Gradient bar at top showing season transition
    - Current value displayed prominently
    - Dark theme like Coinglass
    - Smooth line with area fill
    
    Args:
        days: Days of history to display
        width: Chart width in pixels
        height: Chart height in pixels
    
    Returns:
        Plotly Figure or None
    """
    if not HAS_UI_LIBS:
        return None
    
    # Load data (DB first, fallback to CSV)
    df = load_altcoin_season_history_from_db(days)
    if df is None or df.empty:
        df = load_altcoin_season_history_from_csv()
    
    if df is None or df.empty:
        print("[Altcoin Season Timeline] No data available")
        return None
    
    # Filter data to requested number of days
    if len(df) > days:
        df = df.tail(days).copy()
    
    print(f"[Altcoin Season Timeline] Plotting {len(df)} days ({df['timestamp'].min()} to {df['timestamp'].max()})")
    
    # Create figure
    fig = go.Figure()
    
    # Background zones with better colors
    # Bitcoin Season zone (0-25) - Darker orange
    fig.add_shape(
        type="rect",
        x0=df['timestamp'].min(),
        x1=df['timestamp'].max(),
        y0=0,
        y1=25,
        fillcolor="rgba(244, 130, 37, 0.15)",  # Warmer orange
        line_width=0,
        layer="below"
    )
    
    # Neutral zone (25-75) - Very subtle
    fig.add_shape(
        type="rect",
        x0=df['timestamp'].min(),
        x1=df['timestamp'].max(),
        y0=25,
        y1=75,
        fillcolor="rgba(255, 255, 255, 0.02)",  # Almost invisible
        line_width=0,
        layer="below"
    )
    
    # Altcoin Season zone (75-100) - Brighter blue
    fig.add_shape(
        type="rect",
        x0=df['timestamp'].min(),
        x1=df['timestamp'].max(),
        y0=75,
        y1=100,
        fillcolor="rgba(99, 155, 255, 0.15)",  # Brighter blue
        line_width=0,
        layer="below"
    )
    
    # Add index line with smooth area fill (main visual element)
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['index_value'],
        mode='lines',
        name='Altcoin Season Index',
        line=dict(
            color='#66BB6A',  # Softer green
            width=3,
            shape='spline',  # Smooth curve
            smoothing=1.0
        ),
        fill='tozeroy',
        fillcolor='rgba(102, 187, 106, 0.08)',  # Very subtle fill
        hovertemplate=(
            '<b>%{x|%b %d, %Y}</b><br>' +
            'Index: <b>%{y:.0f}</b><br>' +
            'Outperforming: %{customdata[0]}/%{customdata[1]}<br>' +
            'BTC 90D: %{customdata[2]:+.1f}%' +
            '<extra></extra>'
        ),
        customdata=df[['outperforming_count', 'total_count', 'btc_performance_90d']].values
    ))
    
    # Current value indicator (horizontal dashed line)
    if not df.empty:
        current_value = df['index_value'].iloc[-1]
        
        fig.add_shape(
            type="line",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=current_value,
            y1=current_value,
            line=dict(
                color="rgba(255, 255, 255, 0.6)",
                width=1.5,
                dash="dot"
            ),
            layer="above"
        )
        
        # Large current value annotation (centered, high up)
        fig.add_annotation(
            x=df['timestamp'].iloc[len(df)//2],
            y=110,
            text=f"<b>{current_value:.0f}</b>",
            showarrow=False,
            font=dict(size=48, color="white", family="Arial Black"),
            bgcolor="rgba(30, 33, 48, 0.0)",  # Transparent background
            borderpad=0
        )
        
        # Season label next to value
        if current_value >= 75:
            season_label = "Altcoin Season"
            season_color = "#639bff"
        elif current_value <= 25:
            season_label = "Bitcoin Season"
            season_color = "#f48225"
        else:
            season_label = "Mixed Market"
            season_color = "#999999"
        
        fig.add_annotation(
            x=df['timestamp'].iloc[len(df)//2],
            y=103,
            text=f"<i>{season_label}</i>",
            showarrow=False,
            font=dict(size=16, color=season_color, family="Arial"),
            bgcolor="rgba(0,0,0,0)"
        )
    
    # Reference lines at 25 and 75 (more subtle)
    for level in [25, 75]:
        fig.add_shape(
            type="line",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=level,
            y1=level,
            line=dict(
                color="rgba(255, 255, 255, 0.15)",
                width=1,
                dash="dot"
            ),
            layer="below"
        )
    
    # Gradient bar at top (Bitcoin Season → Altcoin Season)
    time_range = df['timestamp'].max() - df['timestamp'].min()
    bar_y_bottom = 118
    bar_y_top = 122
    
    # Create smooth gradient using multiple rectangles
    num_segments = 20
    for i in range(num_segments):
        x_start = df['timestamp'].min() + (time_range * i / num_segments)
        x_end = df['timestamp'].min() + (time_range * (i + 1) / num_segments)
        
        # Color interpolation from orange to blue
        ratio = i / num_segments
        
        # RGB interpolation
        orange_r, orange_g, orange_b = 244, 130, 37
        blue_r, blue_g, blue_b = 99, 155, 255
        
        r = int(orange_r + (blue_r - orange_r) * ratio)
        g = int(orange_g + (blue_g - orange_g) * ratio)
        b = int(orange_b + (blue_b - orange_b) * ratio)
        
        fig.add_shape(
            type="rect",
            x0=x_start,
            x1=x_end,
            y0=bar_y_bottom,
            y1=bar_y_top,
            fillcolor=f"rgba({r}, {g}, {b}, 0.9)",
            line_width=0
        )
    
    # Labels on gradient bar (improved positioning)
    fig.add_annotation(
        x=df['timestamp'].min() + time_range * 0.15,
        y=(bar_y_bottom + bar_y_top) / 2,
        text="<b>Bitcoin Season</b>",
        showarrow=False,
        font=dict(size=13, color="white", family="Arial"),
        bgcolor="rgba(0,0,0,0.3)",
        borderpad=4
    )
    
    fig.add_annotation(
        x=df['timestamp'].min() + time_range * 0.85,
        y=(bar_y_bottom + bar_y_top) / 2,
        text="<b>Altcoin Season</b>",
        showarrow=False,
        font=dict(size=13, color="white", family="Arial"),
        bgcolor="rgba(0,0,0,0.3)",
        borderpad=4
    )
    
    # Layout (enhanced Coinglass dark theme)
    fig.update_layout(
        title=dict(
            text="<b>Altcoin Season Index</b>",
            font=dict(size=26, color="#e0e0e0", family="Arial"),
            x=0.02,
            y=0.97
        ),
        xaxis=dict(
            title="",
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.05)",
            gridwidth=1,
            color="#a0a0a0",
            rangeslider=dict(visible=False),
            zeroline=False
        ),
        yaxis=dict(
            title="",
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.08)",
            gridwidth=1,
            color="#a0a0a0",
            range=[-2, 125],  # Extended range for gradient bar
            fixedrange=True,
            tickvals=[0, 25, 50, 75, 100],
            ticktext=["0", "25", "50", "75", "100"],
            zeroline=False
        ),
        plot_bgcolor="#1a1d2e",  # Darker background
        paper_bgcolor="#1a1d2e",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#2d3142",
            font_size=13,
            font_family="Arial"
        ),
        width=width,
        height=height,
        margin=dict(l=60, r=60, t=100, b=60),
        showlegend=False
    )
    
    return fig


def show_altcoin_season_metric():
    """Display altcoin season metric in Streamlit."""
    if not HAS_UI_LIBS:
        print("Error: Streamlit and Plotly required for UI display")
        return
    
    st.subheader("🌙 Altcoin Season Index")
    
    # View mode selector
    view_mode = st.radio(
        "📊 View Mode",
        ["Timeline (Coinglass Style)", "Gauge (Classic)"],
        index=0,
        horizontal=True,
        key="altcoin_season_view_mode"
    )
    
    if view_mode == "Timeline (Coinglass Style)":
        # === TIMELINE VIEW (NEW) ===
        st.info("📈 **Altcoin Season Timeline:** Lịch sử dài hạn (1 năm+) với giao diện Coinglass. Data sync hàng ngày lúc 1 AM UTC, không reload API mỗi lần view.")
        
        # Timeline controls
        col1, col2, col3 = st.columns(3)
        with col1:
            days_history = st.selectbox(
                "History",
                ["30 days", "90 days", "180 days", "365 days"],
                index=3,
                key="altseason_timeline_days"
            )
            days_int = int(days_history.split()[0])
        
        with col2:
            # Daily sync status
            try:
                import altcoin_season_daily_sync
                daily_status = altcoin_season_daily_sync.get_daily_sync_status()
                last_sync = daily_status.get('last_sync', 'Never')
                
                if last_sync and last_sync != 'Never':
                    try:
                        dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                        hours_ago = (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600
                        last_sync = f"{hours_ago:.1f}h ago"
                    except:
                        pass
                
                st.caption(f"🕒 Last Snapshot: {last_sync}")
            except:
                st.caption("🕒 Daily sync not started")
        
        with col3:
            force_snapshot_btn = st.button("🔄 Force Snapshot", key="altseason_force_snapshot")
        
        if force_snapshot_btn:
            with st.spinner("Taking snapshot (may take 2-3 min due to API rate limits)..."):
                try:
                    import altcoin_season_daily_sync
                    if altcoin_season_daily_sync.force_daily_sync_now():
                        st.success("✅ Snapshot complete!")
                        st.rerun()
                    else:
                        st.error("❌ Snapshot failed. Check logs.")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        
        # Load and display timeline
        with st.spinner("Loading timeline..."):
            fig_timeline = plot_altcoin_season_timeline(days=days_int, width=1200, height=550)
            
            if fig_timeline:
                st.plotly_chart(fig_timeline, use_container_width=True, config={'displaylogo': False, 'responsive': True})
                
                # Show current stats in clean metrics row
                df_hist = load_altcoin_season_history_from_db(30)
                if df_hist is None:
                    df_hist = load_altcoin_season_history_from_csv()
                
                if df_hist is not None and not df_hist.empty:
                    latest = df_hist.iloc[-1]
                    
                    st.markdown("---")
                    st.markdown("### 📊 Current Market Analysis")
                    
                    metric_cols = st.columns(5)
                    
                    # Index value with delta
                    if len(df_hist) >= 7:
                        prev_week = df_hist.iloc[-7]['index_value']
                        delta_week = latest['index_value'] - prev_week
                        metric_cols[0].metric(
                            "Index", 
                            f"{latest['index_value']:.0f}/100",
                            delta=f"{delta_week:+.1f} (7D)"
                        )
                    else:
                        metric_cols[0].metric("Index", f"{latest['index_value']:.0f}/100")
                    
                    # Outperforming
                    metric_cols[1].metric(
                        "Alts Winning", 
                        f"{latest['outperforming_count']}/{latest['total_count']}",
                        help="Number of altcoins outperforming BTC over 90 days"
                    )
                    
                    # BTC performance
                    btc_perf = latest.get('btc_performance_90d', 0)
                    metric_cols[2].metric(
                        "BTC 90D", 
                        f"{btc_perf:+.1f}%",
                        help="Bitcoin 90-day price change"
                    )
                    
                    # Season determination with color
                    if latest['index_value'] >= 75:
                        season = "Altcoin Season"
                        season_color = "🔵"
                        season_desc = "Strong alt momentum"
                    elif latest['index_value'] <= 25:
                        season = "Bitcoin Season"
                        season_color = "🟠"
                        season_desc = "BTC dominance high"
                    else:
                        season = "Mixed Market"
                        season_color = "⚪"
                        season_desc = "Neutral conditions"
                    
                    metric_cols[3].metric(
                        "Market Phase",
                        f"{season_color} {season}",
                        help=season_desc
                    )
                    
                    # Trend analysis
                    if len(df_hist) >= 7:
                        recent_avg = df_hist['index_value'].tail(7).mean()
                        older_avg = df_hist['index_value'].head(min(7, len(df_hist))).mean()
                        
                        if recent_avg > older_avg + 5:
                            trend = "↗️ Trending Up"
                            trend_color = "green"
                        elif recent_avg < older_avg - 5:
                            trend = "↘️ Trending Down"
                            trend_color = "red"
                        else:
                            trend = "➡️ Stable"
                            trend_color = "gray"
                        
                        metric_cols[4].metric(
                            "Trend",
                            trend,
                            help="7-day moving average trend"
                        )
                    
                    # Additional insights
                    with st.expander("📈 Detailed Analysis", expanded=False):
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.markdown("**Index Interpretation:**")
                            st.markdown(f"""
                            - **Current: {latest['index_value']:.0f}/100** - {season_desc}
                            - **0-25**: Bitcoin Season (BTC outperforms most alts)
                            - **25-75**: Mixed/Transitional market
                            - **75-100**: Altcoin Season (alts outperform BTC)
                            """)
                        
                        with col_b:
                            st.markdown("**Historical Context:**")
                            if len(df_hist) > 1:
                                avg_30d = df_hist['index_value'].mean()
                                max_30d = df_hist['index_value'].max()
                                min_30d = df_hist['index_value'].min()
                                
                                st.markdown(f"""
                                - **30D Average**: {avg_30d:.1f}
                                - **30D High**: {max_30d:.1f}
                                - **30D Low**: {min_30d:.1f}
                                - **Volatility**: {max_30d - min_30d:.1f} points
                                """)
                
            else:
                st.warning("⚠️ No historical data available. Run: `python backfill_altcoin_season_history.py`")
        
        # Info
        st.caption("💾 **Data Source:** MongoDB altcoin_season_history + CSV backup. Updates daily at 1 AM UTC.")
    
    else:
        # === GAUGE VIEW (EXISTING) ===
        st.info("💡 **Gauge View:** So sánh performance 90 ngày của top 50 altcoin vs Bitcoin. Calculation takes 2-3 minutes due to API rate limits.")
        
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
