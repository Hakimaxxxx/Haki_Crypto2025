import streamlit as st
import numpy as np
import plotly.graph_objects as go
import pandas as pd

def overlay_whale_alert_chart(
    whale_txs,
    df_ohlcv,
    coin_symbol: str,
    slider_label: str = None,
    slider_step: float = 1.0,
    value_unit: str = "",
    type_map=None,
    color_map=None,
    default_show=True,
    key_prefix=""
):
    """
    Overlay whale alert markers on a price/volume chart with a filter slider.
    Args:
        whale_txs: List of whale transactions (dicts with 'value', 'type', 'time', ...)
        df_ohlcv: DataFrame with 'datetime' and 'close' columns
        coin_symbol: e.g. 'ETH', 'SOL'
        slider_label: Label for the slider
        slider_step: Step for slider (float)
        value_unit: Unit for display (e.g. 'ETH', 'SOL')
        type_map: Dict mapping tx type to label (optional)
        color_map: Dict mapping tx type to color (optional)
        default_show: Default value for the show checkbox
        key_prefix: Unique key prefix for Streamlit widgets
    Returns:
        None (adds overlay to fig_ohlcv in-place)
    """
    if not whale_txs or df_ohlcv is None or df_ohlcv.empty:
        return
    show = st.checkbox(f"Hiển thị bóng Whale Alert trên chart ({coin_symbol})", value=default_show, key=f"{key_prefix}show_whale_balls_{coin_symbol}")
    if not show:
        return
    whale_values_all = [tx.get("value", 0) for tx in whale_txs]
    min_tx = min(whale_values_all)
    max_tx = max(whale_values_all)
    if not slider_label:
        slider_label = f"Lọc theo độ lớn giao dịch Whale ({coin_symbol})"
    filter_value = st.slider(
        slider_label,
        min_value=float(min_tx),
        max_value=float(max_tx),
        value=float(min_tx),
        step=slider_step,
        format="%.2f" if slider_step < 1 else "%.0f",
        key=f"{key_prefix}slider_{coin_symbol}"
    )
    filtered_txs = [tx for tx in whale_txs if tx.get("value", 0) >= filter_value]
    if not filtered_txs:
        return
    whale_times = []
    whale_values = []
    whale_types = []
    whale_texts = []
    for tx in filtered_txs:
        try:
            tx_time = pd.to_datetime(tx.get("time"))
        except:
            continue
        idx = np.argmin(np.abs(df_ohlcv["datetime"] - tx_time))
        chart_time = df_ohlcv.iloc[idx]["datetime"]
        whale_times.append(chart_time)
        whale_values.append(tx.get("value", 0))
        whale_types.append(tx.get("type", "other"))
        label = type_map.get(tx.get("type"), tx.get("type")) if type_map else tx.get("type", "other")
        whale_texts.append(f"{label}: {tx.get('value',0):.2f} {value_unit}<br>Từ: {tx.get('from','')}<br>Đến: {tx.get('to','')}<br>Thời gian: {tx.get('time','')}")
    min_size, max_size = 10, 40
    vmin, vmax = min(whale_values), max(whale_values)
    def scale_size(v):
        if vmax == vmin:
            return (min_size + max_size) // 2
        return min_size + (max_size - min_size) * (v - vmin) / (vmax - vmin)
    sizes = [scale_size(v) for v in whale_values]
    if color_map:
        colors = [color_map.get(t, "#888") for t in whale_types]
    else:
        colors = ["#43a047" if t in ("MUA", "withdraw") else ("#e53935" if t in ("BÁN", "deposit") else "#888") for t in whale_types]
    go = __import__('plotly.graph_objects', fromlist=['Scatter'])
    df_ohlcv_indexed = df_ohlcv.set_index("datetime")
    fig = st.session_state.get(f"fig_ohlcv_{coin_symbol}")
    if fig is None:
        return
    fig.add_trace(go.Scatter(
        x=whale_times,
        y=[df_ohlcv_indexed.loc[t]["close"] for t in whale_times],
        mode="markers",
        marker=dict(size=sizes, color=colors, opacity=0.7, line=dict(width=1, color="#222")),
        name="Whale Alert",
        text=whale_texts,
        hoverinfo="text"
    ))
