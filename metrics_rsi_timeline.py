"""
RSI Timeline Chart - Altcoin Season Index Style

Displays RSI over time with:
- Large timeline chart (like Coinglass Altcoin Season Index)
- Color zones (oversold, neutral, overbought)
- Historical data from DB (1 year+)
- Daily auto-sync to DB and CSV backup
- No API reload on every view
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import json
from pathlib import Path


def load_rsi_history_from_db(symbol: str, timeframe: str = "1d", days: int = 365) -> Optional[pd.DataFrame]:
    """
    Load RSI historical data from MongoDB.
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH')
        timeframe: RSI timeframe ('1d', '4h', etc.)
        days: Number of days to look back
    
    Returns:
        DataFrame with columns: ['timestamp', 'rsi'] or None
    """
    try:
        from cloud_db import db
        
        if not db.available():
            print(f"[RSI Timeline] DB not available")
            return None
        
        # Query from rsi_history collection
        collection = db.get_collection("rsi_history")
        
        # Calculate date range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        
        # Query documents
        query = {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "timestamp": {
                "$gte": start_time.isoformat(),
                "$lte": end_time.isoformat()
            }
        }
        
        docs = list(collection.find(query).sort("timestamp", 1))
        
        if not docs:
            print(f"[RSI Timeline] No data found for {symbol} {timeframe}")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(docs)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df[['timestamp', 'rsi']].sort_values('timestamp')
        
        print(f"[RSI Timeline] Loaded {len(df)} records for {symbol} {timeframe}")
        return df
        
    except Exception as e:
        print(f"[RSI Timeline] Error loading from DB: {e}")
        return None


def load_rsi_history_from_csv(symbol: str, timeframe: str = "1d") -> Optional[pd.DataFrame]:
    """
    Load RSI history from CSV backup.
    
    CSV structure:
    timestamp,symbol,timeframe,rsi
    2024-10-29T00:00:00Z,BTC,1d,65.3
    ...
    """
    try:
        csv_path = Path(f"rsi_history_{timeframe}.csv")
        
        if not csv_path.exists():
            print(f"[RSI Timeline] CSV not found: {csv_path}")
            return None
        
        df = pd.read_csv(csv_path)
        df = df[df['symbol'] == symbol.upper()]
        
        if df.empty:
            print(f"[RSI Timeline] No data for {symbol} in CSV")
            return None
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df[['timestamp', 'rsi']].sort_values('timestamp')
        
        print(f"[RSI Timeline] Loaded {len(df)} records from CSV for {symbol}")
        return df
        
    except Exception as e:
        print(f"[RSI Timeline] Error loading CSV: {e}")
        return None


def plot_rsi_timeline(
    symbol: str,
    timeframe: str = "1d",
    days: int = 365,
    width: int = 1200,
    height: int = 500,
    show_zones: bool = True,
    show_value_line: bool = True
) -> Optional[go.Figure]:
    """
    Create Altcoin Season Index style RSI timeline chart.
    
    Args:
        symbol: Coin symbol
        timeframe: RSI timeframe
        days: Days of history to show
        width: Chart width
        height: Chart height
        show_zones: Show colored RSI zones (oversold/overbought)
        show_value_line: Show current RSI value line
    
    Returns:
        Plotly Figure or None
    """
    # Try DB first, fallback to CSV
    df = load_rsi_history_from_db(symbol, timeframe, days)
    if df is None or df.empty:
        df = load_rsi_history_from_csv(symbol, timeframe)
    
    if df is None or df.empty:
        print(f"[RSI Timeline] No data available for {symbol}")
        return None
    
    # Create figure
    fig = go.Figure()
    
    # Add colored zones if enabled
    if show_zones:
        # Oversold zone (0-30) - Green/Brown gradient
        fig.add_shape(
            type="rect",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=0,
            y1=30,
            fillcolor="rgba(139, 69, 19, 0.3)",  # Brown (oversold = buy opportunity)
            line_width=0,
            layer="below"
        )
        
        # Neutral zone (30-70) - Transparent
        fig.add_shape(
            type="rect",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=30,
            y1=70,
            fillcolor="rgba(0, 0, 0, 0.05)",
            line_width=0,
            layer="below"
        )
        
        # Overbought zone (70-100) - Blue gradient (like Altcoin Season)
        fig.add_shape(
            type="rect",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=70,
            y1=100,
            fillcolor="rgba(100, 149, 237, 0.3)",  # Cornflower blue
            line_width=0,
            layer="below"
        )
    
    # Add RSI line (main chart)
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['rsi'],
        mode='lines',
        name=f'RSI {timeframe}',
        line=dict(
            color='#4CAF50',  # Green like Altcoin Season Index
            width=2
        ),
        hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>RSI: %{y:.1f}<extra></extra>'
    ))
    
    # Add current value indicator line (horizontal dashed line)
    if show_value_line and not df.empty:
        current_rsi = df['rsi'].iloc[-1]
        fig.add_shape(
            type="line",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=current_rsi,
            y1=current_rsi,
            line=dict(
                color="white",
                width=1,
                dash="dot"
            )
        )
        
        # Add text annotation for current value
        fig.add_annotation(
            x=df['timestamp'].iloc[-1],
            y=current_rsi,
            text=f"{current_rsi:.0f}",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            xshift=10,
            font=dict(size=20, color="white", family="Arial Black"),
            bgcolor="rgba(0,0,0,0.5)",
            borderpad=4
        )
    
    # Add reference lines at 30 and 70
    for level, label in [(30, "Oversold"), (70, "Overbought")]:
        fig.add_shape(
            type="line",
            x0=df['timestamp'].min(),
            x1=df['timestamp'].max(),
            y0=level,
            y1=level,
            line=dict(color="rgba(255,255,255,0.3)", width=1, dash="dash")
        )
    
    # Add gradient bar at top (like Altcoin Season Index)
    # Brown (oversold) -> Neutral -> Blue (overbought)
    fig.add_shape(
        type="rect",
        x0=df['timestamp'].min(),
        x1=df['timestamp'].min() + (df['timestamp'].max() - df['timestamp'].min()) * 0.3,
        y0=105,
        y1=110,
        fillcolor="rgba(139, 69, 19, 0.8)",  # Bitcoin Season (brown)
        line_width=0
    )
    
    fig.add_shape(
        type="rect",
        x0=df['timestamp'].min() + (df['timestamp'].max() - df['timestamp'].min()) * 0.7,
        x1=df['timestamp'].max(),
        y0=105,
        y1=110,
        fillcolor="rgba(100, 149, 237, 0.8)",  # Altcoin Season (blue)
        line_width=0
    )
    
    # Add labels for gradient bar
    fig.add_annotation(
        x=df['timestamp'].min() + (df['timestamp'].max() - df['timestamp'].min()) * 0.15,
        y=107.5,
        text="<b>Oversold</b>",
        showarrow=False,
        font=dict(size=12, color="white"),
        bgcolor="rgba(0,0,0,0)"
    )
    
    fig.add_annotation(
        x=df['timestamp'].min() + (df['timestamp'].max() - df['timestamp'].min()) * 0.85,
        y=107.5,
        text="<b>Overbought</b>",
        showarrow=False,
        font=dict(size=12, color="white"),
        bgcolor="rgba(0,0,0,0)"
    )
    
    # Layout styling (dark theme like Coinglass)
    fig.update_layout(
        title=dict(
            text=f"<b>{symbol.upper()} RSI Timeline</b>",
            font=dict(size=24, color="white"),
            x=0.02,
            y=0.98
        ),
        xaxis=dict(
            title="",
            showgrid=False,
            color="white",
            rangeslider=dict(visible=False)
        ),
        yaxis=dict(
            title="",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)",
            color="white",
            range=[0, 110],  # Extended to show gradient bar
            fixedrange=True
        ),
        plot_bgcolor="#1e2130",  # Dark background
        paper_bgcolor="#1e2130",
        hovermode="x unified",
        width=width,
        height=height,
        margin=dict(l=50, r=50, t=80, b=50),
        showlegend=False
    )
    
    return fig


def get_rsi_summary_stats(symbol: str, timeframe: str = "1d", days: int = 30) -> Dict[str, Any]:
    """
    Get summary statistics for RSI over recent period.
    
    Returns dict with:
    - current: Current RSI value
    - avg_30d: 30-day average
    - min_30d: 30-day minimum
    - max_30d: 30-day maximum
    - trend: 'oversold', 'neutral', 'overbought'
    """
    df = load_rsi_history_from_db(symbol, timeframe, days)
    if df is None or df.empty:
        df = load_rsi_history_from_csv(symbol, timeframe)
    
    if df is None or df.empty:
        return {}
    
    current = df['rsi'].iloc[-1]
    
    # Determine trend
    if current < 30:
        trend = "oversold"
    elif current > 70:
        trend = "overbought"
    else:
        trend = "neutral"
    
    return {
        "current": float(current),
        "avg_30d": float(df['rsi'].mean()),
        "min_30d": float(df['rsi'].min()),
        "max_30d": float(df['rsi'].max()),
        "trend": trend,
        "data_points": len(df),
        "oldest_date": df['timestamp'].min().isoformat(),
        "newest_date": df['timestamp'].max().isoformat()
    }
