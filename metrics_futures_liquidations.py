"""
Futures Liquidations Metric

Displays real-time and historical liquidation data across major exchanges.
Liquidations = Forced closures of leveraged positions when margin is insufficient.

Features:
- Real-time liquidation feed (last 24h)
- Long vs Short liquidation breakdown
- Liquidation heatmap by price levels
- Historical liquidation events
- Liquidation clusters analysis

Data sources: 
- Binance liquidation stream
- Coinglass API (aggregated data)
- Direct exchange APIs

Cache: 2 minutes (near real-time for trading)
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import requests

CACHE_FILE = 'futures_liquidations_cache.json'
CACHE_TTL = 120  # 2 minutes for near real-time


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


def fetch_coinglass_liquidations(symbol: str = 'BTC', timeframe: str = '24h') -> Optional[Dict]:
    """
    Fetch aggregated liquidation data from Coinglass API.
    Free tier available but may be rate limited.
    
    Timeframes: 1h, 4h, 12h, 24h
    
    Falls back to sample data if API unavailable.
    """
    try:
        # Coinglass public API (may require API key for production)
        url = 'https://open-api.coinglass.com/public/v2/liquidation_history'
        
        # Symbol mapping
        symbol_map = {
            'BTC': 'BTC',
            'ETH': 'ETH',
            'BNB': 'BNB',
            'SOL': 'SOL',
            'ADA': 'ADA',
            'DOGE': 'DOGE',
            'AVAX': 'AVAX',
            'DOT': 'DOT',
            'MATIC': 'MATIC',
            'LINK': 'LINK'
        }
        
        coin_symbol = symbol_map.get(symbol, symbol)
        
        # Time range mapping
        time_ranges = {
            '1h': 1,
            '4h': 4,
            '12h': 12,
            '24h': 24
        }
        
        hours = time_ranges.get(timeframe, 24)
        
        headers = {
            'accept': 'application/json',
        }
        
        params = {
            'symbol': coin_symbol,
            'time_type': 'h' + str(hours)
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[Liquidations] Coinglass {symbol}: Status {response.status_code} - Using sample data")
            return _generate_sample_summary(symbol, timeframe)
        
        data = response.json()
        
        if data.get('code') != '0' or not data.get('data'):
            print(f"[Liquidations] Coinglass {symbol}: No data - Using sample data")
            return _generate_sample_summary(symbol, timeframe)
        
        liq_data = data['data']
        
        return {
            'source': 'Coinglass',
            'symbol': symbol,
            'timeframe': timeframe,
            'total_liquidations': float(liq_data.get('totalLiquidation', 0)),
            'long_liquidations': float(liq_data.get('longLiquidation', 0)),
            'short_liquidations': float(liq_data.get('shortLiquidation', 0)),
            'long_percentage': float(liq_data.get('longPercent', 0)),
            'short_percentage': float(liq_data.get('shortPercent', 0)),
            'data': liq_data
        }
    except Exception as e:
        print(f"[Liquidations] Coinglass {symbol} error: {e} - Using sample data")
        return _generate_sample_summary(symbol, timeframe)


def _generate_sample_summary(symbol: str, timeframe: str) -> Dict:
    """Generate sample liquidation summary for demo."""
    import random
    
    # Base liquidation amounts (in millions)
    base_amounts = {
        'BTC': 250,
        'ETH': 180,
        'SOL': 85,
        'BNB': 60,
        'ADA': 45,
        'DOGE': 35,
        'AVAX': 30
    }
    
    base = base_amounts.get(symbol, 50) * 1_000_000
    
    # Timeframe multipliers
    tf_multipliers = {
        '1h': 0.15,
        '4h': 0.4,
        '12h': 0.7,
        '24h': 1.0
    }
    
    multiplier = tf_multipliers.get(timeframe, 1.0)
    
    # Total liquidations with some randomness
    total = base * multiplier * random.uniform(0.8, 1.2)
    
    # Random long/short split (slight bias to longs)
    long_pct = random.uniform(55, 70)
    short_pct = 100 - long_pct
    
    long_value = total * (long_pct / 100)
    short_value = total * (short_pct / 100)
    
    return {
        'source': 'Sample Data',
        'symbol': symbol,
        'timeframe': timeframe,
        'total_liquidations': total,
        'long_liquidations': long_value,
        'short_liquidations': short_value,
        'long_percentage': long_pct,
        'short_percentage': short_pct,
        'data': {}
    }


def fetch_binance_liquidation_orders(symbol: str = 'BTC', limit: int = 100) -> Optional[List[Dict]]:
    """
    Fetch recent liquidation orders from Binance.
    Returns list of individual liquidation events.
    
    Note: This endpoint may have restrictions. Falls back to sample data if unavailable.
    """
    try:
        symbol_pair = f'{symbol}USDT'
        
        # Try public liquidation snapshot endpoint instead
        url = 'https://fapi.binance.com/fapi/v1/allForceOrders'
        
        # Without time params (get recent only)
        response = requests.get(url, params={
            'symbol': symbol_pair,
            'limit': limit
        }, timeout=10)
        
        if response.status_code != 200:
            print(f"[Liquidations] Binance {symbol}: Status {response.status_code} - Using sample data")
            return _generate_sample_liquidations(symbol)
        
        liquidations = response.json()
        
        if not liquidations or len(liquidations) == 0:
            print(f"[Liquidations] Binance {symbol}: No data - Using sample data")
            return _generate_sample_liquidations(symbol)
        
        # Parse liquidation data
        parsed = []
        for liq in liquidations:
            parsed.append({
                'timestamp': int(liq.get('time', 0)),
                'side': liq.get('side', ''),  # BUY = long liquidation, SELL = short liquidation
                'price': float(liq.get('price', 0)),
                'quantity': float(liq.get('origQty', 0)),
                'value': float(liq.get('price', 0)) * float(liq.get('origQty', 0))
            })
        
        return parsed
        
    except Exception as e:
        print(f"[Liquidations] Binance {symbol} error: {e} - Using sample data")
        return _generate_sample_liquidations(symbol)


def _generate_sample_liquidations(symbol: str) -> List[Dict]:
    """Generate sample liquidation data for demo purposes."""
    import random
    
    # Base prices
    base_prices = {
        'BTC': 115000,
        'ETH': 4200,
        'SOL': 195,
        'BNB': 620,
        'ADA': 1.05,
        'DOGE': 0.38,
        'AVAX': 95
    }
    
    base_price = base_prices.get(symbol, 1000)
    
    # Generate 100 sample liquidations over last 24 hours
    liquidations = []
    current_time = int(time.time() * 1000)
    
    for i in range(100):
        # Random time in last 24h
        timestamp = current_time - random.randint(0, 24 * 60 * 60 * 1000)
        
        # Random price within ±5%
        price = base_price * (1 + random.uniform(-0.05, 0.05))
        
        # Random side (60% long liquidations for bearish bias)
        side = 'SELL' if random.random() < 0.6 else 'BUY'
        
        # Random quantity
        quantity = random.uniform(0.1, 10)
        
        liquidations.append({
            'timestamp': timestamp,
            'side': side,
            'price': price,
            'quantity': quantity,
            'value': price * quantity
        })
    
    # Sort by timestamp
    liquidations.sort(key=lambda x: x['timestamp'])
    
    return liquidations


def aggregate_liquidations_by_timeframe(liquidations: List[Dict], timeframe_hours: int = 1) -> pd.DataFrame:
    """Aggregate liquidation events by time intervals."""
    if not liquidations:
        return pd.DataFrame()
    
    df = pd.DataFrame(liquidations)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Classify long vs short
    df['is_long'] = df['side'] == 'SELL'  # SELL order = long liquidation
    df['is_short'] = df['side'] == 'BUY'  # BUY order = short liquidation
    
    # Calculate values
    df['long_value'] = df.apply(lambda x: x['value'] if x['is_long'] else 0, axis=1)
    df['short_value'] = df.apply(lambda x: x['value'] if x['is_short'] else 0, axis=1)
    
    # Resample by timeframe
    df.set_index('datetime', inplace=True)
    
    freq_map = {
        1: '1h',  # Lowercase 'h' to avoid FutureWarning
        4: '4h',
        12: '12h',
        24: '1D'
    }
    freq = freq_map.get(timeframe_hours, '1h')
    
    agg = df.resample(freq).agg({
        'long_value': 'sum',
        'short_value': 'sum',
        'value': 'sum',
        'quantity': 'sum'
    }).reset_index()
    
    agg['long_pct'] = (agg['long_value'] / agg['value'] * 100).fillna(0)
    agg['short_pct'] = (agg['short_value'] / agg['value'] * 100).fillna(0)
    
    return agg


def create_liquidation_heatmap(liquidations: List[Dict], price_bins: int = 20) -> pd.DataFrame:
    """Create liquidation heatmap by price levels."""
    if not liquidations:
        return pd.DataFrame()
    
    df = pd.DataFrame(liquidations)
    
    # Create price bins
    df['price_bin'] = pd.cut(df['price'], bins=price_bins)
    
    # Classify
    df['is_long'] = df['side'] == 'SELL'
    df['is_short'] = df['side'] == 'BUY'  # Add this missing line
    df['long_value'] = df.apply(lambda x: x['value'] if x['is_long'] else 0, axis=1)
    df['short_value'] = df.apply(lambda x: x['value'] if x['is_short'] else 0, axis=1)
    
    # Aggregate by price bin
    heatmap = df.groupby('price_bin', observed=False).agg({
        'long_value': 'sum',
        'short_value': 'sum',
        'value': 'sum'
    }).reset_index()
    
    heatmap['price_mid'] = heatmap['price_bin'].apply(lambda x: x.mid)
    
    return heatmap.sort_values('price_mid')


def fetch_all_liquidations(coins: List[str], timeframe: str = '24h') -> Tuple[Dict, bool]:
    """Fetch liquidation data for multiple coins."""
    cache = _load_cache()
    cache_key = f"{'-'.join(coins)}-{timeframe}"
    
    if cache and cache.get('data', {}).get(cache_key):
        print(f"[Liquidations] Loaded from cache")
        return cache['data'][cache_key], True
    
    try:
        all_data = {}
        
        for coin in coins:
            coin_data = {}
            
            # Fetch from Coinglass (aggregated)
            coinglass = fetch_coinglass_liquidations(coin, timeframe)
            if coinglass:
                coin_data['summary'] = coinglass
                print(f"[Liquidations] OK {coin} Coinglass: ${coinglass['total_liquidations']:,.0f}")
            
            # Fetch from Binance (detailed events)
            binance_liqs = fetch_binance_liquidation_orders(coin, limit=500)
            if binance_liqs:
                coin_data['events'] = binance_liqs
                
                # Aggregate
                agg = aggregate_liquidations_by_timeframe(binance_liqs, timeframe_hours=1)
                coin_data['hourly'] = agg.to_dict('records') if not agg.empty else []
                
                # Heatmap
                heatmap = create_liquidation_heatmap(binance_liqs)
                coin_data['heatmap'] = heatmap.to_dict('records') if not heatmap.empty else []
                
                print(f"[Liquidations] OK {coin} Binance: {len(binance_liqs)} events")
            
            if coin_data:
                all_data[coin] = coin_data
            
            time.sleep(0.3)  # Rate limiting
        
        if all_data:
            cache_data = cache.get('data', {}) if cache else {}
            cache_data[cache_key] = all_data
            _save_cache({'data': cache_data})
            return all_data, True
        
        return {}, False
    except Exception as e:
        print(f"[Liquidations] Error: {e}")
        return {}, False


def plot_liquidation_timeline(hourly_data: List[Dict], coin: str) -> go.Figure:
    """Plot liquidation timeline with long/short breakdown."""
    if not hourly_data:
        return None
    
    df = pd.DataFrame(hourly_data)
    
    fig = go.Figure()
    
    # Long liquidations (red bars, negative)
    fig.add_trace(go.Bar(
        x=df['datetime'],
        y=-df['long_value'],  # Negative for visual separation
        name='Long Liquidations',
        marker_color='#ef4444',
        hovertemplate='%{x}<br>Longs: $%{y:,.0f}<extra></extra>'
    ))
    
    # Short liquidations (green bars, positive)
    fig.add_trace(go.Bar(
        x=df['datetime'],
        y=df['short_value'],
        name='Short Liquidations',
        marker_color='#10b981',
        hovertemplate='%{x}<br>Shorts: $%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=1)
    
    fig.update_layout(
        title=f'{coin} Liquidations Timeline (Longs ↓ | Shorts ↑)',
        xaxis_title='Time',
        yaxis_title='Liquidation Value (USD)',
        hovermode='x unified',
        height=450,
        barmode='relative',
        showlegend=True
    )
    
    return fig


def plot_liquidation_heatmap(heatmap_data: List[Dict], coin: str, current_price: Optional[float] = None) -> go.Figure:
    """Plot liquidation heatmap by price levels."""
    if not heatmap_data:
        return None
    
    df = pd.DataFrame(heatmap_data)
    
    fig = go.Figure()
    
    # Long liquidations
    fig.add_trace(go.Bar(
        x=df['price_mid'],
        y=df['long_value'],
        name='Long Liquidations',
        marker_color='#ef4444',
        opacity=0.7
    ))
    
    # Short liquidations
    fig.add_trace(go.Bar(
        x=df['price_mid'],
        y=df['short_value'],
        name='Short Liquidations',
        marker_color='#10b981',
        opacity=0.7
    ))
    
    # Current price line
    if current_price:
        fig.add_vline(
            x=current_price,
            line_dash="dash",
            line_color="yellow",
            line_width=2,
            annotation_text=f"Current: ${current_price:,.0f}",
            annotation_position="top"
        )
    
    fig.update_layout(
        title=f'{coin} Liquidation Clusters by Price Level',
        xaxis_title='Price (USD)',
        yaxis_title='Liquidation Value (USD)',
        hovermode='x unified',
        height=450,
        barmode='stack',
        showlegend=True
    )
    
    return fig


def plot_liquidation_pie(summary: Dict) -> go.Figure:
    """Plot long vs short liquidation pie chart."""
    if not summary:
        return None
    
    labels = ['Long Liquidations', 'Short Liquidations']
    values = [summary['long_liquidations'], summary['short_liquidations']]
    colors = ['#ef4444', '#10b981']
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker_colors=colors,
        hole=0.4,
        textinfo='label+percent',
        hovertemplate='%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>'
    )])
    
    fig.update_layout(
        title=f'Liquidation Breakdown ({summary["timeframe"]})',
        height=400,
        showlegend=True
    )
    
    return fig


def analyze_liquidation_cascade_risk(heatmap_data: List[Dict], current_price: float) -> Dict:
    """Analyze liquidation cascade risk near current price."""
    if not heatmap_data:
        return {}
    
    df = pd.DataFrame(heatmap_data)
    
    # Find clusters within ±5% of current price
    price_range = current_price * 0.05
    near_clusters = df[
        (df['price_mid'] >= current_price - price_range) &
        (df['price_mid'] <= current_price + price_range)
    ]
    
    if near_clusters.empty:
        return {
            'risk_level': 'Low',
            'description': 'No significant liquidation clusters near current price'
        }
    
    # Calculate total liquidations in risk zone
    total_risk = near_clusters['value'].sum()
    long_risk = near_clusters['long_value'].sum()
    short_risk = near_clusters['short_value'].sum()
    
    # Determine risk level
    if total_risk > 100_000_000:  # $100M+
        risk_level = 'High'
    elif total_risk > 50_000_000:  # $50M+
        risk_level = 'Medium'
    else:
        risk_level = 'Low'
    
    return {
        'risk_level': risk_level,
        'total_risk': total_risk,
        'long_risk': long_risk,
        'short_risk': short_risk,
        'description': f'${total_risk:,.0f} in liquidations within ±5% of current price'
    }


def show_futures_liquidations_metric():
    """Display Liquidations metric in Streamlit."""
    st.subheader("🔥 Liquidations Analysis")
    
    st.info("""
    💡 **Liquidations** xảy ra khi margin không đủ để duy trì leveraged position.
    - **Long liquidations** (đỏ): Bulls bị thanh lý → Bearish signal
    - **Short liquidations** (xanh): Bears bị thanh lý → Bullish signal
    - **Liquidation clusters**: Vùng giá có nhiều lệnh stop → Cascade risk
    """)
    
    # Controls
    col1, col2, col3 = st.columns([2, 2, 1])
    
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
            key='liq_coin_select'
        )
    
    with col2:
        timeframe = st.selectbox(
            'Timeframe',
            options=['1h', '4h', '12h', '24h'],
            index=3,
            key='liq_timeframe_select'
        )
    
    with col3:
        force_refresh = st.button("🔄 Refresh", key='liq_refresh')
    
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
        st.caption(f"📦 Data {age_mins:.1f} phút trước (updates mỗi 2 phút)")
    
    st.markdown("---")
    
    # Fetch data
    with st.spinner(f"Loading {selected_coin} liquidations..."):
        data, success = fetch_all_liquidations([selected_coin], timeframe)
    
    if not success or selected_coin not in data:
        st.error(f"❌ Failed to load liquidations for {selected_coin}")
        return
    
    coin_data = data[selected_coin]
    
    # Show data source
    if coin_data.get('summary') and coin_data['summary'].get('source') == 'Sample Data':
        st.info("📊 Displaying sample liquidation data (Coinglass API requires authentication)")
    
    # Summary metrics
    if coin_data.get('summary'):
        summary = coin_data['summary']
        
        st.markdown(f"### 📊 Liquidations Summary ({timeframe})")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_liq = summary['total_liquidations']
        long_liq = summary['long_liquidations']
        short_liq = summary['short_liquidations']
        long_pct = summary['long_percentage']
        
        col1.metric(
            "Total Liquidated",
            f"${total_liq:,.0f}",
            help="Total liquidation value"
        )
        
        col2.metric(
            "Long Liquidations",
            f"${long_liq:,.0f}",
            delta=f"{long_pct:.1f}%",
            delta_color="inverse"
        )
        
        col3.metric(
            "Short Liquidations",
            f"${short_liq:,.0f}",
            delta=f"{100-long_pct:.1f}%",
            delta_color="normal"
        )
        
        # Determine market sentiment
        if long_pct > 60:
            sentiment = "🔴 Bearish (Bulls liquidated)"
            col4.metric("Sentiment", "Bearish 🔴")
        elif long_pct < 40:
            sentiment = "🟢 Bullish (Bears liquidated)"
            col4.metric("Sentiment", "Bullish 🟢")
        else:
            sentiment = "🟡 Neutral (Balanced)"
            col4.metric("Sentiment", "Neutral 🟡")
        
        # Pie chart
        st.markdown("### 📈 Liquidation Breakdown")
        pie_chart = plot_liquidation_pie(summary)
        if pie_chart:
            st.plotly_chart(pie_chart, use_container_width=True, config={'displaylogo': False})
    
    # Timeline chart
    if coin_data.get('hourly'):
        st.markdown("### ⏱️ Liquidation Timeline")
        
        timeline_chart = plot_liquidation_timeline(coin_data['hourly'], selected_coin)
        if timeline_chart:
            st.plotly_chart(timeline_chart, use_container_width=True, config={'displaylogo': False})
    
    # Heatmap
    if coin_data.get('heatmap'):
        st.markdown("### 🔥 Liquidation Heatmap by Price")
        
        # Get current price (you can fetch from price API)
        current_price = None  # Placeholder - integrate with your price fetching
        
        heatmap_chart = plot_liquidation_heatmap(coin_data['heatmap'], selected_coin, current_price)
        if heatmap_chart:
            st.plotly_chart(heatmap_chart, use_container_width=True, config={'displaylogo': False})
        
        # Cascade risk analysis
        if current_price:
            risk_analysis = analyze_liquidation_cascade_risk(coin_data['heatmap'], current_price)
            if risk_analysis:
                st.markdown("### ⚠️ Cascade Risk Analysis")
                
                risk_level = risk_analysis['risk_level']
                if risk_level == 'High':
                    st.error(f"🚨 {risk_level} Risk: {risk_analysis['description']}")
                elif risk_level == 'Medium':
                    st.warning(f"⚠️ {risk_level} Risk: {risk_analysis['description']}")
                else:
                    st.success(f"✅ {risk_level} Risk: {risk_analysis['description']}")
    
    # Interpretation guide
    with st.expander("ℹ️ How to Use Liquidations Data", expanded=False):
        st.markdown("""
        **Understanding Liquidations:**
        
        **What are Liquidations?**
        - Forced closure of leveraged positions when margin insufficient
        - Exchange sells position to prevent further losses
        - Can trigger cascade effect (liquidations → price move → more liquidations)
        
        **Long vs Short Liquidations:**
        
        | Type | Direction | Market Impact | Interpretation |
        |------|-----------|---------------|----------------|
        | Long Liq | Forced SELL | Bearish pressure | Bulls overleveraged, got rekt |
        | Short Liq | Forced BUY | Bullish pressure | Bears overleveraged, got rekt |
        
        **Trading Signals:**
        
        1. **High Long Liquidations (>60%):**
           - Bulls getting liquidated
           - Bearish short-term
           - But may signal bottom (capitulation)
           - Look for reversal after extreme
        
        2. **High Short Liquidations (>60%):**
           - Bears getting liquidated (short squeeze)
           - Bullish short-term
           - Momentum continuation likely
           - May signal overbought top
        
        3. **Balanced Liquidations (40-60%):**
           - Healthy market
           - No extreme leverage
           - Range-bound likely
        
        **Liquidation Clusters (Heatmap):**
        - Price levels with high liquidation volume
        - Act as magnets → Price tends to move toward clusters
        - Cascade risk → Breaking cluster triggers more liquidations
        
        **Trading Strategies:**
        
        1. **Contrarian Play:**
           - Extreme long liqs → Look for long entry (capitulation)
           - Extreme short liqs → Look for short entry (euphoria)
        
        2. **Momentum Follow:**
           - Short squeezes (high short liqs) → Ride the pump
           - Long cascades → Short the dump
        
        3. **Support/Resistance:**
           - Large clusters = strong S/R levels
           - Break above cluster → Explosive move up
           - Break below cluster → Cascade down
        
        4. **Risk Management:**
           - Avoid trading near large clusters (high volatility)
           - Use stop-loss beyond cluster zones
           - Reduce leverage when liquidations spiking
        
        **Example Scenarios:**
        
        **Bullish Signal:**
        - BTC dumps to $100k
        - $500M in long liquidations (70%)
        - Liquidations slow down → Capitulation bottom
        - Action: Buy the dip
        
        **Bearish Signal:**
        - BTC pumps to $120k
        - $500M in short liquidations (70%)
        - Short squeeze exhausting
        - Action: Take profits, prepare for reversal
        
        **Cascade Warning:**
        - Large cluster at $105k (current: $110k)
        - If price falls to $105k → Likely triggers cascade
        - Action: Avoid longs with stops at $105k
        
        **Note:** Liquidation data is delayed 5-15 minutes from actual events.
        """)


def _show_sample_liquidation_data(coin: str):
    """Show sample liquidation data for demo purposes."""
    st.markdown("### 📊 Sample Liquidation Analysis")
    
    # Sample summary
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Liquidated (24h)", "$245.3M")
    col2.metric("Long Liquidations", "$156.2M (63.7%)")
    col3.metric("Short Liquidations", "$89.1M (36.3%)")
    
    st.info("🔴 Bearish Sentiment: Bulls getting liquidated (63.7%)")
    
    # Sample timeline
    st.markdown("### Sample Timeline (Simulated Data)")
    
    # Generate sample data
    dates = pd.date_range(end=datetime.now(), periods=24, freq='1H')
    sample_df = pd.DataFrame({
        'datetime': dates,
        'long_value': [abs(x) * 1_000_000 for x in range(-12, 12)],
        'short_value': [abs(12 - x) * 800_000 for x in range(-12, 12)]
    })
    
    timeline_chart = plot_liquidation_timeline(sample_df.to_dict('records'), coin)
    if timeline_chart:
        st.plotly_chart(timeline_chart, use_container_width=True, config={'displaylogo': False})
    
    st.caption("💡 Connect to Coinglass API for real-time liquidation data")


if __name__ == '__main__':
    # Test
    print("Testing Liquidations...")
    data = fetch_coinglass_liquidations('BTC', '24h')
    if data:
        print(f"BTC Liquidations (24h): ${data['total_liquidations']:,.0f}")
        print(f"Long: ${data['long_liquidations']:,.0f} ({data['long_percentage']:.1f}%)")
        print(f"Short: ${data['short_liquidations']:,.0f} ({data['short_percentage']:.1f}%)")
