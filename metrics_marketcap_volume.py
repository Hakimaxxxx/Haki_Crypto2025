import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os, time

_MC_CACHE = {"data": None, "ts": 0}

def load_global_marketcap_cached(ttl: int = 180):
    """Return latest total market cap & volume from marketcap_history.csv if available."""
    now = time.time()
    if _MC_CACHE["data"] and now - _MC_CACHE["ts"] < ttl:
        return _MC_CACHE["data"]
    market_file = "marketcap_history.csv"
    if not os.path.exists(market_file):
        return None
    try:
        df_market = pd.read_csv(market_file)
        if df_market.empty:
            return None
        # Expect columns: timestamp, market_cap, volume_1d (existing format in project)
        if 'timestamp' in df_market.columns:
            df_market['timestamp'] = pd.to_datetime(df_market['timestamp'], errors='coerce')
            df_market = df_market.dropna(subset=['timestamp']).sort_values('timestamp')
        last = df_market.iloc[-1]
        rec = {
            'total_market_cap_usd': float(last.get('market_cap', 0)),
            'volume_1d': float(last.get('volume_1d', 0)),
            'timestamp': str(last.get('timestamp'))
        }
        _MC_CACHE['data'] = rec
        _MC_CACHE['ts'] = now
        return rec
    except Exception:
        return None

def show_marketcap_volume_chart(key_suffix=None):
    with st.expander("Total Market Cap (USD) & Volume 1D (USD, scaled)", expanded=True):
        timeframe = st.selectbox("Chọn Timeframe:", ["4H", "1D", "7D", "1M", "3M"], index=1, key="marketcap_timeframe")
        market_file = "marketcap_history.csv"
        if os.path.exists(market_file):
            try:
                df_market = pd.read_csv(market_file)
                df_market["timestamp"] = pd.to_datetime(df_market["timestamp"], errors='coerce')
                df_market = df_market.dropna(subset=["timestamp"]).sort_values("timestamp")
                # Chỉ lấy 30 ngày gần nhất nếu quá dài
                if len(df_market) > 0:
                    last_time = df_market["timestamp"].iloc[-1]
                    df_market = df_market[df_market["timestamp"] >= last_time - pd.Timedelta(days=30)]

                # --- Group theo timeframe lớn ---
                df_vol = df_market.copy()
                if timeframe == "4H":
                    df_vol["tf"] = df_vol["timestamp"].dt.floor('4H')
                elif timeframe == "1D":
                    df_vol["tf"] = df_vol["timestamp"].dt.floor('1D')
                elif timeframe == "7D":
                    df_vol["tf"] = df_vol["timestamp"].dt.to_period('W').apply(lambda r: r.start_time)
                elif timeframe == "1M":
                    df_vol["tf"] = df_vol["timestamp"].dt.to_period('M').apply(lambda r: r.start_time)
                elif timeframe == "3M":
                    q = ((df_vol["timestamp"].dt.month - 1) // 3) + 1
                    df_vol["tf"] = df_vol["timestamp"].dt.year.astype(str) + '-Q' + q.astype(str)
                    df_vol["tf"] = pd.to_datetime(df_vol["timestamp"].dt.year.astype(str) + '-' + ((q-1)*3+1).astype(str) + '-01')
                else:
                    df_vol["tf"] = df_vol["timestamp"]
                idx_last_per = df_vol.groupby("tf")['timestamp'].idxmax()
                df_vol = df_vol.loc[idx_last_per]
                df_vol = df_vol.sort_values("timestamp")

                # Scale volume
                volume_scaled = df_vol["volume_1d"] / (df_market["market_cap"].max() * 0.15)

                fig = go.Figure()
                fig.add_trace(go.Bar(x=df_vol["timestamp"], y=volume_scaled, name="Volume 1D (USD, scaled)", marker_color="orange", yaxis="y2", opacity=0.5))
                fig.add_trace(go.Scatter(x=df_market["timestamp"], y=df_market["market_cap"], name="Total Market Cap (USD)", line=dict(color="royalblue"), yaxis="y1"))

                def human_format(num):
                    num = float(num)
                    if num >= 1e12:
                        return f"${num/1e12:.2f}T"
                    elif num >= 1e9:
                        return f"${num/1e9:.2f}B"
                    elif num >= 1e6:
                        return f"${num/1e6:.2f}M"
                    elif num >= 1e3:
                        return f"${num/1e3:.2f}K"
                    else:
                        return f"${num:.2f}"

                if len(df_market) > 0:
                    last_row = df_market.iloc[-1]
                    mcap_val = last_row["market_cap"]
                    vol_val = last_row["volume_1d"]
                    mcap_str = f"Market Cap: {human_format(mcap_val)}"
                    vol_str = f"Volume :{human_format(vol_val)}"
                    annotation_text = f"<b>{mcap_str}</b><br><b>{vol_str}</b>"
                    fig.add_annotation(
                        xref="paper", yref="paper",
                        x=0.01, y=0.99, xanchor="left", yanchor="top",
                        text=annotation_text,
                        showarrow=False,
                        align="left",
                        font=dict(size=13, color="black"),
                        bgcolor="rgba(255,255,255,0.7)",
                        bordercolor="black",
                        borderwidth=1
                    )

                fig.update_layout(
                    title="Total Market Cap (USD) & Volume 1D (USD, scaled)",
                    xaxis_title="Time",
                    yaxis=dict(title="Market Cap (USD)", side="left", showgrid=False),
                    yaxis2=dict(title="Volume 1D (USD, scaled)", overlaying="y", side="right", showgrid=False, anchor="x",
                               range=[0, 1.2],
                               showticklabels=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True, key="marketcap_volume_combined", config={'displaylogo': False, 'responsive': True})
            except Exception as e:
                st.warning(f"Không thể đọc dữ liệu marketcap/volume: {e}")
