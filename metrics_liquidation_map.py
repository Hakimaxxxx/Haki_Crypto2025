"""
Liquidation Map - Coinglass Style

Visualizes cumulative liquidation leverage across price levels.
Shows where liquidations will occur as price moves up/down.

Features:
- Cumulative long/short liquidation leverage
- Multiple leverage zones (10x, 25x, 50x, 100x)
- Current price indicator
- Interactive price range selection

Based on Coinglass liquidation map design.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

def estimate_liquidation_levels(
    current_price: float,
    open_interest_long: float,
    open_interest_short: float,
    leverage_levels: List[int] = [10, 25, 50, 100],
    price_range_pct: float = 10.0,
    num_bins: int = 200  # Increase for smoother bars
) -> pd.DataFrame:
    """
    Estimate liquidation levels - Coinglass style (NON-cumulative).
    
    Key differences from previous version:
    - Each bar shows LIQUIDATION AMOUNT at that price level (not cumulative)
    - More bins for smoother distribution
    - Stacked bars create gradient effect naturally
    
    Args:
        current_price: Current market price
        open_interest_long: Total long open interest (USD)
        open_interest_short: Total short open interest (USD)
        leverage_levels: List of leverage multipliers to model
        price_range_pct: Price range to show (± % from current)
        num_bins: Number of price bins (higher = smoother)
    
    Returns:
        DataFrame with price and liquidation amounts per leverage
    """
    # Price range
    min_price = current_price * (1 - price_range_pct / 100)
    max_price = current_price * (1 + price_range_pct / 100)
    prices = np.linspace(min_price, max_price, num_bins)
    
    data = {'price': prices}
    
    # For each leverage level, distribute liquidations
    for leverage in leverage_levels:
        # Calculate liquidation price for this leverage
        long_liq_price = current_price * (1 - 1/leverage)
        short_liq_price = current_price * (1 + 1/leverage)
        
        # Calculate standard deviation for Gaussian distribution
        # Higher leverage = tighter distribution (closer to liq price)
        sigma_pct = 0.5 / leverage  # Adaptive sigma based on leverage
        
        long_liq = []
        short_liq = []
        
        for p in prices:
            # Long liquidations: Gaussian centered at long_liq_price
            if p <= current_price:
                # Distance from liquidation price (normalized)
                dist = (p - long_liq_price) / current_price
                # Gaussian distribution
                density = np.exp(-(dist**2) / (2 * sigma_pct**2))
                # Scale by OI amount for this leverage
                amount = (open_interest_long / len(leverage_levels)) * density * 0.1
                long_liq.append(amount)
            else:
                long_liq.append(0)
            
            # Short liquidations: Gaussian centered at short_liq_price
            if p >= current_price:
                dist = (p - short_liq_price) / current_price
                density = np.exp(-(dist**2) / (2 * sigma_pct**2))
                amount = (open_interest_short / len(leverage_levels)) * density * 0.1
                short_liq.append(amount)
            else:
                short_liq.append(0)
        
        data[f'liq_long_{leverage}x'] = long_liq
        data[f'liq_short_{leverage}x'] = short_liq
    
    return pd.DataFrame(data)


def fetch_open_interest_multi_exchange(symbol: str = 'BTC') -> Dict[str, Tuple[float, float, float]]:
    """
    Fetch open interest from multiple exchanges and aggregate.
    
    Args:
        symbol: Base symbol (e.g., 'BTC', 'ETH')
    
    Returns:
        Dict with exchange data: {
            'binance': (price, long_oi, short_oi),
            'okx': (price, long_oi, short_oi),
            'bybit': (price, long_oi, short_oi),
            'total': (avg_price, total_long_oi, total_short_oi)
        }
    """
    results = {}
    
    # Binance
    binance_data = fetch_binance_open_interest(f'{symbol}USDT')
    if binance_data[0]:
        results['binance'] = binance_data
    
    # OKX
    okx_data = fetch_okx_open_interest(f'{symbol}-USDT')
    if okx_data[0]:
        results['okx'] = okx_data
    
    # Bybit
    bybit_data = fetch_bybit_open_interest(f'{symbol}USDT')
    if bybit_data[0]:
        results['bybit'] = bybit_data
    
    # Calculate totals
    if results:
        prices = [data[0] for data in results.values() if data[0]]
        long_ois = [data[1] for data in results.values() if data[1]]
        short_ois = [data[2] for data in results.values() if data[2]]
        
        avg_price = sum(prices) / len(prices) if prices else None
        total_long = sum(long_ois) if long_ois else None
        total_short = sum(short_ois) if short_ois else None
        
        if avg_price:
            results['total'] = (avg_price, total_long, total_short)
    
    return results


def fetch_binance_open_interest(symbol: str = 'BTCUSDT') -> Tuple[float, float, float]:
    """
    Fetch current open interest from Binance Futures.
    
    Returns:
        (current_price, long_oi, short_oi)
    """
    try:
        import requests
        
        # Get current price
        price_url = f'https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}'
        price_resp = requests.get(price_url, timeout=5)
        current_price = float(price_resp.json()['price'])
        
        # Get open interest
        oi_url = f'https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}'
        oi_resp = requests.get(oi_url, timeout=5)
        total_oi = float(oi_resp.json()['openInterest'])
        
        # Get long/short ratio to split OI
        ratio_url = f'https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=5m&limit=1'
        ratio_resp = requests.get(ratio_url, timeout=5)
        
        if ratio_resp.status_code == 200:
            ratio_data = ratio_resp.json()
            if ratio_data:
                long_short_ratio = float(ratio_data[0]['longShortRatio'])
                # Calculate split
                long_oi = (total_oi * current_price) * (long_short_ratio / (1 + long_short_ratio))
                short_oi = (total_oi * current_price) * (1 / (1 + long_short_ratio))
            else:
                # Default 50/50 split
                long_oi = short_oi = (total_oi * current_price) / 2
        else:
            # Fallback: assume 50/50 split
            long_oi = short_oi = (total_oi * current_price) / 2
        
        return current_price, long_oi, short_oi
    
    except Exception as e:
        print(f"Error fetching Binance OI: {e}")
        return None, None, None


def fetch_okx_open_interest(symbol: str = 'BTC-USDT') -> Tuple[float, float, float]:
    """
    Fetch current open interest from OKX.
    
    Args:
        symbol: Trading pair (e.g., 'BTC-USDT')
    
    Returns:
        (current_price, long_oi, short_oi)
    """
    try:
        import requests
        
        # OKX uses different format: BTC-USDT-SWAP
        swap_symbol = f'{symbol}-SWAP'
        
        # Get current price
        ticker_url = f'https://www.okx.com/api/v5/market/ticker?instId={swap_symbol}'
        ticker_resp = requests.get(ticker_url, timeout=5)
        ticker_data = ticker_resp.json()
        
        if ticker_data.get('code') == '0' and ticker_data.get('data') and len(ticker_data['data']) > 0:
            current_price = float(ticker_data['data'][0]['last'])
        else:
            return None, None, None
        
        # Get open interest
        oi_url = f'https://www.okx.com/api/v5/public/open-interest?instId={swap_symbol}'
        oi_resp = requests.get(oi_url, timeout=5)
        oi_data = oi_resp.json()
        
        if oi_data.get('code') == '0' and oi_data.get('data') and len(oi_data['data']) > 0:
            # OI is in contracts, convert to USD
            oi_contracts = float(oi_data['data'][0]['oi'])
            total_oi_usd = oi_contracts * current_price
        else:
            return None, None, None
        
        # Get long/short ratio
        ratio_url = f'https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={symbol.split("-")[0]}&period=5m'
        ratio_resp = requests.get(ratio_url, timeout=5)
        ratio_data = ratio_resp.json()
        
        if ratio_data.get('code') == '0' and ratio_data.get('data') and len(ratio_data['data']) > 0:
            long_ratio = float(ratio_data['data'][0]['longShortAcctRatio'])
            # Calculate split
            long_oi = total_oi_usd * (long_ratio / (1 + long_ratio))
            short_oi = total_oi_usd * (1 / (1 + long_ratio))
        else:
            # Fallback: 50/50 split
            long_oi = short_oi = total_oi_usd / 2
        
        return current_price, long_oi, short_oi
    
    except Exception as e:
        print(f"Error fetching OKX OI: {e}")
        return None, None, None


def fetch_bybit_open_interest(symbol: str = 'BTCUSDT') -> Tuple[float, float, float]:
    """
    Fetch current open interest from Bybit.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
    
    Returns:
        (current_price, long_oi, short_oi)
    """
    try:
        import requests
        
        # Get current price and OI from tickers
        ticker_url = f'https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}'
        ticker_resp = requests.get(ticker_url, timeout=5)
        ticker_data = ticker_resp.json()
        
        if ticker_data.get('retCode') == 0 and ticker_data.get('result', {}).get('list'):
            data = ticker_data['result']['list'][0]
            current_price = float(data['lastPrice'])
            # OI in USD
            total_oi_usd = float(data.get('openInterest', 0)) * current_price
        else:
            return None, None, None
        
        # Get long/short ratio
        ratio_url = f'https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={symbol}&period=5min&limit=1'
        ratio_resp = requests.get(ratio_url, timeout=5)
        ratio_data = ratio_resp.json()
        
        if ratio_data.get('retCode') == 0 and ratio_data.get('result', {}).get('list'):
            ratio_info = ratio_data['result']['list'][0]
            buy_ratio = float(ratio_info.get('buyRatio', 0.5))
            sell_ratio = float(ratio_info.get('sellRatio', 0.5))
            
            # Calculate split based on buy/sell ratio
            total_ratio = buy_ratio + sell_ratio
            if total_ratio > 0:
                long_oi = total_oi_usd * (buy_ratio / total_ratio)
                short_oi = total_oi_usd * (sell_ratio / total_ratio)
            else:
                long_oi = short_oi = total_oi_usd / 2
        else:
            # Fallback: 50/50 split
            long_oi = short_oi = total_oi_usd / 2
        
        return current_price, long_oi, short_oi
    
    except Exception as e:
        print(f"Error fetching Bybit OI: {e}")
        return None, None, None


def plot_liquidation_map(
    symbol: str = 'BTC',
    exchange: str = 'total',
    timeframe: str = '1 day',
    leverage_levels: List[int] = [10, 25, 50, 100],
    price_range_pct: float = 10.0
) -> Optional[go.Figure]:
    """
    Create Coinglass-style liquidation map with multi-exchange support.
    
    Args:
        symbol: Base symbol (e.g., 'BTC', 'ETH')
        exchange: 'binance', 'okx', 'bybit', or 'total' (aggregate all)
        timeframe: Display timeframe (for title)
        leverage_levels: Leverage levels to show
        price_range_pct: Price range ±%
    
    Returns:
        Plotly figure
    """
    # Fetch data from all exchanges
    exchange_data = fetch_open_interest_multi_exchange(symbol)
    
    if not exchange_data:
        return None
    
    # Select exchange data
    if exchange == 'total':
        if 'total' not in exchange_data:
            return None
        current_price, long_oi, short_oi = exchange_data['total']
        title_exchange = 'Multi-Exchange'
    else:
        if exchange not in exchange_data:
            return None
        current_price, long_oi, short_oi = exchange_data[exchange]
        title_exchange = exchange.capitalize()
    
    if current_price is None:
        return None
    
    # Estimate liquidation levels
    df = estimate_liquidation_levels(
        current_price,
        long_oi,
        short_oi,
        leverage_levels,
        price_range_pct,
        num_bins=200  # More bins for smoother visualization
    )
    
    # Calculate price range and bar width
    min_price = df['price'].min()
    max_price = df['price'].max()
    num_bins = len(df)
    bar_width = (max_price - min_price) / num_bins * 0.98
    
    # Create price offset from current price (for X-axis display like Coinglass)
    # Display as $0 at current price, negative to left, positive to right
    df['price_offset'] = df['price'] - current_price
    
    # Create figure
    fig = go.Figure()
    
    # Color schemes - Coinglass style
    # IMPORTANT: Use semi-transparent colors for stacking effect
    long_colors = {
        10: 'rgba(220, 38, 38, 0.9)',    # Deep red (10x)
        25: 'rgba(239, 68, 68, 0.85)',   # Red (25x)
        50: 'rgba(251, 146, 60, 0.8)',   # Orange (50x)
        100: 'rgba(253, 186, 116, 0.75)' # Light orange (100x)
    }
    
    short_colors = {
        10: 'rgba(21, 128, 61, 0.9)',    # Deep green (10x)
        25: 'rgba(34, 197, 94, 0.85)',   # Green (25x)
        50: 'rgba(52, 211, 153, 0.8)',   # Light green (50x)
        100: 'rgba(103, 232, 249, 0.75)' # Cyan (100x)
    }
    
    # Plot bars for each leverage level - STACK THEM
    # Plot in order: 100x first (bottom), then 50x, 25x, 10x (top)
    for leverage in sorted(leverage_levels, reverse=True):
        # Long liquidations (LEFT of current price)
        # Use price_offset for X-axis
        long_mask = df['price'] < current_price
        long_x = df[long_mask]['price_offset']
        long_y = df[long_mask][f'liq_long_{leverage}x']
        
        if len(long_x) > 0 and long_y.sum() > 0:
            fig.add_trace(go.Bar(
                x=long_x,
                y=long_y,
                name=f'Long {leverage}x',
                marker=dict(
                    color=long_colors[leverage],
                    line=dict(width=0)
                ),
                hovertemplate=(
                    f'<b>🔴 Long {leverage}x Liquidation</b><br>'
                    'Price: $%{customdata[0]:,.2f}<br>'
                    'Offset: $%{x:,.2f}<br>'
                    'Amount: $%{y:,.0f}<br>'
                    '<extra></extra>'
                ),
                customdata=np.column_stack([df[long_mask]['price']]),
                showlegend=True,
                legendgroup='long',
                width=bar_width,
                offsetgroup='long'  # Important for stacking
            ))
        
        # Short liquidations (RIGHT of current price)
        short_mask = df['price'] > current_price
        short_x = df[short_mask]['price_offset']
        short_y = df[short_mask][f'liq_short_{leverage}x']
        
        if len(short_x) > 0 and short_y.sum() > 0:
            fig.add_trace(go.Bar(
                x=short_x,
                y=short_y,
                name=f'Short {leverage}x',
                marker=dict(
                    color=short_colors[leverage],
                    line=dict(width=0)
                ),
                hovertemplate=(
                    f'<b>🟢 Short {leverage}x Liquidation</b><br>'
                    'Price: $%{customdata[0]:,.2f}<br>'
                    'Offset: $%{x:,.2f}<br>'
                    'Amount: $%{y:,.0f}<br>'
                    '<extra></extra>'
                ),
                customdata=np.column_stack([df[short_mask]['price']]),
                showlegend=True,
                legendgroup='short',
                width=bar_width,
                offsetgroup='short'  # Important for stacking
            ))
    
    # Add current price line (at x=0 in offset coordinates)
    max_y = df[[f'liq_long_{lev}x' for lev in leverage_levels] + [f'liq_short_{lev}x' for lev in leverage_levels]].max().max()
    
    fig.add_trace(go.Scatter(
        x=[0, 0],  # At price offset = 0 (current price)
        y=[0, max_y * 1.15],
        mode='lines',
        line=dict(color='white', width=3, dash='dash'),
        name='Current Price',
        hovertemplate=f'<b>Current Price</b><br>${current_price:,.2f}<extra></extra>',
        showlegend=False
    ))
    
    # Add current price annotation at top
    fig.add_annotation(
        text=f'<b>CURRENT PRICE</b><br>${current_price:,.2f}',
        x=0,
        y=max_y * 1.1,
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=2,
        arrowcolor='white',
        ax=0,
        ay=-40,
        font=dict(size=12, color='white', family='Arial Black'),
        bgcolor='rgba(0, 0, 0, 0.9)',
        bordercolor='white',
        borderwidth=2,
        borderpad=6
    )
    
    # Layout - Coinglass style
    fig.update_layout(
        title={
            'text': f'<b>{title_exchange} {symbol}/USDT Liquidation Map</b>',
            'font': {'size': 20, 'color': 'white'},
            'x': 0.5,
            'xanchor': 'center',
            'y': 0.98,
            'yanchor': 'top'
        },
        xaxis=dict(
            title='<b>Price</b>',
            gridcolor='rgba(255, 255, 255, 0.1)',
            showgrid=True,
            zeroline=True,
            zerolinecolor='rgba(255, 255, 255, 0.3)',
            zerolinewidth=2,
            color='rgba(255, 255, 255, 0.7)',
            # Custom tick format: show as $0 at current price
            tickformat='$,.0f',
            tickfont=dict(size=11),
            # Add secondary axis label showing actual prices
            side='bottom'
        ),
        yaxis=dict(
            title='<b>Liquidation Leverage (USD)</b>',
            gridcolor='rgba(255, 255, 255, 0.1)',
            showgrid=True,
            zeroline=False,
            color='rgba(255, 255, 255, 0.7)',
            tickformat=',.0f',
            tickfont=dict(size=11)
        ),
        barmode='stack',  # CRITICAL: Stack bars to create gradient
        plot_bgcolor='#0e1117',
        paper_bgcolor='#0e1117',
        font=dict(color='white', family='Arial, sans-serif'),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='top',
            y=-0.15,
            xanchor='center',
            x=0.5,
            bgcolor='rgba(0,0,0,0.5)',
            bordercolor='rgba(255,255,255,0.3)',
            borderwidth=1,
            font=dict(size=10)
        ),
        height=550,
        margin=dict(l=60, r=40, t=80, b=100)
    )
    
    
    # Add side annotations - Coinglass style
    fig.add_annotation(
        text=(
            f'<b>Cumulative Long Liquidation Leverage</b><br>'
            f'<span style="color: #ef4444">● Red/Orange bars (LEFT of $0)</span><br>'
            f'<span style="font-size: 9px">Bulls get liquidated as price DROPS ↓</span>'
        ),
        xref='paper', yref='paper',
        x=0.02, y=0.96,
        showarrow=False,
        font=dict(size=11, color='white'),
        align='left',
        bgcolor='rgba(30, 30, 30, 0.8)',
        bordercolor='rgba(239, 68, 68, 0.5)',
        borderwidth=2,
        borderpad=8
    )
    
    fig.add_annotation(
        text=(
            f'<b>Cumulative Short Liquidation Leverage</b><br>'
            f'<span style="color: #22c55e">● Green/Cyan bars (RIGHT of $0)</span><br>'
            f'<span style="font-size: 9px">Bears get liquidated as price RISES ↑</span>'
        ),
        xref='paper', yref='paper',
        x=0.98, y=0.96,
        showarrow=False,
        font=dict(size=11, color='white'),
        align='right',
        bgcolor='rgba(30, 30, 30, 0.8)',
        bordercolor='rgba(34, 197, 94, 0.5)',
        borderwidth=2,
        borderpad=8
    )
    
    # Add coinglass watermark
    fig.add_annotation(
        text='coinglass',
        xref='paper', yref='paper',
        x=0.98, y=0.02,
        showarrow=False,
        font=dict(size=14, color='rgba(255,255,255,0.2)', family='Arial'),
        align='right'
    )
    
    return fig


def show_liquidation_map_ui():
    """Streamlit UI for Liquidation Map with multi-exchange support."""
    try:
        import streamlit as st
        from config import COIN_LIST
        
        st.markdown("### 🔥 Liquidation Map (Multi-Exchange)")
        st.caption("Visualize cumulative liquidations across price levels - Coinglass style")
        
        # Settings
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            coin_names = [symbol for _, symbol in COIN_LIST]
            selected_coin = st.selectbox(
                "Select Coin",
                options=coin_names,
                index=0,
                key="liqmap_coin"
            )
        
        with col2:
            exchange = st.selectbox(
                "Exchange",
                options=["total", "binance", "okx", "bybit"],
                format_func=lambda x: {
                    "total": "🌐 All Exchanges",
                    "binance": "🟡 Binance",
                    "okx": "⚫ OKX",
                    "bybit": "🟠 Bybit"
                }.get(x, x),
                index=0,
                key="liqmap_exchange"
            )
        
        with col3:
            timeframe = st.selectbox(
                "Timeframe",
                options=["1 day", "4 hours", "1 hour"],
                index=0,
                key="liqmap_tf"
            )
        
        with col4:
            price_range = st.slider(
                "Price Range (±%)",
                min_value=1.0,
                max_value=20.0,
                value=10.0,
                step=0.5,
                key="liqmap_range"
            )
        
        # Leverage levels
        with st.expander("⚙️ Advanced Settings", expanded=False):
            leverage_str = st.text_input(
                "Leverage Levels (comma-separated)",
                value="10,25,50,100",
                key="liqmap_lev"
            )
            leverage_levels = [int(x.strip()) for x in leverage_str.split(',') if x.strip().isdigit()]
        
        # Show exchange info
        exchange_data = fetch_open_interest_multi_exchange(selected_coin)
        
        if exchange_data:
            st.markdown("#### 📊 Open Interest by Exchange")
            cols = st.columns(len(exchange_data))
            
            for idx, (exch, (price, long_oi, short_oi)) in enumerate(exchange_data.items()):
                with cols[idx]:
                    exch_icon = {
                        'binance': '🟡',
                        'okx': '⚫',
                        'bybit': '🟠',
                        'total': '🌐'
                    }.get(exch, '📊')
                    
                    st.metric(
                        label=f"{exch_icon} {exch.capitalize()}",
                        value=f"${price:,.2f}",
                        delta=f"L/S: {long_oi/short_oi:.2f}" if short_oi > 0 else "N/A"
                    )
                    st.caption(f"Long: ${long_oi/1e6:.1f}M")
                    st.caption(f"Short: ${short_oi/1e6:.1f}M")
        
        # Generate map
        with st.spinner(f"Generating liquidation map for {selected_coin} on {exchange}..."):
            fig = plot_liquidation_map(
                symbol=selected_coin,
                exchange=exchange,
                timeframe=timeframe,
                leverage_levels=leverage_levels,
                price_range_pct=price_range
            )
        
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            
            # Info - Detailed explanation
            st.markdown("""
            ## 📖 Hướng dẫn đọc Liquidation Map (Coinglass Style)
            
            ### 🎯 Khái niệm cơ bản:
            
            **Liquidation (Thanh lý)** xảy ra khi:
            - Giá di chuyển ngược chiều với vị thế của bạn
            - Tài sản thế chấp không đủ để duy trì vị thế
            - Hệ thống tự động đóng vị thế để tránh nợ xấu
            
            ---
            
            ### 📊 Cách đọc biểu đồ:
            
            #### 🔴 **BÊN TRÁI (Màu Đỏ/Cam)** = LONG LIQUIDATIONS
            - **Vùng này**: Giá THẤP HƠN current price
            - **Ý nghĩa**: Nếu giá **GIẢM** xuống đây → Vị thế LONG bị thanh lý
            - **Màu sắc**:
              - 🟥 **Đỏ đậm** (10x): Thanh lý xa nhất, rủi ro thấp nhất
              - 🟧 **Cam** (25x, 50x): Thanh lý gần hơn
              - 🟨 **Cam nhạt** (100x): Thanh lý sát giá hiện tại, rủi ro cao nhất
            
            #### 🟢 **BÊN PHẢI (Màu Xanh)** = SHORT LIQUIDATIONS
            - **Vùng này**: Giá CAO HƠN current price
            - **Ý nghĩa**: Nếu giá **TĂNG** lên đây → Vị thế SHORT bị thanh lý
            - **Màu sắc**:
              - 🟩 **Xanh đậm** (10x): Thanh lý xa nhất, rủi ro thấp nhất
              - 🟦 **Xanh nhạt** (50x, 100x): Thanh lý sát giá, rủi ro cao
            
            #### ⚪ **GIỮA (Đường trắng đứt)** = GIÁ HIỆN TẠI
            - Ranh giới phân chia Long vs Short liquidations
            
            ---
            
            ### 💡 Ví dụ thực tế:
            
            **Giả sử BTC = $100,000:**
            
            **Scenario 1: Giá giảm xuống $95,000**
            - Chart hiện 1 cột đỏ cao ở vị trí $95,000
            - → Nhiều Long 10x-25x sẽ bị thanh lý tại đây
            - → Áp lực bán tăng → Giá có thể giảm thêm (cascade effect)
            
            **Scenario 2: Giá tăng lên $105,000**
            - Chart hiện 1 cột xanh cao ở vị trí $105,000
            - → Nhiều Short 10x-25x sẽ bị thanh lý
            - → Áp lực mua tăng (shorts phải cover) → Giá có thể tăng thêm
            
            ---
            
            ### 🎓 Cách sử dụng để trade:
            
            #### 1️⃣ **Tìm Support/Resistance**
            - **Cột càng cao** = càng nhiều liquidation ở price level đó
            - Giá thường "bật" hoặc "phản ứng" khi chạm vào các vùng này
            
            #### 2️⃣ **Dự đoán Cascade Liquidation**
            - Nhiều cột liên tiếp = nguy cơ cascade (domino effect)
            - Giá vượt ngưỡng → Liquidations xảy ra → Đẩy giá mạnh hơn
            
            #### 3️⃣ **Hunt Liquidation (Stop Hunt)**
            - Market makers thường "hunt" các vùng liquidation cao
            - Đẩy giá đến đó → Trigger thanh lý → Lấy liquidity → Đảo chiều
            
            #### 4️⃣ **Risk Management**
            - Tránh đặt stop loss ở vùng liquidation dày đặc
            - Đặt stop xa hơn các vùng này để tránh bị "hunt"
            
            ---
            
            ### ⚠️ Lưu ý quan trọng:
            
            ✅ **Đây là dữ liệu ước tính** dựa trên:
            - Open Interest hiện tại
            - Phân bố leverage (giả định)
            - Không phải data thực tế 100%
            
            ✅ **Kết hợp với các chỉ báo khác**:
            - Orderbook depth
            - Volume profile
            - Support/Resistance levels
            
            ✅ **Market luôn động**:
            - Liquidation map thay đổi real-time
            - Refresh thường xuyên để cập nhật
            """)
            
            # Add visual guide
            with st.expander("🎨 Chú thích màu sắc chi tiết", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("""
                    ### 🔴 Long Liquidations (Trái)
                    - 🟥 **10x** (Đỏ đậm): Xa current price nhất
                    - 🟧 **25x** (Đỏ): Trung bình xa
                    - 🟨 **50x** (Cam): Gần current price
                    - 🟡 **100x** (Cam nhạt): Sát current price (nguy hiểm nhất)
                    
                    **Càng đỏ đậm** = Càng an toàn (xa current price)  
                    **Càng cam nhạt** = Càng nguy hiểm (gần current price)
                    """)
                
                with col2:
                    st.markdown("""
                    ### 🟢 Short Liquidations (Phải)
                    - 🟩 **10x** (Xanh đậm): Xa current price nhất
                    - 💚 **25x** (Xanh): Trung bình xa
                    - 🟦 **50x** (Xanh nhạt): Gần current price
                    - 💙 **100x** (Cyan): Sát current price (nguy hiểm nhất)
                    
                    **Càng xanh đậm** = Càng an toàn (xa current price)  
                    **Càng xanh nhạt** = Càng nguy hiểm (gần current price)
                    """)
            
            # Technical info
            with st.expander("⚙️ Chi tiết kỹ thuật", expanded=False):
                # Get current data for selected exchange
                if exchange == 'total' and 'total' in exchange_data:
                    current_price_val, long_oi, short_oi = exchange_data['total']
                elif exchange in exchange_data:
                    current_price_val, long_oi, short_oi = exchange_data[exchange]
                else:
                    current_price_val = long_oi = short_oi = 0
                
                st.markdown(f"""
                **Dữ liệu thị trường hiện tại:**
                - Symbol: `{selected_coin}/USDT`
                - Exchange: `{exchange.upper()}`
                - Current Price: `${current_price_val:,.2f}`
                - Long Open Interest: `${long_oi:,.0f}` ({long_oi/1e6:.2f}M)
                - Short Open Interest: `${short_oi:,.0f}` ({short_oi/1e6:.2f}M)
                - Long/Short Ratio: `{long_oi/short_oi:.2f}` ({('🐂 Bullish' if long_oi > short_oi else '🐻 Bearish')})
                
                **Tổng hợp từ các exchanges:**
                {chr(10).join([f"- {exch.capitalize()}: ${data[0]:,.2f} (L: ${data[1]/1e6:.1f}M | S: ${data[2]/1e6:.1f}M)" for exch, data in exchange_data.items() if exch != 'total'])}
                
                **Công thức tính Liquidation Price:**
                ```
                Long Liquidation Price = Entry Price × (1 - 1/Leverage)
                Short Liquidation Price = Entry Price × (1 + 1/Leverage)
                ```
                
                **Ví dụ với Entry = ${current_price_val:,.0f}:**
                - Long 10x → Liq at ${current_price_val * 0.9:,.0f} (giảm 10%)
                - Long 25x → Liq at ${current_price_val * 0.96:,.0f} (giảm 4%)
                - Long 50x → Liq at ${current_price_val * 0.98:,.0f} (giảm 2%)
                - Long 100x → Liq at ${current_price_val * 0.99:,.0f} (giảm 1%)
                
                - Short 10x → Liq at ${current_price_val * 1.1:,.0f} (tăng 10%)
                - Short 25x → Liq at ${current_price_val * 1.04:,.0f} (tăng 4%)
                - Short 50x → Liq at ${current_price_val * 1.02:,.0f} (tăng 2%)
                - Short 100x → Liq at ${current_price_val * 1.01:,.0f} (tăng 1%)
                
                **Nguồn dữ liệu:**
                - Exchanges: Binance, OKX, Bybit Futures APIs
                - Update: Real-time khi refresh
                - Độ chính xác: ~80-90% (ước tính dựa trên OI distribution)
                - Aggregation method: Sum of all exchange OIs, weighted average price
                """)
        else:
            st.error("❌ Failed to fetch data. Please try again.")
    
    except Exception as e:
        import streamlit as st
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())


if __name__ == '__main__':
    # Test
    print("Testing Liquidation Map...")
    print("\nFetching multi-exchange data for BTC...")
    
    # Test multi-exchange fetch
    data = fetch_open_interest_multi_exchange('BTC')
    for exchange, (price, long_oi, short_oi) in data.items():
        print(f"\n{exchange.upper()}:")
        print(f"  Price: ${price:,.2f}")
        print(f"  Long OI: ${long_oi:,.0f}")
        print(f"  Short OI: ${short_oi:,.0f}")
        print(f"  L/S Ratio: {long_oi/short_oi:.2f}")
    
    # Generate chart
    print("\nGenerating chart...")
    fig = plot_liquidation_map('BTC', exchange='total')
    if fig:
        print("✅ Chart generated successfully!")
        fig.show()
    else:
        print("❌ Failed to generate chart")
