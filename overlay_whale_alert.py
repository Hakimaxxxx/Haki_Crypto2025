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
    if min_tx == max_tx:
        st.warning("Không có sự khác biệt giữa giá trị nhỏ nhất và lớn nhất. Slider sẽ không hoạt động.")
        return
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
    import logging
    debug_log = []
    whale_times = []
    whale_values = []
    whale_types = []
    whale_texts = []
    for tx in filtered_txs:
        try:
            tx_time_raw = tx.get("time")
            tx_time = pd.to_datetime(tx_time_raw)
            debug_log.append(f"TX: {tx.get('hash','')} | time_raw: {tx_time_raw} | to_datetime: {tx_time}")
            # Marker và chart đều dùng UTC
            if tx_time.tzinfo is None or tx_time.tzinfo.utcoffset(tx_time) is None:
                tx_time = tx_time.tz_localize("UTC")
            debug_log.append(f"TX: {tx.get('hash','')} | after localize: {tx_time}")
        except Exception as e:
            debug_log.append(f"TX: {tx.get('hash','')} | ERROR time parse: {e}")
            continue
        # Tìm index gần nhất
        try:
            idx = np.argmin(np.abs(df_ohlcv["datetime"] - tx_time))
            chart_time_utc = df_ohlcv.iloc[idx]["datetime"]
            if chart_time_utc.tzinfo is not None:
                chart_time_utc = chart_time_utc.tz_convert("UTC")
            debug_log.append(f"TX: {tx.get('hash','')} | chart_time_utc: {chart_time_utc}")
            whale_times.append(chart_time_utc)
            whale_values.append(tx.get("value", 0))
            whale_types.append(tx.get("type", "other"))
            label = type_map.get(tx.get("type"), tx.get("type")) if type_map else tx.get("type", "other")
            # Tooltip chuyển sang GMT+7 khi hiển thị
            try:
                display_time = tx_time.tz_convert("Asia/Bangkok")
                display_time_str = display_time.strftime("%Y-%m-%d %H:%M:%S (GMT+7)")
            except:
                display_time_str = tx.get("time", "")
            whale_texts.append(f"{label}: {tx.get('value',0):.2f} {value_unit}<br>Từ: {tx.get('from','')}<br>Đến: {tx.get('to','')}<br>Thời gian: {display_time_str}")
        except Exception as e:
            debug_log.append(f"TX: {tx.get('hash','')} | ERROR chart index: {e}")
            continue
    # Hiển thị debug log trên Streamlit để kiểm tra
    st.expander("Debug whale marker time mapping").write("\n".join(debug_log))
    # Compact mode: aggregate markers by (candle time, type) to reduce clutter
    from collections import defaultdict
    grouped = defaultdict(lambda: {"value_sum": 0.0, "texts": [], "time": None, "type": None})
    for t, v, ty, txt in zip(whale_times, whale_values, whale_types, whale_texts):
        key = (t, ty)
        g = grouped[key]
        g["time"] = t
        g["type"] = ty
        g["value_sum"] += float(v)
        if len(g["texts"]) < 3:
            g["texts"].append(txt)

    whale_times = []
    whale_values = []
    whale_types = []
    whale_texts = []
    for (_, ty), g in grouped.items():
        whale_times.append(g["time"])
        whale_values.append(g["value_sum"])
        whale_types.append(g["type"])
        extra = "" if len(g["texts"]) <= 3 else f"<br>... (+{len(g['texts'])-3} more)"
        whale_texts.append("<br>".join(g["texts"]) + extra)

    # Small, subtle markers to avoid covering price path
    min_size, max_size = 6, 16
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
    # Build y values from close price at mapped candle times, with safeguards
    df_ohlcv_indexed = df_ohlcv.set_index("datetime")
    base_closes = []
    for t in whale_times:
        try:
            val = df_ohlcv_indexed.loc[t]["close"]
            # If duplicate index returns a Series, take the first
            if hasattr(val, "iloc"):
                val = val.iloc[0]
        except Exception:
            # As a fallback, pick nearest candle
            try:
                nearest_idx = df_ohlcv_indexed.index.get_indexer([t], method="nearest")[0]
                val = df_ohlcv_indexed.iloc[nearest_idx]["close"]
            except Exception:
                val = None
        base_closes.append(val)
    # Filter out any entries that failed to map (should be rare)
    filtered = [(t, v, ty, txt, sz, col) for t, v, ty, txt, sz, col in zip(whale_times, base_closes, whale_types, whale_texts, sizes, colors) if v is not None]
    if not filtered:
        return
    whale_times, base_closes, whale_types, whale_texts, sizes, colors = map(list, zip(*filtered))

    # Jitter duplicated times slightly to avoid perfect overlap on x only (keep y exactly on price path)
    time_counts = defaultdict(int)
    jittered_times = []
    jittered_closes = []
    price_eps_pct = 0.0  # keep on the path
    for t, v in zip(whale_times, base_closes):
        time_counts[t] += 1
        dup_idx = time_counts[t] - 1
        # add tiny seconds jitter on x, no y change
        jittered_times.append(t + pd.Timedelta(milliseconds=100 * dup_idx))
        jittered_closes.append(float(v) * (1 + price_eps_pct * dup_idx))

    # Optional: symbol per type to improve visual distinction
    type_to_symbol = {
        "BUY": "triangle-up",
        "SELL": "triangle-down",
        "MUA": "triangle-up",
        "BÁN": "triangle-down",
        "withdraw": "triangle-up",
        "deposit": "triangle-down",
        "N/A": "circle",
        None: "circle"
    }
    symbols = [type_to_symbol.get(t, "circle") for t in whale_types]

    fig = st.session_state.get(f"fig_ohlcv_{coin_symbol}")
    if fig is None:
        return
    # Split into categories so we can draw N/A as background and BUY/SELL on top
    def categorize(t):
        t_up = (t or "").upper()
        if t_up in ("BUY", "MUA", "WITHDRAW"):
            return "buy"
        if t_up in ("SELL", "BÁN", "DEPOSIT"):
            return "sell"
        return "na"

    items = list(zip(jittered_times, jittered_closes, whale_types, whale_texts, sizes, colors, symbols))
    na_items = [it for it in items if categorize(it[2]) == "na"]
    sell_items = [it for it in items if categorize(it[2]) == "sell"]
    buy_items = [it for it in items if categorize(it[2]) == "buy"]

    def add_trace_for(items_list, label, color_override=None, opacity=0.6, size_scale=1.0, showlegend=True, legendgroup="Whale Alert"):
        if not items_list:
            return
        xs, ys, tys, txts, szs, cols, syms = map(list, zip(*items_list))
        # Apply overrides for N/A background
        if color_override is not None:
            cols = [color_override for _ in cols]
        if size_scale != 1.0:
            szs = [max(6, s * size_scale) for s in szs]
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(
                size=szs,
                color=cols,
                symbol=syms,
                opacity=opacity,
                line=dict(width=0.5, color="#222")
            ),
            name=label,
            legendgroup=legendgroup,
            showlegend=showlegend,
            text=txts,
            hoverinfo="text"
        ))

    # Draw N/A first with muted style so BUY/SELL sit on top visually
    add_trace_for(
        na_items,
        label="Whale Alert (N/A)",
        color_override="#949090",  # muted gray
        opacity=0.5,
        size_scale=2.0,
        showlegend=False
    )
    # Then SELL in vivid red
    add_trace_for(
        sell_items,
        label="Whale Alert (SELL)",
        color_override="#e53935",
        opacity=0.8,
        size_scale=2.0,
        showlegend=True
    )
    # Finally BUY in vivid green/blue
    add_trace_for(
        buy_items,
        label="Whale Alert (BUY)",
        color_override="#3df78a",
        opacity=0.8,
        size_scale=2.0,
        showlegend=True
    )
