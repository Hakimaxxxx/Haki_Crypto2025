"""
Coinglass-Style Liquidation Heatmap

Features:
- Extended historical data (30+ days) from Binance
- Separate Long/Short liquidation visualization
- Overlay liquidation zones on price chart
- Clear color coding: Green (Long liquidations) / Red (Short liquidations)
"""

import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Optional, Literal
import time


def fetch_binance_liquidations_extended(
    symbol: str = "BTCUSDT",
    days: int = 30,
    interval: str = "1h"
) -> pd.DataFrame:
    """
    Fetch liquidation data using aggregated approach (since Binance forceOrders requires API key).
    
    Strategy: Use OKX liquidation data (public API) + Binance price data for correlation.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        days: Number of days to fetch
        interval: Aggregation interval ('1h', '4h', '1d')
    
    Returns:
        DataFrame with columns: datetime, price, long_liq, short_liq, total_liq
    """
    try:
        # Map Binance symbol to OKX
        base = symbol.replace('USDT', '').replace('BUSD', '')
        okx_symbol = f"{base}-USDT-SWAP"
        
        print(f"[Liquidations] Fetching {days} days for {base} from OKX + extended sources...")
        
        # Use existing OKX liquidation fetcher with extended timeframe
        from datetime import datetime, timezone
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)
        
        # Import from metrics_liquidation_okx
        import metrics_liquidation_okx as mliq
        
        # Fetch from multiple sources
        df = mliq.fetch_liquidations_multi(
            asset_symbol=base,
            start_dt=start_dt.replace(tzinfo=None),
            end_dt=end_dt.replace(tzinfo=None),
            sources=["OKX", "BINANCE"],  # Will try both
            okx_inst=okx_symbol
        )
        
        if df.empty:
            print("[Liquidations] No data from OKX, trying direct OKX range fetch...")
            df = mliq.fetch_okx_liquidation_range(
                symbol=okx_symbol,
                start_dt=start_dt.replace(tzinfo=None),
                end_dt=end_dt.replace(tzinfo=None),
                max_pages=100,  # Allow more pages for extended data
                overall_timeout=30.0  # Longer timeout for 30 days
            )
        
        if df.empty:
            print("[Liquidations] No data available")
            return pd.DataFrame()
        
        # Parse side information from OKX data
        # OKX posSide: 'long' = long position liquidated, 'short' = short position liquidated
        if 'posSide' in df.columns:
            df['long_liq'] = df.apply(
                lambda x: x['size'] if x.get('posSide', '').lower() == 'long' else 0,
                axis=1
            )
            df['short_liq'] = df.apply(
                lambda x: x['size'] if x.get('posSide', '').lower() == 'short' else 0,
                axis=1
            )
        elif 'side' in df.columns:
            # Fallback: infer from side
            df['long_liq'] = df.apply(
                lambda x: x['size'] if x.get('side', '').upper() == 'BUY' else 0,
                axis=1
            )
            df['short_liq'] = df.apply(
                lambda x: x['size'] if x.get('side', '').upper() == 'SELL' else 0,
                axis=1
            )
        else:
            # Can't determine direction, split evenly as placeholder
            df['long_liq'] = df['size'] / 2
            df['short_liq'] = df['size'] / 2
        
        print(f"[Liquidations] ✓ Total: {len(df)} liquidations")
        print(f"  Long liquidations: {(df['long_liq'] > 0).sum()}")
        print(f"  Short liquidations: {(df['short_liq'] > 0).sum()}")
        
        return df
        
    except Exception as e:
        print(f"[Liquidations] Error: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def aggregate_liquidations_by_price_time(
    df: pd.DataFrame,
    price_bins: int = 100,
    time_bins: int = 72
) -> tuple:
    """
    Aggregate liquidations into price-time bins.
    
    Returns:
        (long_matrix, short_matrix, price_edges, time_edges)
    """
    if df.empty:
        return None, None, None, None
    
    # Create price bins
    price_min = df['price'].min()
    price_max = df['price'].max()
    price_range = price_max - price_min
    price_step = price_range / price_bins if price_range > 0 else 1
    
    df['price_bin'] = ((df['price'] - price_min) / price_step).astype(int).clip(0, price_bins - 1)
    
    # Create time bins
    df['time_bin'] = pd.cut(df['datetime'], bins=time_bins, labels=False)
    
    # Aggregate by bins
    long_agg = df.groupby(['price_bin', 'time_bin'])['long_liq'].sum().reset_index()
    short_agg = df.groupby(['price_bin', 'time_bin'])['short_liq'].sum().reset_index()
    
    # Create matrices
    long_matrix = pd.pivot_table(
        long_agg,
        values='long_liq',
        index='price_bin',
        columns='time_bin',
        fill_value=0
    )
    
    short_matrix = pd.pivot_table(
        short_agg,
        values='short_liq',
        index='price_bin',
        columns='time_bin',
        fill_value=0
    )
    
    # Calculate edges for visualization
    price_edges = [price_min + i * price_step for i in range(price_bins + 1)]
    
    time_min = df['datetime'].min()
    time_max = df['datetime'].max()
    time_delta = (time_max - time_min) / time_bins
    time_edges = [time_min + i * time_delta for i in range(time_bins + 1)]
    
    return long_matrix, short_matrix, price_edges, time_edges


def plot_coinglass_style_liquidation(
    symbol: str = "BTCUSDT",
    days: int = 30,
    price_bins: int = 100,
    time_bins: int = 72,
    threshold_percentile: float = 50,  # Only show top 50% liquidations
    show_price_overlay: bool = True
) -> go.Figure:
    """
    Create Coinglass-style liquidation heatmap.
    
    Features:
    - Green zones: Long liquidations (bulls killed)
    - Red zones: Short liquidations (bears killed)
    - Overlay on price chart
    - Clear visual separation
    
    Args:
        symbol: Trading pair
        days: Historical period
        price_bins: Number of price levels
        time_bins: Number of time periods
        threshold_percentile: Only show liquidations above this percentile
        show_price_overlay: Whether to overlay price candles
    
    Returns:
        Plotly figure
    """
    print(f"[Coinglass Heatmap] Creating for {symbol}, {days} days")
    
    # Fetch liquidation data
    df_liq = fetch_binance_liquidations_extended(symbol, days=days)
    
    if df_liq.empty:
        print("[Coinglass Heatmap] No liquidation data available")
        return None
    
    # Aggregate into bins
    long_matrix, short_matrix, price_edges, time_edges = aggregate_liquidations_by_price_time(
        df_liq,
        price_bins=price_bins,
        time_bins=time_bins
    )
    
    if long_matrix is None:
        return None
    
    # Apply threshold (only show significant liquidations)
    long_threshold = long_matrix.values.flatten()
    long_threshold = long_threshold[long_threshold > 0]
    if len(long_threshold) > 0:
        long_cutoff = pd.Series(long_threshold).quantile(threshold_percentile / 100)
        long_matrix = long_matrix.where(long_matrix >= long_cutoff, 0)
        print(f"[Coinglass] Long liq cutoff: {long_cutoff:.2f}, max: {long_matrix.max().max():.2f}")
    
    short_threshold = short_matrix.values.flatten()
    short_threshold = short_threshold[short_threshold > 0]
    if len(short_threshold) > 0:
        short_cutoff = pd.Series(short_threshold).quantile(threshold_percentile / 100)
        short_matrix = short_matrix.where(short_matrix >= short_cutoff, 0)
        print(f"[Coinglass] Short liq cutoff: {short_cutoff:.2f}, max: {short_matrix.max().max():.2f}")
    
    print(f"[Coinglass] Long matrix shape: {long_matrix.shape}, non-zero: {(long_matrix > 0).sum().sum()}")
    print(f"[Coinglass] Short matrix shape: {short_matrix.shape}, non-zero: {(short_matrix > 0).sum().sum()}")
    
    # Fetch OHLCV for price overlay
    df_price = None
    if show_price_overlay:
        try:
            from ohlcv_multi_source import fetch_binance_ohlcv_extended
            df_price = fetch_binance_ohlcv_extended(symbol, interval='1h', days=days)
        except Exception as e:
            print(f"[Coinglass Heatmap] Could not fetch price data: {e}")
    
    # Create figure with subplots
    fig = make_subplots(
        rows=1, cols=1,
        specs=[[{"secondary_y": False}]],
        subplot_titles=[f"{symbol} Liquidation Heatmap ({days} days)"]
    )
    
    # Y-axis: price levels (centers of bins)
    y_prices = [(price_edges[i] + price_edges[i+1]) / 2 for i in range(len(price_edges) - 1)]
    
    # X-axis: time centers (convert Timestamp to datetime for plotting)
    x_times = []
    for i in range(len(time_edges) - 1):
        # Calculate midpoint using timestamps
        t1 = pd.Timestamp(time_edges[i])
        t2 = pd.Timestamp(time_edges[i+1])
        mid = t1 + (t2 - t1) / 2
        x_times.append(mid)
    
    # Add Long Liquidation Heatmap (Green - Bulls Killed)
    fig.add_trace(
        go.Heatmap(
            z=long_matrix.values,
            x=x_times,
            y=y_prices,
            colorscale=[[0, 'rgba(0,0,0,0)'], [0.3, 'rgba(76, 175, 80, 0.5)'], [1, 'rgba(76, 175, 80, 0.9)']],  # More visible
            showscale=True,
            colorbar=dict(
                title="Long Liq<br>(Bulls Killed)",
                x=1.15,
                len=0.4,
                y=0.75
            ),
            name="Long Liquidations",
            hovertemplate="Time: %{x}<br>Price: $%{y:,.2f}<br>Long Liq: %{z:,.2f}<extra></extra>",
            zsmooth=False  # Disable smoothing for clearer zones
        )
    )
    
    # Add Short Liquidation Heatmap (Red - Bears Killed)
    fig.add_trace(
        go.Heatmap(
            z=short_matrix.values,
            x=x_times,
            y=y_prices,
            colorscale=[[0, 'rgba(0,0,0,0)'], [0.3, 'rgba(244, 67, 54, 0.5)'], [1, 'rgba(244, 67, 54, 0.9)']],  # More visible
            showscale=True,
            colorbar=dict(
                title="Short Liq<br>(Bears Killed)",
                x=1.15,
                len=0.4,
                y=0.25
            ),
            name="Short Liquidations",
            hovertemplate="Time: %{x}<br>Price: $%{y:,.2f}<br>Short Liq: %{z:,.2f}<extra></extra>",
            zsmooth=False  # Disable smoothing for clearer zones
        )
    )
    
    # Overlay price candles
    if df_price is not None and not df_price.empty:
        fig.add_trace(
            go.Candlestick(
                x=df_price['datetime'],
                open=df_price['open'],
                high=df_price['high'],
                low=df_price['low'],
                close=df_price['close'],
                name="Price",
                increasing_line_color='#26a69a',
                decreasing_line_color='#ef5350',
                opacity=0.8,
                showlegend=True
            )
        )
    
    # Add current price line
    try:
        current_price_url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
        resp = requests.get(current_price_url, timeout=5)
        current_price = float(resp.json()['price'])
        
        fig.add_hline(
            y=current_price,
            line_dash="dash",
            line_color="#00bcd4",
            line_width=2,
            annotation_text=f"Current: ${current_price:,.2f}",
            annotation_position="right"
        )
    except Exception:
        pass
    
    # Update layout
    fig.update_layout(
        title=f"<b>{symbol} Liquidation Heatmap</b> - Coinglass Style<br><sub>Green: Long liquidations (bulls killed) | Red: Short liquidations (bears killed)</sub>",
        xaxis_title="Time",
        yaxis_title="Price (USD)",
        template='plotly_dark',
        hovermode='closest',
        height=700,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Y-axis: Normal orientation (high price at top, low price at bottom)
    # Remove the reversed setting to get correct orientation
    
    return fig


def streamlit_coinglass_liquidation_ui():
    """Streamlit UI for Coinglass-style liquidation heatmap."""
    import streamlit as st
    
    st.title("🔥 Liquidation Heatmap - Coinglass Style")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        symbol = st.selectbox(
            "Select Symbol",
            options=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
            index=0
        )
    
    with col2:
        days = st.selectbox(
            "Timeframe",
            options=[7, 14, 30, 60, 90],
            format_func=lambda x: f"{x} days",
            index=2  # Default 30 days
        )
    
    with col3:
        threshold = st.slider(
            "Threshold %",
            min_value=0,
            max_value=90,
            value=50,
            step=10,
            help="Only show top X% of liquidations"
        )
    
    with st.expander("Advanced Settings", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            price_bins = st.slider("Price Resolution", 50, 200, 100)
        with col_b:
            time_bins = st.slider("Time Resolution", 24, 144, 72)
        
        show_price = st.checkbox("Overlay Price Candles", value=True)
    
    if st.button("🔄 Generate Heatmap", type="primary"):
        with st.spinner(f"Fetching {days} days of liquidation data from Binance..."):
            fig = plot_coinglass_style_liquidation(
                symbol=symbol,
                days=days,
                price_bins=price_bins,
                time_bins=time_bins,
                threshold_percentile=threshold,
                show_price_overlay=show_price
            )
        
        if fig is None:
            st.error("❌ Could not generate heatmap. No liquidation data available.")
        else:
            st.plotly_chart(fig, use_container_width=True)
            
            # Stats
            st.subheader("📊 Liquidation Statistics")
            # You can add stats here after implementation


if __name__ == "__main__":
    # Test
    print("Testing Coinglass-style liquidation heatmap...")
    fig = plot_coinglass_style_liquidation("BTCUSDT", days=7, price_bins=80, time_bins=48)
    
    if fig:
        print("✓ Heatmap created successfully")
        # fig.show()  # Uncomment to display in browser
    else:
        print("✗ Failed to create heatmap")
